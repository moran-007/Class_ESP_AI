"""LED串限流电阻接配置的led GPIO与GND；运行表示接线完成。"""
from _board import connect, PINS
with connect() as robot:
    robot.maintenance.exit()
    robot.gpio.setup(PINS['led'], 'output')
    for value in (1, 0, 1, 0):
        robot.gpio.write(PINS['led'], value)
        robot.wait(1)
