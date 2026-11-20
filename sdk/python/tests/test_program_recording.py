"""Record successful live SDK calls; no serial ports or real hardware."""
import copy
import threading
import time
import unittest
from unittest.mock import patch

from ai_robot import Robot, Program, DeviceError, RequestTimeout, UnsupportedCapability, ConnectionLostError
from test_sdk import ScriptTransport, response


class RecordingTests(unittest.TestCase):
    def setUp(self):
        def mutate(request, reply):
            if request['op'] == 'device.info':
                reply['data']['capabilities'].update(standalone_program=True, display=True)
            if request['op'] == 'device.status':
                reply['data'].update(display={'configured': True, 'active': True}, program={'running': False, 'cleanup_required': False})
            return reply
        self.wire = ScriptTransport(mutate=mutate)
        self.robot = Robot(transport=self.wire, heartbeat_interval=None, timeout=.02)
        self.addCleanup(self.robot.close)
        self.robot.display.set(panel='st7735s_128x160', backlight=16)
        self.robot.start()

    def test_begin_preview_clear_wait_end_and_implicit_save(self):
        start = len(self.wire.requests)
        self.robot.program.begin()
        self.robot.display.clear()
        self.robot.display.text('你好', x=8, y=8)
        before_wait = time.monotonic()
        self.robot.wait(.015)
        self.assertGreaterEqual(time.monotonic() - before_wait, .01)
        flow = self.robot.program.end()
        steps = flow.to_dict()['steps']
        self.assertEqual([s['op'] for s in steps], ['display.begin', 'display.fill', 'display.text', 'wait'])
        self.assertEqual(steps[-1]['args'], {'ms': 15})
        wire_ops = [r['op'] for r in self.wire.requests[start:]]
        self.assertEqual(wire_ops, ['config.get', 'device.status', 'display.fill', 'display.text'])
        flow.led.off()  # Returned object cannot mutate the implicit save snapshot.
        self.robot.program.save(loop=True, autostart=True)
        saved = [r for r in self.wire.requests if r['op'] == 'program.save'][-1]['args']
        self.assertEqual(saved['program']['steps'], steps)
        self.assertTrue(saved['loop'])

    def test_info_heartbeat_do_not_capture_and_config_is_snapshot(self):
        self.robot.program.begin()
        self.robot._request('session.heartbeat')
        self.robot.get_status()
        self.robot.get_info()
        self.robot.program.info()
        self.robot.led.color('green')
        flow = self.robot.program.end()
        self.assertEqual([s['op'] for s in flow.to_dict()['steps']], ['led.set'])
        self.wire.config['display']['sck'] = 18
        self.assertEqual(flow.to_dict()['config']['display']['sck'], 4)

    def test_nested_empty_end_cancel_and_implicit_state(self):
        with self.assertRaises(ValueError): self.robot.program.end()
        with self.assertRaises(ValueError): self.robot.program.save()
        self.robot.program.begin()
        with self.assertRaises(ValueError): self.robot.program.begin()
        with self.assertRaises(ValueError): self.robot.program.end()
        self.robot.program.begin()
        self.robot.led.off()
        self.robot.program.end()
        self.robot.program.begin()  # New capture invalidates previous implicit save.
        self.robot.program.cancel()
        with self.assertRaises(ValueError): self.robot.program.save()
        self.robot.program.begin()
        self.robot.led.off()
        with self.assertRaises(ValueError): self.robot.program.save()
        self.robot.program.cancel()

    def test_unsupported_effects_and_pin_reads_reject_before_wire(self):
        for op, args in [('audio.stop', {}), ('pages.show', {'id': 'home'}), ('gpio.read', {'pin': 2}),
                         ('adc.read', {'pin': 1}), ('display.bitmap', {}), ('maintenance.enter', {})]:
            self.robot.program.begin()
            count = len(self.wire.requests)
            with self.assertRaises(ValueError): self.robot._request(op, args)
            self.assertEqual(len(self.wire.requests), count)
            with self.assertRaises(ValueError): self.robot.program.end()

    def test_bounds_before_preview_and_no_success_after_device_failure(self):
        self.robot.program.begin()
        count = len(self.wire.requests)
        with self.assertRaises(ValueError): self.robot.display.rect(159, 127, 2, 1)
        self.assertEqual(len(self.wire.requests), count)
        with self.assertRaises(ValueError): self.robot.program.end()
        self.robot.program.begin()
        original = self.wire.mutate
        def fail(request, reply):
            if request['op'] == 'display.fill': return response(request, code='HARDWARE_ERROR')
            return original(request, reply)
        self.wire.mutate = fail
        with self.assertRaises(DeviceError): self.robot.display.clear()
        with self.assertRaises(ValueError): self.robot.program.end()
        with self.assertRaises(ValueError): self.robot.program.save()

    def test_timeout_and_wait_interruption_cannot_be_saved(self):
        self.robot.program.begin()
        original = self.wire.mutate
        self.wire.mutate = lambda req, reply: None if req['op'] == 'led.off' else original(req, reply)
        with self.assertRaises(RequestTimeout): self.robot.led.off()
        with self.assertRaises(ValueError): self.robot.program.end()
        self.wire.mutate = original
        self.robot.program.begin()
        with patch.object(self.robot._stop, 'wait', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.robot.wait(.1)
        with self.assertRaises(ValueError): self.robot.program.end()

    def test_capture_bounds_and_failed_new_capture_never_save_old_result(self):
        self.robot.program.begin()
        self.robot.led.off()
        self.robot.program.end()
        self.robot.program.begin()
        for _ in range(64): self.robot.led.off()
        count = len(self.wire.requests)
        with self.assertRaises(ValueError): self.robot.led.off()
        self.assertEqual(count, len(self.wire.requests))
        with self.assertRaises(ValueError): self.robot.program.end()
        with self.assertRaises(ValueError): self.robot.program.save()

    def test_old_capability_and_maintenance_refuse_begin(self):
        self.robot._info['capabilities']['standalone_program'] = False
        count = len(self.wire.requests)
        with self.assertRaises(UnsupportedCapability): self.robot.program.begin()
        self.assertEqual(count, len(self.wire.requests))
        self.robot._info['capabilities']['standalone_program'] = True
        self.robot.maintenance.enter()
        with self.assertRaises(ValueError): self.robot.program.begin()
        self.robot.maintenance.exit()
        self.robot.program.begin()
        self.robot.led.off()
        self.robot.close()
        with self.assertRaises(ValueError): self.robot.program.end()
        self.assertTrue(self.wire.closed)
        self.assertEqual(self.wire.requests[-1]['op'], 'session.close')

    def test_explicit_save_still_works_without_recording(self):
        flow = Program()
        flow.led.off()
        self.robot.program.save(flow)
        self.assertEqual(self.wire.requests[-2]['args']['program'], flow.to_dict())

    def test_wait_is_atomic_for_recording_but_queries_remain_available(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def pause(timeout):
            entered.set()
            release.wait(1)
            return False
        def wait():
            try: self.robot.wait(.015)
            except BaseException as error: errors.append(error)
        self.robot.program.begin()
        with patch.object(self.robot._stop, 'wait', side_effect=pause):
            thread = threading.Thread(target=wait)
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                self.robot.get_status()
                with self.assertRaises(ValueError): self.robot.program.end()
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.robot.program.end().to_dict()['steps'], [{'op': 'wait', 'args': {'ms': 15}}])

    def test_cancelled_wait_does_not_resurrect_a_draft_after_close(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def pause(timeout):
            entered.set()
            release.wait(1)
            return False
        def wait():
            try: self.robot.wait(.1)
            except BaseException as error: errors.append(error)
        self.robot.program.begin()
        with patch.object(self.robot._stop, 'wait', side_effect=pause):
            thread = threading.Thread(target=wait)
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                self.robot.close()
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ConnectionLostError)
        with self.assertRaises(ValueError): self.robot.program.end()

    def test_unicode_size_limit_rejects_before_display_wire(self):
        self.robot.program.begin()
        for _ in range(20):
            count = len(self.wire.requests)
            try: self.robot.display.text('中' * 60)
            except ValueError:
                self.assertEqual(len(self.wire.requests), count)
                break
        else: self.fail('3072-byte limit must reject this flow')
        with self.assertRaises(ValueError): self.robot.program.end()

    def test_stop_always_sends_stop_and_aborts_only_active_capture(self):
        self.robot.program.begin()
        self.robot.led.color('red')
        self.robot.stop()
        self.assertEqual(self.wire.requests[-1]['op'], 'outputs.stop')
        with self.assertRaises(ValueError): self.robot.program.end()
        with self.assertRaises(ValueError): self.robot.program.save()
        self.robot.program.begin()
        self.robot.led.off()
        flow = self.robot.program.end()
        self.robot.stop()  # A completed end snapshot remains usable.
        self.robot.program.save()
        self.assertEqual(self.wire.requests[-2]['args']['program'], flow.to_dict())

    def test_cancel_during_begin_snapshot_cannot_resurrect_capture(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        real_status = self.robot.get_status
        def blocked_status():
            entered.set()
            release.wait(1)
            return real_status()
        def begin():
            try: self.robot.program.begin()
            except BaseException as error: errors.append(error)
        with patch.object(self.robot, 'get_status', side_effect=blocked_status):
            thread = threading.Thread(target=begin)
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                self.robot.program.cancel()
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        with self.assertRaises(ValueError): self.robot.program.end()
        self.robot.program.begin()
        self.robot.led.off()
        self.robot.program.end()


if __name__ == '__main__': unittest.main()
