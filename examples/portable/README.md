# 可复制到其他电脑的SDK示例

实际屏幕固化、清除与恢复原默认页的测试文件在 [tests/standalone](../../tests/standalone/README.md)，直接导入ai_robot；不会清除原页面模板或全部舵机配置。

这些文件只导入已安装的 `ai_robot`，没有 `_board`、项目目录定位或绝对路径。01～11沿用SDK0.5接口；12～14最低需SDK/固件0.6.0；15的begin/end录制最低需SDK0.6.1及固件0.6.0；16计数器需SDK/固件0.7.0及standalone_counter能力。0.6屏幕固化/清除的历史实机确认与0.7本轮验证分开记录在verification。新包尚未发布GitHub附件。可以把某个文件单独复制到其他文件夹编写、运行。IO直接在文件开头 `set(...)` 中调整。

有完整工程时只运行一次 [项目安装入口](../../安装Python环境.cmd)，用根目录 `.venv` 运行所有示例，不用再装 wheel。只带走几个 `.py` 时，在目标电脑的同一 Python 环境里安装一次相应 SDK wheel；带图片/Turtle 时一次安装该 wheel 的 `[drawing]` 并使用带 Tcl/Tk 的 Python。详见 [跨电脑安装说明](../../docs/跨电脑安装与直接导入_V0.5.md)。

| 文件 | 所需外设/行为 |
|---|---|
| 01_info.py | 只需USB，打印当前固件能力和引脚分类 |
| 02_audio_record.py | INMP441，录 3 秒后保存 recording.wav 及电平统计。SDK 0.9.0 可设置 BUTTON_PIN 按住录音。 |
| 03_audio_tone.py | MAX98357A+扬声器，播放1秒低幅440Hz测试音 |
| 04_audio_echo.py | 两个模块共享时钟，先记录3秒再播放，半双工 |
| 05_audio_file.py | 播放严格16kHz/单声道/16bit PCM WAV |
| 06_audio_url.py | 同一播放链读取显式HTTP/HTTPS WAV；示例地址需先自行提供文件服务 |
| 07_io_types.py | 明确区分digital数字量、analog ADC、pwm占空比；先按注释接线 |
| 08_turtle.py | 标准Turtle窗口，发送功能来自SDK包内，关闭窗口释放整条连接 |
| 09_rgb.py | 只需USB，板载RGB自定义低亮度颜色 |
| 10_servo.py | 独立匹配供电并共地的SG90，运行立即发90° |
| 11_display.py | 自定义IO的ST7735S，显示中文与RGB颜色矩形 |
| 15_screen_record.py | SDK0.6.1开始/结束录制，原robot绘图同步预览，随后save；固件仍为0.6.0 |
| 12_program_save.py | 仅保存板载RGB红绿循环，重启/重新接电后自动执行；需0.6 |
| 13_program_control.py | 接管停止、查询；启用/禁用/清除/当前运行均为可选择注释，默认不删除；需0.6 |
| 14_program_button.py | 固化GPIO2按钮控制GPIO12外部LED，带then/otherwise和等待；重启后动作；需0.6 |
| 16_counter.py | 板端每秒加1，重启从0；counter为末尾持续控件，保存loop=False；需SDK/固件0.7 |
| 17_wifi.py | USB 配网，支持中文名称，终端显示状态和 IPv4；`--status` 只读查询，`--clear` 清除；需支持配网的 0.8 固件 |
| 18_single_file.py | 在一个 `.py` 中使用串口、可选的 `robot.setwifi(name, password)` 和板载 RGB；配网简写需要 SDK 0.8.1 |
| 20_wifi_manage.py | 查询当前连接；修改 `CLEAR` 后可清除板端保存的网络。需 SDK 0.8.2。 |
| 21_ai_dialogue.py | 默认连接原项目 HTTPS 网关进行文字对话。`MODE = "voice"` 录 3 秒后播报，`MODE = "button"` 按住录音、松开上传并逐段播报。需 SDK 0.9.0 和服务端设备凭据。 |
| [Wi-Fi 屏幕真机测试](../../tests/wifi/README.md) | 测试入口在 `tests/wifi/`，复用板上 Wi-Fi 和屏幕接线，实时显示名称、IP 和北京时间 |

逐项用途、短代码、参数解释和常见问题见 [开发指南](../../docs/开发指南.md)。后续新增功能同时更新该指南与本表；上述文件可单独复制，所有IO按实际接线调整。

音频功能要求教学固件0.5.0；旧固件会明确报不支持，不模拟成功。默认接线来自原项目但不是强制接口。INMP441的SD是**音频数据输出**，接ESP32 din；MAX98357A的DIN接ESP32 dout，功放SD/EN是**关断控制**，不是数据。换线先维护、断电。麦克风L/R接地选left；若接高电平，set中改mic_channel="right"。

电平统计只能帮助定位全零、削顶等数据问题，不证明实际收音/播放质量。功放需要匹配的供电和扬声器；BTL扬声器输出不能把任一端直接接GND。仅传图/音频回执不等于实物验收。关闭程序会停止运行输出；sd=-1时软件不能保证功放物理断电。

本地和云端统一数据对象是AudioClip：固定pcm_s16le/16000Hz/mono/16bit/little。WAV只是在电脑存文件的容器。URL接口仅下载明确提供的WAV或显式声明的原始PCM，不做语音识别、聊天、TTS或MP3解码，也不会自动访问旧云服务。

Program只保存允许的设备流程，不能直接保存任意Python函数或把电脑Turtle、音频、图片、云端一起固化。save默认loop=False/autostart=False；示例12/14明确选择True。连接Robot即接管并停止固化，close不自动恢复，下次重启按enabled策略执行。首次安装0.6固件后，修改这些流程只需重新save；详见 [程序固化章节](../../docs/开发指南.md#15-程序固化通电后独立运行)。
