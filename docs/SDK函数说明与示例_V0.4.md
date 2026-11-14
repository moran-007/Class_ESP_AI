# AI小创客 Python SDK 函数说明、示例与配置要求 V0.4

> 本篇保留V0.4历史接口说明。当前V0.5新增数字/模拟分类及音频，参见 [V0.5手册](SDK函数说明与示例_V0.5.md)；旧文“音频未实现”只描述当时版本。

适用版本：`ai-maker-s3` 教学固件 0.4.0、`ai-maker-robot` Python SDK 0.4.1，USB协议v1。更新日期：2026-11-11。

本文将“AI函数”按本项目当前的全部公开SDK接口整理。现阶段可运行的是本地板级控制、屏幕、页面和Turtle；语音识别、聊天、模型推理、麦克风录音与功放播放尚未实现，不能将下面的设备控制接口理解为已接入AI服务。

## SDK0.4.1新增：set、统一启动与图片帧率

| 调用 | 参数与行为 |
|---|---|
| `robot.display.set(sck=None, mosi=None, cs=None, dc=None, rst=None, backlight=None, *, panel="st7789_240x320", rotation=1, invert=None, brightness=None, fps=None, **labels)` | 前六个参数也可按位置传GPIO；接受大小写无关的SCL/SDA/RES/BLK等丝印名。保存接线、停止运行输出并保持维护，不开始绘图。省略IO使用旧configure参考默认值，不读取JSON |
| `robot.servo.set(pin, *, name="test", min_angle=30, max_angle=150, min_pulse_us=1000, max_pulse_us=2000)` | SG90课堂预设的短配置；同名替换、异名保留其他映射；不移动。与旧configure默认500～2500µs不同 |
| `robot.start()` | 查询当前状态，必要时退出维护，初始化本连接中display.set请求的屏幕；不自动输出舵机脉冲。重复调用不重置已激活显示和舵机。返回maintenance=False、display初始化回执或None |
| `robot.display.image(...)`新增返回 `transfer_seconds` | 最后一帧分块传输耗时，排除图片缩放、帧率等待及面板扫描；其余参数/返回字段保留 |

先全部set，再start，再动作。set配置过程中会停止其他运行输出，不能把它当作不停机更新；重配置后需start并重新发送需要的动作。每个set保存各自配置，不构成多设备一次性原子事务。现有configure、maintenance、begin和with写法仍有效。

`fps`是1～60整数或None，仅在本连接内为display.image的帧开始限速，不写NVS，不设置面板扫描率，也不限制text/line/rect/bitmap。实际速度可能低于设定。完整丝印表、无with清理和测速方法见 [set接口_丝印对照与刷新帧率](set接口_丝印对照与刷新帧率.md)。下文保留完整底层configure等接口，便于进阶操作。

## 1. 从哪里开始

1. 在项目根目录运行 `安装Python环境.cmd`。IDE解释器选择 `ai_maker/.venv/Scripts/python.exe`。
2. 推荐在当前Python文件直接写 `connect("COM5")` 指定串口，在 `gpio.setup(pin=...)`、`servo.set(pin=...)`、`display.set(SCL=..., SDA=...)` 中指定IO。详见 [代码内配置与最小示例](代码内配置与最小示例.md)。统一JSON配置保留为可选方式。
3. 打开 `tests/guide/` 中的一个短文件运行。每次只运行一项，先确认该项接线与供电。
4. 改接线前：进入维护并确认成功 → 断电换线 → 上电 → 保存匹配配置 → 退出维护 → 测试。

| 示例文件 | 内容 | 最低外设要求 |
|---|---|---|
| `tests/guide/01_info.py` | 信息、状态、引脚能力 | USB开发板 |
| `tests/guide/02_rgb.py` | 板载RGB | 已验证的GPIO48板载WS2812 |
| `tests/guide/03_led.py` | 外部LED | LED串限流电阻 |
| `tests/guide/04_button_led.py` | 按钮控制LED | 按钮与LED |
| `tests/guide/05_adc.py` | ADC原始计数 | 合适电平的模拟信号源 |
| `tests/guide/06_pwm.py` | PWM调光 | LED串限流电阻 |
| `tests/guide/07_servo.py` | SG90动作 | 舵机、匹配的独立电源及共地 |
| `tests/guide/08_screen.py` | 中文与图形 | 支持的SPI屏幕 |
| `tests/guide/09_pages.py` | 页面示例 | 支持的SPI屏幕 |
| `tests/guide/10_turtle.py` | 标准Turtle绘图发送 | 电脑Tcl/Tk、Pillow、SPI屏幕 |
| `tests/guide/11_image.py` | Pillow图片适配整屏 | Pillow、SPI屏幕 |

主示例 `tests/guide/` 已改为代码内显式配置；集中配置版保留在 `tests/guide_shared/`。旧 `tests/quick/01`～`08` 内学员自行写的 `PIN` 仍属于该文件的代码，不会被配置文件强行替换。迁移时应将写死的引脚改为配置中的值。

### 最小程序

在 `tests/guide/` 新建一个Python文件：

```python
from _board import connect

with connect("COM5") as robot:
    print(robot.get_info())
```

`_board` 是项目的教学辅助模块，负责定位SDK；仅省略串口或显式导入预设时才读取统一配置；它不是固件命令。`connect()`本身不保存外设映射，不自动退出维护，也不自动移动舵机。

