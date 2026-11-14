"""Loopback-only page editor and explicit USB bridge. No AI/network service."""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sdk/python/src"))
WEB = Path(__file__).resolve().parent / "web"
MAX_BODY = 16384


def default_robot(**kwargs):
    from ai_robot import Robot
    return Robot(**kwargs)


def default_validator(project):
    from ai_robot.pages import validate_project
    return validate_project(project)


def default_ports():
    from serial.tools import list_ports
    return [{"port": p.device, "description": p.description} for p in list_ports.comports() if p.vid is not None]


class EditorError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def keys(body, allowed):
    if not isinstance(body, dict) or set(body) - set(allowed):
        raise EditorError("请求字段不正确，请刷新编辑器后重试。")


class EditorState:
    def __init__(self, robot_factory=default_robot, ports_factory=default_ports, validator=default_validator):
        self.lock = threading.RLock()
        self.robot_factory = robot_factory
        self.ports_factory = ports_factory
        self.validator = validator
        self.robot = None
        self.port = None

    def close(self):
        with self.lock:
            robot, self.robot = self.robot, None
            self.port = None
            if robot is not None:
                robot.close()

    def require_robot(self):
        if self.robot is None:
            raise EditorError("请先选择串口并点击连接开发板。", 409)
        return self.robot

    def status(self):
        if self.robot is None:
            return dict(connected=False, port=None, info=None, status=None, config=None, pages=None)
        robot = self.robot
        info = robot.get_info()
        pages = robot.pages.info() if info.get("capabilities", {}).get("pages") else None
        return dict(connected=True, port=self.port, info=info, status=robot.get_status(), config=robot.config.get(), pages=pages)

    def action(self, method, path, body):
        with self.lock:
            if method == 'GET' and path == '/api/settings':
                from project_config import load_config
                settings = load_config()
                return {'connection': settings['connection'], 'display': settings['display']}
            if method == "GET" and path == "/api/ports":
                return {"ports": self.ports_factory(), "connected": self.robot is not None}
            if method == "GET" and path == "/api/status":
                return self.status()
            if method == "GET" and path == "/api/project":
                return {"project": self.require_robot().pages.download()}
            if method != "POST":
                raise EditorError("接口不存在。", 404)
            if path == "/api/connect":
                keys(body, ("port",))
                port = body.get("port", "AUTO")
                if not isinstance(port, str) or not port.strip() or len(port) > 128:
                    raise EditorError("串口名称不正确。")
                self.close()
                robot = self.robot_factory(port=port)
                self.robot, self.port = robot, port
                try:
                    return self.status()
                except Exception:
                    self.close()
                    raise
            if path == "/api/disconnect":
                keys(body, ())
                self.close()
                return self.status()
            if path == "/api/configure_display":
                keys(body, ("panel", "sck", "mosi", "cs", "dc", "rst", "backlight", "rotation", "invert", "brightness"))
                robot = self.require_robot()
                result = robot.display.configure(**body)
                robot.maintenance.exit()
                return {"result": result, "status": self.status()}
            if path == "/api/upload":
                keys(body, ("project", "show", "id", "startup"))
                if type(body.get("show", False)) is not bool or type(body.get("startup", False)) is not bool:
                    raise EditorError("show/startup 必须为布尔值。")
                project = self.validator(body.get("project"))
                robot = self.require_robot()
                page_id = body.get("id", project["pages"][0]["id"])
                if not isinstance(page_id, str) or page_id not in [p["id"] for p in project["pages"]]:
                    raise EditorError("所选页面不存在。")
                saved = robot.pages.upload(project)
                try:
                    if body.get("show", False):
                        robot.pages.show(page_id)
                    if body.get("startup", False):
                        robot.pages.startup(page_id, enabled=True)
                except Exception as error:
                    raise EditorError(f"页面已保存，但显示或开机设置失败：{error}", 409) from error
                return {"result": saved, "pages": robot.pages.info()}
            if path == "/api/show":
                keys(body, ("id",))
                if not isinstance(body.get("id"), str):
                    raise EditorError("请选择已保存的页面。")
                return {"result": self.require_robot().pages.show(body["id"])}
            if path == "/api/startup":
                keys(body, ("enabled", "id"))
                if type(body.get("enabled")) is not bool or ("id" in body and not isinstance(body["id"], str)):
                    raise EditorError("开机显示参数不正确。")
                page_id = body.get("id") if body["enabled"] else None
                return {"result": self.require_robot().pages.startup(page_id, enabled=body["enabled"])}
            raise EditorError("接口不存在。", 404)


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address=("127.0.0.1", 8765), state=None):
        if address[0] != "127.0.0.1":
            raise ValueError("编辑器只允许绑定127.0.0.1")
        self.state = state or EditorState()
        self.token = secrets.token_hex(32)
        super().__init__(address, EditorHandler)

    def server_close(self):
        try:
            self.state.close()
        finally:
            super().server_close()


class EditorHandler(BaseHTTPRequestHandler):
    server: EditorServer
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def respond(self, status, content, mime="application/json; charset=utf-8"):
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def valid_host(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        return self.headers.get("Host") in allowed

    def handle_request(self, method):
        try:
            if not self.valid_host():
                raise EditorError("只允许本机编辑器访问。", 403)
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                if not hmac.compare_digest(self.headers.get("X-Editor-Token", ""), self.server.token):
                    raise EditorError("编辑器会话已失效，请刷新页面。", 403)
                origin = self.headers.get("Origin")
                if origin is not None and origin != f"http://{self.headers['Host']}":
                    raise EditorError("请求来源不匹配。", 403)
                body = None
                if method == "POST":
                    if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                        raise EditorError("仅接受JSON请求。", 415)
                    if self.headers.get("Transfer-Encoding"):
                        raise EditorError("不支持分块HTTP请求。")
                    try:
                        length = int(self.headers.get("Content-Length", "-1"))
                    except ValueError:
                        raise EditorError("请求长度不正确。")
                    if not 0 <= length <= MAX_BODY:
                        self.close_connection = True
                        raise EditorError("请求过大，页面包最多8KiB。", 413)
                    raw = self.rfile.read(length)
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except (ValueError, UnicodeError):
                        raise EditorError("JSON格式或UTF-8编码不正确。")
                self.respond(200, self.server.state.action(method, path, body))
                return
            if method != "GET":
                raise EditorError("资源不存在。", 404)
            static = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
                      "/editor.js": ("editor.js", "application/javascript; charset=utf-8"), "/editor.css": ("editor.css", "text/css; charset=utf-8")}
            if path == "/favicon.ico":
                self.respond(204, b"", "image/x-icon"); return
            if path not in static:
                raise EditorError("资源不存在。", 404)
            name, mime = static[path]
            data = (WEB / name).read_bytes()
            if name == "index.html":
                data = data.replace(b"__EDITOR_TOKEN__", json.dumps(self.server.token).encode("ascii"))
            self.respond(200, data, mime)
        except EditorError as error:
            # Some guards reject a POST before its body is consumed.
            self.close_connection = True
            self.respond(error.status, {"error": str(error)})
        except (ValueError, TypeError) as error:
            self.respond(400, {"error": str(error)})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as error:
            self.respond(409, {"error": f"操作未完成：{error}"})

    def do_GET(self): self.handle_request("GET")
    def do_POST(self): self.handle_request("POST")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    server = EditorServer(("127.0.0.1", args.port))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"页面编辑器：{url}\n仅本机访问；按Ctrl+C关闭。连接开发板前可离线设计、预览和导出。", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭USB连接和编辑器。", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__": main()
