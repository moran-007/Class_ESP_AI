"""Exercise the real legacy RGB CLI against the production C++ core, no ports."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_native_integration import ProcessTransport
from test_sdk import ScriptTransport

SCRIPT = Path(__file__).resolve().parents[3] / "tests" / "hardware" / "02_builtin_rgb.py"


class HardwareRGBScriptTests(unittest.TestCase):
    def run_script(self, factory, *, lease=False):
        old_path = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, "path", old_path))
        script = runpy.run_path(str(SCRIPT))
        real_sleep = time.sleep
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            arguments = [str(SCRIPT), "--port", "TEST-NATIVE", "--run", "--cycles", "1", "--hold", "0.1", "--report", str(report)]
            if lease:
                arguments.append("--lease-test")
            # Color observation waits are skipped; the lease test uses the real
            # production 6-second clock and a real 6.4-second wait.
            with patch.object(sys, "argv", arguments), \
                 patch("ai_robot.client.SerialTransport", side_effect=factory), \
                 patch("time.sleep", side_effect=lambda seconds: real_sleep(seconds) if seconds >= 6 else None), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = script["main"]()
            return result, json.loads(report.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.environ.get("AI_MAKER_NATIVE"), "AI_MAKER_NATIVE 未设置")
    def test_normal_and_expired_lease_accept_extended_led_status(self):
        wires = []
        def factory(*args, **kwargs):
            wire = ProcessTransport(os.environ["AI_MAKER_NATIVE"])
            wires.append(wire)
            self.addCleanup(wire.close)
            return wire
        for lease in (False, True):
            with self.subTest(lease=lease):
                result, report = self.run_script(factory, lease=lease)
                self.assertEqual(result, 0, report.get("error"))
                self.assertEqual(report["software_result"], "passed")
                self.assertEqual(len(report["commands"]), 3)
                self.assertTrue(all(item["state"]["driver_ok"] for item in report["commands"]))
                if lease:
                    self.assertTrue(report["lease_expiry"]["passed"])
                    self.assertFalse(report["lease_expiry"]["state"]["session_active"])
        self.assertTrue(all(wire._closed for wire in wires))

    def test_driver_failure_is_not_a_successful_color_match(self):
        led = {"red": 0, "green": 0, "blue": 0}
        def mutate(request, result):
            if request["op"] == "device.info":
                result["data"]["capabilities"]["builtin_led"] = True
            elif request["op"] == "led.set":
                led.update(request["args"])
            elif request["op"] == "device.status":
                result["data"]["led"] = {**led, "driver_ok": False, "physical_verified": False}
            return result
        result, report = self.run_script(lambda *args, **kwargs: ScriptTransport(mutate=mutate))
        self.assertEqual(result, 1)
        self.assertEqual(report["software_result"], "failed")


if __name__ == "__main__": unittest.main()
