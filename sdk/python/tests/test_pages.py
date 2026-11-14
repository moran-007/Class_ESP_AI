"""Page-package validation and bounded USB transfer; never opens physical USB."""
import base64
import copy
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib

from ai_robot import Robot, DeviceError, ProtocolError, UnsupportedCapability
from test_sdk import ScriptTransport, response


def project():
    return {"schema_version": 1, "width": 160, "height": 128, "pages": [
        {"id": "home", "background": 0, "widgets": [
            {"id": "title", "type": "text", "x": 8, "y": 8, "text": "你好", "color": 65535},
            {"id": "bar", "type": "rect", "x": 8, "y": 40, "width": 100, "height": 20, "color": 2016, "filled": True},
        ]}], "images": []}


class PageValidationTests(unittest.TestCase):
    def test_valid_project_is_deep_copy(self):
        from ai_robot.pages import validate_project
        original = project()
        result = validate_project(original)
        self.assertEqual(result, original)
        result["pages"][0]["widgets"][0]["text"] = "changed"
        self.assertEqual(original["pages"][0]["widgets"][0]["text"], "你好")

    def test_invalid_types_geometry_controls_and_unknown_fields(self):
        from ai_robot.pages import validate_project
        cases = []
        for value in (True, 1.5, -1, 321):
            cases.append(dict(project(), width=value))
        cases.append(dict(project(), unknown=1))
        for text in ("", "\0", "\x85", "x" * 193, "\ud800"):
            item = project(); item["pages"][0]["widgets"][0]["text"] = text; cases.append(item)
        item = project(); item["pages"][0]["widgets"][1]["width"] = 161; cases.append(item)
        item = project(); item["pages"][0]["widgets"][1]["filled"] = 1; cases.append(item)
        item = project(); item["pages"].append(copy.deepcopy(item["pages"][0])); cases.append(item)
        for item in cases:
            with self.subTest(item=repr(item)[:80]), self.assertRaises(ValueError):
                validate_project(item)

    def test_rgb565_image_size_reference_and_canonical_base64(self):
        from ai_robot.pages import validate_project
        item = project()
        item["images"] = [{"id": "face", "width": 1, "height": 1, "data": base64.b64encode(bytes((0xf8, 0))).decode()}]
        item["pages"][0]["widgets"].append({"id": "icon", "type": "image", "x": 0, "y": 0, "asset": "face"})
        self.assertEqual(validate_project(item), item)
        for data in ("+A==", "+AAA\n", "+AAB", "????", ""):
            bad = copy.deepcopy(item); bad["images"][0]["data"] = data
            with self.assertRaises(ValueError): validate_project(bad)
        bad = copy.deepcopy(item); bad["pages"][0]["widgets"][-1]["asset"] = "missing"
        with self.assertRaises(ValueError): validate_project(bad)

    def test_formatted_json_file_uses_compact_package_limit(self):
        from ai_robot.pages import load_project
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            formatted = json.dumps(project(), ensure_ascii=False, indent=120)
            self.assertGreater(len(formatted.encode("utf-8")), 8192)
            self.assertLess(len(formatted.encode("utf-8")), 65536)
            path.write_text(formatted, encoding="utf-8")
            self.assertEqual(load_project(path), project())
            path.write_bytes(b" " * 65537)
            with self.assertRaises(ValueError): load_project(path)
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(ValueError): load_project(path)


