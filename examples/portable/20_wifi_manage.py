"""查询 ESP32 当前连上的 Wi-Fi；需要清除时才把 CLEAR 改成 True。"""
from ai_robot import Robot

PORT = "COM5"
CLEAR = False

if __name__ == "__main__":
    with Robot(port=PORT, read_only=not CLEAR) as robot:
        if CLEAR:
            print("清除后的状态：", robot.clearwifi()["state"])
        print("当前连接：", robot.listwifi())
