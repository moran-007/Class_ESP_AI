"""上传160×128示例页，不启用开机显示；其他尺寸先用编辑器布局。"""
from pathlib import Path
from _board import connect_screen
PROJECT = Path(__file__).resolve().parents[2] / 'examples/pages/page_demo.json'
with connect_screen() as robot:
    robot.pages.upload(PROJECT)
    robot.pages.show('home')
    robot.pages.text('status', 'Python更新成功')
    print(robot.pages.info())
    robot.wait(5)
