# V0.3 使用入口

> 配置入口已统一：使用项目根目录 `配置硬件.cmd` 或 `config/hardware.json`。旧settings.py和_screen_settings.py只作兼容读取；下文相关旧配置操作以 `docs/统一配置与接线说明.md` 为准。

当前开发板已更新为 **ai-maker-s3 0.3.0 教学固件**，COM5原生USB、GPIO48。屏幕信号可自定义，先修改 `_screen_settings.py` 再运行新屏幕脚本，详见 [屏幕说明](../../docs/屏幕测试与自定义引脚_V0.3.md)。下文诊断白灯属于历史，只有重新安装诊断固件后才能运行03。当前优先使用 [简易测试](../quick/README.md) 或根目录 `开始测试.cmd`。

当前应用固件：`build/native-usb/ai_maker_s3.ino.bin`。完整文件位置和环境安装见 [快速上手说明](../../docs/快速上手与板级固件V0.2.md)。V0.2 已在当前板运行简易 01/02 和本目录 02 的颜色/租约检查；当轮未重新确认实际发光颜色，外接 GPIO、ADC、PWM、舵机仍待接线验收。

本目录为进阶参数化测试，`tests/quick/` 才是供学员点击运行的简短文件。两者均不会自动烧录。

新增 `04_usb_rx.py` 为只读长帧回归：直接运行或加 `--port COM5`，只查询设备，不建立控制会话、不改配置、不驱动舵机，依次验证160～4096字节的 JSON 查询帧。V0.2.0 的原生 USB 长帧失败，V0.2.1 同样探针全部通过。完整原因及配置读回证据见 [V0.2.1排查记录](../../docs/舵机配置超时排查_V0.2.1.md)。

---

# 历史排查与进阶测试操作说明

本文件夹放置可以自行运行的真机测试。脚本不烧录固件、不启动 AI 服务器。先按下表匹配教学或诊断固件，并确认实际串口、USB通路及板载RGB接线。

当前连接已由外置FTDI的COM3改为板载原生USB的COM5，核验为同一颗芯片。**COM5应匹配native-usb构建；原UART构建即使能从COM5烧录，也不会把应用日志发到这个USB口。**

| 物理连接 | 本次端口示例 | 构建参数 |
|---|---|---|
| 外置FTDI等USB转UART | 原COM3 | `-Transport uart` |
| ESP32-S3原生USB Serial/JTAG | 当前COM5 | `-Transport native-usb` |

每次换线或换USB口后先运行`python -m serial.tools.list_ports -v`。端口编号不是GPIO编号，也不等于串口输出路径已经匹配。

本次已由实际观察确认：**当前板使用GPIO48，COM5原生USB，RGB固定白色可以点亮。** 独立诊断脚本默认选择`--mode rgb --pin 48`。以下命令仅在安装诊断固件后使用：

```powershell
python .\tests\hardware\03_led_diagnostic.py --port COM5 --run
```

## 1 运行哪个文件

| 文件 | 用途 | 是否发送灯控制指令 |
|---|---|---|
| [01_device_status.py](01_device_status.py) | 查询版本、配置、可用引脚和状态 | 否；建立并关闭自己的会话 |
| [02_builtin_rgb.py](02_builtin_rgb.py) | 红绿蓝或原项目状态颜色测试，可选超时测试 | 是，必须添加 `--run` |
| [03_led_diagnostic.py](03_led_diagnostic.py) | 独立诊断固件的GPIO常高、RGB固定白色及关闭 | 是，必须添加 `--run` |

三个脚本没有 `--run` 时都不连接设备。不要同时运行多个测试、串口监视器或另一个 Python 控制程序。01/02使用教学SDK；03只操作独立诊断固件允许的GPIO38/48候选引脚，不探测其他引脚，不操作舵机、麦克风、功放或显示。

**固件与脚本要匹配。** `ai-maker-s3` 教学固件使用01/02；`ai-maker-led-diagnostic` 常高诊断固件使用03。烧入诊断固件时，普通SDK握手不再适用。当前板所装的实际诊断状态见[验证记录](../../docs/verification.md)。

### 常高诊断怎么运行

若板上已安装单独的 `led_diagnostic` 固件，从ai_maker目录运行：

```powershell
# GPIO38保持高电平，串口反馈含read_level=1
.\.venv\Scripts\python.exe .\tests\hardware\03_led_diagnostic.py --port COM5 --run --mode high --pin 38

# 显式选择另一候选引脚GPIO48
.\.venv\Scripts\python.exe .\tests\hardware\03_led_diagnostic.py --port COM5 --run --mode high --pin 48

# 本块板已确认的固定白色数据帧，与常高电平是不同测试
.\.venv\Scripts\python.exe .\tests\hardware\03_led_diagnostic.py --port COM5 --run --mode rgb --pin 48

# 清除当前诊断输出
.\.venv\Scripts\python.exe .\tests\hardware\03_led_diagnostic.py --port COM5 --run --mode off
```

