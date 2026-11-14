"""先修改_screen_settings.py：依次显示红绿蓝白黑，检查颜色和满屏范围。"""
from _screen import connect_screen

with connect_screen() as robot:
    for color in ("red", "green", "blue", "white", "black"):
        print("屏幕颜色指令：", color)
        robot.display.fill(color)
        robot.wait(2)
