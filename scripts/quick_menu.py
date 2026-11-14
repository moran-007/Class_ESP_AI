"""Windows 双击测试入口；连接逻辑仍在可独立运行的短示例中。"""
from pathlib import Path
import subprocess
import sys

EXAMPLES = Path(__file__).resolve().parents[1] / "tests" / "quick"
LABELS = (
    "设备信息（只需 USB）", "板载 RGB（只需 USB）", "GPIO 输出（接线后运行）",
    "按钮输入（接线后运行）", "ADC 输入（接线后运行）", "PWM 输出（接线后运行）",
    "舵机动作（确认接线、独立供电和行程）", "清除全部舵机映射",
    "屏幕纯色（先修改屏幕接线配置）", "屏幕中文与图形（先修改屏幕接线配置）",
    "屏幕背光（仅BLK已接GPIO）",
    "上传页面示例（先配置屏幕，不启用开机页）", "显示已保存页面",
    "启用已保存开机默认页", "关闭开机默认页", "标准库Turtle（电脑画图后点击发送）",
)
FILES = (
    "01_device_info.py", "02_rgb.py", "03_gpio.py", "04_button.py", "05_adc.py",
    "06_pwm.py", "07_servo.py", "08_clear_servos.py", "screen_colors.py",
    "screen_text.py", "screen_backlight.py",
    "pages_upload.py", "pages_show.py", "pages_startup.py", "pages_startup_off.py", "turtle_demo.py",
)


def main():
    files = [EXAMPLES / name for name in FILES]
    if len(files) != len(LABELS) or not all(path.is_file() for path in files):
        raise SystemExit("简易测试文件不完整，请保留整个 ai_maker 文件夹。")
    while True:
        print("\nAI小创客本地测试：一次运行一项，0 退出")
        for index, label in enumerate(LABELS, 1):
            print(f"  {index}. {label}")
        choice = input("选择编号：").strip()
        if choice == "0":
            return
        if choice not in {str(i) for i in range(1, len(files) + 1)}:
            print("请输入列表中的编号。")
            continue
        script = files[int(choice) - 1]
        print(f"\n运行 {script.name}", flush=True)
        result = subprocess.run([sys.executable, str(script)], cwd=EXAMPLES)
        print("运行结束。" if result.returncode == 0 else f"运行失败，退出码 {result.returncode}。")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
