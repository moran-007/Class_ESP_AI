"""Bounded offline device flows, not an arbitrary Python serializer.

Constructing Program never opens USB, accesses files or evaluates source code.
Only the documented instruction whitelist can be saved to the teaching firmware.
"""
from __future__ import annotations

import copy
import json
import math
import re

from .errors import ProtocolError, UnsupportedCapability

MAX_PROGRAM_BYTES = 3072
MAX_PROGRAM_STEPS = 64
MAX_CONDITION_DEPTH = 4
_COLORS = {'black': 0, 'white': 65535, 'red': 63488, 'green': 2016,
           'blue': 31, 'yellow': 65504, 'cyan': 2047, 'magenta': 63519}
_OPERATORS = ('<', '<=', '==', '!=', '>=', '>')
_INPUTS = ('input', 'input_pullup', 'input_pulldown')


def _int(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}须为{low}～{high}整数')
    return value


def _pin(value, adc=False):
    _int(value, 'pin', 0, 48)
    if value in (0, 3, 19, 20, 43, 44, 45, 46) or 22 <= value <= 37:
        raise ValueError('该GPIO在当前S3教学配置中不存在或保留')
    # RGB38/RGB48 variants reserve different pins; the actual firmware remains
    # authoritative for its selected RGB pin, just as for existing live APIs.
    if adc and not 1 <= value <= 20:
        raise ValueError('analog只接受ADC候选GPIO1～20')
    return value


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}', value):
        raise ValueError('设备名须以ASCII字母开头，字母/数字/下划线，最多24字节')
    return value


def _fields(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError(f'{label}字段须精确为{", ".join(names)}')


def _color(value):
    if isinstance(value, str):
        if value not in _COLORS: raise ValueError('未知屏幕颜色')
        return _COLORS[value]
    if type(value) is tuple and len(value) == 3:
        r, g, b = (_int(n, 'RGB', 0, 255) for n in value)
        return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)
    return _int(value, 'RGB565', 0, 65535)


def _text(value):
    if not isinstance(value, str): raise ValueError('text须为字符串')
    try: size = len(value.encode('utf-8'))
    except UnicodeError: raise ValueError('text须为有效UTF8') from None
    if not 1 <= size <= 192 or any((ord(c) < 32 and c != '\n') or 127 <= ord(c) <= 159 for c in value):
        raise ValueError('text须为1～192个UTF8字节且不能包含控制字符')


def _encoded(value):
    try: return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError('程序须为有限、无循环引用的JSON模型') from None


def _config(config):
    if type(config) is not dict or set(config) not in ({'schema_version', 'servos'}, {'schema_version', 'servos', 'display'}):
        raise ValueError('config字段不合法')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('config schema_version须为1')
    servos = config['servos']
    if type(servos) is not list or len(servos) > 4: raise ValueError('最多4个舵机')
    occupied, names = set(), {}
    for servo in servos:
        _fields(servo, ('name', 'pin', 'min_angle', 'max_angle', 'min_pulse_us', 'max_pulse_us'), 'servo')
        name, pin = _name(servo['name']), _pin(servo['pin'])
        if name in names or pin in occupied: raise ValueError('舵机名/引脚不得重复')
        for key in ('min_angle', 'max_angle'): _int(servo[key], key, 0, 180)
        for key in ('min_pulse_us', 'max_pulse_us'): _int(servo[key], key, 500, 2500)
        if servo['min_angle'] >= servo['max_angle'] or servo['min_pulse_us'] >= servo['max_pulse_us']:
            raise ValueError('角度和脉宽范围必须严格递增')
        names[name] = servo
        occupied.add(pin)
    width = height = 0
    if 'display' in config:
        d = config['display']
        _fields(d, ('panel', 'sck', 'mosi', 'cs', 'dc', 'rst', 'backlight', 'rotation', 'invert', 'brightness'), 'display')
        sizes = {'st7735s_128x160': (128, 160), 'st7789_240x320': (240, 320), 'st7789_240x240': (240, 240)}
        if type(d['panel']) is not str or d['panel'] not in sizes: raise ValueError('未知屏幕型号')
        width, height = sizes[d['panel']]
        for key in ('sck', 'mosi', 'cs', 'dc', 'rst', 'backlight'):
            pin = d[key]
            if key == 'backlight' and type(pin) is int and pin == -1: continue
            _pin(pin)
            if pin in occupied: raise ValueError('外设信号引脚重复')
            occupied.add(pin)
        _int(d['rotation'], 'rotation', 0, 3)
        if d['rotation'] % 2: width, height = height, width
        if type(d['invert']) is not bool: raise ValueError('invert须为bool')
        _int(d['brightness'], 'brightness', 0, 100)
        if d['backlight'] == -1 and d['brightness'] != 100: raise ValueError('无GPIO背光时亮度须为100')
    return occupied, names, width, height


