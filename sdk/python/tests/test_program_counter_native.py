"""Actual SDK/C++ timer, persistence and takeover; simulated display only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from ai_robot import Program, Robot
from test_native_integration import ProcessTransport


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'), 'native core not configured')
class CounterNativeTests(unittest.TestCase):
    def transport(self, path):
        wire = ProcessTransport(os.environ['AI_MAKER_NATIVE'], path)
        self.addCleanup(wire.close)
        return wire

    def status(self, wire):
        wire.write(json.dumps(dict(kind='request', protocol_version=1,
            request_id='counter-boot', op='device.status', args={})).encode() + b'\n')
        data = bytearray()
        while b'\n' not in data:
            chunk = wire.read(4096, 2)
            self.assertTrue(chunk)
            data.extend(chunk)
        reply = json.loads(data)
        self.assertTrue(reply['ok'])
        return reply['data']

    def test_counter_restart_timer_no_rewrites_and_takeover(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)/'state.json'
            flow = Program()
            flow.display.set(panel='st7735s_128x160', backlight=16)
            flow.display.fill('black')
            flow.display.text('数字累加', x=8, y=8)
            flow.display.counter(start=0, step=1, interval=1)
            with Robot(transport=self.transport(state), heartbeat_interval=.2) as robot:
                self.assertTrue(robot.get_info()['capabilities']['standalone_counter'])
                robot.program.save(flow, autostart=True)
                self.assertFalse(robot.program.info()['running'])
                self.assertEqual(robot.program.download()['program'], flow.to_dict())
            stored = Path(str(state)+'.program')
            digest = hashlib.sha256(stored.read_bytes()).digest()
            boot = self.transport(state)
            self.status(boot)  # Layout initialization yields before counter clock.
            initial = self.status(boot)
            self.assertFalse(initial['session_active'])
            self.assertTrue(initial['program']['counter']['active'])
            self.assertEqual(initial['program']['counter']['value'], 0)
            time.sleep(2.1)
            later = self.status(boot)
            self.assertGreaterEqual(later['program']['counter']['value'], 2)
            self.assertTrue(later['program']['running'])
            self.assertEqual(hashlib.sha256(stored.read_bytes()).digest(), digest)
            with Robot(transport=boot, heartbeat_interval=.2) as robot:
                self.assertFalse(robot.program.info()['counter']['active'])
                robot.program.start()
                robot.get_status()
                restarted = robot.get_status()
                self.assertEqual(restarted['program']['counter']['value'], 0)
                self.assertTrue(restarted['program']['counter']['active'])
                robot.program.clear()
                self.assertFalse(robot.program.info()['saved'])

    def test_end_recording_then_append_counter_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            with Robot(transport=self.transport(Path(folder)/'state.json'), heartbeat_interval=.2) as robot:
                robot.display.set(panel='st7735s_128x160', backlight=16)
                robot.start()
                robot.program.begin()
                robot.display.clear()
                robot.display.text('count', x=8, y=8)
                flow = robot.program.end()
                flow.display.counter(name='number', start=7, interval=.1)
                robot.program.save(flow)
                self.assertEqual(robot.program.download()['program']['steps'][-1]['args']['start'], 7)
                robot.program.start()
                robot.get_status()
                self.assertEqual(robot.get_status()['program']['counter']['value'], 7)
                robot.program.stop()


if __name__ == '__main__':
    unittest.main()
