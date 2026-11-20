"""连接会接管并停止固化流程；默认只查看/停止，不删除已保存程序。需要0.6固件。"""
from ai_robot import Robot

PORT = "COM5"
with Robot(port=PORT) as robot:
    robot.program.stop()
    print(robot.program.info())
    # robot.program.disable()  # 保留流程，关闭下次开机自启。
    # robot.program.enable()   # 保留流程，启用下次开机自启，不立刻执行。
    # robot.program.clear()    # 删除流程；确认需要删除后才取消注释。
    # robot.program.start()    # 当前会话立即运行；退出/租约到期停止。
    # robot.wait(10)           # 使用start时保留会话一段时间观察。
