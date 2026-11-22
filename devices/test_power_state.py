#!/usr/bin/env python3
"""State-machine tests for e5-power-state (ONLINE -> IDLE -> DEEP).

The daemon is loaded with runpy and driven with fake system operations and a
manual clock, so no radio, service or suspend is ever touched. Ops.suspend's
pm_test staging is exercised against a temporary sysfs tree.
"""
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
NS = runpy.run_path(str(HERE.parent / 'openwrt/overlay/usr/libexec/e5-power-state'))
Machine = NS['Machine']
Ops = NS['Ops']
load_config = NS['load_config']


class FakeOps:
    def __init__(self):
        self.policy = [True, True]
        self.client_count = 0
        self.usb = False
        self.bright = 0
        self.audio = False
        self.locks = []
        self.upgrade = False
        self.radio_error = None
        self.suspend_error = None
        self.calls = []

    def radio_policy(self):
        return list(self.policy)

    def radio_set(self, slot, enabled):
        self.calls.append(('radio', slot, enabled))
        if self.radio_error is None:
            self.policy[slot] = enabled  # data-sim persists the policy
        return self.radio_error

    def service(self, name, on):
        self.calls.append(('service', name, on))
        return None

    def wifi_set(self, on):
        self.calls.append(('wifi', on))
        return None

    def clients(self):
        return self.client_count

    def usb_peer(self):
        return self.usb

    def brightness(self):
        return self.bright

    def audio_running(self):
        return self.audio

    def upgrade_locked(self):
        return self.upgrade

    def wakelocks(self):
        return list(self.locks)

    def usb_runtime_pm(self):
        self.calls.append(('usb_pm',))
        return None

    def suspend(self, test):
        self.calls.append(('suspend', test))
        return self.suspend_error

    def wan_resume(self):
        self.calls.append(('wan',))

    def log(self, message):
        pass


class PowerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'e5-power.json'
        self.state_file = self.root / 'run/e5-power.json'
        self.marker = self.root / 'etc/e5/power-radio-restore.json'
        self.now = [1000.0]
        self.ops = FakeOps()
        self.write_config(idle_min=1, deep_min=0)
        self.machine = self.make_machine()

    def write_config(self, **kwargs):
        cfg = {'idle_min': 0, 'deep_min': 0, 'hold_awake_min': 5, 'inhibit': False}
        cfg.update(kwargs)
        self.config.write_text(json.dumps(cfg))

    def make_machine(self):
        machine = Machine(self.ops, self.config, self.state_file, self.marker,
                          clock=lambda: self.now[0])
        machine.boot()
        return machine

    def advance(self, seconds):
        self.now[0] += seconds
        self.machine.tick(self.now[0])

    def reach_idle(self):
        self.advance(301)  # boot hold expires, idle timer arms
        self.advance(60)   # idle_min = 1
        self.assertEqual(self.machine.state, 'IDLE')

    def published(self):
        return json.loads(self.state_file.read_text())

    def test_disabled_by_default(self):
        self.config.unlink()
        self.machine = self.make_machine()
        self.advance(86400)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertEqual([c for c in self.ops.calls
                          if c[0] in ('radio', 'service', 'wifi', 'suspend')], [])

    def test_usb_runtime_pm_applied_at_boot(self):
        self.assertIn(('usb_pm',), self.ops.calls)

    def test_idle_after_timeout(self):
        self.reach_idle()
        self.assertIn(('radio', 0, False), self.ops.calls)
        self.assertIn(('radio', 1, False), self.ops.calls)
        self.assertIn(('service', 't551m-sim-status', False), self.ops.calls)
        self.assertIn(('service', 'e5-bt', False), self.ops.calls)
        self.assertNotIn(('wifi', False), self.ops.calls)  # hotspot kept
        self.assertEqual(json.loads(self.marker.read_text()), {'enabled': [True, True]})

    def test_idle_wake_on_client(self):
        self.reach_idle()
        self.ops.client_count = 1
        self.advance(5)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertIn(('radio', 0, True), self.ops.calls)
        self.assertIn(('radio', 1, True), self.ops.calls)
        self.assertIn(('service', 'e5-bt', True), self.ops.calls)
        self.assertIn(('wan',), self.ops.calls)
        self.assertFalse(self.marker.exists())
        self.ops.client_count = 0
        self.advance(60)  # hold-awake keeps it ONLINE past idle_min
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_wake_does_not_touch_wifi(self):
        self.reach_idle()
        self.ops.client_count = 2
        self.advance(5)
        self.assertEqual([c for c in self.ops.calls if c[0] == 'wifi'], [])

    def test_deep_after_idle(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.advance(60)  # deep timer arms
        self.advance(60)  # enter DEEP, fake suspend returns immediately
        self.assertIn(('wifi', False), self.ops.calls)
        self.assertIn(('suspend', False), self.ops.calls)
        self.assertIn(('wifi', True), self.ops.calls)
        self.assertIn(('radio', 0, True), self.ops.calls)
        self.assertIn(('service', 't551m-sim-status', True), self.ops.calls)
        self.assertIn(('wan',), self.ops.calls)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertFalse(self.marker.exists())

    def test_deep_test_flag_passed_to_suspend(self):
        self.write_config(idle_min=1, deep_min=1, deep_test=True)
        self.reach_idle()
        self.advance(60)
        self.advance(60)
        self.assertIn(('suspend', True), self.ops.calls)

    def test_deep_blocked_by_sipa_wakelock(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.ops.locks = ['sipa_wakelock']
        self.advance(60)
        self.advance(60)
        self.assertEqual(self.machine.state, 'IDLE')
        self.assertEqual(self.machine.deep_blocked, 'SIPA wakelock still held')
        self.assertNotIn(('suspend', False), self.ops.calls)
        self.assertEqual(self.published()['deep_in'], 300)

    def test_deep_blocked_by_audio(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.ops.audio = True
        self.advance(60)
        self.advance(60)
        self.assertEqual(self.machine.state, 'IDLE')
        self.assertEqual(self.machine.deep_blocked, 'audio playing')

    def test_deep_blocked_by_unreadable_wakelocks(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.ops.locks = ['unknown']
        self.advance(60)
        self.advance(60)
        self.assertEqual(self.machine.state, 'IDLE')
        self.assertEqual(self.machine.deep_blocked, 'wakelock state unreadable')
        self.assertNotIn(('suspend', False), self.ops.calls)

    def test_deep_resume_after_blocked_retry(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.ops.locks = ['sipa']
        self.advance(60)
        self.advance(60)
        self.assertEqual(self.machine.deep_blocked, 'SIPA wakelock still held')
        self.ops.locks = []
        self.advance(300)
        self.assertIn(('suspend', False), self.ops.calls)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_suspend_failure_returns_online(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.ops.suspend_error = 'write error'
        self.advance(60)
        self.advance(60)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertIn('suspend failed', self.machine.last_error)
        self.assertIn(('wifi', True), self.ops.calls)
        self.assertIn(('radio', 1, True), self.ops.calls)

    def test_upgrade_lock_wakes(self):
        self.reach_idle()
        self.ops.upgrade = True
        self.advance(5)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertIn(('radio', 0, True), self.ops.calls)

    def test_inhibit_prevents_and_wakes(self):
        self.write_config(idle_min=1, inhibit=True)
        self.advance(3600)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.write_config(idle_min=1)
        self.reach_idle()
        self.write_config(idle_min=1, inhibit=True)
        self.advance(5)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_boot_restores_marker(self):
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(json.dumps({'enabled': [True, False]}))
        self.machine = self.make_machine()
        self.assertIn(('radio', 0, True), self.ops.calls)
        self.assertNotIn(('radio', 1, True), self.ops.calls)
        self.assertFalse(self.marker.exists())

    def test_radio_failure_aborts_idle(self):
        self.ops.radio_error = 'modem busy'
        self.advance(301)
        self.advance(60)
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertIn(('radio', 0, True), self.ops.calls)  # rolled back
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.published()['idle_in'], 300)

    def test_short_episode_backoff(self):
        self.reach_idle()
        self.ops.client_count = 1
        self.advance(30)  # episode < 120 s
        self.assertEqual(self.machine.state, 'ONLINE')
        self.assertEqual(self.machine.multiplier, 2)
        self.ops.client_count = 0
        self.advance(301)  # hold expires, timer arms at 2x
        self.assertEqual(self.published()['idle_in'], 120)

    def test_long_episode_resets_backoff(self):
        self.reach_idle()
        self.advance(130)
        self.ops.client_count = 1
        self.advance(5)
        self.assertEqual(self.machine.multiplier, 1)

    def test_usb_peer_blocks_idle(self):
        self.ops.usb = True
        self.advance(3600)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_brightness_blocks_idle(self):
        self.ops.bright = 130
        self.advance(3600)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_unknown_clients_block_idle(self):
        self.ops.client_count = None
        self.advance(3600)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_radio_policy_change_wakes(self):
        self.reach_idle()
        self.ops.policy = [True, False]  # user re-enabled a SIM elsewhere
        self.advance(5)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_persisted_off_readback_stays_idle(self):
        self.reach_idle()
        self.assertEqual(self.ops.radio_policy(), [False, False])
        for _ in range(5):
            self.advance(5)
        self.assertEqual(self.machine.state, 'IDLE')

    def test_config_disable_wakes(self):
        self.reach_idle()
        self.write_config(idle_min=0)
        self.advance(5)
        self.assertEqual(self.machine.state, 'ONLINE')

    def test_config_deep_change_rearms(self):
        self.write_config(idle_min=1, deep_min=1)
        self.reach_idle()
        self.advance(30)
        self.write_config(idle_min=1, deep_min=5)
        self.advance(5)
        self.assertEqual(self.published()['deep_in'], 300)

    def test_state_file_published(self):
        self.advance(301)
        data = self.published()
        self.assertEqual(data['state'], 'ONLINE')
        self.assertEqual(data['idle_in'], 60)
        self.assertEqual(data['config']['idle_min'], 1)

    def test_load_config_validation(self):
        self.config.write_text('{"idle_min": -1}')
        cfg, error = load_config(self.config)
        self.assertIsNotNone(error)
        self.assertEqual(cfg['idle_min'], 0)
        self.config.write_text('{"bogus": 1}')
        cfg, error = load_config(self.config)
        self.assertIsNotNone(error)
        self.config.write_text('{"inhibit": "yes"}')
        cfg, error = load_config(self.config)
        self.assertIsNotNone(error)
        self.config.write_text('{"idle_min": 30, "deep_min": 30}')
        cfg, error = load_config(self.config)
        self.assertIsNone(error)
        self.assertEqual(cfg['deep_min'], 30)


class SuspendStagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        power = self.root / 'sys/power'
        power.mkdir(parents=True)
        (power / 'state').write_text('')
        (power / 'pm_test').write_text('none\n')
        self.ops = Ops(self.root)

    def test_real_suspend_leaves_pm_test_alone(self):
        error = self.ops.suspend(False)
        self.assertIsNone(error)
        self.assertEqual((self.root / 'sys/power/state').read_text(), 'mem\n')
        self.assertEqual((self.root / 'sys/power/pm_test').read_text(), 'none\n')

    def test_staged_suspend_resets_pm_test(self):
        error = self.ops.suspend(True)
        self.assertIsNone(error)
        self.assertEqual((self.root / 'sys/power/pm_test').read_text(), 'none\n')

    def test_staged_suspend_resets_pm_test_on_failure(self):
        state = self.root / 'sys/power/state'
        state.unlink()
        state.mkdir()  # writing raises IsADirectoryError (OSError)
        error = self.ops.suspend(True)
        self.assertIsNotNone(error)
        self.assertEqual((self.root / 'sys/power/pm_test').read_text(), 'none\n')


class ServicePathTest(unittest.TestCase):
    """Real Ops.service must invoke <root>/etc/init.d/<name>, not a str/str join."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'etc/init.d').mkdir(parents=True)
        self.ops = Ops(self.root)
        self.calls = []

    def _run(self, returncode=0, stderr=''):
        def run(args, timeout=60, stdin=None):
            self.calls.append((args, timeout))
            return subprocess.CompletedProcess(args, returncode, '', stderr)
        self.ops.run = run

    def test_start_stop_use_init_script_path(self):
        self._run()
        self.assertIsNone(self.ops.service('e5-bt', True))
        self.assertIsNone(self.ops.service('t551m-sim-status', False))
        self.assertEqual([c[0] for c in self.calls], [
            [str(self.root / 'etc/init.d/e5-bt'), 'start'],
            [str(self.root / 'etc/init.d/t551m-sim-status'), 'stop'],
        ])

    def test_failure_returns_stderr(self):
        self._run(returncode=1, stderr='init failed\n')
        self.assertEqual(self.ops.service('e5-bt', True), 'init failed\n')


class WakelockReadTest(unittest.TestCase):
    """Ops.wakelocks against a fake sysfs tree, rows in device tab format."""

    HEADER = ('name\tactive_count\tevent_count\twakeup_count\texpire_count\t'
              'active_since\ttotal_time\tmax_time\tlast_change\tprevent_suspend_time\n')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sys/power').mkdir(parents=True)
        (self.root / 'sys/kernel/debug').mkdir(parents=True)
        (self.root / 'sys/power/wake_lock').write_text('')
        self.ops = Ops(self.root)

    def write_sources(self, rows):
        (self.root / 'sys/kernel/debug/wakeup_sources').write_text(self.HEADER + rows)

    def test_active_kernel_sipa_lock_visible_with_empty_wake_lock(self):
        self.write_sources('soc:ipa-apb:sipa-dele\t20\t20\t0\t0\t33359\t548035\t251972\t576815\t0\n')
        self.assertIn('soc:ipa-apb:sipa-dele', self.ops.wakelocks())

    def test_released_kernel_source_not_listed(self):
        self.write_sources('sipa_dele\t20480\t20480\t0\t0\t0\t548035\t251972\t576815\t0\n')
        self.assertEqual(self.ops.wakelocks(), [])

    def test_userspace_locks_still_listed(self):
        (self.root / 'sys/power/wake_lock').write_text('e5-upgrade\n')
        self.write_sources('')
        self.assertEqual(self.ops.wakelocks(), ['e5-upgrade'])

    def test_unreadable_sources_fail_closed(self):
        self.assertIn('unknown', self.ops.wakelocks())

    def test_unreadable_wake_lock_fail_closed(self):
        (self.root / 'sys/power/wake_lock').unlink()
        self.write_sources('')
        self.assertIn('unknown', self.ops.wakelocks())


class UsbRuntimePmTest(unittest.TestCase):
    """Ops.usb_runtime_pm against a fake UDC tree; glue must stay untouched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.udc = self.root / 'sys/class/udc/25100000.dwc3'
        (self.udc / 'power').mkdir(parents=True)
        (self.udc / 'power/control').write_text('on\n')
        self.glue = self.root / 'sys/devices/platform/soc/soc:ipa-apb/25100000.usb3/power'
        self.glue.mkdir(parents=True)
        (self.glue / 'control').write_text('auto\n')
        self.marker = self.root / 'etc/e5/usb-autosuspend'
        self.marker.parent.mkdir(parents=True)
        self.ops = Ops(self.root)

    def test_applies_auto_to_the_udc_only(self):
        self.marker.write_text('dwc3\n')
        self.assertIsNone(self.ops.usb_runtime_pm())
        self.assertEqual((self.udc / 'power/control').read_text(), 'auto\n')
        self.assertEqual((self.glue / 'control').read_text(), 'auto\n')

    def test_other_board_marker_is_ignored(self):
        self.marker.write_text('e5\n')
        self.assertIsNone(self.ops.usb_runtime_pm())
        self.assertEqual((self.udc / 'power/control').read_text(), 'on\n')

    def test_missing_udc_is_not_an_error(self):
        self.marker.write_text('dwc3\n')
        (self.udc / 'power/control').unlink()
        self.assertIsNone(self.ops.usb_runtime_pm())

    def test_unreadable_marker_is_not_an_error(self):
        self.assertIsNone(self.ops.usb_runtime_pm())
        self.assertEqual((self.udc / 'power/control').read_text(), 'on\n')


if __name__ == '__main__':
    unittest.main()