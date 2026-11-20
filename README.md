# AI小创客本地固件与Python SDK

独立仓库：**Class_ESP_AI**。初学者从 [Python编程与开发指南](docs/开发指南.md) 开始，包含配置、可复制示例和逐项解释；维护者遵循 [功能与文档同步规则](CONTRIBUTING.md)。当前源码接口见 [V0.6 SDK函数手册](docs/SDK函数说明与示例_V0.6.md)，固件附件的适用对象、分区和升级前提见 [固件安装与版本兼容](docs/固件安装与版本兼容.md)。

当前源码为 **Python SDK 0.8.3 / ESP32-S3 固件 0.8.0**。完整工程在 Windows 只需运行一次 [安装Python环境.cmd](安装Python环境.cmd)，所有示例使用根目录 `.venv`。

**USB Wi-Fi 配网**：双击 [配置硬件.cmd](配置硬件.cmd)，在「串口」页选择端口、输入 Wi-Fi 名称和密码。也可用 `robot.setwifi(name, password)`，控制台会显示连接进度与 IP。配网、查询、清除和屏幕状态页都在 [Wi-Fi 测试目录](tests/wifi/README.md)。

**0.7.0 新增板端计数显示**：`Program.display.counter(...)` 固化后可独立运行。见 [16_counter.py](examples/portable/16_counter.py) 和 [参数/恢复说明](docs/数字累加计数器_V0.7.md)。实际版本和验证状态见 [验证记录](docs/verification.md)。

本地0.7安装包为`sdk/python/dist/ai_maker_robot-0.7.0-py3-none-any.whl`，应用为`build/counter-native-usb/ai_maker_s3.ino.bin`。计数测试的清除和恢复之前备份流程入口在 [tests/counter](tests/counter/README.md)；恢复旧流程与只清除计数是两个不同操作。

SDK **0.6.1** 新增 `robot.program.begin()` / `end()`：屏幕绘图同步预览并录制，结束后 `save(loop=True, autostart=True)`；该录制层兼容0.6.0及以上固件，单用录制无需重刷。完整例子为 [15_screen_record.py](examples/portable/15_screen_record.py)，逐项解释见 [录制与固化说明](docs/绘图录制与固化_V0.6.1.md)。本地安装包为`sdk/python/dist/ai_maker_robot-0.6.1-py3-none-any.whl`，GitHub旧附件不自动升级。

