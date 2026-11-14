"""Turtle may use a Robot configured at the top, never opening a second USB."""
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


class ExistingRobotTests(unittest.TestCase):
    def setUp(self):
        previous=sys.path.copy();self.addCleanup(lambda:setattr(sys,'path',previous))
        sys.path.insert(0,str(ROOT/'tests/quick'))
        self.helper=runpy.run_path(str(ROOT/'tests/quick/_turtle.py'))
        self.events=[]
        class Widget:
            def __init__(self,*args,**kwargs):self.options=kwargs
            def pack(self,**kwargs):pass
            def configure(self,**kwargs):self.options.update(kwargs)
        class Variable:
            def __init__(self,value):self.value=value
            def set(self,value):self.value=value
        self.tk=SimpleNamespace(Frame=Widget,Button=Widget,Label=Widget,StringVar=Variable,
            messagebox=SimpleNamespace(showerror=lambda *a,**k:self.events.append('error')))
        root=SimpleNamespace(bind=lambda *a,**k:None,protocol=lambda *a,**k:None)
        self.screen=SimpleNamespace(getcanvas=lambda:SimpleNamespace(winfo_toplevel=lambda:root),
            bye=lambda:self.events.append('bye'),mainloop=lambda:None)
        self.robot=SimpleNamespace(start=lambda:self.events.append('start'),close=lambda:self.events.append('close'),
            display=SimpleNamespace(image=lambda *a,**k:self.events.append('image') or {'width':160,'height':128}))

    def make_sender(self):
        with patch.dict(sys.modules,{'tkinter':self.tk}):
            return self.helper['_Sender'](self.screen,robot=self.robot)

    def test_reuses_existing_robot_for_two_sends_and_closes_once(self):
        sender=self.make_sender()
        self.assertEqual(self.events,[])
        image=SimpleNamespace(close=lambda:self.events.append('image_close'))
        with patch.dict(sender.send.__globals__,capture_turtle=lambda s:image), \
                patch.dict(sender.send.__globals__,connect_screen=lambda **kw:self.fail('second USB connection')):
            sender.send();sender.send();sender.close();sender.close()
        self.assertEqual(self.events,['start','image','image_close','image','image_close','close','bye'])

    def test_closing_before_send_also_closes_the_configured_robot(self):
        sender=self.make_sender();sender.close()
        self.assertEqual(self.events,['close','bye'])

    def test_send_failure_closes_once_and_never_reconnects(self):
        sender=self.make_sender()
        self.robot.start=lambda:(_ for _ in ()).throw(RuntimeError('failed existing robot'))
        image=SimpleNamespace(close=lambda:self.events.append('image_close'))
        with patch.dict(sys.modules,{'tkinter':self.tk}), \
                patch.dict(sender.send.__globals__,capture_turtle=lambda s:image), \
                patch.dict(sender.send.__globals__,connect_screen=lambda **kw:self.fail('no reconnect')):
            sender.send();sender.send();sender.close()
        self.assertEqual(self.events.count('close'),1)
        self.assertTrue(sender._provided_released)

    def test_existing_robot_cannot_be_mixed_with_a_second_port_config(self):
        with self.assertRaisesRegex(ValueError,'robot|连接'):
            self.helper['finish'](self.screen,robot=self.robot,port='COM99')

    def test_finish_passes_existing_robot_and_cleans_up_on_loop_exit(self):
        received=[]
        def factory(screen,options,*,robot):
            received.append((screen,options,robot))
            return SimpleNamespace(close=lambda:self.events.append('close'))
        with patch.dict(self.helper['finish'].__globals__,_Sender=factory):
            self.helper['finish'](self.screen,robot=self.robot)
        self.assertEqual(received,[(self.screen,{},self.robot)])
        self.assertEqual(self.events,['close'])


if __name__=='__main__':unittest.main()