在目录外独立使用SDK时，可以明确写串口：

```python
from ai_robot import Robot

with Robot(port="COM5") as robot:
    print(robot.get_status())
```

SDK的 `Robot` 不会自行寻找项目的 `hardware.json`。项目辅助模块 `connect()` 省略串口时才会读取该文件；`connect("COM5")`使用显式串口，不读JSON。

## 2. 硬件、软件与配置要求

### 2.1 固件与安装

| 项目 | 当前要求 |
|---|---|
| MCU | 当前参考目标ESP32-S3，16MiB Flash、8MiB OPI PSRAM、原生USB，RGB48板级描述 |
| 教学固件 | `ai-maker-s3` V0.4.0；板级屏幕基础接口从V0.3提供，页面与图片需要V0.4 |
| 电脑Python | 3.11及以上；本机已用3.14验证 |
| 串口库 | pyserial `>=3.5,<4` |
| 图片/Turtle额外依赖 | Pillow `>=12.3,<14`，通过安装脚本或 `ai-maker-robot[drawing]` 安装 |
| Turtle窗口 | 标准Python的Tcl/Tk；不需要在ESP32安装turtle或MicroPython |
| AI服务器、API Key | 当前这些本地功能不需要；AI功能本身尚未实现 |
| 已编译应用 | `build/native-usb/ai_maker_s3.ino.bin` |
| SDK安装包 | `sdk/python/dist/ai_maker_robot-0.4.1-py3-none-any.whl` |

当前COM5已烧录V0.4。改Python、GPIO映射、页面JSON或图片不需要重新烧录；增加新的底层驱动或协议能力时才更新固件。不能换成任意Arduino示例、旧AI固件或白灯诊断固件后继续期待本SDK可用。

固件源码构建基线是Arduino-ESP32 3.3.12、ArduinoJson 7.4.3、Adafruit GFX 1.12.6、ST7735/ST7789库1.11.0、BusIO 1.17.4、U8g2_for_Adafruit_GFX 1.8.0。使用已编译固件的学员不需要安装这些编译库。

当前实板保留原有1MiB应用分区，仅升级应用。`merged.bin`包含参考16MiB分区，不能作为本板通用升级文件直接烧入。版本和刷写证据见 [验证记录](verification.md)。

### 2.2 串口和GPIO的区别

`COM5`是电脑USB设备端口；`GPIO14`是开发板芯片信号脚编号。修改COM端口不会改变舵机信号脚。开发板上的3V3、5V、GND属于电源，不是可编程GPIO；开发板排针位置序号也不等于GPIO编号。

统一文件的主要内容：

| 配置组 | 内容 | 应用时机 |
|---|---|---|
| `connection.port` | `AUTO`或`COM5`等 | 新建电脑连接时 |
| `pins.led/button/adc/pwm` | 普通实验GPIO | 可选集中配置版示例调用对应GPIO功能时 |
| `servo` | 名称、信号GPIO、角度范围、脉宽范围 | 代码调用 `servo.configure()` 时保存到板端 |
| `display` | 屏幕型号、SPI信号、BLK、旋转、反色、亮度 | 代码调用 `display.configure()` 时保存到板端 |

例如 `pins.led=12` 和 `pins.pwm=12` 可以供两个独立实验轮流使用同一个LED。它们不是同时运行的两个设备；同一GPIO不能同时承担输入、LED输出和另一设备信号。

当前教学板级描述对0、3、19、20、26～37、43～46和当前板载RGB脚作保留处理。普通可分配候选为1、2、4～18、21、38～42、47，以及未被当前RGB构建使用的另一脚；以实际 `list_pins()` 返回的 `reserved`、`owner` 和开发板引出情况为准。不存在的GPIO22～25不可用。GPIO19/20用于原生USB，不能占用后仍要求COM5通信。

这里的可分配GPIO支持普通输入/输出；ADC仅存在于部分输入脚。某些ESP32-S3脚具有启动或输入能力限制，本固件将相关脚保留，不应通过Python强行绕过。当前能力表不是任意S3模组或未来定制板的通用引脚表。

屏幕所有使用的SCK、MOSI、CS、DC、RST、BLK可在可用GPIO中映射；已配置屏幕或舵机的引脚会被占用，即使设备当前没有输出，也不能直接被普通GPIO实验抢用。释放运行信号与删除保存映射是两件事。

### 2.3 外设接线要求

| 设备 | 接法与条件 |
|---|---|
| 外部LED | GPIO → 限流电阻 → LED正极，LED负极 → GND；此接法输出1亮、0灭。其他接法可能逻辑相反 |
| 按钮 | 一个触点接所选GPIO，另一个接GND；使用 `input_pullup`，按下0、松开1 |
| ADC源 | 模拟输出接具有ADC能力的GPIO，与ESP32共地；输入不得超过开发板允许电压，不能直接输入5V |
| SG90 | 信号接配置GPIO，电源按实际舵机要求，ESP32与电源共地；不能用GPIO给舵机供电 |
| ST77xx屏幕 | VCC/GND按模块电气要求，SCL/SCK接sck，SDA/DIN接mosi，CS/DC/RES各对应配置；屏幕SDA标识不代表I²C |
| BLK | 有GPIO调光才配置该脚；无独立控制时为-1，此时不能调用可调背光 |
| 板载RGB | 固件使用固定板级WS2812脚，当前为48；普通高电平不是WS2812颜色指令 |

