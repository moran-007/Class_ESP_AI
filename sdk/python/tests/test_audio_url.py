"""Actual local HTTP audio sources become the same AudioClip as local files."""
import http.server
import threading
import unittest
from urllib.request import Request

from ai_robot import AudioClip, load_audio_url
from ai_robot.audio import MAX_SOURCE_BYTES, _AudioRedirect


PCM=b'\x00\x80\x00\x00\xff\x7f'*32
WAV=AudioClip(PCM).to_wav()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/redirect-file':
            self.send_response(302);self.send_header('Location','file:///not-allowed.wav');self.end_headers();return
        if self.path=='/large':
            self.send_response(200);self.send_header('Content-Length',str(MAX_SOURCE_BYTES+1));self.end_headers();return
        payload=WAV if self.path=='/clip.wav' else PCM
        self.send_response(200)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Content-Type','audio/wav' if self.path=='/clip.wav' else 'audio/L16')
        self.send_header('X-Audio-Sample-Rate','24000' if self.path=='/wrong-rate' else '16000')
        self.send_header('X-Audio-Channels','1');self.send_header('X-Audio-Bits','16')
        self.end_headers();self.wfile.write(payload)


class AudioURLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)

    def test_local_wav_and_http_wav_are_byte_identical(self):
        self.assertEqual(load_audio_url(self.url+'/clip.wav'),AudioClip(PCM))

    def test_explicit_cloud_raw_pcm_uses_header_metadata_and_same_bytes(self):
        self.assertEqual(AudioClip.from_url(self.url+'/pcm',format='pcm_s16le'),AudioClip(PCM))

    def test_audio_l16_does_not_implicitly_mean_little_endian_pcm(self):
        with self.assertRaises(ValueError):load_audio_url(self.url+'/pcm')

    def test_wrong_rate_and_oversized_response_are_rejected(self):
        with self.assertRaises(ValueError):load_audio_url(self.url+'/wrong-rate',format='pcm_s16le')
        with self.assertRaises(ValueError):load_audio_url(self.url+'/large')

    def test_file_urls_redirects_credentials_and_codecs_are_rejected(self):
        for url in ('file:///tmp/clip.wav','ftp://example.test/clip.wav','https://name:secret@example.test/clip.wav'):
            with self.subTest(url=url),self.assertRaises(ValueError):load_audio_url(url)
        with self.assertRaises(ValueError):load_audio_url(self.url+'/redirect-file')
        with self.assertRaises(ValueError):load_audio_url(self.url+'/pcm',format='mp3')

    def test_cross_origin_redirect_drops_sensitive_headers(self):
        request=Request('https://first.example/a',headers={'Authorization':'Bearer test-only','Cookie':'test-only','Proxy-Authorization':'proxy-test-only'})
        redirected=_AudioRedirect().redirect_request(request,None,302,'Found',{},'https://second.example/b')
        self.assertFalse(redirected.has_header('Authorization'))
        self.assertFalse(redirected.has_header('Cookie'))
        self.assertFalse(any(name.lower()=='proxy-authorization' for name,_ in redirected.header_items()))


if __name__=='__main__':unittest.main()
