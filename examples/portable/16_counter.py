"""SDK/固件0.7：替换保存流程为板端每秒+1；RESET后从0计数，清除可用program.clear。"""
from ai_robot import Program, Robot

PORT = "COM5"
program = Program()
program.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                    CS=15, DC=7, RES=6, BLK=16, rotation=1)
program.display.fill("black")
program.display.text("数字累加", x=8, y=8, color="cyan")
program.display.text("+1 / second", x=8, y=26)
program.display.counter(name="count", start=0, step=1, interval=1,
                        x=8, y=48, width=144, height=20,
                        color="white", background="black")

with Robot(port=PORT) as robot:
    robot.program.save(program, autostart=True)  # counter自带持续运行，保持loop=False。
print("已保存。RESET或重新接电后从0开始，每秒加1；不需要电脑while循环。")
