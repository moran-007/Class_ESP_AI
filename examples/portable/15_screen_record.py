"""SDK0.6.1：屏幕边画边录制，结束后固化；下次RESET/重新接电每3秒切页。"""
from ai_robot import Robot

PORT = "COM5"
with Robot(port=PORT) as robot:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16, rotation=1)
    robot.start()

    robot.program.begin()  # 开始同步预览和录制。
    for title in ("屏幕测试", "屏幕测试2"):
        robot.display.clear()
        robot.display.text("AI Maker", x=8, y=8, color="cyan")
        robot.display.text(title + "\n你好，创客！", x=8, y=28)
        robot.display.rect(8, 68, 105, 28, color=(155, 88, 99), filled=True)
        robot.display.line(8, 108, 112, 108, color="yellow")
        robot.wait(3)  # 预览时实际等待，同时录成板端等待。可改为30。
    robot.program.end()  # 结束录制，尚未上传。

    robot.program.save(loop=True, autostart=True)
    print("已保存；关闭本程序后RESET或重新接电，两页将独立循环。")
