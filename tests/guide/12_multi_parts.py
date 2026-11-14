"""屏幕+SG90+按钮+板载RGB。先完成供电/共地/接线，舵机立即发90°。"""
from _board import Robot

robot = Robot(port="COM5")  # 不强制with；finally负责关闭连接。
try:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16)
    robot.servo.set(pin=14)
    robot.start()  # 全部set完成后统一启动；本行不移动舵机。
    robot.gpio.setup(pin=2, mode="input_pullup")
    robot.display.text("多外设运行", x=8, y=8)
    robot.servo.move("test", 90)
    for _ in range(20):
        pressed = robot.gpio.read(pin=2) == 0
        robot.led.color("red" if pressed else "green")
        robot.wait(0.5)
finally:
    robot.close()
