# Wi-Fi 真机测试

在编辑器中选择项目根目录的 `.venv/Scripts/python.exe`，打开需要的 `.py` 文件，改开头的 `PORT` 后直接点运行。推荐 `ai_robot` SDK 0.8.3 和支持配网的教学固件 0.8.0。先关闭其他占用串口的程序。

| 文件 | 用法 |
|---|---|
| [01_setwifi.py](01_setwifi.py) | 配网。可在顶部填写 `WIFI_NAME` 和 `WIFI_PASSWORD`，也可保留 `None` 在终端输入。成功显示名称和 IP。 |
| [02_listwifi.py](02_listwifi.py) | 只查当前连接，显示名称和 IP，不接管屏幕。ESP32 同时只连接一个网络，没有连接时返回空列表。 |
| [03_clearwifi.py](03_clearwifi.py) | 运行即断网并忘记板上保存的名称和密码。接线、页面、固化程序仍保留。 |
| [wifi_screen.py](wifi_screen.py) | 画出 Wi-Fi 名称、IP 和北京时间。也可双击 [运行.cmd](运行.cmd)。 |

在自己的绘图程序开头调用 `robot.setwifi(name, password)`，后面继续用同一个 `robot` 画屏或使用其他外设。已经配过网的板子可以省略这句。`getpass("Wi-Fi 密码：")` 的参数是提示文字，输入后才返回密码；分享脚本时请保留提示输入。

配网时控制台会实时显示阶段。查询返回 `[]` 表示当时没有可用 IP；若配网失败且保留原配置，等设备重新连回原 Wi-Fi 后再查。

文件开头的 `PORT = "COM5"` 可改成实际串口；`SCREEN = None` 表示直接使用板上保存的屏幕接线。换线后如果想在这个文件里改，可把 `SCREEN` 改成下面这样。运行时会将新接线保存到板上：

```python
SCREEN = dict(panel="st7735s_128x160", SCL=4, SDA=5,
              CS=15, DC=7, RES=6, BLK=16, rotation=1)
```

`wifi_screen.py` 默认使用板上已保存的 Wi-Fi。想在画屏前配网，可在该文件顶部设置 `WIFI_NAME`、`WIFI_PASSWORD`；密码留 `None` 时会提示输入。新板没有保存的网络也会提示输入。命令行 `--ssid "新网络名称"` 可临时选择其他网络。

屏幕显示实际 Wi-Fi 名称、板端 IP 和电脑提供的北京时间。运行期间请保持 USB 连接，按 `Ctrl+C` 结束；也可加 `--seconds 30` 限时测试。测试不覆盖固化程序；退出后如需恢复原先自启的计数，可以按板上 RESET。
