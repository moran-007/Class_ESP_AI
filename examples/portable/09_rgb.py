"""只需USB：板载RGB自定义颜色2秒，结束释放。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.start()
    robot.led.set(red=8, green=16, blue=3)
    robot.wait(2)
