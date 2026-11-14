"""麦克风和功放共用BCLK/WS，录完再播；按实际接线修改所有IO。"""
from ai_robot import Robot

robot = Robot(port="COM5")
try:
    robot.audio.set(bclk=42, ws=41, din=21, dout=40, sd=39, volume=20)
    robot.start()
    clip = robot.audio.record(seconds=3)
    print(clip.levels)
    clip.to_wav("recording.wav")
    robot.audio.play(clip)
finally:
    robot.close()
