'''
Author: 陌
Date: 2026-11-08 21:30:18
LastEditors: 陌
LastEditTime: 2026-11-09 20:56:47
'''
"""三个屏幕示例共用的接线；换屏或换线前请断电。"""

PANEL = "st7735s_128x160"  # 或 st7789_240x240 / st7735s_128x160
SCK = 4
MOSI = 5  # 屏幕标为 SDA 时，此脚仍是 SPI MOSI，不是 I2C。
CS = 15
DC = 7
RST = 6
BACKLIGHT = 16  # 7针无BLK用-1；8针BLK接GPIO16时改为16。
ROTATION = 1  # 0/2竖屏，1/3横屏。
INVERT = None  # 自动按控制器选择；颜色反相时可明确改True/False。
BRIGHTNESS = None  # 自动：有BLK为60%，无BLK为100%且不支持调光。

SCREEN = dict(panel=PANEL, sck=SCK, mosi=MOSI, cs=CS, dc=DC, rst=RST,
              backlight=BACKLIGHT, rotation=ROTATION, invert=INVERT, brightness=BRIGHTNESS)