def _validate(project):
    _fields(project, ('schema_version', 'config', 'steps'), 'program')
    if type(project['schema_version']) is not int or project['schema_version'] != 1:
        raise ValueError('program schema_version须为1')
    occupied, servos, width, height = _config(project['config'])
    count = 0

    def free_pin(pin, adc=False):
        _pin(pin, adc)
        if pin in occupied: raise ValueError('程序GPIO与屏幕/舵机映射冲突')

    def coordinate(value, label, maximum): _int(value, label, 0, maximum - 1)

    def steps(items, depth, required=True):
        nonlocal count
        if type(items) is not list or required and not items:
            raise ValueError('steps/then须为非空数组')
        for index, step in enumerate(items):
            count += 1
            if count > MAX_PROGRAM_STEPS: raise ValueError('程序最多64个步骤（含分支）')
            if type(step) is not dict or type(step.get('op')) is not str: raise ValueError('步骤须含op和args')
            op, args = step['op'], step.get('args')
            if op in ('if.digital', 'if.analog'):
                if set(step) not in ({'op', 'args', 'then'}, {'op', 'args', 'then', 'else'}): raise ValueError('条件字段不合法')
                if depth >= MAX_CONDITION_DEPTH: raise ValueError('条件最多嵌套4层')
                _fields(args, ('pin', 'value') if op == 'if.digital' else ('pin', 'operator', 'value'), op)
                free_pin(args['pin'], adc=op == 'if.analog')
                _int(args['value'], 'value', 0, 1 if op == 'if.digital' else 4095)
                if op == 'if.analog' and args['operator'] not in _OPERATORS: raise ValueError('未知比较运算符')
                steps(step['then'], depth + 1)
                if 'else' in step: steps(step['else'], depth + 1, False)
                continue
            _fields(step, ('op', 'args'), 'step')
            if op == 'wait':
                _fields(args, ('ms',), op); _int(args['ms'], 'ms', 1, 60000)
            elif op == 'led.set':
                _fields(args, ('red', 'green', 'blue'), op)
                for key in args: _int(args[key], key, 0, 32)
            elif op in ('led.off', 'display.begin', 'display.release'):
                _fields(args, (), op)
                if op.startswith('display.') and not width: raise ValueError('先配置屏幕')
            elif op in ('gpio.setup', 'gpio.write', 'gpio.release', 'pwm.write'):
                extra = {'gpio.setup': ('mode',), 'gpio.write': ('value',), 'gpio.release': (), 'pwm.write': ('duty',)}[op]
                _fields(args, ('pin',) + extra, op)
                free_pin(args['pin'])
                if op == 'gpio.setup' and args['mode'] not in _INPUTS + ('output', 'pwm'): raise ValueError('未知GPIO模式')
                if op == 'gpio.write': _int(args['value'], 'value', 0, 1)
                if op == 'pwm.write': _int(args['duty'], 'duty', 0, 100)
            elif op in ('servo.move', 'servo.release'):
                _fields(args, ('device', 'angle') if op == 'servo.move' else ('device',), op)
                device = _name(args['device'])
                if device not in servos: raise ValueError('舵机动作须有对应servo.set映射')
                if op == 'servo.move': _int(args['angle'], 'angle', servos[device]['min_angle'], servos[device]['max_angle'])
            elif op.startswith('display.'):
                if not width: raise ValueError('先配置屏幕')
                fields = {'display.fill': ('color',), 'display.text': ('text', 'x', 'y', 'color'),
                          'display.rect': ('x', 'y', 'width', 'height', 'color', 'filled'),
                          'display.line': ('x0', 'y0', 'x1', 'y1', 'color'), 'display.brightness': ('percent',),
                          'display.counter': ('name', 'start', 'step', 'interval_ms', 'x', 'y', 'width', 'height', 'color', 'background')}
                if op not in fields: raise ValueError('固化程序不支持此屏幕操作')
                _fields(args, fields[op], op)
                if 'color' in args: _int(args['color'], 'color', 0, 65535)
                if op == 'display.text': _text(args['text'])
                if op in ('display.text', 'display.rect'):
                    coordinate(args['x'], 'x', width); coordinate(args['y'], 'y', height)
                if op == 'display.rect':
                    _int(args['width'], 'width', 1, width - args['x'])
                    _int(args['height'], 'height', 1, height - args['y'])
                    if type(args['filled']) is not bool: raise ValueError('filled须为bool')
                if op == 'display.line':
                    for key in ('x0', 'x1'): coordinate(args[key], key, width)
                    for key in ('y0', 'y1'): coordinate(args[key], key, height)
                if op == 'display.brightness':
                    _int(args['percent'], 'percent', 0, 100)
                    if project['config']['display']['backlight'] == -1: raise ValueError('无GPIO背光不支持亮度指令')
                if op == 'display.counter':
                    if depth != 0 or index != len(items) - 1:
                        raise ValueError('counter须为主流程最后一步，不能放在条件分支中')
                    _name(args['name'])
                    _int(args['start'], 'start', 0, 2**63 - 1)
                    _int(args['step'], 'step', 1, 2**31 - 1)
                    _int(args['interval_ms'], 'interval_ms', 50, 60000)
                    coordinate(args['x'], 'x', width); coordinate(args['y'], 'y', height)
                    _int(args['width'], 'width', 133, width - args['x'])
                    _int(args['height'], 'height', 16, height - args['y'])
                    _int(args['background'], 'background', 0, 65535)
            else:
                raise ValueError(f'固化程序不支持操作：{op}')
    steps(project['steps'], 0)
    if len(_encoded(project)) > MAX_PROGRAM_BYTES: raise ValueError('固化程序紧凑JSON最多3072个UTF8字节')
    return copy.deepcopy(project)


