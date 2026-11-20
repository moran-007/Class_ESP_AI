"""直接运行：显示 ESP32 的 Wi-Fi 名称、IP 和北京时间。串口与接线在文件开头设置。"""

import argparse
from datetime import datetime, timedelta, timezone
from getpass import GetPassWarning, getpass
from time import monotonic
from unicodedata import east_asian_width
import warnings

from ai_robot import Robot, RobotError


PORT = "COM5"
WIFI_NAME = None
WIFI_PASSWORD = None
SCREEN = None

BEIJING = timezone(timedelta(hours=8))
LINK = {"unconfigured": "尚未配网", "connecting": "正在连接", "connected": "Wi-Fi 已连接",
        "disconnected": "Wi-Fi 未连接", "error": "Wi-Fi 异常"}


def wrap_name(name, width):
    rows, row, used = [], "", 0
    for char in name:
        pixels = 12 if east_asian_width(char) in {"W", "F", "A"} else 7
        if row and used + pixels > width:
            rows.append(row)
            row, used = "", 0
        row += char
        used += pixels
    return "\n".join(rows + [row])


def show(robot, ssid=None, seconds=None):
    if SCREEN is not None:
        robot.display.set(**SCREEN)
        robot.maintenance.exit()

    wifi = robot.wifi.status()
    provisioning_ok = True
    name = ssid if ssid is not None else WIFI_NAME
    if name is not None or not wifi["saved"]:
        name = name if name is not None else input("Wi-Fi 名称（支持中文）：")
        password = WIFI_PASSWORD if ssid is None else None
        if password is None:
            with warnings.catch_warnings():
                warnings.simplefilter("error", GetPassWarning)
                password = getpass("Wi-Fi 密码（不回显）：")
        wifi = robot.setwifi(name, password)
        del password
        provisioning_ok = wifi["provisioning"] == "saved"

    geometry = robot.display.begin()
    width, height = geometry["width"], geometry["height"]
    if width < 128 or height < 128:
        raise ValueError("Wi-Fi 测试页需要至少 128×128 的屏幕")
    robot.display.clear()
    previous = None
    deadline = None if seconds is None else monotonic() + seconds
    while True:
        link = (wifi["state"], wifi["ssid"], wifi["ip"])
        if link != previous:
            state, name, ip = link
            robot.display.rect(0, 0, width, 92, color="black", filled=True)
            robot.display.text(LINK[state], x=8, y=7, color="cyan")
            robot.display.line(8, 25, width - 9, 25, color="cyan")
            robot.display.text(wrap_name(name or "尚无网络名称", width - 16), x=8, y=32)
            address = f"IP {ip}" if ip and width >= 142 else ip
            robot.display.text(address or "尚未取得 IP", x=8, y=69, color="yellow")
            print(f"{LINK[state]} | Wi-Fi：{name or '—'} | IP：{ip or '—'}", flush=True)
            previous = link
        now = datetime.now(BEIJING)
        robot.display.rect(0, 92, width, height - 92, color="black", filled=True)
        date_format = "%Y-%m-%d %H:%M:%S" if width >= 149 else "%Y-%m-%d\n%H:%M:%S"
        robot.display.text(now.strftime(date_format), x=8, y=92)
        if deadline is not None and monotonic() >= deadline:
            return 0 if provisioning_ok and wifi["state"] == "connected" else 1
        robot.wait(1)
        wifi = robot.wifi.status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=PORT, help="覆盖文件开头的串口")
    parser.add_argument("--ssid", help="重新配网的名称；省略时使用板上保存的网络")
    parser.add_argument("--seconds", type=int, help="运行多少秒；省略时持续刷新，Ctrl+C 退出")
    options = parser.parse_args()
    if options.seconds is not None and options.seconds < 1:
        parser.error("--seconds 至少为 1")
    try:
        with Robot(port=options.port) as robot:
            return show(robot, ssid=options.ssid, seconds=options.seconds)
    except KeyboardInterrupt:
        print("已结束测试。")
        return 0
    except GetPassWarning:
        print("这个窗口不能隐藏密码输入，请使用系统终端或先在「配置硬件」中配网。")
        return 1
    except (RobotError, ValueError, OSError, EOFError) as error:
        print(f"测试未完成：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
