"""LED串限流电阻接pwm GPIO/GND；1kHz调光。"""
from _board import connect, PINS
with connect() as robot:
    robot.maintenance.exit()
    robot.gpio.setup(PINS['pwm'], 'pwm')
    for duty in (0, 25, 50, 75, 100, 0):
        robot.pwm.write(PINS['pwm'], duty)
        robot.wait(1)
