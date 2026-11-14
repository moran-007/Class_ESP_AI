"""Run one configurable lesson at a time; never batch-drive peripherals."""
from pathlib import Path
import subprocess
import sys

GUIDE=Path(__file__).resolve().parents[1]/'tests/guide'
LESSONS=(('01_info.py','设备信息（只需USB）'),('02_rgb.py','板载RGB（只需USB）'),
    ('03_led.py','外接LED'),('04_button_led.py','按钮控制LED'),('05_adc.py','ADC'),
    ('06_pwm.py','PWM调光'),('07_servo.py','舵机动作（先完成供电、接线和校准）'),
    ('08_screen.py','屏幕中文与图形'),('09_pages.py','页面上传（160×128）'),
    ('10_turtle.py','标准库Turtle'),('11_image.py','整屏图片'),
    ('12_multi_parts.py','多外设组合（屏幕+舵机+按钮+RGB，先接线）'),
    ('13_display_fps.py','整屏图片发送测速（先接屏幕）'),
    ('14_turtle_top_setup.py','Turtle开头配置、复用同一连接'))


def main():
    while True:
        print('\n代码内配置示例：在所选Python文件中修改COM串口和GPIO；一次选择一项，0退出')
        for i,(_,label) in enumerate(LESSONS,1):print(f'{i}. {label}')
        choice=input('编号：').strip()
        if choice=='0':return
        if choice not in {str(i) for i in range(1,len(LESSONS)+1)}:
            print('请输入有效编号');continue
        script=GUIDE/LESSONS[int(choice)-1][0]
        result=subprocess.run([sys.executable,str(script)],cwd=GUIDE)
        print(f'运行结束，退出码：{result.returncode}')


if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError):print('\n已退出')
