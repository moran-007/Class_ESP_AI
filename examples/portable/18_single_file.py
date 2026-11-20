"""可选配网与板载 RGB 共用一个连接；已配网时直接运行。"""
from getpass import getpass

from ai_robot import Robot

PORT = "COM5"
WIFI_NAME = None

with Robot(port=PORT) as robot:
    if WIFI_NAME is not None:
        robot.setwifi(WIFI_NAME, getpass("Wi-Fi 密码："))
    print(robot.listwifi())
    robot.led.color("cyan")
    robot.wait(2)
