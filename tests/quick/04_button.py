"""接外部按钮到 PIN 与 GND 后运行；按下读 0，松开读 1。"""
from _board import connect

PIN = 2
with connect() as robot:
    robot.gpio.setup(PIN, "input_pullup")
    robot.gpio.setup(12, "output")

    for _ in range(20):
        if (robot.gpio.read(PIN) == 0):
            print("按下")
            robot.gpio.write(12, robot.gpio.read(PIN))

        else:
            print("松开")
            robot.gpio.write(12, robot.gpio.read(PIN))
        robot.wait(0.5)
