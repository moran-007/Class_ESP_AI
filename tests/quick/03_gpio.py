"""接好外部 LED 和限流电阻后运行；PIN 是信号引脚，可修改。"""
from _board import connect

PIN = 12
with connect() as robot:
    robot.gpio.setup(PIN, "output")
    for level in (1, 0, 1, 0):
        robot.gpio.write(PIN, level)
        print("GPIO 输出：", PIN, level)
        robot.wait(1)
