"""整屏图片发送测速；fps是电脑端上限，不是面板刷新率。无需舵机。"""
import time
from _board import Robot
from PIL import Image

robot = Robot(port="COM5")
try:
    # 位置参数顺序：SCK、MOSI、CS、DC、RST、BLK，不是排针排列顺序。
    robot.display.set(4, 5, 15, 7, 6, 16, panel="st7735s_128x160", fps=10)
    robot.start()
    started = time.monotonic()
    with Image.new("RGB", (160, 128)) as image:
        for frame in range(10):
            image.paste("#103050" if frame % 2 else "#306050", (0, 0, 160, 128))
            result = robot.display.image(image)
    elapsed = time.monotonic() - started
    print(f"电脑发送完成：10帧/{elapsed:.2f}秒，平均{10 / elapsed:.2f}帧/秒")
    print(f"最后一帧分块传输用时：{result['transfer_seconds']:.3f}秒；没有光学反馈")
    robot.wait(3)
finally:
    robot.close()
