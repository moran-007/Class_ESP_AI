"""Start the offline page designer; no USB connection until its Connect button."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editor.server import main

if __name__ == "__main__":
    try:
        main()
    except OSError as error:
        raise SystemExit(f"无法启动本地编辑器：{error}。如端口已占用，请关闭旧窗口或使用 --port 8766。") from None
