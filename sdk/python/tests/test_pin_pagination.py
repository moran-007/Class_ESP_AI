"""Rich pin capabilities stay below JSONL limits with strict paging."""
import copy
import unittest
from ai_robot import Robot, ProtocolError
from test_sdk import ScriptTransport


PINS=[{'pin':pin,'digital_input':True,'digital_output':True,'analog_input':pin<20,
       'analog_output':False,'pwm_output':True} for pin in range(49) if pin not in (22,23,24,25)]


class PinPaginationTests(unittest.TestCase):
    def robot(self,change=None):
        def mutate(request,result):
            if request['op']=='device.info':result['data']['capabilities']['pin_pagination']=True
            if request['op']=='pins.list':
                offset=request['args']['offset'];end=min(len(PINS),offset+request['args']['limit'])
                result['data']={'offset':offset,'total':len(PINS),'next_offset':end if end<len(PINS) else None,
                                'pins':copy.deepcopy(PINS[offset:end])}
                if change:change(request,result['data'])
            return result
        wire=ScriptTransport(mutate=mutate);robot=Robot(transport=wire,heartbeat_interval=None)
        self.addCleanup(robot.close)
        return robot,wire

    def test_all45_pins_assembled_from_four_bounded_pages(self):
        robot,wire=self.robot()
        self.assertEqual(robot.list_pins(),PINS)
        pages=[r for r in wire.requests if r['op']=='pins.list']
        self.assertEqual([r['args']['offset'] for r in pages],[0,12,24,36])
        self.assertTrue(all(r['args']['limit']==12 for r in pages))

    def test_malformed_page_does_not_retry_or_loop(self):
        def duplicate(request,data):data['pins'][1]['pin']=data['pins'][0]['pin']
        changes=[lambda q,d:d.update(offset=1),lambda q,d:d.update(total=100),
                 lambda q,d:d.update(next_offset=0),lambda q,d:d.update(next_offset=True),
                 lambda q,d:d.update(pins=[]),duplicate,
                 lambda q,d:d['pins'][0].update(analog_output='false')]
        for change in changes:
            with self.subTest(change=change):
                robot,wire=self.robot(change)
                with self.assertRaises(ProtocolError):robot.list_pins()
                self.assertEqual(sum(r['op']=='pins.list' for r in wire.requests),1)

    def test_changed_total_or_nonnull_terminal_offset_is_rejected(self):
        for change in (lambda q,d:d.update(total=44) if q['args']['offset'] else None,
                       lambda q,d:d.update(next_offset=45) if q['args']['offset']==36 else None):
            robot,wire=self.robot(change)
            with self.assertRaises(ProtocolError):robot.list_pins()

    def test_legacy_firmware_still_uses_one_legacy_request(self):
        wire=ScriptTransport()
        with Robot(transport=wire,heartbeat_interval=None) as robot:
            self.assertEqual(robot.list_pins(),[{'pin':12,'output':True}])
        self.assertEqual(next(r for r in wire.requests if r['op']=='pins.list')['args'],{})


if __name__=='__main__':unittest.main()