**此前0.6.0已完成本地实现、软件回归、目标编译和COM5升级；屏幕A/B固化、清除复位及原默认页恢复均已通过，实屏效果经用户确认；0.6尚未发布GitHub附件。** 新增`Program`和`robot.program.save(...)`，支持把白名单硬件流程保存到ESP32，启用后下次通电独立执行；电脑连接可接管继续写新代码。不是任意Python函数固化。见 [固化教程](docs/开发指南.md#15-程序固化通电后独立运行)、[MicroPython与当前方案](docs/MicroPython与当前方案.md) 和 [12～14示例](examples/portable/README.md)。屏幕实测文件及清除说明见 [tests/standalone](tests/standalone/README.md)，逐项结果见 [验证记录](docs/verification.md)。首次使用需要支持0.6的固件，之后修改支持流程无需每次重刷。以下0.5发布链接和历史证据继续保留，不代表旧附件已自动升级。

0.6 历史构建产物为 `sdk/python/dist/ai_maker_robot-0.6.0-py3-none-any.whl` 和 `build/standalone-native-usb/ai_maker_s3.ino.bin`，不随源码分发。当前设备升级请使用下面的最新分区说明。

已有 [GitHub Releases](https://github.com/moran-007/Class_ESP_AI/releases/tag/v0.5.0) 附件是历史教学预发布 0.5.0；当前源码不含本机 `build/` 或 `dist/` 产物。需要配网和计数等新功能，请以本分支的源代码、安装入口和固件构建说明为准。

```powershell
python -m pip install "https://github.com/moran-007/Class_ESP_AI/releases/download/v0.5.0/ai_maker_robot-0.5.0-py3-none-any.whl"
```

COM5 已升级到 0.8.0 配网固件和自定义 16 MiB 分区，保留了原接线、页面和计数程序。OTA 仅预留槽位；当前仍使用 USB 升级。GitHub 已发布版本仍为 0.5.0。

V0.5新增 **INMP441收音、MAX98357A播放、数字/ADC/PWM分开接口及可跨电脑安装的SDK**。先按实际接线改 [portable示例](examples/portable/README.md) 的COM和IO，再双击 `运行音频测试.cmd`。本地文件、录音和显式URL音频统一为16kHz/mono/PCM16LE的AudioClip；不包含AI服务器。详见 [IO与音频测试说明](docs/数字模拟IO与音频测试_V0.5.md) 和 [跨电脑安装](docs/跨电脑安装与直接导入_V0.5.md)。当前COM5已更新V0.5，仅验证音频配置与资源保护；实际收音/出声待用户接线测试。

V0.4新增 **本地网页页面编辑器、板端默认页面、标准库 Turtle 电脑画图并发送到屏幕**。双击 `打开页面编辑器.cmd` 或 `打开Turtle绘图.cmd` 即可使用；推荐在Python文件中用 `connect("COM5")` 和外设 `configure(...)` 指定串口与IO；配置窗口/JSON仍可选。详细步骤、短代码和限制见 [页面与Turtle说明](docs/页面编辑器与Turtle_V0.4.md)。V0.4历史测试中，保存页面、复位恢复默认页和整屏图片通信验证通过，用户确认默认页文字、图标和颜色正常。

V0.3新增 **ST7735S / ST7789 屏幕**：SPI信号和BLK引脚全部可配置，支持纯色、中文、矩形、线段与GPIO背光。先用 [配置硬件入口](配置硬件.cmd) 填写屏幕接线，再运行 [纯色测试](tests/quick/screen_colors.py) 或双击 `运行屏幕测试.cmd`。型号、7/8针接法与自定义引脚见 [屏幕使用说明](docs/屏幕测试与自定义引脚_V0.3.md)。

**V0.2.1 修复原生 USB 长请求丢失导致的舵机 config.apply 超时。** 当前 COM5 已更新；原生 USB 和 UART 均在启动前配置 8192 字节 RX 缓冲。GPIO14 的舵机配置保存与完整读回已实机通过，用户随后确认 SG90 能来回转动。详见[排查记录](docs/舵机配置超时排查_V0.2.1.md)。

当前已识别的板卡使用原生 USB COM5、GPIO48 板载 RGB。主教学固件为 `ai-maker-s3`，支持 SDK；之前的上电白灯版 `ai-maker-led-diagnostic` 是独立诊断程序。两者使用不同协议，不能混用脚本。实际安装与测试证据见[验证记录](docs/verification.md)。

## 直接运行：优先使用这里

跨电脑或新课程优先直接 `from ai_robot import Robot, AudioClip`，不需要_board或本工程路径。安装包为 `sdk/python/dist/ai_maker_robot-0.5.0-py3-none-any.whl`，本机已安装。音频入口为 [运行音频测试.cmd](运行音频测试.cmd)，可直接复制运行的文件位于 [examples/portable](examples/portable/README.md)。本机已编译并写入的V0.5应用位于 `build/audio-native-usb/ai_maker_s3.ino.bin`；不要把参考merged.bin直接写入当前板。

组合顺序：先audio/display/servo.set → robot.start → digital/analog/pwm.set → 动作。下方保留原工程内便捷课程入口。

SDK0.4.1新增 `robot.display.set(...)`、`robot.servo.set(pin=14)` 和 `robot.start()`：支持常见屏幕丝印别名及位置参数，可不使用with；多个外设先set再统一start。`fps`仅限制电脑端整屏图片发送上限。详见 [set接口、丝印与刷新帧率](docs/set接口_丝印对照与刷新帧率.md)，组合示例为 `tests/guide/12_multi_parts.py`，测速示例为 `13_display_fps.py`。旧configure/with写法继续支持，无需重刷固件。Turtle也可在开头配置，结尾 `finish(screen, robot=robot)` 复用连接，完整示例 `tests/guide/14_turtle_top_setup.py`。

现在优先使用**代码内配置**：[运行示例.cmd](运行示例.cmd) 打开 [tests/guide](tests/guide/README.md) 中的实验。串口直接写 `connect("COM5")`，IO直接写 `robot.display.set(SCL=4, SDA=5, ...)` 等命名参数，无需JSON。详见 [代码内配置与最小示例](docs/代码内配置与最小示例.md) 和 [完整SDK函数手册](docs/SDK函数说明与示例_V0.5.md)。原 [统一配置窗口](配置硬件.cmd) 与 [hardware.json](config/hardware.json) 仍可选，配套示例在 `tests/guide_shared/`；旧手写实验保留。

1. 双击根目录的 **安装Python环境.cmd**（本机已准备好 `.venv`，以后通常不需要重复安装）。
2. 双击 **运行示例.cmd** 选择实验，串口和IO就在对应Python文件的参数中；板载RGB只需USB。
3. 自己写代码时，打开 `tests/guide/` 内的 `.py` 文件点击运行。IDE 解释器选择 `.venv/Scripts/python.exe`。这些短文件不需要命令行参数。

主示例 `tests/guide/01_info.py`、`02_rgb.py` 只需USB。其他文件先完成外设接线，直接修改 `connect("COM5")` 和 `pin=.../sck=...` 等参数。`tests/quick/` 保留历史手写实验，`tests/guide_shared/` 保留可选集中配置版；旧08会清除全部舵机映射。

```python
from _board import connect

with connect("COM5") as robot:
    robot.led.color("red")
    robot.wait(2)
```

上面的文件保存在 `tests/guide/` 中即可运行。连接、心跳和退出释放由公共模块及 SDK 处理。[简易测试说明](tests/quick/README.md)列出了每个文件的接线与作用；[完整上手说明](docs/快速上手与板级固件V0.2.md)解释固件、引脚和换线流程。

## 已实现范围

| 功能 | 固件 / SDK0.5.0 状态 |
|---|---|
| USB JSONL、版本握手、请求与错误回执 | 已实现 |
| GPIO 输入、上下拉、输出及释放 | 已实现 |
| ADC 原始 12-bit 读数 | 已实现，未作电压精度与校准验收 |
| PWM | 已实现，固定 1 kHz、0～100% 整数占空比，最多 4 路；配置GPIO背光后为3路 |
| 位置舵机 | 已实现，最多 4 路、50 Hz、逻辑名称、可配置引脚和校准范围 |
| 维护、配置修订、持久保存 | 已实现，写入独立 NVS 命名空间 |
| 会话与停止 | 每秒 SDK 心跳，6 秒租约，关闭或到期释放运行输出 |
| 板载 RGB 灯 | GPIO48 默认、可明确构建 GPIO38；GRB 帧与 LOW 复位，检查 RMT 错误，上电主动熄灯 |
| Python 安装包与示例 | 基础、屏幕、页面和Turtle短脚本，颜色名称与等待接口、双击入口；保留原进阶 API |
| 屏幕 | ST7735S128×160、ST7789240×320/240×240；可保存SPI映射、四向旋转、中文、图形和可选BLK PWM |
| 页面编辑器与开机页 | 电脑本地网页拖拽编辑、JSON导入导出、图标上传；页面保存板端，启用后复位或关闭会话恢复默认页 |
| 标准库Turtle／整屏图片 | 原生电脑窗口画图，点击发送或Enter，适配当前屏幕；临时画面，关闭窗口恢复已启用默认页 |
| 麦克风、功放 | INMP441 / MAX98357A I²S驱动、会话IO映射、半双工录放已实现；原生USB；实际声学验收待接线 |
| 数字/模拟IO | digital数字量、analog ADC、PWM占空比独立；真正DAC模拟电压输出不支持 |
| 本地/云端音频数据 | 相同AudioClip，严格PCM/WAV、显式有界HTTP音频URL；非AI云服务 |
| SD、任意学生网页上传 | 尚未实现，能力声明false |
| Wi-Fi | USB 配网、状态和 IPv4 查询、开机重连 |
| AI、云端、无线控制、OTA | 未实现 |

普通 GPIO、舵机和屏幕SPI信号映射现已实现；I²S音频已接入当前会话的共享时钟映射，退出会话清除，不自动收音。屏幕SPI目前独占，不与其他SPI设备共享。回执不能替代实际屏幕图像验收。

## 目录

```text
ai_maker/
├── firmware/
│   ├── ai_maker_s3/       # Arduino入口、生产协议核心、真实ESP适配
│   ├── led_diagnostic/    # 单独GPIO常高与固定RGB诊断，非SDK固件
│   └── build.ps1          # 只编译，不烧录
├── sdk/python/           # ai_robot源码、pyproject、SDK与联调测试
├── editor/               # 本地网页编辑器，不依赖AI服务
├── protocols/usb-v1.md   # 固件与SDK共同遵守的协议
├── examples/             # 状态、GPIO、舵机、板载RGB示例
├── scripts/              # 主机编译、测试、真机RGB验证工具
├── tests/native/         # 同一生产C++核心的主机测试与模拟适配
├── tests/hardware/       # 可自行运行的真机脚本与操作参考
├── tests/quick/          # 学员直接运行的短Python文件
├── docs/                 # 验证记录与后续任务
├── build/                # 按UART或原生USB分开的固件产物与清单
├── build-native/         # 主机测试程序
└── backups/              # 本地硬件备份，已忽略，可能含设备私有数据
```

## 硬件和构建基线

已安装并用于验证的工具链：Arduino CLI 1.4.1、Arduino-ESP32 3.3.12、ArduinoJson 7.4.3；主机测试使用 C++17 编译器。Python 代码要求 3.11 或以上，本机测试使用 Python 3.14。

构建目标为 ESP32-S3、16 MiB Flash、OPI PSRAM，使用 [自定义教学分区](docs/固件安装与版本兼容.md)。默认原生 USB，启用 Hardware CDC；UART 构建使用开发板 USB 转串口的 UART0。两种镜像的通信端点不同，不能仅按文件名混用。已有数据的板不要使用 Arduino 默认 Upload，以免写入项目 NVS。

新工程没有依赖旧 AI 模型、旧密钥或服务器。虽然基础程序体积较小，没有存储更小开发板的完整验证记录，不能把参考镜像直接当作通用 S3 固件。

### 编译固件

在当前 `ai_maker` 目录执行：

```powershell
.\firmware\build.ps1 -Transport uart
.\firmware\build.ps1 -Transport native-usb
# 当板载RGB实际接GPIO38时
.\firmware\build.ps1 -Transport uart -BuiltinRgbPin 38
```

脚本核对核心和 ArduinoJson 版本，产物位于 `build/uart`、`build/native-usb`，同时生成包含 FQBN、分区标识、文件大小和 SHA256 的 `build-manifest.json`。构建不会自动上传或接触串口。

首次安装通常需要匹配的 bootloader、分区和应用；更换已有设备固件前应读取实际分区和备份必要区域。本次硬件验证采用保留现有分区、仅写入可容纳的应用分区的专门流程，不能据此照抄为其他板的通用烧录步骤。

## 安装SDK和查询设备

Windows 上双击 [安装Python环境.cmd](安装Python环境.cmd)。安装只使用项目根目录的 `.venv`；再次运行会先检查，环境正常就复用，不会重装。运行示例、配置窗口、页面编辑器和本机测试都用这一份环境。

```powershell
.\.venv\Scripts\python.exe .\examples\device_status.py --port COM5
```

用 VS Code 打开 `ai_maker` 文件夹，选择 `.venv/Scripts/python.exe`。如果之前选过旧解释器，切换一次即可；也可在「运行和调试」选「AI 小创客：运行当前 Python 文件」，它固定使用项目环境。

把 COM5 换为实际端口。查询也会连接并握手，但不会配置普通输出或移动舵机。`AUTO` 只有在唯一 USB 串口候选时才选择，不自动遍历控制其他串口设备。

已有 AI 机器人 2.1.6 固件不实现此教学协议，必须安装兼容教学固件后使用本 SDK。开串口可能因开发板驱动触发复位；握手超时后显式重连，不自动重发动作。

```python
from ai_robot import Robot

with Robot(port="COM5") as robot:
    print(robot.get_info())
    print(robot.get_status())
    print(robot.list_pins())
```

SDK API、维护换线示例及异常说明见 [SDK说明](sdk/python/README.md)。协议细节见 [USB协议](protocols/usb-v1.md)。

## 板载RGB测试

默认通用 S3 构建将 RGB 定义为 GPIO48，可通过 `-BuiltinRgbPin 38` 生成 GPIO38 版本；不能从芯片标识自动推断实际板载接线。RGB 接口只允许控制所选命名设备，没有开放保留引脚的任意写入。

```powershell
python .\examples\builtin_rgb.py --port COM5 --run
```

使用低亮度红绿蓝指令，默认完成后熄灯。USB 回执和状态查询只证明程序执行了灯控制指令；是否真的发光、颜色顺序是否正确，需要实物观察。

更完整的自动记录工具：

```powershell
python .\tests\hardware\02_builtin_rgb.py --port COM5 --run --lease-test
```

该工具仅调用设备查询与板载 RGB 接口，记录指令、状态及 6 秒租约到期后的清零，不配置其他引脚或舵机。它不会烧录设备。没有 `--run` 时不连接设备。

独立测试文件、原项目红灯/黄灯参考模式、完整运行命令和故障排查见 [真机测试说明](tests/hardware/README.md)。

## 换线和配置

初次启动为空舵机列表，不输出舵机脉冲。合法信号引脚可以更换；保守板级描述保留启动、Flash/PSRAM、原生 USB、UART0 与板载 RGB 资源。

GPIO.setup 的模式和引脚只属于当前会话。舵机映射保存在独立 NVS 记录中，必须经过维护流程修改：

1. 连接设备，进入维护并确认成功；停止当前会话输出，保存维护标记。
2. 断电换线。重新上电仍保持维护状态。
3. 查询最新配置修订，保存合法的新映射。
4. 核对供电、实物接线和校准范围，显式退出维护。
5. 显式发送动作，再观察效果。配置保存、重启和退出维护都不自动移动。

`servo.configure` 会进入并保持维护，不能代替换线之前的操作。保存失败或配置损坏会停留在维护，不自动格式化，也不盲目按旧映射驱动已经改过的接线。

舵机使用匹配电压与峰值电流的电源支路，非隔离连接按方案共地。GPIO 仅作信号，不能用开发板 3.3 V 稳压器给舵机供电。普通舵机没有位置反馈，`position_verified=false`；释放 PWM 不切断电源，也不保证悬挂负载安全。

## 会话和已知边界

默认 SDK 每秒心跳；设备 6 秒没有收到有效身份的会话操作就撤销 PWM、舵机脉冲及 RGB 指令，并将会话 GPIO 恢复输入高阻。正常关闭执行同样释放。上电和断连不会自动重新执行旧动作。

RGB 驱动失败时不能保证实际熄灯。`device.status.led.driver_ok=false` 表示最后驱动失败，颜色字段保留最后成功指令，不能解读为当前物理颜色；显式停止/关闭返回 `HARDWARE_ERROR`。RMT 发送超时后锁定缓冲区，需要复位板卡恢复；GPIO 和舵机释放仍会执行。

公开状态查询不续租，其他会话不能接管活跃会话。请求超时表示结果未知，SDK 不自动重试动作。本版仅面向物理可信的 USB 实验，不含学生教师身份隔离、远程授权或固件安全发布系统。

普通输出模式的 `gpio.read` 返回最后指令值，附带 `source=commanded`，不冒充物理电平测量；数字输入为真实读取。PWM 占空比从状态中查询。ADC 返回原始计数，读后恢复数字输入路径，未提供校准伏特值。

## 软件验证

```powershell
.\scripts\test.ps1
```

脚本先用真实生产 `device_core.cpp` 编译并运行 C++ 测试，再让 Python SDK 通过子进程连接同一核心进行联调。测试不会打开真实串口。构建目录、虚拟环境和本地备份由本目录 `.gitignore` 排除。

学员可自由修改 `tests/quick/01`～`08`，默认回归不自动执行这组可编辑课程文件；需要检查当前示例时显式运行 `scripts/test.ps1 -IncludeExamples`。SDK、核心、新增 SG90 示例和长帧探针的独立回归仍默认执行。

测试与实机结果分别记录于 [验证记录](docs/verification.md)。后续工作见 [后续任务](docs/next_steps.md)。
