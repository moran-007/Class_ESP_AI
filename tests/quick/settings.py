"""兼容入口：请在配置硬件窗口或config/hardware.json修改参数。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from project_config import load_config
CONFIG = load_config()
PORT = CONFIG["connection"]["port"]
PINS = CONFIG["pins"]
SERVO = CONFIG["servo"]
SCREEN = CONFIG["display"]
