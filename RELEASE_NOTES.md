# Class_ESP_AI 0.5.0 教学预发布

使用电脑 Python 控制 ESP32-S3；SDK 和固件版本均为0.5.0，USB协议v1。主教程为 [开发指南](https://github.com/moran-007/Class_ESP_AI/blob/v0.5.0/docs/开发指南.md)，后续功能必须同步说明和示例。

## 下载什么

| 附件 | 用途 |
|---|---|
| ai_maker_robot-0.5.0-py3-none-any.whl | Python3.11+ SDK；pip安装，导入ai_robot |
| ai-maker-s3-0.5.0-native-usb-rgb48.bin | 匹配原板分区的应用升级，不是完整空白板镜像 |
| ai-maker-s3-0.5.0-native-usb-rgb48.zip | 上述应用、固件清单及安装/兼容说明 |
| Class_ESP_AI-0.5.0-source.zip | SDK/固件源码、构建脚本、文档和示例 |
| release-manifest.json | 版本、目标、格式、验证边界与附件校验信息 |
| SHA256SUMS.txt | 所有上述附件的SHA256 |

```powershell
python -m pip install ./ai_maker_robot-0.5.0-py3-none-any.whl
```

图片/Turtle选装同一wheel的 `[drawing]`，且Python需带Tcl/Tk。安装SDK不需要Arduino；重编固件才需要固定Arduino工具链。新程序直接 `from ai_robot import Robot`，不需要复制 `_board.py`。

## 本版能力

- 数字IO、ADC输入、PWM独立；板载RGB、最多4舵机，信号按允许的空闲GPIO配置。
- ST7735S/ST7789屏幕、中文和图形/图片、页面编辑器/默认页、标准库Turtle发送。
- INMP441/MAX98357A，原生USB半双工收音/播放；本地WAV/显式URL统一AudioClip，PCM16LE/16000Hz/mono，一次最多30秒。
- 11个可单独复制的portable示例，主开发指南有用途、参数、代码解释与限制。

## 固件与实物边界

构建目标ESP32-S3、16MiB Flash、8MiB OPI PSRAM、原生USB、WS2812 GPIO48。应用688832字节；已验证的现有板factory从0x10000开始、长度1MiB。**只有核对本机芯片/分区且已有恢复条件时才能使用应用升级路径。** 不能把应用写到0x0，不能用编译参考merged镜像直接覆盖原板。空白板首次安装需另行按匹配板卡流程处理，本版不提供一键空白板包。

软件回归、ESP32目标构建、独立wheel和实际板端配置检查通过；历史舵机/屏幕已有用户确认。**真实收音、功放出声、录音回放质量仍待接线验收**，因此作为教学预发布。没有DAC模拟输出、全双工对讲、压缩音频解码、AI服务器/ASR/TTS、OTA或定制PCB制造文件。

## 回退与隐私

源码与附件不包含本机备份、NVS、整板读回、venv、输出报告或录音。需要回退时，安装已验证旧wheel，固件使用自己备份的匹配原分区旧应用。不要用他人的NVS恢复自己的设备。
