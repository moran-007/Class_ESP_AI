'''
Author: 陌
Date: 2026-11-08 16:53:48
LastEditors: 陌
LastEditTime: 2026-11-08 20:45:33
'''
"""接线、独立供电和校准完成后运行；立即驱动舵机，首次请卸下连杆。"""
from _board import connect

PIN = 14
ANGLE = 30
with connect() as robot:
    robot.servo.configure("test", PIN, min_angle=30, max_angle=150)
    robot.maintenance.exit()  # 运行本文件表示已完成接线及供电确认。
    robot.servo.move("test", ANGLE)
    print("已发角度指令：", ANGLE, "；没有位置反馈")
    robot.wait(3)
