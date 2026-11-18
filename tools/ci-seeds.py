#!/usr/bin/env python3
"""Restore the Changxing 60 CI inputs a clean checkout cannot carry.

Small sanitized seeds (boot/misc templates, UMS9620 baseline config, static
busybox) are committed under devices/changxing60/ci-seeds; they hold no stock
kernel, firmware or vendor userspace. The clean OpenWrt base and the factory
defaults are too large for git and travel as one hash-pinned release asset
recorded in tools/ci-base.lock.json. Everything lands at the paths the
bootstrap gate (tools/ci-inputs.py create) and the release entry point expect.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import runpy
import shutil
import struct
import tarfile
import urllib.request
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]
SEEDS = TOP / 'devices/changxing60/ci-seeds'
BASE_MEMBERS = {'base-e5.tar.gz', 'clean-openwrt-base.tar'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1 << 20), b''):
            digest.update(data)
    return digest.hexdigest()


def place(relative, data, mode=0o644):
    target = TOP / relative
    if target.exists() or target.is_symlink():
        raise ValueError('CI seed destination already exists: ' + relative)
    if any(p.is_symlink() for p in target.parents):
        raise ValueError('CI seed destination contains a symlink: ' + relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(mode)


def base_lock():
    data = json.loads((TOP / 'tools/ci-base.lock.json').read_text(encoding='utf-8'))
    if data.get('format') != 1 or not data.get('url', '').startswith('https://'):
        raise ValueError('Invalid CI base lock')
    if not re.fullmatch('[0-9a-f]{64}', data.get('sha256', '')):
        raise ValueError('Invalid CI base lock checksum')
    if not data['url'].endswith('/cx60-ci-base.tar.gz'):
        raise ValueError('Unexpected CI base asset name')
    for part in data.get('parts', []):
        if not re.fullmatch(r'cx60-ci-base\.tar\.gz\.part-\d{2}', part.get('name', '')):
            raise ValueError('Unexpected CI base part name')
        if not re.fullmatch('[0-9a-f]{64}', part.get('sha256', '')):
            raise ValueError('Invalid CI base part checksum')
    return data


def download(url, pending, want):
    with urllib.request.urlopen(url, timeout=120) as source, pending.open('wb') as output:
        shutil.copyfileobj(source, output)
    if sha(pending) != want:
        raise ValueError('Downloaded CI base checksum mismatch; partial retained: ' + url)


def fetch_base(destination):
    lock = base_lock()
    archive = TOP / 'work/ci-base-download/cx60-ci-base.tar.gz'
    if archive.exists():
        if archive.is_symlink() or sha(archive) != lock['sha256']:
            raise ValueError('Cached CI base download mismatch; inspect ' + str(archive))
    else:
        archive.parent.mkdir(parents=True, exist_ok=True)
        pending = archive.with_name(archive.name + '.partial')
        parts = lock.get('parts')
        if parts:
            # The full asset is uploaded in slices: some networks reset long uploads.
            directory = lock['url'].rsplit('/', 1)[0]
            with pending.open('wb') as output:
                for part in parts:
                    piece = archive.with_name(part['name'] + '.partial')
                    download(directory + '/' + part['name'], piece, part['sha256'])
                    with piece.open('rb') as stream:
                        shutil.copyfileobj(stream, output)
                    piece.unlink()
            if sha(pending) != lock['sha256']:
                raise ValueError('Assembled CI base checksum mismatch; partial retained')
        else:
            download(lock['url'], pending, lock['sha256'])
        pending.rename(archive)
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if {m.name for m in members} != BASE_MEMBERS or not all(m.isfile() for m in members):
            raise ValueError('CI base archive must hold exactly the base and defaults tars')
        if not hasattr(tarfile, 'data_filter'):
            raise ValueError('Update Python to a security-maintained version with tarfile.data_filter')
        source.extractall(destination, filter='data')
    print('Verified CI base asset: ' + lock['sha256'], flush=True)


def restore(with_base=True):
    if os.name != 'posix':
        raise SystemExit('Run on the Linux CI runner or in WSL')
    ci = runpy.run_path(str(TOP / 'tools/ci-inputs.py'))
    boot = gzip.decompress((SEEDS / 'boot_a.template.gz').read_bytes())
    if ci['boot_template'](boot) != boot:
        raise ValueError('committed boot template is not sanitized')
    misc = (SEEDS / 'misc-head.bin').read_bytes()
    if ci['misc_template'](misc) != misc:
        raise ValueError('committed misc template is not sanitized')
    busybox = (SEEDS / 'busybox').read_bytes()
    if busybox[:4] != b'\x7fELF' or struct.unpack_from('<H', busybox, 18)[0] != 183:
        raise ValueError('committed busybox is not an ARM64 ELF')
    config = (SEEDS / 'ums9620-base.config').read_bytes()
    if not all(marker in config.decode() for marker in ci['UMS9620_MARKERS']):
        raise ValueError('committed config is not the tested UMS9620 baseline')
    place('dumps/changxing60-stock/boot_a.img', boot)
    place('dumps/changxing60-stock/misc-head.bin', misc)
    place('work/busybox/ext/usr/bin/busybox', busybox, 0o755)
    place('inputs/ums9620-base.config', config)
    if with_base:
        fetch_base(TOP / 'inputs')
    print('Restored Changxing 60 CI seeds', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-base', action='store_true',
                        help='restore committed seeds only (kernel job needs just the config)')
    args = parser.parse_args()
    try:
        restore(with_base=not args.no_base)
    except (ValueError, KeyError) as error:
        parser.exit(1, 'CI seeds: ' + str(error) + '\n')