class Program:
    """Build a serializable hardware flow. Python if/functions are not captured."""
    def __init__(self):
        self._config = {'schema_version': 1, 'servos': []}
        self._steps = []
        self.led = _LED(self)
        self.digital = _Digital(self)
        self.analog = _Analog(self)
        self.pwm = _PWM(self)
        self.servo = _Servo(self)
        self.display = _Display(self)

    def _append(self, op, args):
        self._steps.append({'op': op, 'args': args})
        return self

    def wait(self, seconds):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 60:
            raise ValueError('wait须为大于0且不超过60秒的有限数')
        return self._append('wait', {'ms': max(1, round(seconds * 1000))})

    def _condition(self, op, args, then, otherwise):
        if not isinstance(then, Program) or otherwise is not None and not isinstance(otherwise, Program):
            raise ValueError('then/otherwise须为Program')
        step = {'op': op, 'args': args}
        for key, child in (('then', then), ('else', otherwise)):
            if child is None: continue
            if child._config != {'schema_version': 1, 'servos': []}:
                raise ValueError('条件子流程不能配置屏幕/舵机；请在主Program中配置')
            if key == 'then' and not child._steps: raise ValueError('then不能是空流程')
            step[key] = copy.deepcopy(child._steps)
        self._steps.append(step)
        return self

    def when_digital(self, pin, value, *, then, otherwise=None):
        return self._condition('if.digital', {'pin': _pin(pin), 'value': _int(value, 'value', 0, 1)}, then, otherwise)

    def when_analog(self, pin, operator, value, *, then, otherwise=None):
        if operator not in _OPERATORS: raise ValueError('operator须为<、<=、==、!=、>=、>')
        return self._condition('if.analog', {'pin': _pin(pin, adc=True), 'operator': operator, 'value': _int(value, 'value', 0, 4095)}, then, otherwise)

    def to_dict(self):
        return _validate({'schema_version': 1, 'config': self._config, 'steps': self._steps})

    @classmethod
    def from_dict(cls, project):
        value = _validate(project)
        result = cls()
        result._config, result._steps = value['config'], value['steps']
        return result


