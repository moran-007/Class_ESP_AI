"""USB provisioning for the board's own Wi-Fi connection."""

from time import monotonic, sleep

from .errors import RequestTimeout, RobotError, UnsupportedCapability


_FAILURES = {
    "connect_timeout": "连接超时，未取得 IP。请检查 Wi-Fi 名称、密码和 2.4 GHz 网络。",
    "storage_error": "设备未能保存 Wi-Fi 配置。",
    "start_failed": "设备未能启动 Wi-Fi。",
}


class Wifi:
    def __init__(self, robot):
        self._robot = robot

    def _request(self, operation, args=None):
        if self._robot._info.get("capabilities", {}).get("wifi_provisioning") is not True:
            raise UnsupportedCapability("该固件不支持 Wi-Fi 配网，请使用支持 wifi_provisioning 的教学固件")
        return self._robot._request(f"wifi.{operation}", args)

    def connect(self, ssid: str, password: str) -> dict:
        """Start connecting. The board saves the profile after it has an IP."""
        if not isinstance(ssid, str):
            raise ValueError("Wi-Fi 名称必须是字符串")
        try:
            length = len(ssid.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("Wi-Fi 名称必须是有效 UTF-8") from None
        if not 1 <= length <= 32 or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in ssid):
            raise ValueError("Wi-Fi 名称须为 1～32 个 UTF-8 字节，不能包含控制字符")
        if not isinstance(password, str) or (password and (
            not 8 <= len(password) <= 63 or any(not 32 <= ord(char) <= 126 for char in password)
        )):
            raise ValueError("Wi-Fi 密码须为 8～63 个可打印 ASCII 字符；开放网络留空")
        return self._request("connect", {"ssid": ssid, "password": password})

    def status(self) -> dict:
        """Read link and last provisioning status; never returns the password."""
        return self._request("status")

    def _connect_and_wait(self, name: str, password: str, *, progress: bool) -> dict:
        def report(message):
            if progress:
                print(f"[Wi-Fi] {message}", flush=True)

        report("1/3 发送配网请求…")
        try:
            result = self.connect(name, password)
            started = monotonic()
            reminder = started + 5
            if result["provisioning"] == "connecting":
                report("2/3 正在连接路由器并等待获得 IP…")
            while result["provisioning"] == "connecting" and monotonic() - started < 25:
                sleep(0.5)
                result = self.status()
                now = monotonic()
                if progress and result["provisioning"] == "connecting" and now >= reminder:
                    report(f"仍在等待 IP（已等待 {int(now - started)} 秒）…")
                    reminder = now + 5
        except RequestTimeout:
            report("USB 回执超时，配网结果未知。可稍后查询状态。")
            raise
        except (RobotError, ValueError):
            report("配网请求未完成，请查看错误信息。")
            raise

        if result["provisioning"] == "saved":
            report(f"3/3 配网成功，已保存。Wi-Fi：{result['ssid']}，IP：{result['ip']}")
        elif result["provisioning"] == "failed":
            reason = _FAILURES.get(result.get("error"), "设备报告配网失败。")
            kept = " 已保留原有 Wi-Fi 配置。" if result["saved"] else ""
            report(f"3/3 配网失败：{reason}{kept}")
        else:
            report("3/3 等待结束，设备仍未确认配网完成。可稍后查询状态。")
        return result

    def clear(self) -> dict:
        """Remove the saved Wi-Fi profile and turn off Wi-Fi."""
        return self._request("clear")
