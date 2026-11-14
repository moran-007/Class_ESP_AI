"""按钮接button GPIO/GND；LED经限流电阻接led GPIO/GND。"""
from _board import connect, PINS
with connect() as robot:
    robot.maintenance.exit()
    robot.gpio.setup(PINS['button'], 'input_pullup')
    robot.gpio.setup(PINS['led'], 'output')
    for _ in range(30):
        pressed = robot.gpio.read(PINS['button']) == 0
        robot.gpio.write(PINS['led'], int(pressed))
        print('按下' if pressed else '松开')
        robot.wait(0.5)
