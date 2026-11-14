"""先在配置窗口填写屏幕接线；运行保存配置并初始化显示。"""
from _board import connect_screen
with connect_screen() as robot:
    robot.display.clear()
    robot.display.text('你好，创客！', x=8, y=8, color='cyan')
    robot.display.rect(8, 40, 90, 24, color=(55, 88, 99), filled=True)
    robot.display.line(8, 80, 110, 80, color='yellow')
    robot.wait(10)
