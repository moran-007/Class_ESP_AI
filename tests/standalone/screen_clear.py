"""清除保存的固化流程；保留屏幕/舵机配置及默认页面，关闭连接后恢复默认页。"""
from ai_robot import Robot

PORT = "COM5"
with Robot(port=PORT) as robot:
    robot.program.clear()
    state = robot.program.info()
    assert not state["saved"] and not state["enabled"] and not state["running"]
    print("固化流程已清除；原屏幕/舵机配置和页面模板保留。")
print("连接已关闭。原先启用的默认页应恢复；重启不会再运行A/B固化测试。")