class _LED:
    def __init__(self, program): self._program = program
    def set(self, *, red=0, green=0, blue=0):
        return self._program._append('led.set', {key: _int(value, key, 0, 32) for key, value in (('red', red), ('green', green), ('blue', blue))})
    def color(self, name, brightness=16):
        colors = {'red': (1,0,0), 'green': (0,1,0), 'blue': (0,0,1), 'yellow': (1,1,0), 'white': (1,1,1), 'off': (0,0,0)}
        if type(name) is not str or name not in colors: raise ValueError('未知板载RGB命名颜色')
        _int(brightness, 'brightness', 0, 32)
        r, g, b = colors[name]
        return self.set(red=r*brightness, green=g*brightness, blue=b*brightness)
    def off(self): return self._program._append('led.off', {})


class _Digital:
    def __init__(self, program): self._program = program
    def set(self, pin, mode='input'):
        if mode not in _INPUTS + ('output',): raise ValueError('digital mode不支持PWM')
        return self._program._append('gpio.setup', {'pin': _pin(pin), 'mode': mode})
    def write(self, pin, value): return self._program._append('gpio.write', {'pin': _pin(pin), 'value': _int(value, 'value', 0, 1)})
    def release(self, pin): return self._program._append('gpio.release', {'pin': _pin(pin)})


class _Analog:
    def __init__(self, program): self._program = program
    def set(self, pin): return self._program._append('gpio.setup', {'pin': _pin(pin, adc=True), 'mode': 'input'})


class _PWM:
    def __init__(self, program): self._program = program
    def set(self, pin): return self._program._append('gpio.setup', {'pin': _pin(pin), 'mode': 'pwm'})
    def write(self, pin, duty): return self._program._append('pwm.write', {'pin': _pin(pin), 'duty': _int(duty, 'duty', 0, 100)})


class _Servo:
    def __init__(self, program): self._program = program
    def set(self, pin, *, name='test', min_angle=30, max_angle=150, min_pulse_us=1000, max_pulse_us=2000):
        item = dict(name=_name(name), pin=_pin(pin), min_angle=_int(min_angle, 'min_angle', 0, 180),
                    max_angle=_int(max_angle, 'max_angle', 0, 180), min_pulse_us=_int(min_pulse_us, 'min_pulse_us', 500, 2500),
                    max_pulse_us=_int(max_pulse_us, 'max_pulse_us', 500, 2500))
        if min_angle >= max_angle or min_pulse_us >= max_pulse_us: raise ValueError('范围必须严格递增')
        next_config = copy.deepcopy(self._program._config)
        next_config['servos'] = [s for s in next_config['servos'] if s['name'] != name] + [item]
        _config(next_config)
        self._program._config = next_config
        return self._program
    def move(self, device, angle): return self._program._append('servo.move', {'device': _name(device), 'angle': _int(angle, 'angle', 0, 180)})
    def release(self, device): return self._program._append('servo.release', {'device': _name(device)})