本SDK的GPIO逻辑电平由ESP32硬件决定；设置为output不等于可提供5V或大电流。舵机和屏幕回执没有位置或光学传感反馈。

## 3. 所有接口共用的规则

大多数硬件函数返回Python `dict`，内容是固件成功响应中的 `data`，不会返回整个JSONL信封。失败通过异常表达；不要依赖“没有报错”来认定舵机已到位或屏幕已显示正确。

数值范围中的整数通常要求真正的 `int`，不接受 `True/False`、浮点角度、字符串数字。`filled`、`invert`、`enabled`则明确要求布尔值。

SDK创建连接时打开唯一控制会话，默认每1秒心跳，固件租约6秒。关闭连接、心跳到期会停止运行输出；已保存映射保留。关闭或到期后，非维护状态下恢复明确启用的默认屏幕页面。`stop()`仍保留当前会话，不立即恢复默认页。

维护状态写入板端，断电重启仍保持维护。`maintenance.exit()`只是允许后续显式动作，不会自动移动舵机。修改本地配置、打开文档、导入模块也不会自动驱动设备。

## 4. 连接与设备信息

### `Robot(...)`

```text
Robot(connection="usb", port="AUTO", *, baudrate=115200, timeout=2.0,
      transport=None, heartbeat_interval=1.0)
```

| 参数 | 含义 |
|---|---|
| `connection` | 当前只支持 `"usb"` |
| `port` | 明确串口号或AUTO；AUTO仅在电脑恰好存在一个USB串口候选时成功，不轮流探测所有设备 |
| `baudrate` | UART传输基准115200；当前原生USB固件也使用此构造参数 |
| `timeout` | 每条请求等待匹配响应的正有限秒数，默认2秒；超时不能判断动作是否已执行 |
| `transport` | 高级测试用自定义传输对象；传入后所有权转交Robot，Robot负责关闭 |
| `heartbeat_interval` | 默认1秒，必须小于租约；设为None关闭后台心跳，只适合自行管理请求与租约的高级调用者 |

构造时会打开串口、查询固件身份、打开会话；会停止正在显示的默认页以取得控制，不会配置或驱动新的运行输出。建议总用 `with Robot(...) as robot:`。

### 设备级函数

| 函数 | 返回 | 用途与前提 |
|---|---|---|
| `robot.get_info()` | dict | 固件家族/版本、协议、boot_id、board_profile、能力、支持屏幕、资源限额；检测到会话中重启会报连接失效 |
| `robot.get_status()` | dict | maintenance、storage_fault、配置修订、GPIO/舵机/LED/display/pages状态、standalone_active |
| `robot.list_pins()` | list[dict] | 每个存在GPIO的pin/input/output/adc/reserved/owner；检查可用性与占用 |
| `robot.stop()` | `{"stopped": True}` | 停止GPIO/PWM、舵机脉冲、RGB与屏幕等运行输出；保留映射与会话 |
| `robot.wait(seconds)` | None | 等待非负有限秒数，同时后台心跳继续；发现通信故障及时抛出异常 |
| `robot.close()` | None | 结束会话、关闭串口；重复调用无操作。关闭时可能报告硬件清理失败 |
| `with robot:` | 上下文 | 进入返回自身，离开关闭；若实验自身已抛异常，不以次要清理异常覆盖原异常 |

```python
from _board import connect

with connect("COM5") as robot:
    print(robot.get_info()["firmware_version"])
    for pin in robot.list_pins():
        if not pin["reserved"]:
            print(pin["pin"], pin["adc"], pin["owner"])
```

`status.servos[].angle`是最后命令角度，`position_verified=False`；`display.physical_verified=False`、LED的同名字段也不是故障，而是声明没有对应物理传感反馈。

## 5. GPIO、按钮与PWM

### GPIO函数

| 函数 | 参数/返回 | 说明 |
|---|---|---|
| `robot.gpio.setup(pin, mode)` | 返回pin、mode | pin为存在、可用、未占用GPIO；mode取下表 |
| `robot.gpio.read(pin)` | int：0或1 | 必须先setup；输入模式读取电平，output模式返回最后指令值，PWM模式不能使用此方法 |
| `robot.gpio.write(pin, value)` | 返回pin、value | 必须已设为output；value仅0或1 |
| `robot.gpio.release(pin)` | 返回pin、released | 恢复该普通GPIO为释放状态；不删除舵机/屏幕映射 |
| `robot.pwm.write(pin, duty)` | 返回pin、duty、frequency_hz | 必须先setup为pwm；duty为0～100整数，频率固定1000Hz |

| mode | 意义 | 常见用途 |
|---|---|---|
| `"input"` | 无内部上拉/下拉输入 | 外部数字源、ADC前置模式 |
| `"input_pullup"` | 内部上拉输入 | 接GND的按钮，按下读0 |
| `"input_pulldown"` | 内部下拉输入 | 接高电平的按钮/数字信号 |
| `"output"` | 数字输出 | LED、逻辑控制信号 |
| `"pwm"` | 固定1kHz PWM输出 | LED占空比调光 |

