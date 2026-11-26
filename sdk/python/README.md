# AI 小创客本地 Python SDK

Python 3.11+ 可从 GitHub 安装 SDK 和串口、绘图依赖。Turtle 窗口还需要 Python 带 Tcl/Tk。

```powershell
python -m pip install "ai-maker-robot[drawing] @ https://github.com/moran-007/Class_ESP_AI/releases/download/v0.9.0/ai_maker_robot-0.9.0-py3-none-any.whl"
```

在这个 Python 环境中运行 `from ai_robot import Robot` 即可使用。安装方法见 [跨电脑说明](../../docs/跨电脑安装与直接导入_V0.5.md)。

## 0.7板端每秒加一

需要SDK和固件0.7.0的standalone_counter能力；不是电脑while循环。终端控件必须是主流程最后一步，保持loop=False默认值：

```python
from ai_robot import Program, Robot

flow = Program()
flow.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                 CS=15, DC=7, RES=6, BLK=16, rotation=1)
flow.display.fill("black")
flow.display.text("数字累加", x=8, y=8, color="cyan")
flow.display.text("+1 / second", x=8, y=26)
flow.display.counter(name="count", start=0, step=1, interval=1,
                     x=8, y=48, width=144, height=20)
with Robot(port="COM5") as robot:
    robot.program.save(flow, autostart=True)
```

RESET后独立显示0、1、2……，RAM计数不每秒写Flash；每次启动从start重来。start为非负64位整数，step为1～2147483647，interval为0.05～60秒；显示区域最小133×16且完整在屏内。延迟按完整周期追赶，64位溢出时报错停止，不静默归零。旧0.6固件或loop=True会在维护/写入前拒绝，旧普通流程不受影响。

begin/end录制继续支持。要给录制背景追加计数器，取得flow=end()返回值，再flow.display.counter(...)，显式save(flow,autostart=True)。不是Robot.display实时方法，也不代表任意变量绑定或命名页面调度。详情见 [数字计数指南](../../docs/数字累加计数器_V0.7.md)；清除仍用program.clear，恢复之前流程需要先有download备份。

SDK0.6.1新增同步预览录制，固件继续使用0.6.0，无需重刷。先配置屏幕/舵机并start，再begin；GPIO/PWM的set需要在录制块内：

```python
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16)
    robot.start()
    robot.program.begin()
    robot.display.clear()
    robot.display.text("你好，创客！", x=8, y=8)
    robot.wait(3)
    robot.program.end()
    robot.program.save(loop=True, autostart=True)
```

支持动作立即预览并录入；wait实际等待并录入时长。end返回独立Program但不写Flash；save省略Program时保存最近成功end的快照，显式save(Program)兼容。cancel丢弃草稿和隐式快照，不撤销已预览动作或删除板端内容；stop/close仍可正常停止。状态查询/心跳不录入；图片/音频/pages/配置更改和GPIO/ADC读取拒绝；录制是调用步骤，不是屏幕截图或Python源码转换。完整说明见 [录制教程](../../docs/绘图录制与固化_V0.6.1.md)。

可在单份 Python 文件中用 `robot.setwifi(name, password)` 配网，后续复用同一个 `robot`。SDK 0.8.3 起默认输出配网阶段，传 `progress=False` 可关闭。`robot.listwifi()` 查询当前连接，`robot.clearwifi()` 清除板端保存的网络。旧入口 `robot.wifi.connect/status/clear` 仍可使用，需要固件声明 `wifi_provisioning`。只需查看时可用 `Robot(port="COM5", read_only=True)`。

SDK 0.9.0 可用 `VoiceClient(url, device_id, token).ask(text)` 连接现有 AI 网关。也可以创建 `VoiceClient(url)` 后分别调用 `ai.AIID(device_id)` 和 `ai.AItoken(token)`。`robot.ai` 直接设置凭据时使用原项目网关，也可先调用 `robot.ai.set(url)` 指定服务器。按下按钮可调用 `robot.ai.record_start()`，松开调用 `robot.ai.record_end()`，自动提交录音并逐段打印和播报回复。完整程序见 [AI 测试目录](../../tests/ai/README.md)。

## 保存到开发板，通电独立运行

