"""仅测试BLK已接GPIO的模块；先在_screen_settings.py设置BACKLIGHT。"""
from _screen import connect_screen
from _screen_settings import BACKLIGHT

if BACKLIGHT == -1:
    raise SystemExit("未配置背光GPIO：7针屏或BLK固定接电源时不支持此调光测试。")
with connect_screen() as robot:
    robot.display.fill("white")
    for percent in (20, 60, 100, 60):
        print("背光指令：", percent, "%")
        robot.display.brightness(percent)
        robot.wait(2)
