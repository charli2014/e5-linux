"""Screen pipeline defaults: fresh images write them, upgrades migrate once."""
from pathlib import Path
import os
import runpy
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
STAGE = runpy.run_path(str(HERE / 'stage.py'))


class ScreenDefaults(unittest.TestCase):
    def make_root(self, directory):
        root = Path(directory)
        (root / 'etc/e5').mkdir(parents=True)
        (root / 'etc/e5/device-profile').write_text('changxing60\n')
        (root / 'usr/libexec/e5-infoscreen').mkdir(parents=True)
        (root / 'usr/libexec/e5-infoscreen/session').write_text(
            '#!/bin/sh\nexec /usr/bin/cog -P wl --bg-color=black http://127.0.0.1/\n')
        (root / 'etc/config').mkdir()
        return root

    def test_fresh_config_gets_pipeline_and_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            config = root / 'etc/config/e5-infoscreen'
            config.write_text("config infoscreen 'main'\n\toption enabled '1'\n")
            STAGE['stage_screen'](root)
            text = config.read_text()
            self.assertEqual(text.count('pipeline_off'), 1)
            self.assertIn("option pipeline_off '1'", text)
            self.assertIn("option pipeline_grace '10'", text)
            self.assertIn('--scale=1.25', (root / 'usr/libexec/e5-infoscreen/session').read_text())
            script = root / 'etc/uci-defaults/97-changxing60-screen'
            self.assertTrue(script.is_file())
            if os.name != 'nt':
                self.assertTrue(script.stat().st_mode & 0o111)
            before = (config.read_text(), script.read_text())
            STAGE['stage_screen'](root)
            self.assertEqual(before, (config.read_text(), script.read_text()))

    def test_explicit_user_choice_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            config = root / 'etc/config/e5-infoscreen'
            original = ("config infoscreen 'main'\n\toption pipeline_off '0'\n"
                        "\toption pipeline_grace '30'\n")
            config.write_text(original)
            STAGE['stage_screen'](root)
            self.assertEqual(config.read_text(), original)

    def run_migration(self, present):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bindir = base / 'bin'
            bindir.mkdir()
            calls = base / 'calls'
            stub = bindir / 'uci'
            stub.write_text(
                '#!/bin/sh\n'
                'echo "$*" >> "$E5_UCI_LOG"\n'
                'if [ "$1" = "-q" ] && [ "$2" = "get" ]; then [ "$E5_UCI_PRESENT" = 1 ] && exit 0; exit 1; fi\n'
                'exit 0\n')
            stub.chmod(0o755)
            env = dict(os.environ, E5_UCI_LOG=str(calls),
                       E5_UCI_PRESENT='1' if present else '0',
                       PATH=str(bindir) + os.pathsep + os.environ['PATH'])
            subprocess.run(['sh', '-ec', STAGE['SCREEN_DEFAULTS_SCRIPT']], env=env, check=True)
            return calls.read_text() if calls.exists() else ''

    def test_migration_fills_only_missing_options(self):
        missing = self.run_migration(False)
        self.assertIn('set e5-infoscreen.main.pipeline_off=1', missing)
        self.assertIn('set e5-infoscreen.main.pipeline_grace=10', missing)
        kept = self.run_migration(True)
        self.assertEqual(kept.count('set '), 0)


if __name__ == '__main__':
    unittest.main()