同一GPIO重新setup会先释放之前模式。普通PWM最多4路；配置了GPIO背光后最多3路。通道不足或引脚被屏幕、舵机占用会报 `RESOURCE_CONFLICT`。

### LED闪烁

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.exit()  # 已完成本次接线确认后运行。
    robot.gpio.setup(12, "output")
    for _ in range(5):
        robot.gpio.write(12, 1)
        robot.wait(0.5)
        robot.gpio.write(12, 0)
        robot.wait(0.5)
```

### 按下亮、松开灭

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.gpio.setup(2, "input_pullup")
    robot.gpio.setup(12, "output")
    for _ in range(100):
        pressed = robot.gpio.read(2) == 0
        robot.gpio.write(12, int(pressed))
        robot.wait(0.1)
```

把按钮读值直接写给LED会得到“按下写0”；对于上述LED接法，这意味着按下灭。使用 `int(pressed)` 才得到按下亮。

### PWM调光

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.gpio.setup(12, "pwm")
    for duty in (0, 25, 50, 75, 100, 0):
        robot.pwm.write(12, duty)
        robot.wait(1)
```

## 6. ADC模拟输入

### `robot.adc.read(pin) -> int`

返回0～4095的12-bit原始计数。必须先 `gpio.setup(pin, "input")`，不能使用带上拉/下拉模式，也不能用没有ADC能力的GPIO。当前固件没有提供校准电压、滤波、采样率控制或连续DMA采样接口。

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.gpio.setup(1, "input")
    for _ in range(10):
        print(robot.adc.read(1))
        robot.wait(0.5)
```

不要直接将计数乘以3.3/4095并当作已校准测量；参考电压、衰减、非线性和实际输入范围尚需独立验证。

## 7. 板载RGB灯

| 函数 | 参数 | 返回与说明 |
|---|---|---|
| `robot.led.color(name, brightness=16)` | name为red/green/blue/yellow/white/off；brightness整数0～32 | 返回red/green/blue、state、physical_verified；使用命名颜色 |
| `robot.led.set(*, red=0, green=0, blue=0)` | 三通道分别为0～32整数，必须使用关键字 | 自定义RGB；当前限幅用于控制板载灯亮度 |
| `robot.led.off()` | 无 | 发送熄灯帧，返回三通道0及命令状态 |

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.led.set(red=20, green=8, blue=3)
    robot.wait(2)
    robot.led.color("blue", brightness=12)
    robot.wait(2)
    robot.led.off()
```

`led.color((55, 88, 99))`无效：该方法只接受上述颜色名称。自定义用 `led.set(...)`，但通道上限是32，不是255。屏幕的颜色接口有不同规则，见第9节。

板载WS2812由数据帧控制，`gpio.write(48, 1)`不等于点亮白灯；板载灯脚也被固件保留，不能当普通GPIO调用。

## 8. 舵机

### `robot.servo.configure(...)`

```text
robot.servo.configure(name, pin, *, min_angle=30, max_angle=150,
                      min_pulse_us=500, max_pulse_us=2500)
```

| 参数 | 规则 |
|---|---|
| `name` | ASCII字母开头，后续字母/数字/下划线，最长24字符 |
| `pin` | 空闲可输出GPIO |
| `min_angle/max_angle` | 各为0～180整数且严格递增，限制允许发送的角度 |
| `min_pulse_us/max_pulse_us` | 各为500～2500整数且严格递增，定义完整0°/180°映射脉宽 |

此方法自动进入维护，读取当前配置，按名称新增/替换一项舵机，保留其他舵机与屏幕映射，保存成功后**仍处于维护**。返回新的 `revision`、`config`，不会自动运动。最多4路舵机。

统一配置给SG90的初始值为1000～2000µs；这与SDK方法的通用默认500～2500不同。实际范围应以实物校准为准。角度限值不会把30°重新映射成最小脉宽：固件始终按完整0～180线性计算，再单独限制可发送的角度。

### 运动与释放

| 函数 | 返回 | 意义 |
|---|---|---|
| `robot.servo.move(device, angle)` | state=commanded、angle、position_verified=False | device为已保存名称，angle须在该项配置角度范围内；输出50Hz脉冲 |
| `robot.servo.release(device)` | released=True | 停止该舵机信号，保留映射，不切断电源 |

```python
from _board import connect

with connect("COM5") as robot:
    robot.servo.configure("test", pin=14, min_angle=30, max_angle=150,
                          min_pulse_us=1000, max_pulse_us=2000)
    robot.maintenance.exit()
    for angle in (60, 90, 120, 90):
        robot.servo.move("test", angle)
        robot.wait(1)
