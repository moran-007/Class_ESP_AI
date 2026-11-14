# set接口、屏幕丝印对照与图片发送帧率

适用版本：Python SDK **0.4.1**，兼容当前ESP32教学固件 **0.4.0**。本次简化接口在电脑SDK中实现，不要求重新烧录固件。更新日期：2026-11-11。

新增写法是：**创建一次连接 → 设置所有设备 → start一次 → 发送动作 → close**。可以直接写 `Robot(port="COM5")`，无需使用with；长期运行的程序建议用try/finally保证异常时也关闭连接。

## 1. 最短屏幕示例

下面的IO适用于目前已测通的ST7735S横屏接线。换屏或换线前断电，并修改成实际GPIO编号。

```python
from ai_robot import Robot

robot = Robot(port="COM5")
robot.display.set(4, 5, 15, 7, 6, 16, panel="st7735s_128x160")
robot.start()
robot.display.text("你好，小创客", x=8, y=8)
robot.wait(5)
robot.close()
```

六个位置参数的顺序固定为：

```text
display.set(SCK, MOSI, CS, DC, RST, BLK, ...)
```

这是API的信号顺序，不是屏幕排针的物理顺序。不能因为某块屏幕从左到右写VCC/GND/SCL/SDA，就把这些排针位置直接依次填入set。

短示例中的close在正常结束时执行；若中途抛异常，这一行可能无法执行。第5节给出异常时也清理的完整写法。

## 2. 按屏幕上的丝印填写

同一个SPI信号在不同屏幕模块上可能使用不同名称。`display.set()`支持下面列出的名称，大小写不敏感。

| 真实信号 | 标准参数 | 可接受的丝印别名 | 当前参考GPIO |
|---|---|---|---|
| SPI时钟 | `sck` | `SCK`、`SCL`、`CLK`、`SCLK` | 4 |
| SPI电脑/主控发送数据 | `mosi` | `MOSI`、`SDA`、`DIN`、`SDI` | 5 |
| 片选 | `cs` | `CS`、`SS` | 15 |
| 数据/命令选择 | `dc` | `DC`、`A0`、`RS` | 7 |
| 复位 | `rst` | `RST`、`RES`、`RESET` | 6 |
| 背光控制 | `backlight` | `BACKLIGHT`、`BLK`、`BL` | 16或-1 |
| 电源正极 | 无 | VCC、VDD、3V3、5V属于供电标识 | 按模块电气要求接电源 |
| 电源地 | 无 | GND | GND |

例如模块标记为SCL、SDA、CS、DC、RES、BLK，可以这样写：

```python
from ai_robot import Robot

robot = Robot(port="COM5")
robot.display.set(SCL=4, SDA=5, CS=15, DC=7, RES=6, BLK=16,
                  panel="st7735s_128x160", rotation=1)
robot.start()
robot.display.fill("blue")
robot.wait(5)
robot.close()
```

另一块模块标为CLK、DIN、SS、A0、RESET、BL，也可写成：

```python
robot.display.set(CLK=4, DIN=5, SS=15, A0=7, RESET=6, BL=16,
                  panel="st7735s_128x160")
```

上面的SCL/SDA是在**本项目已支持的SPI屏幕模块**中的别名，不代表所有名为SCL/SDA的设备都是SPI。I²C显示器、触摸接口或丝印有歧义的LCD模块，应先按控制器和模块资料确认，不能仅凭两个标签判断接法。触摸IRQ、MISO、TE等脚也没有在本接口中映射为其他信号。

### 每个信号只写一次

以下写法会在发送配置前报错，即使两个值相同也会拒绝：

```python
robot.display.set(sck=4, SCL=4, panel="st7735s_128x160")
```

原因是sck与SCL是同一个信号。选择一种写法即可。未知名称、拼错的标签也会提示可用对照；不会悄悄忽略。

VCC、VDD、GND、3V3、5V不能作为GPIO信号配置。传入这些标签会在进入配置操作前报错。电源接线不由Python分配。

## 3. display.set完整参数

```text
robot.display.set(sck=None, mosi=None, cs=None, dc=None, rst=None,
                  backlight=None, *, panel="st7789_240x320",
                  rotation=1, invert=None, brightness=None,
                  fps=None, **labels)
```

