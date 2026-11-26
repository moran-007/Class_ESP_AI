"""Client for the existing /voice-api/v1 voice gateway; no USB required."""

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from http.client import HTTPException
import ipaddress
import json
import math
import re
import ssl
from threading import Event, Lock, Thread
from time import monotonic, sleep
from urllib import error, parse, request

from .audio import AudioClip, MAX_PCM_BYTES, SAMPLE_RATE, SAMPLE_WIDTH, _duration
from .errors import ConnectionLostError, RobotError, UnsupportedCapability


class VoiceError(RobotError):
    """The server was unavailable, rejected the request, or returned invalid data."""

    def __init__(self, message: str, *, code: str = "protocol_error"):
        super().__init__(message)
        self.code = code


_QUOTA_MESSAGE = "AI 服务额度已用尽或余额不足，请联系管理员"
_DEFAULT_VOICE_URL = "https://voice.bsnlch.xyz"
_QUOTA_MARKER = re.compile(
    r"\b(?:insufficient_quota|insufficient_user_quota|quota_?exhausted|insufficient_balance)\b"
    r"|额度(?:不足|(?:已)?用尽)|余额不足|insufficient (?:account )?balance",
    re.IGNORECASE,
)


def _reports_quota(value, depth=0):
    if isinstance(value, str):
        return bool(_QUOTA_MARKER.search(value))
    if isinstance(value, dict) and depth < 4:
        return any(_reports_quota(value.get(key), depth + 1) for key in ("code", "type", "message", "detail", "error"))
    return False


def _read_limited(response, limit, deadline):
    data = bytearray()
    while len(data) <= limit:
        if monotonic() >= deadline:
            raise VoiceError("读取 AI 服务响应超时，请稍后手动重试", code="timeout")
        block = response.read1(min(65536, limit + 1 - len(data)))
        if not block:
            break
        data.extend(block)
    return data


def _http_failure(exc, deadline):
    status = exc.code
    with exc:
        if status == 401:
            return VoiceError("AI 服务 HTTP 401：Token 已失效或设备 ID 不匹配，请更新本机 AI 配置",
                              code="invalid_credentials")
        if status == 402:
            return VoiceError(_QUOTA_MESSAGE, code="quota_exhausted")
        if status == 429:
            try:
                if exc.headers.get_content_type() == "application/json":
                    data = _read_limited(exc, 4096, deadline)
                    if len(data) <= 4096 and _reports_quota(json.loads(data)):
                        return VoiceError(_QUOTA_MESSAGE, code="quota_exhausted")
            except (OSError, HTTPException, ValueError, RecursionError, VoiceError):
                pass
            return VoiceError("AI 服务正在限流，请稍后手动重试（HTTP 429）", code="rate_limited")
    detail = {
        403: "设备没有此接口权限",
        404: "检查服务器地址、接口版本或任务是否过期",
        413: "录音太长，请缩短后再试",
        503: "AI 服务未就绪或已停用",
    }.get(status)
    if 300 <= status < 400:
        detail = "不跟随重定向，请填写最终服务器地址"
    return VoiceError(f"AI 服务 HTTP {status}" + (f"：{detail}" if detail else ""), code="http_error")


