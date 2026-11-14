"""先配置好屏幕；上传示例页面与图标、显示5秒，不自动启用开机页。"""
from pathlib import Path
from _board import connect

PROJECT = Path(__file__).resolve().parents[2] / "examples/pages/page_demo.json"
with connect() as robot:
    robot.pages.upload(PROJECT)
    robot.pages.show("home")
    robot.wait(5)
