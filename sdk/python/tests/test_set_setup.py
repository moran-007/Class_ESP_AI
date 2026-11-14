"""Simple set() spelling and start phase must preserve existing contracts."""
import json
import os
import unittest
from unittest.mock import patch
from ai_robot import Robot
from test_sdk import ScriptTransport
from test_native_integration import ProcessTransport


class SetSetupTests(unittest.TestCase):
    def setUp(self):
        def display_capability(request,result):
            if request['op']=='device.info':result['data']['capabilities']['display']=True
            return result
        self.wire=ScriptTransport(mutate=display_capability)
        self.robot=Robot(transport=self.wire,heartbeat_interval=None)
        self.addCleanup(self.robot.close)

    def test_common_silkscreen_aliases_save_canonical_config(self):
        self.robot.display.set(SCL=4,SDA=5,CS=15,DC=7,RES=6,BLK=16,panel='st7735s_128x160')
        self.assertEqual({k:self.wire.config['display'][k] for k in ('sck','mosi','cs','dc','rst','backlight')},
                         dict(sck=4,mosi=5,cs=15,dc=7,rst=6,backlight=16))
        self.assertTrue(self.wire.maintenance)
        self.assertNotIn('display.begin',[r['op'] for r in self.wire.requests])

    def test_positional_signal_order_and_servo_sg90_preset(self):
        self.robot.display.set(4,5,15,7,6,16,panel='st7735s_128x160')
        self.robot.servo.set(14)
        self.assertEqual(self.wire.config['servos'][0]['name'],'test')
        self.assertEqual(self.wire.config['servos'][0]['min_pulse_us'],1000)
        self.assertIn('display',self.wire.config)

    def test_unknown_ambiguous_duplicate_and_power_labels_fail_before_io(self):
        for args in ({'sck':4,'SCL':5},{'SDA':5,'DIN':5},{'SDA':None,'DIN':5},{'VCC':3},{'GND':0},{'scll':4}):
            with self.subTest(args=args):
                count=len(self.wire.requests)
                with self.assertRaisesRegex(ValueError,'SCK|供电|重复|丝印'):
                    self.robot.display.set(**args)
                self.assertEqual(len(self.wire.requests),count)

    def test_fps_is_local_bounded_and_does_not_enter_firmware_config(self):
        for value in (0,61,True,2.5):
            with self.subTest(value=value):
                count=len(self.wire.requests)
                with self.assertRaises(ValueError):self.robot.display.set(fps=value)
                self.assertEqual(len(self.wire.requests),count)
        self.robot.display.set(fps=10)
        self.assertNotIn('fps',self.wire.config['display'])

    def test_image_frame_start_is_paced_but_low_level_text_is_not(self):
        try:from PIL import Image
        except ImportError:self.skipTest('Pillow optional')
        clock=[10.0]
        def reply(request,result):
            if request['op']=='device.info':result['data']['capabilities'].update(display=True,display_bitmap=True)
            if request['op']=='device.status':result['data']['display']={'active':True,'width':4,'height':4}
            return result
        wire=ScriptTransport(mutate=reply)
        with Robot(transport=wire,heartbeat_interval=None) as robot:
            robot.display.set(fps=10)
            waits=[]
            def wait(seconds):waits.append(seconds);clock[0]+=seconds
            with patch('ai_robot.client.time.monotonic',side_effect=lambda:clock[0]),patch.object(robot,'wait',side_effect=wait),Image.new('RGB',(4,4),'red') as image:
                robot.display.image(image)
                robot.display.text('x')
                self.assertEqual(waits,[])
                robot.display.image(image)
                self.assertAlmostEqual(waits[0],.1)
                clock[0]+=.2
                robot.display.image(image)
                self.assertAlmostEqual(waits[1],0)


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'),'needs production core')
class SetSetupNativeTests(unittest.TestCase):
    def test_screen_and_two_servos_share_one_session_and_start_without_motion(self):
        wire=ProcessTransport(os.environ['AI_MAKER_NATIVE']);self.addCleanup(wire.close)
        with Robot(transport=wire,heartbeat_interval=None) as robot:
            robot.display.set(SCL=4,SDA=5,CS=15,DC=7,RES=6,BLK=16,panel='st7735s_128x160')
            robot.servo.set(14)
            robot.servo.set(13,name='second')
            self.assertTrue(robot.get_status()['maintenance'])
            robot.start()
            status=robot.get_status()
            self.assertTrue(status['display']['active'])
            self.assertFalse(any(s['active'] for s in status['servos']))
            robot.display.text('多外设')
            robot.servo.move('test',90)
            robot.servo.move('second',90)
            status=robot.get_status()
            self.assertTrue(status['display']['active'])
            self.assertTrue(all(s['active'] for s in status['servos']))
            robot.start()  # Does not reinitialize an already active screen.
            self.assertTrue(all(s['active'] for s in robot.get_status()['servos']))


if __name__=='__main__':unittest.main()