```python
from ai_robot import Robot, Program

flow = Program()
flow.led.color("red")
flow.wait(1)
flow.led.color("green")
flow.wait(1)
with Robot(port="COM5") as robot:
    robot.program.save(flow, loop=True, autostart=True)
```

构建Program只记录流程，不打开串口。save成功后退出维护但不立即运行；下次重启在非维护状态自动执行。电脑session.open会停止并接管，关闭电脑程序不会自动恢复动作。显式program.start在当前会话运行，close/租约到期停止。管理接口为info、download、save、enable、disable、clear、start、stop；enable只启用下次开机，clear删除保存流程。save默认loop=False、autostart=False。

支持RGB、数字IO/PWM、舵机、屏幕文字/图形、wait及when_digital/when_analog；3072个UTF8字节、64源节点、4层条件。Program使用独立静态屏幕/舵机映射快照，运行时临时使用，停止后恢复live映射与休眠的会话音频映射，不自动开始收音。Program不能序列化任意Python函数/if/while、Turtle窗口、音频、图片或云端请求。固件升级一次后，改流程只需要save；严格的参数/硬件资源错误会拒绝或停止，动作不自动重发。详细示例见主开发指南和examples/portable/12～14。

组合外设的调用顺序：**先audio/display/servo.set配置映射 → robot.start退出维护并初始化 → digital/analog/pwm.set设置即时GPIO模式 → 读写动作**。digital/analog/pwm.set立即发送gpio.setup，不是延迟配置；不能在维护状态下与映射set混排。

## 直接安装与跨电脑导入

SDK运行代码全部在 `ai_robot` 包内；新增程序可以直接复制到其他目录，不需要 `_board.py`、`classroom.py` 或当前E盘路径。推荐从 [examples/portable](../../examples/portable/README.md) 开始。安装wheel一次后：

```python
from ai_robot import Robot, AudioClip, load_audio_url
from ai_robot.turtle import finish
```

基础依赖只有pyserial；AudioClip/WAV/HTTP来自Python标准库。图片和Turtle截图需要drawing扩展Pillow，窗口需要Tcl/Tk。完整在线/离线安装方法见 [跨电脑说明](../../docs/跨电脑安装与直接导入_V0.5.md)。SDK wheel是纯Python；Pillow离线wheel必须匹配目标系统/Python/架构，不能把某台电脑的完整venv复制过去就宣称通用。

## 数字输入输出、ADC和PWM明确区分

| 入口 | 范围与意义 |
|---|---|
| `robot.digital.set(pin, mode="input")` / `setup` | input/input_pullup/input_pulldown/output；不接收pwm模式 |
| `robot.digital.read(pin)` / `write(pin,value)` / `release(pin)` | 数字0/1；写入须先output，输入先选相应输入模式；output读回仍是最后指令值，不是电压测量 |
| `robot.analog.set(pin)` / `setup` / `read(pin)` | 先配置ADC输入，再读取0～4095原始计数，未校准电压 |
| `robot.analog.write(pin,value)` | 明确报UnsupportedCapability，当前S3教学板未接入真正DAC模拟电压输出 |
| `robot.pwm.set(pin)` / `write(pin,duty)` | PWM独立入口，固定1kHz、占空比整数0～100%；不是DAC电压 |

原gpio/adc/pwm接口保留。新固件的list_pins包含digital_input/digital_output/analog_input/analog_output/pwm_output布尔字段及owner。为遵守4096字节JSONL上限，新SDK在支持pin_pagination的固件中自动分批取得这些信息；不支持分页的旧固件仍用旧查询方式。能力可用不等于引脚空闲，必须同时检查reserved和owner。

## 收音、功放与统一本地/云端音频

先在当前文件填IO，所有set之后统一start；start只初始化I2S时钟、功放默认保持静音，不自动录音、播放或移动舵机。

```python
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.audio.set(bclk=42, ws=41, din=21, dout=40, sd=39,
                    mic_channel="left", volume=20)
    robot.start()
    clip = robot.audio.record(seconds=3)
    print(clip.levels)
    clip.to_wav("recording.wav")
    robot.audio.play(clip)
```

