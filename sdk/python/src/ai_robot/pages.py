"""Bounded, data-only screen projects and the USB page-package client."""
from __future__ import annotations

import base64
import binascii
import copy
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any
import zlib

from .errors import ProtocolError, UnsupportedCapability

if TYPE_CHECKING:
    from .client import Robot

MAX_PROJECT_BYTES = 8192
MAX_SOURCE_BYTES = 65536  # Permit formatted local JSON; wire package is still 8KiB.
MAX_CHUNK_BYTES = 768
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,23}\Z")


def _int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} 必须为 {low}～{high} 的整数")
    return value


def _id(value, name="id"):
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{name} 须以ASCII字母开头，仅含字母、数字、下划线，最长24字符")
    return value


def _text(value):
    if not isinstance(value, str):
        raise ValueError("文字必须为字符串")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("文字必须是合法UTF-8") from error
    if not 1 <= len(encoded) <= 192 or any((ord(c) < 32 and c != "\n") or 127 <= ord(c) <= 159 for c in value):
        raise ValueError("文字须为1～192个UTF-8字节，不含控制字符（允许换行）")
    return value


def _fields(value, required, label):
    if type(value) is not dict or set(value) != set(required):
        raise ValueError(f"{label} 字段必须恰为：{', '.join(required)}")


def _base64(value):
    if not isinstance(value, str):
        raise ValueError("图像data必须为base64字符串")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as error:
        raise ValueError("非法base64数据") from error
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("base64须使用标准填充与规范编码")
    return raw


