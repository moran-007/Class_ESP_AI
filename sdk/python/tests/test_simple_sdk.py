"""Learner-facing convenience calls still use the production SDK contract."""

import time
import unittest

from ai_robot import Robot, ConnectionLostError
from test_sdk import ScriptTransport


class SimpleSDKTests(unittest.TestCase):
    def connect(self, **kwargs):
        wire = ScriptTransport()
        robot = Robot(transport=wire, timeout=0.05, **kwargs)
        self.addCleanup(robot.close)
        return robot, wire

    def test_named_colors_send_bounded_rgb_without_extra_actions(self):
        robot, wire = self.connect(heartbeat_interval=None)
        for name, rgb in (("red", (16, 0, 0)), ("green", (0, 16, 0)),
                          ("blue", (0, 0, 16)), ("yellow", (16, 16, 0)),
                          ("white", (16, 16, 16)), ("off", (0, 0, 0))):
            robot.led.color(name)
            request = wire.requests[-1]
            self.assertEqual(request["op"], "led.set")
            self.assertEqual(tuple(request["args"][key] for key in ("red", "green", "blue")), rgb)
        robot.led.color("white", brightness=32)
        self.assertEqual(wire.requests[-1]["args"], {"red": 32, "green": 32, "blue": 32})
        count = len(wire.requests)
        for name in ("purple_typo", None, 1):
            with self.assertRaises(ValueError): robot.led.color(name)
        for value in (-1, 33, True, 1.0, "1"):
            with self.assertRaises(ValueError): robot.led.color("red", brightness=value)
        self.assertEqual(len(wire.requests), count)

    def test_wait_rejects_invalid_delays_and_closed_connection(self):
        robot, wire = self.connect(heartbeat_interval=None)
        before = len(wire.requests)
        robot.wait(0)
        robot.wait(0.002)
        self.assertEqual(len(wire.requests), before)
        for value in (-1, True, "1", None, float("nan"), float("inf")):
            with self.assertRaises(ValueError): robot.wait(value)
        robot.close()
        with self.assertRaises(ConnectionLostError): robot.wait(0)

    def test_wait_is_interrupted_by_failed_heartbeat(self):
        robot, wire = self.connect(heartbeat_interval=0.01)
        wire.read = lambda *args: (_ for _ in ()).throw(OSError("unplugged"))
        started = time.monotonic()
        with self.assertRaises(ConnectionLostError): robot.wait(2)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(sum(r["op"] == "session.heartbeat" for r in wire.requests), 1)


if __name__ == "__main__": unittest.main()
