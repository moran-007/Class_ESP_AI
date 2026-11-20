# 本地版本验证记录

本地 SDK 为 0.8.3；COM5 已运行 0.8.0 固件与 16 MiB 自定义分区。GitHub 已发布版本仍为 0.5.0。

## SDK 0.8.3：配网阶段提示

- 模拟串口验证阶段提示、成功 IP、超时保留旧配置、密码不输出及 `progress=False`；SDK 回归 145 项，1 项历史实验跳过。独立只读审查通过。
- COM5 用只读会话查询到上次配网 `connect_timeout`，当时查询的空列表不代表没有保存过网络；后来设备已自动连回保存的网络。本轮没有重发配网或改写板端凭据。

## Windows 项目环境统一

- 从空的项目根目录 `.venv` 运行统一安装入口，安装 SDK 0.8.2（读取本项目源码）、pyserial 3.5、Pillow 13.0.0；Python 3.14.0、Tk 8.6 通过检查。再次运行识别并复用同一环境，不重复安装。项目内只剩根目录一份 `pyvenv.cfg`。
- 用该环境运行 `scripts/test.ps1`：C++ 核心及驱动通过，SDK 143 项有 1 项历史实验跳过，配置 15 项及编辑器 6 项通过。从项目外启动 Wi-Fi 两个入口的 `--help` 成功。检查了 Tcl/Tk 窗口和本地课堂脚本语法，未打开串口或动开发板设置。

## SDK 0.8.2：Wi-Fi 查询与清除

- 复用固件原有 USB 操作。配网、查询、清除可在同一 `Robot` 连接中使用；只查时支持只读连接。新增 SDK 行为由模拟串口验证，完整 SDK 回归 143 项，1 项历史实验跳过。独立只读审查通过。
- 本轮 COM5 打开时返回拒绝访问，未重做实机查询，也未清除现有凭据。旧版固件的实机配网结果见下文。

## USB Wi-Fi 屏幕测试：实机连网与自动重连

- 在 COM5 实机配网，中文 SSID 正常，获得 IPv4 并保存配置。使用板上已有 ST7735S 160×128 接线运行 30 秒，屏幕初始化及名称、IPv4、北京时间绘制指令均执行完成；未做实物目视确认。测试脚本现位于 [tests/wifi/wifi_screen.py](../tests/wifi/wifi_screen.py)。
- 测试退出后用 ROM 工具复位，确认没有 USB 控制会话时按已保存配置自动连上 Wi-Fi；原接线、页面 CRC 和计数程序均保留，计数程序恢复运行。没有再次烧录或修改分区。
- 时间由电脑按 UTC+8 提供；此测试未验证板端 NTP 或脱离 USB 刷新。

## 单文件配网与 COM5 分区迁移

- COM5 串口、芯片型号、MAC 和 16 MiB 实际容量核对后，读回完整 Flash，备份存于本机 `backups/wifi_ota_com5_20261119/`。核对旧镜像、分区表校验和、空闲区域及 OTA 元数据后，写入应用、16 MiB 引导程序和自定义分区表，未整片擦除。
- 三处写入均通过 esptool 校验；首次启动前再次读回，引导程序和分区表与构建一致，NVS/PHY 区字节与迁移前完全相同，OTA 元数据仍为空。复位后设备报告 0.8.0 和 `wifi_provisioning`；接线版本仍为 38，页面 CRC 仍为 `c70fa309`，无 USB 控制会话时计数从 15 增至 17。
- `build/ota-ready-native-usb/ai_maker_s3.ino.bin` 为 1,283,712 字节；SHA256 `d46f1b3afba83ba333bce3f9d719dc2a86434a4797cb2928d45e59ed59355661`。SDK 0.8.1 wheel SHA256 `3318dcae6e12797aca3241217716a41669cab3c5a0d52b717d4461315224deeb`。
- SDK 回归 142 项（1 项历史实验预期跳过）、配置 15 项、编辑器 HTTP 6 项。独立只读审查复核分区、构建产物、Tk 串口设置和配网 SDK。COM5 当前报告尚未配网；实际路由器及 DHCP 需输入本地 Wi-Fi 信息后验证。OTA 只预留两个槽，尚未实现联网传输。

## V0.8 USB Wi-Fi 配网：迁移前的构建与软件验证

- 旧核心调用 `wifi.status` 返回 `UNSUPPORTED_OPERATION`。新核心模拟验证中文 UTF-8、控制会话限制、拿到 IPv4 才保存、失败保留旧配置、重启重连、不泄露密码，以及清除后停止重连。
- `scripts/test.ps1` 通过：SDK 141 项（1 项历史实验预期跳过）、配置 15 项、编辑器 HTTP 6 项，以及 C++ 核心和驱动检查。独立只读审查复核固件、SDK 和网页路径，按反馈修正只读接管、输入检查及异常状态。
- Playwright 用模拟设备提交中文名称，确认网页从正在配网更新为已保存并显示测试 IP，提交后密码框清空。390 像素宽显示见本机 `output/wifi_v080_browser.png`。模拟 IP 不代表接入真实路由器。
- 0.8 应用 `build/wifi-native-usb/ai_maker_s3.ino.bin` 为 1,283,712 字节，SHA256 `3287f296cc8db783118cc3d6723274bafa1551d351834b5b86bfbec07d1d6e2d`。目标构建通过；原板已确认应用区只有 1,048,576 字节，本轮未刷写或修改分区。实际 Wi-Fi 连接、DHCP、掉线恢复和独立供电仍未验收。
- SDK 安装包 `sdk/python/dist/ai_maker_robot-0.8.0-py3-none-any.whl` 为 54,109 字节，SHA256 `7f53d5657ba4db7f37666fa2e415d150751fc9408b4f2bc608359fe7e74553fd`。全新虚拟环境安装后用 `python -I` 运行 3 项配网 SDK 测试通过；终端模拟也输出了成功、中文名称和测试 IP，未输出密码。

## V0.7数字累加：固化后每秒加一实测通过

