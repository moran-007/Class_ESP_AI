"""Packaged Turtle helper never imports project files or opens USB on import."""
import importlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class PortableTurtleTests(unittest.TestCase):
    def test_import_is_lazy_and_contains_no_project_path_dependency(self):
        with patch('ai_robot.client.SerialTransport') as serial:
            module=importlib.import_module('ai_robot.turtle')
            serial.assert_not_called()
        self.assertTrue(callable(module.finish))
        with self.assertRaisesRegex(ValueError,'robot|连接'):
            module.finish(SimpleNamespace(),robot=object(),port='COM99')

    def test_packaged_sender_reuses_provided_robot_and_closes_it(self):
        from ai_robot import turtle as module
        events=[]
        class Widget:
            def __init__(self,*args,**kwargs):pass
            def pack(self,**kwargs):pass
            def configure(self,**kwargs):pass
        class Variable:
            def __init__(self,value):pass
            def set(self,value):pass
        tk=SimpleNamespace(Frame=Widget,Button=Widget,Label=Widget,StringVar=Variable)
        root=SimpleNamespace(bind=lambda *a,**k:None,protocol=lambda *a,**k:None)
        screen=SimpleNamespace(getcanvas=lambda:SimpleNamespace(winfo_toplevel=lambda:root),bye=lambda:events.append('bye'))
        robot=SimpleNamespace(start=lambda:events.append('start'),close=lambda:events.append('close'),
            display=SimpleNamespace(image=lambda *a,**k:events.append('image') or {'width':160,'height':128}))
        image=SimpleNamespace(close=lambda:events.append('image_close'))
        with patch.dict(sys.modules,{'tkinter':tk}),patch.object(module,'capture_turtle',return_value=image),patch.object(module,'connect_screen',side_effect=AssertionError('second connection')):
            sender=module._Sender(screen,robot=robot)
            sender.send();sender.send();sender.close()
        self.assertEqual(events,['start','image','image_close','image','image_close','close','bye'])


if __name__=='__main__':unittest.main()
