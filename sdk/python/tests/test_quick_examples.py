"""Execute the actual short learner scripts against the production C++ core."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

from ai_robot import Robot, RobotError
from test_native_integration import ProcessTransport
from test_sdk import ScriptTransport, response

QUICK = Path(__file__).resolve().parents[3] / "tests" / "quick"


class RecordingTransport(ProcessTransport):
    def __init__(self, executable):
        super().__init__(executable)
        self.requests = []

    def write(self, data):
        self.requests.append(json.loads(data))
        super().write(data)


class QuickHelperTests(unittest.TestCase):
    def load_helper(self):
        old_path = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, "path", old_path))
        sys.path.insert(0, str(QUICK))
        return runpy.run_path(str(QUICK / "_board.py"))

    def test_import_does_not_open_serial(self):
        with patch("ai_robot.client.SerialTransport") as serial:
            self.load_helper()
            serial.assert_not_called()

    def test_action_failure_closes_session_and_exits_unsuccessfully(self):
        helper = self.load_helper()
        wire = ScriptTransport()
        with patch("ai_robot.client.SerialTransport", return_value=wire):
            with self.assertRaisesRegex(SystemExit, "运行失败.*test rejected"):
                with helper["connect"]():
                    raise RobotError("test rejected")
        self.assertTrue(wire.closed)
        self.assertEqual(wire.requests[-1]["op"], "session.close")

    def test_normal_program_exits_unsuccessfully_if_output_release_failed(self):
        helper = self.load_helper()
        def mutate(req, result):
            return response(req, code="HARDWARE_ERROR", message="RGB release failed") if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        with patch("ai_robot.client.SerialTransport", return_value=wire):
            with self.assertRaisesRegex(SystemExit, "运行失败.*HARDWARE_ERROR"):
                with helper["connect"]():
                    pass
        self.assertTrue(wire.closed)


@unittest.skipUnless(os.environ.get("AI_MAKER_NATIVE"), "AI_MAKER_NATIVE 未设置")
@unittest.skipUnless(os.environ.get("AI_MAKER_TEST_EXAMPLES") == "1", "学员示例可自由修改；仅在显式选择示例检查时运行")
class QuickExamplesTests(unittest.TestCase):
    def test_every_short_script_runs_and_closes_real_core_session(self):
        expected = {
            "01_device_info.py": "device.info", "02_rgb.py": "led.set",
            "03_gpio.py": "gpio.write", "04_button.py": "gpio.read",
            "05_adc.py": "adc.read", "06_pwm.py": "pwm.write",
            "07_servo.py": "servo.move", "08_clear_servos.py": "config.apply",
        }
        original_wait = Robot.wait
        old_path = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, "path", old_path))
        sys.path.insert(0, str(QUICK))
        for filename, operation in expected.items():
            with self.subTest(filename=filename):
                wire = RecordingTransport(os.environ["AI_MAKER_NATIVE"])
                self.addCleanup(wire.close)
                with patch("ai_robot.client.SerialTransport", return_value=wire), \
                     patch.object(Robot, "wait", lambda robot, seconds: original_wait(robot, min(seconds, 0.001))), \
                     redirect_stdout(io.StringIO()):
                    runpy.run_path(str(QUICK / filename), run_name="__main__")
                operations = [request["op"] for request in wire.requests]
                self.assertIn(operation, operations)
                self.assertEqual(operations[-1], "session.close")
                self.assertIsNotNone(wire.process.returncode)
                self.assertEqual(operations.count("session.open"), 1)
                if filename == "02_rgb.py":
                    self.assertEqual([r["args"] for r in wire.requests if r["op"] == "led.set"], [
                        {"red": 16, "green": 0, "blue": 0},
                        {"red": 0, "green": 16, "blue": 0},
                        {"red": 0, "green": 0, "blue": 16},
                    ])
                if filename == "07_servo.py":
                    self.assertLess(operations.index("config.apply"), operations.index("maintenance.exit"))
                    self.assertLess(operations.index("maintenance.exit"), operations.index("servo.move"))


if __name__ == "__main__": unittest.main()
