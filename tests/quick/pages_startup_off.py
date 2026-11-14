"""停用开机默认页；保留已保存的页面和屏幕接线。"""
from _board import connect

with connect() as robot:
    robot.pages.startup(enabled=False)
    print("已停用默认页，之后退出Python不再自动恢复页面。")
