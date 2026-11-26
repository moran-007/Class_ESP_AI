"""文字问答、固定时长语音或按住按钮说话。"""
from getpass import GetPassWarning, getpass
import os
import warnings

from ai_robot import Robot, RobotError, VoiceClient

MODE = "text"  # text：文字；voice：固定录 3 秒；button：按住录音。
SERVER = os.getenv("AI_MAKER_VOICE_URL", "https://voice.bsnlch.xyz")
DEVICE_ID = os.getenv("AI_MAKER_DEVICE_ID", "")
PORT = "COM5"
BUTTON_PIN = 2  # 按钮接此 GPIO 和 GND。


def main():
    device_id = DEVICE_ID or input("服务器注册的设备 ID：").strip()
    token = os.getenv("AI_MAKER_DEVICE_TOKEN")
    if not token:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            token = getpass("设备 Token：")
    if MODE == "text":
        voice = VoiceClient(SERVER)
        voice.AIID(device_id)
        voice.AItoken(token)
        print(f"AI 服务器：{SERVER}", flush=True)
        displayed = False

        def show_segment(text):
            nonlocal displayed
            print("AI：" + text if not displayed else text, flush=True)
            displayed = True

        reply = voice.ask(input("你想问什么？"), progress=True, on_text=show_segment)
        if not displayed:
            print("AI：", reply.answer_text)
        return
    elif MODE in ("voice", "button"):
        with Robot(port=PORT) as robot:
            robot.ai.set(SERVER)
            robot.ai.AIID(device_id)
            robot.ai.AItoken(token)
            print(f"AI 服务器：{SERVER}", flush=True)
            robot.audio.set(bclk=42, ws=41, din=21, dout=40, sd=39, volume=20)
            robot.start()
            if MODE == "button":
                robot.digital.set(BUTTON_PIN, "input_pullup")
                print("按住按钮说话，松开后分段播报。", flush=True)
                while robot.digital.read(BUTTON_PIN) == 1:
                    robot.wait(0.02)
                robot.ai.record_start()
                while robot.digital.read(BUTTON_PIN) == 0:
                    robot.wait(0.02)
                reply = robot.ai.record_end()
                if reply is not None:
                    print("识别：", reply.recognized_text)
                return
            print("请说话，正在录音 3 秒…", flush=True)
            reply = robot.ai.talk(3, progress=True)
        print("识别：", reply.recognized_text)
    else:
        raise ValueError('MODE 只能填 "text"、"voice" 或 "button"')
    print("AI：", reply.answer_text)


if __name__ == "__main__":
    try:
        main()
    except GetPassWarning:
        raise SystemExit("请在能隐藏输入的系统终端运行。") from None
    except KeyboardInterrupt:
        raise SystemExit("已停止在电脑上等待；服务器已接收的任务可能仍在运行。") from None
    except (RobotError, ValueError, OSError) as failure:
        raise SystemExit(str(failure)) from None
