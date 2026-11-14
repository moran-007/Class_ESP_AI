"""删除全部舵机映射并释放信号；之后 GPIO12 等可重新用于普通实验。"""
from _board import connect

with connect() as robot:
    robot.maintenance.enter()
    current = robot.config.get()
    current["config"]["servos"] = []
    robot.config.apply(current["config"], expected_revision=current["revision"])
    robot.maintenance.exit()
    print("全部舵机映射已清除，请按需要断电换线。")
