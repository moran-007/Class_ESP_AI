"""先完成独立供电、共地及校准，首次卸下连杆；运行立即发90°。"""
from _board import connect
with connect("COM5") as robot:
    robot.servo.set(pin=14)  # 默认名称test、SG90课堂校准预设。
    robot.start()
    robot.servo.move("test", 90)
    robot.wait(3)