```

这里不必额外调用release，退出with会统一释放。若希望保持角度，保持程序与会话运行、继续心跳即可；程序退出后不会自动回90°。回到初始角度必须在关闭前明确move，并留出运动时间。没有位置反馈，指令成功不代表已经实际到位。

要永久删除映射，使用第11节的 `config.get/apply` 删除对应servos条目；release仅停止信号，不能把该脚变为可抢占的普通GPIO。

## 9. SPI屏幕

### 型号、尺寸与颜色

| panel | 0/2方向尺寸 | 1/3方向尺寸 |
|---|---|---|
| `st7735s_128x160` | 128×160 | 160×128 |
| `st7789_240x320` | 240×320 | 320×240 |
| `st7789_240x240` | 240×240 | 240×240 |

坐标原点为可视画面左上角，x向右、y向下。参数必须落在旋转后的实际范围；矩形、位图须完整在屏内。SPI当前由屏幕独占，未实现与其他SPI设备共享。

屏幕绘图颜色支持三种形式：

| 形式 | 示例 | 范围 |
|---|---|---|
| 名称 | `"cyan"` | black/white/red/green/blue/yellow/cyan/magenta |
| RGB元组 | `(55, 88, 99)` | 三个0～255整数；需要tuple，不能传list |
| RGB565整数 | `0xF800` | 0～65535 |

SDK将RGB元组转换为RGB565，会损失部分颜色精度。这里的RGB范围与板载灯的0～32不同。

### 配置和启动

```text
robot.display.configure(panel="st7789_240x320", *, sck=4, mosi=5,
                        cs=15, dc=7, rst=6, backlight=-1,
                        rotation=1, invert=None, brightness=None)
```

所有信号GPIO可更换，但不得重复、占用系统保留脚或与已保存舵机冲突。`backlight=-1`表示不使用GPIO背光；其他为合法GPIO。`rotation`是0～3整数。

`invert=None`时ST7789自动True、ST7735自动False；`brightness=None`时有GPIO背光默认60%，无GPIO背光默认100%。明确值时invert须bool，brightness须0～100整数。无GPIO背光只接受brightness=100。

`configure()`自动进入维护，保留舵机配置并保存屏幕映射，返回新的revision/config；**保持维护，不初始化屏幕**。

| 函数 | 返回 | 说明 |
|---|---|---|
| `robot.display.begin()` | width、height、panel、命令状态 | 要求已保存有效配置且非维护；初始化SPI与控制器并清黑屏 |
| `robot.display.release()` | released=True | 幂等释放屏幕SPI/背光运行资源，维护状态也可用；保留映射 |
| `robot.display.unconfigure()` | revision/config | 自动进入维护并删除display配置，保留servos，仍维护 |

教学辅助 `connect_screen("COM5", panel=..., sck=..., ...)` 会按当前文件的命名参数调用configure、退出维护、begin，再将robot交给with代码；省略参数的 `connect_screen()` 才使用可选统一配置。运行它表示这次已经确认实际屏幕接线；这比普通 `connect()` 会多写板端配置。

### 绘图函数

以下函数需要已经begin并处于非维护状态。成功返回 `state="commanded"`、`physical_verified=False`；亮度另外返回brightness。

| 函数 | 参数与行为 |
|---|---|
| `robot.display.fill(color="black")` | 用一种颜色填满可视范围 |
| `robot.display.clear(color="black")` | fill的同义方法 |
| `robot.display.text(text, x=0, y=0, color="white")` | 1～192个UTF-8字节，允许换行；内置12px GB2312中文字体、行高16；不自动换行，部分Unicode/表情不在字库 |
| `robot.display.rect(x, y, width, height, color="white", filled=False)` | 正整数宽高，filled决定填充或描边 |
| `robot.display.line(x0, y0, x1, y1, color="white")` | 画线段，端点都须在可视范围 |
| `robot.display.brightness(percent)` | 0～100整数；仅配置GPIO BLK才支持，运行时修改不会改保存的初始亮度 |

```python
from _board import connect_screen

with connect_screen("COM5", panel="st7735s_128x160",
                    sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16) as robot:
    robot.display.fill((15, 30, 45))
    robot.display.text("你好，小创客", x=8, y=8, color="cyan")
    robot.display.rect(8, 36, 100, 24, color=(55, 88, 99), filled=True)
    robot.display.line(8, 80, 110, 80, color="yellow")
    robot.wait(10)
```

退出连接后，带GPIO背光的临时屏幕通常熄灭；若启用了板端默认页，则会重新显示默认页。它不是断开后永久保留临时图像的接口。

### 完整图片与小块位图

| 函数 | 返回/要求 |
|---|---|
| `robot.display.image(image_or_path, fit="contain", background="black")` | 输入本地路径str/Path或Pillow Image；返回width、height、chunks、state、physical_verified |
| `robot.display.bitmap(x, y, width, height, pixels)` | 输入精确width×height×2字节的bytes，RGB565大端；一次最多384像素；返回命令状态 |

image自动获取当前屏幕尺寸并分块传输，支持 `contain`等比补边和 `cover`居中裁剪。background使用前述屏幕颜色形式，用于透明背景合成和补边。源图最多1600万像素，目标每边最多320；读取后会处理EXIF旋转。不支持直接传HTTP图片地址，先准备本地文件。

```python
from pathlib import Path
from _board import connect_screen

PICTURE = Path(__file__).with_name("我的图片.png")
with connect_screen("COM5", panel="st7735s_128x160",
                    sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16) as robot:
    print(robot.display.image(PICTURE, fit="contain"))
    robot.wait(10)
```

原始两像素示例：

```python
with connect_screen("COM5", panel="st7735s_128x160",
                    sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16) as robot:
    robot.display.bitmap(0, 0, 2, 1, b"\xf8\x00\x07\xe0")  # 红、绿
    robot.wait(2)
