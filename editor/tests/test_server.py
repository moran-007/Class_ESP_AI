import http.client
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from editor.server import EditorServer, EditorState


class FakePages:
    def __init__(self): self.project = None; self.shown = None; self.enabled = False; self.startup_id = None
    def info(self): return {"saved": self.project is not None, "startup_enabled": self.enabled}
    def upload(self, project): self.project = project; self.enabled = False; return self.info()
    def download(self): return self.project
    def show(self, page_id): self.shown = page_id; return {"id": page_id}
    def startup(self, page_id=None, enabled=True): self.enabled = enabled; self.startup_id = page_id; return self.info()


class FakeRobot:
    created = []
    def __init__(self, port):
        self.port = port; self.pages = FakePages(); self.closed = False
        self.display = self; self.maintenance = self; self.mapping = None; self.exited = False
        self.created.append(self)
    def get_info(self): return {"firmware_version": "0.4.0", "capabilities": {"pages": True}}
    def get_status(self): return {"maintenance": False}
    @property
    def config(self): return self
    def get(self): return {"config": {"display": self.mapping, "servos": []}}
    def configure(self, **mapping): self.mapping = mapping; return mapping
    def exit(self): self.exited = True
    def close(self): self.closed = True


class ServerTests(unittest.TestCase):
    def setUp(self):
        FakeRobot.created = []
        self.state = EditorState(robot_factory=FakeRobot, ports_factory=lambda: [], validator=lambda p: p)
        self.server = EditorServer(("127.0.0.1", 0), self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.finish)
    def finish(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2); self.state.close()
    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        data = None if body is None else json.dumps(body)
        hdr = {"X-Editor-Token": self.server.token, "Content-Type": "application/json"}
        hdr.update(headers or {})
        conn.request(method, path, data, hdr)
        response = conn.getresponse(); raw = response.read(); status = response.status
        conn.close()
        return status, raw
    def test_load_and_status_do_not_connect_hardware(self):
        status, raw = self.request("GET", "/")
        self.assertEqual(status, 200); self.assertNotIn(b"__EDITOR_TOKEN__", raw)
        self.assertIn(self.server.token.encode(), raw)
        self.assertEqual(self.request("GET", "/api/status")[0], 200)
        self.assertEqual(FakeRobot.created, [])

    def test_shared_settings_do_not_connect_hardware(self):
        from project_config import load_config
        status, raw = self.request('GET', '/api/settings')
        self.assertEqual(status, 200)
        settings = json.loads(raw)
        self.assertEqual(settings['connection'], load_config()['connection'])
        self.assertEqual(settings['display'], load_config()['display'])
        self.assertEqual(FakeRobot.created, [])
    def test_token_origin_host_content_type_and_size_guards(self):
        self.assertEqual(self.request("GET", "/api/status", headers={"X-Editor-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("POST", "/api/connect", {"port":"AUTO"}, {"Origin":"https://evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/connect", {}, {"Content-Type":"text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/connect", {"x":"a"*17000})[0], 413)
        self.assertEqual(self.request("GET", "/api/status", headers={"Host":"evil.example"})[0], 403)
        self.assertEqual(FakeRobot.created, [])
    def test_explicit_actions_and_cleanup(self):
        self.assertEqual(self.request("POST", "/api/show", {"id":"home"})[0], 409)
        self.assertEqual(self.request("POST", "/api/connect", {"port":"FAKE"})[0], 200)
        robot = FakeRobot.created[0]
        self.assertEqual(self.request("POST", "/api/configure_display", {"sck":4})[0], 200)
        self.assertTrue(robot.exited)
        project={"pages":[{"id":"home"}]}
        self.assertEqual(self.request("POST", "/api/upload", {"project":project,"show":True,"startup":True})[0], 200)
        self.assertEqual(robot.pages.shown, "home"); self.assertTrue(robot.pages.enabled)
        self.assertEqual(self.request("POST", "/api/startup", {"enabled":False,"id":"not_uploaded_local_page"})[0], 200)
        self.assertIsNone(robot.pages.startup_id)
        status, raw = self.request("GET", "/api/project")
        self.assertEqual(json.loads(raw)["project"], project)
        self.assertEqual(self.request("POST", "/api/disconnect", {})[0], 200)
        self.assertTrue(robot.closed)
    def test_unknown_routes_and_fields_are_not_executed(self):
        self.assertEqual(self.request("GET", "/../../secret")[0], 404)
        self.assertEqual(self.request("POST", "/api/connect", {"port":"AUTO","execute":"anything"})[0], 400)
        self.assertEqual(FakeRobot.created, [])


if __name__ == "__main__": unittest.main()
