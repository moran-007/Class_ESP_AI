from contextlib import contextmanager, redirect_stdout
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
import ssl
from threading import Event, Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from ai_robot import AudioClip, Robot, RobotError, VoiceClient, VoiceError
from test_audio import AudioWire
from test_sdk import ScriptTransport


JOB = "a" * 32
PREFIX = "/voice-api/v1"
PCM = b"\x01\x00\x02\x00" * 16


@contextmanager
def gateway(*, failure=None, states=(), segments=(), rejection=None, job_error=None, segment_count=0):
    seen = []
    pending = iter(states)
    frames = iter(segments)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, payload, kind="application/json", **headers):
            if isinstance(payload, dict):
                payload = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.path, dict(self.headers), body))
            if rejection is not None:
                return self.send(*rejection)
            if failure == "unauthorized":
                return self.send(401, {"detail": "test-token"})
            if failure == "redirect":
                return self.send(302, b"", Location="/credentials-must-not-follow")
            self.send(202, {"job_id": "../invalid" if failure == "bad_id" else JOB,
                            "poll_url": "https://example.invalid/unused"})

        def do_GET(self):
            seen.append((self.path, dict(self.headers), b""))
            if "/segments?" in self.path:
                state, items = next(frames, ("completed", []))
                return self.send(200, {"job_id": JOB, "status": state, "segments": items})
            if self.path.endswith("/audio"):
                rate = "8000" if failure == "bad_rate" else "16000"
                payload = PCM + b"\x00" if failure == "odd_pcm" else PCM
                return self.send(200, payload, "audio/L16", **{"X-Audio-Sample-Rate": rate})
            state = "failed" if failure == "job_failed" or job_error else next(pending, "completed")
            self.send(200, {"job_id": JOB, "status": state,
                            "recognized_text": "识别结果", "answer_text": "回复内容", "error": job_error,
                            "segment_count": segment_count})

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", seen
        finally:
            server.shutdown()
            worker.join()


