"""只需USB：查看固件、保存配置、引脚能力与占用。"""
from _board import connect
with connect() as robot:
    print(robot.get_info())
    print(robot.get_status())
    print(robot.config.get())
    for pin in robot.list_pins():
        print(pin)
