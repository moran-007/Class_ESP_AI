"""在终端运行：USB 配网，显示状态和 IP；密码输入不回显。"""

import argparse
from getpass import GetPassWarning, getpass
import warnings

from ai_robot import Robot, RobotError


def show(result):
    link = {"unconfigured": "尚未配网", "connecting": "正在连接", "connected": "已连接",
            "disconnected": "未连接", "error": "配网异常"}
    setup = {"idle": "未发起新配网", "connecting": "正在配网", "saved": "配网成功，已保存",
             "failed": "本次配网失败"}
    print("配网状态：", setup[result["provisioning"]], "；网络：", link[result["state"]])
    if result["ssid"]:
        print("Wi-Fi 名称：", result["ssid"])
    if result["ip"]:
        print("IP 地址：", result["ip"])
    if result["error"]:
        print("原因：", result["error"])
    if result["provisioning"] == "failed" and result["saved"]:
        print("已保留上一次成功的配网配置。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="AUTO", help="USB 串口，例如 COM5；默认自动选择")
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--status", action="store_true", help="只查询 Wi-Fi 状态")
    commands.add_argument("--clear", action="store_true", help="清除本板保存的 Wi-Fi 配置")
    options = parser.parse_args()
    try:
        if not (options.status or options.clear):
            ssid = input("Wi-Fi 名称（支持中文）：")
            with warnings.catch_warnings():
                warnings.simplefilter("error", GetPassWarning)
                password = getpass("Wi-Fi 密码（输入不显示，开放网络直接回车）：")
        with Robot(port=options.port, read_only=options.status) as robot:
            if options.clear:
                result = robot.wifi.clear()
            elif options.status:
                result = robot.wifi.status()
            else:
                result = robot.setwifi(ssid, password)
            if options.status or options.clear:
                show(result)
            if result["provisioning"] in {"connecting", "failed"} or result["state"] == "error":
                return 1
    except GetPassWarning:
        print("此窗口无法隐藏密码输入，请使用系统终端或页面编辑器配网。")
        return 1
    except (RobotError, ValueError, OSError, EOFError) as error:
        print("配网操作未完成：", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
