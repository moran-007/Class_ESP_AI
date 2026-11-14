"""INMP441：BCLK42、WS41、SD21，L/R接地；3.3V供电并共地。"""
from ai_robot import Robot

with Robot(port="COM5") as robot:
    robot.audio.set(bclk=42, ws=41, din=21, dout=-1, sd=-1)
    robot.start()
    clip = robot.audio.record(seconds=3)
    clip.to_wav("recording.wav")
    print("已保存recording.wav：", clip.to_wire())
    print("电平：", clip.levels, "；回执不代表麦克风实物已验收")
