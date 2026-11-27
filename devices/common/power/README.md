# Suspend correctness patches

Imported from [CharlesGool/e5-sleep-kernel, e5-sleep2](https://github.com/CharlesGool/e5-sleep-kernel/tree/52ad641/patches),
2026-10-16. Original project license: GPL-2.0; kernel files retain their SPDX
licenses. Credit: CharlesGool.

- 0001 stops the UMP9620 watchdog across system sleep and rearms it on resume.
- 0002 avoids cancelling DPU writeback work that was never initialized.
- 0004 powers the SPRD GPU down across system suspend and restores it before
  panfrost accesses the hardware on resume.
- 0005 introduces the original-DT camera genpd provider.
- 0006 adapts the last two patches: GPU start failures unwind power, and the
  camera/DCAM/ISP sequencing and three-sample PMU confirmation follow the E5
  stock qogirn6l driver. Clock references and bus failures are handled explicitly.
  The camera provider is built in, matching `sprd,qogirl6l-camsys-domain`.
- 0007 binds the same provider to the UMS9620 (qogirn6pro) node
  `sprd,qogirn6pro-camsys-domain`, from which the driver already reads the
  force/automatic/state triples and `clk_mm_eb`. Without it the bootloader's
  PD_CAMERA stays powered on Changxing 60 and the provider never probes.
- 0008 keeps `sprd_vchg_wakelock` limited to real charger-online transitions.
  Duplicate charger-absent notifications still reach charger-manager but no
  longer take a 1000 ms wake lock and abort suspend while already offline.

## Order and wiring

The files apply in the order above; 0006 is an increment on 0004 and 0005,
0007 on 0006, and 0008 on 0007, so do not reorder them.
`devices/changxing60/prepare-kernel.py` feeds them to `git apply` after the board
preparation, with CRLF normalized, and skips the stack when 0008 already
reverses. They are not applied to any other profile.

The stack was checked against the registered donor commit
`Enceka/linux-lts-e5@020b970e` (0004/0005/0006 as before; 0007 and 0008 apply
and reverse on top of the preceding stack).

## Kernel configuration

The registered UMS9620 baseline (`devices/changxing60/ci-seeds/ums9620-base.config`)
already carries `CONFIG_SPRD_CAMSYS_PD=y`. Required neighbours: `CONFIG_PM_SLEEP`,
`CONFIG_PM_GENERIC_DOMAINS_OF`, `CONFIG_UMP9620_PMIC_WATCHDOG=y`,
`CONFIG_DRM_PANFROST=m`. `CONFIG_PM_DEBUG=y` stays in `kernel.config` for the
`pm_test` staging test. `olddefconfig` runs after the patches, so the camera
symbol is kept instead of being dropped as unknown.

## What is and is not established

- Verified: the patches apply cleanly to the donor source in stack order and
  the patched tree compiles in the Changxing 60 CI kernel job.
- Verified on Changxing 60 hardware (2026-11-26): the running DT node is
  `sprd,qogirn6pro-camsys-domain` with all nine register triples and
  `clk_mm_eb`, and the unaided kernel leaves PD_CAMERA reported as ON
  (DBG_6 = 0) while ISP/DCAM already read off. That is why the provider in
  0005/0006 never bound and AP/PUB deep-sleep counters stayed at 0 during
  real 20 s and 44 s suspends.
- Verified on the Rongyue E5 only: GPU and camera domains off across suspend
  let `AP_DEEP_SLEEP_CNT` advance (0 -> 1 -> 2), with the stock PD_INFO
  snapshot at suspend.
- Verified on Changxing 60 hardware (2026-11-27): after flashing 0007,
  `sprd-camsys-pd` binds and DBG_6 reads `0x07000000` (camera off). A 59.5 s
  RTC suspend completed with IRQ 23, and `AP_DEEP_SLEEP_CNT` advanced 2 -> 3.
- Verified limitation: `AP_DEEP_SLEEP_CNT` also advances on attempts that abort
  during CPU hotplug, so it is not sufficient evidence by itself. Three
  controlled attempts resumed after about 1.65 s. `wakeup_sources` showed
  `sprd_vchg_wakelock` plus battery/FGU activity, and dmesg showed a duplicate
  charger-absent notification (`charger online = 0`) from `sprd-ssphy`. The
  donor `sprd_vchg_detect.c` holds that source for 1000 ms on every notification.
  0008 removes that wake lock for duplicate offline notifications; the fix is
  included in the next build but is not yet verified on Changxing 60 hardware.
- Not verified on Changxing 60: whole-night battery life. The 60 s charge-counter
  delta is too coarse for a current figure, and the 300 s attempt was cut short
  by the charger wakeup, so neither is used as a battery result.

These patches do not initiate suspend, change hotspot policy, disable IPv6,
change polling intervals, or keep eMMC awake. They only affect the corresponding
drivers and compatible devices. CPU idle is enabled separately in the shared
kernel configuration, consistent with the stock E5/T551M/M8 configuration.

The full stack is covered by transition/failure tests and kernel compilation.
It is not a claim of measured battery-life improvement or whole-system deep
sleep validation on all three models. User field tests remain separate.
