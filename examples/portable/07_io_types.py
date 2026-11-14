"""按需接线：按钮2、LED12、模拟信号1、PWM实验LED17；全部共地。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.start()
    robot.digital.set(pin=2, mode="input_pullup")
    robot.digital.set(pin=12, mode="output")
    robot.analog.set(pin=1)
    robot.pwm.set(pin=17)
    pressed = robot.digital.read(2) == 0
    robot.digital.write(12, int(pressed))
    print("ADC原始值：", robot.analog.read(1))
    robot.pwm.write(17, 25)  # 占空比25%，不是DAC电压值。
    robot.wait(3)
