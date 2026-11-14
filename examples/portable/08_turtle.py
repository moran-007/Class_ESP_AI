"""标准库Turtle：SDK内置传图辅助，无需复制_board或_turtle文件。"""
import turtle
from ai_robot import Robot
from ai_robot.turtle import finish

robot = Robot(port="COM5")
try:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16)
    robot.start()
    screen = turtle.Screen()
    pen = turtle.Turtle()
    pen.color("orange")
    for _ in range(5):
        pen.forward(180)
        pen.right(144)
    pen.hideturtle()
    finish(screen, robot=robot)
finally:
    robot.close()