常高模式启用输出和数字输入回读；读回1证明引脚逻辑电平为高，不证明灯已亮。WS2812这类单线RGB像素靠数据帧设置颜色，持续高电平通常不会直接点亮。RGB模式发送固定白色，不做轮换；常高模式直接输出HIGH，不发送颜色数据。

RGB颜色写入后由灯内部保持，数据线通常空闲为LOW。因此RGB模式的`read_level=0`不表示灯已经关闭。最新诊断固件会报告RMT的`driver_error`、`cleanup_ok`及`previous_release_error`；驱动错误和实际灯光仍是不同的检查层次。

最新诊断固件默认上电即GPIO48固定白色，没有SDK心跳和6秒租约。脚本退出后固件不主动清除状态；复位会恢复开机的固定白色。需要停止时显式使用`--mode off`，或恢复教学固件。`--mode high`保留为单独的电平诊断，不能用于证明RGB发光。诊断固件不作为普通课程的保护与权限实现。

单独编译诊断固件，不自动烧录：

```powershell
.\firmware\build_diagnostic.ps1 -Transport native-usb
```

原生USB输出在`build/led-diagnostic-native-usb`；`-Transport uart`输出在`build/led-diagnostic`。诊断与教学固件源码分别保留。

### 恢复旧教学固件的历史记录

当时核实原 COM3、后来的 COM5 对应同一块板，旧 factory 分区为 `0x10000` 起的 1 MiB。**当前教学固件已超过 1 MiB，不能用旧命令覆盖。** 恢复已有开发板时，先查实际分区，再按 [固件安装与版本兼容](../../docs/固件安装与版本兼容.md) 选择可用的应用镜像；使用自己的备份恢复旧版本。完成写入校验后，先运行 01 查询到 `ai-maker-s3`，再使用 02。

## 2 首次准备Python环境

需要 Python 3.11 或以上。在 Windows 双击项目根目录的 [安装Python环境.cmd](../../安装Python环境.cmd)，硬件测试使用同一个 `.venv`，不用在测试目录再建环境。

首次安装需要取得依赖 `pyserial`；安装好后，本地 USB 测试不需要互联网。脚本也能从本工程源码直接加载 SDK，但运行环境仍需安装 pyserial。不要把原 AI 固件的串口维护命令当成教学协议。

只需查看参数、不接触设备：

```powershell
.\.venv\Scripts\python.exe .\tests\hardware\02_builtin_rgb.py --help
```

## 3 确认串口和固件

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
.\.venv\Scripts\python.exe .\tests\hardware\01_device_status.py --port COM5 --run
```

将示例端口换成实际端口。最初为COM3，换成原生USB后为COM5；Windows重新插入、更换USB口时还可能改变编号。蓝牙COM口不是这里的目标。

正确返回中应有：

- `firmware_family` 为 `ai-maker-s3`，`firmware_version` 为 `0.1.0`；
- `protocol_version` 为整数 1，`capabilities.builtin_led` 为 true；
- `builtin_led.pin` 给出固件当前控制的 RGB GPIO；
- `maintenance` 为 false 才能执行灯测试。若为 true，先核对配置与维护原因，不为消除提示而盲目退出。

没有匹配固件会超时或明确拒绝握手。读到了串口，不表示已经连接正确协议设备。

## 4 运行红绿蓝测试

```powershell
.\.venv\Scripts\python.exe .\tests\hardware\02_builtin_rgb.py --port COM5 --run
```

默认两轮，每色保持 3 秒；每个颜色的分量值为 8，采用低亮度。预期能依次观察红、绿、蓝，然后熄灭。控制台会打印请求与状态是否匹配，并生成 `tests/hardware/reports/hardware-rgb.json`。

延长时间便于观察：

```powershell
.\.venv\Scripts\python.exe .\tests\hardware\02_builtin_rgb.py --port COM5 --run --cycles 3 --hold 5
```

可以用 Ctrl+C 中断。正常退出会请求释放会话；异常断连后由固件 6 秒租约作为释放后备。释放灯信号与实际灯损坏、供电断开等不同，仍需观察实物。

## 5 对照原项目收音与思考颜色

原项目的 `setState` 使用同一个 `rgbLedWrite` 驱动：收音 `(28,0,0)`，思考 `(18,10,0)`，播放 `(0,22,0)`。本仓库的测试只复现这些颜色，不依赖原项目源码，也不开启录音、识别或 AI。

```powershell
.\.venv\Scripts\python.exe .\tests\hardware\02_builtin_rgb.py --port COM5 --run --pattern states --cycles 2 --hold 4
```

预期顺序：收音参考红色 → 思考参考黄色 → 播放参考绿色，重复两轮后熄灭。黄色混色的具体色调与 RGB 灯、亮度和通道顺序有关。

## 6 测试会话超时自动熄灯

```powershell
.\.venv\Scripts\python.exe .\tests\hardware\02_builtin_rgb.py --port COM5 --run --lease-test
```

流程为：

1. 正常心跳下运行红绿蓝并熄灭。
2. 新建一个不发送后台心跳的测试会话，设置低亮度白色。
3. 等待约 6.4 秒，仅查询公开状态。
4. 确认 `session_active=false`，三色指令均为 0，并观察实际灯是否熄灭。

只有这个专门阶段关闭心跳。普通长时间显示颜色时保持心跳，避免把租约到期误以为灯或固件故障。

## 7 为什么GPIO48没有变化

仅有 ESP32-S3 芯片标识无法判断开发板 RGB 引脚。乐鑫 DevKitC-1 早期版本使用 GPIO48，v1.1 使用 GPIO38；其他厂家还可能不同。原代码中的 `RGB_BUILTIN` 来自编译所选开发板定义，不能直接把这个别名值当成排针 GPIO 编号。[官方板型资料](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp-dev-kits-en-master-esp32s3.pdf)

本轮增加两种明确的构建选择，下面命令只编译：

```powershell
# GPIO38版本
.\firmware\build.ps1 -Transport uart -BuiltinRgbPin 38

