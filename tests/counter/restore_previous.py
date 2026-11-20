"""恢复本次计数测试前备份的固化流程；重启后按原开机策略运行。"""
from pathlib import Path
import json
from ai_robot import Program, Robot

PORT = "COM5"
BACKUP = Path(__file__).resolve().parents[2] / "backups/counter_v070_20261115/before.json"
before = json.loads(BACKUP.read_text(encoding="utf-8"))
saved = before["program"]
with Robot(port=PORT) as robot:
    if saved is None:
        robot.program.clear()
    else:
        robot.program.save(Program.from_dict(saved["program"]),
                           loop=saved["loop"], autostart=saved["enabled"])
print("已恢复测试前的固化内容和开机策略；按RESET或重新接电生效。")
