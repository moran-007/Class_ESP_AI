"""Manual fixed-white RGB and GPIO-level tests for the LED diagnostic firmware."""
import argparse
import json
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--pin", type=int, choices=[38, 48], default=48, help="Confirmed board RGB pin: 48")
    parser.add_argument("--mode", choices=["high", "rgb", "off"], default="rgb", help="Default rgb: fixed white; high: GPIO level test")
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    if not args.run:
        print("Not connected. Add --run for the separate LED diagnostic firmware.")
        return 0
    if not 0.5 <= args.seconds <= 60:
        parser.error("seconds must be 0.5..60")
    import serial

    port = serial.Serial(port=None, baudrate=115200, timeout=0.5, write_timeout=2)
    port.dtr = False
    port.rts = False
    port.port = args.port
    expected = {"high": "gpio_high", "rgb": "rgb_solid", "off": "off"}[args.mode]
    with port:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            try:
                frame = json.loads(port.readline())
            except (ValueError, UnicodeError):
                continue
            if isinstance(frame, dict) and frame.get("firmware_family") == "ai-maker-led-diagnostic":
                break
        else:
            raise RuntimeError("No LED diagnostic firmware detected; this is not a teaching SDK test")
        wire = "OFF\n" if args.mode == "off" else f"{'HIGH' if args.mode == 'high' else 'RGB'} {args.pin}\n"
        port.write(wire.encode("ascii"))
        matched = False
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            try:
                frame = json.loads(port.readline())
            except (ValueError, UnicodeError):
                continue
            print(json.dumps(frame, ensure_ascii=False), flush=True)
            if not isinstance(frame, dict) or frame.get("mode") != expected:
                continue
            if args.mode != "off" and frame.get("pin") != args.pin:
                continue
            if frame.get("driver_ok") is not True:
                raise RuntimeError(f"Diagnostic driver failed: {frame.get('driver_error', 'unknown')}; release: {frame.get('previous_release_error', 'unknown')}")
            if args.mode == "high" and frame.get("read_level") != 1:
                raise RuntimeError("The selected GPIO did not read HIGH")
            matched = True
        if not matched:
            raise RuntimeError("No matching diagnostic state received")
    print("Diagnostic state verified. Firmware keeps this state until changed; a reset restores the configured boot-time fixed white. Use --mode off to clear it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
