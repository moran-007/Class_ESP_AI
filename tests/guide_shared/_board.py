"""新课程共用入口；只导入不连接USB。"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / 'tests' / 'quick'))
from classroom import connect, connect_screen


def __getattr__(name):
    import classroom
    return getattr(classroom, name)
