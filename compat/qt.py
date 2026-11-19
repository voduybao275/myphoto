"""Tương thích Qt: mã nguồn dùng cú pháp PySide6 nhưng chạy được trên PySide2 (Qt 5.15).

Windows 10 build 10240 không nạp được plugin nền tảng của Qt 6 (thiếu các API DPI
có từ build 14393). Trên máy đó, module này ánh xạ ``PySide6`` sang ``PySide2``
để toàn bộ mã nguồn giữ nguyên cú pháp enum/import hiện đại.
"""

from __future__ import annotations

import sys
from typing import Any


def _windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except AttributeError:  # pragma: no cover - chỉ để an toàn trên nền tảng lạ
        return 0


def _install_pyside2() -> Any:
    import PySide2
    from PySide2 import QtCore, QtGui, QtWidgets

    # Qt 5 đặt QAction/QActionGroup/QShortcut trong QtWidgets; Qt 6 chuyển sang QtGui.
    for name in ("QAction", "QActionGroup", "QShortcut"):
        if not hasattr(QtGui, name):
            setattr(QtGui, name, getattr(QtWidgets, name))
    sys.modules["PySide6"] = PySide2
    sys.modules["PySide6.QtCore"] = QtCore
    sys.modules["PySide6.QtGui"] = QtGui
    sys.modules["PySide6.QtWidgets"] = QtWidgets
    return PySide2


def _install_pyside6() -> Any:
    import PySide6

    return PySide6


def _select_binding() -> tuple[Any, str]:
    # Trên Windows cũ, ưu tiên PySide2 kể cả khi người dùng đã cài PySide6.
    if _windows_build() and _windows_build() < 14393:
        try:
            return _install_pyside2(), "PySide2"
        except ImportError:
            pass
    try:
        return _install_pyside6(), "PySide6"
    except ImportError:
        try:
            return _install_pyside2(), "PySide2"
        except ImportError as exc:  # pragma: no cover - thiếu hoàn toàn Qt
            raise ImportError(
                "Không tìm thấy PySide6 hoặc PySide2. Hãy chạy lệnh cài đặt trong README.md."
            ) from exc


_binding, QT_BINDING = _select_binding()

from PySide6.QtCore import QPointF  # noqa: E402


def mouse_event_position(event: Any) -> QPointF:
    """Trả về vị trí chuột dạng QPointF cho cả QMouseEvent của Qt 5 và Qt 6."""
    position = getattr(event, "position", None)
    if callable(position):
        return QPointF(position())
    local_pos = getattr(event, "localPos", None)
    if callable(local_pos):
        return QPointF(local_pos())
    return QPointF(event.pos())


def wheel_event_position(event: Any) -> QPointF:
    """Trả về vị trí con trỏ của QWheelEvent trên Qt 5 hoặc Qt 6."""
    position = getattr(event, "position", None)
    if callable(position):
        return QPointF(position())
    pos_f = getattr(event, "posF", None)
    if callable(pos_f):
        return QPointF(pos_f())
    return QPointF(event.pos())


def exec_object(obj: Any) -> int:
    """Gọi exec()/exec_() tuỳ phiên bản Qt (PySide2 chỉ có exec_)."""
    runner = getattr(obj, "exec", None)
    if callable(runner):
        return int(runner())
    return int(obj.exec_())
