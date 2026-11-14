"""安装SDK后可在任意目录运行；只查设备信息，不启动外设。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    print(robot.get_info())
    for pin in robot.list_pins():
        print(pin)