def _serialize(project):
    try:
        return json.dumps(project, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError("页面包必须为可序列化的UTF-8 JSON对象") from error


def validate_project(project: dict[str, Any]) -> dict[str, Any]:
    """Validate data without opening a port; return an independent deep copy."""
    _fields(project, ("schema_version", "width", "height", "pages", "images"), "页面包")
    if len(_serialize(project)) > MAX_PROJECT_BYTES:
        raise ValueError("页面包紧凑UTF-8 JSON不能超过8192字节")
    _int(project["schema_version"], "schema_version", 1, 1)
    width = _int(project["width"], "width", 1, 320)
    height = _int(project["height"], "height", 1, 320)
    images = project["images"]
    pages = project["pages"]
    if type(images) is not list or len(images) > 4:
        raise ValueError("images须为数组，最多4张图像")
    if type(pages) is not list or not 1 <= len(pages) <= 4:
        raise ValueError("pages须为数组，允许1～4页")
    assets = {}
    image_bytes = 0
    for image in images:
        _fields(image, ("id", "width", "height", "data"), "图像")
        name = _id(image["id"], "图像id")
        if name in assets:
            raise ValueError("图像id不可重复")
        iw = _int(image["width"], "图像width", 1, 48)
        ih = _int(image["height"], "图像height", 1, 48)
        raw = _base64(image["data"])
        if len(raw) != iw * ih * 2:
            raise ValueError("图像RGB565数据长度须为width*height*2")
        image_bytes += len(raw)
        assets[name] = (iw, ih)
    if image_bytes > 4608:
        raise ValueError("图像解码数据合计不能超过4608字节")
    page_ids = set()
    widget_count = 0
    for page in pages:
        _fields(page, ("id", "background", "widgets"), "页面")
        name = _id(page["id"], "页面id")
        if name in page_ids:
            raise ValueError("页面id不可重复")
        page_ids.add(name)
        _int(page["background"], "background", 0, 65535)
        widgets = page["widgets"]
        if type(widgets) is not list:
            raise ValueError("widgets必须为数组")
        widget_count += len(widgets)
        if widget_count > 32:
            raise ValueError("所有页面控件合计不能超过32个")
        widget_ids = set()
        for widget in widgets:
            if type(widget) is not dict:
                raise ValueError("控件必须为对象")
            kind = widget.get("type")
            fields = {
                "text": ("id", "type", "x", "y", "text", "color"),
                "rect": ("id", "type", "x", "y", "width", "height", "color", "filled"),
                "line": ("id", "type", "x0", "y0", "x1", "y1", "color"),
                "image": ("id", "type", "x", "y", "asset"),
            }
            if not isinstance(kind, str) or kind not in fields:
                raise ValueError("控件type须为text/rect/line/image")
            _fields(widget, fields[kind], "控件")
            name = _id(widget["id"], "控件id")
            if name in widget_ids:
                raise ValueError("同一页面控件id不可重复")
            widget_ids.add(name)
            if kind == "line":
                for key in ("x0", "x1"):
                    _int(widget[key], key, 0, width - 1)
                for key in ("y0", "y1"):
                    _int(widget[key], key, 0, height - 1)
            else:
                x = _int(widget["x"], "x", 0, width - 1)
                y = _int(widget["y"], "y", 0, height - 1)
            if kind != "image":
                _int(widget["color"], "color", 0, 65535)
            if kind == "text":
                _text(widget["text"])
            elif kind == "rect":
                _int(widget["width"], "矩形width", 1, width - x)
                _int(widget["height"], "矩形height", 1, height - y)
                if type(widget["filled"]) is not bool:
                    raise ValueError("filled必须为bool")
            elif kind == "image":
                asset = _id(widget["asset"], "asset")
                if asset not in assets:
                    raise ValueError("图像控件引用了不存在的asset")
                iw, ih = assets[asset]
                if x + iw > width or y + ih > height:
                    raise ValueError("图像必须完整位于画布内")
    return copy.deepcopy(project)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON字段重复：{key}")
        result[key] = value
    return result


def load_project(path: str | Path) -> dict[str, Any]:
    """Read a bounded local JSON file. This never executes its contents."""
    with Path(path).open("rb") as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("本地页面JSON源文件不能超过65536字节；紧凑数据仍限8192字节")
    try:
        project = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("页面文件不是合法UTF-8 JSON") from error
    return validate_project(project)


class Pages:
    """One saved project. Transfer operations are bounded and never retried."""
    def __init__(self, robot: Robot):
        self._robot = robot

    def _check(self):
        if not self._robot._info.get("capabilities", {}).get("pages", False):
            raise UnsupportedCapability("当前固件未声明pages能力，请使用V0.4.0或以上页面固件")

    def info(self) -> dict[str, Any]:
        self._check()
        return self._robot._request("pages.info")

    def upload(self, project_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
        self._check()
        project = load_project(project_or_path) if isinstance(project_or_path, (str, Path)) else validate_project(project_or_path)
        payload = _serialize(project)
        opened = self._robot._request("pages.upload.begin", {"bytes": len(payload), "crc32": f"{zlib.crc32(payload):08x}"})
        token = opened.get("upload_id")
        if not isinstance(token, str) or not token or len(token) > 64:
            raise ProtocolError("上传回执缺少有效upload_id")
        try:
            for offset in range(0, len(payload), MAX_CHUNK_BYTES):
                chunk = payload[offset:offset + MAX_CHUNK_BYTES]
                response = self._robot._request("pages.upload.chunk", {
                    "upload_id": token, "offset": offset,
                    "data": base64.b64encode(chunk).decode("ascii"),
                })
                if type(response.get("next_offset")) is not int or response["next_offset"] != offset + len(chunk):
                    raise ProtocolError("上传next_offset不匹配，停止传输，不自动重发")
            return self._robot._request("pages.upload.commit", {"upload_id": token})
        except BaseException:
            try:
                self._robot._request("pages.upload.abort", {"upload_id": token})
            except Exception:
                pass
            raise

    def download(self) -> dict[str, Any]:
        self._check()
        info = self.info()
        total = info.get("bytes")
        crc = info.get("crc32")
        if info.get("saved") is not True:
            raise ValueError("开发板尚未保存页面包")
        if type(total) is not int or not 1 <= total <= MAX_PROJECT_BYTES or not isinstance(crc, str) or re.fullmatch(r"[0-9a-fA-F]{8}", crc) is None:
            raise ProtocolError("页面包大小或CRC32回执无效")
        payload = bytearray()
        while len(payload) < total:
            offset = len(payload)
            response = self._robot._request("pages.read", {"offset": offset, "max_bytes": min(MAX_CHUNK_BYTES, total - offset)})
            if type(response.get("offset")) is not int or response["offset"] != offset or type(response.get("total_bytes")) is not int or response["total_bytes"] != total:
                raise ProtocolError("下载页面包偏移或总长度不匹配")
            try:
                chunk = _base64(response.get("data"))
            except ValueError as error:
                raise ProtocolError("下载页面包base64无效") from error
            if not 1 <= len(chunk) <= min(MAX_CHUNK_BYTES, total - offset):
                raise ProtocolError("下载页面包分块长度无效")
            payload.extend(chunk)
            if type(response.get("eof")) is not bool or response["eof"] != (len(payload) == total):
                raise ProtocolError("下载页面包eof不匹配")
        if zlib.crc32(payload) != int(crc, 16):
            raise ProtocolError("下载页面包CRC32不匹配")
        try:
            return validate_project(json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object))
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ProtocolError("下载的数据不是合法页面包") from error

    def show(self, id: str = "home") -> dict[str, Any]:
        self._check()
        return self._robot._request("pages.show", {"id": _id(id)})

    def text(self, id: str, text: str) -> dict[str, Any]:
        self._check()
        return self._robot._request("pages.text", {"id": _id(id), "text": _text(text)})

    def startup(self, id: str | None = None, enabled: bool = True) -> dict[str, Any]:
        self._check()
        if type(enabled) is not bool:
            raise ValueError("enabled必须为bool")
        args: dict[str, Any] = {"enabled": enabled}
        if id is not None:
            args["id"] = _id(id)
        return self._robot._request("pages.startup", args)

    def clear(self) -> dict[str, Any]:
        self._check()
        self._robot.maintenance.enter()
        return self._robot._request("pages.clear")