- 用户要求持续数字累加；按板端定时控件实现，默认start0、step1、interval1秒，计数存在RAM，重启回start，不每秒写Flash。display.counter是根末尾唯一终端步骤，loop=False，不是全局变量/命名页面引擎。
- 有效Red：旧0.6固件缺standalone_counter；新模型和SDK有效counter用例先因无接口而失败。新增模型5组、执行器6组通过，覆盖严格类型/终端/矩形、每秒进度、延迟追赶、uint32毫秒回绕、int64溢出停止、驱动失败、接管/close/lease/disable/clear和无NVS运行写入。
- 完整软件回归：SDK138项，137通过、1项旧学员自由实验预期跳过；配置15项、编辑器5项通过。新增2项真实SDK/生产C++核心联调含进程重启后的无owner计数、保存内容不随数值更新、接管重置、end后添加counter。
- ESP32-S3原生USB/RGB48构建通过，应用721984字节，SHA256 `7414df74fa1486c838807d369d433a656e53475975da146117d00d09280b6bd4`，小于原板1MiB应用区。
- 发现板上已有用户启用的13步A/B流程。先在`backups/counter_v070_20261115/`保存原程序及enabled/loop、原config/页面模型、真实64KiB前缀和完整1MiB旧应用；0.6应用字节和原分区表核对正确后，仅写0x10000新应用并哈希验证通过。
- 升级后0.7能力通过，原config和完整页面模型/原保存程序完整相等，舵机未激活、音频未启动。再运行portable16保存counter并ROM复位，之后无控制会话运行。
- 只读采样15次，约14.235秒从52增加到66，每条约1.017秒、数值逐次+1；超过6秒会话租约仍running/active且无错误，随后串口关闭。用户回复“每秒正常加一，显示正常”，实屏确认通过。
- 当前按用户“一直增加”要求保留计数运行，没有自动清除。清除入口tests/counter/clear_counter.py；恢复本次测试前旧A/B流程的入口restore_previous.py。两脚本已对native核心实际执行，恢复blob与原程序/loop/enabled相同；此检查没有打断真板计数。
- 独立只读counter_review确认无未解决P0/P1/P2；原用户quick文件哈希保持，不改写学员实验。实际拔USB改独立电源的冷启动未声称由软件代做，当前证明是复位后无SDK会话运行及用户观察。
- SDK wheel52967字节，SHA256 `05c3bff4958be01d1dab56d81422901796eed59025cec84db771c1d5f3ac47b9`；9模块与源码核对，版本0.7.0。本轮不提交/推送/发布，不覆盖旧GitHub附件。
- 工程editable及SDK独立环境已更新0.7.0；全新venv安装最终wheel和drawing依赖，从工程目录外以Python -I运行全部138项SDK检查通过，1项预期跳过。11份文档50段Python和全部本地链接检查通过。

证据：`output/counter_v070_hardware.json`、`counter_v070_full_tests.log`、`counter_v070_sdk_final.log`；私有备份/刷写日志均被忽略。用法见 [数字累加指南](数字累加计数器_V0.7.md) 和 [清除/恢复入口](../tests/counter/README.md)。

## SDK0.6.1：begin/end录制验证

- 新增begin/end/cancel、save省略Program的同步预览录制，保留显式Program写法；固件和协议模型不变。屏幕/舵机set及start在begin前，GPIO/PWM模式设置在块内；不是屏幕像素或设备完整运行状态截图。
- 行为Red：新增测试先因缺begin/end失败。实现后14项录制测试通过，覆盖预检、成功提交、原config快照、深拷贝、非法/不支持操作、DeviceError/超时、wait真实等待及并发、取消令牌、stop/close、中文大小/64节点上限。
- 新增2项与同一生产C++核心联调通过；完整portable15真实预览等待两次3秒，录制13步骤并保存，隐式快照与显式Program一致；原配置和清除路径验证通过。
- 最终SDK129项运行：128通过、1项旧学员实验预期跳过；配置15项、编辑器5项通过。新的全量结果记录在output/recording_v061_full_sdk.log等日志。
- 回归基线修正：用户已自由修改quick/screen_text.py，其内容不再符合旧测试硬编码的config.apply预期。保留用户文件，改用发布的portable11标准文本示例，保留原初始化顺序和close断言；其他屏幕核心验证未减弱。
- wheel51748字节，SHA256 `2325237417a2c58e6aaae731cd27f73b8bfc4dbc6f0eff1ca73b2c5ddbdb0f6b`，9个模块与最终源码逐字节相同。工程editable与SDK独立环境均升级0.6.1。
- 全新venv安装最终wheel及drawing，从工程目录外以Python -I运行完整129项SDK检查通过（1项预期跳过）。安装验证日志output/recording_v061_installed_sdk.log。
- 独立只读审查recording_review确认无未解决P0/P1/P2；45个固件/用户quick文件hash与保护快照一致。8份相关文档48段Python语法与本地链接检查通过。
- 本轮未打开真实串口、未改固件、未改写板上已清除的程序、未发布GitHub新版本。0.6.1同步预览本轮验证为生产核心模拟硬件；之前0.6.0屏幕实物固化/清除结果单列如下，不重复声称为新录制层的实屏测试。

主示例：[portable15](../examples/portable/15_screen_record.py)，操作说明：[绘图录制与固化](绘图录制与固化_V0.6.1.md)。命名页面/动态数字使用已有pages模板的在线show/text；不因录制新增离线变量或自动page ID。

## V0.6屏幕真机测试：固化、清除与原页面恢复通过

- 识别同一原生USB COM5，升级前为0.5.0、无控制会话；屏幕ST7735S128×160、rotation1、GPIO4/5/15/7/6/16；原默认页home启用，CRC c70fa309，原舵机映射保留且未激活。
- 在`backups/screen_program_v060_20261114/`保存配置/完整页面模型、真实64KiB前缀及完整1MiB应用区；实际旧应用与已知0.5.0产物一致，原分区表与先前备份一致。没有公开这些私有备份。
- 只写0x10000应用717376字节，esptool哈希验证通过；0.6.0握手、原config完整相等、原页面模型/CRC相等；没有移动舵机或启用音频。
- 运行`tests/standalone/screen_save.py`保存A/B屏幕循环并关闭会话，再通过ROM复位。新boot_id变化；无SDK控制会话，program.saved/enabled/running=true，display.active=true，error为空。
- 只读查询间隔13秒后仍运行，超过6秒会话租约；随后关闭串口，留下A/B画面供用户观察。该结果是板端状态，不是屏幕光学确认，也不是替用户断USB改电源的证明。
- 用户确认A/B正常交替，中文和青色/黄色横条均正常，屏幕固化光学观察通过。
- 之后电脑会话接管停止固化，原config和完整页面模型再次核对相同；运行screen_clear实际清除并ROM复位。新boot_id变化，无会话时program.saved/enabled/running/boot_pending/cleanup_required全部false，error为空；page home独立显示、CRC仍c70fa309，原config完整相同，舵机未激活。
- 当前板已清除测试流程，保留0.6固件；不会再按保存策略启动A/B。用户再次确认“已恢复原页面，不再出现A/B”，原默认页恢复实屏观察通过。本轮屏幕固化、清除、软件复位后保持清除和恢复原页面的测试通过；实际拔USB、改独立电源的断电测试仍未声称完成。
- 两个短测试文件语法检查通过；screen_save模型检查通过，screen_clear已对生产native核心验证会话关闭与清除逻辑，后者不代替实际板测试。