class _Display:
    _LABELS = {'sck':'sck','scl':'sck','clk':'sck','sclk':'sck','mosi':'mosi','sda':'mosi','din':'mosi','sdi':'mosi',
               'cs':'cs','ss':'cs','dc':'dc','a0':'dc','rs':'dc','rst':'rst','res':'rst','reset':'rst',
               'backlight':'backlight','blk':'backlight','bl':'backlight'}
    def __init__(self, program): self._program = program
    def set(self, sck=None, mosi=None, cs=None, dc=None, rst=None, backlight=None, *, panel='st7789_240x320', rotation=1, invert=None, brightness=None, **labels):
        values = dict(sck=sck, mosi=mosi, cs=cs, dc=dc, rst=rst, backlight=backlight)
        seen = {k for k,v in values.items() if v is not None}
        for label, pin in labels.items():
            name = self._LABELS.get(label.lower())
            if name is None or name in seen: raise ValueError('未知/重复屏幕丝印；供电脚不能配置GPIO')
            seen.add(name); values[name] = pin
        defaults = dict(sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=-1)
        values = {k: defaults[k] if v is None else v for k,v in values.items()}
        if type(panel) is not str: raise ValueError('panel须为型号字符串')
        d = dict(panel=panel, **values, rotation=rotation,
                 invert=panel.startswith('st7789_') if invert is None else invert,
                 brightness=(100 if values['backlight'] == -1 else 60) if brightness is None else brightness)
        next_config = copy.deepcopy(self._program._config)
        next_config['display'] = d
        _config(next_config)
        self._program._config = next_config
        if not any(s['op'] == 'display.begin' for s in self._program._steps): self._program._append('display.begin', {})
        return self._program
    def fill(self, color='black'): return self._program._append('display.fill', {'color': _color(color)})
    def text(self, text, x=0, y=0, color='white'):
        _text(text)
        return self._program._append('display.text', dict(text=text, x=_int(x,'x',0,319), y=_int(y,'y',0,319), color=_color(color)))
    def rect(self, x, y, width, height, color='white', filled=False):
        if type(filled) is not bool: raise ValueError('filled须为bool')
        return self._program._append('display.rect', dict(x=_int(x,'x',0,319), y=_int(y,'y',0,319), width=_int(width,'width',1,320), height=_int(height,'height',1,320), color=_color(color), filled=filled))
    def line(self, x0, y0, x1, y1, color='white'):
        args = {key: _int(value,key,0,319) for key,value in (('x0',x0),('y0',y0),('x1',x1),('y1',y1))}
        return self._program._append('display.line', dict(**args,color=_color(color)))
    def brightness(self, percent): return self._program._append('display.brightness', {'percent': _int(percent,'percent',0,100)})
    def release(self): return self._program._append('display.release', {})
    def counter(self, *, name='count', start=0, step=1, interval=1,
                x=8, y=48, width=144, height=20, color='white', background='black'):
        """Append one autonomous terminal counter; save with loop=False.

        Counts in device RAM, restarts from start, never writes each tick to
        Flash. Firmware0.7.0 standalone_counter capability is required.
        """
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not .05 <= interval <= 60:
            raise ValueError('interval须为0.05～60秒的有限数')
        return self._program._append('display.counter', dict(
            name=_name(name), start=_int(start, 'start', 0, 2**63 - 1),
            step=_int(step, 'step', 1, 2**31 - 1),
            interval_ms=_int(round(interval * 1000), 'interval_ms', 50, 60000),
            x=_int(x, 'x', 0, 319), y=_int(y, 'y', 0, 319),
            width=_int(width, 'width', 133, 320), height=_int(height, 'height', 16, 320),
            color=_color(color), background=_color(background)))


