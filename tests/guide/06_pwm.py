"""LED串限流电阻接pwm GPIO/GND；1kHz调光。"""
from _board import connect
with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.gpio.setup(12, 'pwm')
    for duty in (0, 25, 50, 75, 100, 0):
        robot.pwm.write(12, duty)
        robot.wait(1)
