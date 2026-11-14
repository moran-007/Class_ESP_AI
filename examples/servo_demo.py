"""单舵机示例，分配置和动作两步；需匹配外部舵机电源并按方案共地。"""

import argparse

from ai_robot import Robot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    configure = subparsers.add_parser("configure", help="保存 head 的 GPIO 映射，保持维护模式，不动作")
    configure.add_argument("--pin", required=True, type=int)
    move = subparsers.add_parser("move", help="确认接线后退出维护并执行一次动作")
    move.add_argument("--angle", type=int, default=90)
    move.add_argument("--run", action="store_true", help="确认校准、接线、供电与机械范围")
    options = parser.parse_args()
    if options.command == "move" and not options.run:
        parser.error("动作必须显式加 --run；信号释放不等于断电，不保证机械负载安全")
    with Robot(port=options.port) as robot:
        if options.command == "configure":
            print(robot.servo.configure("head", options.pin, min_angle=30, max_angle=150))
            print("仍处于维护模式。换线需先维护、断电、换线、重上电；不会自动运动。")
        else:
            robot.maintenance.exit()
            print(robot.servo.move("head", options.angle))
            input("观察完成后按 Enter 撤销控制脉冲；请避免悬挂负载。")
            robot.servo.release("head")


if __name__ == "__main__": main()