IO均可改为当前板合法空闲脚。INMP441的BCLK/WS/SD分别接bclk/ws/din，L/R接地时left；MAX98357A的BCLK/LRC/DIN分别接bclk/ws/dout，功放SD/EN接sd。**麦克风SD是数据，功放SD是关断控制，不能仅按同名相接。** 两模块共享时钟，数据方向分开；本版RPC只允许录完再播（half-duplex），不宣称实时全双工。

| 方法 | 参数/结果 |
|---|---|
| `audio.set(bclk=42,ws=41,din=21,dout=40,sd=39,*,mic_channel="left",volume=20)` | 保存本会话运行时映射并保持维护；din/dout/sd可-1，至少一个数据方向，所有实际脚互斥；mic_channel为left/right，volume整数0～100。无音频NVS写入，不在复位后自动启用 |
| `audio.info()` | 返回配置、活动、driver_ok、recording/playing、字节计数及固定格式元数据 |
| `audio.begin()` | 显式初始化，通常用robot.start统一调用；不开始录放 |
| `audio.record(seconds=3)` | 大于0、最多30秒；按采样数量取整，返回AudioClip，发生错误会尽力audio.stop并保留原错误，不重试读块 |
| `audio.play(clip)` | 参数必须AudioClip；768字节有界分块，结束排空此前采样并静音；返回bytes/samples/duration_seconds/state=commanded/physical_verified=False |
| `audio.play_file(path, format="wav")` | 本地PCM WAV；原始PCM需显式format="pcm_s16le"，不自动解MP3/OGG |
| `audio.play_url(url, **options)` | 只在明确调用时下载；参数同load_audio_url，成功变为相同AudioClip再播放 |
| `audio.stop()` | 停止当前录放，保留活动I2S总线及本会话映射 |
| `audio.release()` | 释放I2S硬件，保留本会话映射；之后start可重新初始化 |
| `audio.unconfigure()` | 同时清除本会话映射和占用，之后须再次set |

音频映射会在本会话的维护、其他配置应用、stop后保留；会话关闭或租约到期后清除。与屏幕/舵机已保存映射冲突会拒绝。修改接线前进入维护并确认、断电换线；音频I2S初始化/流出错不等于实物不存在探测。sd=-1时释放软件输出不能保证功放物理断电。

### AudioClip：统一格式和文件/网络边界

规范永远是 `pcm_s16le` / 16000Hz / mono / 16bit / little，最多30秒960000 PCM字节。WAV是电脑文件容器，ESP32及现有云端PCM入口不接收WAV文件头。本版不自动重采样、混音、压缩解码或猜字节序。

| 调用/属性 | 含义 |
|---|---|
| `AudioClip(pcm)` / `AudioClip.from_pcm(bytes_or_path, **metadata)` | 明确声明的非空、偶数字节canonical PCM；可用构造参数验证rate/channels/width/format/byte_order |
| `AudioClip.from_wav(bytes_or_path)` / `clip.to_wav(path=None)` | 严格PCM WAV读写；to_wav返回WAV bytes，可同时保存文件；截断、其他采样率/通道/位宽拒绝 |
| `clip.to_pcm(path=None)` / `clip.pcm` | 原始PCM bytes，不含容器头 |
| `clip.to_wire()` / `AudioClip.from_wire(pcm,metadata)` | schema_version=1和format/rate/channels/sample_width/byte_order/bytes显式元数据；检查实际长度，无整段base64或可执行代码 |
| `clip.samples` / `duration_seconds` | 根据实际PCM字节数计算采样数及音频时长 |
| `clip.peak` / `rms` / `levels` | 数字峰值、RMS、削顶计数和all_zero等诊断。没有语音识别或麦克风在场/光学反馈；全零数据不是“已正常收音”证据 |
| `AudioClip.tone(frequency=440,seconds=1,volume=.1)` | 生成canonical正弦测试音源，frequency大于0低于8000Hz，volume0～1；功放本身另受audio.set的0～100音量限制 |
| `AudioClip.from_url(url, **options)` / `load_audio_url(...)` | 同一有界HTTP/HTTPS下载入口；不会读取环境Key或启动AI服务 |

