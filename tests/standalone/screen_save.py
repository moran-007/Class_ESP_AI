"""屏幕固化：默认ST7735S接线；保存后按RESET或重新接电，A/B每4秒交替。"""
from ai_robot import Program, Robot

PORT = "COM5"
program = Program()
program.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                    CS=15, DC=7, RES=6, BLK=16, rotation=1)
for label, background, stripe in (
        ("A", (16, 38, 58), "cyan"),
        ("B", (0, 72, 48), "yellow")):
    program.display.fill(background)
    program.display.text("固化屏幕 " + label, x=8, y=8)
    program.display.text("standalone " + label, x=8, y=30)
    program.display.rect(8, 70, 144, 18, color=stripe, filled=True)
    program.wait(4)

with Robot(port=PORT) as robot:
    robot.program.save(program, loop=True, autostart=True)
    print("已保存。关闭本程序后按RESET或重新接电，屏幕将自动交替显示A/B。")
    print("清除并恢复原默认页：运行同文件夹的 screen_clear.py。")
