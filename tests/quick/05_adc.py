'''
Author: 陌
Date: 2026-11-08 16:53:48
LastEditors: 陌
LastEditTime: 2026-11-08 19:15:15
'''
"""模拟信号接 PIN 并共地后运行；只输出原始计数，不是电压。"""
from _board import connect

PIN = 1
with connect() as robot:
    robot.gpio.setup(PIN, "input")
    for _ in range(100):
        print("ADC 原始计数：", robot.adc.read(PIN))
        robot.wait(0.1)
