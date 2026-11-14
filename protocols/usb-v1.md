# 本地 USB 协议 v1

固件家族 `ai-maker-s3`，当前版本 `0.5.0`，协议仍为 v1；基础操作仍兼容 SDK 0.2.0，页面/图片使用SDK0.4.0。实现本地板级控制、SPI屏幕、页面保存和默认显示，新增INMP441/MAX98357A音频驱动，没有AI、Wi-Fi和任意学生网页宿主。音频合同见 [audio-v1.md](audio-v1.md)。Arduino-ESP32 3.3.12；默认原生 USB CDC，可显式构建 USB 转 UART 115200 版本。屏幕配置和基础操作见 [display-v1.md](display-v1.md)，页面与位图合同见 [pages-v1.md](pages-v1.md)。

V0.4新增能力 `pages/page_images/page_startup/display_bitmap=true`。`display.bitmap`以RGB565大端base64传输最多384像素小块；SDK据实际屏幕分块整帧。`pages.*`为不执行代码的JSON页面传输、保存和显示。未持有控制会话且非维护时，可显示明确启用的默认页；关闭会话/租约到期会先释放运行输出，再恢复默认页。进入会话后默认页让出屏幕。此行为不包含舵机程序自动恢复。

UTF-8 JSONL，一行最多 4096 字节（不含换行）；输出只有结构化响应，不混入维护控制台或二进制。上电 ROM 日志可能出现，SDK 可跳过非 JSON 行。无自动重试有副作用的请求。

V0.2.1 将 UART 与原生 HWCDC 的接收缓冲统一设置为 8192 字节，覆盖完整合法帧和换行；V0.2.0 原生 USB 误用了 256 字节默认缓冲，可能在较长 config.apply 请求到达时丢字节并超时。增加主机超时时间不能补回已丢字节。

```json
{"kind":"request","protocol_version":1,"request_id":"r1","session_id":"demo-session","op":"servo.move","args":{"device":"head","angle":60}}
{"kind":"response","protocol_version":1,"request_id":"r1","ok":true,"code":"OK","data":{"state":"commanded","angle":60,"position_verified":false}}
```

失败响应 `ok:false,code:"…",message:"…"`。请求编号为非空字符串，最长 64 字节；会话编号最长 40 字节。`args` 必须为对象。数值参数只接受 JSON 整数，不接受字符串、浮点或布尔冒充整数。

## 操作合同

| op | args | data |
|---|---|---|
| device.info | {} | firmware_family, firmware_version, protocol_version, target, capabilities, limits, boot_id |
| device.status | {} | session_active, maintenance, storage_fault, config_revision, gpio 数组, servos 数组, led |
| pins.list | {} | pins 数组，每项 pin/input/output/adc/reserved/owner |
| config.get | {} | revision, config（schema_version=1，servos 数组） |
| session.open | {} | session_id, lease_ms=6000；使用请求顶层 session_id |
| session.heartbeat | {} | lease_ms |
| session.close | {} | closed:true |
| outputs.stop | {} | stopped:true；保留会话和配置，释放本会话运行输出 |
| led.set | {red:整数0～32,green:整数0～32,blue:整数0～32} | 三色指令值，state=commanded，physical_verified=false |
| led.off | {} | 三色全0，state=commanded，physical_verified=false |
| maintenance.enter | {} | maintenance:true；停止输出，持久保存维护标记 |
| config.apply | {config:{schema_version:1,servos:[…]},expected_revision:整数} | revision, config；只能在维护状态应用；保存成功才发布新配置 |
| maintenance.exit | {} | maintenance:false；不会自动输出舵机脉冲 |
| gpio.setup | {pin:整数,mode:"input"/"input_pullup"/"input_pulldown"/"output"/"pwm"} | pin, mode |
| gpio.read | {pin:整数} | pin, value=0/1；必须已 setup |
| gpio.write | {pin:整数,value:0/1} | pin, value；必须 output |
| gpio.release | {pin:整数} | pin, released:true |
| adc.read | {pin:整数} | pin, raw, bits=12；原始值，无电压校准；必须已 setup 为 input |
| pwm.write | {pin:整数,duty:整数0～100} | pin, duty, frequency_hz=1000；必须 pwm |
| servo.move | {device:字符串,angle:整数} | state:"commanded",angle,position_verified:false |
| servo.release | {device:字符串} | released:true |

