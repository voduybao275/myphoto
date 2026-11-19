"""Công cụ chọn chữ nhật/ellipse, Lasso, Magic Wand, Quick Selection và Crop."""

from __future__ import annotations

import math

import numpy as np

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from core.selection import MAX_FEATHER_RADIUS, Selection
from core.wand import (
    MAX_TOLERANCE,
    color_eligibility,
    flood_fill_eligible,
    flood_fill_mask,
    layer_sample,
    mask_to_path,
)
from tools.base import CanvasTool

_QUICK_CURSOR_CACHE: dict[int, QCursor] = {}


def _quick_cursor(diameter: int) -> QCursor:
    cached = _QUICK_CURSOR_CACHE.get(diameter)
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
    painter.setPen(QPen(QColor(255, 255, 255, 230), 1.0))
    painter.drawEllipse(QPointF(center - 1.0, center - 1.0), radius - 1.0, radius - 1.0)
    painter.end()
    cursor = QCursor(pixmap, int(center), int(center))
    _QUICK_CURSOR_CACHE[diameter] = cursor
    return cursor


def selection_mode_from(event: QMouseEvent) -> str:
    """Shift = cộng, Alt = trừ, Shift+Alt = giao (giống thói quen Photoshop)."""
    modifiers = event.modifiers()
    shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
    alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
    if shift and alt:
        return "intersect"
    if shift:
        return "add"
    if alt:
        return "subtract"
    return "replace"


def combine_selection(
    origin: Selection | None, candidate: Selection | None, mode: str
) -> Selection | None:
    """Kết hợp vùng chọn gốc với vùng chọn mới theo chế độ Shift/Alt."""
    if candidate is None or candidate.is_empty:
        if mode == "replace":
            return None
        return origin
    if mode == "replace" or origin is None:
        if mode in ("subtract", "intersect"):
            return None
        return candidate
    combined = origin.combine(candidate, mode)
    return None if combined.is_empty else combined


def _clamp_to_document(view, image_pos: QPointF) -> QPointF:
    document = view.document
    return QPointF(
        min(max(image_pos.x(), 0.0), float(document.width)),
        min(max(image_pos.y(), 0.0), float(document.height)),
    )


