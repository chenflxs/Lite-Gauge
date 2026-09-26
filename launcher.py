"""Compatibility launcher for the portable LiteGauge distribution.

The actual application lives in ``dist/LiteGauge`` so its Qt native DLLs keep
their required directory layout.  This tiny, Qt-free executable preserves the
original ``dist/LiteGauge.exe`` entry point for existing shortcuts.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, "LiteGauge", 0x10)


def main() -> int:
    dist_dir = Path(sys.executable).resolve().parent
    application = dist_dir / "LiteGauge" / "LiteGauge.exe"
    if not application.is_file():
        show_error(f"找不到 LiteGauge 程序文件：\n{application}")
        return 1
    try:
        subprocess.Popen([str(application)], cwd=str(application.parent))
    except OSError as error:
        show_error(f"无法启动 LiteGauge：\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
