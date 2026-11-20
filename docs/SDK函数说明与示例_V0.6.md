# AI小创客SDK函数说明、配置与示例 V0.6

当前固件 0.8.0、SDK 0.8.3，导入名 `ai_robot`，USB 协议 v1。本手册保留原文件名。见 [附件下载](https://github.com/moran-007/Class_ESP_AI/releases/tag/v0.8.3) 和 [实机及软件验证](verification.md)。旧 GPIO/ADC/PWM 及 `configure` 接口保留兼容。

## 1. 安装、连接及组合顺序

Python 3.11+；Windows 完整工程只需运行 [安装Python环境.cmd](../安装Python环境.cmd)，使用工程根目录的 `.venv`。单独分发脚本时才安装对应的 [SDK wheel](跨电脑安装与直接导入_V0.5.md)，带图片/Turtle 时用 `[drawing]` 并安装 Python 自带的 Tcl/Tk。安装后用同一个解释器即可在任意文件夹 `from ai_robot import Robot`。

```python
from ai_robot import Robot

with Robot(port="COM5") as robot:
    print(robot.get_info())
```

不强制with，等价管理方式是创建Robot后用try/finally执行close。COM5改为当前电脑实际端口；AUTO只接受唯一USB候选，不扫描探测全部串口。`Robot("COM5")`不是正确缩写，因为第一个位置参数是connection。

**组合顺序：audio/display/servo.set → robot.start → digital/analog/pwm.set → 动作。** 前三种set配置映射并保持维护；后三种set立即设置GPIO模式，不能放在维护状态下执行。多外设共用一个Robot，不为同一COM口各建一个连接。配置映射时会停止已有运行输出，所有set不构成跨外设原子事务。

```python
from ai_robot import Robot

robot = Robot(port="COM5")
try:
    robot.audio.set(bclk=42, ws=41, din=21, dout=40, sd=39, volume=20)
    robot.start()
    robot.digital.set(pin=2, mode="input_pullup")
    robot.wait(0.2)
    clip = robot.audio.record(seconds=3)
    clip.to_wav("recording.wav")
    print(clip.levels)
    robot.audio.play(clip)
finally:
    robot.close()
```

示例运行即使用外设，先完成供电、共地、接线并按实际IO修改。麦克风与功放不能直接用GPIO供电。本轮实物收音和听感待用户接线确认；回执成功不等于实物验收。

## 2. Robot主接口

构造：`Robot(connection="usb", port="AUTO", *, baudrate=115200, timeout=2.0, transport=None, heartbeat_interval=1.0)`。构造时打开串口、握手并取得会话；不会自动移动舵机。connection目前仅usb；原生USB的baudrate数字不是其实际数据吞吐。transport供测试/自定义传输注入并把关闭责任交给Robot；通常不填写。heartbeat_interval=None关闭自动心跳，适合受控测试，课堂默认保留1秒。

| 函数 | 返回及说明 |
|---|---|
| `get_info()` | dict：固件家族/版本/boot_id/板级描述/capabilities/limits；会话内重启会报连接失效 |
| `get_status()` | dict：维护、存储、显示、舵机、GPIO、页面、音频运行状态；含commanded/physical_verified边界 |
| `list_pins()` | list[dict]：GPIO能力、reserved、owner；新固件自动分页合并，调用者无需管offset |
| `start()` | 必要时退出维护，初始化本连接set请求的屏幕和音频；返回maintenance、display、audio；不自动录放或移动舵机 |
| `stop()` | 停止运行输出但保留会话/配置；不等于关闭串口，默认页通常等关闭后恢复 |
| `wait(seconds)` | None；等待期间心跳线程保持会话，通信失败会抛异常；非负有限秒数 |
| `close()` | None；结束会话、关闭串口，幂等；停止该会话的输出；适用时恢复已启用默认屏幕页 |

SDK动作不自动重发，通信失败也不自动重连。设备租约6秒；close不是切断舵机或功放电源。长时间运行靠正常心跳而不是每条动作重开串口。

## 3. 数字IO、模拟输入及PWM

GPIO参数是真正整数，通常拒绝bool、浮点、字符串。数字输出值为0/1；建议按钮状态用 `int(pressed)` 转换。模式在当前会话有效；退出释放。ADC候选1～20中仍要排除系统保留脚和其他外设占用。

| 接口 | 参数/返回/前提 |
|---|---|
| `digital.set(pin, mode="input")` | 设置input/input_pullup/input_pulldown/output；不接受pwm |
| `digital.setup(pin, mode="input")` | set别名 |
| `digital.read(pin)` | int0/1；先配置；输出模式读的是最后指令值，不是电压测量 |
| `digital.write(pin, value)` | dict回执；value0/1，须output模式 |
| `digital.release(pin)` | dict；释放该脚运行模式，不删除外设持久映射 |
| `analog.set(pin)` / `analog.setup(pin)` | 配置ADC输入模式；ADC候选1～20，板端再检查保留和占用 |
| `analog.read(pin)` | int原始12bit计数0～4095；未校准电压；须先配置input |
| `analog.write(pin, value)` | 抛UnsupportedCapability；当前不提供真正DAC模拟电压输出，不会伪装PWM |
| `pwm.set(pin)` | 设置该脚为PWM；须非维护、无冲突 |
| `pwm.write(pin, duty)` | duty整数0～100%，固定1kHz；最多4路，GPIO背光占用后3路 |
| `gpio.setup(pin, mode)` | 旧通用入口；支持上述四种数字模式和pwm |
| `gpio.read(pin)` / `gpio.write(pin, value)` / `gpio.release(pin)` | 兼容旧数字操作，约束同digital |
| `adc.read(pin)` | 兼容analog.read，返回原始计数 |

PWM是高低电平占空比，不是直接模拟电压。I²S音频也不是普通PWM。`list_pins`新增digital_input/digital_output/analog_input/analog_output/pwm_output，还要结合reserved和owner判断可用性；GPIO有ADC能力不等于现在可抢占。相关接线和边界见 [IO与音频说明](数字模拟IO与音频测试_V0.5.md)。

## 4. 舵机、板载RGB

| 接口 | 参数及含义 |
|---|---|
| `servo.set(pin, *, name="test", min_angle=30, max_angle=150, min_pulse_us=1000, max_pulse_us=2000)` | SG90课堂短配置；同名替换、其他名保留；保存映射并保持维护，不移动 |
| `servo.configure(name, pin, *, min_angle=30, max_angle=150, min_pulse_us=500, max_pulse_us=2500)` | 原接口；注意默认脉宽与set不同；校准须按实际型号 |
| `servo.move(device, angle)` | 逻辑名和整数角度；角度在该项允许范围内；返回commanded，不提供位置反馈 |
| `servo.release(device)` | 撤销该舵机PWM，保留映射，不切断电源、不保证回90° |
| `led.color(name, brightness=16)` | red/green/blue/yellow/white/off；brightness整数0～32 |
| `led.set(*, red=0, green=0, blue=0)` | 每通道整数0～32，按安全课堂亮度限幅；不是0～255 |
| `led.off()` | 板载WS2812熄灯指令；普通GPIO高电平不能代替RGB数据帧 |

最多4个位置舵机，各用不同GPIO/名称；50Hz，角度范围0～180严格递增，脉宽500～2500µs严格递增。脉宽仍按完整0～180度线性映射，min/max_angle仅限制可发角度。独立匹配供电并共地，首次卸下连杆。RGB驱动失败会报告故障，回执不构成光学验收。

## 5. 屏幕、丝印与图片

支持st7735s_128x160、st7789_240x320、st7789_240x240。坐标按旋转后尺寸，整数且在范围内；文字左上角，12px字体/16px行距，不自动换行。中文受内置字体字库限制，不能假设所有Unicode字符都有字形。

| 接口 | 参数/行为 |
|---|---|
| `display.set(sck=None, mosi=None, cs=None, dc=None, rst=None, backlight=None, *, panel="st7789_240x320", rotation=1, invert=None, brightness=None, fps=None, **labels)` | 前六参数也可按位置传；别名大小写无关；保存屏幕映射并保持维护，随后start |
| `display.configure(panel="st7789_240x320", *, sck=4, mosi=5, cs=15, dc=7, rst=6, backlight=-1, rotation=1, invert=None, brightness=None)` | 原明确配置；保留舵机映射，保持维护；之后exit+begin或采用set/start流程 |
| `display.unconfigure()` | 删除屏幕映射、保留舵机，保持维护；不是仅熄屏 |
| `display.begin()` | 明确初始化SPI及屏幕，清黑屏；非维护且已配置 |
| `display.fill(color="black")` / `clear(color="black")` | 清/填整屏；需已begin |
| `display.text(text, x=0, y=0, color="white")` | 1～192个UTF8字节，允许换行，不接受其他控制字符 |
| `display.rect(x, y, width, height, color="white", filled=False)` | 完整在屏内，宽高正数，filled为布尔 |
| `display.line(x0, y0, x1, y1, color="white")` | 两端坐标有效 |
| `display.bitmap(x, y, width, height, pixels)` | pixels为精确w×h×2字节RGB565大端；每块最多384像素 |
| `display.image(image_or_path, fit="contain", background="black")` | Pillow对象/本地文件，适配实际屏幕并分块；contain补边、cover居中裁剪；源图最多1600万像素 |
| `display.brightness(percent)` | 有GPIO背光才可调0～100%；无GPIO背光不提供调光 |
| `display.release()` | 关闭显示/背光/释放SPI，保留映射，维护模式可用 |

颜色支持black/white/red/green/blue/yellow/cyan/magenta、RGB565整数0～65535、或RGB三元组0～255；与板载led.set的0～32不同。set省略IO使用configure参考值，不读取另一块屏幕接线：SCK4/MOSI5/CS15/DC7/RST6/BLK=-1。BLK=-1时亮度只能100；invert默认ST7789=True/ST7735=False。

丝印：SCK/SCL/CLK/SCLK→sck，MOSI/SDA/DIN/SDI→mosi，CS/SS→cs，DC/A0/RS→dc，RST/RES/RESET→rst，BLK/BL/BACKLIGHT→backlight。每个信号只填一次，未知和供电脚名称拒绝；位置顺序不等于排针顺序。详见 [丝印/set/帧率](set接口_丝印对照与刷新帧率.md)。

fps为1～60整数或None，只限制PC display.image的帧开始上限，不设置面板扫描率，不限制text/line/rect/bitmap，不保证达到目标。image返回width/height/chunks/state/physical_verified及transfer_seconds；传输耗时不含图片缩放、限帧等待或实际扫描。图片临时显示不写NVS。

## 6. 页面保存与默认页

| 接口 | 说明 |
|---|---|
| `pages.info()` | 保存大小、CRC、页ID、开机策略及当前页 |
| `pages.upload(project_or_path)` | dict或本地JSON；验证、CRC、768字节分块、提交；新上传关闭开机显示，不自动执行代码 |
| `pages.download()` | dict；完整读回并验证长度/CRC/模型，不是截图 |
| `pages.show(id="home")` | 显示已保存页；尺寸须与当前屏幕一致；不自动退出维护或修改接线 |
| `pages.text(id, text)` | 当前页文本控件的临时更新，不写入保存模板 |
| `pages.startup(id=None, enabled=True)` | 启用/关闭默认页；关闭会话/复位时按策略恢复，仅恢复屏幕 |
| `pages.clear()` | SDK先进入维护再清空页面包，随后仍维护 |
| `validate_project(project)` | 纯PC校验并返回项目副本，不连接设备、不执行内容 |
| `load_project(path)` | 纯PC读取并验证JSON，拒绝重复字段；源文件≤64KiB，紧凑包≤8192字节 |

最多4页、32控件、4图；单图≤48×48，总解码图像≤4608字节，紧凑包≤8192字节。双槽NVS提交保留上一有效版本，但不是历史版本菜单；空间不足返回错误，不自动擦除旧NVS。格式见 [pages-v1](../protocols/pages-v1.md)。

## 7. 音频设备接口

全部使用16kHz、mono、PCM16LE；原生USB流要求固件0.5.0。UART115200构建关闭音频能力。一个共享BCLK/WS总线、独立din/dout、半双工录完再播；没有全双工对讲、压缩解码、重采样、AI识别或TTS。IO是会话映射，不写NVS；进入/退出维护仍会保存维护标志。

| 接口 | 参数/返回/前提 |
|---|---|
| `audio.set(bclk=42, ws=41, din=21, dout=40, sd=39, *, mic_channel="left", volume=20)` | 可位置/命名参数；-1禁用din/dout/sd，至少一数据方向。麦克风单独用dout=-1、sd=-1。volume0～100仅影响播放；保存会话映射并保持维护 |
| `audio.info()` | 配置、active、driver_ok、cleanup_required、录放标志、计数、PCM元数据 |
| `audio.begin()` | 初始化I²S时钟，默认静音，不录放；通常由start调用；返回started等状态 |
| `audio.record(seconds=3)` | 有限正秒数≤30，按采样数取整，返回AudioClip；错误会尽力stop并保留原异常，不自动重读块 |
| `audio.play(clip)` | 必须AudioClip；768字节块、偏移校验、结束排空并静音；返回bytes/samples/duration_seconds/state/physical_verified |
| `audio.play_file(path, *, format="wav")` | 本地PCM WAV，裸PCM须显式format="pcm_s16le" |
| `audio.play_url(url, **options)` | 明确下载成AudioClip再走同一play；参数同load_audio_url，不自动联系AI服务 |
| `audio.stop()` | 结束录放，保留活动I²S总线和映射；不是断电或释放所有时钟 |
| `audio.release()` | 结束I²S硬件，保留本会话映射，之后可begin/start |
| `audio.unconfigure()` | 同时释放硬件与会话映射，让这些GPIO空闲 |

INMP441：BCLK/SCK→bclk，WS→ws，SD数据→din，L/R接地选left、高电平选right。MAX98357A：BCLK→bclk，LRC→ws，DIN→dout，SD/EN关断控制→sd。**两模块SD含义不同**。功放SD=-1不能保证硬件关断。共享时钟仅定义一份，不把I²S当I²C。详见 [接线、测试与格式](数字模拟IO与音频测试_V0.5.md)。

## 8. AudioClip和本地/云端一致性

`AudioClip(pcm, sample_rate=16000, channels=1, sample_width=2, format="pcm_s16le", byte_order="little")` 是不可变音频值；pcm为非空偶数字节，最多960000字节/30秒。元数据必须严格匹配，不自动转格式。WAV头不发送给板端或现有裸PCM服务。

| 接口/属性 | 说明 |
|---|---|
| `pcm` | 原始PCM16LE字节，可送现有16k/16bit/mono数据入口 |
| `samples` / `duration_seconds` | 采样数量/按采样算的时长，不代表传输墙钟时间 |
| `peak` / `rms` | PCM绝对峰值/RMS；不是声压级测量 |
| `levels` | peak/rms/clipped_samples/all_zero/physical_verified；有数据不代表实物听感正确 |
| `AudioClip.from_pcm(source, **metadata)` | bytes或有界本地PCM文件，调用即声明该固定格式 |
| `clip.to_pcm(path=None)` | 返回PCM；指定path时还写文件 |
| `AudioClip.from_wav(source)` | bytes或有界WAV文件；只接受未压缩16k/mono/16bit完整PCM WAV |
| `clip.to_wav(path=None)` | 返回WAV容器；指定path时写文件，默认当前工作目录 |
| `clip.to_wire()` | schema_version/format/sample_rate/channels/sample_width/byte_order/bytes元数据dict，不含整段base64 |
| `AudioClip.from_wire(pcm, metadata)` | 严格校验元数据、版本、长度后构造同格式对象 |
| `AudioClip.tone(frequency=440, seconds=1, volume=.1)` | 生成正弦PCM；频率0～8000之间、时长≤30秒、幅度0～1；不是自动播放 |
| `AudioClip.from_url(url, **options)` | load_audio_url别名 |
| `load_audio_url(url, *, format="wav", sample_rate=None, channels=None, headers=None, timeout=10)` | 显式有界HTTP/HTTPS读取；返回AudioClip；不读取环境密钥、不自动重试 |

裸PCM URL需format="pcm_s16le"，并以参数或响应X-Audio-Sample-Rate/X-Audio-Channels声明16000/1；若提供格式、字节序、bit等头，必须一致。仅audio/L16 MIME不代表小端；本地与线上统一对象，不代表本轮已实现云端识别/聊天/合成任务API。headers可显式传鉴权，跨源重定向不转发Authorization、Cookie、Proxy-Authorization。未知编码、截断/超大内容、错误采样率会拒绝。

```python
from ai_robot import AudioClip, load_audio_url

local = AudioClip.from_wav("recording.wav")
same = AudioClip.from_wire(local.to_pcm(), local.to_wire())
remote = load_audio_url("http://127.0.0.1:8000/recording.wav")
```

本地文件、麦克风与URL都得到同一AudioClip，后续均用audio.play；不把MP3、OGG或WAV头当PCM。例子中的本地HTTP服务须事先明确启动，SDK不会自行启动服务器。

## 9. 维护与配置

| 接口 | 说明 |
|---|---|
| `maintenance.enter()` | 停止输出，保存维护标记；成功确认后才断电换线 |
| `maintenance.exit()` | 保存退出维护；不自动移动舵机或开始音频 |
| `config.get()` | 返回revision及config：schema_version、servos、可选display；音频会话映射在audio.info里 |
| `config.apply(config, *, expected_revision)` | 维护中按最新revision保存；拒绝未知字段、重复/系统脚/跨设备冲突；失败保留旧有效映射 |

物理换线：enter确认 → 断电 → 换线改代码 → 上电 → 配置 → start/exit → 显式测试。删除舵机映射需要修改servos列表，不是release；多个映射应保留不相关项。新配置会停当前输出，不应在动作循环中每帧set。

## 10. 包内Turtle和绘图工具

```python
import turtle
from ai_robot import Robot
from ai_robot.turtle import finish

robot = Robot(port="COM5")
try:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16)
    robot.start()
    screen = turtle.Screen()
    pen = turtle.Turtle()
    pen.circle(60)
    pen.hideturtle()
    finish(screen, robot=robot)
finally:
    robot.close()
```

| 入口 | 说明 |
|---|---|
| `ai_robot.turtle.finish(screen=None, *, robot=None, port=None, **display)` | 真实Turtle窗口加发送/Enter；已有robot则复用，不能同时再传port/IO；关窗接管并关闭整条连接，包括其他输出，即使未发送 |
| `ai_robot.turtle.connect_screen(port="AUTO", **display)` | 包内屏幕上下文辅助，不读工程JSON；set、start后yield Robot，退出关闭 |
| `capture_turtle(screen)` | ai_robot.drawing；捕获可见内部画布，返回调用方负责close的Pillow图；不含按钮/桌面 |
| `send_turtle(robot, screen, **fit_options)` | ai_robot.drawing；直接捕获并调用display.image，不另建/关闭该Robot，不增加按钮 |
| `load_image(image_or_path)` | 返回有界RGBA副本，调用方负责关闭 |
| `fit_image(source, size, fit="contain", background=(0,0,0))` | 返回RGB适配图，目标每边≤320；调用方负责关闭 |
| `rgb565_strips(image)` | 迭代y/rows/RGB565大端bytes，每块≤384像素；高级渲染辅助 |

不传robot的finish在第一次发送时才连接；传已有robot时开头已连接。不能最小化后捕获。已有robot模式发送失败会关闭连接并停用按钮，需关窗修正重跑；自行建连接模式允许修正后手动再点，不自动重发。Turtle在电脑运行，板端只接收像素。

## 11. 异常及传输扩展

从ai_robot导入RobotError、DeviceError、ProtocolError、RequestTimeout、ConnectionLostError、UnsupportedCapability。DeviceError提供code/message/request_id；RequestTimeout表示动作执行结果可能未知，不应自动再发；ValueError通常是本地参数/格式问题。当前robot.ai、robot.web未实现，明确报UnsupportedCapability；URL音频不是已接入AI服务器。

```python
from ai_robot import Robot, DeviceError, RequestTimeout

try:
    with Robot(port="COM5") as robot:
        print(robot.get_status())
except DeviceError as error:
    print(error.code, error.message)
except RequestTimeout as error:
    print(error)  # 不自动重复动作。
```

旧classroom.connect便捷入口会把SDK错误转换为易读SystemExit，捕获原始异常时直接用Robot。通常不需要自行操作以下传输接口：

| 传输接口 | 合同 |
|---|---|
| `Transport` | Protocol：write(data:bytes)、read(size:int,timeout:float)->bytes、close()；由Robot串行使用 |
| `SerialTransport(port, baudrate=115200, write_timeout=2.0)` | 立即打开指定串口；实现write/read/close；通常直接让Robot创建 |

常见错误：PIN_RESERVED/RESOURCE_CONFLICT核对list_pins；MAINTENANCE_REQUIRED核对start与即时GPIO设置顺序；CONFIG_REVISION_MISMATCH重新读配置；STORAGE_ERROR保留证据、不自动擦整板；HARDWARE_ERROR需检查driver_ok/cleanup_required，失败的音频释放必须完整release恢复，不能用stop假装修复。

## 12. 测试位置与验收

可复制的14个文件在 [examples/portable](../examples/portable/README.md)，按功能解释的主教程为 [开发指南](开发指南.md)，音频菜单为工程根目录运行音频测试.cmd。IO/格式/接线见 [数字模拟IO与音频测试](数字模拟IO与音频测试_V0.5.md)，实际验证记录见 [verification.md](verification.md)。V0.5历史应用位于build/audio-native-usb/ai_maker_s3.ino.bin并有GitHub Release；V0.6请核对本地构建清单，不存在已发布0.6附件的承诺。应用升级只适用匹配当前板与分区的流程，不能把参考merged镜像直接覆盖当前板。

软件、构建、实际板端配置及物理收音/出声分别验收；FakeHardware合成的PCM或仅driver_ok=true不证明真实麦克风/扬声器工作。当前用户将自行调整接线，实际声音质量仍待其测试。


## 13. Program：构建离线硬件流程（0.6新增）

从`ai_robot`导入`Program`。构造和添加步骤均不打开串口、不驱动硬件，不执行任意源码。Program收集白名单动作、主外设配置和板端条件；电脑的Python if/函数/导入库不会自动变成离线程序。

```python
from ai_robot import Program, Robot

program = Program()
program.led.color("red", brightness=8)
program.wait(1)
program.led.color("green", brightness=8)
program.wait(1)
with Robot(port="COM5") as robot:
    robot.program.save(program, loop=True, autostart=True)
```

只保存不立即运行；显式选择autostart=True后，下次重启且非维护状态运行。首次需要升级支持0.6的固件，以后改支持流程只需save。使用说明见 [开发指南](开发指南.md#15-程序固化通电后独立运行)，格式见 [program-v1](../protocols/program-v1.md)。

| Program接口 | 参数、返回与说明 |
|---|---|
| `Program()` | 纯电脑端创建构建器，初始config含空servos列表 |
| `wait(seconds)` | 有限正数≤60秒，四舍五入为毫秒且至少1ms；返回自身，不在电脑睡眠 |
| `when_digital(pin, value, *, then, otherwise=None)` | value严格0/1；运行时采样数字输入；then必须非空Program，otherwise可省略/为空Program；返回自身 |
| `when_analog(pin, operator, value, *, then, otherwise=None)` | ADC候选IO；operator为<、<=、==、!=、>=、>；value0～4095原始计数；返回自身 |
| `to_dict()` | 严格校验并返回深拷贝的schema_version/config/steps模型；不连接设备 |
| `Program.from_dict(project)` | 严格校验模型并创建独立Program，不执行其中内容；不读取文件 |

分支Program不能自带屏幕/舵机配置；把映射放在主Program，分支引用主配置名称。构建器会复制分支步骤，后续修改原分支不会隐式改变已经加入的条件。

| 子接口 | 行为与和在线Robot接口的区别 |
|---|---|
| `program.led.set(*, red=0, green=0, blue=0)` | 每通道0～32，记录步骤，返回Program |
| `program.led.color(name, brightness=16)` / `off()` | red/green/blue/yellow/white/off；brightness0～32；记录步骤 |
| `program.digital.set(pin, mode="input")` | input/input_pullup/input_pulldown/output；记录setup；不接受pwm |
| `program.digital.write(pin, value)` / `release(pin)` | 记录0/1写入或释放；没有read接口，条件用when_digital |
| `program.analog.set(pin)` | 记录ADC输入setup；没有read/write，条件用when_analog |
| `program.pwm.set(pin)` / `write(pin, duty)` | 记录PWMsetup或占空比0～100；1kHz，仍受板端通道预算限制 |
| `program.servo.set(pin, *, name="test", min_angle=30, max_angle=150, min_pulse_us=1000, max_pulse_us=2000)` | 修改主程序config快照，同名替换；不插入移动动作；默认脉宽与在线servo.set相同 |
| `program.servo.move(device, angle)` / `release(device)` | 记录步骤；名称须在主程序配置，move在保存时及板端校验范围 |
| `program.display.set(sck=None, mosi=None, cs=None, dc=None, rst=None, backlight=None, *, panel="st7789_240x320", rotation=1, invert=None, brightness=None, **labels)` | 与在线set相同丝印别名/参考IO；保存主程序快照并自动插入一次display.begin步骤；不接受fps |
| `program.display.fill(color="black")` | 记录填色；支持命名/RGB565整数/RGB元组0～255 |
| `program.display.text(text, x=0, y=0, color="white")` | 记录内置字库文字，UTF8 1～192字节、坐标按旋转后屏幕校验 |
| `program.display.rect(x, y, width, height, color="white", filled=False)` | 完整在屏内，filled严格bool |
| `program.display.line(x0, y0, x1, y1, color="white")` | 两端在屏内 |
| `program.display.brightness(percent)` / `release()` | 记录0～100亮度或释放；亮度需要GPIO背光 |
| `program.display.counter(...)`（0.7新增） | 根流程最后唯一的持续累加显示控件；完整参数和行为见第16节，保存loop=False |

这些构建方法返回Program，便于顺序添加；不是动作回执。Program不提供gpio/adc别名、servo.configure、display.configure/begin/clear/image/bitmap、audio、pages、web或ai等未列入口，不应照搬全部Robot方法。显示set会自动插入begin；不要把robot.start当成Program初始化步骤。

限制：紧凑UTF8模型≤3072字节、源节点≤64（所有分支合计）、条件≤4层。普通Python循环可用于在电脑生成重复步骤，但仍受数量/大小限制；需要整个流程持续循环时用save(loop=True)。条件按板端实时值判断，不是上传时捕获。先设置输入/输出/PWM模式，路径相关错误在板端执行时停止并报告。

## 14. robot.program：保存、控制和查询（0.6新增）

`robot.program`只在固件capabilities.standalone_program=True时可用，旧固件明确报UnsupportedCapability。程序拥有自己的屏幕/舵机配置快照，运行时临时生效，不改写原在线持久映射；结束后恢复映射不等于自动移动舵机。

| 接口 | 参数、返回与状态 |
|---|---|
| `program.info()` | dict：saved/enabled/loop/running/boot_pending/instruction/error/cleanup_required/physical_verified |
| `program.download()` | dict含program（模型深拷贝）、enabled、loop；SDK校验模型和元数据；未保存时返回明确错误 |
| `program.save(program=None, *, loop=False, autostart=False)` | 显式接受Program，或SDK0.6.1省略时使用最近成功end的快照；bool严格布尔。校验、进入维护、保存、成功退出维护；不立即运行；返回状态 |
| `program.enable()` | 保留模型/loop，启用下次开机，不立即运行；SDK维护进入/成功退出 |
| `program.disable()` | 保留模型/loop，关闭下次开机；SDK维护进入/成功退出 |
| `program.clear()` | 删除保存流程及开机策略；SDK维护进入/成功退出；不是仅停止 |
| `program.start()` | 非维护时当前会话显式运行已保存流程；先清理输出，不要求enabled=True；保持会话才继续运行 |
| `program.stop()` | 停当前流程并释放输出，保留保存内容和开机策略；返回stopped |

注意上表`program`是`robot.program`管理器；前一节`program = Program()`是待保存构建器，两者角色不同。

电脑建立会话时接管停止开机流程，之后可以正常用Robot写新代码。显式start运行期间先stop再发普通实时动作，不能同时混用。close或租约到期停止；**close默认不恢复固化，只有下次重启才按enabled策略启动**。loop=False到末尾清理输出；loop=True从程序起点继续；等待按tick处理，不阻塞整个USB读循环。

```python
from ai_robot import Robot

with Robot(port="COM5") as robot:
    print(robot.program.info())
    robot.program.stop()
    # robot.program.disable()  # 保留但不自启。
    # robot.program.clear()    # 明确需要删除时执行。
```

save/enable/disable/clear任何一步失败都不自动重试，也不自动假定已经退出维护。如果保存已完成而maintenance.exit失败，必须核对状态；不要把“可能已保存”当作“下次开机已准备好”。STORAGE_ERROR不触发擦除NVS；PROGRAM_INVALID是模型/映射/限位错误；HARDWARE_ERROR要检查error与cleanup_required，不假装执行或清理完成。

固化范围不包含音频、Turtle/图片、云端或任意 Python 源码执行。固件仍使用 C++，路线比较见 [MicroPython说明](MicroPython与当前方案.md)。历次构建、屏幕固化、清除恢复结果见 [验证记录](verification.md)；回执不能代替实物验收。

## 15. 开始/结束同步录制（SDK0.6.1新增，固件仍0.6.0）

| 接口 | 参数、返回与作用 |
|---|---|
| `robot.program.begin()` | None；检查固化能力、非维护/程序未运行，快照当前屏幕和舵机config，开始新轮并作废旧隐式save快照；不改NVS |
| `robot.program.end()` | 返回独立Program，另保留独立隐式save快照；不保存、不停止屏幕预览。无begin、空录制、wait未完成、录制失败时拒绝 |
| `robot.program.cancel()` | None；丢弃录制及隐式save快照，不撤销实际动作，不删除板端保存程序 |
| `robot.program.save(loop=True, autostart=True)` | SDK0.6.1可省略Program，保存最近成功end快照；显式save(Program)兼容 |

支持原Robot的白名单动作：led.set/off，gpio.setup/write/release，pwm.write，servo.move/release，display.begin/fill/text/rect/line/brightness/release及wait。clear会成为fill；首次屏幕绘制为回放补begin。屏幕/舵机set和start须在begin前，GPIO/PWM的set须在begin内；不快照已有GPIO模式/当前像素。

状态查询和心跳不计入动作。配置更改、页面、图片、音频及GPIO/ADC读取在录制期间拒绝；动态条件使用原Program构建器。发送前校验候选，成功回执后才提交；设备失败/超时不能结束为成功流程。wait仍真实等待并录入请求时长（0秒不加步骤），wait期间不允许并发end或动作。cancel/close不复活草稿；robot.stop始终可用，取消进行中录制并发送原停止命令，已完成end快照不因普通stop而丢失。

需要手动画多页时，只记录clear与重画顺序，没有自动page ID；要命名页/更新数字用既有pages模板，但此类pages操作不属于录制固化白名单。详情及完整代码见 [begin/end录制教程](绘图录制与固化_V0.6.1.md) 和 [portable15](../examples/portable/15_screen_record.py)。

## 16. 板端持续累加显示（SDK/固件0.7新增）

签名：`Program.display.counter(*, name="count", start=0, step=1, interval=1, x=8, y=48, width=144, height=20, color="white", background="black")`。返回所属Program，只构建步骤，不连接、不睡眠、不立即驱动屏幕。

| 参数 | 语义和限制 |
|---|---|
| name | ASCII字母开头、字母/数字/下划线，最长24字节 |
| start | 精确整数0～9223372036854775807，每次start/重启从此值开始，默认0 |
| step | 整数1～2147483647，每周期增加量 |
| interval | 有限秒数0.05～60，换算round(interval×1000)为50～60000ms |
| x、y、width、height | 旋转后屏幕内的完整矩形，最小133×16，默认位置8/48、尺寸144×20 |
| color、background | 计数字体和擦除区域颜色；命名色、RGB565整数、RGB元组0～255 |

必须先在Program配置屏幕。counter只能在根steps最后，不能放条件分支，一个Program最多一个。它作为终端步骤持续按时钟周期更新，不需要while/Program.wait；计数器程序保存时必须loop=False，否则SDK在任何维护/IO前拒绝、固件也拒绝。不含counter的旧循环行为不变。

运行中值保存在RAM，不每周期保存NVS；数字区域先擦除后画新数，静态标题不必重复绘制。处理延迟按完整周期补足，毫秒回绕使用无符号差值；到64bit上限下一次会溢出时停止并报告错误，不回绕成0/负数。它不是硬实时精度保证。

`robot.program.save`对counter额外要求`capabilities.standalone_counter=True`，旧0.6板在维护/写入前报UnsupportedCapability，升级SDK不等于自动升级固件。0.7的program.info及device.status.program增加`counter`对象，含active/name/value/interval_ms；创建Robot仍会接管并停止开机程序，值不代表光学反馈。

录制背景后，可用`flow = robot.program.end()`、`flow.display.counter(...)`、`robot.program.save(flow, autostart=True)`；仍无Robot.display.counter实时方法，也不把此步骤加入录制wire白名单。end返回模型与隐式save快照独立，须显式保存追加控件后的flow。

停止/关闭会话规则与原Program相同；clear清程序，disable保留模型但关闭自启，start按start值重新试跑。还原旧流程必须先有download模型和loop/enabled备份，不改原live配置或降级固件。实际本机入口见 [tests/counter](../tests/counter/README.md)，完整示例见 [portable16](../examples/portable/16_counter.py)，参数及验证边界见 [计数指南](数字累加计数器_V0.7.md)。计数控件不代表通用变量绑定或命名页面离线调度。

## 17. robot.wifi：USB 配网

| 方法 | 参数与返回 |
|---|---|
| `robot.wifi.connect(ssid, password)` | `ssid` 1～32 UTF-8 字节，支持中文、不含控制字符；`password` 为空或 8～63 个可打印 ASCII 字符。需控制会话，启动试连并返回状态。 |
| `robot.wifi.status()` | 可只读查询，返回当前链接及最近一次配网结果。 |
| `robot.wifi.clear()` | 需控制会话，移除设备保存的 Wi-Fi 信息，关闭无线，返回状态。 |
| `robot.setwifi(name, password, *, progress=True)` | SDK 0.8.3 起默认实时打印请求、等待 IP 和结果；`progress=False` 关闭提示。复用同一个 `Robot` 连接，返回状态字典；轮询到期仍在进行时返回最后的 `connecting` 状态。USB 超时仍抛出原 SDK 异常。 |
| `robot.listwifi()` | SDK 0.8.2；返回当前连接的 `[{"ssid": 名称, "ip": IPv4}]`，未连接时返回 `[]`。支持只读 USB 会话。 |
| `robot.clearwifi()` | SDK 0.8.2；等同于 `robot.wifi.clear()`，断开 Wi-Fi 并清除保存的名称和密码，需要普通控制会话。 |

状态字段为 `state`, `provisioning`, `ssid`, `ip`, `saved`, `error`。状态不含密码。`wifi_provisioning` 缺失时抛出 `UnsupportedCapability`；参数非法抛 `ValueError`，设备拒绝会返回 `DeviceError`；连接失败看 `provisioning == "failed"` 及 `error`。旧网络可能已恢复，不能仅以 `ip` 非空判定配置成功。详细状态和 USB 格式见 [wifi-v1](../protocols/wifi-v1.md)。

`Robot(port="COM5", read_only=True)` 不取得控制会话，只允许无需会话的查询，例如 `wifi.status()`、`get_info()`、`get_status()`，不会接管并停止板端计数。配网完整示例见 [17_wifi.py](../examples/portable/17_wifi.py)。
