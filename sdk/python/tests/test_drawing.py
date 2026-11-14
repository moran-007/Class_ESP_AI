"""Bitmap/Turtle transport checks; these tests never open a physical port."""
import base64
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import contextmanager
import runpy
import sys

from ai_robot import Robot, UnsupportedCapability, DeviceError
from test_sdk import ScriptTransport, response
from test_native_integration import ProcessTransport

HAS_PIL = importlib.util.find_spec("PIL") is not None


class DrawingTests(unittest.TestCase):
    def connect(self, supported=True, width=160, height=128):
        def mutate(request, result):
            if request["op"] == "device.info":
                result["data"]["capabilities"].update(display=True, display_bitmap=supported)
            if request["op"] == "device.status":
                result["data"]["display"] = {"active": True, "width": width, "height": height}
            return result
        wire = ScriptTransport(mutate=mutate)
        robot = Robot(transport=wire, heartbeat_interval=None)
        self.addCleanup(robot.close)
        return robot, wire

    def test_bitmap_uses_bounded_rgb565_big_endian_bytes(self):
        robot, wire = self.connect()
        pixels = bytes((0xf8, 0, 0x07, 0xe0, 0, 0x1f))
        robot.display.bitmap(2, 3, 3, 1, pixels)
        frame = wire.requests[-1]
        self.assertEqual(frame["op"], "display.bitmap")
        self.assertEqual(frame["args"], {"x": 2, "y": 3, "width": 3, "height": 1,
                                          "data": base64.b64encode(pixels).decode()})

    def test_bad_bitmap_values_are_rejected_before_action(self):
        robot, wire = self.connect()
        for args in ((0, 0, 0, 1, b""), (0, 0, True, 1, b"\0\0"),
                     (0, 0, 385, 1, b"\0" * 770), (0, 0, 2, 1, b"\0\0"),
                     (159, 0, 2, 1, b"\0" * 4), (0, 128, 1, 1, b"\0\0")):
            with self.subTest(args=args[:4]), self.assertRaises(ValueError):
                robot.display.bitmap(*args)
        self.assertFalse(any(r["op"] == "display.bitmap" for r in wire.requests))

    def test_old_firmware_rejected_before_any_drawing_request(self):
        robot, wire = self.connect(supported=False)
        before = len(wire.requests)
        with self.assertRaises(UnsupportedCapability): robot.display.bitmap(0, 0, 1, 1, b"\0\0")
        self.assertEqual(len(wire.requests), before)

    @unittest.skipUnless(HAS_PIL, "安装SDK drawing可选依赖后执行")
    def test_image_contain_cover_and_strip_pixel_bounds(self):
        from PIL import Image
        robot, wire = self.connect(width=4, height=4)
        source = Image.new("RGB", (4, 2), "red")
        result = robot.display.image(source)
        self.assertEqual((result["width"], result["height"], result["chunks"]), (4, 4, 1))
        frame = next(r for r in wire.requests if r["op"] == "display.bitmap")
        raw = base64.b64decode(frame["args"]["data"])
        self.assertEqual(raw[:8], b"\0" * 8)
        self.assertEqual(raw[8:24], b"\xf8\0" * 8)
        wire.requests.clear()
        robot.display.image(source, fit="cover")
        raw = base64.b64decode(wire.requests[-1]["args"]["data"])
        self.assertEqual(raw, b"\xf8\0" * 16)
        robot, wire = self.connect(width=320, height=240)
        result = robot.display.image(source)
        chunks = [r for r in wire.requests if r["op"] == "display.bitmap"]
        self.assertEqual(result["chunks"], 240)
        self.assertTrue(all(r["args"]["width"] * r["args"]["height"] <= 384 for r in chunks))

    @unittest.skipUnless(HAS_PIL, "安装SDK drawing可选依赖后执行")
    def test_image_failure_is_not_retried_or_persisted(self):
        from PIL import Image
        robot, wire = self.connect(width=320, height=3)
        original = wire.mutate
        def failure(request, result):
            result = original(request, result)
            if request["op"] == "display.bitmap":
                return response(request, code="HARDWARE_ERROR", message="injected bitmap failure")
            return result
        wire.mutate = failure
        with self.assertRaises(DeviceError): robot.display.image(Image.new("RGB", (2, 2), "blue"))
        self.assertEqual(sum(r["op"] == "display.bitmap" for r in wire.requests), 1)
        self.assertFalse(any("pages.upload" in r["op"] for r in wire.requests))

    @unittest.skipUnless(HAS_PIL, "安装SDK drawing可选依赖后执行")
    def test_bad_image_options_and_large_sources_do_not_write_pixels(self):
        from PIL import Image
        robot, wire = self.connect()
        source = Image.new("RGB", (1, 1))
        with self.assertRaises(ValueError): robot.display.image(source, fit="stretch")
        with self.assertRaises(ValueError): robot.display.image(source, background=True)
        source._size = (4001, 4000)
        with self.assertRaises(ValueError): robot.display.image(source)
        self.assertFalse(any(r["op"] == "display.bitmap" for r in wire.requests))

    @unittest.skipUnless(HAS_PIL, "安装SDK drawing可选依赖后执行")
    def test_windows_capture_targets_only_inner_canvas_hwnd(self):
        from PIL import Image
        from ai_robot.drawing import capture_turtle
        canvas = SimpleNamespace(update_idletasks=lambda: None, winfo_toplevel=lambda: SimpleNamespace(state=lambda: "normal"),
            winfo_exists=lambda: True, winfo_ismapped=lambda: True, winfo_viewable=lambda: True,
            winfo_width=lambda: 100, winfo_height=lambda: 80, winfo_id=lambda: 1234)
        screen = SimpleNamespace(getcanvas=lambda: SimpleNamespace(_canvas=canvas), update=lambda: None)
        with patch("ai_robot.drawing.sys.platform", "win32"), patch("PIL.ImageGrab.grab", return_value=Image.new("RGB", (100, 80))) as grab:
            result = capture_turtle(screen)
            self.assertEqual(result.size, (100, 80))
            grab.assert_called_once_with(window=1234)
        canvas.winfo_ismapped = lambda: False
        with patch("PIL.ImageGrab.grab") as grab, self.assertRaises(ValueError):
            capture_turtle(screen)
        grab.assert_not_called()

    def test_send_turtle_closes_capture_even_if_transfer_fails(self):
        from ai_robot.drawing import send_turtle
        closed = []
        image = SimpleNamespace(close=lambda: closed.append(True))
        def fail(*args, **kwargs): raise RuntimeError("send failed")
        robot = SimpleNamespace(display=SimpleNamespace(image=fail))
        with patch("ai_robot.drawing.capture_turtle", return_value=image), self.assertRaisesRegex(RuntimeError, "send failed"):
            send_turtle(robot, object())
        self.assertEqual(closed, [True])