class Programs:
    """Manage one saved flow. Saving arms reboot startup, never starts outputs."""
    _RECORDABLE = frozenset(('led.set', 'led.off', 'gpio.setup', 'gpio.write', 'gpio.release',
        'pwm.write', 'servo.move', 'servo.release', 'display.begin', 'display.fill',
        'display.text', 'display.rect', 'display.line', 'display.brightness', 'display.release'))
    _READONLY = frozenset(('device.info', 'device.status', 'config.get', 'pins.list',
        'program.info', 'program.download', 'pages.info', 'audio.info', 'wifi.status',
        'session.heartbeat', 'session.close'))

    def __init__(self, robot):
        self._robot = robot
        self._recording = None
        self._recorded = None
        self._record_error = None
        self._record_count = 0
        self._record_token = 0
        self._record_waiting = False
        self._record_display_started = False
        self._beginning = False

    def _reset_recording(self):
        self._recording = None
        self._recorded = None
        self._record_error = None
        self._record_count = 0
        self._record_waiting = False
        self._record_display_started = False

    def begin(self):
        """Record successful live actions until end; configure/start devices first."""
        self._check()
        with self._robot._lock:
            if self._recording is not None or self._beginning:
                raise ValueError('不能嵌套begin；请先end或cancel')
            if self._robot._closed or self._robot._closing:
                raise ValueError('连接已关闭，不能开始录制')
            self._reset_recording()
            self._record_token += 1
            token = self._record_token
            self._beginning = True
        try:
            config = self._robot.config.get()['config']
            status = self._robot.get_status()
            if status.get('maintenance') is not False:
                raise ValueError('请先完成外设配置并robot.start，再begin录制')
            program = status.get('program', {})
            if program.get('running') or program.get('cleanup_required'):
                raise ValueError('请先停止已运行程序并完成清理，再开始录制')
            _config(config)
            draft = Program()
            draft._config = copy.deepcopy(config)
            with self._robot._lock:
                if self._robot._closed or self._robot._closing or self._robot._fault is not None:
                    raise ValueError('连接已失效，不能开始录制')
                if token != self._record_token or not self._beginning:
                    raise ValueError('begin已被cancel或stop取消')
                self._recording = draft
        finally:
            with self._robot._lock:
                if token == self._record_token:
                    self._beginning = False

    def end(self):
        """Finish recording and return an independent Program; do not save or stop."""
        with self._robot._lock:
            if self._recording is None:
                raise ValueError('没有进行中的录制；请先begin')
            if self._record_waiting:
                raise ValueError('wait尚未完成，不能同时end')
            draft, error, count = self._recording, self._record_error, self._record_count
            if self._robot._closed or self._robot._closing or self._robot._fault is not None:
                error = error or '连接已失效'
            self._reset_recording()
            if error is not None:
                raise ValueError('录制失败，不能固化；请修正后重新begin：' + error)
            if not count:
                raise ValueError('录制为空；请在begin/end之间执行支持的动作')
            value = draft.to_dict()
            self._recorded = Program.from_dict(value)
            return Program.from_dict(value)

    def cancel(self):
        """Discard recording/implicit-save snapshot; do not stop live outputs."""
        with self._robot._lock:
            self._cancel_recording()

    def _cancel_recording(self):
        self._record_token += 1
        self._beginning = False
        self._reset_recording()

    def _record_failure(self, error):
        # Called with Robot's lock. Failed previews cannot become saved success.
        if self._recording is not None and self._record_error is None:
            self._record_error = str(error)

    def _record_candidate(self, op, args):
        candidate = Program()
        candidate._config = copy.deepcopy(self._recording._config)
        candidate._steps = copy.deepcopy(self._recording._steps)
        started = self._record_display_started
        if op.startswith('display.'):
            if op not in ('display.begin', 'display.release') and not started:
                candidate._append('display.begin', {})
                started = True
            if op == 'display.begin': started = True
            elif op == 'display.release': started = False
        candidate._append(op, copy.deepcopy(args))
        candidate.to_dict()  # Whitelist, geometry and bounds before live IO.
        return self._record_token, candidate, started

    def _prepare_record_request(self, op, args):
        """Private lock-held wire hook, returning a candidate only for actions."""
        if op == 'outputs.stop':
            # Keep the existing stop entry point available, including while
            # begin snapshots or a live wait are in progress. It aborts capture.
            if self._recording is not None or self._beginning:
                self._cancel_recording()
            return None
        if op in self._READONLY:
            return None
        if self._beginning:
            raise ValueError('begin正在读取配置快照，请勿并发修改外设')
        if self._recording is None:
            return None
        try:
            if self._record_error is not None:
                raise ValueError('本轮录制已失败；请end或cancel后重新begin')
            if self._record_waiting:
                raise ValueError('录制wait期间不能从其它线程插入动作')
            if op not in self._RECORDABLE:
                raise ValueError('录制不支持' + op + '；先end；动态条件请用Program.when_*')
            return self._record_candidate(op, args)
        except Exception as error:
            self._record_failure(error)
            raise

    def _commit_record_request(self, ticket):
        if ticket is not None and self._recording is not None and ticket[0] == self._record_token:
            self._recording, self._record_display_started = ticket[1], ticket[2]
            self._record_count += 1

    def _prepare_record_wait(self, seconds):
        if self._recording is None or seconds == 0:
            return None
        try:
            if self._record_error is not None or self._record_waiting:
                raise ValueError('本轮录制已失败或wait尚未完成')
            candidate = Program()
            candidate._config = copy.deepcopy(self._recording._config)
            candidate._steps = copy.deepcopy(self._recording._steps)
            candidate.wait(seconds)
            candidate.to_dict()
            self._record_waiting = True
            return self._record_token, candidate, self._record_display_started
        except Exception as error:
            self._record_failure(error)
            raise

    def _finish_record_wait(self, ticket, error):
        if ticket is None or self._recording is None or ticket[0] != self._record_token:
            return
        self._record_waiting = False
        if error is not None:
            self._record_failure(error)
        elif self._record_error is None:
            self._commit_record_request(ticket)
    def _check(self):
        if self._robot._info.get('capabilities', {}).get('standalone_program') is not True:
            raise UnsupportedCapability('当前固件不支持固化流程；请使用ai-maker-s3 V0.6.0或以上')
    def _mutate(self, op, args=None):
        self._check()
        with self._robot._lock:
            if self._recording is not None or self._beginning:
                raise ValueError('请先end或cancel录制，再修改固化程序')
        self._robot.maintenance.enter()
        result = self._robot._request(op, args or {})
        self._robot.maintenance.exit()
        return result
    def info(self):
        self._check()
        return self._robot._request('program.info')
    def download(self):
        self._check()
        result = self._robot._request('program.download')
        if type(result.get('enabled')) is not bool or type(result.get('loop')) is not bool:
            raise ProtocolError('固化程序下载元数据无效')
        try: value = Program.from_dict(result.get('program')).to_dict()
        except (ValueError, TypeError): raise ProtocolError('固化程序下载模型无效') from None
        return {**result, 'program': value}
    def save(self, program=None, *, loop=False, autostart=False):
        with self._robot._lock:
            if self._recording is not None or self._beginning:
                raise ValueError('请先end录制，再save固化')
            if program is None:
                if self._recorded is None:
                    raise ValueError('没有成功end的录制；请先begin/end或传入Program')
                program = Program.from_dict(self._recorded.to_dict())
        if not isinstance(program, Program): raise ValueError('save须传Program；不能序列化任意Python函数')
        if type(loop) is not bool or type(autostart) is not bool: raise ValueError('loop/autostart须为bool')
        value = program.to_dict()
        if value['steps'][-1]['op'] == 'display.counter':
            if loop:
                raise ValueError('counter本身持续运行，请使用loop=False，不要循环重新初始化')
            if self._robot._info.get('capabilities', {}).get('standalone_counter') is not True:
                raise UnsupportedCapability('该固件不支持板端计数显示，请使用声明standalone_counter的0.7.0或以上固件')
        return self._mutate('program.save', {'program': value, 'loop': loop, 'autostart': autostart})
    def enable(self): return self._mutate('program.enable')
    def disable(self): return self._mutate('program.disable')
    def clear(self): return self._mutate('program.clear')
    def start(self):
        self._check()
        return self._robot._request('program.start')
    def stop(self):
        self._check()
        return self._robot._request('program.stop')
