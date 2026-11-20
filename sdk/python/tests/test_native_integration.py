"""Cross-process checks against the same C++ core compiled for the ESP32.

Set AI_MAKER_NATIVE to the native firmware executable. This is still simulated
electrical hardware, not physical GPIO/ADC/servo verification.
"""

import os
from pathlib import Path
import queue
import subprocess
import threading
import unittest

from ai_robot import Robot, DeviceError


class ProcessTransport:
    def __init__(self, executable, *arguments):
        self.process = subprocess.Popen(
            [str(executable), *map(str, arguments)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, bufsize=0,
        )
        self._queue = queue.Queue()
        self._pending = bytearray()
        self._closed = False
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self):
        try:
            while chunk := os.read(self.process.stdout.fileno(), 256):
                self._queue.put(chunk)
        finally:
            self._queue.put(None)

    def write(self, data):
        if self.process.poll() is not None:
            raise OSError(f"native process exited: {self.process.returncode}")
        if self.process.stdin.write(data) != len(data):
            raise OSError("incomplete native request")
        self.process.stdin.flush()

    def read(self, size, timeout):
        if not self._pending:
            try: chunk = self._queue.get(timeout=timeout)
            except queue.Empty: return b""
            if chunk is None: raise OSError("native stdout closed")
            self._pending.extend(chunk)
        result = bytes(self._pending[:size])
        del self._pending[:size]
        return result

    def close(self):
        if self._closed: return
        self._closed = True
        self.process.stdin.close()
        try: self.process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2.0)
        self._reader.join(1.0)
        self.process.stdout.close()


@unittest.skipUnless(os.environ.get("AI_MAKER_NATIVE"), "AI_MAKER_NATIVE 未设置，未执行真实 C++ 核心联调")
class NativeIntegrationTests(unittest.TestCase):
    def connect(self):
        executable = Path(os.environ["AI_MAKER_NATIVE"])
        self.assertTrue(executable.is_file(), f"native executable not found: {executable}")
        wire = ProcessTransport(executable)
        self.addCleanup(wire.close)
        robot = Robot(transport=wire, heartbeat_interval=None, timeout=2.0)
        self.addCleanup(robot.close)
        return robot

    def test_servo_configure_maintenance_move_remap_and_close(self):
        robot = self.connect()
        self.assertEqual(robot.get_info()["firmware_family"], "ai-maker-s3")
        self.assertTrue(robot.get_info()["capabilities"]["servo"])
        original = robot.config.get()
        applied = robot.servo.configure("head", 12, min_angle=30, max_angle=150)
        self.assertGreater(applied["revision"], original["revision"])
        self.assertTrue(robot.get_status()["maintenance"])
        with self.assertRaises(DeviceError) as raised: robot.servo.move("head", 60)
        self.assertEqual(raised.exception.code, "MAINTENANCE_REQUIRED")
        robot.maintenance.exit()
        commanded = robot.servo.move("head", 60)
        self.assertEqual(commanded["angle"], 60)
        self.assertEqual(commanded["state"], "commanded")
        self.assertIs(commanded["position_verified"], False)
        with self.assertRaises(DeviceError) as raised: robot.servo.move("head", 10)
        self.assertEqual(raised.exception.code, "ANGLE_OUT_OF_RANGE")
        robot.servo.release("head")
        robot.servo.configure("head", 13)
        self.assertEqual(robot.config.get()["config"]["servos"][0]["pin"], 13)
        robot.maintenance.exit()
        robot.gpio.setup(12, "output")  # Old servo pin was released by remap.
        robot.gpio.write(12, 1)
        robot.stop()
        robot.close()

    def test_gpio_adc_pwm_and_reserved_resources(self):
        robot = self.connect()
        pins = robot.list_pins()
        self.assertTrue(any(item["pin"] == 12 for item in pins))
        robot.gpio.setup(12, "output")
        robot.gpio.write(12, 1)
        self.assertEqual(robot.gpio.read(12), 1)
        robot.gpio.release(12)
        robot.gpio.setup(1, "input")
        reading = robot.adc.read(1)
        self.assertIs(type(reading), int)
        self.assertGreaterEqual(reading, 0)
        self.assertLessEqual(reading, 4095)
        robot.gpio.setup(12, "pwm")
        self.assertEqual(robot.pwm.write(12, 25)["frequency_hz"], 1000)
        with self.assertRaises(DeviceError) as raised: robot.gpio.setup(19, "output")
        self.assertEqual(raised.exception.code, "PIN_RESERVED")
        robot.stop()

    def test_config_revision_and_pin_conflict_are_rejected(self):
        robot = self.connect()
        original = robot.config.get()
        robot.servo.configure("head", 12)
        with self.assertRaises(DeviceError) as raised:
            robot.config.apply(original["config"], expected_revision=original["revision"])
        self.assertEqual(raised.exception.code, "CONFIG_REVISION_MISMATCH")
        before = robot.config.get()
        duplicate = dict(before["config"])
        duplicate["servos"] = [dict(before["config"]["servos"][0]), dict(before["config"]["servos"][0], name="arm")]
        with self.assertRaises(DeviceError): robot.config.apply(duplicate, expected_revision=before["revision"])
        self.assertEqual(robot.config.get(), before)

    def test_builtin_led_state_stop_and_maintenance(self):
        robot = self.connect()
        self.assertTrue(robot.get_info()["capabilities"]["builtin_led"])
        for color in ({"red": 8}, {"green": 8}, {"blue": 8}):
            commanded = robot.led.set(**color)
            self.assertEqual(commanded["state"], "commanded")
            self.assertIs(commanded["physical_verified"], False)
            expected = {"red": color.get("red", 0), "green": color.get("green", 0), "blue": color.get("blue", 0)}
            led = robot.get_status()["led"]
            self.assertEqual({key: led[key] for key in expected}, expected)
        robot.stop()
        stopped = robot.get_status()["led"]
        self.assertEqual((stopped["red"], stopped["green"], stopped["blue"]), (0, 0, 0))
        robot.led.set(red=8)
        robot.led.off()
        off = robot.get_status()["led"]
        self.assertEqual((off["red"], off["green"], off["blue"]), (0, 0, 0))
        robot.maintenance.enter()
        with self.assertRaises(DeviceError) as raised: robot.led.set(blue=8)
        self.assertEqual(raised.exception.code, "MAINTENANCE_REQUIRED")


if __name__ == "__main__": unittest.main()
