"""明确启用已保存home开机页：退出Python后恢复显示，重启也显示。"""
from _board import connect

with connect() as robot:
    robot.pages.startup("home", enabled=True)
    print("已启用home默认页；退出本程序后由ESP32独立显示。")
