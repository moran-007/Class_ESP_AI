"""Run one audio test at a time; IO remains explicit in each Python file."""
from pathlib import Path
import subprocess
import sys

EXAMPLES=Path(__file__).resolve().parents[1]/'examples/portable'
LESSONS=(('01_info.py','设备与IO信息（只需USB）'),
    ('02_audio_record.py','麦克风收音3秒，保存WAV'),('03_audio_tone.py','功放低幅测试音'),
    ('04_audio_echo.py','先收音再回放'),('05_audio_file.py','播放本地recording.wav'),
    ('06_audio_url.py','播放显式HTTP音频（先提供文件服务）'),('07_io_types.py','数字/ADC/PWM区分'))

def main():
    while True:
        print('\n先修改所选文件的COM与IO，完成接线；一次运行一项，0退出')
        for i,(_,label) in enumerate(LESSONS,1):print(f'{i}. {label}')
        choice=input('编号：').strip()
        if choice=='0':return
        if choice not in {str(i) for i in range(1,len(LESSONS)+1)}:
            print('请输入有效编号');continue
        result=subprocess.run([sys.executable,str(EXAMPLES/LESSONS[int(choice)-1][0])],cwd=EXAMPLES)
        print(f'运行结束，退出码：{result.returncode}')

if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError):print('\n已退出')
