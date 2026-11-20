"""Eyedropper — hút màu từ ảnh ghép của tài liệu."""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from tools.base import CanvasTool


class EyedropperTool(CanvasTool):
    id = "eyedropper"
    name = "Eyedropper"
    shortcut = "I"
    hint = "Nhấp để lấy màu Foreground từ ảnh ghép. Alt+Click để lấy màu Background."
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self) -> None:
        self._sampling = False

    def _sample(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        document = view.document
        x = int(image_pos.x())
        y = int(image_pos.y())
        if x < 0 or y < 0 or x >= document.width or y >= document.height:
            return False
        r, g, b, a = (int(v) for v in document.get_composite().array[y, x])
        to_background = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        view.color_picked.emit((r, g, b, a), to_background)
        target = "Background" if to_background else "Foreground"
        view.status_message.emit(
            f"{target}: #{r:02X}{g:02X}{b:02X}  RGB({r}, {g}, {b})  A={a}"
        )
        return True

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._sampling = True
        self._sample(view, event, image_pos)
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._sampling:
            return False
        self._sample(view, event, image_pos)
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton or not self._sampling:
            return False
        self._sampling = False
        return True

    def reset(self, view) -> None:
        self._sampling = False