记录：`output/screen_program_v060_hardware.json`；备份/刷写/复位日志在上述私有目录。操作说明见 [屏幕固化、清除与恢复](屏幕固化测试与清除恢复_V0.6.md)。

## V0.6本地验证：固化流程与MicroPython路线说明

| 检查 | 结果与边界 |
|---|---|
| 行为Red | 旧0.5核心device.info不含standalone_program，新增能力断言失败；SDK缺Program接口，模型有效用例在stub上失败 |
| 生产核心回归 | 基础29、屏幕11、页面模型10、页面运行12、音频12组及RGB/屏幕故障检查通过，音频HAL8组通过 |
| 固化模型与执行 | 模型6组、执行11组通过：3072B/64节点/4层条件、严格类型/范围/白名单、RGB/数字/ADC/PWM/舵机/屏幕、非阻塞等待、循环预算及uint32时间回绕 |
| 重启/接管 | 同一C++核心无owner的模拟启动执行；保存不立即运行，session.open停止接管，close/租约不自动恢复，maintenance阻止开机动作 |
| 保留配置 | 独立程序映射临时切换，正常停止恢复原在线屏幕/舵机与休眠音频映射；没有把程序映射写入原live配置 |
| 故障Red与修复 | 新回归先重现：cleanup失败保存临时映射、尾随坏数据仍启动、失败close/expiry泄漏音频快照；修复后11组全通过 |
| 中文请求边界 | 接近3072B中文模型曾因ensure_ascii转义超4096；仅program.save改UTF8编码，实际线长仍校验；真实SDK+C++保存/下载通过 |
| Python回归 | 完整113项，112通过、1项旧学员自由实验预期跳过；新增3项真实核心联调含文件持久化进程重启、无session执行/接管、控制及中文大小边界 |
| 课程/编辑器 | 配置15项、编辑器5项最终完整运行通过；曾有一次旧413超大请求测试发生Windows10053连接中止，同码单独重跑5项及最终全量均通过，未因此改动编辑器 |
| ESP32构建 | Arduino-ESP32 3.3.12、原生USB/RGB48编译通过；应用717376字节，小于已核对原板factory1MiB；没有写设备或参考分区 |
| SDK安装包 | wheel49415字节；9个模块与最终源码一致；本机项目editable和SDK独立环境更新0.6.0 |
| 新环境可移植性 | 新venv安装最终wheel及drawing依赖，从工程目录外以Python -I运行全部113项SDK检查，1项预期跳过；12/13/14示例分别复制到临时目录，用安装包与真实native核心运行、关闭和保存策略验证通过，不依赖_board或源码src导入 |
| 独立审查 | standalone_review只读追踪运行/故障/配置/lease/编码与实际产物；提出问题均有回归修复，最终无未解决P0/P1/P2 |
| 文档与示例 | 固定开发指南、V0.6全API、Program协议、MicroPython比较、README/CHANGELOG及12/13/14示例同步；7份主要文档41段Python语法/本地链接和14个portable脚本语法通过 |
| 实物边界 | 本轮未打开串口、未刷板、未驱动实物；真板断电自启、NVS掉电恢复、外部按钮/电气/机械效果待验收。模拟文件持久化不是NVS实物断电测试 |

最终应用：`build/standalone-native-usb/ai_maker_s3.ino.bin`，SHA256 `44785b9ff225b256a48258ebaac48626519b616e9b09959dc70983b7fd22e95b`。

最终wheel：`sdk/python/dist/ai_maker_robot-0.6.0-py3-none-any.whl`，SHA256 `a9abf9a0a1b64f49d2e6525aeccefe979b707cb09051825ab3b2b92db0f32db5`。

运行命令：`scripts/test.ps1 -Python .venv/Scripts/python.exe -Compiler D:/msys64/ucrt64/bin/g++.exe`；日志`output/standalone_v060_full_tests.log`。目标构建`firmware/build.ps1 -Transport native-usb -BuiltinRgbPin 48 -BuildDirectory build/standalone-native-usb`。

检查点：实现、Red、回归/目标构建及独立审查通过；0.6未提交/推送/发布，没有覆盖0.5附件。实际板需先升级匹配0.6应用才能运行固化示例。用户的MicroPython比较问题已在独立说明中结合官方文档回答。

## V0.5当前验证：IO分类、I²S音频、统一格式与跨电脑SDK

| 检查 | 结果与边界 |
|---|---|
| 初始失败证据 | 旧固件audio_in/out=false、SDK无AudioClip；新增公开接口检查先失败后实现通过 |
| 生产C++核心 | 基础29组、屏幕11组、页面模型10组、页面运行12组、音频12组通过；原RGB/屏幕驱动故障测试通过 |
| I²S真实HAL | 8组严格C++17故障/PCM转换测试通过；还用真实ESP32-S3交叉编译参数编译HAL单元成功 |
| 录放生命周期 | 配置与运行分开；半双工；768字节有界块、偏移/长度/base64校验、局部失败不假装完成、不自动重播；关闭/超时释放；运行时IO不写NVS |
| 引脚能力与回执上限 | 新digital/analog/pwm标识；真DAC=false。发现直接扩展全表8347字节超4096，改为兼容旧全表+新SDK每页12项；最坏旧表仍小于4096 |
| 已纠正的审查问题 | 失败的I²S释放不能被stop错误清除故障；跨源重定向中Proxy-Authorization按实际大小写规范清除；补齐GPIO即时set在start后调用的说明 |
| PythonSDK | 完整100项运行：99通过，1项旧学员自由修改课程按开关跳过；含实际C++核心收音/回放、PCM精确字节和pin分页 |
| HTTP本地/云端格式 | 本地HTTP实际服务6项通过；PCM/WAV/显式URL都得到同一16kHz/mono/PCM16LE AudioClip；只接音频入口，无AI服务调用 |
| 原课程与网页编辑器 | 配置/课程15项、编辑器HTTP5项通过；旧gpio/adc/pwm、页面、RGB、舵机、屏幕及旧Turtle辅助保留 |
| 可移植性 | 全新venv安装wheel并从工程目录外以Python -I导入site-packages；AudioClip/WAV往返、包内Turtle、100项SDK验证通过；再将01_info.py单独复制到临时目录，以安装包查询真实COM5成功，无_board/E盘源码定位依赖 |
| 依赖与安装 | 包本体纯Python；核心只需pyserial。图片/Turtle可选Pillow，窗口需Tcl/Tk；未声称一套Pillow二进制能适配所有电脑 |
| ESP32最终构建 | 原生USB/RGB48；Arduino-ESP32 3.3.12固定；应用688832字节，小于实际factory1MiB，未写参考分区/merged |
| 升级备份 | 先verify-flash确认真实旧V0.4应用匹配已知产物，再保存该应用副本；ROM读取当前64KiB前缀含NVS，原分区表逐字节相同；未声称全16MiB备份 |
| 实板写入 | 核对 COM5 设备身份，确认无控制会话后，仅写0x10000应用；esptool哈希验证通过 |
| 实板配置回归 | 身份0.5.0、45项新SDK分页、audio运行时映射/冲突/保留脚拒绝/清理通过；旧screen/servo配置完全一致，退出后默认页恢复、舵机未激活 |
| 实物音频边界 | 用户确认模块INMP441/MAX98357A，但IO将自行调整；本轮实板未audio.begin、未录放、未操作舵机，不声称真实收音或听感通过 |
| 文档与入口 | V0.5完整函数手册覆盖当前公开方法；5份入口文档的11段Python代码语法、全部本地链接、8个portable文件语法检查通过；菜单启动并输入0退出通过 |
| 审查 | 独立只读审查者audio_review确认运行实现无未解决P1/P2；其提出的释放故障、重定向鉴权头、配置顺序问题均已修正并回归。最终文档补充由主代理核对签名、示例与链接；实际音频接线验收单列待测 |