URL默认format="wav"，只接受严格WAV。原始PCM应明确format="pcm_s16le"，同时用sample_rate=16000/channels=1参数或X-Audio-Sample-Rate/X-Audio-Channels头声明；如果服务器头存在且不匹配，则拒绝。旧服务器的audio/L16 MIME不能单独当成小端格式声明。URL不允许内嵌用户名密码；headers可由调用者显式传入，跨源重定向丢弃Authorization/Cookie/Proxy-Authorization；下载大小和套接字超时有界，不自动重试。

本地WAV与URL均先变为AudioClip，因此后续接ASR/TTS服务时可以复用clip.pcm与to_wire元数据。这里没有实现AI服务端或对现有对话服务发起请求。原云服务“提交PCM→job→轮询分段”仍是独立上层流程，不把音频URL接口冒充完整语音对话。

## 简短set接口、多外设与图片帧率

SDK0.4.1新增 `display.set()`、`servo.set()` 和 `robot.start()`，这些旧功能兼容固件0.4.0；新增音频需要固件0.5.0。先audio/display/servo.set配置映射，再start，之后设置digital/analog/pwm模式并执行动作；set会进入并保持维护，start本身不移动舵机。

```python
from ai_robot import Robot

robot = Robot(port="COM5")
try:
    robot.display.set(panel="st7735s_128x160", SCL=4, SDA=5,
                      CS=15, DC=7, RES=6, BLK=16, fps=10)
    robot.servo.set(pin=14)
    robot.start()
    robot.display.text("你好，创客！", x=8, y=8)
    robot.servo.move("test", 90)
    robot.wait(3)
finally:
    robot.close()
```

无with也可用；仍应保证close。SG90示例先完成独立供电、共地和校准。位置参数支持 `display.set(4,5,15,7,6,16,panel="st7735s_128x160")`，顺序固定为SCK/MOSI/CS/DC/RST/BLK，与实际排针位置无关。SCL/SDA/RES/BLK等别名不区分大小写；重复、拼错或VCC/GND等供电脚参数会明确拒绝。

`fps=1..60`是电脑端 `display.image()` 帧开始的上限，None不额外限速；不设置面板扫描率、不保证实际速度、不限制text/rect/line/bitmap。图像返回 `transfer_seconds` 为分块传输耗时，排除缩放和帧率等待。完整说明见项目 `docs/set接口_丝印对照与刷新帧率.md`，直接运行示例见 `tests/guide/12_multi_parts.py` 和 `13_display_fps.py`。

## 标准库 Turtle 电脑窗口绘画

`turtle_demo.py` 使用真正的Python标准库 `turtle`，不是仿Turtle指令接口：`forward()`、`circle()`、`begin_fill()`、`write()`等照常画在电脑窗口。项目公共模块 `_turtle.finish` 为窗口添加“发送到ESP32”按钮，Enter也可发送。`finish(screen)` 在首次发送时建立连接；当前项目默认turtle_demo也支持开头创建并配置Robot，再 `finish(screen, robot=robot)` 复用同一连接。后一方式开头已连接，关窗会关闭这个Robot及其全部输出；不能同时再传port或IO。下方示例展示前一种延迟连接方式。

```python
import turtle
from ai_robot.turtle import finish

screen = turtle.Screen()
pen = turtle.Turtle()
pen.color("red")
pen.circle(80)
pen.hideturtle()
finish(screen)
```

代码放在项目 `tests/quick/` 中即可引用 `_turtle`；实际接线继续使用 `_screen_settings.py`。发送时捕获标准Turtle的内部Tk画布，Windows只捕获该画布HWND，不发送窗口标题、工具条、其他应用或整个桌面。窗口须保持可见，不能最小化。关闭窗口才关闭USB会话，发送后等待期间SDK心跳持续运行；如果启用了默认页面，窗口关闭后由固件恢复默认页。

Windows 工程的 [统一安装入口](../../安装Python环境.cmd) 已在根目录 `.venv` 安装绘图依赖。若只分发 SDK wheel，可在同一个课程环境安装 wheel 的 `[drawing]`。依赖 Pillow 12.3～13；图片功能会延迟导入，Linux 还需系统提供 Tk。

