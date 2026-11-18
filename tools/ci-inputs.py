#!/usr/bin/env python3
"""Prepare/verify the small bootstrap archive required by a clean CI build.

The boot template retains only the Android header, vbmeta and footer; the misc
template retains only bootloader_control. No stock kernel, firmware or vendor
userspace is included. Cached WPE files must belong to the three named packages.

The changxing60 profile carries the same templates for its stock slot-a image
plus the registered UMS9620 baseline config and the prepared clean base,
defaults and APK inputs as opaque, hash-pinned archives. Their contents are
re-checked by build-release.py input_check and prepare-root at assembly time.
"""
import argparse
import hashlib
import io
import json
import os
import posixpath
import runpy
import stat
import struct
import tarfile
import zlib
from pathlib import Path, PurePosixPath

TOP = Path(__file__).resolve().parents[1]
PACKAGES = {'cog', 'libcogcore', 'libwpewebkit'}
MAX_BYTES = 256 << 20
CX60_MAX_BYTES = 1 << 30
CX60_BOOT = 'dumps/changxing60-stock/boot_a.img'
CX60_MISC = 'dumps/changxing60-stock/misc-head.bin'
BUSYBOX_PATH = 'work/busybox/ext/usr/bin/busybox'
CX60_CONFIG = 'inputs/ums9620-base.config'
CX60_TARS = ('inputs/base-e5.tar.gz', 'inputs/clean-openwrt-base.tar',
             'inputs/wifi-sae.tar.gz', 'inputs/iwinfo-ap-scan.tar.gz', 'inputs/lpac.tar.gz')
UMS9620_MARKERS = ('CONFIG_SPRD_UMS9620_CLK=y', 'CONFIG_PINCTRL_SPRD_QOGIRN6PRO=y')
DEVICE_PATHS = ('lib/firmware/wcnmodem.bin', 'opt/e5/android')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def boot_template(data):
    if len(data) != 64 << 20 or data[:8] != b'ANDROID!' or struct.unpack_from('<I', data, 40)[0] != 4:
        raise ValueError('expected a 64 MiB E5 Android boot v4 image')
    if data[-64:-60] != b'AVBf':
        raise ValueError('boot image has no AVB footer')
    offset, size = struct.unpack_from('>QQ', data, len(data) - 44)
    if size < 256 or offset + size > len(data) - 64 or data[offset:offset + 4] != b'AVB0':
        raise ValueError('boot image has invalid vbmeta bounds')
    result = bytearray(len(data))
    result[:44] = data[:44]
    struct.pack_into('<II', result, 8, 0, 0)
    result[4096:4096 + size] = data[offset:offset + size]
    result[-64:] = data[-64:]
    struct.pack_into('>QQQ', result, len(result) - 52, 4096, 4096, size)
    return bytes(result)


def misc_template(data):
    bc = data[0x800:0x820]
    if len(bc) != 32 or bc[4:8] != b'BCAB' or zlib.crc32(bc[:28]) != struct.unpack_from('<I', bc, 28)[0]:
        raise ValueError('misc template has invalid bootloader_control')
    result = bytearray(4096)
    result[0x800:0x820] = bc
    return bytes(result)


def package_paths(text):
    blocks = [b for b in text.split('\n\n') if b.strip()]
    names, paths = set(), set()
    for block in blocks:
        directory = None
        for line in block.splitlines():
            if line.startswith('P:'):
                names.add(line[2:])
            elif line.startswith('F:'):
                directory = line[2:]
            elif line.startswith('R:'):
                if not directory:
                    raise ValueError('package file without a directory')
                path = directory + '/' + line[2:]
                if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
                    raise ValueError('invalid package path')
                paths.add(path)
    if names != PACKAGES:
        raise ValueError('bootstrap cache must contain exactly cog, libcogcore and libwpewebkit')
    return paths