device.info/status、pins.list、config.get 不要求会话，其余要求与已打开会话一致；另一会话打开时报 DEVICE_BUSY，过期会话须重新打开。心跳每 1 秒建议一次；设备过期 6 秒释放 GPIO 与 PWM，撤销舵机脉冲。释放信号不切断舵机电源，不保证机械负载安全。SDK 断连不自动重新执行动作。

会话活动时每次有效身份的操作续租；显式心跳避免长时间无命令时掉线。会话到期、关闭、维护与 outputs.stop 均将 GPIO 恢复输入（高阻）并撤销 LEDC；关闭后配置仍保留。

板载 RGB 指令通过单独的 `led` 逻辑设备执行，构建可明确选择GPIO38或GPIO48，普通GPIO接口拒绝占用当前选择的引脚。`device.info` 返回 builtin_led 描述和能力；`device.status.led` 返回 red/green/blue 最后成功指令值、driver_ok 和 physical_verified=false。上电主动发送熄灯帧；停止、维护、关闭及租约到期尝试发送熄灯帧，驱动成功才归零。驱动失败置 driver_ok=false，保留最后成功颜色，其物理状态未知；显式停止/关闭/进入维护返回 HARDWARE_ERROR，但仍释放 GPIO、舵机，并关闭会话或保存维护状态。RMT 写入超时后需复位恢复。没有光学反馈，不能仅凭回执声明实际灯色已验证。`gpio.read` 在 output 模式返回最后指令值且 source=commanded；输入模式 source=input；PWM 模式使用状态中的占空比，不通过数字读值冒充测量。

维护模式允许查询、会话、停止、配置应用与幂等display.release；其余硬件命令报 MAINTENANCE_REQUIRED。换线流程：进入维护并确认 → 断电换线 → 上电仍为维护 → 连接并应用新配置 → 退出维护 → 显式测试动作。无有效配置时初始化为空舵机列表，不自动移动；保存或恢复display映射也不自动初始化SPI。

servo 配置项：`name`（1～24 字节 ASCII 字母数字及下划线，首字符字母）、`pin`、`min_angle`、`max_angle`（0～180，严格递增）、`min_pulse_us`、`max_pulse_us`（500～2500，严格递增）。所有字段必须给出。最多 4 路；脉宽按完整 0～180 度线性换算，角度上下限独立限制。配置引脚互斥。配置结构不接受未知字段，避免拼写错误静默生效。

默认配置 `{ "schema_version":1,"servos":[] }`，所有可分配引脚空闲。当前参考板描述保守保留启动、原生 USB、UART0、模组存储与板载 RGB；以匹配发布目标为准，不能代表任意 S3 板。现有模块接线不能凭此自动识别。四路 1 kHz PWM 与四路 50 Hz 舵机分别使用有限通道，不提供任意频率接口。

历史V0.3能力：gpio/adc/pwm/servo/configurable_servo_pins/display/configurable_display_pins=true；audio_in/audio_out/sd/student_web/ai=false。屏幕SPI已可运行时配置；V0.5原生USB构建新增I²S会话映射、录放及引脚分页，详见audio-v1。SDK调用未实现模块明确报不支持。GPIO背光保留一个普通PWM通道；配置含display字段时降级旧固件前须移除该字段或恢复匹配NVS。

错误码：INVALID_REQUEST、INVALID_ARGUMENT、PROTOCOL_MISMATCH、UNSUPPORTED_OPERATION、SESSION_REQUIRED、DEVICE_BUSY、MAINTENANCE_REQUIRED、PIN_INVALID、PIN_RESERVED、PIN_CAPABILITY_MISMATCH、RESOURCE_CONFLICT、CONFIG_REVISION_MISMATCH、CONFIG_INVALID、STORAGE_ERROR、HARDWARE_ERROR、DEVICE_NOT_FOUND、ANGLE_OUT_OF_RANGE、LINE_TOO_LONG。

本地 USB 是物理可信实验通路，本版无课堂身份鉴权。维护模式、心跳和资源冲突检查不等于抵御可物理重刷设备的安全控制。