```

完整图片不受页面小图标48×48限制，但只是内存画面，不自动保存NVS。当前逐块同步传输适合静态作品，不是视频流或实时动画协议。失败不自动重发。

## 10. 页面包与开机默认页

页面是受限JSON数据，不是HTML、JavaScript或Python代码。可以在网页编辑器制作后上传，也可以用下面接口操作。

### 页面函数

| 函数 | 返回与行为 |
|---|---|
| `robot.pages.info()` | saved、bytes、crc32、width/height、page_ids、startup_enabled、default_page、shown_page、standalone_active、last_error |
| `robot.pages.upload(project_or_path)` | 输入dict或本地JSON路径；校验后分块上传并提交，返回页面信息；成功会关闭自动开机显示，并将默认页ID指向第一页 |
| `robot.pages.download()` | 下载已保存包，校验长度/CRC/模型，返回独立dict；没有已保存包时报错 |
| `robot.pages.show(id="home")` | 显示已保存页，必要时初始化屏幕；清除本次文本覆盖；返回id和命令状态 |
| `robot.pages.text(id, text)` | 更新当前页指定text控件，重绘页面；id指控件ID而非页面ID；不写入NVS |
| `robot.pages.startup(id=None, enabled=True)` | 保存默认页及开关，返回页面信息；None表示不更换已有默认ID；不会立即自动显示 |
| `robot.pages.clear()` | 先进入维护再清空页面包和默认页，返回页面信息；仍保持维护，不删除屏幕/舵机映射 |

show/text/startup要求非维护；upload/download/info可在维护状态使用。show/startup要求页面尺寸与当前屏幕旋转后尺寸一致；show不会自动改变接线或退出维护。clear是删除当前保存项目的操作。

### 上传最小页面并显示

以下代码可在任意已支持的屏幕尺寸上创建一页：

```python
from _board import connect_screen

with connect_screen("COM5", panel="st7735s_128x160",
                    sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16) as robot:
    screen = robot.get_status()["display"]
    project = {
        "schema_version": 1,
        "width": screen["width"], "height": screen["height"],
        "pages": [{"id": "home", "background": 0, "widgets": [
            {"id": "status", "type": "text", "x": 8, "y": 8,
             "text": "准备就绪", "color": 65535}
        ]}],
        "images": []
    }
    robot.pages.upload(project)
    robot.pages.show("home")
    robot.pages.text("status", "正在运行")
    robot.wait(5)
```

### 启用或关闭默认页

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.exit()  # 接线和保存配置已确认。
    robot.pages.startup("home", enabled=True)
```

关闭连接后默认页显示；上电/复位也会显示，需要持续供电。`pages.text()`临时覆盖不会写回，所以恢复时读取原包中的“准备就绪”。仅停止临时输出而保留会话的 `robot.stop()` 不会立即恢复默认页。

关闭自动显示：

```python
with connect("COM5") as robot:
    robot.maintenance.exit()
    robot.pages.startup(enabled=False)
```

维护模式禁止自动页面；屏幕尺寸改变或移除屏幕配置会关闭不兼容的默认页策略，需上传匹配项目后重新启用。默认页仅恢复屏幕，不运行学生Python，也不恢复舵机动作。

### 页面数据限制

| 项目 | 上限/规则 |
|---|---|
| 紧凑JSON | 8192 UTF-8字节 |
| 格式化本地JSON源文件 | 65536字节；去掉格式空白后的发送包仍限8192 |
| 页面数量 | 1～4 |
| 所有页面控件合计 | 32 |
| 图片数量 | 最多4 |
| 单图尺寸 | 每边1～48 |
| 全部图片解码数据 | 合计4608字节；RGB565大端base64 |
| 控件类型 | text、rect、line、image |
| ID | 字母开头，ASCII字母数字下划线，最长24字符；页面/图像各自唯一，控件在本页唯一 |
| 文本 | 1～192 UTF-8字节，允许LF换行，禁止其他控制字符 |

上传采用768字节分块、CRC32、板端再次校验；两个二进制NVS槽先保存新项目再切换元数据，失败保留之前有效项目。不会自动擦除旧项目的其他NVS数据。NVS空间不足时仍可能返回STORAGE_ERROR；这不表示可以安全地重试所有动作或擦除整片Flash。

### 纯电脑页面校验函数

```python
from ai_robot import validate_project, load_project
```

| 函数 | 返回与行为 |
|---|---|
| `validate_project(project)` | 对dict执行完整结构、范围和大小检查，返回独立深复制；不打开串口、不执行数据内容 |
| `load_project(path)` | 读取UTF-8/UTF-8 BOM本地JSON，拒绝重复字段，调用validate_project后返回dict；不打开串口 |

更底层 `Pages(robot)` 类位于 `ai_robot.pages`，通常不需要手工构造；`Robot` 已创建 `robot.pages`。它的全部公开方法就是本节所列接口。

## 11. 维护与完整板端配置

| 函数 | 返回 | 副作用 |
|---|---|---|
| `robot.maintenance.enter()` | maintenance=True | 停止运行输出并持久保存维护标记；保存失败时不要换线 |
| `robot.maintenance.exit()` | maintenance=False | 清除持久维护标记；存在storage_fault时拒绝退出；不自动开始设备动作 |
| `robot.config.get()` | revision、config | 读取板端配置；这不是读取电脑hardware.json |
| `robot.config.apply(config, *, expected_revision)` | 新revision、config | 必须已进入维护；整体校验、保存，保持维护；修订不匹配会拒绝 |

