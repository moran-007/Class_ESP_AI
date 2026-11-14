# 数字/模拟IO与麦克风、功放测试 V0.5

适用：教学固件0.5.0、Python SDK0.5.0，当前ESP32-S3 N16R8原生USB。日期：2026-11-13。INMP441与MAX98357A按原项目接入，所有信号GPIO在Python代码中修改；当前参考接线不是固定接口。本轮不开发AI服务器。

## 1. 数字输入、数字输出、ADC与PWM分开使用

| 类型 | 建议API | 数据/含义 | 当前状态 |
|---|---|---|---|
| 数字输入 | `robot.digital.set(2, "input_pullup")`，`robot.digital.read(2)` | 只读0/1；按钮接地按下0 | 已实现 |
| 数字输出 | `robot.digital.set(12, "output")`，`robot.digital.write(12, 1)` | 设置低/高逻辑电平 | 已实现 |
| 模拟输入ADC | `robot.analog.set(1)`，`robot.analog.read(1)` | 原始12bit计数0～4095，不是电压值 | 已实现 |
| PWM输出 | `robot.pwm.set(17)`，`robot.pwm.write(17, 25)` | 固定1kHz，25为25%占空比 | 已实现，独立接口 |
| 真正模拟电压输出DAC | `robot.analog.write(...)` | 连续模拟电压 | 当前S3教学固件不提供，明确报不支持 |

PWM通过改变高低电平占空比调节平均效果，不能把它当成直接的模拟电压输出。音频功放也不经过普通PWM：这里使用I²S数字音频。INMP441的输出是I²S数字数据，不接ADC输入来收音。

原来的 `gpio.setup/read/write/release`、`adc.read`、`pwm.write` 保持兼容。`digital.set`拒绝pwm模式，`analog.set`只接受ADC候选GPIO1～20，再由板端检查系统保留脚和占用；不能用ADC读取GPIO21。数字输出上的read是最后指令值，不是外接电压测量。ADC未完成电压校准，不把原始计数简单称为精确电压。

`robot.list_pins()`会返回每脚 `digital_input/digital_output/analog_input/analog_output/pwm_output`，同时保留旧 `input/output/adc`。还要结合 `reserved` 和 `owner`：能力存在不表示该脚现在空闲。当前profile保留原生USB、模组存储、启动脚和RGB48等。S3芯片脚能力不等于所有开发板都引出该脚。

新固件提供引脚分页，SDK自动合并；旧SDK仍能读取原格式全表，避免扩展字段使JSON回执超过4096字节。

## 2. 麦克风与功放的接线

| 模块丝印 | 信号功能 | Python参数 | 参考GPIO |
|---|---|---|---|
| 两模块BCLK、麦克风SCK | 音频位时钟，由ESP32输出 | bclk | 42 |
| 麦克风WS、功放LRC/LRCLK | 左右声道字时钟，由ESP32输出 | ws | 41 |
| INMP441 SD | 麦克风数字数据输出，进入ESP32 | din | 21 |
| MAX98357A DIN | 功放音频数据输入，来自ESP32 | dout | 40 |
| MAX98357A SD/EN | 功放关断/使能控制 | sd | 39，可无GPIO控制时-1 |
| INMP441 L/R | 选择麦克风左/右槽 | mic_channel | 接GND选left；高电平选right |

**麦克风的SD是数据，功放的SD是关断控制，不能因为名字相同就接到同一GPIO。** 两模块共用BCLK和WS，但数据线分开。I²S和I²C不是同一种总线，不把BCLK/WS当成I²C的SCL/SDA。当前实现标准I²S，不支持PDM麦克风、模拟麦克风或需要外部MCLK的其他型号。

INMP441按3.3V供电，信号使用ESP32的3.3V逻辑域。功放按实际模块供电要求供电并共地，不能用GPIO供电。扬声器接MAX98357A的SPK+/SPK-；这是桥接输出，不能把任一扬声器端直接接地。sd=-1仅表示没有GPIO关断控制，软件停止不等于物理断电。没有扬声器接入检测或麦克风型号自动识别。

