"""先运行录音示例生成同一工作目录的recording.wav，或修改为自己的文件。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.audio.set(bclk=42, ws=41, din=-1, dout=40, sd=39, volume=20)
    robot.start()
    robot.audio.play_file("recording.wav")  # 必须16kHz、mono、PCM16 WAV。
