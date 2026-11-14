"""SG90信号14，独立匹配供电并共地；运行即发90°，首次卸下连杆。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.servo.set(pin=14, name="arm", min_angle=30, max_angle=150)
    robot.start()
    robot.servo.move("arm", 90)
    robot.wait(3)
