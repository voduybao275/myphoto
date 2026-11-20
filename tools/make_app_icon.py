"""Sinh assets/app_icon.png (256 px) từ icon vẽ bằng QPainter của ứng dụng.

Chỉ dùng lúc đóng gói; PyInstaller cần file icon để nhúng vào .exe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


def main() -> int:
    app = QApplication.instance() or QApplication([])
    from ui import icons

    target = ROOT / "assets" / "app_icon.png"
    pixmap = icons.pixmap("app", 256, QColor("#e0a052"))
    if pixmap.isNull() or not pixmap.save(str(target), "PNG"):
        print(f"Không ghi được icon: {target}", file=sys.stderr)
        return 1
    del app
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
