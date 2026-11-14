'''
Author: 陌
Date: 2026-11-08 21:30:18
LastEditors: 陌
LastEditTime: 2026-11-09 21:15:58
'''
"""先修改_screen_settings.py：显示中英文、边框、线段和自定义RGB颜色。"""
from _screen import connect_screen

with connect_screen() as robot:
    robot.display.clear()
    robot.display.text("AI Maker", x=8, y=8, color="cyan")
    robot.display.text("屏幕测试\n你好，创客！", x=8, y=28)
    robot.display.rect(8, 68, 105, 28, color=(155, 88, 99), filled=True)
    robot.display.line(8, 108, 112, 108, color="yellow")
    print("图案已发送；请观察文字、线段和颜色，10秒后结束。")
    robot.wait(10)
