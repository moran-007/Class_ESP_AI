"""填好串口、Wi-Fi 名称和密码后直接运行；密码为 None 时在终端隐藏输入。"""
from getpass import GetPassWarning, getpass
import warnings

from ai_robot import Robot, RobotError

PORT = "COM5"
WIFI_NAME = None
WIFI_PASSWORD = None


def main():
    name = WIFI_NAME if WIFI_NAME is not None else input("Wi-Fi 名称：")
    password = WIFI_PASSWORD
    if password is None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Wi-Fi 密码（输入不显示）：")
    with Robot(port=PORT) as robot:
        result = robot.setwifi(name, password)
        if result["provisioning"] != "saved":
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except GetPassWarning:
        raise SystemExit("当前窗口不能隐藏密码，请改用系统终端。") from None
    except (RobotError, OSError, ValueError, EOFError) as error:
        raise SystemExit(f"配网未完成：{error}") from None
