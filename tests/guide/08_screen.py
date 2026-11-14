"""在本文件填写串口和屏幕IO；运行保存配置并初始化显示。"""
from _board import connect
with connect("COM5") as robot:
    # SCL=SCK，SDA=MOSI，RES=RST，BLK=背光；按实际GPIO修改。
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16, rotation=1)
    robot.start()
    robot.display.clear()
    robot.display.text('你好，创客！', x=8, y=8, color='cyan')
    robot.display.rect(8, 40, 90, 24, color=(55, 88, 99), filled=True)
    robot.display.line(8, 80, 110, 80, color='yellow')
    robot.wait(10)
