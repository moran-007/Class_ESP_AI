# Class_ESP_AI v0.8.3 教学预发布

本版包含 **Python SDK 0.8.3** 和 **ESP32-S3 教学固件 0.8.0**，使用 USB 协议 v1。适合使用电脑 Python 做 GPIO、舵机、屏幕、音频及 Wi-Fi 配网实验。

## 下载哪一个

| 附件 | 用途 |
|---|---|
| `Class_ESP_AI-0.8.3-source.zip` | 完整工程、固件源码、文档和可运行示例。Windows 解压后运行 `安装Python环境.cmd` 一次即可。 |
| `ai_maker_robot-0.8.3-py3-none-any.whl` | 只需要 Python SDK 时使用。Python 3.11+，导入 `ai_robot`。 |
| `ai-maker-s3-0.8.0-native-usb-rgb48.bin` | 单独应用镜像，仅用于已核对分区的设备。 |
| `ai-maker-s3-0.8.0-native-usb-rgb48.zip` | 固件应用、引导程序、分区表、写入地址和安装说明。 |
| `release-manifest.json`、`SHA256SUMS.txt` | 核对版本、适用板型、附件大小和 SHA-256。 |

完整工程会在根目录创建并复用 `.venv`，不用再装 wheel。只安装 SDK 时，在自己的 Python 环境中运行：

```powershell
python -m pip install ./ai_maker_robot-0.8.3-py3-none-any.whl
```

需要图像或 Turtle 时，用 `python -m pip install "./ai_maker_robot-0.8.3-py3-none-any.whl[drawing]"` 替换上面的命令，并使用带 Tcl/Tk 的 Python。使用现成附件无需安装 Arduino 编译环境。

## 本版变化

- USB 配网支持中文 Wi-Fi 名称、连接进度、IPv4 查询、清除网络和开机重连。Wi-Fi 屏幕测试用电脑时间刷新。
- 屏幕绘图可预览并录制；支持将限定流程固化到板上，运行开机页和独立计数器。
- 使用统一的 Python 环境和双击入口；配网、绘图、硬件配置和测试带有可复用示例。

## 固件兼容性

附件适用于 **ESP32-S3、16 MiB Flash、8 MiB OPI PSRAM、原生 USB、GPIO48 板载 RGB**。应用为 1,283,712 字节，旧 1 MiB 应用分区装不下。已迁移到 3 MiB factory 应用区、仍从 factory 启动的板，经核对和备份后可仅更新 `0x10000` 的应用。空白板使用固件 ZIP 的分段安装说明。**不要用 Arduino 通用 Upload 或 `boot_app0.bin` 刷本项目分区。** 布局不同的板先查看 [分区与版本兼容](https://github.com/moran-007/Class_ESP_AI/blob/v0.8.3/docs/固件安装与版本兼容.md)。

软件回归与 ESP32 构建通过；已有实机配网、复位后自动重连以及板端计数验证。实际音频收放质量仍待验收；OTA 仅预留分区。附件不含 Wi-Fi 凭据、NVS 备份或整板读回。回退时请使用自己的备份和匹配原分区的固件。

[开发指南](https://github.com/moran-007/Class_ESP_AI/blob/v0.8.3/docs/开发指南.md) · [验证记录](https://github.com/moran-007/Class_ESP_AI/blob/v0.8.3/docs/verification.md)
