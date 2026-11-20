"""SDK recording runs against the unchanged production 0.6.0 C++ core."""
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

import ai_robot
from ai_robot import Robot
from test_native_integration import ProcessTransport

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'), 'native core not configured')
class RecordingNativeTests(unittest.TestCase):
    def connect(self, state):
        wire = ProcessTransport(os.environ['AI_MAKER_NATIVE'], state)
        self.addCleanup(wire.close)
        robot = Robot(transport=wire, heartbeat_interval=.2)
        self.addCleanup(robot.close)
        return robot

    def test_preview_capture_save_and_original_config(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            with self.connect(state) as robot:
                robot.servo.set(pin=14, name='arm')
                robot.display.set(panel='st7735s_128x160', backlight=16)
                robot.start()
                config = robot.config.get()
                robot.program.begin()
                robot.display.clear()
                robot.display.text('录制测试', x=8, y=8, color='cyan')
                robot.display.rect(8, 40, 100, 20, color=(155, 88, 99), filled=True)
                robot.display.line(8, 108, 112, 108, color='yellow')
                robot.wait(.02)
                self.assertTrue(robot.get_status()['display']['active'])
                flow = robot.program.end()
                self.assertEqual([s['op'] for s in flow.to_dict()['steps']],
                    ['display.begin', 'display.fill', 'display.text', 'display.rect', 'display.line', 'wait'])
                self.assertFalse(robot.program.info()['saved'])
                robot.program.save(loop=True, autostart=True)
                self.assertEqual(robot.program.download()['program'], flow.to_dict())
                self.assertEqual(robot.config.get(), config)
                robot.program.start()
                self.assertTrue(robot.get_status()['program']['running'])
                robot.program.stop()
                self.assertEqual(robot.config.get(), config)
                robot.program.clear()
            saved = json.loads(Path(str(state)+'.program').read_text(encoding='utf-8'))
            self.assertIsNone(saved['program'])

    def test_portable_two_page_script_previews_records_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            robots = []
            def factory(*args, **kwargs):
                robot = self.connect(state)
                robots.append(robot)
                return robot
            with patch.object(ai_robot, 'Robot', factory):
                runpy.run_path(str(ROOT/'examples/portable/15_screen_record.py'), run_name='__main__')
            self.assertEqual(len(robots), 1)
            self.assertTrue(robots[0]._closed)
            saved = json.loads(Path(str(state)+'.program').read_text(encoding='utf-8'))
            self.assertTrue(saved['enabled'])
            self.assertTrue(saved['loop'])
            steps = saved['program']['steps']
            self.assertEqual(len(steps), 13)
            self.assertEqual([s['args']['ms'] for s in steps if s['op']=='wait'], [3000, 3000])
            texts = [s['args']['text'] for s in steps if s['op']=='display.text']
            self.assertEqual(texts, ['AI Maker', '屏幕测试\n你好，创客！', 'AI Maker', '屏幕测试2\n你好，创客！'])


if __name__ == '__main__':
    unittest.main()
