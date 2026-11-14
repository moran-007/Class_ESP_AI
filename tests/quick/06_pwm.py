'''
Author: 陌
Date: 2026-11-08 16:53:48
LastEditors: 陌
LastEditTime: 2026-11-08 17:59:30
'''
"""接好外部 LED 和限流电阻后运行；固定 1kHz 调光。"""
from _board import connect

PIN = 17
with connect() as robot:
    robot.gpio.setup(PIN, "pwm")
    for duty in (0, 25, 50, 75, 100, 0):
        robot.pwm.write(PIN, duty)
        print("PWM 占空比：", duty, "%")
        robot.wait(1)