class VoiceTests(unittest.TestCase):
    def test_device_credentials_can_use_default_server_without_set(self):
        with Robot(transport=ScriptTransport(), heartbeat_interval=None) as robot:
            robot.ai.AIID("class-01")
            robot.ai.AItoken("test-token")
            self.assertEqual(robot.ai._configured()._base, "https://voice.bsnlch.xyz/voice-api/v1")

    def test_record_start_is_local_and_record_end_plays_each_segment_in_order(self):
        frames = tuple((status, [{"index": index, "text": text, "byte_count": len(PCM), "sample_rate": 16000,
                                  "audio_url": "https://example.invalid/do-not-follow"}])
                       for index, (status, text) in enumerate((("generating", "第一段"), ("completed", "第二段"))))
        wire = AudioWire()
        finished = Event()

        def observe(request, result):
            result = wire.audio_reply(request, result)
            if request["op"] == "audio.record.end":
                finished.set()
            return result

        wire.mutate = observe
        with (gateway(segments=frames, segment_count=2) as (url, seen),
              Robot(transport=wire, heartbeat_interval=None) as robot,
              redirect_stdout(StringIO()) as output, patch("ai_robot.voice.sleep")):
            robot.ai.set(url, "class-01", "test-token")
            robot.audio.set()
            robot.start()
            playback_positions = []
            play = robot.audio.play

            def observe_play(clip):
                playback_positions.append(seen[-1][0])
                return play(clip)

            with patch.object(robot.audio, "play", side_effect=observe_play):
                robot.ai.record_start(max_seconds=.24)
                self.assertTrue(finished.wait(2))
                self.assertEqual(seen, [])
                with self.assertRaisesRegex(VoiceError, "录音"):
                    robot.ai.record_start()
                with self.assertRaisesRegex(VoiceError, "录音"):
                    robot.ai.talk()
                reply = robot.ai.record_end()
                with self.assertRaisesRegex(VoiceError, "录音"):
                    robot.ai.record_end()
        self.assertEqual(reply.answer_text, "回复内容")
        self.assertIsNone(reply.audio)
        paths = [path for path, _, _ in seen]
        job_path = PREFIX + f"/jobs/{JOB}"
        self.assertEqual(paths, [PREFIX + "/dialogue", job_path + "/segments?after=-1",
                                 job_path + "/segments/0/audio", job_path + "/segments?after=0",
                                 job_path + "/segments/1/audio", job_path])
        self.assertEqual(playback_positions, [job_path + f"/segments/{i}/audio" for i in range(2)])
        self.assertEqual(sum(r["op"] == "audio.play.begin" for r in wire.requests), 2)
        self.assertLess(output.getvalue().index("第一段"), output.getvalue().index("第二段"))

    def test_recording_cancels_on_close_without_network(self):
        wire = AudioWire()
        started, stopped = Event(), Event()
        with gateway() as (url, seen), Robot(transport=wire, heartbeat_interval=None) as robot:
            robot.ai.set(url, "class-01", "test-token")
            robot.audio.set()
            robot.start()

            def capture(keep_recording, **kwargs):
                started.set()
                while keep_recording():
                    stopped.wait(.01)
                stopped.set()

            with patch.object(robot.audio, "record_while", side_effect=capture):
                robot.ai.record_start()
                self.assertTrue(started.wait(2))
                robot.close()
                self.assertTrue(stopped.wait(2))
            self.assertEqual(seen, [])

    def test_short_recordings_are_discarded_and_leave_next_round_available(self):
        with gateway() as (url, seen), Robot(transport=AudioWire(), heartbeat_interval=None) as robot:
            robot.ai.set(url, "class-01", "test-token")
            robot.audio.set()
            robot.start()
            with patch.object(robot.audio, "record_while", return_value=AudioClip(PCM)):
                for _ in range(2):
                    robot.ai.record_start()
                    self.assertIsNone(robot.ai.record_end(progress=False))
            self.assertEqual(seen, [])

    def test_segment_metadata_is_checked_and_bad_segment_is_not_played(self):
        good = {"index": 0, "text": "第一段", "byte_count": len(PCM), "sample_rate": 16000}
        cases = (({"index": 1}, None), ({"sample_rate": 8000}, None), ({"byte_count": len(PCM) + 2}, None),
                 ({}, "bad_rate"))
        for overrides, failure in cases:
            with self.subTest(overrides=overrides, failure=failure):
                frames = (("generating", [{**good, **overrides}]),)
                with gateway(segments=frames, failure=failure) as (url, seen):
                    played = []
                    voice = VoiceClient(url, "class-01", "test-token")
                    with self.assertRaisesRegex(VoiceError, JOB):
                        voice.dialogue(AudioClip(PCM), audio=False, on_segment=lambda *items: played.append(items))
                    self.assertEqual(played, [])
                    self.assertEqual(sum(path.endswith("/dialogue") for path, _, _ in seen), 1)

    def test_id_and_token_can_be_configured_separately(self):
        with gateway() as (url, seen):
            voice = VoiceClient(url)
            voice.AIID("class-01")
            with self.assertRaisesRegex(RobotError, "AItoken"):
                voice.ask("你好")
            self.assertEqual(seen, [])
            voice.AItoken("test-token")
            with self.assertRaises(ValueError) as invalid:
                voice.AItoken("do-not-echo-this\n")
            self.assertNotIn("do-not-echo-this", str(invalid.exception))
            self.assertEqual(voice.ask("你好").answer_text, "回复内容")
            self.assertEqual(seen[0][1]["X-Device-Id"], "class-01")
            self.assertEqual(seen[0][1]["Authorization"], "Bearer test-token")

    def test_robot_uses_same_credential_setters(self):
        with gateway() as (url, seen), Robot(transport=ScriptTransport(), heartbeat_interval=None) as robot:
            robot.ai.set(url)
            robot.ai.AIID("class-01")
            robot.ai.AItoken("test-token")
            self.assertEqual(robot.ai.ask("你好").answer_text, "回复内容")
            self.assertEqual(seen[0][1]["Authorization"], "Bearer test-token")

    def test_text_segments_are_delivered_before_final_job_response(self):
        received = []
        frames = (("generating", [{"index": 0, "text": "第一段"}]),
                  ("completed", [{"index": 1, "text": "第二段"}]))
        with gateway(segments=frames) as (url, seen), patch("ai_robot.voice.sleep"):
            def receive(text):
                received.append((text, seen[-1][0]))

            reply = VoiceClient(url, "class-01", "test-token").ask("讲个故事", on_text=receive)
        self.assertEqual(received, [("第一段", PREFIX + f"/jobs/{JOB}/segments?after=-1"),
                                    ("第二段", PREFIX + f"/jobs/{JOB}/segments?after=0")])
        self.assertEqual(reply.answer_text, "回复内容")
        self.assertEqual(seen[-1][0], PREFIX + f"/jobs/{JOB}")
        self.assertEqual(sum(path.endswith("/text-dialogue") for path, _, _ in seen), 1)

    def test_progress_follows_server_states_and_keeps_credentials_out(self):
        messages = StringIO()
        with gateway(states=("queued", "generating", "generating")) as (url, seen):
            with redirect_stdout(messages), patch("ai_robot.voice.sleep"):
                reply = VoiceClient(url, "class-01", "test-token").ask("讲个故事", progress=True)
        self.assertEqual(reply.answer_text, "回复内容")
        self.assertEqual(sum(path.endswith("/text-dialogue") for path, _, _ in seen), 1)
        output = messages.getvalue()
        stages = ["正在提交", "已接收", "排队中", "正在生成回复", "回复已完成"]
        self.assertEqual([output.index(stage) for stage in stages], sorted(output.index(stage) for stage in stages))
        self.assertEqual(output.count("正在生成回复"), 1)
        self.assertNotIn("test-token", output)

    def test_voice_reuses_pcm_and_downloads_valid_clip(self):
        with gateway() as (url, seen):
            reply = VoiceClient(url, "class-01", "test-token").dialogue(AudioClip(PCM))
        self.assertEqual(reply.answer_text, "回复内容")
        self.assertEqual(reply.recognized_text, "识别结果")
        self.assertEqual(reply.audio, AudioClip(PCM))
        self.assertEqual([item[0] for item in seen], [
            PREFIX + "/dialogue", PREFIX + f"/jobs/{JOB}", PREFIX + f"/jobs/{JOB}/audio"])
        self.assertEqual(seen[0][2], PCM)
        for _, headers, _ in seen:
            self.assertEqual(headers["Authorization"], "Bearer test-token")
            self.assertEqual(headers["X-Device-Id"], "class-01")
        self.assertEqual(seen[0][1]["Content-Type"], "audio/L16")

    def test_text_without_audio_and_transport_rejects_cross_origin(self):
        with gateway() as (url, seen):
            reply = VoiceClient(url, "class-01", "test-token").ask("你好")
        self.assertIsNone(reply.audio)
        self.assertEqual(seen[0][0], PREFIX + "/text-dialogue")
        self.assertEqual(json.loads(seen[0][2]), {"text": "你好"})
        self.assertEqual(len(seen), 2)
        with gateway(failure="redirect") as (url, seen):
            with self.assertRaisesRegex(RobotError, "重定向"):
                VoiceClient(url, "class-01", "test-token").ask("你好")
        self.assertEqual(len(seen), 1)
        with self.assertRaises(ValueError):
            VoiceClient("http://example.invalid", "class-01", "test-token")

    def test_failed_jobs_format_and_auth_errors_are_visible(self):
        for failure, detail in (("unauthorized", "401"), ("bad_id", "任务编号"),
                                ("job_failed", "任务失败"), ("bad_rate", "16000"),
                                ("odd_pcm", "PCM")):
            with self.subTest(failure=failure), gateway(failure=failure) as (url, _):
                with self.assertRaisesRegex(RobotError, detail) as error:
                    VoiceClient(url, "class-01", "test-token").dialogue(AudioClip(PCM))
                self.assertNotIn("test-token", str(error.exception))

    def test_robot_talk_uses_same_audio_api(self):
        with gateway() as (url, _), Robot(transport=ScriptTransport(), heartbeat_interval=None) as robot:
            with self.assertRaisesRegex(RobotError, "ai.set"):
                robot.ai.ask("你好")
            robot.ai.set(url, "class-01", "test-token")
            robot._info["capabilities"].update(i2s_audio=True, audio_in=True, audio_out=True)
            def record_once(seconds):
                with self.assertRaisesRegex(VoiceError, "录音"):
                    robot.ai.record_start()
                return AudioClip(PCM)

            with (patch.object(robot.audio, "info", return_value={"active": True, "din": 21, "dout": 40}),
                  patch.object(robot.audio, "record", side_effect=record_once) as record,
                  patch.object(robot.audio, "play") as play):
                reply = robot.ai.talk(2)
                record.assert_called_once_with(2)
                play.assert_called_once_with(reply.audio)

    def test_http_rejections_have_distinct_safe_errors(self):
        cases = (
            (401, {"detail": "test-token"}, "invalid_credentials", "Token 已失效"),
            (402, b"", "quota_exhausted", "额度"),
            (429, {"detail": {"error": {"code": "insufficient_quota", "message": "test-token"}}},
             "quota_exhausted", "额度"),
            (429, {"detail": "request rate limit"}, "rate_limited", "限流"),
            (429, b"<html>test-token</html>", "rate_limited", "限流"),
        )
        for status, payload, code, message in cases:
            with self.subTest(code=code), gateway(rejection=(status, payload)) as (url, seen):
                with self.assertRaisesRegex(VoiceError, message) as rejected:
                    VoiceClient(url, "class-01", "test-token").ask("你好")
                self.assertEqual(rejected.exception.code, code)
                self.assertNotIn("test-token", str(rejected.exception))
                self.assertEqual(len(seen), 1)

    def test_task_quota_failure_retains_code_and_job_id(self):
        for detail, code in (("语音合成失败：额度不足 test-token", "quota_exhausted"),
                             ("请检查连通性或额度 test-token", "job_failed")):
            with self.subTest(code=code), gateway(job_error=detail) as (url, seen):
                with self.assertRaisesRegex(VoiceError, JOB) as failure:
                    VoiceClient(url, "class-01", "test-token").ask("你好")
                self.assertEqual(failure.exception.code, code)
                self.assertNotIn("test-token", str(failure.exception))
                self.assertEqual(len(seen), 2)

    def test_rate_limit_status_is_reported_even_if_error_body_budget_is_used_up(self):
        voice = VoiceClient("https://example.invalid", "class-01", "test-token", timeout=1)
        headers = Message()
        headers["Content-Type"] = "application/json"
        http_failure = HTTPError("https://example.invalid", 429, "Limit", headers, None)
        with (patch.object(voice._opener, "open", side_effect=http_failure),
              patch.object(http_failure, "read1", create=True) as read_chunk,
              patch.object(http_failure, "read", create=True, return_value=b"{}") as read_all,
              patch("ai_robot.voice.monotonic", side_effect=(0.0, 0.1, 1.0))):
            with self.assertRaises(VoiceError) as limited:
                voice.ask("你好")
        self.assertEqual(limited.exception.code, "rate_limited")
        read_chunk.assert_not_called()
        read_all.assert_not_called()

    def test_connection_timeout_and_tls_errors_do_not_retry_or_echo_reason(self):
        for reason, code, message in (
            (ConnectionRefusedError("test-token"), "connection_error", "连接"),
            (TimeoutError("test-token"), "timeout", "超时"),
            (ssl.SSLCertVerificationError("test-token"), "tls_error", "HTTPS"),
        ):
            with self.subTest(code=code):
                voice = VoiceClient("https://example.invalid", "class-01", "test-token")
                with patch.object(voice._opener, "open", side_effect=URLError(reason)) as open_url:
                    with self.assertRaisesRegex(VoiceError, message) as failure:
                        voice.ask("你好")
                self.assertEqual(failure.exception.code, code)
                self.assertNotIn("test-token", str(failure.exception))
                open_url.assert_called_once()
