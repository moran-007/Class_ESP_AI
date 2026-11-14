'''
Author: 陌
Date: 2026-11-11 11:28:28
LastEditors: 陌
LastEditTime: 2026-11-11 18:25:20
'''
"""开头连接和配置；点击发送复用同一个robot，关闭窗口释放连接。"""
import turtle
from _turtle import finish
from _board import Robot

robot = Robot(port="COM5")
try:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16)
    robot.start()  # 全部外设set之后启动，后面只绘图和发送。
         
    screen = turtle.Screen()
    screen.setup(640, 480)
    screen.bgcolor("#10263a")
    pen = turtle.Turtle()
    pen.speed(0)
    for color in ("#25d0e8", "#ffbd59", "#4a0818"):
        pen.color(color)
        pen.begin_fill()
        pen.circle(65)
        pen.end_fill()
        pen.right(120)
    pen.penup()
    pen.goto(-160, -150)
    pen.color("white")
    pen.write("AI小创客", font=("Microsoft YaHei", 48, "bold"))
    pen.hideturtle()
    finish(screen, robot=robot)  # 复用开头的连接，不会再次打开COM5。
finally:
    robot.close()  # 出错时也关闭；正常关窗后重复close是幂等的。
