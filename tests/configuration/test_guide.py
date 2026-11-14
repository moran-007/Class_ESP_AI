"""Run the new lessons on the actual production C++ core with alternate pins."""
from contextlib import redirect_stdout
import copy
import io
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'sdk/python/tests'))
from ai_robot import Robot
from test_native_integration import ProcessTransport
import classroom


class RecordingTransport(ProcessTransport):
    def __init__(self, executable):
        super().__init__(executable);self.requests=[]
    def write(self,data):
        self.requests.append(json.loads(data));super().write(data)


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'),'requires production native core')
class GuideTests(unittest.TestCase):
    def test_shared_lessons_use_shared_pins_and_close_the_real_core(self):
        expected={'01_info.py':'pins.list','02_rgb.py':'led.set','03_led.py':'gpio.write',
            '04_button_led.py':'gpio.read','05_adc.py':'adc.read','06_pwm.py':'pwm.write',
            '07_servo.py':'servo.move','08_screen.py':'display.text','09_pages.py':'pages.upload.commit',
            '11_image.py':'display.bitmap'}
        screen=dict(panel='st7735s_128x160',sck=4,mosi=5,cs=15,dc=7,rst=6,backlight=16,
                    rotation=1,invert=False,brightness=60)
        servo=dict(name='test',pin=21,min_angle=30,max_angle=150,min_pulse_us=1000,max_pulse_us=2000)
        pins=dict(led=13,button=18,adc=2,pwm=17)
        if importlib.util.find_spec('PIL') is None:
            expected.pop('11_image.py')  # Optional drawing dependency has separate SDK tests.
        helper=ModuleType('_board')
        for key in ('connect','connect_screen'):setattr(helper,key,getattr(classroom,key))
        helper.PINS=pins;helper.SERVO=servo
        original_wait=Robot.wait
        for filename, operation in expected.items():
            with self.subTest(filename=filename):
                wire=RecordingTransport(os.environ['AI_MAKER_NATIVE'])
                self.addCleanup(wire.close)
                with patch.dict(sys.modules,{'_board':helper}),patch.dict(classroom.SCREEN,screen,clear=True), \
                        patch('ai_robot.client.SerialTransport',return_value=wire), \
                        patch.object(Robot,'wait',lambda robot,seconds:original_wait(robot,min(seconds,.001))), \
                        redirect_stdout(io.StringIO()):
                    runpy.run_path(str(ROOT/'tests/guide_shared'/filename),run_name='__main__')
                requests=wire.requests;operations=[x['op'] for x in requests]
                self.assertIn(operation,operations)
                self.assertEqual(operations[-1],'session.close')
                if filename=='03_led.py':self.assertEqual({x['args']['pin'] for x in requests if x['op']=='gpio.write'},{13})
                if filename=='04_button_led.py':self.assertEqual({x['args']['pin'] for x in requests if x['op']=='gpio.read'},{18})
                if filename=='05_adc.py':self.assertEqual({x['args']['pin'] for x in requests if x['op']=='adc.read'},{2})
                if filename=='06_pwm.py':self.assertEqual({x['args']['pin'] for x in requests if x['op']=='pwm.write'},{17})
                if filename=='07_servo.py':
                    item=next(x['args']['config']['servos'][0] for x in requests if x['op']=='config.apply')
                    self.assertEqual(item['pin'],21)

    def test_inline_lessons_run_without_the_optional_settings_file(self):
        helper=ModuleType('_board')
        helper.connect=classroom.connect;helper.connect_screen=classroom.connect_screen
        helper.Robot=Robot
        expected={'01_info.py':'pins.list','02_rgb.py':'led.set','03_led.py':'gpio.write',
            '04_button_led.py':'gpio.read','05_adc.py':'adc.read','06_pwm.py':'pwm.write',
            '07_servo.py':'servo.move','08_screen.py':'display.text','09_pages.py':'pages.upload.commit',
            '12_multi_parts.py':'servo.move'}
        if importlib.util.find_spec('PIL') is not None:
            expected['11_image.py']='display.bitmap';expected['13_display_fps.py']='display.bitmap'
        original_wait=Robot.wait
        for filename,operation in expected.items():
            with self.subTest(filename=filename):
                wire=RecordingTransport(os.environ['AI_MAKER_NATIVE']);self.addCleanup(wire.close)
                with patch.dict(sys.modules,{'_board':helper}), \
                        patch('classroom._config',None), \
                        patch('classroom.load_config',side_effect=AssertionError('inline mode must not load JSON')), \
                        patch('ai_robot.client.SerialTransport',return_value=wire) as serial, \
                        patch.object(Robot,'wait',lambda robot,seconds:original_wait(robot,min(seconds,.001))), \
                        redirect_stdout(io.StringIO()):
                    runpy.run_path(str(ROOT/'tests/guide'/filename),run_name='__main__')
                self.assertEqual(serial.call_args.args[0],'COM5')
                self.assertIn(operation,[x['op'] for x in wire.requests])
                self.assertEqual(wire.requests[-1]['op'],'session.close')
                if filename=='03_led.py':self.assertEqual({x['args']['pin'] for x in wire.requests if x['op']=='gpio.write'},{12})
                if filename=='08_screen.py':
                    mapping=next(x['args']['config']['display'] for x in wire.requests if x['op']=='config.apply')
                    self.assertEqual([mapping[k] for k in ('sck','mosi','cs','dc','rst','backlight')],[4,5,15,7,6,16])


if __name__=='__main__':unittest.main()
