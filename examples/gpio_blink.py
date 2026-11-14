"""显式启用 GPIO 闪灯；LED 必须串限流电阻，先按实际接线核验引脚。"""

import argparse
import time

from ai_robot import Robot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--pin", required=True, type=int)
    parser.add_argument("--run", action="store_true", help="确认接线后允许实际输出")
    options = parser.parse_args()
    if not options.run:
        parser.error("先核验接线，再加 --run 启用实际输出")
    with Robot(port=options.port) as robot:
        robot.gpio.setup(options.pin, "output")
        for _ in range(3):
            robot.gpio.write(options.pin, 1)
            time.sleep(0.5)
            robot.gpio.write(options.pin, 0)
            time.sleep(0.5)


if __name__ == "__main__": main()
