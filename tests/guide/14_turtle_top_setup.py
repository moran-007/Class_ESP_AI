"""开头配置屏幕，后面绘图，finish复用连接；没有第二个COM会话。"""
from _board import Robot
from _turtle import finish
import turtle

robot = Robot(port="COM5")
try:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16)
    robot.start()
    screen = turtle.Screen()
    pen = turtle.Turtle()
    pen.pensize(5)
    pen.color("orange")
    for _ in range(5):
        pen.forward(180)
        pen.right(144)
    pen.hideturtle()
    finish(screen, robot=robot)
finally:
    robot.close()
