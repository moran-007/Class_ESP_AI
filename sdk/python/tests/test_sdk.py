"""SDK protocol behavior; this emulator is not hardware verification."""

import json
import threading
import time
import unittest
from unittest.mock import patch

from ai_robot import (
    Robot, RobotError, ProtocolError, DeviceError, RequestTimeout,
    ConnectionLostError, UnsupportedCapability, SerialTransport,
)


def response(request, data=None, *, code="OK", message="rejected"):
    result = {
        "kind": "response", "protocol_version": 1,
        "request_id": request["request_id"], "ok": code == "OK", "code": code,
    }
    if code == "OK": result["data"] = {} if data is None else data
    else: result["message"] = message
    return result


class ScriptTransport:
    def __init__(self, mutate=None, chunk_size=256):
        self.requests = []
        self.buffer = bytearray()
        self.closed = False
        self.chunk_size = chunk_size
        self.mutate = mutate
        self.config = {"schema_version": 1, "servos": []}
        self.revision = 0
        self.maintenance = False

    def write(self, data):
        request = json.loads(data)
        self.requests.append(request)
        op = request["op"]
        values = {
            "device.info": {"firmware_family": "ai-maker-s3", "protocol_version": 1, "boot_id": "boot-a", "capabilities": {}},
            "session.open": {"session_id": request["session_id"], "lease_ms": 6000},
            "session.heartbeat": {"lease_ms": 6000},
            "session.close": {"closed": True},
            "device.status": {"session_active": True, "maintenance": self.maintenance, "servos": []},
            "pins.list": {"pins": [{"pin": 12, "output": True}]},
            "config.get": {"revision": self.revision, "config": self.config},
            "gpio.read": {"pin": 1, "value": 1},
            "adc.read": {"pin": 1, "raw": 2048, "bits": 12},
        }
        if op == "maintenance.enter": self.maintenance = True
        elif op == "maintenance.exit": self.maintenance = False
        elif op == "config.apply":
            self.config = request["args"]["config"]
            self.revision += 1
        if op == "config.apply": values[op] = {"revision": self.revision, "config": self.config}
        result = response(request, values.get(op, request["args"]))
        if self.mutate is not None:
            result = self.mutate(request, result)
        if result is not None:
            encoded = result if isinstance(result, bytes) else json.dumps(result).encode() + b"\n"
            self.buffer.extend(encoded)

    def read(self, size, timeout):
        if not self.buffer:
            time.sleep(min(timeout, 0.001))
            return b""
        size = min(size, self.chunk_size, len(self.buffer))
        chunk = bytes(self.buffer[:size])
        del self.buffer[:size]
        return chunk

    def close(self): self.closed = True


