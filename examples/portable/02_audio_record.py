"""INMP441：BCLK42、WS41、SD21，L/R接地；3.3V供电并共地。"""
from ai_robot import Robot

BUTTON_PIN = None  # 填 GPIO 编号可改为按住录音，按钮另一端接 GND。

with Robot(port="COM5") as robot:
    robot.audio.set(bclk=42, ws=41, din=21, dout=-1, sd=-1)
    robot.start()
    if BUTTON_PIN is None:
        clip = robot.audio.record(seconds=3)
    else:
        robot.digital.set(BUTTON_PIN, "input_pullup")
        print("按住按钮说话，松开结束录音。")
        while robot.digital.read(BUTTON_PIN) == 1:
            robot.wait(0.02)
        clip = robot.audio.record_while(lambda: robot.digital.read(BUTTON_PIN) == 0)
        if clip is None:
            raise SystemExit("没有采到音频，请按住按钮说话。")
    clip.to_wav("recording.wav")
    print("已保存recording.wav：", clip.to_wire())
    print("电平：", clip.levels, "；回执不代表麦克风实物已验收")
