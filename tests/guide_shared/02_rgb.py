"""只需USB：板载RGB自定义颜色，分量范围0～32。"""
from _board import connect
with connect() as robot:
    robot.maintenance.exit()
    robot.led.color('yellow')
    robot.wait(2)
    robot.led.set(red=12, green=5, blue=20)
    robot.wait(2)
    robot.led.off()
