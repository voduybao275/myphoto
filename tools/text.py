"""Text Tool — nhấp vào canvas để gõ chữ ngay tại chỗ."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from tools.base import CanvasTool


class TextTool(CanvasTool):
    id = "text"
    name = "Text"
    shortcut = "T"
    hint = (
        "Nhấp để gõ chữ trên canvas; nhấp vào layer chữ để sửa. "
        "Ctrl+Enter xong, Esc huỷ. Menu Type mở hộp thoại định dạng."
    )
    cursor = Qt.CursorShape.IBeamCursor

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        if not (
            0.0 <= image_pos.x() < document.width
            and 0.0 <= image_pos.y() < document.height
        ):
            view.status_message.emit("Hãy nhấp bên trong canvas để đặt văn bản.")
            return False
        view.text_placement_requested.emit(
            QPointF(round(image_pos.x()), round(image_pos.y()))
        )
        return True