换线顺序：进入维护并确认 → 断电 → 按接线改代码 → 上电 → 全部set → start → 测试。系统脚、屏幕、舵机及其他占用会检查冲突；共享时钟只在一份audio.set里定义一次。

## 3. 最简配置及调用

```python
from ai_robot import Robot

robot = Robot(port="COM5")
try:
    robot.audio.set(bclk=42, ws=41, din=21, dout=40, sd=39,
                    mic_channel="left", volume=20)
    robot.start()
    robot.wait(0.2)  # 首次上电测试给麦克风时钟/电源留出稳定时间。
    clip = robot.audio.record(seconds=3)
    clip.to_wav("recording.wav")
    print(clip.levels)
    robot.audio.play(clip)
finally:
    robot.close()
```

`set`配置当前会话的IO并保持维护；`start`初始化I²S，功放仍静音，不自行录音/播放。`record`才读数据，`play`才使能功放。其他屏幕/舵机等映射也先set，再统一start；digital/analog/pwm.set立即设置GPIO模式，需在start之后调用。配置过程中会停止当前运行输出，不是不停机改线。

只接麦克风：`audio.set(..., din=21, dout=-1, sd=-1)`；只接功放：`audio.set(..., din=-1, dout=40, sd=39)`。不启用某方向用-1，不能把全部数据方向都关掉。默认 `volume=20` 为播放软件增益百分比0～100；不控制麦克风增益，不是自动音量校准。

音频映射**只属于这次USB会话，不写NVS**；进入/退出维护本身仍会保存维护标志，这与保存音频映射是两件事。退出程序、连接超时会结束I²S并释放映射，下次重新set；启动不会自动收音或出声。普通stop/维护会关闭当前音频硬件，但会话还在时仍保留映射，之后可重新begin/start。`audio.release()`释放硬件而保留映射，`audio.unconfigure()`同时删除会话映射，让GPIO重新空闲。

当前录音与播放采用半双工：录完再播，不同时读写；I²S底层具有双向数据引脚不等于本SDK已提供全双工对讲。每块最多768字节PCM；单条硬件操作有超时，不用一条长请求阻塞几秒。驱动不完整读写不会假装整段成功，也不自动重发可能已播放的内容。

使用原生USB CDC固件和开发板原生USB口。16kHz×16bit×mono的裸数据约32KB/s，UART115200不能支撑这一路实时PCM；UART构建的音频能力会关闭，旧GPIO等接口仍可用。USB线或电脑调度长时间卡顿也可能影响实时采样/播放连续性，本版没有音频丢帧测量和端到端实时保证。

## 4. 按顺序运行测试

先安装SDK，或运行工程根目录 `安装Python环境.cmd`。可双击 `运行音频测试.cmd` 选择一项，或直接运行以下Python文件。文件只导入 `ai_robot`，没有当前电脑绝对路径；串口和IO就在开头。

| 文件，位于examples/portable | 测什么 | 运行前/观察 |
|---|---|---|
| 01_info.py | 身份、能力及IO表 | 只需USB；先确认firmware_version=0.5.0 |
| 02_audio_record.py | INMP441收音3秒并存WAV | 只启用麦克风，近距离正常说话；观察peak/rms/all_zero |
| 03_audio_tone.py | 功放/扬声器独立测试 | 只启用功放，1秒440Hz低幅正弦，低音量起步 |
| 04_audio_echo.py | 先收音再回放 | 两模块共用时钟；不做语音识别或回声消除 |
| 05_audio_file.py | 播放电脑本地WAV | 使用之前生成的recording.wav；CWD需相同或改成明确路径 |
| 06_audio_url.py | 从本地HTTP/云端URL取得同格式音频 | 先启动提供WAV文件的服务，明确改URL，不会自动连接旧AI服务 |
| 07_io_types.py | 数字、ADC、PWM分别调用 | 按文件注释接线，一次运行一个实验 |

录音、回放、URL及本地文件目前限30秒。请先做02/03单项，再做04组合；不把板端回执当作声音已经正确。`all_zero=true`可能是错数据脚、左右槽不符、未供电、未接麦克风或启动未稳定；不能直接认定“环境很安静”。大量clipped_samples表示削顶数据，需要检查信号和设置。peak/rms有数值仍不证明听感、噪声或时序正确。

