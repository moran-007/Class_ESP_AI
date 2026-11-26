"""Synchronous USB protocol client with a single serialized heartbeat lease."""

from __future__ import annotations

import copy
import base64
import json
import math
import re
import threading
import time
import uuid
from typing import Any

from .errors import (
    ConnectionLostError, DeviceError, ProtocolError, RequestTimeout,
    RobotError, UnsupportedCapability,
)
from .transport import SerialTransport, Transport
from .pages import Pages
from .audio import Audio
from .program import Programs
from .wifi import Wifi
from .voice import RobotVoice

MAX_LINE = 4096
PROTOCOL_VERSION = 1
FAMILY = "ai-maker-s3"
READ_ONLY_OPS = frozenset({"device.info", "device.status", "pins.list", "config.get",
                           "program.info", "pages.info", "audio.info", "wifi.status"})


def _integer(value: int, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} 必须为 {minimum}～{maximum} 的整数")
    return value


def _name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", value):
        raise ValueError("设备名须以 ASCII 字母开头，仅含字母、数字、下划线，最长 24 字节")
    return value


class Robot:
    """Connect to one local teaching device.

    Opens the port, queries identity and normally acquires a control lease.
    With read_only=True it skips the lease and permits sessionless queries.
    Actions are never retried.
    Injected transports transfer their ownership to this instance.
    """

    def __init__(
        self, connection: str = "usb", port: str = "AUTO", *,
        baudrate: int = 115200, timeout: float = 2.0,
        transport: Transport | None = None, heartbeat_interval: float | None = 1.0,
        read_only: bool = False,
    ):
        if connection != "usb":
            raise UnsupportedCapability("Robot 当前只支持 USB 控制开发板；AI 服务请用 robot.ai.set()")
        if type(read_only) is not bool:
            raise ValueError("read_only 必须是布尔值")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout 必须为正的有限秒数")
        if heartbeat_interval is not None and (
            isinstance(heartbeat_interval, bool)
            or not isinstance(heartbeat_interval, (int, float))
            or not math.isfinite(heartbeat_interval) or heartbeat_interval <= 0
        ):
            raise ValueError("heartbeat_interval 必须为正的有限秒数或 None")
        self._timeout = float(timeout)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._closed = False
        self._closing = False
        self._fault: BaseException | None = None
        self._buffer = bytearray()
        self._discard_line = False
        self._counter = 0
        self._session = uuid.uuid4().hex
        self._session_open = False
        self._read_only = read_only
        self._thread: threading.Thread | None = None
        self._transport = transport if transport is not None else SerialTransport(port, baudrate, self._timeout)
        self.gpio = _GPIO(self)
        self.adc = _ADC(self)
        self.pwm = _PWM(self)
        self.digital = _Digital(self)
        self.analog = _Analog(self)
        self.servo = _Servo(self)
        self.led = _LED(self)
        self.config = _Config(self)
        self.maintenance = _Maintenance(self)
        self.display = _Display(self)
        self.pages = Pages(self)
        self.audio = Audio(self)
        self.program = Programs(self)
        self.wifi = Wifi(self)
        self.web = _Unavailable("student_web")
        self.ai = RobotVoice(self)
        try:
            self._info = self._request("device.info")
            if self._info.get("firmware_family") != FAMILY or type(self._info.get("protocol_version")) is not int or self._info["protocol_version"] != PROTOCOL_VERSION:
                raise ProtocolError("连接的设备不是兼容的 ai-maker-s3 协议 v1 固件")
            if not isinstance(self._info.get("boot_id"), str) or not self._info["boot_id"]:
                raise ProtocolError("设备未提供有效 boot_id")
            if self._read_only:
                return
            opened = self._request("session.open")
            if opened.get("session_id") != self._session or type(opened.get("lease_ms")) is not int or opened["lease_ms"] <= 0:
                raise ProtocolError("设备会话回执不合法")
            self._session_open = True
            if heartbeat_interval is not None:
                if heartbeat_interval * 1000 >= opened["lease_ms"]:
                    raise ValueError("心跳间隔必须小于设备会话租约")
                self._thread = threading.Thread(
                    target=self._heartbeat, args=(float(heartbeat_interval),),
                    name="ai-robot-heartbeat", daemon=True,
                )
                self._thread.start()
        except BaseException:
            # Constructor failure must not leave a serial descriptor or live
            # lease held; the firmware timeout remains the final fallback.
            try:
                if self._session_open:
                    self._request("session.close")
            except Exception:
                pass
            finally:
                self._closed = True
                self._transport.close()
            raise

    def _heartbeat(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                self._request("session.heartbeat")
            except Exception as exc:
                self._fault = exc
                self._stop.set()
                return

    def _lines(self, chunk: bytes):
        lines = []
        for byte in chunk:
            if byte == 10:
                if not self._discard_line:
                    lines.append(bytes(self._buffer).rstrip(b"\r"))
                self._buffer.clear()
                self._discard_line = False
            elif not self._discard_line:
                if len(self._buffer) >= MAX_LINE:
                    self._buffer.clear()
                    self._discard_line = True
                else:
                    self._buffer.append(byte)
        return lines

    def _request(self, op: str, args: dict[str, Any] | None = None, *, closing: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._closed or (self._closing and not closing):
                raise ConnectionLostError("连接已经关闭")
            if self._fault is not None and not closing:
                raise ConnectionLostError("心跳或通信已失败，请显式重新连接") from self._fault
            if self._read_only and op not in READ_ONLY_OPS:
                raise UnsupportedCapability("只读 USB 连接不能修改配置或控制输出")
            record_ticket = self.program._prepare_record_request(op, {} if args is None else args)
            self._counter += 1
            request_id = f"r{self._counter}"
            payload = {
                "kind": "request", "protocol_version": PROTOCOL_VERSION,
                "request_id": request_id, "session_id": self._session,
                "op": op, "args": {} if args is None else args,
            }
            # Saved flows are bounded in UTF8 bytes; escaping every Chinese
            # character would expand valid 3072-byte programs beyond JSONL.
            encoded = json.dumps(payload, ensure_ascii=op not in ("program.save", "wifi.connect"), separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_LINE:
                raise ValueError("请求超过协议单行 4096 字节限制")
            deadline = time.monotonic() + self._timeout
            try:
                self._transport.write(encoded + b"\n")
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RequestTimeout(f"请求 {request_id} ({op}) 超时；动作可能已执行，不会自动重发")
                    chunk = self._transport.read(256, remaining)
                    if not isinstance(chunk, bytes):
                        raise ProtocolError("Transport.read 必须返回 bytes")
                    if not chunk:
                        continue
                    for line in self._lines(chunk):
                        try:
                            response = json.loads(line.decode("utf-8"))
                        except (ValueError, UnicodeError):
                            continue  # ROM startup messages are not protocol frames.
                        if not isinstance(response, dict) or response.get("kind") != "response":
                            continue
                        if response.get("request_id") != request_id:
                            continue
                        if type(response.get("protocol_version")) is not int or response["protocol_version"] != PROTOCOL_VERSION:
                            raise ProtocolError("响应协议版本不兼容")
                        if type(response.get("ok")) is not bool or not isinstance(response.get("code"), str):
                            raise ProtocolError("响应缺少合法的 ok/code")
                        if not response["ok"]:
                            message = response.get("message", "设备拒绝请求")
                            if not isinstance(message, str):
                                raise ProtocolError("错误响应 message 必须是字符串")
                            raise DeviceError(response["code"], message, request_id)
                        if response["code"] != "OK" or not isinstance(response.get("data"), dict):
                            raise ProtocolError("成功响应必须包含 code=OK 和 data 对象")
                        self.program._commit_record_request(record_ticket)
                        return response["data"]
            except (DeviceError, RequestTimeout, ProtocolError) as exc:
                self.program._record_failure(exc)
                raise
            except Exception as exc:
                self.program._record_failure(exc)
                self._fault = exc
                raise ConnectionLostError("USB 通信失败，执行结果可能未知；不会自动重连或重发动作") from exc
            except BaseException as exc:
                self.program._record_failure(exc)
                raise

    def get_info(self) -> dict[str, Any]:
        info = self._request("device.info")
        if info.get("boot_id") != self._info.get("boot_id"):
            self._fault = ProtocolError("设备在会话中重启")
            raise ConnectionLostError("设备已重新启动，请重新连接")
        return info

    def get_status(self) -> dict[str, Any]:
        return self._request("device.status")

    def setwifi(self, name: str, password: str, *, progress: bool = True) -> dict[str, Any]:
        """Provision Wi-Fi, reporting progress to stdout unless disabled."""
        return self.wifi._connect_and_wait(name, password, progress=progress)

    def listwifi(self) -> list[dict[str, str]]:
        """Return the board's current Wi-Fi network and IPv4, or an empty list."""
        status = self.wifi.status()
        if status["state"] != "connected" or not status["ip"]:
            return []
        return [{"ssid": status["ssid"], "ip": status["ip"]}]

    def clearwifi(self) -> dict[str, Any]:
        """Forget the board's saved Wi-Fi credentials and close its Wi-Fi link."""
        return self.wifi.clear()

    def list_pins(self) -> list[dict[str, Any]]:
        if self._info.get('capabilities', {}).get('pin_pagination') is True:
            pins, seen, offset, expected_total = [], set(), 0, None
            while True:
                data = self._request('pins.list', {'offset': offset, 'limit': 12})
                page, total, next_offset = data.get('pins'), data.get('total'), data.get('next_offset')
                if type(data.get('offset')) is not int or data['offset'] != offset or type(total) is not int or not 0 <= total <= 49 or type(page) is not list or len(page) > 12:
                    raise ProtocolError('分页引脚回执的偏移、总数或列表无效')
                if expected_total is not None and total != expected_total:
                    raise ProtocolError('分页过程中引脚总数变化，停止而不重试')
                expected_total = total
                end = offset + len(page)
                if end > total or not page and end < total:
                    raise ProtocolError('分页引脚列表没有进展或超过总数')
                for item in page:
                    if type(item) is not dict or type(item.get('pin')) is not int or not 0 <= item['pin'] <= 48 or item['pin'] in seen:
                        raise ProtocolError('分页引脚回执包含无效或重复GPIO')
                    if any(type(item.get(key)) is not bool for key in ('digital_input','digital_output','analog_input','analog_output','pwm_output')):
                        raise ProtocolError('分页引脚数字/模拟/PWM能力字段无效')
                    seen.add(item['pin']); pins.append(item)
                if end == total:
                    if next_offset is not None:
                        raise ProtocolError('最后一页next_offset必须为null')
                    return pins
                if type(next_offset) is not int or next_offset != end:
                    raise ProtocolError('分页引脚next_offset不匹配，停止而不重试')
                offset = end
        data = self._request("pins.list")
        if not isinstance(data.get("pins"), list):
            raise ProtocolError("引脚列表响应不合法")
        return data["pins"]

    def stop(self) -> dict[str, Any]:
        return self._request("outputs.stop")

    def start(self) -> dict[str, Any]:
        """Finish set() and initialize requested screen/audio; never move servos.

        Call all display.set/servo.set operations before this method. Repeating
        start on active devices does not clear the screen or stop servo PWM.
        """
        status = self.get_status()
        if status.get('maintenance') is True:
            self.maintenance.exit()
        screen = status.get('display', {})
        result = None
        if self.display._start_requested and screen.get('configured') is True and screen.get('active') is not True:
            result = self.display.begin()
        audio_state = status.get('audio', {})
        audio_result = None
        if self.audio._start_requested and audio_state.get('configured') is True and audio_state.get('active') is not True:
            audio_result = self.audio.begin()
        return {'maintenance': False, 'display': result, 'audio': audio_result}

    def wait(self, seconds: float) -> None:
        """Wait while the background heartbeat runs; surface disconnects promptly."""
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("等待时间必须为不小于 0 的有限秒数")
        with self._lock:
            record_ticket = self.program._prepare_record_wait(seconds)
        error = None
        try:
            deadline = time.monotonic() + seconds
            while True:
                if self._closed or self._closing:
                    raise ConnectionLostError("连接已经关闭")
                if self._fault is not None:
                    raise ConnectionLostError("心跳或通信已失败，请显式重新连接") from self._fault
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._stop.wait(min(remaining, 0.1))
        except BaseException as exc:
            error = exc
            raise
        finally:
            with self._lock:
                self.program._finish_record_wait(record_ticket, error)

    def close(self) -> None:
        if self._closed:
            return
        self._closing = True
        self.ai._discard_recording()
        self.program.cancel()
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(self._timeout + 1.0)
        try:
            if self._session_open:
                try:
                    self._request("session.close", closing=True)
                except DeviceError as error:
                    # A structured rejection can mean output release failed.
                    # Keep that visible even though the host port must close.
                    # SESSION_REQUIRED means the lease already expired; this
                    # connection no longer owns outputs and cannot close it.
                    if error.code != "SESSION_REQUIRED":
                        raise
                except RobotError:
                    # Best effort only: a disconnected device must expire its
                    # lease without depending on this final request.
                    pass
        finally:
            self._session_open = False
            self._closed = True
            self._transport.close()

    def __enter__(self) -> Robot:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except Exception:
                # Cleanup failure must not replace the learner's original
                # exception (including Ctrl+C); normal exits surface failures.
                pass


class _GPIO:
    def __init__(self, robot: Robot): self._robot = robot

    def setup(self, pin: int, mode: str) -> dict[str, Any]:
        _integer(pin, "pin", 0, 48)
        if mode not in ("input", "input_pullup", "input_pulldown", "output", "pwm"):
            raise ValueError("mode 必须为 input/input_pullup/input_pulldown/output/pwm")
        return self._robot._request("gpio.setup", {"pin": pin, "mode": mode})

    def read(self, pin: int) -> int:
        return self._robot._request("gpio.read", {"pin": _integer(pin, "pin", 0, 48)})["value"]

    def write(self, pin: int, value: int) -> dict[str, Any]:
        return self._robot._request("gpio.write", {"pin": _integer(pin, "pin", 0, 48), "value": _integer(value, "value", 0, 1)})

    def release(self, pin: int) -> dict[str, Any]:
        return self._robot._request("gpio.release", {"pin": _integer(pin, "pin", 0, 48)})


class _ADC:
    def __init__(self, robot: Robot): self._robot = robot

    def read(self, pin: int) -> int:
        """Return raw 12-bit counts, not calibrated volts."""
        return self._robot._request("adc.read", {"pin": _integer(pin, "pin", 0, 48)})["raw"]


class _Digital:
    """Digital0/1 only. Use analog for ADC input and pwm for duty output."""
    def __init__(self, robot: Robot): self._robot = robot

    def set(self, pin: int, mode: str = 'input') -> dict[str, Any]:
        if mode not in ('input','input_pullup','input_pulldown','output'):
            raise ValueError('digital模式只接受input/input_pullup/input_pulldown/output；PWM请用robot.pwm.set')
        return self._robot.gpio.setup(pin, mode)

    def setup(self, pin: int, mode: str = 'input') -> dict[str, Any]:
        return self.set(pin, mode)

    def read(self, pin: int) -> int: return self._robot.gpio.read(pin)

    def write(self, pin: int, value: int) -> dict[str, Any]: return self._robot.gpio.write(pin, value)

    def release(self, pin: int) -> dict[str, Any]: return self._robot.gpio.release(pin)


class _Analog:
    """ADC raw12bit input. ESP32-S3 teaching profile has no true DAC output."""
    def __init__(self, robot: Robot): self._robot = robot

    def set(self, pin: int) -> dict[str, Any]:
        _integer(pin, 'ADC输入引脚', 1, 20)
        return self._robot.gpio.setup(pin, 'input')

    def setup(self, pin: int) -> dict[str, Any]: return self.set(pin)

    def read(self, pin: int) -> int: return self._robot.adc.read(pin)

    def write(self, pin: int, value) -> None:
        raise UnsupportedCapability('当前ESP32-S3教学板没有已接入的真正模拟电压/DAC输出；PWM是脉宽占空比，不等同于模拟电压。请用robot.pwm.set/write或外接DAC驱动')


class _PWM:
    def __init__(self, robot: Robot): self._robot = robot

    def set(self, pin: int) -> dict[str, Any]: return self._robot.gpio.setup(pin, 'pwm')

    def write(self, pin: int, duty: int) -> dict[str, Any]:
        return self._robot._request("pwm.write", {"pin": _integer(pin, "pin", 0, 48), "duty": _integer(duty, "duty", 0, 100)})


class _Config:
    def __init__(self, robot: Robot): self._robot = robot

    def get(self) -> dict[str, Any]:
        return self._robot._request("config.get")

    def apply(self, config: dict[str, Any], *, expected_revision: int) -> dict[str, Any]:
        if not isinstance(config, dict):
            raise ValueError("config 必须为对象")
        _integer(expected_revision, "expected_revision", 0, 2**31 - 1)
        return self._robot._request("config.apply", {"config": config, "expected_revision": expected_revision})


class _Maintenance:
    def __init__(self, robot: Robot): self._robot = robot

    def enter(self) -> dict[str, Any]: return self._robot._request("maintenance.enter")

    def exit(self) -> dict[str, Any]: return self._robot._request("maintenance.exit")


class _Servo:
    def __init__(self, robot: Robot): self._robot = robot

    def set(self, pin: int, *, name: str = 'test', min_angle: int = 30, max_angle: int = 150,
            min_pulse_us: int = 1000, max_pulse_us: int = 2000) -> dict[str, Any]:
        """Set a servo signal pin; default SG90 classroom preset, no movement.

        Equivalent to configure(name, pin, ...), with the classroom pulse preset.
        Set all devices, then robot.start(), then servo.move(name, angle).
        Match independent power, common ground and calibration to your servo.
        """
        return self.configure(name, pin, min_angle=min_angle, max_angle=max_angle,
                              min_pulse_us=min_pulse_us, max_pulse_us=max_pulse_us)

    def configure(
        self, name: str, pin: int, *, min_angle: int = 30, max_angle: int = 150,
        min_pulse_us: int = 500, max_pulse_us: int = 2500,
    ) -> dict[str, Any]:
        """Save a mapping and remain in maintenance. Never move automatically.

        Physical rewiring requires maintenance BEFORE power is disconnected.
        This convenience method is not a substitute for that safety sequence.
        """
        _name(name)
        _integer(pin, "pin", 0, 48)
        _integer(min_angle, "min_angle", 0, 180)
        _integer(max_angle, "max_angle", 0, 180)
        _integer(min_pulse_us, "min_pulse_us", 500, 2500)
        _integer(max_pulse_us, "max_pulse_us", 500, 2500)
        if min_angle >= max_angle or min_pulse_us >= max_pulse_us:
            raise ValueError("角度及脉宽上下限必须严格递增")
        self._robot.maintenance.enter()
        current = self._robot.config.get()
        config = copy.deepcopy(current["config"])
        item = {
            "name": name, "pin": pin, "min_angle": min_angle, "max_angle": max_angle,
            "min_pulse_us": min_pulse_us, "max_pulse_us": max_pulse_us,
        }
        servos = config["servos"]
        for index, existing in enumerate(servos):
            if existing["name"] == name:
                servos[index] = item
                break
        else:
            servos.append(item)
        return self._robot.config.apply(config, expected_revision=current["revision"])

    def move(self, device: str, angle: int) -> dict[str, Any]:
        return self._robot._request("servo.move", {"device": _name(device), "angle": _integer(angle, "angle", 0, 180)})

    def release(self, device: str) -> dict[str, Any]:
        return self._robot._request("servo.release", {"device": _name(device)})


class _LED:
    """Board RGB command values. No optical feedback is available."""

    def __init__(self, robot: Robot): self._robot = robot

    def color(self, name: str, brightness: int = 16) -> dict[str, Any]:
        """Set a named color using the same 0..32 per-channel limit as set()."""
        colors = {
            "red": (1, 0, 0), "green": (0, 1, 0), "blue": (0, 0, 1),
            "yellow": (1, 1, 0), "white": (1, 1, 1), "off": (0, 0, 0),
        }
        if not isinstance(name, str) or name not in colors:
            raise ValueError("颜色须为 red/green/blue/yellow/white/off")
        _integer(brightness, "brightness", 0, 32)
        red, green, blue = colors[name]
        return self.set(red=red * brightness, green=green * brightness, blue=blue * brightness)

    def set(self, *, red: int = 0, green: int = 0, blue: int = 0) -> dict[str, Any]:
        return self._robot._request("led.set", {
            "red": _integer(red, "red", 0, 32),
            "green": _integer(green, "green", 0, 32),
            "blue": _integer(blue, "blue", 0, 32),
        })

    def off(self) -> dict[str, Any]:
        return self._robot._request("led.off")


class _Display:
    """One configurable ST77xx SPI panel; replies are not optical feedback."""

    _PANELS = ("st7789_240x320", "st7789_240x240", "st7735s_128x160")
    _COLORS = {
        "black": 0x0000, "white": 0xFFFF, "red": 0xF800, "green": 0x07E0,
        "blue": 0x001F, "yellow": 0xFFE0, "cyan": 0x07FF, "magenta": 0xF81F,
    }

    _LABELS = {
        'sck':'sck', 'scl':'sck', 'clk':'sck', 'sclk':'sck',
        'mosi':'mosi', 'sda':'mosi', 'din':'mosi', 'sdi':'mosi',
        'cs':'cs', 'ss':'cs', 'dc':'dc', 'a0':'dc', 'rs':'dc',
        'rst':'rst', 'res':'rst', 'reset':'rst',
        'backlight':'backlight', 'blk':'backlight', 'bl':'backlight',
    }
    _PIN_HELP = 'SPI屏幕丝印：SCK/SCL/CLK→sck，MOSI/SDA/DIN→mosi，CS/SS→cs，DC/A0/RS→dc，RST/RES→rst，BLK/BL→backlight'

    def __init__(self, robot: Robot):
        self._robot = robot
        self._start_requested = False
        self._fps = None
        self._last_frame_at = None

    def set(self, sck=None, mosi=None, cs=None, dc=None, rst=None, backlight=None, *,
            panel: str = 'st7789_240x320', rotation: int = 1, invert=None, brightness=None,
            fps: int | None = None, **labels) -> dict[str, Any]:
        """Set SPI wiring, then call robot.start() after all devices are set.

        Positional order: SCK, MOSI, CS, DC, RST, BLK. GPIO numbers, not header
        positions. Named aliases (case-insensitive): SCL/CLK/SCLK -> SCK;
        SDA/DIN/SDI -> MOSI; SS -> CS; A0/RS -> DC; RES/RESET -> RST;
        BLK/BL -> backlight. VCC/GND are power, not configurable GPIO signals.

        fps=1..60 limits PC display.image() frame starts; None means no added
        limit. It does not set panel scan rate or guarantee transfer throughput.
        Existing configure() remains available with its original contract.
        """
        values = dict(sck=sck, mosi=mosi, cs=cs, dc=dc, rst=rst, backlight=backlight)
        seen = {key for key, value in values.items() if value is not None}
        for label, pin in labels.items():
            normalized = label.lower()
            if normalized in ('vcc','vdd','gnd','3v3','5v'):
                raise ValueError(f'{label}是供电脚，不能填IO；{self._PIN_HELP}')
            canonical = self._LABELS.get(normalized)
            if canonical is None:
                raise ValueError(f'未知屏幕丝印/参数{label}；{self._PIN_HELP}')
            if canonical in seen:
                raise ValueError(f'{label}与{canonical}重复，请每个信号只填写一次；{self._PIN_HELP}')
            seen.add(canonical)
            values[canonical] = pin
        if fps is not None:
            _integer(fps, 'fps（整屏图片发送上限）', 1, 60)
        defaults = dict(sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=-1)
        values = {k: defaults[k] if v is None else v for k, v in values.items()}
        result = self.configure(panel, **values, rotation=rotation, invert=invert, brightness=brightness)
        self._start_requested = True
        self._fps = fps
        self._last_frame_at = None
        return result

    def _check(self) -> None:
        if self._robot._info.get("capabilities", {}).get("display") is not True:
            raise UnsupportedCapability("该固件未声明屏幕能力，请安装支持 display 的教学固件 V0.3.0 或以上")

    def __getattr__(self, name: str):
        self._check()
        raise AttributeError(f"屏幕接口没有 {name} 方法")

    @classmethod
    def _color(cls, value) -> int:
        if isinstance(value, str):
            if value not in cls._COLORS:
                raise ValueError("颜色须为 black/white/red/green/blue/yellow/cyan/magenta")
            return cls._COLORS[value]
        if isinstance(value, tuple) and len(value) == 3:
            red, green, blue = (_integer(part, "RGB分量", 0, 255) for part in value)
            return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        return _integer(value, "RGB565颜色", 0, 65535)

    def configure(
        self, panel: str = "st7789_240x320", *, sck: int = 4, mosi: int = 5,
        cs: int = 15, dc: int = 7, rst: int = 6, backlight: int = -1,
        rotation: int = 1, invert: bool | None = None, brightness: int | None = None,
    ) -> dict[str, Any]:
        """Save screen wiring in maintenance; never initialize or draw yet."""
        self._check()
        if not isinstance(panel, str) or panel not in self._PANELS:
            raise ValueError("panel 须为 st7789_240x320/st7789_240x240/st7735s_128x160")
        signals = {"sck": sck, "mosi": mosi, "cs": cs, "dc": dc, "rst": rst}
        for name, pin in signals.items():
            _integer(pin, name, 0, 48)
        _integer(backlight, "backlight", -1, 48)
        assigned = list(signals.values()) + ([] if backlight == -1 else [backlight])
        if len(set(assigned)) != len(assigned):
            raise ValueError("屏幕信号和背光引脚不得重复")
        _integer(rotation, "rotation", 0, 3)
        if invert is None:
            invert = panel.startswith("st7789_")
        if type(invert) is not bool:
            raise ValueError("invert 必须为 bool")
        if brightness is None:
            brightness = 100 if backlight == -1 else 60
        _integer(brightness, "brightness", 0, 100)
        if backlight == -1 and brightness != 100:
            raise ValueError("未连接 GPIO 背光时 brightness 只能为100，不能调光")
        self._robot.maintenance.enter()
        current = self._robot.config.get()
        config = copy.deepcopy(current["config"])
        config["display"] = {"panel": panel, **signals, "backlight": backlight,
                             "rotation": rotation, "invert": invert, "brightness": brightness}
        return self._robot.config.apply(config, expected_revision=current["revision"])

    def unconfigure(self) -> dict[str, Any]:
        """Remove only the display mapping and remain in maintenance."""
        self._check()
        self._robot.maintenance.enter()
        current = self._robot.config.get()
        config = copy.deepcopy(current["config"])
        config.pop("display", None)
        return self._robot.config.apply(config, expected_revision=current["revision"])

    def begin(self) -> dict[str, Any]:
        self._check()
        return self._robot._request("display.begin")

    def fill(self, color="black") -> dict[str, Any]:
        self._check()
        return self._robot._request("display.fill", {"color": self._color(color)})

    def clear(self, color="black") -> dict[str, Any]:
        return self.fill(color)

    def text(self, text: str, x: int = 0, y: int = 0, color="white") -> dict[str, Any]:
        self._check()
        if not isinstance(text, str):
            raise ValueError("text 必须为字符串")
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("text 必须是合法 UTF-8 字符串") from error
        if not 1 <= len(encoded) <= 192 or any((ord(c) < 32 and c != "\n") or 127 <= ord(c) <= 159 for c in text):
            raise ValueError("text 须为1～192个UTF-8字节，不含控制字符（允许换行）")
        return self._robot._request("display.text", {
            "x": _integer(x, "x", 0, 319), "y": _integer(y, "y", 0, 319),
            "text": text, "color": self._color(color),
        })

    def rect(self, x: int, y: int, width: int, height: int, color="white", filled: bool = False) -> dict[str, Any]:
        self._check()
        if type(filled) is not bool:
            raise ValueError("filled 必须为 bool")
        return self._robot._request("display.rect", {
            "x": _integer(x, "x", 0, 319), "y": _integer(y, "y", 0, 319),
            "width": _integer(width, "width", 1, 320), "height": _integer(height, "height", 1, 320),
            "color": self._color(color), "filled": filled,
        })

    def line(self, x0: int, y0: int, x1: int, y1: int, color="white") -> dict[str, Any]:
        self._check()
        return self._robot._request("display.line", {
            "x0": _integer(x0, "x0", 0, 319), "y0": _integer(y0, "y0", 0, 319),
            "x1": _integer(x1, "x1", 0, 319), "y1": _integer(y1, "y1", 0, 319),
            "color": self._color(color),
        })

    def _check_bitmap(self) -> None:
        self._check()
        if self._robot._info.get("capabilities", {}).get("display_bitmap") is not True:
            raise UnsupportedCapability("该固件未声明display_bitmap能力，请更新支持图片传输的教学固件")

    def _viewport(self) -> tuple[int, int]:
        state = self._robot.get_status().get("display")
        if not isinstance(state, dict) or state.get("active") is not True:
            raise ValueError("请先配置屏幕并调用display.begin()")
        width, height = state.get("width"), state.get("height")
        if type(width) is not int or type(height) is not int or not 1 <= width <= 320 or not 1 <= height <= 320:
            raise ProtocolError("固件返回的屏幕尺寸无效")
        return width, height

    @staticmethod
    def _bitmap_args(x: int, y: int, width: int, height: int, pixels: bytes) -> dict[str, Any]:
        _integer(x, "x", 0, 319); _integer(y, "y", 0, 319)
        _integer(width, "width", 1, 320); _integer(height, "height", 1, 320)
        if width * height > 384 or x + width > 320 or y + height > 320:
            raise ValueError("每块图像最多384像素，并须完整位于屏幕内")
        if not isinstance(pixels, bytes) or len(pixels) != width * height * 2:
            raise ValueError("pixels须为精确width*height*2字节的RGB565大端bytes")
        return {"x": x, "y": y, "width": width, "height": height,
                "data": base64.b64encode(pixels).decode("ascii")}

    def bitmap(self, x: int, y: int, width: int, height: int, pixels: bytes) -> dict[str, Any]:
        """Send one bounded RGB565BE rectangle; never writes NVS or retries."""
        self._check_bitmap()
        args = self._bitmap_args(x, y, width, height, pixels)
        screen_width, screen_height = self._viewport()
        if x + width > screen_width or y + height > screen_height:
            raise ValueError("图像块必须完整位于当前旋转后的屏幕内")
        return self._robot._request("display.bitmap", args)

    def image(self, image_or_path, fit: str = "contain", background="black") -> dict[str, Any]:
        """Fit a Pillow/local image to the active panel and stream RAM strips."""
        self._check_bitmap()
        if fit not in ("contain", "cover"):
            raise ValueError("fit须为contain或cover")
        color = self._color(background)
        rgb = (((color >> 11) & 31) * 255 // 31, ((color >> 5) & 63) * 255 // 63, (color & 31) * 255 // 31)
        from .drawing import load_image, fit_image, rgb565_strips
        source = load_image(image_or_path)
        try:
            size = self._viewport()
            fitted = fit_image(source, size, fit, rgb)
        finally:
            source.close()
        chunks = 0
        try:
            if self._fps is not None and self._last_frame_at is not None:
                self._robot.wait(max(0.0, 1 / self._fps - (time.monotonic() - self._last_frame_at)))
            self._last_frame_at = time.monotonic()
            transfer_started = self._last_frame_at
            for y, rows, pixels in rgb565_strips(fitted):
                self._robot._request("display.bitmap", self._bitmap_args(0, y, size[0], rows, pixels))
                chunks += 1
        finally:
            fitted.close()
        return {"width": size[0], "height": size[1], "chunks": chunks,
                "state": "commanded", "physical_verified": False,
                "transfer_seconds": time.monotonic() - transfer_started}

    def brightness(self, percent: int) -> dict[str, Any]:
        self._check()
        return self._robot._request("display.brightness", {"percent": _integer(percent, "percent", 0, 100)})

    def release(self) -> dict[str, Any]:
        self._check()
        return self._robot._request("display.release")


class _Unavailable:
    def __init__(self, capability: str): self._capability = capability

    def __getattr__(self, name: str):
        raise UnsupportedCapability(f"首版尚未实现 {self._capability}，不会模拟执行 {name}")