class SDKTests(unittest.TestCase):
    def connect(self, transport=None, **kwargs):
        transport = transport or ScriptTransport()
        robot = Robot(transport=transport, heartbeat_interval=None, timeout=0.05, **kwargs)
        self.addCleanup(robot.close)
        return robot, transport

    def test_fragmented_frames_and_multiple_requests(self):
        robot, wire = self.connect(ScriptTransport(chunk_size=3))
        self.assertEqual(robot.gpio.read(1), 1)
        self.assertEqual(robot.adc.read(1), 2048)
        self.assertEqual(len(robot.list_pins()), 1)
        self.assertTrue(robot.get_status()["session_active"])
        ids = [r["request_id"] for r in wire.requests]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual(len(wire.requests[0]["session_id"]), 40)

    def test_boot_noise_wrong_ids_and_log_frames_are_ignored(self):
        def mutate(req, result):
            wrong = dict(result, request_id="stale-response")
            return b"ROM boot\n\xff\n" + json.dumps({"kind": "log", "text": "hello"}).encode() + b"\n" + json.dumps(wrong).encode() + b"\n" + json.dumps(result).encode() + b"\n"
        robot, _ = self.connect(ScriptTransport(mutate=mutate))
        self.assertTrue(robot.get_status()["session_active"])

    def test_oversize_boot_line_recovers_at_newline(self):
        def mutate(req, result):
            return b"x" * 9000 + b"\n" + json.dumps(result).encode() + b"\n"
        robot, _ = self.connect(ScriptTransport(mutate=mutate, chunk_size=23))
        self.assertTrue(robot.get_status()["session_active"])

    def test_wrong_device_closes_transport_without_opening_lease(self):
        def mutate(req, result):
            result["data"]["firmware_family"] = "unrelated-device"
            return result
        wire = ScriptTransport(mutate=mutate)
        with self.assertRaises(ProtocolError): Robot(transport=wire, heartbeat_interval=None)
        self.assertTrue(wire.closed)
        self.assertEqual([r["op"] for r in wire.requests], ["device.info"])

    def test_response_protocol_rejected(self):
        def mutate(req, result): return dict(result, protocol_version=2)
        wire = ScriptTransport(mutate=mutate)
        with self.assertRaises(ProtocolError): Robot(transport=wire, heartbeat_interval=None)
        self.assertTrue(wire.closed)

    def test_boolean_protocol_is_not_integer_version(self):
        def mutate(req, result):
            result["data"]["protocol_version"] = True
            return result
        wire = ScriptTransport(mutate=mutate)
        with self.assertRaises(ProtocolError): Robot(transport=wire, heartbeat_interval=None)
        self.assertTrue(wire.closed)

    def test_error_exposes_device_code_and_request_id(self):
        def mutate(req, result):
            return response(req, code="PIN_RESERVED", message="引脚保留") if req["op"] == "gpio.setup" else result
        robot, _ = self.connect(ScriptTransport(mutate=mutate))
        with self.assertRaises(DeviceError) as raised: robot.gpio.setup(19, "output")
        self.assertEqual(raised.exception.code, "PIN_RESERVED")
        self.assertTrue(raised.exception.request_id.startswith("r"))
        self.assertIn("引脚保留", str(raised.exception))

    def test_command_timeout_does_not_retry_action(self):
        def mutate(req, result): return None if req["op"] == "servo.move" else result
        robot, wire = self.connect(ScriptTransport(mutate=mutate))
        with self.assertRaises(RequestTimeout): robot.servo.move("head", 60)
        self.assertEqual(sum(r["op"] == "servo.move" for r in wire.requests), 1)

    def test_handshake_timeout_closes_transport(self):
        wire = ScriptTransport(mutate=lambda req, result: None)
        with self.assertRaises(RequestTimeout): Robot(transport=wire, timeout=0.01, heartbeat_interval=None)
        self.assertTrue(wire.closed)

    def test_context_close_releases_lease_once(self):
        wire = ScriptTransport()
        with Robot(transport=wire, heartbeat_interval=None) as robot:
            self.assertFalse(wire.closed)
        robot.close()
        self.assertTrue(wire.closed)
        self.assertEqual(sum(r["op"] == "session.close" for r in wire.requests), 1)
        with self.assertRaises(ConnectionLostError): robot.get_status()

    def test_normal_context_reports_firmware_close_error_and_closes_transport(self):
        def mutate(req, result):
            return response(req, code="HARDWARE_ERROR", message="RGB release failed") if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        with self.assertRaises(DeviceError) as raised:
            with Robot(transport=wire, heartbeat_interval=None):
                pass
        self.assertEqual(raised.exception.code, "HARDWARE_ERROR")
        self.assertTrue(wire.closed)

    def test_body_error_survives_firmware_close_error(self):
        def mutate(req, result):
            return response(req, code="HARDWARE_ERROR") if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        original = ValueError("original learner error")
        with self.assertRaises(ValueError) as raised:
            with Robot(transport=wire, heartbeat_interval=None):
                raise original
        self.assertIs(raised.exception, original)
        self.assertTrue(wire.closed)
        self.assertEqual(wire.requests[-1]["op"], "session.close")

    def test_explicit_close_error_still_marks_closed_and_is_idempotent(self):
        def mutate(req, result):
            return response(req, code="HARDWARE_ERROR") if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        robot = Robot(transport=wire, heartbeat_interval=None)
        self.addCleanup(robot.close)
        with self.assertRaises(DeviceError): robot.close()
        self.assertTrue(wire.closed)
        robot.close()
        self.assertEqual(sum(r["op"] == "session.close" for r in wire.requests), 1)
        with self.assertRaises(ConnectionLostError): robot.get_status()

    def test_close_timeout_remains_best_effort(self):
        def mutate(req, result):
            return None if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        with Robot(transport=wire, heartbeat_interval=None, timeout=0.01):
            pass
        self.assertTrue(wire.closed)
        self.assertEqual(sum(r["op"] == "session.close" for r in wire.requests), 1)

    def test_expired_session_close_is_already_released(self):
        def mutate(req, result):
            return response(req, code="SESSION_REQUIRED") if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        with Robot(transport=wire, heartbeat_interval=None):
            pass
        self.assertTrue(wire.closed)
        self.assertEqual(sum(r["op"] == "session.close" for r in wire.requests), 1)

    def test_body_error_survives_expired_session_close(self):
        def mutate(req, result):
            return response(req, code="SESSION_REQUIRED") if req["op"] == "session.close" else result
        wire = ScriptTransport(mutate=mutate)
        original = ValueError("original after lease expired")
        with self.assertRaises(ValueError) as raised:
            with Robot(transport=wire, heartbeat_interval=None):
                raise original
        self.assertIs(raised.exception, original)
        self.assertTrue(wire.closed)

    def test_heartbeat_failure_is_not_hidden_by_next_action(self):
        attempted = threading.Event()
        def mutate(req, result):
            if req["op"] == "session.heartbeat":
                attempted.set()
                return response(req, code="SESSION_REQUIRED")
            return result
        wire = ScriptTransport(mutate=mutate)
        robot = Robot(transport=wire, heartbeat_interval=0.01, timeout=0.1)
        self.addCleanup(robot.close)
        self.assertTrue(attempted.wait(0.5))
        self.assertTrue(robot._stop.wait(0.5))
        with self.assertRaises(ConnectionLostError): robot.gpio.write(12, 1)
        self.assertFalse(any(r["op"] == "gpio.write" for r in wire.requests))

    def test_heartbeat_and_commands_are_serialized(self):
        heartbeat_seen = threading.Event()
        def observe(req, result):
            if req["op"] == "session.heartbeat": heartbeat_seen.set()
            return result
        wire = ScriptTransport(chunk_size=1, mutate=observe)
        robot = Robot(transport=wire, heartbeat_interval=0.002, timeout=0.2)
        self.addCleanup(robot.close)
        self.assertTrue(heartbeat_seen.wait(0.5))
        for _ in range(15): self.assertEqual(robot.gpio.read(1), 1)
        self.assertTrue(any(r["op"] == "session.heartbeat" for r in wire.requests))

    def test_unsafe_local_numeric_values_rejected_before_io(self):
        robot, wire = self.connect()
        before = len(wire.requests)
        calls = [lambda: robot.gpio.write(True, 1), lambda: robot.gpio.write(12, True),
                 lambda: robot.servo.move("head", 60.0), lambda: robot.pwm.write(12, -1),
                 lambda: robot.adc.read("1"), lambda: robot.config.apply({}, expected_revision=True)]
        for call in calls:
            with self.assertRaises(ValueError): call()
        self.assertEqual(len(wire.requests), before)

    def test_servo_configuration_preserves_others_and_stays_in_maintenance(self):
        robot, wire = self.connect()
        robot.servo.configure("arm", 12)
        robot.servo.configure("head", 13, min_angle=40, max_angle=140)
        robot.servo.configure("head", 14)
        self.assertTrue(wire.maintenance)
        servos = wire.config["servos"]
        self.assertEqual([(s["name"], s["pin"]) for s in servos], [("arm", 12), ("head", 14)])
        self.assertFalse(any(r["op"] == "servo.move" for r in wire.requests))
        robot.maintenance.exit()
        self.assertFalse(wire.maintenance)

    def test_invalid_servo_calibration_does_not_enter_maintenance(self):
        robot, wire = self.connect()
        before = len(wire.requests)
        for kwargs in ({"min_angle": 100, "max_angle": 50}, {"min_pulse_us": 2500, "max_pulse_us": 500}, {"min_angle": True}):
            with self.assertRaises(ValueError): robot.servo.configure("head", 12, **kwargs)
        self.assertEqual(len(wire.requests), before)

    def test_unimplemented_modules_explicitly_rejected(self):
        robot, _ = self.connect()
        for module in (robot.display, robot.audio, robot.web):
            with self.assertRaises(UnsupportedCapability): module.anything()

    def test_builtin_led_set_off_payload_and_unverified_state(self):
        def mutate(req, result):
            if req["op"] == "led.set":
                return response(req, {**req["args"], "state": "commanded", "physical_verified": False})
            if req["op"] == "led.off":
                return response(req, {"red": 0, "green": 0, "blue": 0, "state": "commanded", "physical_verified": False})
            return result
        robot, wire = self.connect(ScriptTransport(mutate=mutate))
        color = robot.led.set(red=8, green=0, blue=0)
        self.assertEqual(color["red"], 8)
        self.assertIs(color["physical_verified"], False)
        self.assertEqual(color["state"], "commanded")
        off = robot.led.off()
        self.assertEqual((off["red"], off["green"], off["blue"]), (0, 0, 0))
        led_requests = [r for r in wire.requests if r["op"].startswith("led.")]
        self.assertEqual([r["op"] for r in led_requests], ["led.set", "led.off"])
        self.assertEqual(led_requests[0]["args"], {"red": 8, "green": 0, "blue": 0})
        self.assertEqual(led_requests[1]["args"], {})

    def test_builtin_led_invalid_values_rejected_before_io(self):
        robot, wire = self.connect()
        before = len(wire.requests)
        colors = ({"red": True}, {"green": 1.0}, {"blue": "8"}, {"red": -1}, {"green": 33})
        for color in colors:
            with self.assertRaises(ValueError): robot.led.set(**color)
        self.assertEqual(len(wire.requests), before)

    def test_cloud_mode_not_silently_connected(self):
        with self.assertRaises(UnsupportedCapability): Robot(connection="cloud")

    def test_auto_no_candidate_never_opens_serial(self):
        with patch("serial.tools.list_ports.comports", return_value=[]), patch("serial.Serial") as serial:
            with self.assertRaises(RobotError): SerialTransport("AUTO")
            serial.assert_not_called()

    def test_auto_multiple_candidates_never_guesses(self):
        from types import SimpleNamespace
        ports = [SimpleNamespace(device="COM1", vid=1), SimpleNamespace(device="COM2", vid=2)]
        with patch("serial.tools.list_ports.comports", return_value=ports), patch("serial.Serial") as serial:
            with self.assertRaisesRegex(RobotError, "COM1.*COM2"): SerialTransport("AUTO")
            serial.assert_not_called()

    def test_read_failure_sets_fault_and_never_resends_action(self):
        robot, wire = self.connect()
        wire.read = lambda *args: (_ for _ in ()).throw(OSError("disconnected"))
        with self.assertRaises(ConnectionLostError): robot.servo.move("head", 60)
        with self.assertRaises(ConnectionLostError): robot.servo.move("head", 60)
        self.assertEqual(sum(r["op"] == "servo.move" for r in wire.requests), 1)

    def test_device_restart_is_detected_by_identity_query(self):
        robot, wire = self.connect()
        def mutate(req, result):
            if req["op"] == "device.info": result["data"]["boot_id"] = "boot-b"
            return result
        wire.mutate = mutate
        with self.assertRaises(ConnectionLostError): robot.get_info()


if __name__ == "__main__": unittest.main()