录音数据在电脑，不存板上Flash或SD卡；record.end/audio.stop结束本次收音读数，但活动I²S总线仍可能有时钟和DMA采样；audio.release或关闭连接才结束I²S。WAV只在明确调用to_wav时写文件，默认写当前工作目录。注意IDE运行目录和菜单运行目录可能不同；必要时在代码里给出明确路径。

## 5. 本地和云端使用同一种音频

统一对象 `AudioClip`：

```text
format=pcm_s16le
sample_rate=16000
channels=1
sample_width=2
byte_order=little
```

| 来源 | 获得AudioClip | 后续同样播放 |
|---|---|---|
| 麦克风 | `clip = robot.audio.record(3)` | `robot.audio.play(clip)` |
| 本地WAV | `clip = AudioClip.from_wav("recording.wav")` | 同上 |
| 本地裸PCM | `clip = AudioClip.from_pcm("recording.pcm")` | 同上；调用即明确声明是上述PCM |
| HTTP/HTTPS WAV | `clip = load_audio_url(url)` | 同上 |
| HTTP/HTTPS裸PCM | `clip = load_audio_url(url, format="pcm_s16le", sample_rate=16000, channels=1)` | 同上；还会核对响应中提供的音频头 |

`clip.to_pcm()`得到可以送给现有服务端16k/16bit/mono数据入口的字节，**不带WAV头**。`clip.to_wire()`得到schema_version/format/sample_rate/channels/sample_width/byte_order/bytes元数据，`AudioClip.from_wire(pcm, metadata)`做严格一致性校验。不能把MP3/OGG、立体声WAV、44.1kHz音频直接冒充本格式；本版不自动解码和重采样。

现有cloud_server的原始PCM实现为小端，部分旧响应使用audio/L16 MIME；标准L16与本项目小端格式容易混淆，因此SDK不会仅凭这个MIME猜字节序。应由调用方明确声明pcm_s16le，或提供正确的X-Audio-Format/X-Audio-Byte-Order/X-Audio-Sample-Rate等元数据。

本轮HTTP入口是明确URL的音频下载，不实现识别、聊天、TTS任务轮询、云端鉴权或服务器部署。URL可以先换成本地服务，后续再换线上地址而保留同一AudioClip与播放流程。本地测试服务器示例：

```powershell
# 在有recording.wav的目录运行，只绑定本机；Ctrl+C停止。
python -m http.server 8000 --bind 127.0.0.1
```

之后运行06_audio_url.py读取 `http://127.0.0.1:8000/recording.wav`。HTTP只在显式调用load/play_url时发生；SDK不会自动读取AI密钥或联系服务。下载限制大小，拒绝未知/不匹配的格式，跨源重定向不转发鉴权/cookie等敏感头。

## 6. 在另一台电脑直接写程序

安装 `sdk/python/dist/ai_maker_robot-0.5.0-py3-none-any.whl`，使用Python3.11+：

```powershell
python -m pip install .\ai_maker_robot-0.5.0-py3-none-any.whl
```

之后可在任意文件夹写 `from ai_robot import Robot, AudioClip`。不需要复制_board.py、当前E盘工程、Arduino库或固件源码。图片/Turtle再选装wheel的 `[drawing]`，入口为 `from ai_robot.turtle import finish`；原本地课程入口继续兼容。详细说明见 [跨电脑安装与直接导入](跨电脑安装与直接导入_V0.5.md)。

## 7. 实现与验证边界

软件测试、ESP32构建、安装包验证、当前开发板升级及真实收音/出声必须分别记录。本轮用户确认了两种模块，但IO将自行调整，因此在未完成实际接线前，只能验证协议、驱动故障处理、编译、安装及板端配置；不能声称麦克风/扬声器已物理验收。最新执行结果见 [verification.md](verification.md)。

实现依据：固定Arduino-ESP32 3.3.12本地头文件，以及 [Espressif I²S说明](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html)、[ESP32-S3 GPIO说明](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html)、[MAX98357A原厂数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)。旧项目源码仅作为接线与PCM格式参考，未修改旧AI或云端工程。
