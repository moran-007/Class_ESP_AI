# V0.3 屏幕实现合同（协议仍为v1）

固件与SDK均为0.3.0。一个独占SPI屏幕，原项目参考SCK4/MOSI5/CS15/DC7/RST6，BLK可选-1（无GPIO控制）或合法空闲GPIO；所有信号可配置，MISO不使用。支持panel枚举`st7789_240x320`、`st7789_240x240`、`st7735s_128x160`。7/8针ST7789使用相同控制器；有BLK且接GPIO时配置backlight，否则-1。rotation=0..3，invert布尔（ST7789通常true，ST7735通常false）。

## 配置与生命周期

已有schema_version=1与servos保留，新增可选display字段，缺失或null表示禁用，序列化禁用时省略：

```json
{"schema_version":1,"servos":[],"display":{"panel":"st7789_240x320","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":-1,"rotation":1,"invert":true,"brightness":60}}
```

display对象必须具备以上全部字段，拒绝未知字段、类型不符、系统保留脚、重复脚和与任意舵机脚冲突。配置只在维护模式保存；恢复配置、重启、退出维护均不初始化屏幕。配置有效即保留屏幕引脚，不论是否已begin；pins.list的owner为display。一个背光GPIO占用LEDC通道3，一般PWM配额因此从4变3，舵机仍4；-1时一般PWM仍4。brightness=0..100，带BLK以固定1kHz/14bit PWM控制。无BLK只能存brightness=100，brightness命令明确不支持。

display.begin显式初始化SPI和屏幕、清黑屏。其余绘图先要求begin。会话停止/关闭/租约到期/维护进入会关闭显示、停止背光并释放SPI及相关GPIO；配置仍保留。所有图像回执state=commanded,physical_verified=false；没有MISO读回或屏幕在场检测，正常回执不能确认实际接线/图像。

## 操作

- device.info: capabilities.display/configurable_display_pins=true；display_panels列举三个枚举，limits.display_text_bytes=192。
- device.status.display: configured,active,driver_ok,panel,width,height,brightness,physical_verified=false；width/height按rotation调整。
- display.begin {} -> width,height,panel,state,physical_verified。
- display.fill {color:0..65535} -> state,physical_verified。RGB565颜色。
- display.text {x,y,text,color} -> state,physical_verified。text为1..192 UTF8字节，禁止NUL、控制字符（仅允许换行），内置文泉驿12px GB2312字体；x,y按左上角计，行高16，不自动换行。
- display.rect {x,y,width,height,color,filled:bool} -> state,physical_verified。
- display.line {x0,y0,x1,y1,color} -> state,physical_verified。
- display.brightness {percent:0..100} -> brightness,state,physical_verified。有BLK才支持。
- display.release {} -> released:true，幂等，维护模式可用。

坐标须为整数，落在当前可视范围；矩形须完整在屏内，w/h>0。color必须为整数RGB565。文字长度、UTF8合法性与控制字符需板端验证。只有本会话可操作；维护模式只允许release，其余硬件命令仍拒绝。begin失败释放已分配屏幕资源，状态driver_ok=false，返回HARDWARE_ERROR。失败清理不得阻止GPIO和舵机释放。

## SDK

`robot.display.configure(panel='st7789_240x320', *, sck=4,mosi=5,cs=15,dc=7,rst=6,backlight=-1,rotation=1,invert=None,brightness=None)`读现有配置保留servos，在维护中保存屏幕配置并保持维护；默认invert按panel，brightness无BLK100、有BLK60。

`begin()`、`fill(color='black')`、`clear(color='black')`、`text(text, x=0,y=0,color='white')`、`rect(x,y,width,height,color='white',filled=False)`、`line(x0,y0,x1,y1,color='white')`、`brightness(percent)`、`release()`、`unconfigure()`（维护中删除display配置，保留servos，仍维护）。

SDK颜色接收常见名称black/white/red/green/blue/yellow/cyan/magenta、RGB565整数0..65535，或RGB三元组0..255转换为RGB565；拒绝bool/浮点/越界。SDK先检查capabilities.display，不支持则明确异常，不写配置。不改变现有led.color和led.set限幅。

新短示例不覆盖用户01～08。独立_screen_settings.py集中panel与pins，_screen.py的connect_screen()调用connect、保存配置、显式退出维护、begin再yield，结束由现有会话清理。screen_colors.py、screen_text.py每文件约10～15行。文档明确运行表示已完成接线且会保存配置；一次连接一种屏幕，换屏断电，背光接法须按模块确认。

Hardware接口已定义于device_core.h：beginDisplay(DisplaySpec)、fillDisplay、textDisplay、rectDisplay、lineDisplay、brightnessDisplay、releaseDisplay。ESP驱动封装BoardDisplay，提供begin/fill/text/rect/line/brightness/release，参数与Hardware对应。release为幂等，尽力关闭/释放所有自己的GPIO，即使个别失败也继续清理；无物理反馈。
