#!/usr/bin/env python3
"""P720S20 UFS bring-up, using the shared 41S/M8 UMS9620 platform.

The initial probe loads only display/USB; touch and power diagnostics are
explicit make-probe options. No 41S SGM41513 address remap, ST7123 firmware
or AW883xx amplifier is inherited.

The system-suspend stack under common/power is applied to the donor kernel
after the board preparation. 0006 is an increment on 0004/0005, 0007 is
an increment on 0006, and 0008 is an increment on 0007, so the order is
not interchangeable.
"""
from pathlib import Path
import runpy
import subprocess

HERE=Path(__file__).resolve().parent

POWER_PATCHES=(
    '0001-watchdog-ump9620-stop-across-system-suspend.patch',
    '0002-sprd-dpu-no-cancel-of-uninitialised-wb-work.patch',
    '0004-drm-panfrost-sprd-power-the-GPU-off-across-system-su.patch',
    '0005-soc-sprd-add-the-UMS9621-camera-subsystem-power-doma.patch',
    '0006-sprd-stock-power-sequence-and-error-unwind.patch',
    '0007-soc-sprd-bind-the-UMS9620-camera-power-domain.patch',
    '0008-power-sprd-vchg-ignore-duplicate-absent-wakeup.patch',
)


def apply_power_patches(kernel):
    # git apply reads CRLF checkouts literally; normalize so a reused local
    # kernel view and a fresh Linux CI checkout behave the same.
    git=['git','-c','safe.directory='+str(kernel),'-C',str(kernel),'apply']

    def run(patch, *args):
        text=(HERE.parent/'common/power'/patch).read_text().replace('\r\n','\n')
        return subprocess.run(git+list(args)+['-'],input=text,text=True,
                              capture_output=True)

    # The last patch covers the whole stack: once it reverses, nothing to do.
    if run(POWER_PATCHES[-1],'--reverse','--check').returncode==0:
        return
    for patch in POWER_PATCHES:
        if run(patch,'--reverse','--check').returncode==0:
            continue
        result=run(patch)
        if result.returncode:
            raise SystemExit(f'{patch} does not apply to {kernel}:\n{result.stderr}')


def apply(kernel):
    kernel=Path(kernel)
    full=runpy.run_path(str(HERE.parent/'common/charger-hardware-full.py'))
    full['restore'](kernel)
    runpy.run_path(str(HERE.parent/'m8/prepare-kernel.py'))['apply'](
        kernel,recipient='changxing60',
        charger_adapter=runpy.run_path(str(HERE/'charger.py'))['apply'])
    for path in ('common/ufs.py','common/display-pipeline.py','common/display-dsi-fifo.py','common/dwc3-sink-start.py',
                 'common/display-bindings.py','common/display-resume-planes.py','changxing60/display-ready.py',
                 'yuanhang41s/display.py','yuanhang41s/spi.py','yuanhang41s/display-imports.py',
                 'changxing60/touch.py','changxing60/spi-timing.py',
                 'changxing60/spi-do-stay.py','changxing60/spi-fifo.py',
                 'changxing60/spi-interval.py','changxing60/spi-rx-clear.py','changxing60/audio.py',
                 'changxing60/audio-dapm.py'):
        runpy.run_path(str(HERE.parent/path))['apply'](kernel)
    # Own DT has the legacy UMP96xx CC controller, the combined UMS9620 PHY
    # and a real BQ boost regulator. Reuse the shared manual/host-sink ABI,
    # without importing the 41S TCPM or its charger register table.
    for path in ('common/dwc3-host-policy.py', 'common/dwc3-host-sink.py'):
        runpy.run_path(str(HERE.parent/path))['apply'](kernel)
    full['apply'](kernel)
    apply_power_patches(kernel)


if __name__=='__main__':
    import sys
    apply(sys.argv[1])
