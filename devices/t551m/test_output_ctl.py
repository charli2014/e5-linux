"""Drive the production output-ctl client against a mock Wayland compositor.

The mock speaks the real wire format (wl_display/wl_registry/zwlr_output_*),
so the marshalling, the bind, the head snapshot and the apply handshake are
all exercised without a compositor or libwayland on the build host.
"""
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import unittest

SOURCE=(Path(__file__).resolve().parents[1] / 'common/infoscreen')/'native/output-ctl.c'
HEAD=0xFF000001
MODE=0xFF000002


def u32(v):return struct.pack('<I',v&0xFFFFFFFF)
def wstr(s):
    b=s.encode()+b'\0';pad=(len(b)+3)&~3
    return u32(len(b))+b+b'\0'*(pad-len(b))
def msg(sender,opcode,payload=b''):
    return u32(sender)+u32(((8+len(payload))<<16)|opcode)+payload
def recv_n(conn,n):
    buf=b''
    while len(buf)<n:
        chunk=conn.recv(n-len(buf))
        if not chunk:return None
        buf+=chunk
    return buf
def read_msg(conn):
    hdr=recv_n(conn,8)
    if hdr is None:return None
    sender,size_op=struct.unpack('<II',hdr)
    size=size_op>>16
    payload=recv_n(conn,size-8) if size>8 else b''
    if payload is None:return None
    return sender,size_op&0xFFFF,payload
def parse_bind(p):
    l=struct.unpack_from('<I',p,4)[0]
    off=8+((l+3)&~3)
    ver,new_id=struct.unpack_from('<II',p,off)
    return new_id


class Compositor:
    """Advertises one DSI head; records every client request."""
    def __init__(self,path,enabled=True,apply_result=0,advertise=True,error=False):
        self.requests=[];self.manager=None;self.serial=7
        self.enabled=enabled;self.apply_result=apply_result
        self.advertise=advertise;self.error=error
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.bind(path);self.sock.listen(1)
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        conn,_=self.sock.accept()
        with conn:
            while True:
                m=read_msg(conn)
                if m is None:break
                sender,op,payload=m
                self.requests.append((sender,op,payload))
                self.handle(conn,sender,op,payload)
        self.sock.close()

    def advertise_heads(self,conn):
        m=self.manager
        conn.sendall(msg(m,0,u32(HEAD)))
        conn.sendall(msg(HEAD,0,wstr('DSI-1')))
        conn.sendall(msg(HEAD,3,u32(MODE)))
        conn.sendall(msg(MODE,0,u32(480)+u32(854)))
        conn.sendall(msg(MODE,1,u32(60000)))
        conn.sendall(msg(MODE,2,b''))
        conn.sendall(msg(HEAD,4,u32(1 if self.enabled else 0)))
        if self.enabled:
            conn.sendall(msg(HEAD,5,u32(MODE)))
            conn.sendall(msg(HEAD,6,u32(0)+u32(0)))
            conn.sendall(msg(HEAD,8,u32(256)))
        conn.sendall(msg(m,1,u32(self.serial)))

    def handle(self,conn,sender,op,payload):
        if sender==1 and op==1:  # get_registry
            conn.sendall(msg(2,0,u32(1)+wstr('zwlr_output_manager_v1')+u32(4)))
        elif sender==2 and op==0:  # registry.bind
            self.manager=parse_bind(payload)
            if self.error:
                conn.sendall(msg(1,0,u32(self.manager)+u32(0)+wstr('mock refusal')))
            elif self.advertise:
                self.advertise_heads(conn)
        elif sender==self.manager and op==0:  # create_configuration
            self.config=struct.unpack_from('<I',payload,0)[0]
        elif sender==getattr(self,'config',None) and op==2:  # apply
            conn.sendall(msg(self.config,self.apply_result,b''))


class OutputCtl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory();cls.binary=Path(cls.build.name)/'output-ctl'
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',str(SOURCE),'-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def run_ctl(self,cmd,**kw):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        path=str(Path(tmp.name)/'wl')
        comp=Compositor(path,**kw)
        env=dict(os.environ,E5_WAYLAND_SOCKET=path)
        r=subprocess.run([str(self.binary),cmd],env=env,capture_output=True,text=True,timeout=8)
        comp.thread.join(timeout=4)
        return r,comp

    def test_status_on(self):
        r,comp=self.run_ctl('status')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout,'on\n')
        self.assertEqual([(s,o) for s,o,_ in comp.requests],[(1,1),(2,0)])

    def test_status_off(self):
        r,_=self.run_ctl('status',enabled=False)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout,'off\n')

    def test_off_disables_and_applies(self):
        r,comp=self.run_ctl('off')
        self.assertEqual(r.returncode,0,r.stderr)
        cfg=comp.config
        self.assertIn((cfg,1,u32(HEAD)),comp.requests)
        self.assertIn((cfg,2,b''),comp.requests)
        self.assertIn((cfg,4,b''),comp.requests)  # destroy

    def test_on_uses_preferred_mode_when_disabled(self):
        r,comp=self.run_ctl('on',enabled=False)
        self.assertEqual(r.returncode,0,r.stderr)
        cfg=comp.config
        enable=[p for s,o,p in comp.requests if s==cfg and o==0]
        self.assertEqual(len(enable),1)
        ch=struct.unpack_from('<I',enable[0],0)[0]
        self.assertIn((ch,0,u32(MODE)),comp.requests)      # set_mode preferred
        self.assertIn((ch,2,u32(0)+u32(0)),comp.requests)  # set_position
        self.assertIn((ch,4,u32(256)),comp.requests)       # set_scale 1.0
        self.assertIn((cfg,2,b''),comp.requests)

    def test_on_keeps_current_mode_when_enabled(self):
        r,comp=self.run_ctl('on')
        self.assertEqual(r.returncode,0,r.stderr)
        ch=[struct.unpack_from('<I',p,0)[0] for s,o,p in comp.requests if s==comp.config and o==0][0]
        self.assertIn((ch,0,u32(MODE)),comp.requests)

    def test_apply_failed_is_exit_1(self):
        r,_=self.run_ctl('off',apply_result=1)
        self.assertEqual(r.returncode,1)
        self.assertIn('failed',r.stderr)

    def test_compositor_error_is_exit_1(self):
        r,_=self.run_ctl('status',error=True)
        self.assertEqual(r.returncode,1)
        self.assertIn('mock refusal',r.stderr)

    def test_no_advertisement_times_out(self):
        r,_=self.run_ctl('status',advertise=False)
        self.assertEqual(r.returncode,2)
        self.assertIn('timeout',r.stderr)

    def test_missing_socket_is_exit_2(self):
        env=dict(os.environ,E5_WAYLAND_SOCKET='/nonexistent/e5-output-ctl-test')
        r=subprocess.run([str(self.binary),'status'],env=env,capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,2)

    def test_usage(self):
        r=subprocess.run([str(self.binary),'bogus'],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,2)


if __name__=='__main__':unittest.main()