'''
Author: 陌
Date: 2026-11-08 15:28:42
LastEditors: 陌
LastEditTime: 2026-11-08 15:58:10
'''
"""Query one teaching device without GPIO setup or output commands."""
import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("Not connected. Add --run to query the device.")
        return 0
    from ...sdk.python.src.ai_robot import Robot

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))
    with Robot(port=args.port, timeout=3.0) as robot:
        print(json.dumps({"info": robot.get_info(), "status": robot.get_status(), "config": robot.config.get(), "pins": robot.list_pins()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