@dataclass(frozen=True, slots=True)
class VoiceReply:
    job_id: str
    recognized_text: str
    answer_text: str
    audio: AudioClip | None = None


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class VoiceClient:
    """Use the same HTTP endpoints and device credentials as the original robot."""

    def __init__(self, url: str, device_id: str | None = None, token: str | None = None, *, timeout: float = 90):
        if not isinstance(url, str) or not url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
            raise ValueError("请填写有效的 AI 服务器地址")
        try:
            endpoint = parse.urlsplit(url)
            port = endpoint.port
        except ValueError:
            raise ValueError("请填写有效的 AI 服务器地址") from None
        host = endpoint.hostname
        if (endpoint.scheme not in {"http", "https"} or not host or port == 0 or endpoint.username is not None
                or endpoint.query or endpoint.fragment or endpoint.path.rstrip("/") not in {"", "/voice-api/v1"}):
            raise ValueError("请填写服务器根地址或 /voice-api/v1 地址，不要在 URL 中填写凭据")
        if endpoint.scheme == "http":
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = host == "localhost"
            if not loopback:
                raise ValueError("远程 AI 服务器须使用 HTTPS；HTTP 仅用于本机测试")
        if type(timeout) not in (int, float) or not 0 < timeout <= 300 or not math.isfinite(timeout):
            raise ValueError("timeout 须为大于 0 且不超过 300 秒的数值")
        self._base = f"{endpoint.scheme}://{endpoint.netloc}/voice-api/v1"
        self._headers: dict[str, str] = {}
        if device_id is not None:
            self.AIID(device_id)
        if token is not None:
            self.AItoken(token)
        self._timeout = timeout
        self._opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def AIID(self, device_id: str) -> None:
        """Set the registered device ID in memory without making a request."""
        if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{3,64}", device_id):
            raise ValueError("设备 ID 须为 3～64 个字母、数字或 ._:-")
        self._headers["X-Device-ID"] = device_id

    def AItoken(self, token: str) -> None:
        """Set the device Token in memory without making a request."""
        if not isinstance(token, str) or not re.fullmatch(r"[!-~]{1,512}", token):
            raise ValueError("请填写设备 Token；不能包含空格、换行或非 ASCII 字符")
        self._headers["Authorization"] = f"Bearer {token}"

    def _fetch(self, path, *, deadline, limit, status, body=None, content_type=None):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise VoiceError("等待 AI 服务超时，请稍后手动重试", code="timeout")
        headers = self._headers.copy()
        if content_type is not None:
            headers["Content-Type"] = content_type
        call = request.Request(self._base + path, data=body, headers=headers)
        try:
            with self._opener.open(call, timeout=min(15, remaining)) as response:
                if response.status != status:
                    raise VoiceError(f"AI 服务返回意外的 HTTP 状态：{response.status}")
                if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
                    raise VoiceError("AI 服务返回了不支持的压缩响应")
                length = response.headers.get("Content-Length")
                if length is not None:
                    if not length.isascii() or not length.isdecimal() or len(length) > 12 or int(length) > limit:
                        raise VoiceError("AI 服务响应长度无效或超过上限")
                    length = int(length)
                data = _read_limited(response, limit, deadline)
                if len(data) > limit or (length is not None and len(data) != length):
                    raise VoiceError("AI 服务响应过大或不完整")
                return bytes(data), response.headers
        except error.HTTPError as exc:
            raise _http_failure(exc, deadline) from None
        except (OSError, HTTPException) as exc:
            reason = exc.reason if isinstance(exc, error.URLError) else exc
            if isinstance(reason, TimeoutError):
                raise VoiceError("等待 AI 服务超时，请稍后手动重试", code="timeout") from None
            if isinstance(reason, ssl.SSLError):
                raise VoiceError("AI 服务 HTTPS 连接失败，请检查服务器证书和电脑时间",
                                 code="tls_error") from None
            raise VoiceError("连接 AI 服务失败，请检查电脑网络和服务器地址", code="connection_error") from None

    def _json(self, path, deadline, *, body=None, content_type=None):
        data, _ = self._fetch(path, deadline=deadline, limit=128 * 1024, status=202 if body is not None else 200,
                              body=body, content_type=content_type)
        try:
            result = json.loads(data)
        except (ValueError, RecursionError):
            raise VoiceError("AI 服务返回的 JSON 无效") from None
        if not isinstance(result, dict):
            raise VoiceError("AI 服务未返回任务对象")
        return result

    def _dialogue(self, path, body, content_type, audio, progress, on_text=None, on_segment=None):
        self._check_credentials()
        if on_text is not None and not callable(on_text):
            raise ValueError("on_text 须为接收一个文字片段的函数")
        if on_segment is not None and not callable(on_segment):
            raise ValueError("on_segment 须为接收段号、文字和 AudioClip 的函数")

        def report(message):
            if progress:
                print(f"[AI] {message}", flush=True)

        started = monotonic()
        deadline = started + self._timeout
        report("正在提交问题…")
        job_id = self._json(path, deadline, body=body, content_type=content_type).get("job_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise VoiceError("AI 服务未返回有效任务编号")
        report(f"服务器已接收，任务号：{job_id}")
        try:
            return self._wait_job(job_id, deadline, started, audio, report, on_text, on_segment)
        except VoiceError as failure:
            raise VoiceError(f"任务 {job_id}：{failure}", code=failure.code) from None

    def _wait_job(self, job_id, deadline, started, audio, report, on_text, on_segment):
        path = f"/jobs/{job_id}"
        stages = {"queued": "排队中", "transcribing": "正在识别语音", "generating": "正在生成回复"}
        previous = None
        reminder = monotonic() + 10
        after = -1
        read_segments = on_text is not None or on_segment is not None
        while True:
            job = self._json(f"{path}/segments?after={after}" if read_segments else path, deadline)
            if job.get("job_id") != job_id:
                raise VoiceError("AI 服务返回的任务编号不匹配")
            status = job.get("status")
            if status == "failed":
                if _reports_quota(job.get("error")):
                    raise VoiceError(_QUOTA_MESSAGE, code="quota_exhausted")
                raise VoiceError("AI 服务任务失败，请用任务编号查看服务器日志", code="job_failed")
            if status not in ("queued", "transcribing", "generating", "completed"):
                raise VoiceError("AI 服务返回了未知的任务状态")
            now = monotonic()
            if status != "completed" and status != previous:
                report(stages[status] + "…")
                previous = status
                reminder = now + 10
            elif status != "completed" and now >= reminder:
                report(f"仍在等待服务器（已用时 {int(now - started)} 秒）…")
                reminder = now + 10
            if read_segments:
                segments = job.get("segments")
                if not isinstance(segments, list):
                    raise VoiceError("AI 服务未返回有效的回复分段")
                for segment in segments:
                    if (not isinstance(segment, dict) or type(segment.get("index")) is not int
                            or segment["index"] != after + 1 or not isinstance(segment.get("text"), str)
                            or not segment["text"].strip()):
                        raise VoiceError("AI 服务返回的文字分段或顺序无效")
                    if on_text is not None:
                        on_text(segment["text"])
                    if on_segment is not None:
                        clip = self._segment_audio(path, segment, deadline)
                        callback_started = monotonic()
                        on_segment(segment["index"], segment["text"], clip)
                        deadline += monotonic() - callback_started
                    after = segment["index"]
            if status == "completed":
                if read_segments:
                    job = self._json(path, deadline)
                    if job.get("job_id") != job_id or job.get("status") != "completed":
                        raise VoiceError("AI 服务没有确认同一任务已完成")
                if on_segment is not None and (
                    after < 0 or type(job.get("segment_count")) is not int or job["segment_count"] != after + 1
                ):
                    raise VoiceError("AI 服务的回复分段不完整")
                break
            if on_segment is not None and segments:
                continue
            sleep(max(0, min(0.5, deadline - monotonic())))
        recognized = job.get("recognized_text")
        answer = job.get("answer_text")
        if not isinstance(recognized, str) or not isinstance(answer, str) or not answer.strip():
            raise VoiceError("AI 任务已完成，但回复文字无效")
        clip = None
        if audio:
            report("正在下载回复音频…")
            clip = self._audio(path + "/audio", deadline)
        report(f"回复已完成，用时 {monotonic() - started:.1f} 秒。")
        return VoiceReply(job_id, recognized, answer, clip)

    def _segment_audio(self, path, segment, deadline):
        size = segment.get("byte_count")
        if (type(size) is not int or not 0 < size <= MAX_PCM_BYTES or size % SAMPLE_WIDTH
                or type(segment.get("sample_rate")) is not int or segment["sample_rate"] != SAMPLE_RATE):
            raise VoiceError("AI 回复分段的字节数或采样率无效")
        return self._audio(f"{path}/segments/{segment['index']}/audio", deadline, expected_bytes=size)

    def _audio(self, path, deadline, *, expected_bytes=None):
        limit = MAX_PCM_BYTES if expected_bytes is None else expected_bytes
        data, headers = self._fetch(path, deadline=deadline, limit=limit, status=200)
        if expected_bytes is not None and len(data) != expected_bytes:
            raise VoiceError("AI 回复分段的实际长度与声明不一致")
        if headers.get_content_type() != "audio/l16" or headers.get("X-Audio-Sample-Rate") != str(SAMPLE_RATE):
            raise VoiceError("AI 回复音频须为服务器约定的 16000 Hz PCM")
        for name, expected in (("X-Audio-Channels", "1"), ("X-Audio-Bits", "16"),
                               ("X-Audio-Byte-Order", "little"), ("X-Audio-Format", "pcm_s16le")):
            if headers.get(name, expected) != expected:
                raise VoiceError("AI 回复音频格式与单声道 PCM16LE 不符")
        try:
            return AudioClip(data)
        except ValueError:
            raise VoiceError("AI 回复的 PCM 为空、长度不完整或超过 30 秒") from None

    def ask(self, text: str, *, audio: bool = False, progress: bool = False,
            on_text: Callable[[str], None] | None = None) -> VoiceReply:
        """Submit text; optionally report ready text segments before completion."""
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError("问题须为 1～8000 字符的非空文字")
        body = json.dumps({"text": text.strip()}, ensure_ascii=False).encode("utf-8")
        return self._dialogue("/text-dialogue", body, "application/json", audio, progress, on_text)

    def dialogue(self, clip: AudioClip, *, audio: bool = True, progress: bool = False,
                 on_segment: Callable[[int, str, AudioClip], None] | None = None) -> VoiceReply:
        """Submit existing AudioClip PCM with the original server's wire format."""
        if not isinstance(clip, AudioClip):
            raise ValueError("语音输入须为 AudioClip；文件可先用 AudioClip.from_wav() 加载")
        return self._dialogue("/dialogue", clip.pcm, "audio/L16", audio, progress, on_segment=on_segment)

    def _check_credentials(self):
        if "X-Device-ID" not in self._headers:
            raise VoiceError("请先调用 AIID(device_id) 设置设备 ID")
        if "Authorization" not in self._headers:
            raise VoiceError("请先调用 AItoken(token) 设置设备 Token")


class _Recording:
    def __init__(self, audio, max_seconds):
        self.stop = Event()
        self.result: Future[AudioClip | None] = Future()
        self.thread = Thread(target=self._capture, args=(audio, max_seconds), daemon=True)

    def _capture(self, audio, max_seconds):
        try:
            clip = audio.record_while(lambda: not self.stop.is_set(), max_seconds=max_seconds)
        except BaseException as failure:
            self.result.set_exception(failure)
        else:
            self.result.set_result(clip)


class RobotVoice:
    def __init__(self, robot):
        self._robot = robot
        self._client = None
        self._recording: _Recording | None = None
        self._recording_lock = Lock()
        self._talking = False

    def set(self, url, device_id=None, token=None, *, timeout=90):
        """Set the PC-side gateway credentials for this Robot object."""
        self._client = VoiceClient(url, device_id, token, timeout=timeout)

    def _configured(self):
        if self._client is None:
            raise UnsupportedCapability("请先调用 robot.ai.set(url) 设置 AI 服务器")
        return self._client

    def _credentials_client(self):
        if self._client is None:
            self.set(_DEFAULT_VOICE_URL)
        return self._client

    def AIID(self, device_id: str) -> None:
        self._credentials_client().AIID(device_id)

    def AItoken(self, token: str) -> None:
        self._credentials_client().AItoken(token)

    def ask(self, text, *, audio=False, progress=False, on_text=None):
        return self._configured().ask(text, audio=audio, progress=progress, on_text=on_text)

    def dialogue(self, clip, *, audio=True, progress=False, on_segment=None):
        return self._configured().dialogue(clip, audio=audio, progress=progress, on_segment=on_segment)

    def _check_audio(self, *, play):
        client = self._configured()
        client._check_credentials()
        if self._robot._read_only:
            raise UnsupportedCapability("语音录放需要普通 USB 控制连接")
        self._robot.audio._check("audio_in")
        if play:
            self._robot.audio._check("audio_out")
        setup = self._robot.audio.info()
        if not setup.get("active") or setup.get("din", -1) < 0 or (play and setup.get("dout", -1) < 0):
            raise UnsupportedCapability("请先用 robot.audio.set(...) 配置收音和所需的功放引脚，再调用 robot.start()")
        if setup.get("recording") or setup.get("playing"):
            raise VoiceError("开发板正在录音或播放，请等待本轮结束", code="recording_busy")
        return client

    def record_start(self, *, max_seconds=20) -> None:
        """Start local capture in the background; pressing alone makes no HTTP request."""
        if _duration(max_seconds) / SAMPLE_RATE < 0.2:
            raise ValueError("AI 录音上限至少为 0.2 秒")
        with self._recording_lock:
            if self._recording is not None or self._talking:
                raise VoiceError("上一轮录音或回复尚未结束", code="recording_busy")
            self._check_audio(play=True)
            recording = _Recording(self._robot.audio, max_seconds)
            self._recording = recording
            try:
                recording.thread.start()
            except BaseException:
                recording.stop.set()
                self._recording = None
                raise

    def record_end(self, *, progress=True) -> VoiceReply | None:
        """Stop capture, submit it once, and play each ready segment on the board."""
        with self._recording_lock:
            recording = self._recording
            if recording is None or recording.stop.is_set():
                raise VoiceError("请先调用 robot.ai.record_start() 开始录音", code="recording_inactive")
            recording.stop.set()

        def play_segment(index, text, clip):
            if progress:
                print(f"AI 第 {index + 1} 段：{text}", flush=True)
            self._robot.audio.play(clip)

        try:
            clip = recording.result.result()
            if self._robot._closing or self._robot._closed:
                raise ConnectionLostError("连接已经关闭")
            if clip is None or clip.duration_seconds < 0.2:
                if progress:
                    print("录音太短，请按住按钮说完再松开。", flush=True)
                return None
            return self.dialogue(clip, audio=False, progress=progress, on_segment=play_segment)
        finally:
            if not recording.result.done():
                recording.thread.join()
            with self._recording_lock:
                if self._recording is recording:
                    self._recording = None

    def _discard_recording(self):
        with self._recording_lock:
            if self._recording is not None:
                self._recording.stop.set()
                self._recording = None

    def talk(self, seconds=3, *, play=True, progress=False):
        """Record once, submit to the gateway and optionally play the answer."""
        with self._recording_lock:
            if self._recording is not None or self._talking:
                raise VoiceError("上一轮录音或回复尚未结束", code="recording_busy")
            self._talking = True
        try:
            client = self._check_audio(play=play)
            clip = self._robot.audio.record(seconds)
            reply = client.dialogue(clip, audio=play, progress=progress)
            if play:
                if progress:
                    print("[AI] 正在通过功放播放回复…", flush=True)
                self._robot.audio.play(reply.audio)
            return reply
        finally:
            with self._recording_lock:
                self._talking = False