API形式：`from ai_robot.drawing import capture_turtle, send_turtle`。`capture_turtle(screen)`返回调用方拥有的Pillow RGB图像；`send_turtle(robot,screen,fit="contain")`捕获后发送并关闭临时图像。它不会帮调用方延长Robot上下文；使用 `_turtle.finish` 才会按窗口生命周期保持连接。

已有图片可调用 `robot.display.image("picture.png", fit="contain", background="black")`，或直接传Pillow Image对象。源图最多1600万像素；目标采用当前旋转后的屏幕尺寸。`contain`保持完整内容并居中补边，`cover`居中裁切铺满。透明区域按背景色合成，源文件的EXIF方向会先应用。

图片按RGB565大端、每块最多384像素（768字节）通过 `display.bitmap` 传输，错误不自动重发。完整图片可以大于8KiB，因为这是RAM中的临时显示流；**不会保存为页面包、不会写NVS，也不会自动成为开机画面**。中途失败可能留下部分图像，用户修正后再明确点击发送。

低层接口：`robot.display.bitmap(x,y,width,height,pixels)`，pixels必须是精确width*height*2字节的RGB565大端bytes，矩形须在已初始化的屏幕内且不超过384像素。固件需声明display_bitmap能力；未支持的固件会明确拒绝。

Turtle图像会按目标屏幕分辨率缩放，电脑字体、细线和大画布的细节不保证在128×160屏幕上逐像素保留；这条路径传的是实际画布像素，不是SVG或一组固定绘图命令。

## JSON 页面包

页面包是数据JSON，不含可执行脚本。它可以含文字、矩形、线段与小图标，保存在板上后使用名称切换。支持1～4页、合计最多32个控件、最多4张图像；每张图像边长1～48像素，全部RGB565图像解码合计不超过4608字节，整个紧凑UTF-8 JSON不超过8192字节。图像数据采用RGB565大端像素的base64，网页编辑器导入图片后可完成转换。

```python
from ai_robot import Robot

with Robot() as robot:
    robot.pages.upload("my_pages.json")
    robot.pages.show("home")
    robot.pages.text("status", "准备就绪")
    robot.wait(5)
```

屏幕型号及引脚仍由 `display.configure()` 配置，页面包不改GPIO；显示前须退出维护，画布尺寸须与旋转后的屏幕一致。`pages.upload()`只保存，不启用开机页，成功后可用 `pages.download()` 读回独立dict。`pages.info()`查询页面名、大小、CRC32和启动状态。传输按768字节分块并检查偏移/CRC32；错误不自动重发，上传失败尽力取消暂存，不覆盖原异常。

```python
with Robot() as robot:
    robot.pages.startup("home", enabled=True)
```

上例**明确启用**默认页：正常退出后由ESP32恢复home；断开电脑、重启后也由ESP32显示，不需要Python心跳。新控制会话临时停止默认页，结束后恢复。进入维护会停止默认页，保存的维护标记会阻止重启显示；GPIO与舵机仍按原安全策略释放，只有屏幕参与默认程序。

停用默认页：`robot.pages.startup(enabled=False)`。删除页面：`robot.pages.clear()`先进入维护，删除后仍保持维护，屏幕与舵机映射保留。运行时 `pages.text(id,text)`只改变当前页的文字，不写Flash；切页或恢复默认页时回到已保存文字。保存新包会关闭自动启动，需要再次明确启用。

JSON校验可离线执行：`from ai_robot.pages import validate_project, load_project`。`validate_project(dict)`严格验证并返回深拷贝；`load_project(path)`读取最大64KiB的格式化UTF-8 JSON源文件，不执行内容，紧凑序列化后的页面包仍限8KiB。示例项目位于 `examples/pages/page_demo.json`，对应160×128横屏；屏幕尺寸不同须先用编辑器调整布局。

学员短脚本位于 `tests/quick/pages_upload.py`、`pages_show.py`、`pages_startup.py`、`pages_startup_off.py`。首次建议先上传显示，再单独运行开机页脚本；不要把演示上传等同于默认启用离线显示。

## 学员直接运行