| 参数 | 范围与行为 |
|---|---|
| sck/mosi/cs/dc/rst | 各为可用GPIO整数，信号不能重复；还需通过板端保留脚及资源冲突检查 |
| backlight | GPIO整数，或-1表示不通过GPIO控制背光 |
| panel | `st7735s_128x160`、`st7789_240x320`或`st7789_240x240` |
| rotation | 0～3整数；1/3为交换宽高后的方向 |
| invert | True/False；None按型号自动选择，ST7789为True，ST7735为False |
| brightness | 0～100整数；None时有GPIO背光为60，无GPIO背光为100；backlight=-1时只能为100 |
| fps | None或1～60整数；仅为电脑端 `display.image()` 增加帧开始频率上限，详见第6节 |
| labels | 第2节列出的大小写不敏感别名；不接受任意标签 |

没有填写的信号使用原configure接口的默认值：SCK4、MOSI5、CS15、DC7、RST6、backlight=-1。这里**不会读取并沿用上一块屏幕的全部实际接线**。更换屏幕时建议把所有信号写全，尤其有GPIO背光的模块需明确填BLK。

默认panel仍是ST7789 240×320；当前实际使用ST7735S时必须明确 `panel="st7735s_128x160"`，不会自动识别控制器型号。

`set()`会保存板端屏幕配置、停止运行输出并保持维护状态，同时记住本次连接需要在start时初始化屏幕。返回值与configure相同，为新的 `revision`、`config`。

旧写法 `display.configure(...)` 保留。它只保存配置，不设置本次set/start流程的“需要启动屏幕”标记；旧流程继续明确调用 `maintenance.exit()`、`display.begin()`。不要把两套生命周期规则混在一起推断。

## 4. servo.set与多个设备

舵机简写：

```text
robot.servo.set(pin, *, name="test", min_angle=30, max_angle=150,
                min_pulse_us=1000, max_pulse_us=2000)
```

第一个参数直接写信号GPIO。默认使用课堂SG90预设30～150°、1000～2000µs；仍须按实际舵机供电和校准确认。这个预设与旧 `servo.configure()` 的默认脉宽500～2500µs不同。

`set()`会保存该名称的映射并保持维护，不会移动。按同一name再次set会替换该项；不同舵机必须使用不同名称、不同GPIO。系统最多保存4个舵机，屏幕信号与舵机之间也不能重用GPIO。

以下程序在一个USB连接中设置一块屏幕、两只舵机和一颗外部LED。`test`使用目前已有的GPIO14映射，第二只使用GPIO13。须先确认两只舵机实际独立供电、共地，屏幕接线与代码一致；LED经限流电阻接GPIO12/GND。

```python
from ai_robot import Robot

robot = Robot(port="COM5")
robot.display.set(4, 5, 15, 7, 6, 16, panel="st7735s_128x160")
robot.servo.set(14, name="test")
robot.servo.set(13, name="head")
robot.start()

robot.gpio.setup(12, "output")
robot.gpio.write(12, 1)
robot.display.text("两个舵机", x=8, y=8)
robot.servo.move("test", 90)
robot.servo.move("head", 90)
robot.wait(3)
robot.close()
```

这些动作共用同一个robot会话，不需要为屏幕和两只舵机创建三次连接。另一个程序同时打开同一设备，可能遇到串口被占用或DEVICE_BUSY。

### 为什么所有set都要放在start之前

每次保存配置都会进入维护、停止旧运行输出。因此应先做全部display.set/servo.set，接着start，最后才setup普通GPIO、绘图和move。若先点亮LED或移动舵机，再调用另一设备set，前面的运行输出会被停止。

`robot.start()`读取当前状态，必要时退出维护；仅在本连接通过display.set明确请求、且屏幕当前未激活时调用begin。它不会自动移动舵机。返回 `{"maintenance": False, "display": ...}`，display是此次begin的结果，未重新初始化时为None。

已经处于激活状态时重复start不会清屏，也不会停止正在输出的舵机脉冲。它不是“重新执行所有初始动作”。若有持久维护或存储故障仍须按实际错误处理，不会模拟启动成功。

## 5. 异常时也关闭的完整写法

短课堂示例便于阅读；需要在报错、Ctrl+C时也及时关闭会话，可以使用try/finally，无需with：

```python
from ai_robot import Robot

robot = Robot(port="COM5")
try:
    robot.display.set(4, 5, 15, 7, 6, 16, panel="st7735s_128x160")
    robot.servo.set(14, name="test")
    robot.start()
    robot.display.text("设备就绪", x=8, y=8)
    robot.servo.move("test", 90)
    robot.wait(3)
finally:
    robot.close()
```