板端基础配置schema为：

```json
{
  "schema_version": 1,
  "servos": [
    {"name":"test","pin":14,"min_angle":30,"max_angle":150,
     "min_pulse_us":1000,"max_pulse_us":2000}
  ],
  "display": {
    "panel":"st7735s_128x160","sck":4,"mosi":5,"cs":15,
    "dc":7,"rst":6,"backlight":16,"rotation":1,
    "invert":false,"brightness":60
  }
}
```

没有屏幕时省略display；没有舵机时servos为[]。该对象不包含电脑COM端口、普通实验PIN别名或Turtle窗口设置。不能把整个hardware.json直接交给config.apply；两种文件负责不同的配置范围。

删除一项舵机映射、保留其他内容：

```python
from _board import connect

with connect("COM5") as robot:
    robot.maintenance.enter()
    current = robot.config.get()
    config = current["config"]
    config["servos"] = [s for s in config["servos"]
                        if s["name"] != "test"]
    robot.config.apply(config, expected_revision=current["revision"])
    # 保持维护；完成实际接线确认后再明确退出。
```

`config.apply`是整体替换，不是自动合并。如果手写 `{"schema_version":1,"servos":[]}` 保存，会同时移除未包含的屏幕映射。一般优先使用servo/display的configure便利方法，它们会读取并保留另一类配置。

## 12. 标准库Turtle

### 教学入口 `finish(screen=None, *, robot=None, port=None, **display)`

`finish`来自项目教学辅助 `_turtle`，不是Python标准库函数。支持 `finish(screen, robot=robot)` 复用开头已创建的连接；此模式不再接收port/IO。关闭窗口接管并关闭该robot及全部运行输出；即使没有发送也会清理。需要保留连接则使用send_turtle自行管理。它在真实Turtle窗口添加“发送到ESP32”按钮并进入事件循环。使用它后无需另调 `turtle.done()`。

```python
import _board  # 在guide目录中定位公共Turtle辅助模块，不连接USB。
import turtle
from _turtle import finish

screen = turtle.Screen()
screen.setup(640, 480)
pen = turtle.Turtle()
pen.pensize(5)
pen.color("orange")
for _ in range(5):
    pen.forward(180)
    pen.right(144)
pen.hideturtle()
finish(screen, port="COM5", panel="st7735s_128x160",
       sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16)
```

不传robot时，绘图阶段不连接USB，显式点击或Enter后才按配置连接；传入robot时，开头已连接，按钮只复用它。发送前先捕获内部画布，再初始化所需屏幕并传图；连接保持到窗口关闭，重复发送复用同一会话。关闭后释放连接并恢复已启用的默认页。窗口须可见且不能最小化；只发可见画布，不包含按钮、标题栏或画到窗口外的内容。未隐藏海龟光标时光标也会成为图片的一部分。

### SDK绘图工具函数

下列函数位于 `ai_robot.drawing`，适合自建界面或高级课程；导入模块本身不打开窗口或串口。它们需要drawing/Pillow依赖。

| 函数 | 输入/返回 | 说明 |
|---|---|---|
| `capture_turtle(screen)` | 标准turtle.Screen → 新Pillow RGB Image | Windows捕获内部Canvas HWND；其他平台按画布坐标区域捕获。调用者负责close返回图像 |
| `send_turtle(robot, screen, **fit_options)` | 返回 `display.image()` 结果 | 捕获后发送并关闭临时截图；robot须已配置且begin；fit_options传给display.image |
| `load_image(image_or_path)` | 本地路径或Pillow Image → 新RGBA Image | 检查最多1600万像素、应用EXIF方向；不修改调用者图像；调用者close返回图像 |
| `fit_image(source, size, fit="contain", background=(0,0,0))` | RGBA源图，size=(宽,高) → 新RGB Image | 目标每边1～320；等比补边/居中裁剪；background为三个RGB整数；调用者close返回图像 |
| `rgb565_strips(image)` | 目标图像 → 生成器 | 每次yield `(y, rows, pixels)`，pixels为RGB565大端bytes，每包≤384像素；目标每边1～320 |

例：自行捕获并保存电脑图片，不连接USB：

```python
from ai_robot.drawing import capture_turtle

image = capture_turtle(screen)  # screen是已经创建并绘制的真实Turtle窗口。
try:
    image.save("作品.png")
finally:
    image.close()
```

例：已有Turtle窗口和屏幕连接时直接发送：

```python
from _board import connect_screen
from ai_robot.drawing import send_turtle

with connect_screen("COM5", panel="st7735s_128x160",
                    sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=16) as robot:
    print(send_turtle(robot, screen, fit="contain"))
    robot.wait(10)
```

Turtle命令运行在电脑；ESP32接收的是缩放后的像素，不接收可继续执行的turtle代码。640×480缩小到160×128时，小字与细线会损失细节，宜用大字、粗线和高对比配色。

## 13. 异常、超时与排查

错误类型可从 `ai_robot` 导入：

