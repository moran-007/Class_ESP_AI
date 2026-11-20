"""Public SDK + actual production C++ core, with process restart persistence.

Simulated hardware and file storage do not prove physical NVS power-loss or LEDs.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest

from ai_robot import DeviceError, Program, Robot
from test_native_integration import ProcessTransport


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'), 'native core not configured')
class SavedProgramNativeTests(unittest.TestCase):
    def transport(self, state):
        wire = ProcessTransport(os.environ['AI_MAKER_NATIVE'], state)
        self.addCleanup(wire.close)
        return wire

    def status_before_session(self, wire):
        request = dict(kind='request', protocol_version=1, request_id='boot-proof', op='device.status', args={})
        wire.write(json.dumps(request).encode() + b'\n')
        data = bytearray()
        while b'\n' not in data:
            chunk = wire.read(4096, 2)
            self.assertTrue(chunk, 'native response must arrive')
            data.extend(chunk)
            self.assertLessEqual(len(data), 4096)
        reply = json.loads(data)
        self.assertTrue(reply['ok'])
        return reply['data']

    def test_save_restart_without_owner_then_sdk_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            flow = Program()
            flow.led.color('red', brightness=8)
            flow.wait(1)
            flow.led.color('green', brightness=8)
            flow.wait(1)
            with Robot(transport=self.transport(state), heartbeat_interval=None) as robot:
                result = robot.program.save(flow, loop=True, autostart=True)
                self.assertTrue(result['saved'])
                self.assertFalse(robot.program.info()['running'])
                self.assertEqual(flow.to_dict(), robot.program.download()['program'])
            restarted = self.transport(state)
            boot = self.status_before_session(restarted)
            self.assertFalse(boot['session_active'])
            self.assertTrue(boot['program']['running'])
            self.assertEqual(boot['led']['red'], 8)
            with Robot(transport=restarted, heartbeat_interval=None) as robot:
                self.assertFalse(robot.program.info()['running'])
                self.assertEqual(robot.get_status()['led']['red'], 0)
                robot.program.disable()
            boot = self.status_before_session(self.transport(state))
            self.assertFalse(boot['program']['enabled'])
            self.assertFalse(boot['program']['running'])

    def test_explicit_start_stop_and_clear_use_public_api(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = Program()
            flow.digital.set(12, mode='output')
            flow.digital.write(12, 1)
            flow.wait(1)
            with Robot(transport=self.transport(Path(directory)/'state.json'), heartbeat_interval=None) as robot:
                robot.program.save(flow, loop=True)
                robot.program.start()
                status = robot.get_status()
                self.assertTrue(status['program']['running'])
                self.assertEqual(status['gpio'][0]['value'], 1)
                with self.assertRaises(DeviceError) as error:
                    robot.led.off()
                self.assertEqual(error.exception.code, 'RESOURCE_CONFLICT')
                robot.program.stop()
                self.assertFalse(robot.program.info()['running'])
                robot.program.clear()
                self.assertFalse(robot.program.info()['saved'])
                with self.assertRaises(DeviceError) as error:
                    robot.program.download()
                self.assertEqual(error.exception.code, 'DEVICE_NOT_FOUND')

    def test_largest_text_flow_still_fits_protocol_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = Program()
            flow.display.set(panel='st7735s_128x160', backlight=16)
            # Repeated legal text makes a near-limit saved program and download.
            while True:
                candidate = Program.from_dict(flow.to_dict())
                candidate.display.text('中' * 60, x=0, y=0)
                try:
                    candidate.to_dict()
                except ValueError:
                    break
                flow = candidate
            with Robot(transport=self.transport(Path(directory)/'state.json'), heartbeat_interval=None) as robot:
                robot.program.save(flow)
                self.assertEqual(flow.to_dict(), robot.program.download()['program'])


if __name__ == '__main__':
    unittest.main()
