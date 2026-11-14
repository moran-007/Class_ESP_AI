"""Inline classroom calls work without loading the optional JSON config."""
from pathlib import Path
from contextlib import contextmanager
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'sdk/python/tests'))
import classroom
from test_sdk import ScriptTransport


class InlineConfigurationTests(unittest.TestCase):
    def test_explicit_com_does_not_load_shared_file(self):
        wire=ScriptTransport()
        with patch('classroom._config',None), \
                patch('classroom.load_config',side_effect=AssertionError('shared configuration must be optional')), \
                patch('ai_robot.client.SerialTransport',return_value=wire) as serial:
            with classroom.connect('COM99') as robot:
                robot.get_info()
            self.assertEqual(serial.call_args.args[0],'COM99')
        self.assertEqual(wire.requests[-1]['op'],'session.close')

    def test_explicit_screen_parameters_are_not_merged_with_shared_wiring(self):
        def capabilities(request, result):
            if request['op']=='device.info':result['data']['capabilities']['display']=True
            if request['op']=='device.status':result['data']['display']={'configured':True,'active':False}
            return result
        wire=ScriptTransport(mutate=capabilities)
        with patch('classroom._config',None), \
                patch('classroom.load_config',side_effect=AssertionError('must not read shared wiring')), \
                patch('ai_robot.client.SerialTransport',return_value=wire):
            with classroom.connect_screen('COM99',panel='st7735s_128x160',sck=18,mosi=21,cs=9,dc=10,rst=11,backlight=-1) as robot:
                robot.display.fill('red')
        config=next(r['args']['config']['display'] for r in wire.requests if r['op']=='config.apply')
        self.assertEqual([config[k] for k in ('sck','mosi','cs','dc','rst','backlight')],[18,21,9,10,11,-1])
        self.assertEqual(config['brightness'],100)
        self.assertIn('display.begin',[r['op'] for r in wire.requests])
        self.assertEqual(wire.requests[-1]['op'],'session.close')

    def test_importing_inline_helpers_does_not_read_optional_file(self):
        with patch('classroom._config',None),patch('classroom.load_config',side_effect=AssertionError('no eager JSON')):
            runpy.run_path(str(ROOT/'tests/guide/_board.py'))
            runpy.run_path(str(ROOT/'tests/quick/_board.py'))

    def test_turtle_options_are_forwarded_only_when_send_is_clicked(self):
        previous=sys.path.copy()
        self.addCleanup(lambda:setattr(sys,'path',previous))
        sys.path.insert(0,str(ROOT/'tests/quick'))
        with patch('classroom._config',None),patch('classroom.load_config',side_effect=AssertionError('no JSON')):
            helper=runpy.run_path(str(ROOT/'tests/quick/_turtle.py'))
        cls=helper['_Sender'];events=[];options={'port':'COM99','panel':'st7735s_128x160','sck':18,'mosi':21,'cs':9,'dc':10,'rst':11,'backlight':-1}
        screen=SimpleNamespace(bye=lambda:events.append('bye'),mainloop=lambda:None)
        fake=SimpleNamespace(close=lambda:events.append('close'))
        with patch.dict(helper['finish'].__globals__,_Sender=lambda s,kw:events.append(kw.copy()) or fake):
            helper['finish'](screen,**options)
        self.assertEqual(events,[options,'close'])
        events.clear()
        @contextmanager
        def connector(**kw):
            events.append(kw)
            try:yield SimpleNamespace(display=SimpleNamespace(image=lambda *a,**k:{'width':160,'height':128}))
            finally:events.append('disconnect')
        sender=cls.__new__(cls)
        sender.screen=screen;sender.connect_options=options;sender.context=sender.robot=None
        sender._provided_robot=None;sender._provided_released=False
        sender.busy=sender.closed=False
        sender.button=SimpleNamespace(configure=lambda **kw:None)
        sender.status=SimpleNamespace(set=lambda text:None)
        image=SimpleNamespace(close=lambda:events.append('image_closed'))
        with patch.dict(cls.send.__globals__,connect_screen=connector,capture_turtle=lambda s:image):
            self.assertEqual(events,[])
            sender.send();sender.close()
        self.assertEqual(events,[options,'image_closed','disconnect','bye'])


if __name__=='__main__':unittest.main()
