"""直接运行：查询设备和引脚，不驱动外设。"""
from _board import connect

with connect() as robot:
    print("设备：", robot.get_info())
    print("状态：", robot.get_status())
    print("引脚：", robot.list_pins())
