"""固化板载RGB红绿循环；本次只保存，重启/重新接电后自动运行。需要0.6固件。"""
from ai_robot import Program, Robot

PORT = "COM5"
program = Program()
program.led.color("red", brightness=8)
program.wait(1)
program.led.color("green", brightness=8)
program.wait(1)

with Robot(port=PORT) as robot:
    robot.program.save(program, loop=True, autostart=True)
    print("已保存；关闭本程序不会立即运行，重启或重新接电后循环红绿。")
