"""直接运行：列出 ESP32 当前已连接的 Wi-Fi 和 IP，不接管屏幕。"""
from ai_robot import Robot, RobotError

PORT = "COM5"

if __name__ == "__main__":
    try:
        with Robot(port=PORT, read_only=True) as robot:
            networks = robot.listwifi()
            for network in networks:
                print(f"Wi-Fi：{network['ssid']}，IP：{network['ip']}")
            if not networks:
                print("ESP32 当前没有已连接的 Wi-Fi。")
    except (RobotError, OSError) as error:
        raise SystemExit(f"查询未完成，请检查串口是否被占用：{error}") from None