class _MarqueeTool(CanvasTool):
    cursor = Qt.CursorShape.CrossCursor
    selection_label = "Vùng chọn"

    def __init__(self) -> None:
        self._origin: Selection | None = None
        self._start = QPointF()
        self._mode = "replace"
        self._active = False
        self.feather = 0.0
        self.antialias = True

    def configure(
        self, *, feather: float | None = None, antialias: bool | None = None
    ) -> None:
        """Cập nhật tuỳ chọn biên cho vùng chọn kế tiếp."""
        if feather is not None:
            value = float(feather)
            if not math.isfinite(value):
                raise ValueError("Bán kính feather phải là số hữu hạn.")
            self.feather = float(min(max(value, 0.0), MAX_FEATHER_RADIUS))
        if antialias is not None:
            self.antialias = bool(antialias)

    def options(self) -> dict[str, object]:
        return {"feather": self.feather, "antialias": self.antialias}

    def _make_selection(self, width: int, height: int, rect: QRectF) -> Selection:
        raise NotImplementedError

    def _compose(self, view, start: QPointF, current: QPointF) -> Selection | None:
        document = view.document
        rect = QRectF(start, current).normalized()
        candidate = self._make_selection(document.width, document.height, rect)
        return combine_selection(self._origin, candidate, self._mode)

    def _status_text(self, selection: Selection) -> str:
        bounds = selection.bounds()
        text = f"{self.selection_label}: {bounds.width()} × {bounds.height()} px"
        if self.feather > 0:
            text += f" · Feather {self.feather:g} px"
        if not self.antialias:
            text += " · Không anti-alias"
        return text

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        self._origin = document.selection.copy() if document.has_selection() else None
        self._start = _clamp_to_document(view, image_pos)
        self._mode = selection_mode_from(event)
        self._active = True
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        current = _clamp_to_document(view, image_pos)
        selection = self._compose(view, self._start, current)
        view.document.preview_selection(selection)
        if selection is not None:
            view.status_message.emit(self._status_text(selection))
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        current = _clamp_to_document(view, image_pos)
        selection = self._compose(view, self._start, current)
        view.document.commit_selection(self._origin, selection, self.selection_label)
        self._reset()
        return True

    def key_press(self, view, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._active:
            view.document.preview_selection(self._origin)
            self._reset()
            return True
        return False

    def _reset(self) -> None:
        self._origin = None
        self._active = False


class RectSelectTool(_MarqueeTool):
    id = "rect_select"
    name = "Rectangular Marquee"
    shortcut = "M"
    hint = "Kéo để chọn chữ nhật. Shift cộng, Alt trừ, Shift+Alt giao vùng chọn."
    selection_label = "Vùng chọn chữ nhật"

    def _make_selection(self, width: int, height: int, rect: QRectF) -> Selection:
        return Selection.from_rect(
            width,
            height,
            rect,
            feather=self.feather,
            antialias=self.antialias,
        )


class EllipseSelectTool(_MarqueeTool):
    id = "ellipse_select"
    name = "Elliptical Marquee"
    shortcut = "E"
    hint = "Kéo để chọn ellipse. Shift cộng, Alt trừ, Shift+Alt giao vùng chọn."
    selection_label = "Vùng chọn ellipse"

    def _make_selection(self, width: int, height: int, rect: QRectF) -> Selection:
        return Selection.from_ellipse(
            width,
            height,
            rect,
            feather=self.feather,
            antialias=self.antialias,
        )


class LassoSelectTool(_MarqueeTool):
    id = "lasso"
    name = "Lasso"
    shortcut = "L"
    hint = "Kéo để vẽ đường chọn tự do. Shift cộng, Alt trừ, Esc để huỷ."
    selection_label = "Vùng chọn tự do"

    def __init__(self) -> None:
        super().__init__()
        self._points: list[QPointF] = []

    def _candidate(self, document) -> Selection | None:
        if len(self._points) < 3:
            return None
        path = QPainterPath()
        path.moveTo(self._points[0])
        for point in self._points[1:]:
            path.lineTo(point)
        path.closeSubpath()
        path.setFillRule(Qt.FillRule.WindingFill)
        return Selection.from_path(
            document.width,
            document.height,
            path,
            feather=self.feather,
            antialias=self.antialias,
        )

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        self._origin = document.selection.copy() if document.has_selection() else None
        start = _clamp_to_document(view, image_pos)
        self._points = [start]
        self._start = start
        self._mode = selection_mode_from(event)
        self._active = True
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        current = _clamp_to_document(view, image_pos)
        if self._points:
            last = self._points[-1]
            if math.hypot(current.x() - last.x(), current.y() - last.y()) < 1.0:
                return True
        self._points.append(current)
        candidate = self._candidate(view.document)
        selection = combine_selection(self._origin, candidate, self._mode)
        view.document.preview_selection(selection)
        if selection is not None:
            view.status_message.emit(self._status_text(selection))
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or event.button() != Qt.MouseButton.LeftButton:
            return False
        current = _clamp_to_document(view, image_pos)
        if not self._points or self._points[-1] != current:
            self._points.append(current)
        candidate = self._candidate(view.document)
        selection = combine_selection(self._origin, candidate, self._mode)
        view.document.commit_selection(
            self._origin, selection, self.selection_label
        )
        if selection is not None:
            view.status_message.emit(
                self._status_text(selection) + " (Ctrl+Z để hoàn tác)."
            )
        self._reset()
        return True

    def _reset(self) -> None:
        super()._reset()
        self._points = []

    def reset(self, view) -> None:
        self._reset()


class MagicWandTool(CanvasTool):
    id = "magic_wand"
    name = "Magic Wand"
    shortcut = "W"
    hint = (
        "Nhấp để chọn vùng màu tương tự trên layer đang chọn. "
        "Shift cộng, Alt trừ, Shift+Alt giao."
    )
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self) -> None:
        self.tolerance = 32
        self.contiguous = True
        self.feather = 0.0
        self.antialias = False

    def configure(
        self,
        *,
        tolerance: float | None = None,
        contiguous: bool | None = None,
        feather: float | None = None,
        antialias: bool | None = None,
    ) -> None:
        if tolerance is not None:
            value = float(tolerance)
            if not math.isfinite(value):
                raise ValueError("Dung sai phải là số hữu hạn.")
            self.tolerance = int(min(max(value, 0.0), float(MAX_TOLERANCE)))
        if contiguous is not None:
            self.contiguous = bool(contiguous)
        if feather is not None:
            value = float(feather)
            if not math.isfinite(value):
                raise ValueError("Bán kính feather phải là số hữu hạn.")
            self.feather = float(min(max(value, 0.0), MAX_FEATHER_RADIUS))
        if antialias is not None:
            self.antialias = bool(antialias)

    def options(self) -> dict[str, object]:
        return {
            "tolerance": self.tolerance,
            "contiguous": self.contiguous,
            "feather": self.feather,
            "antialias": self.antialias,
        }

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        layer = document.active_layer
        if layer is None:
            view.status_message.emit(
                "Magic Wand cần một layer đang chọn để lấy mẫu màu."
            )
            return True
        sample_x = int(math.floor(image_pos.x()))
        sample_y = int(math.floor(image_pos.y()))
        if not (
            0 <= sample_x < document.width and 0 <= sample_y < document.height
        ):
            view.status_message.emit("Hãy nhấp bên trong canvas để chọn màu.")
            return True
        try:
            sample = layer_sample(
                layer.pixels,
                layer.offset_x,
                layer.offset_y,
                document.width,
                document.height,
            )
            region = flood_fill_mask(
                sample,
                sample_x,
                sample_y,
                self.tolerance,
                contiguous=self.contiguous,
            )
        except ValueError as error:
            view.status_message.emit(str(error))
            return True
        if not region.any():
            view.status_message.emit("Không tìm thấy pixel phù hợp với dung sai.")
            return True
        candidate = Selection.from_path(
            document.width,
            document.height,
            mask_to_path(region),
            feather=self.feather,
            antialias=self.antialias,
        )
        origin = document.selection.copy() if document.has_selection() else None
        mode = selection_mode_from(event)
        selection = combine_selection(origin, candidate, mode)
        document.commit_selection(origin, selection, "Magic Wand")
        if selection is None:
            view.status_message.emit("Vùng chọn đã bị bỏ.")
        else:
            bounds = selection.bounds()
            mode_text = {
                "add": "cộng",
                "subtract": "trừ",
                "intersect": "giao",
            }.get(mode, "")
            suffix = f" ({mode_text})" if mode_text else ""
            view.status_message.emit(
                f"Magic Wand: {bounds.width()} × {bounds.height()} px"
                f"{suffix} · dung sai {self.tolerance}."
            )
        view.update()
        return True


