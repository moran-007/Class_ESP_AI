"""按钮接 GPIO2/GND；GPIO12 经限流电阻接 LED 正极，负极接 GND。"""
from _board import connect

BUTTON_PIN = 2
LED_PIN = 12
with connect() as robot:
    robot.gpio.setup(BUTTON_PIN, "input_pullup")
    robot.gpio.setup(LED_PIN, "output")
    while True:  # 持续测试，按 Ctrl+C 或 IDE 停止按钮退出。
        pressed = robot.gpio.read(BUTTON_PIN) == 0
        robot.gpio.write(LED_PIN, int(pressed))
        print("按下 → 输出1" if pressed else "松开 → 输出0")
        robot.wait(0.1)
