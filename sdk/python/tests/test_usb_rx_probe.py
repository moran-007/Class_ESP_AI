"""The USB probe must send genuine large queries without opening a session."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

from ai_robot import Robot
from test_native_integration import ProcessTransport

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.environ.get("AI_MAKER_NATIVE"), "AI_MAKER_NATIVE 未设置")
class USBRegressionTests(unittest.TestCase):
    def test_large_query_probe_uses_single_write_and_no_control_session(self):
        probe = runpy.run_path(str(ROOT / "tests/hardware/04_usb_rx.py"))
        wire = ProcessTransport(os.environ["AI_MAKER_NATIVE"])
        self.addCleanup(wire.close)
        sent = []
        original_write = wire.write
        def record(data):
            sent.append(data)
            original_write(data)
        wire.write = record
        for index, size in enumerate((255, 256, 257, 384, 768, 2048, 4096)):
            result = probe["query"](wire, index, size, 2)
            self.assertTrue(result["passed"], result)
            self.assertEqual(len(sent[-1]), size + 1)
        self.assertEqual(len(sent), 7)
        self.assertTrue(all(json.loads(line)["op"] == "device.info" for line in sent))

    def test_sg90_short_script_uses_conservative_pulses_and_four_targets(self):
        quick = ROOT / "tests/quick"
        old_path = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, "path", old_path))
        sys.path.insert(0, str(quick))
        wire = ProcessTransport(os.environ["AI_MAKER_NATIVE"])
        self.addCleanup(wire.close)
        sent = []
        original_write = wire.write
        def record(data):
            sent.append(json.loads(data))
            original_write(data)
        wire.write = record
        with patch("ai_robot.client.SerialTransport", return_value=wire), \
             patch.object(Robot, "wait", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(quick / "servo_sg90.py"), run_name="__main__")
        config = next(r["args"]["config"] for r in sent if r["op"] == "config.apply")
        self.assertEqual(config["servos"][0]["pin"], 14)
        self.assertEqual((config["servos"][0]["min_pulse_us"], config["servos"][0]["max_pulse_us"]), (1000, 2000))
        self.assertEqual([r["args"]["angle"] for r in sent if r["op"] == "servo.move"], [60, 90, 120, 90])
        self.assertEqual(sent[-1]["op"], "session.close")


if __name__ == "__main__":
    unittest.main()
