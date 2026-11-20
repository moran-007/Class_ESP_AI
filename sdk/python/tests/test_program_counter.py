"""Autonomous display counter models and capability gates; no serial IO."""
import copy
import unittest

from ai_robot import Program, Robot, UnsupportedCapability
from test_sdk import ScriptTransport


def counter_program(**options):
    flow = Program()
    flow.display.set(panel='st7735s_128x160', backlight=16)
    flow.display.fill('black')
    flow.display.counter(**options)
    return flow


class CounterModelTests(unittest.TestCase):
    def test_defaults_int64_and_roundtrip(self):
        flow = counter_program()
        model = flow.to_dict()
        self.assertEqual(model['steps'][-1], {'op': 'display.counter', 'args': {
            'name': 'count', 'start': 0, 'step': 1, 'interval_ms': 1000,
            'x': 8, 'y': 48, 'width': 144, 'height': 20,
            'color': 65535, 'background': 0}})
        self.assertEqual(Program.from_dict(model).to_dict(), model)
        args = counter_program(start=2**63-1, step=2**31-1, interval=.05,
            color=(255, 0, 0), background='blue').to_dict()['steps'][-1]['args']
        self.assertEqual(args['start'], 2**63-1)
        self.assertEqual(args['interval_ms'], 50)
        self.assertEqual(args['color'], 63488)
        self.assertEqual(args['background'], 31)
        exact = counter_program(width=133, height=16, interval=60).to_dict()['steps'][-1]['args']
        self.assertEqual((exact['width'], exact['height'], exact['interval_ms']), (133, 16, 60000))

    def test_invalid_arguments_and_geometry(self):
        for options in ({'name': '1count'}, {'name': 'a'*25}, {'start': True},
                {'start': 1.0}, {'start': -1}, {'start': 2**63},
                {'step': 0}, {'step': True}, {'step': 2**31},
                {'interval': True}, {'interval': .049}, {'interval': 61},
                {'interval': 10**1000},
                {'interval': float('nan')}, {'interval': float('inf')},
                {'width': 132}, {'height': 15}, {'x': -1}, {'color': 65536}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                counter_program(**options).to_dict()
        for options in ({'x': 17}, {'y': 109}, {'width': 160}, {'height': 128}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                counter_program(**options).to_dict()
        flow = Program()
        flow.display.counter()
        with self.assertRaises(ValueError): flow.to_dict()

    def test_terminal_unique_root_rule(self):
        flow = counter_program()
        flow.wait(1)
        with self.assertRaises(ValueError): flow.to_dict()
        flow = counter_program()
        flow.display.counter(name='second')
        with self.assertRaises(ValueError): flow.to_dict()
        root = counter_program().to_dict()
        counter = root['steps'].pop()
        root['steps'].append({'op': 'if.digital', 'args': {'pin': 2, 'value': 0}, 'then': [counter]})
        with self.assertRaises(ValueError): Program.from_dict(root)

    def test_downloaded_models_reject_types_and_unknown_fields(self):
        model = counter_program().to_dict()
        for key, value in (('start', '1'), ('start', True), ('interval_ms', 49), ('interval_ms', 1000.0),
                           ('step', 0), ('width', 132), ('background', False)):
            invalid = copy.deepcopy(model)
            invalid['steps'][-1]['args'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                Program.from_dict(invalid)
        invalid = copy.deepcopy(model)
        invalid['steps'][-1]['args']['unknown'] = 1
        with self.assertRaises(ValueError): Program.from_dict(invalid)


class CounterSDKTests(unittest.TestCase):
    def setUp(self):
        def mutate(request, reply):
            if request['op'] == 'device.info':
                reply['data']['capabilities'].update(standalone_program=True, standalone_counter=True, display=True)
            if request['op'] == 'device.status':
                reply['data'].update(display={'configured': True, 'active': True},
                    program={'running': False, 'cleanup_required': False})
            return reply
        self.wire = ScriptTransport(mutate=mutate)
        self.robot = Robot(transport=self.wire, heartbeat_interval=None)
        self.addCleanup(self.robot.close)

    def test_loop_and_old_capability_reject_before_any_io(self):
        flow = counter_program()
        count = len(self.wire.requests)
        with self.assertRaises(ValueError): self.robot.program.save(flow, loop=True)
        self.assertEqual(len(self.wire.requests), count)
        self.robot._info['capabilities']['standalone_counter'] = False
        with self.assertRaises(UnsupportedCapability): self.robot.program.save(flow, autostart=True)
        self.assertEqual(len(self.wire.requests), count)
        ordinary = Program()
        ordinary.led.off()
        self.robot.program.save(ordinary, loop=True)
        self.assertEqual(self.wire.requests[-2]['op'], 'program.save')

    def test_supported_counter_body_has_single_maintenance_sequence(self):
        flow = counter_program(start=12, interval=1)
        self.robot.program.save(flow, autostart=True)
        sequence = self.wire.requests[-3:]
        self.assertEqual([r['op'] for r in sequence], ['maintenance.enter', 'program.save', 'maintenance.exit'])
        self.assertEqual(sequence[1]['args'], {'program': flow.to_dict(), 'loop': False, 'autostart': True})

    def test_recorded_background_can_append_counter_without_changing_implicit_copy(self):
        self.robot.display.set(panel='st7735s_128x160', backlight=16)
        self.robot.start()
        self.robot.program.begin()
        self.robot.display.clear()
        self.robot.display.text('每秒加一', x=8, y=8)
        flow = self.robot.program.end()
        flow.display.counter()
        self.robot.program.save(flow, autostart=True)
        self.assertEqual(self.wire.requests[-2]['args']['program']['steps'][-1]['op'], 'display.counter')
        self.robot._info['capabilities']['standalone_counter'] = False
        self.robot.program.save(loop=True)  # Original successful end snapshot stays ordinary.
        self.assertNotIn('display.counter', [s['op'] for s in self.wire.requests[-2]['args']['program']['steps']])


if __name__ == '__main__':
    unittest.main()
