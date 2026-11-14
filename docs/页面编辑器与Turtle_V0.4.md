# 自定义页面与标准库 Turtle 使用说明 V0.4

固件：0.4.0；Python SDK：0.4.1。面向当前 ESP32-S3 + ST7735S/ST7789；不依赖 AI 服务器。电脑 Python 通过 USB 调用板级固件，修改绘图代码不需要重新烧录。

## 一、选择操作方式

| 目标 | 建议方式 | 关闭电脑程序后 |
|---|---|---|
| 状态面板、中文标题、小图标、多页面 | 本地网页页面编辑器，或 Python 上传 JSON | 保存到开发板；明确启用开机页后可自动显示 |
| 几何、自由绘画、标准库 turtle 课程 | 标准 Turtle 电脑窗口，完成后点击发送 | 临时图像；连接关闭后恢复已启用默认页 |
| 照片、PNG/JPEG、完整插画 | Python `robot.display.image()` | 临时整屏图像；无需压缩成小图标 |
| 任意 HTML/CSS/JavaScript 学员网页 | 后续独立作品宿主 | 本轮尚未实现上传任意网页并在板端运行 |

电脑网页编辑器是页面制作工具。开发板保存的是受限 JSON 页面数据及图标，不运行浏览器、学生 Python 或 Turtle。

## 二、准备与入口

1. 接好屏幕，保留目前已经测通的接线；换线前断电。自定义接线使用根目录 `配置硬件.cmd` 或修改 `config/hardware.json`，不要求固定SPI GPIO。
2. 首次双击根目录 `安装Python环境.cmd`，安装 Python SDK、pyserial、Pillow。需要 Python 3.11+，Turtle 还需要 Python 安装自带的 Tcl/Tk。当前电脑两个项目环境均已更新至SDK0.4，Pillow13。
3. 串口、屏幕及新示例引脚统一配置见 [统一配置与接线说明](统一配置与接线说明.md)，旧配置文件为兼容入口。当前板端安装教学固件 `ai-maker-s3` V0.4.0。确认版本可运行 `tests/quick/01_device_info.py`；旧诊断白灯固件不能运行SDK。
4. 多个USB串口时在配置窗口选择实际串口，或修改 `config/hardware.json` 的 `connection.port`。关闭串口监视器，一次只用一个程序控制COM5。

| 入口 | 作用 |
|---|---|
| `打开页面编辑器.cmd` | 启动电脑本地服务并打开浏览器 |
| `打开Turtle绘图.cmd` | 运行可直接修改的标准Turtle示例 |
| `tests/quick/turtle_demo.py` | IDE点击运行，与上方入口相同 |
| `tests/quick/pages_upload.py` | 上传并显示示例页面5秒，默认不启用开机页 |
| `tests/quick/pages_show.py` | 显示已保存页面 |
| `tests/quick/pages_startup.py` | 明确启用已保存的开机默认页 |
| `tests/quick/pages_startup_off.py` | 关闭开机默认页 |

## 三、网页编辑器

双击入口后访问 `http://127.0.0.1:8765`。先编辑、预览，再连接ESP32上传。打开页面、拖拽和导入文件本身不会连接串口。

1. 设置画布宽高，与实际屏幕旋转后的尺寸一致。目前ST7735S横屏为160×128；ST7789 240×320横屏为320×240。
2. 添加文字、矩形、线段、图片控件。拖拽调整位置，属性区修改内容、颜色、大小与控件ID；页面ID、控件ID使用ASCII字母开头的字母数字下划线，最长24字符。
3. 导入PNG/JPEG/WebP作为小图标，编辑器缩放并转为RGB565。背景透明度在导入时合成到所选背景色。图标不是完整照片传输方式。
4. 导出JSON留存电脑；之后可以导入继续编辑，也可查看/编辑JSON。非法结构、越界、超限会拒绝。
5. 选择COM5并连接；查看或设置屏幕引脚。更改引脚前须按维护、断电换线流程操作。不要在实际接线未改时随意应用新映射。
6. 上传到开发板，选择显示页面；需要脱离电脑显示时，再明确启用默认页。上传新页面包会关闭之前的开机显示，避免新内容意外自动运行。
7. 点击**断开连接**，验证板端默认页。仅关闭浏览器标签页不会停止后台服务及心跳；也可以在启动服务的命令行按Ctrl+C。

一次保存一个页面包，最多4页、32个控件、4张图；单图最大48×48，总解码图像数据最多4608字节，紧凑JSON总计8192字节。文本支持内置中文字体，长文本需自己换行、安排位置；没有自动排版和滚动。

板端以两个NVS二进制槽保存页面，先写新槽再切换元数据；失败返回错误并保留之前有效版本。旧槽不是可选历史版本列表。当前NVS只有24KiB，含旧项目数据，仍可能因空间不足写入失败；本功能不会自动擦除原NVS。清空页面调用 `robot.pages.clear()`，会进入并保持维护状态。

## 四、标准库 Turtle 电脑绘图

双击 `打开Turtle绘图.cmd`，会出现真实标准库Turtle窗口。当前默认文件在开头创建Robot、set屏幕、start，画好后通过 `finish(screen, robot=robot)` 复用同一连接；点击窗口下方**发送到ESP32**或按Enter才传图。图片会按屏幕尺寸等比缩小，再次绘图后可再次发送。若使用不传robot的旧方式，则第一次发送时才打开USB。

学员可以在 `tests/quick/` 新建这个短文件：

