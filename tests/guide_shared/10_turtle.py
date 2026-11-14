"""标准库Turtle：画好后点击发送按钮，关闭窗口恢复默认页。"""
from _board import PORT  # 加载统一配置和公共模块，不连接USB。
import turtle
from _turtle import finish
screen = turtle.Screen()
pen = turtle.Turtle()
pen.pensize(5)
pen.color('orange')
for _ in range(5):
    pen.forward(180)
    pen.right(144)
pen.hideturtle()
finish(screen)
