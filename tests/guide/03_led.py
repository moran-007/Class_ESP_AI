"""LED串限流电阻接配置的led GPIO与GND；运行表示接线完成。"""
from _board import connect
with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.gpio.setup(12, 'output')
    for value in (1, 0, 1, 0):
        robot.gpio.write(12, value)
        robot.wait(1)
