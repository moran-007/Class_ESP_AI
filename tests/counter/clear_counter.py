"""清除计数固化，不删除原屏幕/舵机配置和默认页面；固件保留0.7.0。"""
from ai_robot import Robot

PORT = "COM5"
with Robot(port=PORT) as robot:
    robot.program.clear()
    state = robot.program.info()
    assert not state["saved"] and not state["enabled"] and not state["running"]
    print("计数程序已清除：", state)
print("连接已关闭，原来启用的默认页应恢复。")
