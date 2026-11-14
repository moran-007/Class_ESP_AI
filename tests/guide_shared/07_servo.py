"""先完成独立供电、共地及校准，首次卸下连杆；运行立即发90°。"""
from _board import connect, SERVO
with connect() as robot:
    robot.servo.configure(**SERVO)
    robot.maintenance.exit()
    robot.servo.move(SERVO['name'], 90)
    robot.wait(3)
