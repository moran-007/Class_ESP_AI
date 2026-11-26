"""按住接在 GPIO 与 GND 之间的按钮说话，松开后等待 AI 播报。"""
import json
from pathlib import Path

from ai_robot import Robot, RobotError, VoiceError

PORT = "AUTO"  # 只连接一块 USB 开发板时自动选；也可填 "COM5"。
BUTTON_PIN = 2
MAX_SECONDS = 20
AUDIO_PINS = dict(bclk=42, ws=41, din=21, dout=40, sd=39, volume=20)
CONFIG = Path(__file__).resolve().parents[2] / "config" / "ai.local.json"


def load_config():
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        return config["url"], config["device_id"], config["token"]
    except FileNotFoundError:
        raise SystemExit("请复制 config/ai.example.json 为 config/ai.local.json，再填写设备 ID 和 Token。") from None
    except (KeyError, TypeError, ValueError, RecursionError):
        raise SystemExit("AI 配置格式不对，请参考 config/ai.example.json。") from None
    except OSError:
        raise SystemExit("无法读取 config/ai.local.json，请检查文件访问权限。") from None


def wait_for_button(robot, level):
    while True:
        before = robot.digital.read(BUTTON_PIN)
        robot.wait(0.02)
        if before == level and robot.digital.read(BUTTON_PIN) == level:
            return


def main():
    url, device_id, token = load_config()
    robot = Robot(port=PORT)
    with robot:
        robot.ai.set(url)
        robot.ai.AIID(device_id)
        robot.ai.AItoken(token)
        robot.audio.set(**AUDIO_PINS)
        robot.start()  # 退出维护模式后，才能启用通用 GPIO。
        robot.digital.set(BUTTON_PIN, "input_pullup")

        print(f"开发板已连接。按钮接 GPIO{BUTTON_PIN} 和 GND，按 Ctrl+C 退出。", flush=True)
        while True:
            wait_for_button(robot, 1)
            print("准备就绪，请按住按钮说话。", flush=True)
            wait_for_button(robot, 0)
            robot.ai.record_start(max_seconds=MAX_SECONDS)
            print(f"正在录音，最多录 {MAX_SECONDS} 秒，松开后发送…", flush=True)
            wait_for_button(robot, 1)

            try:
                reply = robot.ai.record_end()
            except VoiceError as failure:
                print(f"AI 请求失败：{failure}", flush=True)
                continue
            if reply is not None:
                print("识别：", reply.recognized_text, flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("已停止等待。服务器已接收的任务可能继续运行。") from None
    except (RobotError, ValueError, OSError) as failure:
        raise SystemExit(f"测试失败：{failure}") from None