@unittest.skipUnless(os.environ.get("AI_MAKER_NATIVE"), "AI_MAKER_NATIVE未设置")
class DrawingNativeTests(unittest.TestCase):
    def test_bitmap_and_full_image_stream_real_core(self):
        wire = ProcessTransport(os.environ["AI_MAKER_NATIVE"])
        self.addCleanup(wire.close)
        with Robot(transport=wire, heartbeat_interval=None) as robot:
            robot.display.configure("st7735s_128x160", backlight=16)
            robot.maintenance.exit()
            robot.display.begin()
            result = robot.display.bitmap(0, 0, 2, 1, b"\xf8\0\x07\xe0")
            self.assertEqual(result["state"], "commanded")
            if HAS_PIL:
                from PIL import Image
                result = robot.display.image(Image.new("RGB", (8, 4), "blue"))
                self.assertEqual((result["width"], result["height"]), (160, 128))
            self.assertFalse(robot.pages.info()["saved"], "image stream must not persist as an8KiBpagepackage")


class TurtleHelperTests(unittest.TestCase):
    def test_explicit_send_captures_first_and_holds_session_until_close(self):
        events = []
        class Widget:
            def __init__(self, *args, **kwargs): self.options = kwargs
            def pack(self, **kwargs): pass
            def configure(self, **kwargs): self.options.update(kwargs)
        class Variable:
            def __init__(self, value): self.value = value
            def set(self, value): self.value = value
        fake_tk = SimpleNamespace(Frame=Widget, Button=Widget, Label=Widget, StringVar=Variable,
                                  messagebox=SimpleNamespace(showerror=lambda *a, **k: events.append("error")))
        root = SimpleNamespace(bind=lambda *a, **k: None, protocol=lambda *a: None)
        screen = SimpleNamespace(getcanvas=lambda: SimpleNamespace(winfo_toplevel=lambda: root),
                                 bye=lambda: events.append("bye"))
        def capture(screen):
            events.append("capture")
            return SimpleNamespace(close=lambda: events.append("image_closed"))
        def send(image, **options):
            events.append("send")
            return {"width": 160, "height": 128}
        @contextmanager
        def connect():
            events.append("connect")
            try: yield SimpleNamespace(display=SimpleNamespace(image=send))
            finally: events.append("disconnect")
        quick = Path(__file__).resolve().parents[3] / "tests/quick"
        previous = sys.path.copy()
        self.addCleanup(lambda: setattr(sys, "path", previous))
        sys.path.insert(0, str(quick))
        with patch("ai_robot.client.SerialTransport") as serial:
            helper = runpy.run_path(str(quick / "_turtle.py"))
            serial.assert_not_called()
        cls = helper["_Sender"]
        with patch.dict(sys.modules, {"tkinter": fake_tk}), patch.dict(cls.send.__globals__, capture_turtle=capture, connect_screen=connect):
            sender = cls(screen)
            self.assertEqual(events, [], "creating controls must not connect")
            sender.send()
            self.assertEqual(events[:3], ["capture", "connect", "send"])
            self.assertNotIn("disconnect", events)
            sender.send()
            self.assertEqual(events.count("connect"), 1)
            sender.close()
            sender.close()
        self.assertEqual(events.count("disconnect"), 1)
        self.assertEqual(events[-1], "bye")


if __name__ == "__main__":
    unittest.main()
