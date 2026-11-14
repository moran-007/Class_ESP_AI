"""MAX98357A+扬声器：BCLK42、LRC41、DIN40、SD39；先低音量测试。"""
from ai_robot import AudioClip, Robot

with Robot(port="COM5") as robot:
    robot.audio.set(bclk=42, ws=41, din=-1, dout=40, sd=39, volume=20)
    robot.start()
    robot.audio.play(AudioClip.tone(frequency=440, seconds=1, volume=0.1))