应用：`build/audio-native-usb/ai_maker_s3.ino.bin`，688832字节，SHA256：`f35a1233ca191dbe6260a41c025b61b947594b21e69c997a4ff4386a62c52a9a`。

SDK：`sdk/python/dist/ai_maker_robot-0.5.0-py3-none-any.whl`，42160字节，SHA256：`1b46d87ef9c4fc39e4677c22ac5296ace1e2f00a3f6419d217367c7befc4bc7e`。8个Python模块与最终源码逐字节一致；两个项目环境已更新0.5.0。最终wheel重建只补明即时GPIO与映射set顺序，运行代码未变。

备份/刷写记录：`backups/audio_v050_backup_manifest.json`、`pre_audio_verify_v040.log`、`pre_audio_read_prefix.log`、`audio_v050_flash.log`。配置证据：`output/audio_pre_upgrade_state.json`、`output/audio_v050_hardware_config_proof.json`。备份和output均已忽略，不应作为公开源码分发。

当前入口：[IO与音频测试](数字模拟IO与音频测试_V0.5.md)、[跨电脑安装](跨电脑安装与直接导入_V0.5.md)、`examples/portable/`、根目录运行音频测试.cmd。原生USB流为本轮支持路径；UART构建音频能力关闭，已有板级接口保留。

本轮检查点：实现的隔离、初始失败、回归证明及独立运行代码审查已完成；最后文档检查通过。没有提交、发布或AI服务器交付步骤。后续由用户按实际IO完成麦克风、功放及回放的实物测试；不把该项未接线验收写为通过。

## 2026-11-11：Turtle开头配置、复用已有Robot

新增项目教学辅助 `finish(screen, robot=robot)`，不修改SDK运行代码或固件。开头全部set、start，后面绘图并将已有Robot交给finish；不得同时传第二组port/IO。发送前捕获画布，首次发送幂等start，重复发送复用该Robot。关闭窗口接管并关闭整条连接及其所有外设输出，即使没有发送；失败后关闭、禁用按钮并要求修正重跑，不会另开连接。

测试先因不支持robot参数失败，新增5项通过：同一Robot两次发送、关窗前从未发送也清理、失败只关闭一次且不重连、拒绝混合配置、finish传递对象身份并退出清理。完整配置套件15项通过；SDK78项OK（1项可编辑旧课程跳过）。真实Windows Turtle画布与生产native C++核心传图两次、同一Robot、关闭通过，记录 `output/turtle/top_setup_native_gui_proof.json`。

首次COM5复测因其他进程占用而被拒绝，未关闭用户进程。用户明确回复“已关闭，可以复测”后，真实COM5路径通过：执行当前quick/turtle_demo.py，用原发送回调传图两次，Robot构造一次，协议session.open=1、session.close=1，发送期间display.active=true，最后连接关闭；无舵机动作。证据 `output/turtle/top_setup_reuse_hardware_proof.json`。仅程序回执，不替代实屏图像的光学确认。

当前默认quick/turtle_demo已改为开头配置，作者字段及绘图AST保持相同；原延迟连接版存于 `backups/turtle_demo_before_top_setup_0b8efcdd0901.py`。新增最小示例 `tests/guide/14_turtle_top_setup.py`。旧延迟连接模式继续支持。SDKwheel0.4.1保持原运行代码及文件，本次变化位于项目教学辅助和文档，两个环境无需重装SDK。

## 2026-11-11：Turtle屏幕发送冲突修复

用户的quick/turtle_demo.py在绘图前创建Robot(COM5)并display.set，结尾又finish(screen)。前者持有串口和心跳、配置后保持维护；后者发送按钮会再次尝试建立独立连接。离线执行原文件确认finish之前已存在Robot，违反单连接路径；只移动连接配置后，同一检查通过。

修正仅删除前置Robot/屏幕配置，将同一COM5和实际IO传给finish；作者信息、三色值及全部绘图语句逐字比较一致。原文件存于 `backups/turtle_demo_before_connection_fix_0589ea9ab158.py`。没有修改SDK或固件，没有驱动舵机。

实际COM5验证：`tests/guide/08_screen.py`完成，退出码0；修正后的真实标准库Turtle文件执行，并通过原Sender发送回调连续传图两次，构造Robot计数=1，display.active=true，关闭窗口后Robot.closed=true。记录 `output/turtle/connection_fix_proof.json`。这证明连接/初始化/传图闭环，不替代用户对本次Turtle屏幕图像的光学确认。

## 2026-11-11：SDK0.4.1 set别名、多设备与整屏图片限帧

新增display.set、servo.set、robot.start，旧API保留；屏幕丝印别名大小写不敏感，供电脚、重复信号、未知拼写拒绝后不发送配置。位置顺序固定SCK/MOSI/CS/DC/RST/BLK，与排针位置无关。set保存配置并保持维护，全部set之后start初始化本连接请求的屏幕，不移动舵机。

fps=1～60/None仅用于电脑端display.image帧开始上限，不写NVS、不改面板扫描率、不限制text/line/rect/bitmap。新增transfer_seconds是分块传输耗时，未声称已测真实面板FPS。

