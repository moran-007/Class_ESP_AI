"""Explicit, local, built-in RGB smoke test; no flashing or general GPIO writes."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--run", action="store_true", help="Actually connect and send RGB commands")
    parser.add_argument("--lease-test", action="store_true")
    parser.add_argument("--pattern", choices=["rgb", "states"], default="rgb")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--hold", type=float, default=3.0)
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parent / "reports" / "hardware-rgb.json")
    args = parser.parse_args()
    if not args.run:
        print("Not connected. Add --run to execute the physical RGB test.")
        return 0
    if not 1 <= args.cycles <= 10 or not 0.1 <= args.hold <= 30:
        parser.error("cycles must be 1..10 and hold must be 0.1..30 seconds")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))
    from ai_robot import Robot

    report = {"port": args.port, "software_result": "running", "optical_confirmation": None, "commands": []}
    try:
        with Robot(port=args.port, timeout=3.0, heartbeat_interval=1.0) as robot:
            info = robot.get_info()
            report["device"] = info
            if not info.get("capabilities", {}).get("builtin_led"):
                raise RuntimeError("This firmware does not implement the built-in RGB interface")
            if robot.get_status()["maintenance"]:
                raise RuntimeError("Device is in maintenance; review the wiring/configuration before exiting explicitly")
            colors = [("red", (8, 0, 0)), ("green", (0, 8, 0)), ("blue", (0, 0, 8))]
            if args.pattern == "states":
                colors = [("recording_red", (28, 0, 0)), ("thinking_yellow", (18, 10, 0)), ("playing_green", (0, 22, 0))]
            for cycle in range(args.cycles):
                for name, color in colors:
                    start = time.monotonic()
                    response = robot.led.set(red=color[0], green=color[1], blue=color[2])
                    elapsed = (time.monotonic() - start) * 1000
                    state = robot.get_status()["led"]
                    expected = dict(zip(("red", "green", "blue"), color))
                    if any(state.get(channel) != value for channel, value in expected.items()) or not state.get("driver_ok", True):
                        raise RuntimeError(f"LED command-state mismatch: {state}")
                    report["commands"].append({"cycle": cycle + 1, "color": name, "response": response, "state": state, "request_ms": round(elapsed, 2)})
                    print(f"RGB {name}: command and status matched ({elapsed:.1f} ms)", flush=True)
                    time.sleep(args.hold)
            robot.led.off()
        if args.lease_test:
            with Robot(port=args.port, timeout=3.0, heartbeat_interval=None) as robot:
                robot.led.set(red=8, green=8, blue=8)
                time.sleep(6.4)
                state = robot.get_status()
                led = state["led"]
                passed = (not state["session_active"]
                          and all(led.get(channel) == 0 for channel in ("red", "green", "blue"))
                          and led.get("driver_ok", True))
                report["lease_expiry"] = {"passed": passed, "state": state}
                if not passed:
                    raise RuntimeError("Lease did not expire or RGB command state was not cleared")
                print("Lease expiry: session released and RGB state cleared", flush=True)
        report["software_result"] = "passed"
        return 0
    except Exception as error:
        report["software_result"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        causes = []
        cause = error.__cause__
        while cause is not None and len(causes) < 8:
            causes.append(f"{type(cause).__name__}: {cause}")
            cause = cause.__cause__
        report["error_causes"] = causes
        print(report["error"], file=sys.stderr)
        return 1
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report: {args.report}")


if __name__ == "__main__":
    raise SystemExit(main())
