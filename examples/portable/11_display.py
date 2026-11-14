"""按实际屏幕与接线改参数；显示中文和矩形10秒。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16, rotation=1)
    robot.start()
    robot.display.fill("black")
    robot.display.text("你好，创客！", x=8, y=8)
    robot.display.rect(8, 40, 80, 20, color=(55, 88, 99), filled=True)
    robot.wait(10)
