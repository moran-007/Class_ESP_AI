"""Offline programs and maintenance/upload boundaries; no real serial IO."""
import copy
import unittest

from ai_robot import Program, Robot, DeviceError, UnsupportedCapability
from test_sdk import ScriptTransport


class ProgramTests(unittest.TestCase):
    def test_builder_is_offline_and_snapshots_are_independent(self):
        p = Program()
        p.led.color('red', brightness=8)
        p.wait(0.125)
        p.led.off()
        value = p.to_dict()
        self.assertEqual(value['steps'][1], {'op': 'wait', 'args': {'ms': 125}})
        self.assertEqual(value['config'], {'schema_version': 1, 'servos': []})
        value['steps'].clear()
        self.assertEqual(len(p.to_dict()['steps']), 3)
        self.assertEqual(Program.from_dict(p.to_dict()).to_dict(), p.to_dict())

    def test_mappings_aliases_and_conditional_children(self):
        p = Program()
        p.display.set(panel='st7735s_128x160', SCL=4, SDA=5, CS=15, DC=7, RES=6, BLK=16)
        p.servo.set(pin=14, name='arm')
        p.digital.set(2, 'input_pullup')
        p.analog.set(1)
        yes, no = Program(), Program()
        yes.servo.move('arm', 90)
        no.led.off()
        p.when_digital(2, 0, then=yes, otherwise=no)
        p.when_analog(1, '>=', 2000, then=no)
        p.display.text('你好', x=8, y=8, color=(55, 88, 99))
        value = p.to_dict()
        self.assertEqual(value['steps'][0]['op'], 'display.begin')
        self.assertEqual(value['config']['display']['sck'], 4)
        self.assertEqual(value['config']['servos'][0]['min_pulse_us'], 1000)
        self.assertEqual(value['steps'][3]['then'][0]['args']['device'], 'arm')
        yes.led.color('green')
        self.assertEqual(len(p.to_dict()['steps'][3]['then']), 1)

    def test_limits_unknown_operations_and_config_collisions(self):
        p = Program()
        p.led.off()
        value = p.to_dict()
        for op in ('audio.play', 'python.exec', 'jump', 'gpio.read'):
            invalid = copy.deepcopy(value)
            invalid['steps'][0]['op'] = op
            with self.assertRaises(ValueError): Program.from_dict(invalid)
        for seconds in (0, -1, True, 61, float('nan')):
            with self.assertRaises(ValueError): p.wait(seconds)
        too_many = Program()
        for _ in range(65): too_many.led.off()
        with self.assertRaises(ValueError): too_many.to_dict()
        for _ in range(5):
            outer = Program()
            outer.when_digital(2, 0, then=p)
            p = outer
        with self.assertRaises(ValueError): p.to_dict()
        conflict = Program()
        conflict.servo.set(pin=14)
        conflict.digital.set(14, 'output')
        with self.assertRaises(ValueError): conflict.to_dict()
        oversized = Program()
        oversized.display.set()
        for _ in range(16): oversized.display.text('中' * 60)
        with self.assertRaises(ValueError): oversized.to_dict()

    def test_invalid_numbers_unknown_fields_and_branch_configuration(self):
        p = Program()
        with self.assertRaises(ValueError): p.led.set(red=True)
        with self.assertRaises(ValueError): p.digital.set(pin=19)
        with self.assertRaises(ValueError): p.pwm.write(12, 101)
        branch = Program()
        branch.servo.set(pin=14)
        branch.led.off()
        with self.assertRaises(ValueError): p.when_digital(2, 0, then=branch)
        p.led.off()
        value = p.to_dict()
        value['steps'][0]['args']['surprise'] = 1
        with self.assertRaises(ValueError): Program.from_dict(value)

    def test_config_validation_and_screen_bounds_are_not_deferred_to_hardware(self):
        p = Program()
        with self.assertRaises(ValueError): p.display.set(SCL=4, sck=5)
        with self.assertRaises(ValueError): p.display.set(BLK=16, brightness=True)
        p.display.set(panel='st7735s_128x160', rotation=1)
        p.display.rect(159, 127, 2, 1)
        with self.assertRaises(ValueError): p.to_dict()
        for value in (True, 1.5, '14'):
            with self.assertRaises(ValueError): Program().servo.set(pin=value)
        exact = Program()
        for _ in range(64): exact.led.off()
        self.assertEqual(len(exact.to_dict()['steps']), 64)


