"""运行即让 ESP32 断开 Wi-Fi、清除板端保存的名称和密码。"""
from ai_robot import Robot, RobotError

PORT = "COM5"

if __name__ == "__main__":
    try:
        with Robot(port=PORT) as robot:
            result = robot.clearwifi()
            if result["state"] != "unconfigured" or result["saved"]:
                raise SystemExit(f"清除后的状态：{result['state']}，原因：{result['error']}")
            print("已清除板上的 Wi-Fi 名称和密码，并断开连接。")
    except (RobotError, OSError) as error:
        raise SystemExit(f"清除未完成：{error}") from None
