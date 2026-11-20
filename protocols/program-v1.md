# Standalone program protocol v1

0.7增加`display.counter`终端控件，schema_version仍为1，原0.6模型兼容。新控件另需`standalone_counter=true`；不具备此能力的固件不能执行。它是定时累加显示，不是通用变量/命名页面调度。

SDK0.6.1增加begin/end同步预览录制，这是纯电脑端构建流程，**没有program.begin/end/cancel板端RPC**。录制最终仍生成本协议的schema1 Program并用原program.save保存；固件版本仍0.6.0。命名pages控件和动态变量不因录制而自动加入本协议。

固件/SDK0.6.0本地开发能力；USB协议仍为v1，设备能力`standalone_program=true`才支持本协议。不是任意Python、JavaScript或源代码执行接口。当前GitHub0.5.0附件不具备本能力。

## 1. 程序模型

```json
{
  "schema_version": 1,
  "config": {"schema_version": 1, "servos": []},
  "steps": [
    {"op": "led.set", "args": {"red": 8, "green": 0, "blue": 0}},
    {"op": "wait", "args": {"ms": 1000}},
    {"op": "led.off", "args": {}}
  ]
}
```

根字段精确为schema_version/config/steps。紧凑UTF8 JSON最多3072字节，源步骤节点最多64（含条件和所有分支），条件嵌套最多4层；编译后内部指令最多128。steps和then非空，else可省略或为空。未知字段/操作、非整数数值、bool冒充整数、非法UTF8、越界坐标、保留/冲突IO都拒绝。原始JSON外尾随数据或嵌入NUL拒绝。

config沿用`config.apply`模型：schema_version1、servos数组及可选display。程序使用自己的快照，屏幕/舵机映射仅在程序上下文临时生效，不覆盖在线保存配置；没有音频字段。程序GPIO不能抢占其屏幕/舵机脚，板级保留脚策略仍生效。路径相关“先setup再读写”由执行时检查，不假装任意分支都可安全执行。

## 2. 白名单步骤

每个普通步骤精确为`op`与对象`args`。颜色是RGB565整数，板载RGB为每通道0～32；所有范围和主在线接口保持对应关系。

| op | args |
|---|---|
| led.set / led.off | red/green/blue整数0～32 / 空对象 |
| gpio.setup | pin、mode=input/input_pullup/input_pulldown/output/pwm |
| gpio.write / gpio.release | pin、value整数0/1 / pin |
| pwm.write | pin、duty整数0～100 |
| servo.move / servo.release | device、angle / device；必须在程序config存在且角度满足校准限制 |
| display.begin / display.release | 空对象；需要程序display配置 |
| display.fill | color整数0～65535 |
| display.text | text有效UTF8 1～192字节、x、y、color；只允许换行控制符 |
| display.rect | x、y、width、height、color、filled布尔；完整在屏内 |
| display.line | x0、y0、x1、y1、color；两端有效 |
| display.brightness | percent整数0～100；需要GPIO背光 |
| display.counter（0.7） | name、start、step、interval_ms、x、y、width、height、color、background；根steps最后唯一一个，禁止分支，持续运行 |
| wait | ms整数1～60000；调度等待，不阻塞整个USB处理循环 |

不接受录放音频、图片像素、Turtle、网页代码、云端请求或任意源代码。没有由外部模型指定的跳转地址；内部jump只由验证后的条件编译器生成。

条件节点额外有then及可选else：

```json
{
  "op": "if.digital",
  "args": {"pin": 2, "value": 0},
  "then": [{"op": "gpio.write", "args": {"pin": 12, "value": 1}}],
  "else": [{"op": "gpio.write", "args": {"pin": 12, "value": 0}}]
}
```

`if.analog`的args为pin/operator/value，pin须可用ADC候选，value为0～4095，operator只允许`< <= == != >= >`。条件在运行时采样，输入模式必须已建立；不是上传时读取的旧值。

counter参数精确为上表10字段：name为合法ASCII名称≤24字节；start非负int64≤9223372036854775807；step整数1～2147483647；interval_ms整数50～60000；数字区域width≥133、height≥16且在旋转后屏内；color/background为RGB565整数。bool/浮点/字符串数值、未知字段拒绝。计数器程序的loop必须为false，SDK在IO前拒绝，固件save/load也校验，避免旧策略导致循环重新初始化。

## 3. RPC

所有请求沿用USB JSONL封装、请求ID和错误回执，动作不自动重发。`program.info`是查询；其它操作按会话和维护/运行状态校验。

| op | args与行为 |
|---|---|
| program.info | {}；saved/enabled/loop/running/boot_pending/instruction/error/cleanup_required/physical_verified |
| program.download | {}；返回program模型、enabled、loop；没有保存内容时明确错误，不造空程序 |
| program.save | program对象、loop布尔、autostart布尔；维护中校验并保存，不立即运行 |
| program.enable / program.disable | {}；维护中持久启用/禁用下次开机执行，不修改步骤和循环策略 |
| program.clear | {}；维护中清除保存流程和自启策略 |
| program.start | {}；非维护中显式启动当前会话的保存流程，先清理输出 |
| program.stop | {}；停止并释放运行输出，保留程序和开机策略 |

SDK save默认`loop=False, autostart=False`；SDK save/enable/disable/clear执行enter → 对应RPC → 成功后exit。失败保留维护状态，不能把“程序可能已经保存”误当作“已经可以开机执行”；需查看回执和状态。保存/删除失败不应声称已替换旧有效数据。

0.7 program.info及device.status.program增加counter对象，包含active/name/value/interval_ms，供诊断；不是光学反馈。新建控制会话仍接管停止开机计数，不能用新建Robot查询代替不接管诊断。

## 4. 启动、所有权与结束

- 开机仅对有效保存流程、enabled且非维护/非存储故障情况安排执行；禁用或故障不运行。保存本身不驱动输出。
- session.open接管并停止正在运行/待启动的离线流程。在线运行可以继续控制其它外设，但不与固化执行器同时抢同一套输出。
- program.start在当前会话显式运行；普通实时动作不能和运行流程混用，先program.stop再调用在线动作。心跳维持此会话，close或租约到期停止。
- close默认不恢复固化程序；enabled保留，下一次重启才按策略自启。不会因为电脑程序意外退出就突然恢复舵机动作。
- loop=False到末尾结束并清理输出；loop=True回到程序起点。屏幕/舵机配置快照结束后恢复在线配置；恢复映射不自动移动舵机。
- 0.7的terminal counter例外：该指令显示start后持续按interval_ms局部擦除/绘制，不到达普通程序末尾；只接受loop=False。计数RAM运行、不每周期写NVS，停止/重启后再次start从start初始化；有处理延迟时按完整经过周期补足，毫秒回绕使用无符号差值。即将超过int64上限时停止报错，不静默回绕。
- 驱动/输入/资源错误停止流程并记录错误；清理失败显式报告，不当成完成。physical_verified始终false，软件回执不代替光学/电气/机械验收。

存储使用独立的程序记录，不把程序快照混进原在线配置。空间不足返回错误，不擦除其它NVS数据。现有板仅1MiB应用区的兼容条件仍需由目标编译和安装说明核对；本协议文档不表示已经刷写真板或完成断电实物验收。