```python
import turtle
from _turtle import finish

screen = turtle.Screen()
screen.setup(640, 480)
pen = turtle.Turtle()
pen.color("orange")
for _ in range(5):
    pen.forward(180)
    pen.right(144)
pen.hideturtle()
finish(screen)
```

使用 `finish(screen)` 作为结尾，会添加发送按钮并进入事件循环。不要再调用 `turtle.done()`；标准库其余画线、填色、事件处理方式照常使用。可自定义 `screen.bgcolor()`，也可以创建多个Turtle。

**连接只由一个入口管理，支持两种方式。**

- 开头连接并配置：`robot = Robot(port="COM5")`，全部外设set、start，结尾写 `finish(screen, robot=robot)`。发送按钮复用同一robot，不再打开串口。首次发送会幂等调用start；不会自动移动舵机。
- 点击发送才连接：前面不创建Robot，结尾写 `finish(screen, port="COM5", panel="st7735s_128x160", SCL=4, SDA=5, CS=15, DC=7, RES=6, BLK=16)`。

传了robot后不能再传port或IO，避免两份配置冲突。**finish会接管该连接的结束清理**：关闭窗口时关闭robot，即使从未点发送；这个连接上的舵机、GPIO、RGB等运行输出也一同停止。若尚未start、仍处维护，关闭窗口不会擅自退出维护。正常关窗后再次robot.close是幂等的；若希望窗口关闭后其他外设继续运行，不用finish接管，改用 `ai_robot.drawing.send_turtle(robot, screen)` 并自己管理界面与连接。

推荐开头配置的完整短文件见 `tests/guide/14_turtle_top_setup.py`。实际绘图可能出错，因此采用try/finally兜底close；不要求使用with。传入已有连接的模式失败后会释放并停用发送按钮，应关闭窗口后修正重跑，不会自动另开连接。修改程序前先关闭旧运行窗口/脚本，避免旧进程继续占串口。

发送捕获当前内部画布，排除按钮、标题栏和桌面；不是解析EPS，也不需要Ghostscript。Windows使用Pillow的窗口捕获，窗口须已显示且不能最小化。只发送当前可见画布；画到可视区域外的内容不会包含。图片只有像素，没有可编辑的海龟命令；光标未隐藏时也会出现在图中。

发送成功后保持串口会话及心跳，画面持续显示。关闭Turtle窗口才关闭会话；固件停止临时输出，然后恢复已启用的默认页。未启用默认页时屏幕释放，带GPIO背光的屏幕会熄灭。异常断连由6秒租约回收。期间不会自动驱动舵机。

高分辨率画布缩小到160×128时，细线和小字会损失细节。建议粗线、少量大字、高对比色；当前是画好后整帧发送，适合静态作品，不适合实时动画或视频。传输失败不自动重发。由finish自行建连接的方式，修正后可手动再次点击；传入已有robot的方式，错误后会关闭该连接并停用发送按钮，需要关闭窗口后修正重跑。

## 五、Python图片与页面接口

完整图片可直接发送，不受48×48图标限制：

```python
from _screen import connect_screen

with connect_screen() as robot:
    robot.display.image("我的图片.png", fit="contain")
    robot.wait(10)
```

`contain`等比缩放补边，`cover`等比缩放居中裁剪。SDK按实际屏幕尺寸缩放，每包最多384像素，以RGB565分块发送；没有每帧NVS写入。源图上限1600万像素；当前支持最大320×320目标尺寸，覆盖已接入的屏幕尺寸。

页面脚本可用 `robot.pages.upload(path)`、`show("home")`、`text("status", "新状态")`、`startup("home")`、`download()`。`text()`只更新当前显示的文本，不写入页面包；断开后恢复保存的原文字。JSON格式见 `protocols/pages-v1.md` 和 `examples/pages/page_demo.json`。

## 六、固件与脱机行为

本轮已更新ESP32固件至V0.4，因为新增了页面存储、默认页渲染和位图协议。以后修改Python绘图、页面JSON或图标，只需运行/上传数据；新增驱动或协议能力时才更新固件。

当前板通过COM5原生USB，RGB48；应用产物 `build/native-usb/ai_maker_s3.ino.bin`，SDK包 `sdk/python/dist/ai_maker_robot-0.4.1-py3-none-any.whl`。本次仅写现有0x10000应用区域，保留1MiB应用分区、NVS和旧接线；**不能将参考16MiB merged镜像直接用于当前板**。

启用默认页后，上电和复位会读取保存的页面；电脑取得控制会话时让出屏幕，关闭/到期后再恢复。维护模式禁止自动显示。改变屏幕尺寸导致页面不匹配时会关闭自动显示，需要重新制作/上传匹配尺寸的页面。脱离电脑运行仍需要USB电源或适配的独立电源；这不是电池管理功能。

降级固件前先关闭默认页，并恢复对应版本的NVS备份或兼容配置；V0.3不理解V0.4页面状态元数据，不能假设无损降级。备份位于本机 `backups/`，可能含旧项目私有数据，不应分发。

## 七、本次验证

COM5安装V0.4并完成哈希校验。48×48图像页面包大于4KiB，真实NVS保存及完整读回一致；示例页面上传、文本更新、本地HTTP编辑器连接/上传/断开通过。真实Turtle画布捕获已在Windows检验像素；截图经64个分块完成160×128真机传输。关闭会话及复位后，板端状态确认默认页正在显示、舵机未激活。用户确认默认页文字、图标、颜色均正常。

Turtle整屏画面的光学效果仍需按实际作品观察；驱动回执无法测量屏幕像素。软件验证与SHA详见 `docs/verification.md`。
