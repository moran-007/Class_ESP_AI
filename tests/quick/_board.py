"""旧示例兼容入口，统一配置与连接见ai_maker/classroom.py。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from classroom import connect


def __getattr__(name):
    import classroom
    return getattr(classroom, name)
