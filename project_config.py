"""Project-local classroom configuration. Reading/saving never opens USB."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile

CONFIG_PATH = Path(__file__).resolve().parent / 'config' / 'hardware.json'
PANELS = ('st7735s_128x160', 'st7789_240x320', 'st7789_240x240')
# This is the current conservative N16R8 / RGB48 firmware profile, not every S3.
RESERVED = {0, 3, 19, 20, *range(26, 38), 43, 44, 45, 46, 48}


def _keys(value, names, location):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError(f'{location}字段须为：{names}')


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}须为{low}～{high}整数')


def _pin(value, label):
    _integer(value, 0, 48, label)
    if not (value <= 21 or value >= 26) or value in RESERVED:
        raise ValueError(f'{label}: GPIO{value}在当前板级固件不可自由分配')


def validate_config(config):
    _keys(config, 'schema_version connection pins servo display', '配置')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('schema_version须为1')
    c, p, s, d = (config[k] for k in ('connection','pins','servo','display'))
    _keys(c, 'port', 'connection')
    if not isinstance(c['port'], str) or not c['port'].strip() or len(c['port']) > 128 or any(ord(x)<32 for x in c['port']):
        raise ValueError('port须为AUTO或实际串口名，例如COM5')
    if c['port'] != c['port'].strip():
        raise ValueError('port首尾不能包含空格')
    _keys(p, 'led button adc pwm', 'pins')
    for key,value in p.items(): _pin(value, f'pins.{key}')
    if not 1 <= p['adc'] <= 20:
        raise ValueError('当前板ADC应选择1～20中的可用引脚')
    _keys(s, 'name pin min_angle max_angle min_pulse_us max_pulse_us', 'servo')
    if not isinstance(s['name'], str) or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}',s['name']) is None:
        raise ValueError('servo.name须以字母开头，使用字母数字下划线，最长24字符')
    _pin(s['pin'], 'servo.pin')
    for k in ('min_angle','max_angle'): _integer(s[k],0,180,f'servo.{k}')
    for k in ('min_pulse_us','max_pulse_us'): _integer(s[k],500,2500,f'servo.{k}')
    if s['min_angle'] >= s['max_angle'] or s['min_pulse_us'] >= s['max_pulse_us']:
        raise ValueError('舵机角度、脉宽上下限须严格递增')
    _keys(d, 'panel sck mosi cs dc rst backlight rotation invert brightness', 'display')
    if d['panel'] not in PANELS: raise ValueError('请选择已支持的屏幕型号')
    signals = [d[k] for k in ('sck','mosi','cs','dc','rst')]
    for k in ('sck','mosi','cs','dc','rst'): _pin(d[k],f'display.{k}')
    _integer(d['backlight'],-1,48,'display.backlight')
    if d['backlight'] != -1:
        _pin(d['backlight'],'display.backlight');signals.append(d['backlight'])
    if len(signals) != len(set(signals)): raise ValueError('屏幕信号引脚不能重复')
    if s['pin'] in signals: raise ValueError('舵机信号与屏幕引脚冲突')
    _integer(d['rotation'],0,3,'display.rotation')
    if type(d['invert']) is not bool: raise ValueError('display.invert须为true或false')
    _integer(d['brightness'],0,100,'display.brightness')
    if d['backlight'] == -1 and d['brightness'] != 100:
        raise ValueError('无GPIO背光时brightness必须为100')
    return copy.deepcopy(config)


def _unique(pairs):
    result = {}
    for k,v in pairs:
        if k in result: raise ValueError(f'配置存在重复字段：{k}')
        result[k] = v
    return result


def load_config(path=CONFIG_PATH):
    path=Path(path)
    try:
        with path.open('rb') as source: raw=source.read(65537)
        if len(raw)>65536: raise ValueError('配置文件不能超过64KiB')
        return validate_config(json.loads(raw.decode('utf-8-sig'),object_pairs_hook=_unique))
    except (ValueError, UnicodeError, OSError, RecursionError) as error:
        raise ValueError(f'配置文件 {path}：{error}') from error


def _atomic_write(path, data):
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as out:
            temporary=Path(out.name);out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def save_config(config, path=CONFIG_PATH):
    config=validate_config(config)
    path=Path(path)
    data=(json.dumps(config,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): _atomic_write(path.with_suffix(path.suffix+'.bak'),path.read_bytes())
    _atomic_write(path,data)


def pin_warnings(config):
    """These experiment presets may share pins; they are not all auto-enabled."""
    reserved_by_display={config['display'][k] for k in ('sck','mosi','cs','dc','rst','backlight')}
    messages=[]
    for name,pin in config['pins'].items():
        if pin in reserved_by_display or pin==config['servo']['pin']:
            messages.append(f'{name}=GPIO{pin}与保存的屏幕/舵机映射可能冲突，运行前检查list_pins()')
    if config['pins']['button']==config['pins']['led']:
        messages.append('按钮与LED使用同一个引脚，按钮控制LED示例需要不同引脚')
    return messages