验证：完整SDK78项OK（1项旧可编辑课程跳过）；新增6项覆盖别名与位置顺序、无IO失败提示、确定性限帧、同一生产C++核心屏幕+2舵机共存且start不移动/重复start不停止PWM。配置/课程10项通过（含新12多外设、13图片测速脚本运行真实native核心）；编辑器HTTP5项通过。实际串口本轮未打开，未驱动真实舵机、未测实屏FPS。

新wheel `sdk/python/dist/ai_maker_robot-0.4.1-py3-none-any.whl`（28948字节），SHA256：`99a870a768ad8207e5798b2d4efbc3f9db80c595da5589d2e5c7508fa2e95eef`。6个Python模块与源码逐字节一致；项目editable环境与SDK独立环境已升级0.4.1。板端应用仍为原V0.4.0，未烧录。

## 2026-11-11：改为推荐代码内COM与IO配置

用户进一步明确课堂应在当前Python文件中写连接和IO调用。主示例 `tests/guide/` 已改为 `connect("COM5")` 及命名IO参数；原集中配置示例保留在 `tests/guide_shared/`，不删除配置窗口。

`classroom`兼容入口改为懒加载：显式串口和屏幕参数不读取可选JSON；原无参数入口保留原行为。Turtle的 `finish(screen, port=..., sck=..., ...)` 仅在点击发送后应用参数。未改变SDK安装包和板端固件。

验证：配置套件10项通过，覆盖不读JSON的显式COM/屏幕参数、公共模块导入、Turtle参数转交和生命周期、10个主示例与10个保留集中配置示例连接同一生产C++核心；72项SDK回归OK（1项旧可编辑课程跳过）。本轮没有连接真实串口或驱动外设。

## 2026-11-11：统一配置与全API手册

本次不修改ESP32固件或SDK安装包。新增 `config/hardware.json`、本地Tk配置窗口和11个新课程示例；串口、基础GPIO、舵机、屏幕预设集中管理。现有用户01～08、screen_text、turtle_demo文件SHA在修改前后相同，旧settings/_screen_settings原文保存在config/legacy，原有效屏幕参数与统一配置相同。

验证：配置读写/备份/无效数据拒绝/兼容入口以及10个非GUI示例在生产C++核心的集成，共5项通过；使用替代GPIO13/18/2/17/舵机21，确认没有写死原预设。SDK72项OK（1项旧可编辑课程按开关跳过）；编辑器HTTP5项通过，新增统一设置预填接口不连接USB。

真实Tk窗口在临时配置上修改COM123/LED13、保存及读回一致，屏幕重复引脚保存被拒绝，serial.Serial打开次数为0。已查看串口、屏幕页截图，字段和操作区完整可见。实际Chrome有界面运行验证统一串口AUTO、屏幕型号及4/5/15/7/6/16预填、反相false、背光60，0控制台错误；本轮未点击连接硬件。

全API说明按当前源码核对，22段Python示例通过语法检查、本地链接存在，公开方法名称无遗漏。独立只读审查发现并纠正了异常捕获示例（原始Robot异常与课堂SystemExit区别）和旧配置入口说明，最终Review Gate PASS。

证据位于 `output/configuration/`（Tk截图、浏览器截图与快照）；该目录已忽略。配置新示例的外部实际电气效果沿用此前已验收能力，本轮没有驱动真实GPIO/舵机，未将native验证当成新接线验收。

## V0.4 当前验证：页面、默认页与标准库Turtle

| 检查 | 结果与边界 |
|---|---|
| 初始失败证据 | 原V0.3生产核心不支持pages；SDK缺失接口测试先失败；模型占位解析器拒绝合法项目，完成后通过 |
| 生产核心主机验证 | 基础29组、屏幕11组、页面模型10组、页面运行时12组通过；真实显示与RGB适配桩故障测试通过 |
| Python完整测试 | 72项运行，71通过、1项可编辑旧课程整组测试按开关跳过；图片、页面、实际C++核心跨进程通信均覆盖 |
| 独立wheel验证 | 0.4 wheel全部Python模块与源码字节一致；装入SDK独立环境，从site-packages导入，72项结果相同；Pillow13/pyserial3.5 |
| 编辑器HTTP | 4项实际HTTP测试通过，检查显式连接、上传、关闭、令牌及来源；Fake硬件不作为真机证据 |
| 浏览器界面 | 实际Chrome验证属性编辑、拖拽、16×16图片导入、JSON导入导出、非法JSON提示；0控制台错误；截图在output/playwright |
| Windows Turtle画布 | 真实标准库Turtle内部Canvas HWND截图418×318；已断言已知填色像素并检查只含画布；独立审查再次用纯绿背景得到96.16%精确绿像素 |
| 窗口生命周期 | 捕获先于USB连接，显式点击后连接一次、多次发送复用会话，关闭窗口才释放；失败不自动重试 |
| ESP32目标构建 | native-usb/RGB48、Arduino-ESP32 3.3.12；应用661056字节，小于实际factory1MiB |
| 升级保护 | ROM路径读取升级前V0.3应用620736字节和64KiB前缀；应用SHA与已知V0.3一致，原分区表逐字节一致，备份清单已保存 |
| 实板刷写 | 核对 COM5 设备身份；只写0x10000应用，esptool哈希校验通过；未写参考merged或分区表 |
| 配置迁移 | 屏幕ST7735S、160×128横屏、自定义SPI/BLK和SG90 GPIO14映射保留；全程无servo.move |
| 真实NVS页面 | 含48×48图像的页面JSON超过4KiB，上传、保存、下载内容完全一致，证明实际blob路径可用；随后保存1577字节示例页 |
| 真实网页到开发板 | 本地HTTP服务→实际SDK→COM5完成连接、上传、显示、启用默认页、断开；不是FakeRobot |
| 整屏图像 | Windows实际Turtle截图经64块发送160×128；随后实际执行turtle_demo.py和发送回调，显示active、窗口关闭清理通过；不能替代屏幕逐像素光学验证 |
| 关闭与复位 | 关闭会话、ROM硬复位后在未打开控制会话条件下查询，默认页active、显示驱动ok、无storage_fault、舵机active=false，boot_id已变 |
| 用户图像确认 | 用户2026-11-11确认默认页“文字、图标和颜色均正常”；Turtle自由作品尚待用户自行运行观察 |
| 独立审查 | review_pages只读审查页面保存/恢复、位图边界与RGB565顺序、捕获及会话生命周期，无阻塞问题；review gate通过 |

当前应用：`build/native-usb/ai_maker_s3.ino.bin`（661056字节）。SHA256：`1e778344d76ad650dda2528aaab9ecda1f4c788fd1acd7dc0ec1dfce59665f04`。

