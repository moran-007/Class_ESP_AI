"""示例共用的连接与源码定位；导入本文件不会打开串口。"""

from contextlib import contextmanager
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "sdk" / "python" / "src"))

from ai_robot import Robot, RobotError, RequestTimeout, ProtocolError, DeviceError
from project_config import load_config

_config = None


def _settings():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def __getattr__(name):
    # Legacy shared presets are loaded only when explicitly requested. Inline
    # COM/pin programs do not depend on the optional JSON file being present.
    if name == 'CONFIG': return _settings()
    if name == 'PORT': return _settings()['connection']['port']
    if name in ('PINS','SERVO','SCREEN'):
        return _settings()[{'PINS':'pins','SERVO':'servo','SCREEN':'display'}[name]]
    raise AttributeError(name)


@contextmanager
def connect(port=None):
    """一次连接、一次关闭；异常保留失败退出状态，动作不自动重发。"""
    try:
        with Robot(port=_settings()['connection']['port'] if port is None else port) as robot:
            yield robot
    except KeyboardInterrupt:
        raise SystemExit("已停止，连接已关闭；断连时固件会在租约到期后释放输出。") from None
    except (RobotError, OSError, ModuleNotFoundError) as error:
        if isinstance(error, ModuleNotFoundError):
            hint = "缺少 Python 依赖，请先运行 ai_maker 文件夹的安装脚本。"
        elif isinstance(error, RequestTimeout):
            hint = "某条请求未收到回执，不能据此判断固件不兼容。不要自动重发动作；请检查 USB、固件版本和设备状态。V0.2.0 原生 USB 长请求问题请升级到 V0.2.1 或以上。"
        elif isinstance(error, ProtocolError):
            hint = "请确认已安装 ai-maker-s3 教学固件；旧 AI 固件和常亮白灯诊断固件不能运行这些示例。关闭串口监视器后重新运行。"
        elif isinstance(error, DeviceError):
            hint = {
                "RESOURCE_CONFLICT": "该引脚或通道已被占用。先用 01 查看配置；确认后可用 08 清除全部舵机映射。",
                "PIN_RESERVED": "该引脚由系统占用，请根据 01 的引脚表更换 PIN。",
                "PIN_CAPABILITY_MISMATCH": "引脚能力与当前操作不匹配，请查看 01 的引脚表及 setup 模式。",
                "MAINTENANCE_REQUIRED": "设备处于维护状态。确认接线后显式退出维护；07 或 08 会按各自用途退出维护。",
                "HARDWARE_ERROR": "硬件驱动返回失败，不能确认输出已停止。请查看设备状态，并复位开发板后重新测试。",
            }.get(error.code, "请根据上面的固件错误码检查引脚、配置和设备状态。")
        else:
            hint = "请检查 USB 连接并关闭占用串口的程序；在connect('COM5')中填写实际串口，或使用可选的统一配置。"
        raise SystemExit(f"运行失败：{error}\n{hint}") from None


@contextmanager
def connect_screen(port=None, **display):
    """运行表示已完成接线；保存屏幕映射、退出维护并初始化显示。"""
    mapping = display if display else _settings()['display']
    with connect(port) as robot:
        robot.display.set(**mapping)
        robot.start()
        yield robot
