"""只查询设备；必须显式指定串口，不会自动配置或驱动输出。"""

import argparse
import json

from ai_robot import Robot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="例如 COM4，需先确认连接的是教学固件")
    options = parser.parse_args()
    with Robot(port=options.port) as robot:
        print(json.dumps(robot.get_info(), ensure_ascii=False, indent=2))
        print(json.dumps(robot.get_status(), ensure_ascii=False, indent=2))
        print(json.dumps(robot.list_pins(), ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
