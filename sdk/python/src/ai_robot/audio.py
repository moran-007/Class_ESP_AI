"""Canonical local/cloud audio and bounded USB I2S commands.

Wire audio is always signed PCM16 little-endian, 16000 Hz, mono. WAV is a
desktop container. Importing this module never opens USB, files or the network.
"""
from __future__ import annotations

import array
import base64
from dataclasses import dataclass
import io
import math
from pathlib import Path
import struct
import sys
from typing import Any, TYPE_CHECKING
from urllib import error as urlerror, parse as urlparse, request as urlrequest
import wave

from .errors import ProtocolError, UnsupportedCapability

if TYPE_CHECKING:
    from .client import Robot

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
FORMAT = 'pcm_s16le'
MAX_SECONDS = 30
MAX_PCM_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * MAX_SECONDS
MAX_SOURCE_BYTES = MAX_PCM_BYTES + 65536
CHUNK_BYTES = 768


def _int(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}须为{low}～{high}整数')
    return value


def _duration(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= MAX_SECONDS:
        raise ValueError(f'录音/音频时长须为大于0且不超过{MAX_SECONDS}秒的有限数')
    return max(1, round(seconds * SAMPLE_RATE))


def _bounded_file(path):
    with Path(path).open('rb') as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError('音频源文件超出本版30秒/有界容器大小限制')
    return data


@dataclass(frozen=True, slots=True)
class AudioClip:
    """An immutable, explicitly formatted local/cloud audio value, max30seconds.

    No automatic resampling, stereo mixing, MP3 decoding or endian guessing.
    Send ``clip.pcm`` to the existing cloud dialogue PCM endpoint; use
    ``clip.to_wire()`` as explicit metadata for future transports.
    """
    pcm: bytes
    sample_rate: int = SAMPLE_RATE
    channels: int = CHANNELS
    sample_width: int = SAMPLE_WIDTH
    format: str = FORMAT
    byte_order: str = 'little'

    def __post_init__(self):
        if type(self.pcm) is not bytes or not self.pcm or len(self.pcm) % 2 or len(self.pcm) > MAX_PCM_BYTES:
            raise ValueError('PCM须为非空、偶数字节的bytes，最多30秒/960000字节')
        if type(self.sample_rate) is not int or self.sample_rate != SAMPLE_RATE or type(self.channels) is not int or self.channels != CHANNELS or type(self.sample_width) is not int or self.sample_width != SAMPLE_WIDTH or self.format != FORMAT or self.byte_order != 'little':
            raise ValueError('仅接受pcm_s16le、16000Hz、单声道、16bit、little字节序；请先显式转换')

    @property
    def samples(self): return len(self.pcm) // SAMPLE_WIDTH

    @property
    def duration_seconds(self): return self.samples / SAMPLE_RATE

    def _samples(self):
        samples = array.array('h', self.pcm)
        if sys.byteorder != 'little': samples.byteswap()
        return samples

    @property
    def peak(self): return max(abs(sample) for sample in self._samples())

    @property
    def rms(self): return math.sqrt(sum(sample * sample for sample in self._samples()) / self.samples)

    @property
    def levels(self):
        samples = self._samples()
        return {'peak': max(abs(sample) for sample in samples),
                'rms': math.sqrt(sum(sample * sample for sample in samples) / len(samples)),
                'clipped_samples': sum(sample in (-32768, 32767) for sample in samples),
                'all_zero': not any(samples), 'physical_verified': False}

    @classmethod
    def from_pcm(cls, source, **metadata):
        """Read explicitly declared canonical PCM bytes or a bounded local file."""
        data = _bounded_file(source) if isinstance(source, (str, Path)) else source
        return cls(data, **metadata)

    def to_pcm(self, path=None):
        if path is not None: Path(path).write_bytes(self.pcm)
        return self.pcm

    @classmethod
    def from_wav(cls, source):
        data = _bounded_file(source) if isinstance(source, (str, Path)) else source
        if type(data) is not bytes or not 1 <= len(data) <= MAX_SOURCE_BYTES:
            raise ValueError('WAV须为有界bytes或本地文件路径')
        try:
            with wave.open(io.BytesIO(data), 'rb') as wav:
                if wav.getcomptype() != 'NONE' or wav.getnchannels() != CHANNELS or wav.getsampwidth() != SAMPLE_WIDTH or wav.getframerate() != SAMPLE_RATE:
                    raise ValueError('WAV须为未压缩PCM、16000Hz、单声道、16bit；本版不自动重采样')
                expected = wav.getnframes() * SAMPLE_WIDTH
                if not 0 < expected <= MAX_PCM_BYTES: raise ValueError('WAV时长超出0～30秒范围')
                pcm = wav.readframes(wav.getnframes())
                if len(pcm) != expected: raise ValueError('WAV数据截断，不能作为完整音频发送')
        except (wave.Error, EOFError, struct.error) as error:
            raise ValueError('不是受支持的完整PCM WAV文件') from error
        return cls(pcm)

    def to_wav(self, path=None):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(CHANNELS); wav.setsampwidth(SAMPLE_WIDTH); wav.setframerate(SAMPLE_RATE)
            wav.writeframes(self.pcm)
        data = buffer.getvalue()
        if path is not None: Path(path).write_bytes(data)
        return data

    def to_wire(self):
        return {'schema_version': 1, 'format': FORMAT, 'sample_rate': SAMPLE_RATE,
                'channels': CHANNELS, 'sample_width': SAMPLE_WIDTH, 'byte_order': 'little', 'bytes': len(self.pcm)}

    @classmethod
    def from_wire(cls, pcm, metadata):
        if type(metadata) is not dict or set(metadata) != {'schema_version','format','sample_rate','channels','sample_width','byte_order','bytes'}:
            raise ValueError('音频元数据字段不完整或包含未知字段')
        if type(metadata['schema_version']) is not int or metadata['schema_version'] != 1 or type(metadata['bytes']) is not int or type(pcm) is not bytes or metadata['bytes'] != len(pcm):
            raise ValueError('音频元数据版本或bytes与实际数据不匹配')
        return cls(pcm, **{key: metadata[key] for key in ('format','sample_rate','channels','sample_width','byte_order')})

    @classmethod
    def tone(cls, frequency=440, seconds=1, volume=.1):
        """Generate a low-level sine for an explicitly requested amplifier test."""
        count = _duration(seconds)
        if isinstance(frequency, bool) or not isinstance(frequency, (int, float)) or not math.isfinite(frequency) or not 0 < frequency < SAMPLE_RATE / 2:
            raise ValueError('测试频率须大于0且低于8000Hz')
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 1:
            raise ValueError('测试音源volume须为0～1有限数，建议0.1起步')
        pcm = bytearray(count * SAMPLE_WIDTH)
        for index in range(count):
            struct.pack_into('<h', pcm, index * 2, round(math.sin(2 * math.pi * frequency * index / SAMPLE_RATE) * volume * 32767))
        return cls(bytes(pcm))

    @classmethod
    def from_url(cls, url, **options):
        return load_audio_url(url, **options)


def _validate_url(url):
    if not isinstance(url, str): raise ValueError('音频URL须为http/https字符串')
    parsed = urlparse.urlsplit(url)
    if parsed.scheme.lower() not in ('http','https') or not parsed.hostname or parsed.username is not None or parsed.password is not None or any(ord(c) < 32 for c in url):
        raise ValueError('音频URL须为http/https且不能内嵌用户名密码')


class _AudioRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        old, new = urlparse.urlsplit(req.full_url), urlparse.urlsplit(newurl)
        if redirected is not None and (old.scheme,old.hostname,old.port) != (new.scheme,new.hostname,new.port):
            for name, _ in list(redirected.header_items()):
                if name.lower() in ('authorization','cookie','proxy-authorization'):
                    redirected.remove_header(name)
        return redirected


def load_audio_url(url, *, format='wav', sample_rate=None, channels=None, headers=None, timeout=10):
    """Download only on explicit call; return the same AudioClip as local files.

    Raw PCM must be explicitly declared with format='pcm_s16le' and a16000Hz,
    mono declaration via arguments or X-Audio-* headers. audio/L16 MIME alone
    is deliberately insufficient: it does not declare this little-endian wire.
    No AI API, automatic credentials, resampling or compressed codecs here.
    """
    _validate_url(url)
    if format not in ('wav', FORMAT): raise ValueError('URL音频格式只支持wav或明确的pcm_s16le')
    if sample_rate is not None and (type(sample_rate) is not int or sample_rate != SAMPLE_RATE): raise ValueError('仅接受16000Hz音频')
    if channels is not None and (type(channels) is not int or channels != CHANNELS): raise ValueError('仅接受单声道音频')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError('下载timeout须为0～120秒有限数')
    if headers is not None and (type(headers) is not dict or not all(isinstance(k,str) and isinstance(v,str) and '\r' not in k+v and '\n' not in k+v for k,v in headers.items())):
        raise ValueError('HTTP headers须为不含换行的字符串字典')
    request = urlrequest.Request(url, headers=headers or {}, method='GET')
    try:
        with urlrequest.build_opener(_AudioRedirect()).open(request, timeout=timeout) as source:
            if source.headers.get('Content-Encoding', 'identity').lower() not in ('identity',''):
                raise ValueError('不接受压缩传输的音频内容，请提供WAV或原始PCM')
            declared = source.headers.get('Content-Length')
            if declared is not None:
                try: size = int(declared)
                except ValueError: raise ValueError('音频Content-Length无效') from None
                if not 0 < size <= MAX_SOURCE_BYTES: raise ValueError('云端音频大小超出本版限制')
            payload = source.read(MAX_SOURCE_BYTES + 1)
            if len(payload) > MAX_SOURCE_BYTES: raise ValueError('云端音频超出本版30秒大小限制')
            if declared is not None and len(payload) != size: raise ValueError('云端音频下载不完整')
            response_headers = source.headers
    except urlerror.HTTPError as error:
        status = error.code
        error.close()
        raise ValueError(f'音频下载HTTP错误：{status}') from None
    except urlerror.URLError as error:
        raise OSError(f'音频下载连接失败：{error.reason}') from None
    if format == 'wav': return AudioClip.from_wav(payload)
    for header, expected in (('X-Audio-Format', FORMAT), ('X-Audio-Byte-Order','little')):
        if response_headers.get(header) not in (None, expected): raise ValueError(f'{header}与规范音频格式不匹配')
    declared_rate = response_headers.get('X-Audio-Sample-Rate')
    declared_channels = response_headers.get('X-Audio-Channels')
    declared_bits = response_headers.get('X-Audio-Bits')
    if sample_rate is None and declared_rate is None or channels is None and declared_channels is None:
        raise ValueError('原始PCM需显式声明sample_rate=16000、channels=1，或由X-Audio头声明')
    if declared_rate is not None and declared_rate != '16000' or declared_channels is not None and declared_channels != '1' or declared_bits is not None and declared_bits != '16':
        raise ValueError('云端PCM元数据与16000Hz/mono/16bit规范不匹配')
    return AudioClip(payload)


class Audio:
    """One configured I2S bus in this Robot session; no implicit playback."""
    def __init__(self, robot: Robot):
        self._robot = robot
        self._start_requested = False

    def _check(self, capability='i2s_audio'):
        if self._robot._info.get('capabilities', {}).get(capability) is not True:
            raise UnsupportedCapability('当前固件不支持该I2S音频操作，请使用ai-maker-s3 V0.5.0或以上；旧固件不会模拟成功')

    def __getattr__(self, name):
        self._check()
        raise AttributeError(f'音频接口没有{name}方法')

    def set(self, bclk=42, ws=41, din=21, dout=40, sd=39, *, mic_channel='left', volume=20):
        """Configure runtime I2S GPIO, remain in maintenance; then robot.start().

        INMP441: BCLK/SCK=bclk, WS/LRCLK=ws, SD=data to din. MAX98357A:
        BCLK=bclk, LRC=ws, DIN=dout, SD/EN=sd. Microphone SD is DATA; amplifier
        SD is shutdown. Missing din/dout/sd may be-1; at least one data pin.
        Defaults are only reference wiring. Input PCM format is fixed16000/mono16.
        volume0..100 controls software playback gain, default20. Not NVS-stored.
        """
        self._check()
        _int(bclk,0,48,'bclk'); _int(ws,0,48,'ws')
        for key,value in (('din',din),('dout',dout),('sd',sd)): _int(value,-1,48,key)
        _int(volume,0,100,'volume')
        if mic_channel not in ('left','right'): raise ValueError('mic_channel须为left/right，对应麦克风L/R绑地/高电平选择')
        assigned = [pin for pin in (bclk,ws,din,dout,sd) if pin != -1]
        if len(set(assigned)) != len(assigned): raise ValueError('I2S各信号IO不能重复；BCLK/WS由两个模块共享同一个定义即可')
        if din == -1 and dout == -1: raise ValueError('din和dout至少启用一个方向')
        self._robot.maintenance.enter()
        result = self._robot._request('audio.configure', dict(bclk=bclk,ws=ws,din=din,dout=dout,sd=sd,mic_channel=mic_channel,volume=volume))
        self._start_requested = True
        return result

    def info(self):
        self._check()
        return self._robot._request('audio.info')

    def begin(self):
        self._check()
        return self._robot._request('audio.begin')

    def _stop_on_error(self):
        try: self._robot._request('audio.stop')
        except Exception: pass

    def record(self, seconds=3):
        """Capture0..30s into a PC AudioClip; not voice recognition or mic detection."""
        count = _duration(seconds) * SAMPLE_WIDTH
        self._check('audio_in')
        pcm = bytearray()
        try:
            self._robot._request('audio.record.begin')
            while len(pcm) < count:
                expected = min(CHUNK_BYTES, count - len(pcm))
                result = self._robot._request('audio.read', {'bytes': expected})
                if type(result.get('offset')) is not int or result['offset'] != len(pcm) or type(result.get('bytes')) is not int or result['bytes'] != expected:
                    raise ProtocolError('录音分块偏移或长度不匹配；停止而不重发')
                try: chunk = base64.b64decode(result.get('data'), validate=True)
                except (ValueError, TypeError): raise ProtocolError('录音回执base64无效') from None
                if len(chunk) != expected: raise ProtocolError('录音实际PCM字节数与回执不一致')
                pcm.extend(chunk)
            end = self._robot._request('audio.record.end')
            if type(end.get('bytes')) is not int or end['bytes'] != count or type(end.get('samples')) is not int or end['samples'] != count // 2:
                raise ProtocolError('录音结束回执长度不匹配')
            return AudioClip(bytes(pcm))
        except BaseException:
            self._stop_on_error()
            raise

    def play(self, clip):
        """Play a validated AudioClip, bounded chunks and explicit drain/mute."""
        if not isinstance(clip, AudioClip): raise ValueError('play参数须为AudioClip；文件用play_file，URL用play_url')
        self._check('audio_out')
        try:
            self._robot._request('audio.play.begin')
            for offset in range(0,len(clip.pcm),CHUNK_BYTES):
                data = clip.pcm[offset:offset+CHUNK_BYTES]
                result = self._robot._request('audio.write', {'offset': offset, 'data': base64.b64encode(data).decode('ascii')})
                if type(result.get('bytes')) is not int or result['bytes'] != len(data) or type(result.get('next_offset')) is not int or result['next_offset'] != offset+len(data):
                    raise ProtocolError('播放分块长度/偏移回执不匹配；停止而不重发')
            result = self._robot._request('audio.play.end')
            if type(result.get('bytes')) is not int or result['bytes'] != len(clip.pcm) or type(result.get('samples')) is not int or result['samples'] != clip.samples:
                raise ProtocolError('播放结束回执长度不匹配')
            return {**result,'duration_seconds':clip.duration_seconds,'state':'commanded','physical_verified':False}
        except BaseException:
            self._stop_on_error()
            raise

    def play_file(self, path, *, format='wav'):
        self._check('audio_out')
        if format == 'wav': clip = AudioClip.from_wav(path)
        elif format == FORMAT: clip = AudioClip.from_pcm(path)
        else: raise ValueError('本地音频仅支持wav或明确声明的pcm_s16le，不自动解码MP3/OGG')
        return self.play(clip)

    def play_url(self, url, **options):
        self._check('audio_out')
        return self.play(load_audio_url(url, **options))

    def stop(self):
        self._check()
        return self._robot._request('audio.stop')

    def release(self):
        self._check()
        return self._robot._request('audio.release')

    def unconfigure(self):
        self._check()
        result = self._robot._request('audio.unconfigure')
        self._start_requested = False
        return result
