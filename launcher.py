"""Frozen entry point with non-interactive diagnostics for packaging failures."""
import ctypes
import json
from pathlib import Path
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "windows"))

try:
    from desktop_app import main
    raise SystemExit(main())
except Exception as error:
    for option in ("--self-test", "--ui-smoke"):
        if option in sys.argv:
            path = Path(sys.argv[sys.argv.index(option) + 1])
            path.write_text(json.dumps({"error": f"{type(error).__name__}: {error}"}), encoding="utf-8")
            raise SystemExit(1)
    ctypes.windll.user32.MessageBoxW(0, f"ClipBridge 蓝牙启动失败：{error}", "ClipBridge 蓝牙", 0x10)
    raise SystemExit(1)
