"""显式音频URL入口；测试时可用本地HTTP服务，未来换成云端地址。"""
from ai_robot import Robot

URL = "http://127.0.0.1:8000/recording.wav"  # 先启动提供此文件的服务。
with Robot(port="COM5") as robot:
    robot.audio.set(bclk=42, ws=41, din=-1, dout=40, sd=39, volume=20)
    robot.start()
    robot.audio.play_url(URL)  # 默认WAV；不连接任何AI服务、不自动读取密钥。