class PageWire(ScriptTransport):
    def __init__(self):
        super().__init__(mutate=self.handle)
        self.saved = b""
        self.staging = bytearray()
        self.expected = 0
        self.crc = ""
        self.fail_chunk = False
        self.bad_next_offset = False
        self.bad_download = False

    def info(self):
        return {"saved": bool(self.saved), "bytes": len(self.saved), "crc32": f"{zlib.crc32(self.saved):08x}",
                "width": 160, "height": 128, "page_ids": ["home"], "startup_enabled": False,
                "default_page": "home", "shown_page": "", "standalone_active": False}

    def handle(self, req, result):
        op, args = req["op"], req["args"]
        if op == "device.info":
            result["data"]["capabilities"] = {"pages": True, "display": True}
        elif op == "pages.upload.begin":
            self.staging.clear(); self.expected = args["bytes"]; self.crc = args["crc32"]
            return response(req, {"upload_id": "upload1"})
        elif op == "pages.upload.chunk":
            if self.fail_chunk:
                return response(req, code="INVALID_ARGUMENT", message="injected chunk rejection")
            assert args["offset"] == len(self.staging)
            self.staging.extend(base64.b64decode(args["data"], validate=True))
            return response(req, {"next_offset": len(self.staging) + int(self.bad_next_offset)})
        elif op == "pages.upload.commit":
            assert len(self.staging) == self.expected and f"{zlib.crc32(self.staging):08x}" == self.crc
            self.saved = bytes(self.staging)
            return response(req, self.info())
        elif op == "pages.upload.abort":
            return response(req, code="HARDWARE_ERROR", message="abort failed too")
        elif op == "pages.info":
            return response(req, self.info())
        elif op == "pages.read":
            offset = args["offset"]
            data = self.saved[offset:offset + args["max_bytes"]]
            return response(req, {"offset": offset + int(self.bad_download), "total_bytes": len(self.saved),
                                  "data": base64.b64encode(data).decode(), "eof": offset + len(data) == len(self.saved)})
        return result


class PagesSDKTests(unittest.TestCase):
    def connect(self, wire=None):
        wire = wire or PageWire()
        robot = Robot(transport=wire, heartbeat_interval=None, timeout=.1)
        self.addCleanup(robot.close)
        return robot, wire

    def test_upload_download_chunk_bounds_and_data(self):
        robot, wire = self.connect()
        item = project()
        item["images"] = [{"id": "icon", "width": 32, "height": 32,
                           "data": base64.b64encode(b"\xf8\x00" * 1024).decode()}]
        robot.pages.upload(item)
        self.assertEqual(robot.pages.download(), item)
        chunks = [r for r in wire.requests if r["op"] == "pages.upload.chunk"]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(1 <= len(base64.b64decode(r["args"]["data"])) <= 768 for r in chunks))
        self.assertEqual(wire.requests[2]["op"], "pages.upload.begin")
        self.assertFalse(any(r["op"] == "pages.startup" for r in wire.requests))

    def test_upload_failure_aborts_once_and_keeps_original_exception(self):
        robot, wire = self.connect()
        wire.fail_chunk = True
        with self.assertRaisesRegex(DeviceError, "injected chunk rejection") as caught:
            robot.pages.upload(project())
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENT")
        self.assertEqual(sum(r["op"] == "pages.upload.chunk" for r in wire.requests), 1)
        self.assertEqual(sum(r["op"] == "pages.upload.abort" for r in wire.requests), 1)
        self.assertFalse(any(r["op"] == "pages.upload.commit" for r in wire.requests))

    def test_upload_offset_and_download_metadata_are_verified(self):
        robot, wire = self.connect()
        wire.bad_next_offset = True
        with self.assertRaises(ProtocolError): robot.pages.upload(project())
        wire.bad_next_offset = False
        robot.pages.upload(project())
        wire.bad_download = True
        with self.assertRaises(ProtocolError): robot.pages.download()

    def test_old_firmware_and_invalid_projects_never_upload(self):
        robot, wire = self.connect(ScriptTransport())
        count = len(wire.requests)
        with self.assertRaises(UnsupportedCapability): robot.pages.upload(project())
        self.assertEqual(len(wire.requests), count)
        robot, wire = self.connect()
        count = len(wire.requests)
        with self.assertRaises(ValueError): robot.pages.upload(dict(project(), width=True))
        self.assertEqual(len(wire.requests), count)

    def test_runtime_and_startup_payloads_and_clear_stays_maintenance(self):
        robot, wire = self.connect()
        robot.pages.show("home")
        robot.pages.text("title", "更新\n就绪")
        robot.pages.startup("home", enabled=True)
        robot.pages.startup(enabled=False)
        for invalid in ("bad id", "x\0", "a" * 25):
            with self.assertRaises(ValueError): robot.pages.show(invalid)
        with self.assertRaises(ValueError): robot.pages.startup(enabled=1)
        robot.pages.clear()
        self.assertTrue(wire.maintenance)
        operations = [(r["op"], r["args"]) for r in wire.requests]
        self.assertIn(("pages.startup", {"enabled": True, "id": "home"}), operations)
        self.assertIn(("pages.startup", {"enabled": False}), operations)
        self.assertEqual(operations[-2][0], "maintenance.enter")
        self.assertEqual(operations[-1][0], "pages.clear")


