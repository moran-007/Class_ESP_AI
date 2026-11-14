"""屏幕公共连接兼容入口，统一配置见config/hardware.json。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from classroom import connect_screen