优先使用项目的 [`tests/quick`](../../tests/quick/README.md) 简易示例。打开 `02_rgb.py` 点击运行即可，不需要命令行参数。依赖安装后，示例会直接加载本项目 SDK 源码。多个USB串口时在当前文件明确写COM端口；旧无参数入口读取项目可选的config/hardware.json。完整的基础板级固件须先安装，旧常亮白灯诊断固件不兼容教学 SDK。

```python
from ai_robot import Robot

with Robot() as robot:
    robot.led.color("red")
    robot.wait(2)
```

`Robot()` 默认使用 `port="AUTO"`；`with` 结束时关闭会话、请求停止输出。`wait()` 接收不小于 0 的有限秒数，后台心跳在等待期间正常运行，发现心跳失败或连接关闭会尽快报错。它不自动重连或重发命令，也不替代外设物理反馈。`heartbeat_interval=None` 是高级测试设置，会禁用心跳，长时间等待仍可能导致固件租约到期。

`robot.led.color(name, brightness=16)` 支持 `red/green/blue/yellow/white/off`；亮度为整数 0～32。原有 `led.set(red=..., green=..., blue=...)` 混色方式继续保留。简易示例将 RGB、GPIO、按钮、ADC、PWM 和舵机分别放在独立文件，学员不用编写连接管理和异常清理代码。

## 安装与状态查询

需要 Python 3.11 或以上。Windows 完整工程先运行一次 [统一安装入口](../../安装Python环境.cmd)，然后从 `ai_maker` 目录执行：

```powershell
.\.venv\Scripts\python.exe .\examples\device_status.py --port COM4
```

端口名称应按实际设备填写。构造 `Robot` 会打开端口、验证设备身份并建立租约，不会自动配置或驱动输出。`port="AUTO"` 仅在系统恰有一个 USB 串口候选时选择它，随后仍验证协议；零个或多个候选会要求显式指定，不逐个探测。驱动开串口时某些开发板可能复位，需按实物确认。

```python
from ai_robot import Robot

with Robot(port="COM4") as robot:
    print(robot.get_info())
    print(robot.get_status())
    print(robot.list_pins())
```

只有已烧入本地教学固件的设备可以使用以上代码。不要将旧维护命令串口当作协议 v1 端点。

若开发板在打开串口后复位且初次握手超时，SDK 会关闭连接；确认设备启动完成后，可显式重新运行状态查询或重建 Robot。不会自动重发动作命令，也不会把超时当作未执行。

## 板载 RGB

已声明 `capabilities.builtin_led=true` 的设备可以使用专门板载灯接口，无需把保留的 RGB GPIO 分配给普通 GPIO 实验。每色通道值为整数 0～32；未填写的通道默认 0，布尔、浮点、字符串和越界数值均在发指令前拒绝。

```python
with Robot(port="COM3") as robot:
    print(robot.led.set(red=8, green=0, blue=0))
    print(robot.get_status()["led"])  # 最后指令值，不是光学测量
    robot.led.off()
```

回执中的 `state="commanded"`、`physical_verified=False` 表示发出了控制指令，没有验证灯光实际颜色。维护模式拒绝颜色操作；会话关闭、超时和 `robot.stop()` 会清零 RGB 指令。需要观察实际颜色时运行显式演示：

```powershell
python .\examples\builtin_rgb.py --port COM3 --run --cycles 1 --seconds 2
```

此演示依次保持红、绿、蓝指令供观察，正常结束或中断时尝试关闭灯光。仅通信回执不能证明颜色顺序与实际模块一致。

## GPIO ADC 与 PWM

以下代码会实际输出，须先核对设备、接线和允许引脚。LED 串限流电阻；ADC 只输入允许范围内的电压。

```python
with Robot(port="COM4") as robot:
    robot.gpio.setup(12, "output")
    robot.gpio.write(12, 1)
    print(robot.gpio.read(12))
    robot.gpio.release(12)

    robot.gpio.setup(1, "input")
    print(robot.adc.read(1))  # 原始 12-bit 计数，不是校准后的伏特数

    robot.gpio.setup(12, "pwm")
    robot.pwm.write(12, 25)  # 首版固定 1 kHz，25% 占空比
    robot.stop()
```