class ProgramsSDKTests(unittest.TestCase):
    def setUp(self):
        def mutate(request, result):
            if request['op'] == 'device.info':
                result['data']['capabilities']['standalone_program'] = True
            return result
        self.wire = ScriptTransport(mutate=mutate)
        self.robot = Robot(transport=self.wire, heartbeat_interval=None)
        self.addCleanup(self.robot.close)

    def test_save_and_lifecycle_have_explicit_maintenance_sequence(self):
        p = Program()
        p.led.color('green')
        self.robot.program.save(p, loop=True, autostart=True)
        requests = self.wire.requests[-3:]
        self.assertEqual([r['op'] for r in requests], ['maintenance.enter', 'program.save', 'maintenance.exit'])
        self.assertEqual(requests[1]['args'], {'program': p.to_dict(), 'loop': True, 'autostart': True})
        for action in ('enable', 'disable', 'clear'):
            getattr(self.robot.program, action)()
            self.assertEqual([r['op'] for r in self.wire.requests[-3:]], ['maintenance.enter', 'program.' + action, 'maintenance.exit'])
        for action in ('info', 'start', 'stop'):
            getattr(self.robot.program, action)()
            self.assertEqual(self.wire.requests[-1]['op'], 'program.' + action)

    def test_invalid_program_and_options_have_no_side_effects(self):
        count = len(self.wire.requests)
        with self.assertRaises(ValueError): self.robot.program.save(Program())
        p = Program()
        p.led.off()
        with self.assertRaises(ValueError): self.robot.program.save(p, autostart=1)
        self.assertEqual(len(self.wire.requests), count)

    def test_save_failure_stays_in_maintenance_and_is_not_retried(self):
        def failure(request, result):
            if request['op'] == 'device.info': result['data']['capabilities']['standalone_program'] = True
            if request['op'] == 'program.save':
                result.pop('data', None)
                result.update(ok=False, code='STORAGE_ERROR', message='not committed')
            return result
        self.wire.mutate = failure
        p = Program()
        p.led.off()
        with self.assertRaises(DeviceError): self.robot.program.save(p)
        self.assertTrue(self.wire.maintenance)
        self.assertEqual([r['op'] for r in self.wire.requests].count('program.save'), 1)
        self.assertEqual(self.wire.requests[-1]['op'], 'program.save')

    def test_old_firmware_refuses_before_maintenance(self):
        self.robot._info['capabilities']['standalone_program'] = False
        count = len(self.wire.requests)
        with self.assertRaises(UnsupportedCapability): self.robot.program.info()
        self.assertEqual(len(self.wire.requests), count)

    def test_download_requires_a_valid_model_and_boolean_metadata(self):
        p = Program()
        p.led.color('blue')
        def downloaded(request, result):
            if request['op'] == 'program.download':
                result['data'] = {'program': p.to_dict(), 'enabled': True, 'loop': False}
            return result
        self.wire.mutate = downloaded
        result = self.robot.program.download()
        self.assertEqual(result['program'], p.to_dict())
        self.assertTrue(result['enabled'])
        def invalid(request, result):
            if request['op'] == 'program.download':
                result['data'] = {'program': p.to_dict(), 'enabled': 1, 'loop': False}
            return result
        self.wire.mutate = invalid
        from ai_robot import ProtocolError
        with self.assertRaises(ProtocolError): self.robot.program.download()


if __name__ == '__main__': unittest.main()
