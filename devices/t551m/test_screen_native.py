"""Execute the production C screen-power code against fake sysfs/UCI."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SOURCE=(Path(__file__).resolve().parents[1] / 'common/infoscreen')/'native/screen-power.c'


class ScreenPower(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory();cls.binary=Path(cls.build.name)/'screen-power'
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-DSCREEN_POWER_TEST',str(SOURCE),'-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.light=self.root/'sys/class/backlight/panel/brightness'
        self.touch=self.root/'sys/class/input/input7/inhibited'
        for p in (self.light,self.touch):p.parent.mkdir(parents=True,exist_ok=True);p.write_text('0\n')
        (self.touch.parent/'properties').write_text('2\n')
        for d in ('run','etc/config','tmp/.uci','bin'):(self.root/d).mkdir(parents=True,exist_ok=True)
        self.setting=self.root/'etc/config/e5-infoscreen';self.setting.write_text('1\n')
        uci=self.root/'bin/uci';uci.write_text('#!/bin/sh\ncat "$E5_SCREEN_ROOT/etc/config/e5-infoscreen"\n');uci.chmod(0o755)
        self.trace=self.root/'trace'
        self.env=dict(os.environ,E5_SCREEN_ROOT=str(self.root),SCREEN_POWER_TRACE=str(self.trace),PATH=str(self.root/'bin')+':'+os.environ['PATH'])

    def call(self,*args,ok=True):
        r=subprocess.run([str(self.binary),*args],env=self.env,capture_output=True,text=True,timeout=4)
        self.assertEqual(r.returncode==0,ok,r.stderr)
        return r

    def test_dark_wake_order_and_repeated_operations(self):
        self.call('set','0');self.call('set','180')
        self.assertEqual(self.trace.read_text().splitlines(),['inhibited=1','inhibited=0','brightness=180'])
        for _ in range(4):self.call('set','0');self.call('set','180')
        self.assertEqual(self.touch.read_text(),'0\n')

    def test_explicit_touch_off_and_config_change(self):
        self.setting.write_text('0\n');self.call('set','255');self.assertEqual(self.touch.read_text(),'1\n')
        self.setting.write_text('1\n');self.call('sync');self.assertEqual(self.touch.read_text(),'0\n')

    def test_same_brightness_skips_driver_write_but_reconciles_touch(self):
        self.call('set','120')
        self.trace.write_text('')
        self.setting.write_text('0\n');self.call('set','120')
        self.assertEqual(self.trace.read_text().splitlines(),['inhibited=1'])
        self.setting.write_text('1\n');self.call('set','120')
        self.assertEqual(self.trace.read_text().splitlines(),['inhibited=1','inhibited=0'])
        self.call('set','120')
        self.assertEqual(self.trace.read_text().splitlines(),['inhibited=1','inhibited=0'])

    def test_each_backlight_is_reconciled_independently(self):
        second=self.root/'sys/class/backlight/second/brightness'
        second.parent.mkdir();second.write_text('20\n')
        self.light.write_text('120\n')
        self.call('set','120')
        self.assertEqual(second.read_text(),'120\n')
        self.assertEqual(self.trace.read_text().splitlines(),['brightness=120'])

    def test_driver_names_and_indirect_input(self):
        for name in ('tlsc6x_touch','fts_ts','other-panel'):
            (self.touch.parent/'name').write_text(name);self.call('sync')
        (self.touch.parent/'properties').write_text('0\n');self.call('sync',ok=False)

    def test_external_state_and_restart(self):
        self.light.write_text('120\n');self.touch.write_text('1\n');self.call('sync');self.assertEqual(self.touch.read_text(),'0\n')
        self.light.write_text('0\n');self.call('sync');self.assertEqual(self.touch.read_text(),'1\n')

    def test_invalid_commands_and_clamping(self):
        for args in [('bad',),('set',),('set','bad'),('sync','1')]:self.call(*args,ok=False)
        self.call('set','999');self.assertEqual(self.light.read_text(),'255\n')
        self.call('set','-20');self.assertEqual(self.light.read_text(),'0\n')

    def test_event_watch_config_external_brightness_idle_and_shutdown(self):
        p=subprocess.Popen([str(self.binary),'watch'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        def wait_value(path,value):
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if path.read_text()==value:return
                time.sleep(.01)
            self.fail('Event was not reconciled: '+str(path))
        try:
            wait_value(self.touch,'1\n')
            time.sleep(.05)
            before=self.trace.read_text()
            self.light.write_text('90\n');wait_value(self.touch,'0\n')
            replacement=self.root/'new';replacement.write_text('0\n');replacement.replace(self.setting)
            wait_value(self.touch,'1\n')
            before=self.trace.read_text();time.sleep(.15);self.assertEqual(self.trace.read_text(),before)
        finally:
            p.terminate();out,err=p.communicate(timeout=3);self.assertEqual(p.returncode,0,err)


class ScreenPipeline(unittest.TestCase):
    """Two-stage blanking against a fake output-control client and per-option uci."""
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory();cls.binary=Path(cls.build.name)/'screen-power'
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-DSCREEN_POWER_TEST',str(SOURCE),'-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.light=self.root/'sys/class/backlight/panel/brightness'
        self.touch=self.root/'sys/class/input/input7/inhibited'
        for p in (self.light,self.touch):p.parent.mkdir(parents=True,exist_ok=True);p.write_text('0\n')
        (self.touch.parent/'properties').write_text('2\n')
        for d in ('run','etc/config','tmp/.uci','bin','usr/libexec'):(self.root/d).mkdir(parents=True,exist_ok=True)
        self.cfg=self.root/'etc/config'
        (self.cfg/'touch').write_text('1\n')
        (self.cfg/'pipeline_off').write_text('1\n')
        (self.cfg/'pipeline_grace').write_text('1\n')
        (self.cfg/'ctl_state').write_text('on\n')
        uci=self.root/'bin/uci'
        uci.write_text('#!/bin/sh\ncase "$3" in\n e5-infoscreen.main.*) cat "$E5_SCREEN_ROOT/etc/config/${3##*.}";;\n *) exit 1;;\nesac\n')
        uci.chmod(0o755)
        ctl=self.root/'usr/libexec/e5-output-ctl'
        ctl.write_text('#!/bin/sh\necho "$1" >> "$E5_SCREEN_ROOT/ctl.log"\ncase "$1" in\n status) cat "$E5_SCREEN_ROOT/etc/config/ctl_state";;\n on) printf "on\\n" > "$E5_SCREEN_ROOT/etc/config/ctl_state";;\n off) printf "off\\n" > "$E5_SCREEN_ROOT/etc/config/ctl_state";;\nesac\n')
        ctl.chmod(0o755)
        self.log=self.root/'ctl.log'
        self.env=dict(os.environ,E5_SCREEN_ROOT=str(self.root),PATH=str(self.root/'bin')+':'+os.environ['PATH'])

    def call(self,*args,ok=True):
        r=subprocess.run([str(self.binary),*args],env=self.env,capture_output=True,text=True,timeout=6)
        self.assertEqual(r.returncode==0,ok,r.stderr)
        return r

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def wait_call(self,name,deadline=3.0):
        end=time.monotonic()+deadline
        while time.monotonic()<end:
            if name in self.calls():return
            time.sleep(.02)
        self.fail('output-ctl %s was not invoked: %s'%(name,self.calls()))

    def test_wake_enables_pipeline_before_backlight(self):
        (self.cfg/'ctl_state').write_text('off\n')
        self.call('set','180')
        self.assertEqual(self.calls(),['status','on'])
        self.assertEqual(self.light.read_text(),'180\n')
        self.assertEqual((self.cfg/'ctl_state').read_text(),'on\n')

    def test_external_bright_wake_also_enables(self):
        (self.cfg/'ctl_state').write_text('off\n')
        self.light.write_text('120\n')
        self.call('sync')
        self.assertIn('on',self.calls())

    def test_blank_grace_then_off_and_wake_on(self):
        p=subprocess.Popen([str(self.binary),'watch'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            self.wait_call('off')
            self.assertEqual((self.cfg/'ctl_state').read_text(),'off\n')
            self.light.write_text('90\n')
            end=time.monotonic()+3
            while time.monotonic()<end and self.calls().count('on')<1:time.sleep(.02)
            self.assertIn('on',self.calls())
        finally:
            p.terminate();out,err=p.communicate(timeout=3);self.assertEqual(p.returncode,0,err)

    def test_grace_not_shortened_by_early_poll(self):
        (self.cfg/'pipeline_grace').write_text('2\n')
        p=subprocess.Popen([str(self.binary),'watch'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            time.sleep(.8)
            self.assertNotIn('off',self.calls())
            self.wait_call('off',deadline=3.0)
        finally:
            p.terminate();out,err=p.communicate(timeout=3);self.assertEqual(p.returncode,0,err)

    def test_gate_off_keeps_backlight_only(self):
        (self.cfg/'pipeline_off').write_text('0\n')
        (self.cfg/'ctl_state').write_text('off\n')
        self.call('set','180')
        self.assertEqual(self.light.read_text(),'180\n')
        self.assertEqual(self.calls(),[])

    def test_missing_client_binary_degrades(self):
        (self.root/'usr/libexec/e5-output-ctl').unlink()
        (self.cfg/'ctl_state').write_text('off\n')
        self.call('set','180')
        self.assertEqual(self.light.read_text(),'180\n')
        self.assertEqual(self.calls(),[])

    def test_unknown_compositor_state_gives_up_quietly(self):
        (self.cfg/'ctl_state').write_text('garbage\n')
        p=subprocess.Popen([str(self.binary),'watch'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            self.wait_call('status')
            time.sleep(1.3)
            self.assertNotIn('off',self.calls())
        finally:
            p.terminate();out,err=p.communicate(timeout=3);self.assertEqual(p.returncode,0,err)


if __name__=='__main__':unittest.main()
