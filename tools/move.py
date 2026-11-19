"""Move Tool — di chuyển layer đang chọn trên canvas."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from core.layer import Layer, LayerKind
from tools.base import CanvasTool


class MoveTool(CanvasTool):
    id = "move"
    name = "Move"
    shortcut = "V"
    hint = "Kéo để di chuyển layer đang chọn. Giữ Shift để khoá theo trục."
    cursor = Qt.CursorShape.SizeAllCursor

    def __init__(self) -> None:
        self._layer: Layer | None = None
        self._start_offset: tuple[int, int] = (0, 0)
        self._start_pos = QPointF()
        self._dragging = False

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        layer = document.active_layer
        if layer is None:
            view.status_message.emit("Chưa có layer nào. Hãy tạo layer mới (Ctrl+Shift+N).")
            return False
        if layer.locked:
            view.status_message.emit(f"Layer '{layer.name}' đang bị khoá.")
            return False
        if layer.kind == LayerKind.ADJUSTMENT:
            view.status_message.emit(
                "Layer điều chỉnh không có pixel để di chuyển. "
                "Nhấp đôi layer để sửa tham số."
            )
            return False
        self._layer = layer
        self._start_offset = (layer.offset_x, layer.offset_y)
        self._start_pos = QPointF(image_pos)
        self._dragging = True
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._dragging or self._layer is None:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        delta_x = image_pos.x() - self._start_pos.x()
        delta_y = image_pos.y() - self._start_pos.y()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if abs(delta_x) >= abs(delta_y):
                delta_y = 0.0
            else:
                delta_x = 0.0
        view.document.preview_layer_offset(
            self._layer,
            round(self._start_offset[0] + delta_x),
            round(self._start_offset[1] + delta_y),
        )
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._dragging or self._layer is None:
            return False
        layer = self._layer
        self._dragging = False
        self._layer = None
        view.document.commit_layer_offset(layer, self._start_offset, (layer.offset_x, layer.offset_y))
        return True