close停止会话运行输出并保留保存映射；非维护且启用默认页面时，恢复板端默认页。它不会自动把舵机转回90°，也不切断舵机电源。程序仍运行并保持心跳时，不必反复release再配置；完成实验后关闭即可。意外断连仍由固件6秒租约回收。

## 6. fps究竟控制什么

```python
robot.display.set(4, 5, 15, 7, 6, 16,
                  panel="st7735s_128x160", fps=5)
```

这里的fps=5表示：同一robot的后续 `display.image()` 整屏图片传输，在电脑端限制相邻两帧开始发送的频率不超过每秒5次。第一次发送无需为此额外等待；实际传输和图片处理已超过间隔时不会补发丢失帧。

| 概念 | 当前支持情况 |
|---|---|
| 图片帧开始频率上限 | 支持，set中的fps=1～60整数；None关闭额外节流 |
| 保证实际5/30/60 FPS | 不保证；USB请求往返、分块、分辨率、Pillow处理和代码都会影响实际速度 |
| 修改LCD控制器物理扫描/刷新频率 | 不提供；fps参数不是屏幕寄存器设置 |
| 限制text/rect/line/fill/bitmap调用频率 | 不提供；fps只约束image整帧发送入口 |
| 确认屏幕已经扫描显示完该帧 | 不提供；没有光学或TE同步反馈 |

`send_turtle()`最终调用image，因此使用同一robot时也受该电脑端上限约束。普通Turtle界面仍以画好后点击发送为主；没有把海龟每一步自动实时投送到屏幕。

fps保存在当前Python对象中，不写入板端NVS，关闭连接或新建Robot后需要重新设置。调用display.set时也会重置本对象的上一帧计时起点。

### image返回的transfer_seconds

```text
{
  "width": 160,
  "height": 128,
  "chunks": 64,
  "state": "commanded",
  "physical_verified": false,
  "transfer_seconds": 本次分块传输耗时
}
```

`transfer_seconds`从本帧开始分块发送计时，包含RGB565分块编码与USB请求/回执过程，不含此前Pillow图像加载、适配缩放及帧率节流等待。它也不测量面板实际扫描时间。不能用它的倒数当作整个绘图程序的真实帧率。

### 实测自己程序的平均帧率

下面是可自行运行的图片传输计时示例，需安装Pillow。它在循环外准备两张纯色图片，用monotonic测完整image调用循环，包含循环中的适配、节流与传输开销。

```python
from time import monotonic
from PIL import Image
from ai_robot import Robot

robot = Robot(port="COM5")
images = []
try:
    robot.display.set(4, 5, 15, 7, 6, 16,
                      panel="st7735s_128x160", fps=5)
    robot.start()
    images = [Image.new("RGB", (160, 128), color)
              for color in ("blue", "orange")]
    frames = 10
    started = monotonic()
    for index in range(frames):
        last = robot.display.image(images[index % 2])
    elapsed = monotonic() - started
    print("完整循环平均帧率：", round(frames / elapsed, 2), "FPS")
    print("最后一帧传输耗时：", round(last["transfer_seconds"], 3), "秒")
finally:
    for image in images:
        image.close()
    robot.close()
```

这是供实测的程序，不是已测性能结论。短循环会受到首帧没有等待等边界影响；若用于比较，保持分辨率、图像处理和帧数一致，运行更长时间再比较。实际图像变化仍需观察屏幕，程序回执只证明命令通信结果。

## 7. 三层使用提示

1. **IDE提示**：`display.set`、`servo.set`、`robot.start`有参数签名和docstring；在IDE悬停或查看帮助，可看到位置顺序、别名和启动约定。使用代码补全时仍应按实际接线填写GPIO。
2. **运行错误提示**：未知丝印、重复别名、供电脚误填、fps范围错误会返回清晰参数提示；合法参数仍需经过设备的保留脚、占用、维护和存储检查。错误后不自动重发动作。
3. **文档和短示例**：本文集中提供丝印表、完整参数、生命周期和帧率解释；直接运行文件放在 `tests/guide/12_multi_parts.py`、`tests/guide/13_display_fps.py`。运行前看文件顶部接线说明。

改变统一硬件配置后，读取该配置的示例会使用新值；本文明确写COM5和GPIO的独立示例则以代码本身为准，不能同时维护两处不同接线还期待自动一致。

进一步参考：[完整SDK函数手册](SDK函数说明与示例_V0.4.md)、[页面编辑器与Turtle](页面编辑器与Turtle_V0.4.md)、[当前验证记录](verification.md)。
