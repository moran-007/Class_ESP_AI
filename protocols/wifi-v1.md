# USB Wi-Fi 配网协议 v1

使用 [USB JSONL](usb-v1.md)，`device.info.capabilities.wifi_provisioning=true`。只配置 ESP32 的 2.4 GHz STA 连接；设备不开放网络控制接口。密码仅用 USB 请求提交，不出现在响应中。

| 操作 | 参数 | 语义 |
|---|---|---|
| `wifi.connect` | `ssid`：1～32 UTF-8 字节，不含控制字符；`password`：8～63 可打印 ASCII 字符，开放网络填空字符串 | 需 USB 会话；启动试连，不等待 DHCP。已有试连时返回 `DEVICE_BUSY`。 |
| `wifi.status` | `{}` | 只读，无需设备控制会话，不占用控制权。 |
| `wifi.clear` | `{}` | 需 USB 会话；清除独立 Wi-Fi 记录，关闭无线并取消重连。 |

三个操作都返回 `state`（`unconfigured/connecting/connected/disconnected/error`）、`provisioning`（`idle/connecting/saved/failed`）、`ssid`、`ip`（无可用 IPv4 时为空）、`saved`（是否有已保存配置）和 `error`（无错为空）。`wifi.connect` 的成功回执表示已受理，最终以 `provisioning=saved` 确认为准；`state=connected` 单独表示当前有连接，可能是失败后恢复了原网络。

无线驱动启动有短暂等待，路由关联与 DHCP 在后续轮询处理。试连等待约 20 秒，仅在取得目标网络 IPv4 后写独立 NVS 记录；超时、启动或保存失败时不替换原记录，有旧记录则约 10 秒后尝试恢复。开机使用最后保存的记录，掉线后尝试重连，重连不反复写 Flash。测试开始后即便 USB 会话关闭，也会继续完成。密码为开机重连保存在板端 NVS，不在电脑接线配置中；含 NVS 的读回备份须留在本机。

参数错误返回 `INVALID_ARGUMENT`；无会话的写操作返回 `SESSION_REQUIRED`；不支持的固件由 SDK 按能力拦截。异步错误 `start_failed/connect_timeout/storage_error`、链路错误 `link_lost` 和关闭错误 `stop_failed` 通过状态查询获得。清除时 NVS 写失败返回 `STORAGE_ERROR` 并保留原配置。
