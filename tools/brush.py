"""Brush và Eraser — kéo trên canvas để vẽ màu hoặc tẩy pixel."""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap

from core.paint import MAX_BRUSH_SIZE, MIN_BRUSH_SIZE, BrushSettings
from tools.base import CanvasTool

_UNSET = object()
_CURSOR_CACHE: dict[tuple[int, bool], QCursor] = {}


def _brush_cursor(diameter: int, erase: bool) -> QCursor:
    key = (diameter, erase)
    cached = _CURSOR_CACHE.get(key)
    if cached is not None:
        return cached
    size = diameter + 4
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    center = size / 2.0
    radius = diameter / 2.0
    painter.setPen(QPen(QColor(0, 0, 0, 200), 2.0))
    painter.drawEllipse(QPointF(center, center), radius, radius)
    if not erase:
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.0))
        painter.drawEllipse(QPointF(center - 1.0, center - 1.0), radius - 1.0, radius - 1.0)
    painter.end()
    cursor = QCursor(pixmap, int(center), int(center))
    _CURSOR_CACHE[key] = cursor
    return cursor


class PaintTool(CanvasTool):
    """Lớp chung cho cọ và tẩy."""

    erase = False

    def __init__(self) -> None:
        self.size = 40
        self.hardness = 0.8
        self.opacity = 1.0
        self.color: tuple[int, int, int, int] = (0, 0, 0, 255)
        self.paint_mask = False
        self._session = None
        self._active = False

    # --------------------------------------------------------------- cấu hình
    def configure(
        self,
        *,
        size: int | None = None,
        hardness: float | None = None,
        opacity: float | None = None,
        color: tuple[int, int, int, int] | None = None,
        paint_mask: object = _UNSET,
    ) -> None:
        if size is not None:
            self.size = max(MIN_BRUSH_SIZE, min(MAX_BRUSH_SIZE, int(round(size))))
        if hardness is not None:
            self.hardness = max(0.0, min(1.0, float(hardness)))
        if opacity is not None:
            self.opacity = max(0.0, min(1.0, float(opacity)))
        if color is not None:
            self.color = tuple(int(channel) for channel in color)  # type: ignore[assignment]
        if paint_mask is not _UNSET:
            self.paint_mask = bool(paint_mask) and not self.erase

    def options(self) -> dict[str, object]:
        return {
            "size": self.size,
            "hardness": self.hardness,
            "opacity": self.opacity,
            "color": self.color,
            "paint_mask": self.paint_mask,
        }

    @property
    def paint_target(self) -> str:
        return "mask" if self.paint_mask else "pixels"

    def cursor_for(self, view) -> QCursor | Qt.CursorShape:
        diameter = int(round(self.size * view.zoom))
        if diameter < 6 or diameter > 160:
            return Qt.CursorShape.CrossCursor
        return _brush_cursor(diameter, self.erase)

    # ------------------------------------------------------------ sự kiện chuột
    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        settings = BrushSettings(
            size=self.size,
            hardness=self.hardness,
            opacity=self.opacity,
            color=self.color,
            erase=self.erase,
        )
        try:
            session = view.document.begin_brush_stroke(
                settings, target=self.paint_target
            )
        except (ValueError, TypeError) as exc:
            view.status_message.emit(str(exc))
            return True
        self._session = session
        self._active = True
        session.stroke_to(image_pos.x(), image_pos.y())
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or self._session is None:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        self._session.stroke_to(image_pos.x(), image_pos.y())
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        session = self._session
        target = self.paint_target
        self._active = False
        self._session = None
        if session is None:
            return True
        session.stroke_to(image_pos.x(), image_pos.y())
        changed = session.finish()
        if not changed:
            view.status_message.emit("Nét cọ không tạo thay đổi nào.")
        elif target == "mask":
            view.status_message.emit(
                "Đã vẽ lên layer mask (Ctrl+Z để hoàn tác)."
            )
        elif self.erase:
            view.status_message.emit("Đã tẩy pixel (Ctrl+Z để hoàn tác).")
        else:
            view.status_message.emit("Đã vẽ nét cọ (Ctrl+Z để hoàn tác).")
        return True

    def key_press(self, view, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._active:
            self.cancel(view)
            return True
        return False

    def reset(self, view) -> None:
        if self._session is not None:
            self._session.cancel()
        self._session = None
        self._active = False

    def cancel(self, view) -> None:
        if self._session is not None:
            self._session.cancel()
        self._session = None
        self._active = False
        view.status_message.emit("Đã huỷ nét cọ.")


class BrushTool(PaintTool):
    id = "brush"
    name = "Brush"
    shortcut = "B"
    hint = "Kéo để vẽ bằng màu Foreground. Có thể chọn vẽ lên layer mask."
    cursor = Qt.CursorShape.CrossCursor


class EraserTool(PaintTool):
    id = "eraser"
    name = "Eraser"
    shortcut = "Shift+E"
    hint = "Kéo để tẩy pixel (giảm độ đục)."
    cursor = Qt.CursorShape.CrossCursor
    erase = True
