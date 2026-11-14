# 可复制到其他电脑的SDK示例

这些文件只导入已安装的 `ai_robot`，没有 `_board`、项目目录定位或绝对路径。安装SDK0.5.0后，可以把某个文件单独复制到其他文件夹编写、运行。IO直接在文件开头 `set(...)` 中调整。

首次使用另一台电脑：Python3.11+ → `python -m pip install ai_maker_robot-0.5.0-py3-none-any.whl` → 修改COM串口及IO → 运行一个示例。图片/Turtle再安装同一wheel的 `[drawing]` 扩展，且Python需带Tcl/Tk；详细步骤见 [跨电脑安装说明](../../docs/跨电脑安装与直接导入_V0.5.md)。

| 文件 | 所需外设/行为 |
|---|---|
| 01_info.py | 只需USB，打印当前固件能力和引脚分类 |
| 02_audio_record.py | INMP441，记录3秒，保存当前工作目录recording.wav及电平统计 |
| 03_audio_tone.py | MAX98357A+扬声器，播放1秒低幅440Hz测试音 |
| 04_audio_echo.py | 两个模块共享时钟，先记录3秒再播放，半双工 |
| 05_audio_file.py | 播放严格16kHz/单声道/16bit PCM WAV |
| 06_audio_url.py | 同一播放链读取显式HTTP/HTTPS WAV；示例地址需先自行提供文件服务 |
| 07_io_types.py | 明确区分digital数字量、analog ADC、pwm占空比；先按注释接线 |
| 08_turtle.py | 标准Turtle窗口，发送功能来自SDK包内，关闭窗口释放整条连接 |
| 09_rgb.py | 只需USB，板载RGB自定义低亮度颜色 |
| 10_servo.py | 独立匹配供电并共地的SG90，运行立即发90° |
| 11_display.py | 自定义IO的ST7735S，显示中文与RGB颜色矩形 |

逐项用途、短代码、参数解释和常见问题见 [开发指南](../../docs/开发指南.md)。后续新增功能同时更新该指南与本表；上述文件可单独复制，所有IO按实际接线调整。

音频功能要求教学固件0.5.0；旧固件会明确报不支持，不模拟成功。默认接线来自原项目但不是强制接口。INMP441的SD是**音频数据输出**，接ESP32 din；MAX98357A的DIN接ESP32 dout，功放SD/EN是**关断控制**，不是数据。换线先维护、断电。麦克风L/R接地选left；若接高电平，set中改mic_channel="right"。

电平统计只能帮助定位全零、削顶等数据问题，不证明实际收音/播放质量。功放需要匹配的供电和扬声器；BTL扬声器输出不能把任一端直接接GND。仅传图/音频回执不等于实物验收。关闭程序会停止运行输出；sd=-1时软件不能保证功放物理断电。

本地和云端统一数据对象是AudioClip：固定pcm_s16le/16000Hz/mono/16bit/little。WAV只是在电脑存文件的容器。URL接口仅下载明确提供的WAV或显式声明的原始PCM，不做语音识别、聊天、TTS或MP3解码，也不会自动访问旧云服务。