class StateProcessTransport:
    """Native executable with optional persisted test state, never physical USB."""
    def __init__(self, executable, state_path):
        self.process = subprocess.Popen([str(executable), str(state_path)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=None, bufsize=0)
        self._queue = queue.Queue(); self._pending = bytearray(); self._closed = False
        self.requests = []
        self.closed_status = None
        self._reader = threading.Thread(target=self._pump, daemon=True); self._reader.start()

    def _pump(self):
        try:
            while chunk := os.read(self.process.stdout.fileno(), 512): self._queue.put(chunk)
        finally: self._queue.put(None)

    def write(self, data):
        self.requests.append(json.loads(data))
        if self.process.stdin.write(data) != len(data): raise OSError("Incomplete native request")
        self.process.stdin.flush()

    def read(self, size, timeout):
        if not self._pending:
            try: chunk = self._queue.get(timeout=timeout)
            except queue.Empty: return b""
            if chunk is None: raise OSError("native stdout closed")
            self._pending.extend(chunk)
        result = bytes(self._pending[:size]); del self._pending[:size]; return result

    def close(self):
        if self._closed: return
        if self.process.poll() is None:
            try: self.closed_status = self.query_status()
            except (OSError, RuntimeError): pass
        self._closed = True; self.process.stdin.close()
        try: self.process.wait(timeout=1)
        except subprocess.TimeoutExpired: self.process.terminate(); self.process.wait(timeout=2)
        self._reader.join(1); self.process.stdout.close()

    def query_status(self):
        identity = f"native-probe-{len(self.requests)}"
        self.write((json.dumps({"kind": "request", "protocol_version": 1,
                               "request_id": identity, "op": "device.status", "args": {}}) + "\n").encode())
        pending = bytearray(); deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pending.extend(self.read(1024, .1))
            while b"\n" in pending:
                line, _, tail = pending.partition(b"\n"); pending = bytearray(tail)
                frame = json.loads(line)
                if frame.get("request_id") == identity: return frame["data"]
        raise RuntimeError("Native public status query timed out")


@unittest.skipUnless(os.environ.get("AI_MAKER_NATIVE"), "AI_MAKER_NATIVE 未设置")
class PagesNativeTests(unittest.TestCase):
    def test_saved_package_restart_default_takeover_and_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "page.state.json"
            first = StateProcessTransport(os.environ["AI_MAKER_NATIVE"], state_path)
            with Robot(transport=first, heartbeat_interval=None) as robot:
                robot.display.configure("st7735s_128x160", backlight=16)
                robot.maintenance.exit()
                item = project()
                item["images"] = [{"id": "stamp", "width": 16, "height": 16,
                                   "data": base64.b64encode(b"\xf8\x00" * 256).decode()}]
                item["pages"][0]["widgets"].append({"id": "icon", "type": "image", "x": 128, "y": 8, "asset": "stamp"})
                robot.pages.upload(item)
                self.assertEqual(robot.pages.download(), item)
                robot.pages.show("home")
                robot.pages.text("title", "已更新")
                robot.pages.startup("home")
            self.assertTrue(first.closed_status["standalone_active"], "normal close must restore default page")
            self.assertGreater(sum(r["op"] == "pages.upload.chunk" for r in first.requests), 1)
            second = StateProcessTransport(os.environ["AI_MAKER_NATIVE"], state_path)
            self.assertTrue(second.query_status()["standalone_active"], "startup must render before a control session opens")
            with Robot(transport=second, heartbeat_interval=None) as robot:
                self.assertEqual(robot.pages.download(), item)
                status = robot.get_status()
                self.assertTrue(status["pages"]["startup_enabled"])
                self.assertFalse(status["standalone_active"], "opening session must take over default page")
                robot.maintenance.enter()
            self.assertFalse(second.closed_status["standalone_active"], "maintenance must suppress default recovery")
            third = StateProcessTransport(os.environ["AI_MAKER_NATIVE"], state_path)
            self.assertFalse(third.query_status()["standalone_active"], "saved maintenance must suppress startup")
            with Robot(transport=third, heartbeat_interval=None) as robot:
                self.assertTrue(robot.get_status()["maintenance"])
                self.assertFalse(robot.get_status()["standalone_active"])
                robot.pages.clear()
                self.assertFalse(robot.pages.info()["saved"])


if __name__ == "__main__":
    unittest.main()