| 类型 | 含义/处理 |
|---|---|
| `RobotError` | SDK错误基类，可用于统一捕获 |
| `DeviceError(code, message, request_id)` | 设备明确拒绝；可读.code、.message、.request_id |
| `ProtocolError` | 家族/协议或响应格式不匹配；核对是否正确教学固件 |
| `RequestTimeout` | 没有及时收到本次回执；动作可能已执行，不自动重发 |
| `ConnectionLostError` | USB或心跳已失效、设备重启等；修正后明确重建连接 |
| `UnsupportedCapability` | 当前设备或SDK不提供此能力，也用于提示缺少drawing依赖 |
| `ValueError` | 本地参数类型/范围/数据结构错误；先修正代码或配置 |
| `OSError`及文件/图像相关异常 | 串口、文件不存在、图片解码等底层错误；结合路径和原始错误排查 |

```python
from ai_robot import Robot, DeviceError, RequestTimeout

try:
    with Robot(port="COM5") as robot:
        print(robot.get_status())
except DeviceError as error:
    print(error.code, error.message)
except RequestTimeout as error:
    print(error)  # 不在这里自动重复动作。
```

这里直接使用 `Robot`，以便捕获SDK原始异常。课堂便捷入口 `connect()` 会将 `RobotError` 转为带说明的 `SystemExit`，不能用上面的异常处理方式包裹它来捕获原始设备错误。

| 常见设备错误码 | 需要检查 |
|---|---|
| `MAINTENANCE_REQUIRED` | 设备正处维护；确认接线后显式退出 |
| `PIN_INVALID` / `PIN_RESERVED` | GPIO是否存在、是否被USB/存储/板级描述保留 |
| `PIN_CAPABILITY_MISMATCH` | 例如ADC用了无ADC能力的脚 |
| `RESOURCE_CONFLICT` | 屏幕/舵机持久映射冲突、重复引脚或PWM通道耗尽 |
| `DEVICE_NOT_FOUND` | 舵机名称、页面ID或当前页文本控件是否已存在 |
| `CONFIG_INVALID` | 配置字段、引脚、页面与屏幕尺寸是否匹配 |
| `CONFIG_REVISION_MISMATCH` | 重新读取config后再基于最新revision明确应用 |
| `ANGLE_OUT_OF_RANGE` | 是否超出这只舵机配置的角度范围 |
| `STORAGE_ERROR` | NVS保存失败或空间不足；保留错误证据，不自动擦除全板 |
| `HARDWARE_ERROR` | 驱动初始化、输出或清理失败；检查状态、供电、接线，必要时复位 |
| `SESSION_REQUIRED` / `DEVICE_BUSY` | 会话过期或另一个程序占用；关闭其他工具后重新连接 |

常见“运行后没反应”：检查固件家族/版本、COM选择、维护状态、实际引脚与共地；检查程序是否刚显示后就退出with；查看是否有默认页覆盖临时画面。配置成功与驱动成功不能代替实物观察。

## 14. 高级传输接口

这些接口用于测试、自定义通信适配，普通学员无需使用。

```python
from ai_robot import Transport, SerialTransport
```

`Transport`是结构协议，要求实现：

| 方法 | 合同 |
|---|---|
| `write(data: bytes) -> None` | 完整写入请求；失败抛异常，不静默吞丢数据 |
| `read(size: int, timeout: float) -> bytes` | 返回至多指定大小的bytes，无数据可返回b""；遵守超时 |
| `close() -> None` | 关闭所拥有资源 |

`SerialTransport(port, baudrate=115200, write_timeout=2.0)`是其pyserial实现。构造时打开端口，AUTO规则与第4节一致；不主动脉冲DTR/RTS复位线，但驱动/硬件在打开端口时仍可能复位。`write/read/close`方法使用上表签名；对象的 `port` 是最终选定名称。

传给 `Robot(transport=...)` 后不要同时直接读写该transport，以免破坏请求匹配；Robot负责序列化心跳与命令，并在结束时关闭。生产协议是UTF-8 JSONL，单行上限4096字节，命令有副作用时无自动重试。页面和位图的分块由SDK处理，无需学生自己拼JSONL。

## 15. 尚未实现的接口

| 当前属性/能力 | 状态 |
|---|---|
| `robot.ai` / capabilities.ai | 占位，访问方法会抛UnsupportedCapability；没有聊天、识别或模型API |
| `robot.audio` / audio_in、audio_out | 占位；麦克风、I²S功放录放音尚未实现 |
| `robot.web` / student_web | 占位；任意学员HTML/CSS/JS上传宿主尚未实现 |
| sd | 未实现SD文件服务 |
| Wi-Fi、OTA、云身份 | 不在当前SDK功能范围 |

本地网页页面编辑器已经实现，但它制作并上传的是受限JSON屏幕页面；这与“学生写任意网页并上传运行”是不同的功能。当前不需要填写AI模型、服务地址、密钥或麦克风/功放引脚；填写配置也不会使尚未实现的驱动生效。

## 16. 对照源码与进一步资料

本文对应 `sdk/python/src/ai_robot/client.py`、`pages.py`、`drawing.py`、`transport.py`、`errors.py`；带前导下划线的内部函数不是学员调用合同。

- [页面编辑器与Turtle操作说明](页面编辑器与Turtle_V0.4.md)
- [屏幕接线与自定义GPIO](屏幕测试与自定义引脚_V0.3.md)
- [USB协议](../protocols/usb-v1.md)
- [屏幕基础协议](../protocols/display-v1.md)
- [页面与图片协议](../protocols/pages-v1.md)
- [验证记录与版本证据](verification.md)
