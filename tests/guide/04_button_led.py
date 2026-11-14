"""按钮接button GPIO/GND；LED经限流电阻接led GPIO/GND。"""
from _board import connect
with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.gpio.setup(2, 'input_pullup')
    robot.gpio.setup(12, 'output')
    for _ in range(30):
        pressed = robot.gpio.read(2) == 0
        robot.gpio.write(12, int(pressed))
        print('按下' if pressed else '松开')
        robot.wait(0.5)