class QuickSelectionTool(CanvasTool):
    id = "quick_select"
    name = "Quick Selection"
    shortcut = "Shift+W"
    hint = (
        "Kéo qua vùng cần chọn; công cụ tự lan theo màu tương tự. "
        "Shift cộng, Alt trừ, Esc để huỷ."
    )
    cursor = Qt.CursorShape.CrossCursor

    MIN_SIZE = 1
    MAX_SIZE = 400

    def __init__(self) -> None:
        self.size = 40
        self.tolerance = 32
        self.feather = 0.0
        self.antialias = False
        self._origin: Selection | None = None
        self._mode = "replace"
        self._active = False
        self._sample: np.ndarray | None = None
        self._working: np.ndarray | None = None
        self._last_position: QPointF | None = None
        self._selected_count = 0

    def configure(
        self,
        *,
        size: float | None = None,
        tolerance: float | None = None,
        feather: float | None = None,
        antialias: bool | None = None,
    ) -> None:
        if size is not None:
            value = float(size)
            if not math.isfinite(value):
                raise ValueError("Cỡ cọ chọn phải là số hữu hạn.")
            self.size = int(
                min(max(round(value), self.MIN_SIZE), self.MAX_SIZE)
            )
        if tolerance is not None:
            value = float(tolerance)
            if not math.isfinite(value):
                raise ValueError("Dung sai phải là số hữu hạn.")
            self.tolerance = int(min(max(value, 0.0), float(MAX_TOLERANCE)))
        if feather is not None:
            value = float(feather)
            if not math.isfinite(value):
                raise ValueError("Bán kính feather phải là số hữu hạn.")
            self.feather = float(min(max(value, 0.0), MAX_FEATHER_RADIUS))
        if antialias is not None:
            self.antialias = bool(antialias)

    def options(self) -> dict[str, object]:
        return {
            "size": self.size,
            "tolerance": self.tolerance,
            "feather": self.feather,
            "antialias": self.antialias,
        }

    def cursor_for(self, view) -> QCursor | Qt.CursorShape:
        diameter = int(round(self.size * view.zoom))
        if diameter < 6 or diameter > 160:
            return Qt.CursorShape.CrossCursor
        return _quick_cursor(diameter)

    def _apply_dab(self, view, position: QPointF) -> bool:
        if self._sample is None or self._working is None:
            return False
        document = view.document
        radius = max(1.0, self.size / 2.0)
        center_x = position.x()
        center_y = position.y()
        x0 = max(0, int(math.floor(center_x - radius)))
        y0 = max(0, int(math.floor(center_y - radius)))
        x1 = min(document.width, int(math.ceil(center_x + radius)))
        y1 = min(document.height, int(math.ceil(center_y + radius)))
        if x1 <= x0 or y1 <= y0:
            return False
        seed_x = int(math.floor(center_x))
        seed_y = int(math.floor(center_y))
        if not (x0 <= seed_x < x1 and y0 <= seed_y < y1):
            return False
        local = self._sample[y0:y1, x0:x1]
        eligible = color_eligibility(
            local, local[seed_y - y0, seed_x - x0], self.tolerance
        )
        ys, xs = np.ogrid[y0:y1, x0:x1]
        circle = (xs + 0.5 - center_x) ** 2 + (ys + 0.5 - center_y) ** 2 <= radius**2
        eligible &= circle
        filled = flood_fill_eligible(eligible, seed_x - x0, seed_y - y0)
        if not filled.any():
            return False
        target = self._working[y0:y1, x0:x1]
        new_pixels = int(np.count_nonzero(filled & ~target))
        if new_pixels:
            target |= filled
            self._selected_count += new_pixels
        return True

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        document = view.document
        layer = document.active_layer
        if layer is None:
            view.status_message.emit(
                "Quick Selection cần một layer đang chọn để lấy mẫu màu."
            )
            return True
        x = int(math.floor(image_pos.x()))
        y = int(math.floor(image_pos.y()))
        if not (0 <= x < document.width and 0 <= y < document.height):
            view.status_message.emit("Hãy nhấp bên trong canvas để chọn vùng.")
            return True
        self._origin = document.selection.copy() if document.has_selection() else None
        self._mode = selection_mode_from(event)
        self._sample = layer_sample(
            layer.pixels,
            layer.offset_x,
            layer.offset_y,
            document.width,
            document.height,
        )
        self._working = np.zeros((document.height, document.width), dtype=bool)
        self._selected_count = 0
        self._active = True
        self._last_position = QPointF(image_pos)
        self._apply_dab(view, image_pos)
        view.set_selection_preview(self._working)
        view.status_message.emit(
            "Quick Selection: kéo qua vùng cần chọn, thả chuột để hoàn tất."
        )
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        spacing = max(1.0, self.size * 0.25)
        last = self._last_position
        if last is not None:
            if math.hypot(image_pos.x() - last.x(), image_pos.y() - last.y()) < spacing:
                return True
        self._last_position = QPointF(image_pos)
        self._apply_dab(view, image_pos)
        view.set_selection_preview(self._working)
        view.status_message.emit(
            f"Quick Selection: {self._selected_count} px — thả chuột để hoàn tất."
        )
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or event.button() != Qt.MouseButton.LeftButton:
            return False
        self._apply_dab(view, image_pos)
        document = view.document
        candidate = None
        if self._working is not None and self._working.any():
            candidate = Selection.from_path(
                document.width,
                document.height,
                mask_to_path(self._working),
                feather=self.feather,
                antialias=self.antialias,
            )
        selection = combine_selection(self._origin, candidate, self._mode)
        document.commit_selection(self._origin, selection, "Quick Selection")
        view.set_selection_preview(None)
        if selection is None:
            view.status_message.emit("Vùng chọn đã bị bỏ.")
        else:
            bounds = selection.bounds()
            view.status_message.emit(
                f"Quick Selection: {bounds.width()} × {bounds.height()} px"
                " (Ctrl+Z để hoàn tác)."
            )
        self._reset(view)
        return True

    def key_press(self, view, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._active:
            view.set_selection_preview(None)
            view.document.preview_selection(self._origin)
            view.status_message.emit("Đã huỷ Quick Selection.")
            self._reset(view)
            return True
        return False

    def reset(self, view) -> None:
        view.set_selection_preview(None)
        self._reset(view)

    def _reset(self, view) -> None:
        self._origin = None
        self._active = False
        self._sample = None
        self._working = None
        self._last_position = None
        self._selected_count = 0


class CropTool(CanvasTool):
    id = "crop"
    name = "Crop"
    shortcut = "C"
    hint = "Kéo chọn vùng cần giữ. Enter để cắt ảnh, Esc để huỷ."
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self) -> None:
        self._start = QPointF()
        self._active = False

    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start = _clamp_to_document(view, image_pos)
        self._active = True
        view.set_crop_rect(QRectF(self._start, self._start))
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        current = _clamp_to_document(view, image_pos)
        delta = current - self._start
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            side = max(abs(delta.x()), abs(delta.y()))
            current = QPointF(
                self._start.x() + math.copysign(side, delta.x() or 1.0),
                self._start.y() + math.copysign(side, delta.y() or 1.0),
            )
        view.set_crop_rect(QRectF(self._start, current).normalized())
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active:
            return False
        self._active = False
        rect = view.crop_rect
        if rect is None or rect.width() < 2.0 or rect.height() < 2.0:
            view.clear_crop_rect()
            view.status_message.emit("Vùng crop quá nhỏ. Hãy kéo lại.")
        else:
            view.status_message.emit(
                f"Vùng crop {int(rect.width())} × {int(rect.height())} px — Enter để cắt, Esc để huỷ."
            )
        return True

    def key_press(self, view, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return view.apply_crop()
        if event.key() == Qt.Key.Key_Escape and view.crop_rect is not None:
            view.clear_crop_rect()
            view.status_message.emit("Đã huỷ vùng crop.")
            return True
        return False