# GPIO48版本
.\firmware\build.ps1 -Transport uart -BuiltinRgbPin 48
```

对应输出为 `build/uart-rgb38` 与 `build/uart`。切换这个参数需要匹配应用写入流程，测试脚本本身不会改固件或修改引脚。烧录前需核对目标、现有分区、镜像大小和备份；本项目不提供一条忽略现有数据的自动通用刷机命令。

COM3首轮虽有指令回执，用户未看到灯亮，不记为该轮光学通过。切换并匹配COM5原生USB后，GPIO48固定白色已有用户确认。本块板使用GPIO48；GPIO38仅作为其他板型的明确候选，不再默认用于本块板。仅凭芯片型号不能推广到所有开发板。

## 8 结果怎样判断

| 检查项 | 软件能够证明 | 仍需观察或测量 |
|---|---|---|
| 串口握手 | 收到匹配协议和家族的响应 | 无 |
| 颜色设置 | 指令被接受，固件状态一致 | 灯是否亮、颜色是否正确 |
| 超时释放 | 会话到期、指令归零 | 实物灯是否熄灭 |
| GPIO/ADC/PWM/舵机 | 本轮只有软件和模拟适配器验证 | 真实电平、波形、精度、行程和负载 |

回执 `state=commanded` 和 `physical_verified=false` 不表示驱动失败，它明确表示没有光学反馈。报告中的 `software_result=passed` 也不能覆盖人工反馈“没有变化”。

如需保留多次报告，可以指定不同文件：

```powershell
.\.venv\Scripts\python.exe .\tests\hardware\02_builtin_rgb.py --port COM5 --run --pattern states --report .\tests\hardware\reports\rgb_states_my_board.json
```

## 9 常见故障

| 现象 | 检查方法 |
|---|---|
| 找不到 ai_robot 或 serial | 使用安装 SDK 的同一 Python 解释器；检查虚拟环境路径 |
| 无法打开串口 | 关闭串口监视器和其他控制程序；核对端口、USB数据线及驱动 |
| RequestTimeout | 确认板上是教学固件；开发板可能因开串口复位，等待启动后显式重连 |
| DEVICE_BUSY | 另一个会话仍在运行；先关闭它或等待租约到期 |
| MAINTENANCE_REQUIRED | 读取状态和配置，按维护流程处理，不能直接跑动作 |
| 回执正常但灯不变 | 核对 builtin_led.pin、开发板版本、RGB供电与实际引脚 |
| 颜色顺序不对 | 记录实际顺序，核对灯型号与RGB/GRB顺序，不用改颜色名称掩盖 |
| 指令一段时间后归零 | 检查心跳是否关闭、USB是否断开，区分正常租约与灯故障 |

其他软件验证、固件状态和实际备份范围见 [完整验证记录](../../docs/verification.md)。未经外设实测，不把本文件夹的 RGB 测试结果推广为全部硬件通过。