SDK：`sdk/python/dist/ai_maker_robot-0.4.0-py3-none-any.whl`。SHA256：`d00e8b8cfd7223df0829659aedb675870c2f2433d7b2034ed4f57825322d004d`。

本地证据：`output/pages_hardware_proof.json`、`output/pages_reboot_status.json`、`output/turtle/demo_hardware_proof.json`、`output/turtle/demo_capture.png`；备份清单 `backups/pages_v040_backup_manifest.json`、刷写日志 `backups/pages_v040_flash.log`。这些均不应作为产品源码发布，备份可能包含旧NVS私有数据。

实现范围：本地受限页面编辑、图标与默认页、标准Turtle临时传图；尚未实现任意HTML作品宿主、视频/实时动画、音频、AI服务。默认页仅恢复屏幕，不恢复舵机动作。

## V0.3 历史验证：屏幕与自定义引脚

| 检查 | 结果与边界 |
|---|---|
| 初始失败证据 | 旧生产核心返回display=false；新增SDK屏幕接口测试先因缺少接口失败，实现后通过 |
| 生产C++核心 | 原29组通过，新增10组屏幕合同通过；包含三种尺寸、四向旋转、持久化、UTF8、资源和故障状态 |
| 真实屏幕适配驱动 | board_display.cpp配HAL桩的故障测试通过；初始化/绘图8MHz、运行时SPI映射、BLK、部分失败及完整清理；不是实际波形/光学验收 |
| Python SDK与跨进程 | 52项中51通过，1项可编辑课程整组测试按显式开关跳过；三个真实短屏幕脚本均连接同一生产C++核心执行 |
| 安装包 | wheel源码逐一核对一致，安装到SDK独立环境并确认从site-packages导入，重复52项结果一致；项目内环境已更新0.3.0 |
| ESP32目标构建 | native-usb/RGB48、Arduino-ESP323.3.12、ArduinoJson7.4.3；AdafruitGFX1.12.6、ST7735/ST7789库1.11.0、BusIO1.17.4、U8g2适配1.8.0 |
| 应用文件 | 620736字节，小于当前原factory1MiB；不是将参考合并分区写入当前板 |
| 刷写前备份 | 扩展至原始和升级前factory完整1MiB，并备份当前64KiB前缀（含NVS）；前384KiB+此前未改写的640KiB尾部重建，升级前应用SHA与已知0.2.1一致 |
| 串口备份读取异常 | 大块stub读取多次中断，不作为成功备份；随后完整384KiB由ROM路径读取成功，213.65秒，才完成备份拼接和哈希核对 |
| 当前板写入 | 已确认同一COM5，原分区一致；仅写0x10000应用，esptool哈希校验通过 |
| 真机配置测试 | ST7789240×320无BLK、带BLK与ST7735S带BLK三种配置保存/完整读回通过；实际自定义信号18/21/9/10/11、BLK16或-1，保留舵机映射 |
| 真机保护与恢复 | 屏幕配置拒绝USB保留脚19；owner与3/4路普通PWM配额吻合；恢复原配置和维护状态，没有发送display.begin或servo.move |
| USB长帧回归 | 新固件160～4096字节8组单次发送查询全部通过，保留V0.2.1修复 |
| Windows入口 | 开始测试.cmd包含11项，菜单进入/退出实测通过；运行屏幕测试.cmd已提供 |
| 独立审查 | review_screen软件范围Looks good；核对SPI引脚、析构、失败清理、PWM配额和旧配置兼容 |
| 用户屏幕图像确认 | 2026-11-09用户反馈“纯色、满屏范围和中文都正常”，本次所测屏幕的这三项通过；未在回复中明确型号，不推广为所有型号均实测通过 |

V0.3历史应用（已由V0.4替换）：升级前备份 `backups/pre_pages_v030_application.bin`。

SHA256：`4d7f132de196cc2f286e12de222c8a1d3692de57a707d19b51ca19deaee82524`。

SDK包：`sdk/python/dist/ai_maker_robot-0.3.0-py3-none-any.whl`。

SHA256：`1cddc35852ddd117315e4eda0ec9452b71de44f1e5a326d772bf2deaedeeb047`。

本地忽略的实机记录：`tests/hardware/reports/flash_v030_native_usb_COM5.log`、`COM5_screen_v030_config.json`、`usb_rx_v030_regression.json`。私有备份清单：`backups/display_v030_backup_manifest.json`，不是整片16MiB备份，不公开分发。

自动验证阶段只保存映射，没有初始化SPI屏幕。随后用户确认本次测试的纯色、满屏范围和中文正常，已获得独立人工图像反馈；驱动自身仍无光学传感器，回执继续physical_verified=false。反馈时配置文件为st7735s_128x160、SCK4/MOSI5/CS15/DC7/RST6/BLK16、ROTATION1，此为当前文件状态，用户回复未逐项确认各型号和背光调光，因此其余组合仍需分别记录。使用步骤见 [屏幕测试说明](屏幕测试与自定义引脚_V0.3.md)。

修改范围限于任务创建的ai_maker；保留用户01～08及屏幕接线配置等编辑，原AI/云端工程未改动。Implementation与独立Change Review已完成，并已有本次屏幕图像人工确认；其他屏幕组合与背光继续逐项验收，没有提交、推送或发布。

## V0.2.1 历史验证：舵机配置超时修复

根因是原生 HWCDC 接收缓冲默认256字节，而V0.2.0的8192字节设置被条件编译限制为UART。真实配置请求293字节，可能因队列满而丢字节；该报错发生在servo.move之前。修复后两个通路都在Serial.begin前设置8192字节接收缓冲，未修改舵机PWM驱动，也未加入动作重发。

- 同一COM5板在旧版的长帧单次发送失败、64字节分段成功；更新后160～4096字节的8组只读请求全部通过。
- GPIO14完整配置保存约50.92ms完成，内容读回与写入完全一致；结束后恢复原空配置和维护状态，没有发送servo.move。
- 原生USB / RGB48构建通过，应用360720字节；仅写入原应用区0x10000、哈希校验通过，分区与备份核对正确。
- V0.2.1应用SHA256：`d86c32c3ecc8289c0fba9e412b64cbc794c4d476e67afd2111b57dc54de79d1e`。
- 29组核心测试及RGB驱动故障检查通过；44项Python/联调中43通过，1项可编辑课程文件整组检查改为显式选择。
- 独立审查review_usb_rx_fix：Looks good，无未解决阻塞项。
- 用户随后运行SG90/GPIO14动作测试，明确反馈“能看到来回转动”，该组合的实际往返运动验证通过；精确角度、供电余量、带载能力及PWM波形未测量。

