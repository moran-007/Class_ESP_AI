"""固化按钮控制外接LED：按钮2接GND，LED12串限流电阻；重启后动作。需要0.6固件。"""
from ai_robot import Program, Robot

PORT, BUTTON, LED = "COM5", 2, 12
pressed, released = Program(), Program()
pressed.digital.write(LED, 1)
pressed.wait(0.05)
released.digital.write(LED, 0)
released.wait(0.05)

program = Program()
program.digital.set(BUTTON, "input_pullup")
program.digital.set(LED, "output")
program.when_digital(BUTTON, 0, then=pressed, otherwise=released)

with Robot(port=PORT) as robot:
    robot.program.save(program, loop=True, autostart=True)
    print("已保存；重新接电后按下点亮，松开熄灭。按实际接线修改BUTTON和LED。")
