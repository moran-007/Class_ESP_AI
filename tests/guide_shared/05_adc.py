"""模拟信号接adc GPIO并共地；须处于3.3V域允许范围，不接5V。"""
from _board import connect, PINS
with connect() as robot:
    robot.maintenance.exit()
    robot.gpio.setup(PINS['adc'], 'input')
    for _ in range(10):
        print(robot.adc.read(PINS['adc']))
        robot.wait(0.5)