新增 `tests/quick/servo_sg90.py`，用户原07等脚本未覆盖。原02的颜色元组不是SDK支持的颜色名称；默认SDK回归不再自动运行可编辑的01～08，显式 `scripts/test.ps1 -IncludeExamples` 可检查当前学员版本。新SG90示例和只读长帧工具独立回归仍默认执行。

详情和复现命令见 [舵机配置超时排查](舵机配置超时排查_V0.2.1.md)。SDK源码及wheel未变，版本仍0.2.0；修复在板端，无需用户重新安装SDK。

实施、独立审查和用户SG90往返运动确认均已完成，本次配置超时问题已解决，无必需后续技能交接。没有提交、推送或发布。

## V0.2.0 历史验证

| 检查 | 结果 |
|---|---|
| 启动熄灯与关闭失败信号 | 新增测试先复现启动未清灯、停止失败却成功回执；修复后通过 |
| 生产 C++ 核心 | 29 组通过，包含 RGB 启动清理、停止失败仍释放 GPIO、租约到期与恢复 |
| 生产 RGB 适配驱动 | 真实 board_rgb.cpp 配合故障注入 HAL 通过；GRB 顺序、LOW 复位、熄灯、初始化/清理/发送超时；不等于实测波形 |
| Python 与联调 | 42 项通过，含全部 8 个短文件连接同一生产 C++ 核心；旧硬件 02 实际脚本正常及真实 6.4 秒租约等待通过 |
| Python 退出异常 | 正常退出传播明确硬件错误并关闭串口；正文原异常不被覆盖；已到期会话关闭不误报；对应先失败后通过 |
| 主固件原生 USB | Arduino-ESP32 3.3.12、ArduinoJson 7.4.3、RGB48 构建通过；应用文件 360704 字节 |
| 兼容构建 | V0.2 的 UART / RGB38 目标编译通过；未刷入当前 RGB48 板，不作为 GPIO38 实物验证 |
| 当前板刷写 | 识别同一 COM5 板；原始备份大小/SHA256 正确；实时分区与原备份一致；仅写 0x10000 应用，esptool 哈希校验通过 |
| 简易脚本真机 | 未指定端口，01_device_info.py、02_rgb.py 均退出 0；固件家族/版本/引脚符合，结束后 RGB=0,0,0，driver_ok=true |
| 真机超时释放 | 旧硬件02颜色/状态匹配，6.4秒后会话释放、RGB归零，软件结果 passed |
| Windows 入口 | 开始测试.cmd 实际运行菜单、输入0、退出码0；环境安装在项目内 .venv 成功 |
| 独立审查 | review_board_v02：Looks good；两项 P2（关闭错误被吞掉、旧硬件脚本状态兼容）已修复并回归，无未解决阻塞项 |

V0.2.0 主应用 SHA256：`170eb20d9c1aeb22b6452cf03bc4f4a8dff14f03a5ca146dceaeb1b1c7fed5d2`。

当前 SDK wheel：`sdk/python/dist/ai_maker_robot-0.2.0-py3-none-any.whl`，SHA256：`362c63b11a57f1a2236c981ea46d39be9d5872b1313b448fa1db011a6f32a45f`；zip 内 Python 源码逐一核对与最终 SDK 源码一致。

该 wheel 已安装到 SDK 独立虚拟环境，核对导入路径来自 site-packages 后，相同 42 项测试再次通过。面向用户的 README 和上手说明本地 Markdown 链接检查全部存在。

本轮真机记录（本地忽略文件）：

- `tests/hardware/reports/flash_v02_native_usb_COM5.log`
- `tests/hardware/reports/COM5_v02_partitions.bin`
- `tests/hardware/reports/COM5_v02_quick_test.json`
- `tests/hardware/reports/COM5_v02_rgb_lease.json`

主固件启动时熄灯，已替换此前默认白灯的独立诊断固件。先前“GPIO48白灯已亮”是用户确认的历史光学证据；本轮主固件有真实 RMT 成功回执与状态检查，未追加用户光学确认，不将其写成三色光学验收。外部设备仍等待用户接线后逐项验收。

实施范围隔离：仍使用原工作区，所有改动限于本任务创建的 ai_maker，原 AI、云端和其他用户变更未编辑。Implementation → Change Review 完成，下一步无必需技能交接；没有提交、推送或发布。后续外设接线验收见 next_steps.md。

## V0.1 历史验证与排查

## 软件验证

| 检查 | 结果与证据 |
|---|---|
| 初始失败信号 | 空协议核心返回 UNSUPPORTED_OPERATION，device.info 测试按预期失败；实现后通过 |
| 生产C++核心 | 27组行为测试通过，使用 -Wall -Wextra -Werror；模拟适配器，不代表物理外设 |
| Python SDK与联调 | 23项SDK协议测试、4项真实C++核心跨进程测试通过，共27项 |
| SDK安装包 | wheel构建并安装至独立环境，相同27项测试通过 |
| ESP32 UART目标 | Arduino-ESP32 3.3.12、ArduinoJson 7.4.3，16M Flash、OPI PSRAM目标编译通过 |
| ESP32原生USB目标 | 同工具链编译通过；未在当前硬件通路执行原生USB真机测试 |
| GPIO38/48配置 | 增加单一编译参数控制实际RGB、能力声明及资源保留；按目标参数分别回归 |
| 独立审查 | 已修正GPIO预置、ADC切换和字符串NUL边界；软件范围无剩余阻塞项 |

自动命令从 ai_maker 目录运行：

```powershell
.\scripts\test.ps1 -BuiltinRgbPin 48
.\scripts\test.ps1 -BuiltinRgbPin 38
.\firmware\build.ps1 -Transport uart -BuiltinRgbPin 38
```

核心测试覆盖会话争用、心跳续租、6秒租约与计时回绕、GPIO模式、ADC能力、PWM配额、舵机限位与脉宽、维护模式重启、坏配置与保存失败事务、重映射、严格类型、NUL/超长字符串、行边界及RGB释放。跨进程测试运行同一份生产C++核心，不只验证Python mock。

## 实物识别与备份

- 串口：COM3，FTDI USB转串口通路。
- 芯片：ESP32-S3 revision v0.2，检测到16 MB Quad Flash、8 MB内置PSRAM。
- 本次只读取安全状态：安全启动与Flash加密均未启用，未写eFuse。
- 现有分区：NVS起始0x9000、长度0x6000；phy_init位于0xF000；factory应用起始0x10000、长度1 MiB。
- 原始Flash完整高速读取出现数据错误，因此没有宣称取得完整16 MB备份。
- 最终备份为起始64 KiB（含原启动、分区与配置）和factory应用前384 KiB（覆盖本次写入及擦除范围），文件大小与SHA256已校验。
- 备份保存在本机 `backups/`，清单为 `backup-manifest.json`，可能含设备私有配置，已加入忽略规则。