def tar_directory(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('not a directory: ' + str(directory))
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz', format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(directory.rglob('*')):
            info = archive.gettarinfo(str(path), arcname=path.relative_to(directory).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            if info.isfile():
                with path.open('rb') as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)
    return buffer.getvalue()


def check_inner_tar(data, name, required=()):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        members = archive.getnames()
    for member in members:
        path = PurePosixPath(member)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe path in ' + name + ': ' + member)
        if any(member == p or member.startswith(p + '/') for p in DEVICE_PATHS):
            raise ValueError('device-specific content in ' + name + ': ' + member)
    for member in required:
        if member not in members:
            raise ValueError(name + ' lacks ' + member)


def write_archive(payload, links, output, profile=None):
    manifest = {'format': 1, 'files': {n: sha(data) for n, (data, _) in payload.items()}, 'links': links}
    if profile:
        manifest['profile'] = profile
    payload['ci-inputs.json'] = ((json.dumps(manifest, indent=2) + '\n').encode(), 0o644)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz', format=tarfile.GNU_FORMAT) as archive:
        for name in sorted(payload.keys() | links.keys()):
            entry = tarfile.TarInfo(name)
            if name in links:
                entry.type = tarfile.SYMTYPE
                entry.linkname = links[name]
                archive.addfile(entry)
            else:
                data, entry.mode = payload[name]
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
    inspect(output)
    digest = sha(output.read_bytes())
    Path(str(output) + '.sha256').write_text(digest + '  ' + output.name + '\n')
    print(output)
    print('SHA256=' + digest)


def create(args):
    if args.profile == 'changxing60':
        return create_changxing60(args)
    cache = args.transplant
    installed = (cache / 'installed').read_text()
    payload = {
        'dumps/boot_b.img': (boot_template(args.boot.read_bytes()), 0o644),
        'dumps/misc-head.bin': (misc_template(args.misc.read_bytes()), 0o644),
        BUSYBOX_PATH: (args.busybox.read_bytes(), 0o755),
        'work/openwrt/transplant/installed': (installed.encode(), 0o644),
        'work/openwrt/transplant/names': ('\n'.join(sorted(PACKAGES)).encode() + b'\n', 0o644),
        'work/openwrt/transplant/deps': ((cache / 'deps').read_bytes(), 0o644),
    }
    links = {}
    for relative in sorted(package_paths(installed)):
        path = cache / 'root' / relative
        name = 'work/openwrt/transplant/root/' + relative
        if path.is_symlink():
            links[name] = os.readlink(path)
        elif path.is_file():
            payload[name] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        else:
            raise ValueError('missing cached package file: ' + relative)
    write_archive(payload, links, args.output)


def create_changxing60(args):
    workspace = args.workspace.expanduser().resolve()
    boot = args.boot or TOP / 'dumps/changxing60-stock/boot_a.img'
    misc = args.misc or TOP / 'dumps/changxing60-stock/misc-head.bin'
    base_config = args.base_config or workspace / 'kernels/m8/config'
    base_dir = args.base_dir or workspace / 'base/e5'
    defaults = args.defaults or TOP / 'work/e5-port/clean-openwrt-base.tar'
    wifi = args.wifi_apks or TOP / 'work/wifi-sae'
    iwinfo = args.iwinfo_apks or TOP / 'work/iwinfo-ap-scan'
    lpac = args.lpac_apks or workspace / 'artifacts/lpac'
    config = base_config.read_text(encoding='utf-8')
    if not all(marker in config for marker in UMS9620_MARKERS):
        raise ValueError('base config is not the tested UMS9620 baseline: ' + str(base_config))
    if not (base_dir / 'sbin/sysupgrade.openwrt').is_file():
        raise ValueError('clean base lacks sbin/sysupgrade.openwrt: ' + str(base_dir))
    for relative in DEVICE_PATHS:
        if (base_dir / relative).exists():
            raise ValueError('clean base carries device-specific content: ' + relative)
    for script, directory in (('wifi-sae-state', wifi), ('iwinfo-ap-scan-state', iwinfo), ('lpac-state', lpac)):
        runpy.run_path(str(TOP / 'openwrt' / (script + '.py')))['inspect'](directory)
    if not tarfile.is_tarfile(defaults):
        raise ValueError('defaults is not a tar archive: ' + str(defaults))
    base_tar = tar_directory(base_dir)
    check_inner_tar(base_tar, 'base-e5.tar.gz', required=('sbin/sysupgrade.openwrt',))
    payload = {
        CX60_BOOT: (boot_template(boot.read_bytes()), 0o644),
        CX60_MISC: (misc_template(misc.read_bytes()), 0o644),
        BUSYBOX_PATH: (args.busybox.read_bytes(), 0o755),
        CX60_CONFIG: (config.encode(), 0o644),
        'inputs/base-e5.tar.gz': (base_tar, 0o644),
        'inputs/clean-openwrt-base.tar': (defaults.read_bytes(), 0o644),
        'inputs/wifi-sae.tar.gz': (tar_directory(wifi), 0o644),
        'inputs/iwinfo-ap-scan.tar.gz': (tar_directory(iwinfo), 0o644),
        'inputs/lpac.tar.gz': (tar_directory(lpac), 0o644),
    }
    for name in CX60_TARS[1:]:
        check_inner_tar(payload[name][0], name)
    write_archive(payload, {}, args.output, profile='changxing60')


def inspect(path):
    with tarfile.open(path) as archive:
        entries = archive.getmembers()
        names = [e.name for e in entries]
        if len(names) != len(set(names)):
            raise ValueError('duplicate entries in bootstrap archive')
        data, links, modes = {}, {}, {}
        for entry in entries:
            name = entry.name
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or name.endswith('/'):
                raise ValueError('invalid bootstrap path: ' + name)
            if entry.isfile():
                data[name] = archive.extractfile(entry).read()
                modes[name] = entry.mode & 0o777
            elif entry.issym():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), entry.linkname))
                if entry.linkname.startswith('/') or not target.startswith('work/openwrt/transplant/root/'):
                    raise ValueError('unsafe cache symlink: ' + name)
                links[name] = entry.linkname
            else:
                raise ValueError('unexpected bootstrap file type: ' + name)
        manifest = json.loads(data.pop('ci-inputs.json'))
        if manifest.get('format') != 1 or manifest['files'] != {n: sha(v) for n, v in data.items()} or manifest['links'] != links:
            raise ValueError('bootstrap manifest mismatch')
        profile = manifest.get('profile', 'e5')
        if profile not in ('e5', 'changxing60'):
            raise ValueError('unknown bootstrap profile: ' + str(profile))
        cap = CX60_MAX_BYTES if profile == 'changxing60' else MAX_BYTES
        if sum(e.size for e in entries) > cap:
            raise ValueError('oversized bootstrap archive')
        if profile == 'changxing60':
            if links:
                raise ValueError('changxing60 bootstrap must not contain symlinks')
            if boot_template(data[CX60_BOOT]) != data[CX60_BOOT]:
                raise ValueError('boot template includes a stock payload')
            if misc_template(data[CX60_MISC]) != data[CX60_MISC]:
                raise ValueError('misc template includes data outside bootloader_control')
            config = data[CX60_CONFIG].decode()
            if not all(marker in config for marker in UMS9620_MARKERS):
                raise ValueError('base config is not the tested UMS9620 baseline')
            permitted = {CX60_BOOT, CX60_MISC, BUSYBOX_PATH, CX60_CONFIG, *CX60_TARS}
            if set(data) != permitted:
                raise ValueError('bootstrap includes files outside the changxing60 input set')
            check_inner_tar(data['inputs/base-e5.tar.gz'], 'base-e5.tar.gz',
                            required=('sbin/sysupgrade.openwrt',))
            for name in CX60_TARS[1:]:
                check_inner_tar(data[name], name)
        else:
            if boot_template(data['dumps/boot_b.img']) != data['dumps/boot_b.img']:
                raise ValueError('boot template includes a stock payload')
            if misc_template(data['dumps/misc-head.bin']) != data['dumps/misc-head.bin']:
                raise ValueError('misc template includes data outside bootloader_control')
            permitted = {'dumps/boot_b.img', 'dumps/misc-head.bin', BUSYBOX_PATH,
                         'work/openwrt/transplant/installed', 'work/openwrt/transplant/names',
                         'work/openwrt/transplant/deps'}
            installed = data['work/openwrt/transplant/installed'].decode()
            permitted.update('work/openwrt/transplant/root/' + p for p in package_paths(installed))
            if set(data) | set(links) != permitted:
                raise ValueError('bootstrap includes files outside the boot templates, BusyBox and WPE packages')
        bb = data[BUSYBOX_PATH]
        if bb[:4] != b'\x7fELF' or struct.unpack_from('<H', bb, 18)[0] != 183:
            raise ValueError('BusyBox must be an ARM64 ELF')
        for link in links:
            if any(parent.as_posix() in links for parent in PurePosixPath(link).parents):
                raise ValueError('nested cache symlink')
        for name in data:
            if any(parent.as_posix() in links for parent in PurePosixPath(name).parents):
                raise ValueError('file beneath cache symlink')
        data['ci-inputs.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
        modes['ci-inputs.json'] = 0o644
        return data, links, modes


def restore(args):
    if sha(args.archive.read_bytes()) != args.sha256.lower():
        raise ValueError('bootstrap SHA-256 mismatch')
    data, links, modes = inspect(args.archive)
    for name in data.keys() | links.keys():
        target = args.destination / name
        if target.exists() or target.is_symlink():
            raise ValueError('bootstrap destination already exists: ' + name)
        if any(p.is_symlink() for p in target.parents):
            raise ValueError('bootstrap destination contains a symlink: ' + name)
    for name, content in data.items():
        target = args.destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(modes[name])
    for name, link in links.items():
        target = args.destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(link)
    print('Verified and restored CI inputs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('create')
    build.add_argument('--profile', choices=('e5', 'changxing60'), default='e5')
    build.add_argument('--workspace', type=Path, default=Path.home() / 'openwrt-build')
    build.add_argument('--boot', type=Path, default=None)
    build.add_argument('--misc', type=Path, default=None)
    build.add_argument('--busybox', type=Path, default=TOP / 'work/busybox/ext/usr/bin/busybox')
    build.add_argument('--transplant', type=Path, default=TOP / 'work/openwrt/transplant')
    build.add_argument('--base-config', type=Path, default=None)
    build.add_argument('--base-dir', type=Path, default=None)
    build.add_argument('--defaults', type=Path, default=None)
    build.add_argument('--wifi-apks', type=Path, default=None)
    build.add_argument('--iwinfo-apks', type=Path, default=None)
    build.add_argument('--lpac-apks', type=Path, default=None)
    build.add_argument('--output', type=Path, default=None)
    unpack = sub.add_parser('restore')
    unpack.add_argument('archive', type=Path)
    unpack.add_argument('--sha256', required=True)
    unpack.add_argument('--destination', type=Path, default=TOP)
    args = parser.parse_args()
    if args.command == 'create':
        if args.boot is None:
            args.boot = TOP / ('dumps/changxing60-stock/boot_a.img' if args.profile == 'changxing60' else 'dumps/boot_b.img')
        if args.misc is None:
            args.misc = TOP / ('dumps/changxing60-stock/misc-head.bin' if args.profile == 'changxing60' else 'dumps/misc-head.bin')
        if args.output is None:
            args.output = TOP / ('out/cx60-ci-inputs.tar.gz' if args.profile == 'changxing60' else 'out/e5-ci-inputs.tar.gz')
    try:
        (create if args.command == 'create' else restore)(args)
    except (ValueError, KeyError) as error:
        parser.exit(1, 'CI inputs: ' + str(error) + '\n')
