"""Configuration loading/saving must not open USB or change hardware."""
import copy
import json
import runpy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from project_config import load_config, save_config, validate_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = {'schema_version':1,'connection':{'port':'AUTO'},
            'pins':{'led':12,'button':2,'adc':1,'pwm':12},
            'servo':{'name':'test','pin':14,'min_angle':30,'max_angle':150,'min_pulse_us':1000,'max_pulse_us':2000},
            'display':{'panel':'st7735s_128x160','sck':4,'mosi':5,'cs':15,'dc':7,'rst':6,
                       'backlight':16,'rotation':1,'invert':False,'brightness':60}}

    def test_compatibility_settings_read_the_shared_source(self):
        settings=runpy.run_path(str(ROOT/'tests/quick/settings.py'))
        actual=load_config()
        self.assertEqual(settings['PORT'],actual['connection']['port'])
        self.assertEqual(settings['SCREEN'],actual['display'])

    def test_invalid_pins_types_and_screen_collisions_are_rejected(self):
        for section, key, value in [('pins','led',19),('pins','button',True),('pins','adc',21),
                ('display','cs',4),('servo','pin',4),('display','brightness',101)]:
            with self.subTest(section=section,key=key,value=value):
                invalid=copy.deepcopy(self.config); invalid[section][key]=value
                with self.assertRaises(ValueError): validate_config(invalid)
        invalid=copy.deepcopy(self.config);invalid['display']['backlight']=-1;invalid['display']['brightness']=60
        with self.assertRaises(ValueError):validate_config(invalid)

    def test_save_roundtrip_backup_and_invalid_save_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'hardware.json'
            save_config(self.config,path)
            changed=copy.deepcopy(self.config);changed['connection']['port']='COM15'
            save_config(changed,path)
            self.assertEqual(load_config(path),changed)
            self.assertEqual(json.loads(path.with_suffix('.json.bak').read_text(encoding='utf-8')), self.config)
            changed['servo']['min_angle']=180
            with self.assertRaises(ValueError):save_config(changed,path)
            self.assertEqual(load_config(path)['connection']['port'],'COM15')

    def test_loading_does_not_open_usb_and_malformed_json_is_not_defaulted(self):
        with patch('serial.Serial') as serial:
            load_config()
            serial.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'hardware.json';p.write_text('{invalid',encoding='utf-8')
            with self.assertRaises(ValueError):load_config(p)


if __name__=='__main__':unittest.main()
