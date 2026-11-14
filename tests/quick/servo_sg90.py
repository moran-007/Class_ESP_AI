"""SG90 信号接 GPIO14；匹配的独立电源与 ESP32 共地，卸下连杆后运行。"""
from _board import connect

PIN = 14
with connect() as robot:
    robot.servo.configure("test", PIN, min_angle=30, max_angle=150,
                          min_pulse_us=1000, max_pulse_us=2000)
    robot.maintenance.exit()
    for angle in (60, 90, 120, 90):
        print("发送角度：", angle)
        robot.servo.move("test", angle)
        robot.wait(1)
