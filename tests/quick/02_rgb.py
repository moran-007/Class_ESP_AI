'''
Author: 陌
Date: 2026-11-08 16:53:48
LastEditors: 陌
LastEditTime: 2026-11-08 17:10:37
'''
"""直接运行：板载灯依次红、绿、蓝各 2 秒，结束后熄灭。"""
from _board import connect

with connect() as robot:
    for color in ("yellow", (55,88,99), "blue"):
        print("板载灯：", color)
        robot.led.color(color)
        robot.wait(2)
