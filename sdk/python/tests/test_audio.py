"""Audio codec and bounded USB contracts; no physical sound is claimed."""
import base64
import copy
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from ai_robot import AudioClip, Robot, UnsupportedCapability, DeviceError, ProtocolError
from test_sdk import ScriptTransport, response
from test_native_integration import ProcessTransport


class AudioClipTests(unittest.TestCase):
    def test_pcm_wav_and_wire_roundtrip_preserve_exact_little_endian_samples(self):
        pcm=struct.pack('<5h',-32768,-1234,0,1234,32767)
        clip=AudioClip(pcm)
        self.assertEqual(AudioClip.from_wav(clip.to_wav()).pcm,pcm)
        self.assertEqual(AudioClip.from_wire(pcm,clip.to_wire()),clip)
        self.assertEqual(clip.samples,5)
        self.assertEqual(clip.peak,32768)
        self.assertGreater(clip.rms,0)

    def test_wrong_format_alignment_and_truncated_wav_are_rejected(self):
        for pcm in (b'',b'\0',bytearray(b'\0\0')):
            with self.subTest(pcm=pcm),self.assertRaises(ValueError):AudioClip(pcm)
        for kwargs in ({'sample_rate':8000},{'channels':2},{'sample_width':1},{'byte_order':'big'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):AudioClip(b'\0\0',**kwargs)
        clip=AudioClip(b'\0\0'*32)
        with self.assertRaises(ValueError):AudioClip.from_wav(clip.to_wav()[:-4])
        metadata=clip.to_wire();metadata['bytes']+=2
        with self.assertRaises(ValueError):AudioClip.from_wire(clip.pcm,metadata)

    def test_tone_is_bounded_and_local_files_share_the_wire_format(self):
        clip=AudioClip.tone(seconds=.05,volume=.1)
        self.assertEqual(clip.samples,800)
        self.assertLessEqual(clip.peak,3277)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sound.wav';clip.to_wav(path)
            self.assertEqual(AudioClip.from_wav(path),clip)
        with self.assertRaises(ValueError):AudioClip.tone(seconds=31)


class AudioWire(ScriptTransport):
    def __init__(self):
        self.audio_config={};self.active=False;self.recording=False;self.playing=False
        self.read_offset=0;self.written=bytearray();self.fail_op=None
        super().__init__(mutate=self.audio_reply)

    def audio_reply(self,request,result):
        op,args=request['op'],request['args']
        if op==self.fail_op:return response(request,code='HARDWARE_ERROR',message='audio failed')
        if op=='device.info':result['data']['capabilities'].update(audio_in=True,audio_out=True,i2s_audio=True,configurable_audio_pins=True)
        elif op=='device.status':result['data']['audio']={'configured':bool(self.audio_config),'active':self.active}
        elif op=='audio.configure':self.audio_config=copy.deepcopy(args);result['data']={'configured':True,**args}
        elif op=='audio.begin':self.active=True;result['data']={'active':True}
        elif op=='audio.info':result['data']={'active':self.active,**self.audio_config}
        elif op=='audio.record.begin':self.recording=True;self.read_offset=0
        elif op=='audio.read':
            count=args['bytes'];pcm=struct.pack('<h',1234)*(count//2)
            result['data']={'data':base64.b64encode(pcm).decode(),'bytes':count,'offset':self.read_offset};self.read_offset+=count
        elif op=='audio.record.end':self.recording=False;result['data']={'bytes':self.read_offset,'samples':self.read_offset//2}
        elif op=='audio.play.begin':self.playing=True;self.written.clear()
        elif op=='audio.write':
            pcm=base64.b64decode(args['data']);self.written.extend(pcm)
            result['data']={'bytes':len(pcm),'next_offset':len(self.written)}
        elif op=='audio.play.end':self.playing=False;result['data']={'bytes':len(self.written),'samples':len(self.written)//2}
        elif op=='audio.stop':self.recording=self.playing=False
        return result


class AudioSDKTests(unittest.TestCase):
    def setUp(self):
        self.wire=AudioWire();self.robot=Robot(transport=self.wire,heartbeat_interval=None)
        self.addCleanup(self.robot.close)

    def test_set_then_start_preserves_other_configs_and_does_not_play_or_record(self):
        self.robot.audio.set(bclk=18,ws=17,din=21,dout=40,sd=39)
        self.assertTrue(self.wire.maintenance)
        self.robot.start()
        self.assertTrue(self.wire.active)
        self.assertFalse(self.wire.recording or self.wire.playing)

    def test_record_and_play_are_chunked_and_preserve_exact_pcm(self):
        self.robot.audio.set();self.robot.start()
        clip=self.robot.audio.record(.05)
        self.assertEqual(clip.samples,800)
        self.assertEqual(clip.peak,1234)
        result=self.robot.audio.play(clip)
        self.assertEqual(self.wire.written,clip.pcm)
        self.assertEqual(result['bytes'],1600)
        self.assertTrue(all(r['args']['bytes']<=768 for r in self.wire.requests if r['op']=='audio.read'))
        self.assertTrue(all(len(base64.b64decode(r['args']['data']))<=768 for r in self.wire.requests if r['op']=='audio.write'))
        self.assertFalse(self.wire.recording or self.wire.playing)

    def test_record_while_stops_at_release_or_sample_limit(self):
        self.robot.audio.set()
        self.robot.start()
        pressed = iter([True, True, False])
        clip = self.robot.audio.record_while(lambda: next(pressed), max_seconds=1)
        self.assertEqual(len(clip.pcm), 2 * 768)
        self.assertFalse(self.wire.recording)
        capped = self.robot.audio.record_while(lambda: True, max_seconds=.05)
        self.assertEqual(capped.samples, 800)
        self.assertFalse(self.wire.recording)
        self.assertIsNone(self.robot.audio.record_while(lambda: False))
        self.assertFalse(self.wire.recording)
        self.assertEqual(self.wire.requests[-1]["op"], "audio.record.end")

    def test_record_while_releases_capture_when_reading_button_fails(self):
        self.robot.audio.set()
        self.robot.start()

        def failed_read():
            raise OSError("button disconnected")

        with self.assertRaisesRegex(OSError, "button disconnected"):
            self.robot.audio.record_while(failed_read)
        self.assertFalse(self.wire.recording)
        self.assertEqual(self.wire.requests[-1]["op"], "audio.stop")

    def test_failure_stops_audio_without_replay_or_replacing_the_error(self):
        self.robot.audio.set();self.robot.start();self.wire.fail_op='audio.write'
        with self.assertRaisesRegex(DeviceError,'audio failed'):self.robot.audio.play(AudioClip(b'\0\0'*1000))
        self.assertEqual(sum(r['op']=='audio.write' for r in self.wire.requests),1)
        self.assertEqual(self.wire.requests[-1]['op'],'audio.stop')
        self.wire.fail_op='audio.read'
        with self.assertRaises(DeviceError):self.robot.audio.record(.05)
        self.assertEqual(self.wire.requests[-1]['op'],'audio.stop')

    def test_inconsistent_read_offset_is_a_protocol_failure_with_cleanup(self):
        original=self.wire.mutate
        def corrupt(request,result):
            result=original(request,result)
            if request['op']=='audio.read':result['data']['offset']+=2
            return result
        self.wire.mutate=corrupt
        with self.assertRaises(ProtocolError):self.robot.audio.record(.05)
        self.assertEqual(self.wire.requests[-1]['op'],'audio.stop')

    def test_invalid_local_args_do_not_change_hardware(self):
        for args in ({'bclk':True},{'ws':42},{'din':-1,'dout':-1},{'volume':101},{'mic_channel':'center'}):
            with self.subTest(args=args):
                count=len(self.wire.requests)
                with self.assertRaises(ValueError):self.robot.audio.set(**args)
                self.assertEqual(len(self.wire.requests),count)
        for seconds in (0,True,float('inf'),31):
            with self.assertRaises(ValueError):self.robot.audio.record(seconds)

    def test_digital_analog_and_pwm_have_distinct_entry_points(self):
        self.robot.digital.set(12,'output');self.robot.digital.write(12,1)
        self.robot.analog.set(1);self.assertEqual(self.robot.analog.read(1),2048)
        self.robot.pwm.set(13);self.robot.pwm.write(13,20)
        count=len(self.wire.requests)
        with self.assertRaises(UnsupportedCapability):self.robot.analog.write(1,.5)
        with self.assertRaises(ValueError):self.robot.analog.set(21)
        with self.assertRaises(ValueError):self.robot.digital.set(12,'pwm')
        self.assertEqual(len(self.wire.requests),count)


@unittest.skipUnless(os.environ.get('AI_MAKER_NATIVE'),'requires new native core')
class AudioNativeTests(unittest.TestCase):
    def test_actual_core_capture_playback_and_pin_ownership(self):
        wire=ProcessTransport(os.environ['AI_MAKER_NATIVE']);self.addCleanup(wire.close)
        with Robot(transport=wire,heartbeat_interval=None) as robot:
            robot.audio.set();robot.start()
            clip=robot.audio.record(.05)
            self.assertEqual(clip.samples,800)
            robot.audio.play(clip)
            status=robot.get_status()['audio']
            self.assertFalse(status['recording'] or status['playing'])
            self.assertTrue(status['active'])
            self.assertTrue(any(p['owner'].startswith('audio') for p in robot.list_pins()))
            robot.audio.unconfigure()
            self.assertFalse(robot.audio.info()['configured'])


if __name__=='__main__':unittest.main()
