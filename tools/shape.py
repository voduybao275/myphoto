"""Shape Tool — kéo trên canvas để tạo layer hình khối."""

from __future__ import annotations

import math

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from core.shape_layer import (
    MAX_CORNER_RADIUS,
    MAX_STROKE_WIDTH,
    SHAPE_KINDS,
    ShapeProperties,
)
from tools.base import CanvasTool

_UNSET = object()


class ShapeTool(CanvasTool):
    id = "shape"
    name = "Shape"
    shortcut = "U"
    hint = "Kéo để vẽ hình. Giữ Shift để tạo hình vuông/tròn. Esc để huỷ."
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self) -> None:
        self.kind = "rectangle"
        self.fill_color: tuple[int, int, int, int] | None = (59, 110, 165, 255)
        self.stroke_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self.stroke_width = 0
        self.corner_radius = 12.0
        self._start = QPointF()
        self._active = False

    # --------------------------------------------------------------- cấu hình
    def configure(
        self,
        *,
        kind: str | None = None,
        fill_color: object = _UNSET,
        stroke_color: tuple[int, int, int, int] | None = None,
        stroke_width: int | None = None,
        corner_radius: float | None = None,
    ) -> None:
        """Cập nhật kiểu hình cho lần vẽ kế tiếp (Options Bar gọi hàm này)."""
        if kind is not None:
            if kind not in SHAPE_KINDS:
                raise ValueError(f"Loại hình khối không hợp lệ: {kind}")
            self.kind = kind
        if fill_color is not _UNSET:
            self.fill_color = None if fill_color is None else tuple(fill_color)  # type: ignore[arg-type]
        if stroke_color is not None:
            self.stroke_color = tuple(stroke_color)
        if stroke_width is not None:
            self.stroke_width = max(0, min(MAX_STROKE_WIDTH, int(stroke_width)))
        if corner_radius is not None:
            self.corner_radius = max(
                0.0, min(MAX_CORNER_RADIUS, float(corner_radius))
            )

    def options(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "fill_color": self.fill_color,
            "stroke_color": self.stroke_color,
            "stroke_width": self.stroke_width,
            "corner_radius": self.corner_radius,
        }

    # ------------------------------------------------------------ sự kiện chuột
    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        self._start = _clamp_to_document(view, image_pos)
        self._active = True
        view.set_shape_preview(QRectF(self._start, self._start))
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        rect = self._build_rect(view, image_pos, event.modifiers())
        view.set_shape_preview(rect)
        if rect.width() >= 1.0 and rect.height() >= 1.0:
            view.status_message.emit(
                f"Hình khối: {int(round(rect.width()))} × {int(round(rect.height()))} px"
            )
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        rect = self._build_rect(view, image_pos, event.modifiers())
        self._active = False
        view.set_shape_preview(None)
        x = int(round(rect.left()))
        y = int(round(rect.top()))
        width = int(round(rect.width()))
        height = int(round(rect.height()))
        if width < 2 or height < 2:
            view.status_message.emit("Hình quá nhỏ. Hãy kéo lại trên canvas.")
            return True
        stroke_width = min(self.stroke_width, max(0, min(width, height) // 2))
        try:
            properties = ShapeProperties(
                kind=self.kind,
                width=width,
                height=height,
                fill_color=self.fill_color,
                stroke_color=self.stroke_color,
                stroke_width=stroke_width,
                corner_radius=self.corner_radius,
            )
            layer = view.document.add_shape_layer(properties, x, y)
        except ValueError as exc:
            view.status_message.emit(str(exc))
            return True
        view.status_message.emit(
            f"Đã tạo {layer.name} {width} × {height} px (Ctrl+Z để hoàn tác)."
        )
        return True

    def key_press(self, view, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._active:
            self.cancel(view)
            return True
        return False

    def reset(self, view) -> None:
        self._active = False
        view.set_shape_preview(None)

    def cancel(self, view) -> None:
        self.reset(view)
        view.status_message.emit("Đã huỷ vẽ hình khối.")

    # ------------------------------------------------------------------ helpers
    def _build_rect(self, view, image_pos: QPointF, modifiers) -> QRectF:
        current = _clamp_to_document(view, image_pos)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            delta = current - self._start
            side = max(abs(delta.x()), abs(delta.y()))
            current = QPointF(
                self._start.x() + math.copysign(side, delta.x() or 1.0),
                self._start.y() + math.copysign(side, delta.y() or 1.0),
            )
        document_rect = QRectF(
            0.0, 0.0, float(view.document.width), float(view.document.height)
        )
        return QRectF(self._start, current).normalized().intersected(document_rect)


def _clamp_to_document(view, image_pos: QPointF) -> QPointF:
    document = view.document
    return QPointF(
        min(max(image_pos.x(), 0.0), float(document.width)),
        min(max(image_pos.y(), 0.0), float(document.height)),
    )
