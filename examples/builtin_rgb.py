"""按红绿蓝循环发送板载 RGB 指令；颜色需由观察者确认，无光学反馈。"""

import argparse
import time

from ai_robot import Robot, RobotError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="显式指定教学固件串口，例如 COM3")
    parser.add_argument("--run", action="store_true", help="允许实际发送板载 RGB 指令")
    parser.add_argument("--brightness", type=int, default=8, help="每色指令值 1～32，默认 8")
    parser.add_argument("--seconds", type=float, default=2.0, help="每色保持 0.5～10 秒，默认 2")
    parser.add_argument("--cycles", type=int, default=2, help="循环次数 1～10，默认 2")
    options = parser.parse_args()
    if not options.run:
        parser.error("确认设备与固件后，显式加 --run 才会连接并驱动 RGB")
    if not 1 <= options.brightness <= 32:
        parser.error("brightness 必须为 1～32")
    if not 0.5 <= options.seconds <= 10:
        parser.error("seconds 必须为 0.5～10")
    if not 1 <= options.cycles <= 10:
        parser.error("cycles 必须为 1～10")
    colors = (
        ("红", {"red": options.brightness}),
        ("绿", {"green": options.brightness}),
        ("蓝", {"blue": options.brightness}),
    )
    with Robot(port=options.port) as robot:
        if not robot.get_info().get("capabilities", {}).get("builtin_led", False):
            raise RobotError("该设备未声明板载 RGB 能力，未发送颜色命令")
        try:
            for cycle in range(options.cycles):
                for label, channels in colors:
                    result = robot.led.set(**channels)
                    print(f"第 {cycle + 1} 轮：已发送{label}色指令，请观察实际颜色。回执：{result}", flush=True)
                    time.sleep(options.seconds)
                robot.led.off()
                time.sleep(0.5)
        finally:
            try:
                print("关闭 RGB 指令回执：", robot.led.off(), flush=True)
            except RobotError as error:
                print(f"无法确认关闭指令结果，请检查连接并等待设备租约超时：{error}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已中断演示；会话关闭或超时将请求关闭 RGB。")