写入应用前检查镜像不超过已备份区域及原factory分区。测试采用只写0x10000应用的方式，保留原bootloader、分区和其余资源；实际写入日志位于本地备份目录。普通完整安装包仍以构建清单中的参考分区为准，不能把这次专门操作直接推广到其他设备。

## 真机RGB记录

### GPIO48首轮

SDK已成功连接教学固件0.1.0，六次红绿蓝指令与状态一致；请求往返约33～35 ms，仅为少量本地烟雾测试数据，不是完整性能分位统计。专门关闭心跳后，约6秒租约到期，会话失效、RGB指令清零。

用户观察反馈为“无变化，疑似引脚不对”。因此此轮只记为软件通信通过，**本块板GPIO48光学测试不通过**。原始报告 `build/hardware-rgb.json` 已写入光学反馈为false，不把软件成功等同于灯亮。

### GPIO38后续

已核对原项目的状态灯实现：录音红色(28,0,0)、思考黄色(18,10,0)、播放绿色(0,22,0)，均调用rgbLedWrite(RGB_BUILTIN,...)。这个别名依赖开发板定义，不能从源码别名直接判定实物引脚。

官方资料说明DevKitC-1早期版与v1.1的RGB引脚为GPIO48和GPIO38；因此本轮加入明确的38/48构建选择，不能遍历任意GPIO猜灯。两种配置均运行了27项核心与27项SDK/跨进程测试，全部通过。

GPIO38教学固件编译、写入和哈希校验通过，状态查询显示`s3-n16r8-rgb38-v1`。参考颜色测试在第二轮红色后出现心跳通信失败，共完成4条颜色命令，没有完成整轮及该轮超时测试。报告位于`tests/hardware/reports/rgb38_states.json`，软件结果为failed；不记录为GPIO38灯光通过。断线原因尚未证明，后续教学固件真机稳定性测试需继续追踪。

### 持续高电平诊断

根据用户后续要求，另建`firmware/led_diagnostic/`，保留教学固件不混用。诊断应用308240字节，写入原factory的0x10000后哈希校验通过，没有改写分区表。

本次实际运行：

```powershell
python .\tests\hardware\03_led_diagnostic.py --port COM3 --run --mode high --pin 38 --seconds 6
```

连续6秒返回`firmware_family=ai-maker-led-diagnostic`、`mode=gpio_high`、`pin=38`、`commanded_level=1`、`read_level=1`、`driver_ok=true`。这证明GPIO38当前逻辑高电平，不证明RGB灯光已点亮。诊断状态记录位于`tests/hardware/reports/gpio_high38.log`。

当时板上保留独立诊断固件，GPIO38持续高电平，没有教学SDK心跳或6秒租约；用户随后确认灯仍未亮。GPIO38读回高电平不能证明该引脚连接着RGB，也不能代替单线像素的颜色数据帧。

另提供固定白色RGB模式供明确选择，发送WS2812数据帧而非直流高电平。本次未把该模式声明为已经光学通过，也未自动遍历其他GPIO。

### COM5原生USB续测

用户更换连接后，外置FTDI的COM3消失，原生USB的COM5出现。串口设备序列号和esptool读取的芯片MAC一致，确认是同一颗ESP32-S3；COM5显示USB-Serial/JTAG。通过COM5读回的分区表与原始备份一致。

已复现的通信问题：旧诊断构建`CDCOnBoot=default`，应用输出走UART；在COM5运行03不能收到诊断家族，报`No LED diagnostic firmware detected`。新增`build_diagnostic.ps1 -Transport native-usb`，设置`CDCOnBoot=cdc`，与UART产物分目录；编译后仅写入原factory应用区，哈希校验通过。该变化修复应用串口路径不匹配，不将它直接认定为所有灯光异常的唯一原因。

诊断发送增加真实RMT初始化、写入返回值和清理错误报告；明确保证颜色帧前后LOW复位间隔。像素位时序与本机Arduino驱动保持一致。失败时静态缓冲保留生命周期并终止RMT，故障后拒绝复用，避免超时后仍发送的数据引用失效。该故障分支经源码审查，未在真实硬件上强行制造RMT故障。

实际运行：

```powershell
python .\tests\hardware\03_led_diagnostic.py --port COM5 --run --mode rgb --pin 48 --seconds 60
```

60秒监测结束成功，`mode=rgb_solid`、`pin=48`、`driver_ok=true`、`driver_error=none`、`cleanup_ok=true`。脚本结束后再次只读检查，仍为GPIO48固定白色指令状态，没有复位回常高模式。日志为`tests/hardware/reports/COM5_rgb_solid48.log`。随后用户明确反馈“亮白色了”，本板GPIO48固定白色光学验证通过。固件仍报告`physical_verified=false`，因为它没有光学传感器；人工观察单独记录。

### 最终上电常亮版本

确认实际接线后，诊断固件默认改为原生USB、GPIO48，上电自动发送固定白色，不依赖电脑点灯命令。03测试脚本默认`--mode rgb --pin 48`，HIGH和OFF仍可显式选择。

最终应用304672字节，写入COM5原factory应用区并通过哈希校验。随后仅打开COM5读取、不向应用发送任何命令，连续收到5条启动状态：`mode=rgb_solid`、`pin=48`、`driver_ok=true`、`driver_error=none`。这验证了自动启动路径。记录为`tests/hardware/reports/COM5_boot_white48.json`。

本次确认有效的组合为COM5原生USB、GPIO48、RGB颜色数据帧。已证明换口后的UART构建与原生USB输出路径不匹配；GPIO38常高也不是本板RGB的正常控制方式。最初COM3不亮是否还涉及供电或旧驱动起始状态，没有单独测量，不将它归为已证明的唯一原因。

## 自行重复测试

入口、安装命令、测试现象、原项目状态颜色和故障排查见 [真机测试说明](../tests/hardware/README.md)。

```powershell
python .\tests\hardware\01_device_status.py --port COM3 --run
python .\tests\hardware\02_builtin_rgb.py --port COM3 --run --pattern states --lease-test
```

测试脚本不会烧录固件；不带--run不连接设备。默认报告保存在tests/hardware/reports，可用--report单独保留。

## 尚未验证

真实GPIO电平、ADC精度及ADC/数字模式切换、PWM波形、舵机校准和机械行为、NVS真实断电恢复尚未完成。屏幕、音频、SD和学生网页上传尚未实现；对应能力为false。没有把板载RGB测试扩展声称为全部技术需求已经完成。
