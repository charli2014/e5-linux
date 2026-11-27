"""Changxing 60 suspend patch wiring and charger wake-lock regression."""
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
TOP = HERE.parents[1]
POWER = TOP / 'devices/common/power'
VCHG_PATCH = POWER / '0008-power-sprd-vchg-ignore-duplicate-absent-wakeup.patch'


class SuspendPatches(unittest.TestCase):
    def test_vchg_patch_applies_reverses_and_keeps_manager_notification(self):
        source = '''static int sprd_vchg_change(struct notifier_block *nb, unsigned long limit, void *data)
{
\tstruct sprd_vchg_info *info = container_of(nb, struct sprd_vchg_info, usb_notify);
\tbool chgr_online = false;

\tif (!info) {
\t\tpr_err("%s:line%d: NULL pointer!!!\\n", SPRD_VCHG_TAG, __LINE__);
\t\treturn NOTIFY_OK;
\t}

\tif (info->shutdown_flag)
\t\treturn NOTIFY_OK;

\tif (info->usb_phy->chg_state == USB_CHARGER_PRESENT)
\t\tchgr_online = true;

\tif (!info->pd_hard_reset) {
\t\tinfo->chgr_online = chgr_online;
\t\tif (info->typec_online) {
\t\t\tinfo->typec_online = false;
\t\t\tdev_info(info->dev, "%s, typec not disconnect while pd hard reset.\\n",
\t\t\t\t SPRD_VCHG_TAG);
\t\t}

\t\t__pm_wakeup_event(info->sprd_vchg_ws, SPRD_VCHG_WAKE_UP_MS);
\t\tschedule_work(&info->sprd_vchg_work);
\t} else {
\t\tinfo->pd_hard_reset = false;
\t}
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            path = root / 'drivers/power/supply/sprd_vchg_detect.c'
            path.parent.mkdir(parents=True)
            path.write_text(source, encoding='utf-8')
            subprocess.run(['git', 'apply', '--check', str(VCHG_PATCH)], cwd=root, check=True)
            subprocess.run(['git', 'apply', str(VCHG_PATCH)], cwd=root, check=True)
            result = path.read_text(encoding='utf-8')
            self.assertIn('chgr_online_changed = info->chgr_online != chgr_online;', result)
            self.assertIn('if (chgr_online_changed)\n\t\t\t__pm_wakeup_event', result)
            self.assertIn('schedule_work(&info->sprd_vchg_work);', result)
            subprocess.run(['git', 'apply', '--reverse', '--check', str(VCHG_PATCH)],
                           cwd=root, check=True)

    def test_changxing60_registers_vchg_patch_last(self):
        module = runpy.run_path(str(HERE / 'prepare-kernel.py'))
        self.assertEqual(module['POWER_PATCHES'][-1], VCHG_PATCH.name)
        self.assertEqual(len(module['POWER_PATCHES']), 7)


if __name__ == '__main__':
    unittest.main()
