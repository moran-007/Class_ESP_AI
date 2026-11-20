from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from ai_robot import Robot, UnsupportedCapability
from test_sdk import ScriptTransport


def wifi_response(request, reply):
    if request["op"] == "device.info":
        reply["data"]["capabilities"]["wifi_provisioning"] = True
    if request["op"].startswith("wifi."):
        reply["data"] = {"state": "connected", "provisioning": "saved", "ssid": "创客教室",
                         "ip": "192.0.2.4", "saved": True, "error": ""}
    return reply


class WifiTests(unittest.TestCase):
    def test_setwifi_reports_wait_and_timeout_without_credentials(self):
        def respond(request, reply):
            reply = wifi_response(request, reply)
            if request["op"] == "wifi.connect":
                reply["data"].update(state="connecting", provisioning="connecting", ip="", saved=True)
            if request["op"] == "wifi.status":
                reply["data"].update(state="disconnected", provisioning="failed", ip="", saved=True,
                                     error="connect_timeout")
            return reply

        output = StringIO()
        with Robot(transport=ScriptTransport(respond), heartbeat_interval=None) as robot:
            with patch("ai_robot.wifi.sleep"), redirect_stdout(output):
                status = robot.setwifi("创客教室", "synthetic-password")
            self.assertEqual(status["error"], "connect_timeout")
            self.assertEqual(robot.listwifi(), [])
        self.assertIn("发送配网请求", output.getvalue())
        self.assertIn("等待获得 IP", output.getvalue())
        self.assertIn("连接超时", output.getvalue())
        self.assertIn("保留原有", output.getvalue())
        self.assertNotIn("synthetic-password", output.getvalue())

    def test_listwifi_and_clearwifi_report_board_state(self):
        saved = True

        def respond(request, reply):
            nonlocal saved
            reply = wifi_response(request, reply)
            if request["op"] == "wifi.clear":
                saved = False
            if request["op"].startswith("wifi.") and not saved:
                reply["data"].update(state="unconfigured", ssid="", ip="", saved=False)
            return reply

        wire = ScriptTransport(respond)
        with Robot(transport=wire, read_only=True) as robot:
            self.assertEqual(robot.listwifi(), [{"ssid": "创客教室", "ip": "192.0.2.4"}])
            with self.assertRaises(UnsupportedCapability):
                robot.clearwifi()
        self.assertEqual([item["op"] for item in wire.requests], ["device.info", "wifi.status"])

        with Robot(transport=ScriptTransport(respond), heartbeat_interval=None) as robot:
            self.assertFalse(robot.clearwifi()["saved"])
            self.assertEqual(robot.listwifi(), [])
            robot.led.off()

    def test_setwifi_waits_for_final_board_result_using_same_session(self):
        def respond(request, reply):
            reply = wifi_response(request, reply)
            if request["op"] == "wifi.connect":
                reply["data"].update(state="connecting", provisioning="connecting", ip="", saved=False)
            return reply

        wire = ScriptTransport(respond)
        output = StringIO()
        with Robot(transport=wire, heartbeat_interval=None) as robot, patch("ai_robot.wifi.sleep"), redirect_stdout(output):
            status = robot.setwifi("创客教室", "example-only")
        self.assertEqual((status["provisioning"], status["ip"]), ("saved", "192.0.2.4"))
        self.assertEqual([req["op"] for req in wire.requests],
                         ["device.info", "session.open", "wifi.connect", "wifi.status", "session.close"])
        self.assertEqual(len({req["session_id"] for req in wire.requests}), 1)
        self.assertIn("配网成功，已保存", output.getvalue())
        self.assertIn("192.0.2.4", output.getvalue())
        self.assertNotIn("example-only", output.getvalue())

    def test_setwifi_progress_can_be_disabled(self):
        output = StringIO()
        with Robot(transport=ScriptTransport(wifi_response), heartbeat_interval=None) as robot, redirect_stdout(output):
            self.assertEqual(robot.setwifi("创客教室", "example-only", progress=False)["ip"], "192.0.2.4")
        self.assertEqual(output.getvalue(), "")

    def test_chinese_name_preserved_and_invalid_inputs_blocked(self):
        wire = ScriptTransport(wifi_response)
        with Robot(transport=wire, heartbeat_interval=None) as robot:
            for ssid, password in (("教" * 11, "abcdefgh"), ("有\u0081", "abcdefgh"), ("名字", "short")):
                with self.assertRaises(ValueError):
                    robot.wifi.connect(ssid, password)
            self.assertEqual(len(wire.requests), 2)
            result = robot.wifi.connect("创客教室", "example-only")
            self.assertEqual(wire.requests[-1]["args"]["ssid"], "创客教室")
            self.assertEqual(result["ip"], "192.0.2.4")
            self.assertNotIn("password", result)

    def test_read_only_query_does_not_take_control(self):
        wire = ScriptTransport(wifi_response)
        with Robot(transport=wire, read_only=True) as robot:
            self.assertEqual(robot.wifi.status()["state"], "connected")
            with self.assertRaises(UnsupportedCapability):
                robot.wifi.clear()
            with self.assertRaises(UnsupportedCapability):
                robot.led.off()
        self.assertEqual([request["op"] for request in wire.requests], ["device.info", "wifi.status"])
        self.assertTrue(wire.closed)

    def test_old_firmware_rejects_credentials_before_sending(self):
        wire = ScriptTransport()
        with Robot(transport=wire, heartbeat_interval=None) as robot:
            with self.assertRaises(UnsupportedCapability):
                robot.wifi.connect("创客教室", "example-only")
        self.assertNotIn("wifi.connect", [request["op"] for request in wire.requests])
