"""Verify that the root environment uses this checkout and the classroom dependencies."""

from importlib.metadata import version
from pathlib import Path
import sys
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    if Path(sys.prefix).resolve() != (root / ".venv").resolve():
        print("Use the project root .venv.", file=sys.stderr)
        return 1
    try:
        import ai_robot
        import serial
        import tkinter
        from PIL import ImageTk

        sdk = root / "sdk" / "python"
        target = tomllib.loads((sdk / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        if Path(ai_robot.__file__).resolve() != sdk / "src" / "ai_robot" / "__init__.py":
            raise ValueError("ai_robot is not loaded from this project checkout")
        if version("ai-maker-robot") != target or ai_robot.__version__ != target:
            raise ValueError(f"expected ai_robot {target}")
        pillow = version("Pillow")
        if not (12, 3) <= tuple(map(int, pillow.split(".")[:2])) < (14, 0):
            raise ValueError("Pillow has an incompatible version")
    except (ImportError, ValueError, OSError) as error:
        print(f"Project environment check failed: {error}", file=sys.stderr)
        return 1
    print(f"Python {sys.version.split()[0]} | ai_robot {target} | pyserial {serial.VERSION} | Pillow {pillow} | Tk {tkinter.TkVersion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
