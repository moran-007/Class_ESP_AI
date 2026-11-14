"""显示板上已保存的页面；修改PAGE切换home或status，不重新上传。"""
from _board import connect

PAGE = "home"
with connect() as robot:
    robot.pages.show(PAGE)
    robot.wait(5)