数字输入还支持 `input_pullup`、`input_pulldown`。GPIO 必须先 setup；ADC 必须先设为 input。芯片专用、板载占用和已配置舵机引脚由固件拒绝。

以上示例中的 GPIO12 只适用于它未被舵机等配置占用的情况。`servo.release` 仅停止脉冲；要把已配置的舵机引脚重新用于普通 GPIO，需要在维护模式下移除或更换该映射。

## 舵机配置与换线

原型舵机使用匹配电压和峰值电流的外部供电支路，非隔离方案按设计共地。不要从 GPIO 或开发板 3.3 V 稳压器供电。初次校准不安装受力连杆，不使用悬挂负载。

换线顺序：进入维护并确认 → 断电换线 → 重上电仍为维护 → 通过 USB 更新配置 → 确认接线及校准后退出维护 → 显式发动作命令。`servo.configure` 会进入维护、保存映射并保持维护，不自动移动，也不能替代换线前的维护步骤。

```python
with Robot(port="COM4") as robot:
    robot.servo.configure("head", pin=12, min_angle=30, max_angle=150)
    print(robot.config.get())
    # 在真实接线和校准确认完成前，不退出维护，不发 move。
```

接线、供电和校准确认后，单独执行动作：

```python
with Robot(port="COM4") as robot:
    robot.maintenance.exit()
    result = robot.servo.move("head", angle=90)
    print(result)  # position_verified=False：无反馈舵机的实际位置未被测量
    input("观察完成后按 Enter 释放控制脉冲")
    robot.servo.release("head")
```

默认脉宽为 500～2500 µs，需针对实际舵机批次校准；角度上下限独立限制可发出的目标位置。配置最多四路、引脚不得重复，使用名称替代固定通道号。要删除舵机映射，在维护模式下通过 `config.get()` 获取完整配置，删除相应项，再调用 `config.apply(config, expected_revision=revision)`。配置冲突、旧修订号、保存失败都会收到设备错误。

## 会话 异常与关闭

默认每秒发送心跳，设备租约为 6 秒。正常 `close()` 或退出 `with` 请求结束会话；异常断线后，固件必须通过租约超时释放 GPIO/PWM 与舵机脉冲。信号释放不切断舵机电源，也不保证机械结构保持或释放负载。

固件在结束会话时若明确返回 `HARDWARE_ERROR` 等错误，`close()` 和正常退出 `with` 会抛出 `DeviceError`，并在抛出前关闭串口；例如 RGB 熄灭失败不能当作测试成功。`SESSION_REQUIRED` 表示租约已经到期、当前连接不再拥有输出，关闭时按会话已结束处理；仍应查询状态和观察实物确认输出是否释放。关闭后的对象不可继续使用，重复 `close()` 不重发请求。若程序正文已经抛出异常，退出时保留原始异常，关闭错误不会覆盖它。请求超时或连接丢失时的最后一次关闭仍为尽力而为，SDK 不自动重发，输出是否释放须结合实物及固件状态确认。

请求与心跳共享同一串口锁，依据 request_id 匹配回执。SDK 不自动重试动作；`RequestTimeout` 表示结果未知，不能简单再发一次非幂等动作。后台心跳失败后，下一次调用抛出 `ConnectionLostError`，需要显式重新连接。

```python
from ai_robot import DeviceError, RequestTimeout

try:
    with Robot(port="COM4") as robot:
        robot.servo.move("head", 60)
except DeviceError as error:
    print(error.code, error.request_id, error.message)
except RequestTimeout as error:
    print(error)  # 先查询设备和实际状态，不盲目重复动作
```

`heartbeat_interval=None` 只用于受控测试或自行管理租约的情况；长时间无命令会到期。任意学生网页和AI模块仍抛出 `UnsupportedCapability`；音频在旧固件不支持时也明确拒绝，不会模拟成功。屏幕接口在固件未声明display能力时也明确拒绝，不改写配置。

## SPI 屏幕

支持 `st7789_240x320`、`st7789_240x240` 和 `st7735s_128x160`。7针与8针ST7789共用相应控制器设置；8针有BLK并接GPIO时可调背光。SCK、MOSI、CS、DC、RST及可选BLK均可改为合法空闲GPIO，不能与舵机或系统资源冲突。参考接线为4、5、15、7、6，背光默认-1（无GPIO控制）。

