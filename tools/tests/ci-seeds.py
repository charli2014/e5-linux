#!/usr/bin/env python3
"""Committed CI seeds, the pinned clean-base lock and the workflow wiring."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import io

TOP = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), TOP / 'tools' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


seeds = module('ci-seeds')
inputs = module('ci-inputs')


def digest(data):
    return hashlib.sha256(data).hexdigest()


class CommittedSeeds(unittest.TestCase):
    def test_boot_and_misc_templates_are_sanitized_and_idempotent(self):
        boot = gzip.decompress((seeds.SEEDS / 'boot_a.template.gz').read_bytes())
        self.assertEqual(len(boot), 64 << 20)
        self.assertEqual(inputs.boot_template(boot), boot)
        misc = (seeds.SEEDS / 'misc-head.bin').read_bytes()
        self.assertEqual(len(misc), 4096)
        self.assertEqual(inputs.misc_template(misc), misc)

    def test_busybox_is_an_arm64_elf(self):
        data = (seeds.SEEDS / 'busybox').read_bytes()
        self.assertEqual(data[:4], b'\x7fELF')
        self.assertEqual(struct.unpack_from('<H', data, 18)[0], 183)

    def test_config_is_the_registered_ums9620_baseline(self):
        text = (seeds.SEEDS / 'ums9620-base.config').read_text(encoding='utf-8')
        for marker in inputs.UMS9620_MARKERS:
            self.assertIn(marker, text)

    def test_seeds_carry_no_device_payload_paths(self):
        for path in seeds.SEEDS.iterdir():
            self.assertNotIn(path.name, ('wcnmodem.bin', 'android'))

    def test_every_seed_is_tracked_by_git(self):
        # A bare .gitignore pattern (e.g. "busybox") can silently skip a seed
        # at commit time; the CI checkout would then lack it.
        import subprocess
        tracked = subprocess.run(['git', 'ls-files', 'devices/changxing60/ci-seeds'],
                                 cwd=TOP, capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(sorted(tracked), sorted(
            'devices/changxing60/ci-seeds/' + p.name for p in seeds.SEEDS.iterdir()))


class BaseLock(unittest.TestCase):
    def test_committed_lock_is_valid(self):
        lock = seeds.base_lock()
        self.assertEqual(lock['openwrt_version'], '25.12.5')
        self.assertTrue(lock['parts'])
        self.assertEqual(len(lock['parts']), 4)

    def test_lock_rejects_tampering(self):
        good = json.loads((TOP / 'tools/ci-base.lock.json').read_text(encoding='utf-8'))
        bad = []
        x = dict(good); x['format'] = 2; bad.append(x)
        x = dict(good); x['url'] = 'http://example.com/cx60-ci-base.tar.gz'; bad.append(x)
        x = dict(good); x['url'] = 'https://example.com/other.tar.gz'; bad.append(x)
        x = dict(good); x['sha256'] = 'z' * 64; bad.append(x)
        x = dict(good); x['parts'] = [{'name': 'evil.sh', 'sha256': 'a' * 64}]; bad.append(x)
        x = dict(good); x['parts'] = [{'name': 'cx60-ci-base.tar.gz.part-00', 'sha256': 'short'}]; bad.append(x)
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / 'tools').mkdir()
            for lock in bad:
                (fake / 'tools/ci-base.lock.json').write_text(json.dumps(lock), encoding='utf-8')
                with patch.object(seeds, 'TOP', fake):
                    with self.assertRaises(ValueError):
                        seeds.base_lock()


class FetchBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
            for name, data in (('base-e5.tar.gz', b'base'), ('clean-openwrt-base.tar', b'defaults')):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        self.whole = buffer.getvalue()
        cut = len(self.whole) // 2
        self.pieces = [self.whole[:cut], self.whole[cut:]]
        self.lock = {
            'format': 1,
            'url': 'https://example.invalid/releases/download/tag/cx60-ci-base.tar.gz',
            'sha256': digest(self.whole),
            'parts': [{'name': f'cx60-ci-base.tar.gz.part-{i:02d}', 'sha256': digest(p)}
                      for i, p in enumerate(self.pieces)],
        }

    def fake_download(self, url, pending, want):
        name = url.rsplit('/', 1)[1]
        piece = next(p for n, p in zip((x['name'] for x in self.lock['parts']), self.pieces) if n == name)
        if digest(piece) != want:
            raise ValueError('part checksum mismatch')
        Path(pending).write_bytes(piece)

    def test_parts_are_assembled_verified_and_extracted(self):
        dest = self.root / 'inputs'
        dest.mkdir()
        with patch.object(seeds, 'TOP', self.root), \
             patch.object(seeds, 'base_lock', return_value=self.lock), \
             patch.object(seeds, 'download', side_effect=self.fake_download):
            seeds.fetch_base(dest)
        self.assertEqual({p.name for p in dest.iterdir()}, seeds.BASE_MEMBERS)
        archive = self.root / 'work/ci-base-download/cx60-ci-base.tar.gz'
        self.assertEqual(archive.read_bytes(), self.whole)
        self.assertFalse(list(archive.parent.glob('*.partial')))

    def test_wrong_whole_checksum_is_refused(self):
        lock = dict(self.lock, sha256='b' * 64)
        with patch.object(seeds, 'TOP', self.root), \
             patch.object(seeds, 'base_lock', return_value=lock), \
             patch.object(seeds, 'download', side_effect=self.fake_download):
            with self.assertRaises(ValueError):
                seeds.fetch_base(self.root)

    def test_cached_archive_skips_download(self):
        archive = self.root / 'work/ci-base-download/cx60-ci-base.tar.gz'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(self.whole)
        dest = self.root / 'inputs'
        dest.mkdir()
        def refuse(*args):
            raise AssertionError('download called despite a valid cache')
        with patch.object(seeds, 'TOP', self.root), \
             patch.object(seeds, 'base_lock', return_value=self.lock), \
             patch.object(seeds, 'download', side_effect=refuse):
            seeds.fetch_base(dest)
        self.assertEqual({p.name for p in dest.iterdir()}, seeds.BASE_MEMBERS)

    def test_corrupt_cache_is_refused(self):
        archive = self.root / 'work/ci-base-download/cx60-ci-base.tar.gz'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'corrupt')
        with patch.object(seeds, 'TOP', self.root), \
             patch.object(seeds, 'base_lock', return_value=self.lock):
            with self.assertRaises(ValueError):
                seeds.fetch_base(self.root)


class WorkflowWiring(unittest.TestCase):
    def setUp(self):
        self.text = (TOP / '.github/workflows/changxing60-release.yml').read_text(encoding='utf-8')

    def test_no_repository_variable_inputs_remain(self):
        self.assertNotIn('E5_CX60_CI_INPUTS', self.text)

    def test_seeds_restore_precedes_input_placement(self):
        self.assertLess(self.text.index('python3 tools/ci-seeds.py'),
                        self.text.index('Place registered inputs'))
        self.assertIn('python3 tools/ci-seeds.py --no-base', self.text)

    def test_apk_builds_precede_volume_cleanup_and_are_cached(self):
        for script in ('openwrt/build-hostapd.sh', 'openwrt/build-iwinfo-ap-scan.sh', 'openwrt/build-lpac.sh'):
            self.assertLess(self.text.index(script), self.text.index('docker volume rm e5-openwrt-src'))
        for path in ('work/wifi-sae/', 'work/iwinfo-ap-scan/', 'work/lpac-apks/'):
            self.assertEqual(self.text.count(path), 2)

    def test_bootstrap_gate_precedes_layout_and_android_dir_follows_gate(self):
        gate = self.text.index('tools/ci-inputs.py create --profile changxing60')
        self.assertLess(gate, self.text.index('Write the CI build layout'))
        self.assertLess(gate, self.text.index('mkdir -p "$CX60_WS/base/e5/opt/e5/android"'))
        self.assertIn("data['lpac_apks'] = f'{repo}/work/lpac-apks'", self.text)

    def test_release_notes_use_measured_checksums(self):
        self.assertIn('BOOTSTRAP_SHA256: ${{ steps.bootstrap.outputs.sha256 }}', self.text)
        self.assertIn("tools/ci-base.lock.json", self.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)