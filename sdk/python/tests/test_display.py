"""Display SDK payloads and integration; no physical screen is accessed."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_robot import Robot, UnsupportedCapability, DeviceError
from test_sdk import ScriptTransport
from test_native_integration import ProcessTransport

QUICK = Path(__file__).resolve().parents[3] / 'tests/quick'
PORTABLE = Path(__file__).resolve().parents[3] / 'examples/portable'


class DisplaySDKTests(unittest.TestCase):
    def connect(self, supported=True):
        def capabilities(request, result):
            if request['op'] == 'device.info':
                result['data']['capabilities']['display'] = supported
            return result
        wire = ScriptTransport(mutate=capabilities)
        robot = Robot(transport=wire, heartbeat_interval=None)
        self.addCleanup(robot.close)
        return robot, wire

    def test_configure_preserves_servos_and_keeps_maintenance(self):
        robot, wire = self.connect()
        servo = {'name':'head','pin':14,'min_angle':30,'max_angle':150,'min_pulse_us':1000,'max_pulse_us':2000}
        wire.config['servos'] = [copy.deepcopy(servo)]
        robot.display.configure('st7735s_128x160', backlight=16)
        self.assertEqual(wire.config['servos'], [servo])
        self.assertEqual(wire.config['display'], {
            'panel':'st7735s_128x160','sck':4,'mosi':5,'cs':15,'dc':7,'rst':6,
            'backlight':16,'rotation':1,'invert':False,'brightness':60})
        self.assertTrue(wire.maintenance)
        self.assertNotIn('display.begin', [r['op'] for r in wire.requests])
        robot.display.unconfigure()
        self.assertNotIn('display', wire.config)
        self.assertEqual(wire.config['servos'], [servo])
        self.assertTrue(wire.maintenance)

    def test_drawing_payloads_named_and_rgb565_colors(self):
        robot, wire = self.connect()
        robot.display.begin()
        robot.display.fill('red')
        robot.display.clear((0, 255, 0))
        robot.display.text('你好\nESP32', x=10, y=20, color=(55, 88, 99))
        robot.display.rect(1, 2, 30, 40, color=0xFFFF, filled=True)
        robot.display.line(0, 0, 20, 30, color='blue')
        robot.display.brightness(45)
        robot.display.release()
        frames = wire.requests[2:]
        self.assertEqual([r['op'] for r in frames], ['display.begin','display.fill','display.fill','display.text','display.rect','display.line','display.brightness','display.release'])
        self.assertEqual(frames[1]['args'], {'color':0xF800})
        self.assertEqual(frames[2]['args'], {'color':0x07E0})
        self.assertEqual(frames[3]['args'], {'x':10,'y':20,'text':'你好\nESP32','color':0x32CC})
        self.assertEqual(frames[4]['args']['filled'], True)
        self.assertEqual(frames[6]['args'], {'percent':45})

    def test_seven_pin_defaults_and_explicit_zero_brightness(self):
        robot, wire = self.connect()
        robot.display.configure('st7789_240x240')
        display = wire.config['display']
        self.assertEqual((display['backlight'], display['invert'], display['brightness']), (-1, True, 100))
        robot.display.configure(backlight=16, brightness=0)
        self.assertEqual(wire.config['display']['brightness'], 0)

    def test_invalid_arguments_do_not_send_requests(self):
        robot, wire = self.connect()
        count = len(wire.requests)
        invalid = [
            lambda: robot.display.configure('unknown'),
            lambda: robot.display.configure(sck=True),
            lambda: robot.display.configure(sck=5, mosi=5),
            lambda: robot.display.configure(backlight=-2),
            lambda: robot.display.configure(rotation=4),
            lambda: robot.display.configure(invert=1),
            lambda: robot.display.configure(brightness=50),
            lambda: robot.display.fill(True),
            lambda: robot.display.fill((0, 0, 256)),
            lambda: robot.display.fill((0, 0.0, 3)),
            lambda: robot.display.fill('orange'),
            lambda: robot.display.text(''),
            lambda: robot.display.text('中'*65),
            lambda: robot.display.text('\ud800'),
            lambda: robot.display.text('a\0b'),
            lambda: robot.display.text('a\tb'),
            lambda: robot.display.text('a\x85b'),
            lambda: robot.display.text('abc', x=-1),
            lambda: robot.display.rect(0, 0, 0, 5),
            lambda: robot.display.rect(0, 0, 5, 5, filled=1),
            lambda: robot.display.line(0, 0, 320, 4),
            lambda: robot.display.brightness(False),
        ]
        for call in invalid:
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(len(wire.requests), count)

    def test_old_firmware_capability_fails_without_configuration_writes(self):
        robot, wire = self.connect(supported=False)
        before = len(wire.requests)
        for call in (robot.display.begin, robot.display.configure, robot.display.unconfigure,
                     lambda: robot.display.fill('white'), robot.display.release):
            with self.assertRaises(UnsupportedCapability):
                call()
        self.assertEqual(len(wire.requests), before)

    def test_shared_screen_import_never_opens_serial(self):
        before = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, 'path', before))
        sys.path.insert(0, str(QUICK))
        with patch('ai_robot.client.SerialTransport') as serial:
            runpy.run_path(str(QUICK / '_screen.py'))
            serial.assert_not_called()


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'), 'AI_MAKER_NATIVE 未设置')
class DisplayNativeTests(unittest.TestCase):
    def connect(self):
        wire = ProcessTransport(os.environ['AI_MAKER_NATIVE'])
        self.addCleanup(wire.close)
        robot = Robot(transport=wire, heartbeat_interval=None)
        self.addCleanup(robot.close)
        return robot

    def test_real_core_configures_draws_and_releases_without_losing_mapping(self):
        robot = self.connect()
        self.assertTrue(robot.get_info()['capabilities']['display'])
        robot.servo.configure('head', 14)
        robot.display.configure('st7789_240x320', backlight=16)
        config = robot.config.get()['config']
        self.assertEqual(config['servos'][0]['pin'], 14)
        self.assertEqual(config['display']['backlight'], 16)
        with self.assertRaises(DeviceError):
            robot.display.begin()
        robot.maintenance.exit()
        result = robot.display.begin()
        self.assertEqual((result['width'], result['height']), (320, 240))
        robot.display.fill((10, 20, 30))
        robot.display.text('屏幕测试', x=10, y=12)
        robot.display.rect(10, 40, 70, 30, 'yellow', filled=True)
        robot.display.line(0, 0, 319, 239)
        robot.display.brightness(20)
        self.assertTrue(robot.get_status()['display']['active'])
        robot.stop()
        self.assertFalse(robot.get_status()['display']['active'])
        self.assertEqual(robot.config.get()['config'], config)
        robot.display.begin()
        robot.display.release()
        self.assertFalse(robot.get_status()['display']['active'])
        robot.display.unconfigure()
        self.assertNotIn('display', robot.config.get()['config'])
        self.assertEqual(robot.config.get()['config']['servos'][0]['pin'], 14)

    def test_all_three_short_screen_scripts_use_real_core_and_close(self):
        before = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, 'path', before))
        sys.path.insert(0, str(QUICK))
        settings = SimpleNamespace(SCREEN=dict(panel='st7789_240x320', sck=4, mosi=5,
            cs=15, dc=7, rst=6, backlight=16, rotation=1, invert=None, brightness=None), BACKLIGHT=16)
        # screen_text.py is a learner-owned scratch file. Exercise the shipped
        # text example instead, keeping configuration/order/close assertions.
        for script in (QUICK / 'screen_colors.py', PORTABLE / '11_display.py', QUICK / 'screen_backlight.py'):
            with self.subTest(filename=script.name):
                wire = ProcessTransport(os.environ['AI_MAKER_NATIVE'])
                self.addCleanup(wire.close)
                sent = []
                original_write = wire.write
                def record(data):
                    sent.append(json.loads(data))
                    original_write(data)
                wire.write = record
                with patch.dict(sys.modules, {'_screen_settings': settings}), \
                     patch('ai_robot.client.SerialTransport', return_value=wire), \
                     patch.object(Robot, 'wait', return_value=None), redirect_stdout(io.StringIO()):
                    runpy.run_path(str(script), run_name='__main__')
                operations = [r['op'] for r in sent]
                self.assertLess(operations.index('config.apply'), operations.index('maintenance.exit'))
                self.assertLess(operations.index('maintenance.exit'), operations.index('display.begin'))
                self.assertEqual(operations[-1], 'session.close')
                self.assertIsNotNone(wire.process.returncode)


if __name__ == '__main__':
    unittest.main()