最短上手：在当前程序调用display.set填写屏幕型号及引脚；原tests/quick的兼容设置现读取项目可选config/hardware.json。示例公共模块会保存配置、退出维护并初始化屏幕；运行前应完成接线、供电及屏幕型号确认。结束时会话关闭，固件关闭显示并释放SPI及背光，配置保留。换屏、换线应先维护并断电。

完整SDK写法：

```python
with Robot() as robot:
    robot.display.configure("st7789_240x320", sck=4, mosi=5, cs=15, dc=7, rst=6)
    robot.maintenance.exit()  # 已确认实物接线后才退出维护。
    print(robot.display.begin())
    robot.display.fill("black")
    robot.display.text("你好，创客！", x=8, y=8, color="white")
    robot.display.rect(8, 40, 100, 30, color=(55, 88, 99), filled=True)
    robot.display.line(8, 80, 110, 80, color="yellow")
    robot.wait(5)
```

`configure()`与`unconfigure()`保留原舵机映射，只修改屏幕配置，保持维护状态；不会自动初始化屏幕。`begin()`清黑屏并初始化，绘图前必须调用。`release()`关闭显示并释放运行资源，不删除保存的引脚配置；`unconfigure()`在维护中删除屏幕映射，才能让这些引脚重新用于GPIO等实验。保存映射后重启仍不自动点屏。

绘图颜色接受8种名称 `black/white/red/green/blue/yellow/cyan/magenta`、0～65535的RGB565整数，或每通道0～255的RGB元组（SDK转换为RGB565）。这与板载灯 `led.set()` 每通道0～32的限制不同，LED接口保持原样。

`text()`使用文泉驿12px GB2312字体，支持常用中文及英文；坐标按文字左上角计，换行行高16px，不自动折行。单条最多192个UTF-8字节，禁止NUL与其他控制字符（允许换行）。屏幕像素宽高随`rotation=0..3`调整，矩形和线段坐标须落在当前屏幕范围。

带GPIO背光时 `configure(backlight=16, brightness=60)`，之后用 `display.brightness(20)` 临时调整0～100%。它占用一个LEDC通道，因此普通PWM最多3路，舵机仍最多4路。无背光GPIO时brightness固定100，亮度命令不支持；BLK直接接电源也不能通过软件调光。模块BLK是控制端还是背光供电端，应按具体模块规格接线。

本接口不使用MISO、没有屏幕在场或光学反馈。`state=commanded`、`physical_verified=False`仅表明指令执行，仍需观察实物颜色、文字、完整显示范围和方向。

## 验证

从 `ai_maker` 目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\sdk\python\src).Path
python -m unittest discover -s .\sdk\python\tests -v
```

SDK 单元测试用分块字节传输验证请求编号、启动噪声、协议拒绝、超时不重发、错误码、关闭与心跳并发、数值类型、维护配置、RGB 参数与指令回执及 AUTO 歧义。它不是物理硬件测试。

设置 `AI_MAKER_NATIVE` 为主工程编译的 native 固件可执行文件绝对路径后，同一命令会额外通过子进程运行真实 C++ 协议核心，覆盖 GPIO/ADC/PWM、舵机维护配置、动作、重映射、修订冲突、RGB 状态和停止清零及关闭。未设置该变量时这些测试明确跳过。

```powershell
$env:AI_MAKER_NATIVE = (Resolve-Path .\build-native\ai_maker_native.exe).Path
python -m unittest discover -s .\sdk\python\tests -v
```

新组件没有可运行的旧 SDK 基线，因此未把包不存在的导入错误当作有效 Red 证据；替代证明为协议行为测试、同一 C++ 核心跨进程联调及 ESP32 目标编译。RGB 增量先以缺失接口的失败测试建立 Red，再实现并复测。供电、实际颜色、GPIO 电平、ADC 精度、PWM 波形和舵机行程需要各自的实机证据，以主工程记录为准。本目录的自动化测试不打开真实串口或烧录设备。tests/quick内的简易脚本点击运行就会建立会话并执行对应操作；上传页面、启用开机页须按文件说明分别进行。
