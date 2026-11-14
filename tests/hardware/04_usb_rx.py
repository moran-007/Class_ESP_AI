"""只读 USB 长帧回归；不打开控制会话，不改配置，不发送舵机动作。"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk/python/src"))
from ai_robot import SerialTransport


def query(wire, index, size, timeout):
    request = {"kind": "request", "protocol_version": 1,
               "request_id": f"rx-{index}", "op": "device.info", "args": {"padding": ""}}
    encode = lambda: json.dumps(request, separators=(",", ":")).encode("ascii")
    request["args"]["padding"] = "x" * (size - len(encode()))
    payload = encode()
    if len(payload) != size:
        raise ValueError("Requested frame size is too small")
    # One write is intentional: pacing could hide a too-small board RX queue.
    start = time.monotonic()
    wire.write(payload + b"\n")
    pending = bytearray()
    while time.monotonic() - start < timeout:
        pending.extend(wire.read(1024, 0.05))
        if len(pending) > 16384:
            raise RuntimeError("Unexpectedly large device response")
        while b"\n" in pending:
            line, _, rest = pending.partition(b"\n")
            pending = bytearray(rest)
            try:
                frame = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(frame, dict) and frame.get("request_id") == request["request_id"]:
                valid = (frame.get("ok") is True and frame.get("protocol_version") == 1
                         and frame.get("data", {}).get("firmware_family") == "ai-maker-s3")
                return {"json_bytes": size, "passed": valid, "response": frame,
                        "elapsed_ms": round((time.monotonic() - start) * 1000, 2)}
    return {"json_bytes": size, "passed": False, "error": "No matching response"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="AUTO")
    parser.add_argument("--report", type=Path, default=ROOT / "tests/hardware/reports/usb-rx.json")
    args = parser.parse_args()
    report = {"read_only": True, "port": args.port, "frames": []}
    wire = None
    try:
        wire = SerialTransport(args.port)
        report["port"] = wire.port
        for index, size in enumerate((160, 255, 256, 257, 384, 768, 2048, 4096)):
            # Recover framing after a prior failed probe; never repeat an action.
            wire.write(b"\n")
            quiet = time.monotonic() + 0.05
            while time.monotonic() < quiet:
                wire.read(1024, 0.01)
            result = query(wire, index, size, 2.0)
            report["frames"].append(result)
            print(f"{size} JSON bytes: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
        report["passed"] = all(frame["passed"] for frame in report["frames"])
        return 0 if report["passed"] else 1
    except Exception as error:
        report.update(passed=False, error=f"{type(error).__name__}: {error}")
        print(report["error"], file=sys.stderr)
        return 1
    finally:
        if wire is not None:
            wire.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Report:", args.report)


if __name__ == "__main__":
    raise SystemExit(main())
