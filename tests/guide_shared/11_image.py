"""Pillow绘图后适配整屏发送；依赖安装脚本中的drawing扩展。"""
from _board import connect_screen
from PIL import Image, ImageDraw
with Image.new('RGB', (160, 128), '#10263a') as image:
    ImageDraw.Draw(image).ellipse((40, 24, 120, 104), fill='orange')
    with connect_screen() as robot:
        robot.display.image(image)
        robot.wait(10)
