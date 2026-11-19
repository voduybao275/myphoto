"""Hand và Zoom — các công cụ điều hướng canvas."""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from compat.qt import mouse_event_position
from tools.base import CanvasTool


class HandTool(CanvasTool):
    id = "hand"
    name = "Hand"
    shortcut = "H"
    hint = "Kéo để di chuyển khung nhìn. Giữ Space tại bất kỳ công cụ nào."
    cursor = Qt.CursorShape.OpenHandCursor

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.LeftButton:
            view.begin_pan(mouse_event_position(event))
            return True
        return False

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if view.is_panning:
            view.update_pan(mouse_event_position(event))
            return True
        return False

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.LeftButton and view.is_panning:
            view.end_pan()
            return True
        return False


class ZoomTool(CanvasTool):
    id = "zoom"
    name = "Zoom"
    shortcut = "Z"
    hint = "Click để phóng to; Alt+Click để thu nhỏ."
    cursor = Qt.CursorShape.CrossCursor

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        factor = 1.0 / 1.5 if event.modifiers() & Qt.KeyboardModifier.AltModifier else 1.5
        view.set_zoom(view.zoom * factor, mouse_event_position(event))
        return True
