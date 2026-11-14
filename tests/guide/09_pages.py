"""上传160×128示例页，不启用开机显示；其他尺寸先用编辑器布局。"""
from pathlib import Path
from _board import connect_screen
PROJECT = Path(__file__).resolve().parents[2] / 'examples/pages/page_demo.json'
with connect_screen("COM5", panel="st7735s_128x160",
                    sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16) as robot:
    robot.pages.upload(PROJECT)
    robot.pages.show('home')
    robot.pages.text('status', 'Python更新成功')
    print(robot.pages.info())
    robot.wait(5)
