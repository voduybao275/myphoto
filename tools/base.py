"""Giao diện chung cho các công cụ canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

if TYPE_CHECKING:  # pragma: no cover
    from ui.canvas_view import CanvasView


class CanvasTool:
    id: str = ""
    name: str = ""
    shortcut: str = ""
    hint: str = ""
    cursor: Qt.CursorShape = Qt.CursorShape.ArrowCursor

    def mouse_press(self, view: "CanvasView", event: QMouseEvent, image_pos: QPointF) -> bool:
        return False

    def mouse_move(self, view: "CanvasView", event: QMouseEvent, image_pos: QPointF) -> bool:
        return False

    def mouse_release(self, view: "CanvasView", event: QMouseEvent, image_pos: QPointF) -> bool:
        return False

    def key_press(self, view: "CanvasView", event: QKeyEvent) -> bool:
        return False
