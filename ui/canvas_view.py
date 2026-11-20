"""CanvasView — hiển thị tài liệu, zoom, pan và chuyển sự kiện cho công cụ."""

from __future__ import annotations

import math

import numpy as np

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPoint, QPointF, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from core.canvas import composite_layers, numpy_rgba_to_qimage
from core.document import Document
from core.layer import Layer, LayerKind
from core.text_layer import TextRun
from core.tiles import TileCache
from compat.qt import mouse_event_position, wheel_event_position
from ui.inline_text import InlineTextEditor
from tools.base import CanvasTool
from tools.brush import BrushTool, EraserTool
from tools.eyedropper import EyedropperTool
from tools.gradient import GradientTool
from tools.move import MoveTool
from tools.navigation import HandTool, ZoomTool
from tools.selection import (
    CropTool,
    EllipseSelectTool,
    LassoSelectTool,
    MagicWandTool,
    QuickSelectionTool,
    RectSelectTool,
)
from tools.shape import ShapeTool
from tools.text import TextTool
from ui.theme import current_theme

MIN_ZOOM = 0.02
MAX_ZOOM = 32.0
CHECKER_CELL = 8
PREVIEW_MAX_SIDE = 2048
TILE_ZOOM_THRESHOLD = 0.5
SELECTION_TOOL_IDS = (
    "rect_select",
    "ellipse_select",
    "lasso",
    "magic_wand",
    "quick_select",
)


class CanvasView(QWidget):
    cursor_moved = Signal(QPointF, bool)
    zoom_changed = Signal(float)
    tool_changed = Signal(str)
    status_message = Signal(str)
    crop_changed = Signal()
    text_placement_requested = Signal(QPointF)
    inline_text_finished = Signal(str, object, QPointF)
    quick_mask_changed = Signal(bool)
    color_picked = Signal(object, bool)
    color_shortcut = Signal(str)
    paint_options_changed = Signal()

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._fit_mode = True
        self._fit_on_show = True
        self._tile_cache = TileCache(document)
        self._render_mode = "tiles"
        self._space_held = False
        self._panning = False
        self._last_mouse_pos = QPointF()
        self._checker = QPixmap()
        self._crop_rect: QRectF | None = None
        self._shape_preview: QRectF | None = None
        self._ants_offset = 0
        self._selection_preview_image: QImage | None = None
        self._quick_mask = False
        self._quick_mask_image: QImage | None = None
        self._inline_editor: InlineTextEditor | None = None
        self._inline_layer: Layer | None = None
        self._inline_position = QPointF()
        self._inline_backdrop: QImage | None = None
        self._inline_finishing = False

        self._tool_id = "move"
        self._tools: dict[str, CanvasTool] = {
            "move": MoveTool(),
            "rect_select": RectSelectTool(),
            "ellipse_select": EllipseSelectTool(),
            "lasso": LassoSelectTool(),
            "magic_wand": MagicWandTool(),
            "quick_select": QuickSelectionTool(),
            "crop": CropTool(),
            "text": TextTool(),
            "shape": ShapeTool(),
            "brush": BrushTool(),
            "eraser": EraserTool(),
            "gradient": GradientTool(),
            "eyedropper": EyedropperTool(),
            "hand": HandTool(),
            "zoom": ZoomTool(),
        }

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumSize(120, 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._ants_timer = QTimer(self)
        self._ants_timer.setInterval(140)
        self._ants_timer.timeout.connect(self._advance_ants)

        self._make_checker()
        self._content_slot = self.update
        document.content_changed.connect(self._content_slot)
        document.selection_changed.connect(self._on_selection_changed)
        self._update_selection_animation()
        self._apply_cursor()

    def dispose(self) -> None:
        """Ngắt liên kết signal khi đóng tài liệu để tránh giữ widget trong bộ nhớ."""
        self._teardown_inline_text()
        self._ants_timer.stop()
        self._tile_cache.clear()
        for signal, slot in (
            (self.document.content_changed, self._content_slot),
            (self.document.selection_changed, self._on_selection_changed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._tools.clear()

    # ------------------------------------------------------------------ thuộc tính
    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def render_mode(self) -> str:
        """Cách canvas đang vẽ: ``tiles``, ``preview`` hoặc ``inline``."""
        return self._render_mode

    @property
    def tile_cache(self) -> TileCache:
        return self._tile_cache

    @property
    def tool_id(self) -> str:
        return self._tool_id

    @property
    def current_tool(self) -> CanvasTool:
        return self._tools[self._tool_id]

    @property
    def is_panning(self) -> bool:
        return self._panning

    @property
    def crop_rect(self) -> QRectF | None:
        return QRectF(self._crop_rect) if self._crop_rect is not None else None

    @property
    def shape_preview(self) -> QRectF | None:
        return QRectF(self._shape_preview) if self._shape_preview is not None else None

    def shape_options(self) -> dict[str, object]:
        """Kiểu hình hiện tại của Shape Tool (Options Bar đọc để đồng bộ)."""
        return self._tools["shape"].options()

    def set_shape_options(self, **options: object) -> None:
        """Cập nhật kiểu hình cho lần vẽ kế tiếp (Options Bar gọi)."""
        self._tools["shape"].configure(**options)
        self.update()

    def brush_options(self) -> dict[str, object]:
        return self._tools["brush"].options()

    def set_brush_options(self, **options: object) -> None:
        self._tools["brush"].configure(**options)
        self._apply_cursor()

    def eraser_options(self) -> dict[str, object]:
        return self._tools["eraser"].options()

    def set_eraser_options(self, **options: object) -> None:
        self._tools["eraser"].configure(**options)
        self._apply_cursor()

    def step_brush_size(self, direction: int) -> None:
        """Tăng/giảm cỡ cọ theo bậc giống Photoshop ([ và ])."""
        tool_id = "eraser" if self._tool_id == "eraser" else "brush"
        size = int(self._tools[tool_id].options()["size"])
        if size < 10:
            step = 1
        elif size < 100:
            step = 10
        elif size < 200:
            step = 25
        elif size < 300:
            step = 50
        else:
            step = 100
        if direction < 0 and size <= 10:
            step = 1
        new_size = size + step * (1 if direction > 0 else -1)
        self._tools[tool_id].configure(size=new_size)
        self._apply_cursor()
        self.paint_options_changed.emit()
        self.status_message.emit(f"Cỡ cọ: {self._tools[tool_id].options()['size']} px")

    def set_brush_color(self, color: tuple[int, int, int, int]) -> None:
        """Đồng bộ màu Foreground cho cả cọ và tẩy."""
        self._tools["brush"].configure(color=color)
        self._tools["eraser"].configure(color=color)

    def gradient_options(self) -> dict[str, object]:
        return self._tools["gradient"].options()

    def set_gradient_options(self, **options: object) -> None:
        self._tools["gradient"].configure(**options)
        self.update()

    def set_gradient_colors(
        self,
        foreground: tuple[int, int, int, int],
        background: tuple[int, int, int, int],
    ) -> None:
        """Đồng bộ màu Foreground/Background cho công cụ Gradient."""
        self._tools["gradient"].set_colors(foreground, background)

    def selection_options(self) -> dict[str, object]:
        """Tuỳ chọn của công cụ chọn đang hoạt động."""
        if self._tool_id not in SELECTION_TOOL_IDS:
            return {"feather": 0.0, "antialias": True}
        return self._tools[self._tool_id].options()

    def set_selection_options(self, **options: object) -> None:
        """Cập nhật feather/anti-alias cho vùng chọn kế tiếp của công cụ hiện tại."""
        if self._tool_id in SELECTION_TOOL_IDS:
            payload = {
                key: value
                for key, value in options.items()
                if key in ("feather", "antialias")
            }
            self._tools[self._tool_id].configure(**payload)
            self.update()

    def magic_wand_options(self) -> dict[str, object]:
        return self._tools["magic_wand"].options()

    def set_magic_wand_options(self, **options: object) -> None:
        self._tools["magic_wand"].configure(**options)

    def quick_select_options(self) -> dict[str, object]:
        return self._tools["quick_select"].options()

    def set_quick_select_options(self, **options: object) -> None:
        self._tools["quick_select"].configure(**options)
        self._apply_cursor()

    def set_paint_mask(self, enabled: bool) -> bool:
        """Bật/tắt vẽ lên mask cho các công cụ tô; False nếu layer chưa có mask."""
        layer = self.document.active_layer
        if enabled and (layer is None or layer.mask is None):
            return False
        self._tools["brush"].configure(paint_mask=enabled)
        self._tools["gradient"].configure(paint_mask=enabled)
        return True

    # --------------------------------------------------------------- toạ độ
    def image_rect(self) -> QRectF:
        return QRectF(
            self._pan,
            QSizeF(float(self.document.width) * self._zoom, float(self.document.height) * self._zoom),
        )

    def widget_to_image(self, position: QPointF) -> QPointF:
        return QPointF(
            (position.x() - self._pan.x()) / self._zoom,
            (position.y() - self._pan.y()) / self._zoom,
        )

    def image_to_widget(self, position: QPointF) -> QPointF:
        return QPointF(
            self._pan.x() + position.x() * self._zoom,
            self._pan.y() + position.y() * self._zoom,
        )

    # ------------------------------------------------------------------ zoom
    def set_zoom(self, value: float, anchor: QPointF | None = None) -> None:
        value = max(MIN_ZOOM, min(MAX_ZOOM, float(value)))
        if abs(value - self._zoom) < 1e-6:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        image_anchor = self.widget_to_image(anchor)
        self._zoom = value
        self._pan = anchor - QPointF(image_anchor.x() * value, image_anchor.y() * value)
        self._fit_mode = False
        self._sync_inline_geometry()
        self.update()
        self._apply_cursor()
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def zoom_actual(self) -> None:
        self.set_zoom(1.0)

    def fit_to_window(self) -> None:
        if self.width() <= 10 or self.height() <= 10:
            return
        margin = 56.0
        available_w = max(40.0, self.width() - margin * 2)
        available_h = max(40.0, self.height() - margin * 2)
        scale = min(
            available_w / max(1, self.document.width),
            available_h / max(1, self.document.height),
        )
        self._zoom = max(MIN_ZOOM, min(4.0, scale))
        self._pan = QPointF(
            (self.width() - self.document.width * self._zoom) / 2.0,
            (self.height() - self.document.height * self._zoom) / 2.0,
        )
        self._fit_mode = True
        self._fit_on_show = False
        self._sync_inline_geometry()
        self.update()
        self._apply_cursor()
        self.zoom_changed.emit(self._zoom)

    # ------------------------------------------------------------------ công cụ
    def set_tool(self, tool_id: str) -> None:
        if tool_id not in self._tools:
            raise ValueError(f"Công cụ không tồn tại: {tool_id}")
        if tool_id == self._tool_id:
            return
        self.commit_inline_text()
        if self._panning:
            self.end_pan()
        if self._tool_id == "crop":
            self.clear_crop_rect()
        if self._tool_id == "shape" and tool_id != "shape":
            self._tools["shape"].reset(self)
        if (
            self._tool_id in ("brush", "eraser", "gradient", "eyedropper")
            and tool_id != self._tool_id
        ):
            self._tools[self._tool_id].reset(self)
        if self._tool_id in ("quick_select", "lasso") and tool_id != self._tool_id:
            self._tools[self._tool_id].reset(self)
            self.set_selection_preview(None)
        self._tool_id = tool_id
        if tool_id == "crop" and self.document.has_selection():
            bounds = QRectF(self.document.selection.bounds())
            if bounds.width() >= 1.0 and bounds.height() >= 1.0:
                self.set_crop_rect(bounds)
        self._apply_cursor()
        self.tool_changed.emit(self._tool_id)

    # -------------------------------------------------------- vùng chọn / crop
    def _make_overlay_image(
        self, mask: np.ndarray, color: tuple[int, int, int], max_alpha: int
    ) -> QImage:
        array = np.asarray(mask)
        expected = (self.document.height, self.document.width)
        if array.shape != expected:
            raise ValueError(
                f"Mask phải có kích thước {expected[1]} × {expected[0]} px."
            )
        if array.dtype == bool:
            strength = array.astype(np.uint8) * 255
        else:
            strength = np.clip(array, 0, 255).astype(np.uint8)
        alpha = (
            strength.astype(np.uint16) * int(max_alpha) // 255
        ).astype(np.uint8)
        rgba = np.empty(
            (self.document.height, self.document.width, 4), dtype=np.uint8
        )
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha
        return numpy_rgba_to_qimage(rgba)

    def set_selection_preview(self, mask: np.ndarray | None) -> None:
        """Lớp phủ tạm trong lúc kéo Quick Selection (chưa ghi history)."""
        if mask is None:
            if self._selection_preview_image is None:
                return
            self._selection_preview_image = None
            self.update()
            return
        self._selection_preview_image = self._make_overlay_image(
            mask, (70, 150, 245), 110
        )
        self.update()

    @property
    def quick_mask(self) -> bool:
        return self._quick_mask

    def set_quick_mask(self, enabled: bool) -> bool:
        """Bật/tắt lớp phủ đỏ cho phần chưa nằm trong vùng chọn."""
        enabled = bool(enabled)
        if enabled and not self.document.has_selection():
            enabled = False
        if enabled == self._quick_mask:
            if enabled:
                self._rebuild_quick_mask_image()
            return self._quick_mask
        self._quick_mask = enabled
        if enabled:
            self._rebuild_quick_mask_image()
        else:
            self._quick_mask_image = None
        self._update_selection_animation()
        self.update()
        self.quick_mask_changed.emit(enabled)
        return enabled

    def toggle_quick_mask(self) -> bool:
        if not self.document.has_selection():
            self.status_message.emit(
                "Hãy tạo vùng chọn trước khi bật Quick Mask (phím Q)."
            )
            if self._quick_mask:
                self.set_quick_mask(False)
            return False
        return self.set_quick_mask(not self._quick_mask)

    def _rebuild_quick_mask_image(self) -> None:
        selection = self.document.selection
        if selection is None or selection.is_empty:
            self._quick_mask_image = None
            return
        mask = selection.mask()
        self._quick_mask_image = self._make_overlay_image(
            (255 - mask.astype(np.uint16)).astype(np.uint8),
            (210, 45, 45),
            150,
        )

    def _on_selection_changed(self) -> None:
        if self._quick_mask:
            if not self.document.has_selection():
                self.set_quick_mask(False)
            else:
                self._rebuild_quick_mask_image()
        self._update_selection_animation()
        self.update()

    def _update_selection_animation(self) -> None:
        if self.document.has_selection() and not self._quick_mask:
            if not self._ants_timer.isActive():
                self._ants_timer.start()
        else:
            self._ants_timer.stop()
        self._ants_offset = 0

    def _advance_ants(self) -> None:
        if not self.document.has_selection() or self._quick_mask:
            self._ants_timer.stop()
            return
        self._ants_offset = (self._ants_offset + 1) % 8
        self.update()

    def set_crop_rect(self, rect: QRectF | None) -> None:
        if rect is None:
            self.clear_crop_rect()
            return
        document_rect = QRectF(0.0, 0.0, float(self.document.width), float(self.document.height))
        clipped = rect.normalized().intersected(document_rect)
        if clipped.width() < 1.0 or clipped.height() < 1.0:
            clipped = QRectF()
        self._crop_rect = clipped
        self.crop_changed.emit()
        self.update()

    def clear_crop_rect(self) -> None:
        if self._crop_rect is None:
            return
        self._crop_rect = None
        self.crop_changed.emit()
        self.update()

    def set_shape_preview(self, rect: QRectF | None) -> None:
        """Cập nhật khung xem trước khi kéo vẽ hình (toạ độ ảnh)."""
        if rect is None:
            if self._shape_preview is None:
                return
            self._shape_preview = None
            self.update()
            return
        document_rect = QRectF(
            0.0, 0.0, float(self.document.width), float(self.document.height)
        )
        clipped = rect.normalized().intersected(document_rect)
        if clipped.width() < 1.0 or clipped.height() < 1.0:
            clipped = None
        self._shape_preview = clipped
        self.update()

    def apply_crop(self) -> bool:
        rect = self._crop_rect
        if rect is None or rect.width() < 1.0 or rect.height() < 1.0:
            return False
        x = max(0, math.floor(rect.left()))
        y = max(0, math.floor(rect.top()))
        right = min(self.document.width, math.ceil(rect.right()))
        bottom = min(self.document.height, math.ceil(rect.bottom()))
        try:
            changed = self.document.crop(x, y, right - x, bottom - y)
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return False
        self.clear_crop_rect()
        if changed:
            self._fit_mode = True
            self.fit_to_window()
            self.status_message.emit("Đã crop ảnh (Ctrl+Z để hoàn tác).")
        return changed

    # ------------------------------------------------------- gõ chữ trên canvas
    @property
    def inline_editor(self) -> InlineTextEditor | None:
        return self._inline_editor

    def begin_inline_text(self, position: QPointF, default_run: TextRun) -> bool:
        """Mở ô soạn chữ tại ``position``; sửa layer chữ nếu nhấp trúng layer đó."""
        if self._inline_editor is not None:
            self.commit_inline_text()
        if not isinstance(default_run, TextRun):
            raise TypeError("Định dạng mặc định phải là TextRun.")
        layer = self._text_layer_at(position)
        if layer is not None and layer.mask is not None:
            self.status_message.emit(
                "Layer văn bản đang có mask — hãy áp hoặc xoá mask trước khi sửa chữ."
            )
            return False
        base = layer.text if layer is not None else None
        origin = (
            QPointF(float(layer.offset_x), float(layer.offset_y))
            if layer is not None
            else QPointF(position)
        )
        editor = InlineTextEditor(base, default_run, self._zoom, self)
        editor.commit_requested.connect(self.commit_inline_text)
        editor.cancel_requested.connect(self.cancel_inline_text)
        editor.content_size_changed.connect(self._sync_inline_geometry)

        self._inline_editor = editor
        self._inline_layer = layer
        self._inline_position = QPointF(origin)
        self._inline_backdrop = None
        if layer is not None:
            others = [item for item in self.document.layers if item is not layer]
            pixels = composite_layers(others, self.document.width, self.document.height)
            self._inline_backdrop = numpy_rgba_to_qimage(pixels)
        self._sync_inline_geometry()
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()
        if layer is None:
            self.status_message.emit(
                "Gõ chữ ngay trên canvas — Ctrl+Enter để xong, Esc để huỷ."
            )
        else:
            self.status_message.emit(
                "Đang sửa layer văn bản trên canvas — Ctrl+Enter để xong, Esc để huỷ."
            )
        return True

    def commit_inline_text(self) -> None:
        self._end_inline_text(commit=True)

    def cancel_inline_text(self) -> None:
        self._end_inline_text(commit=False)

    def _end_inline_text(self, *, commit: bool) -> None:
        editor = self._inline_editor
        if editor is None or self._inline_finishing:
            return
        self._inline_finishing = True
        try:
            properties = None
            if commit:
                try:
                    properties = editor.text_properties()
                except ValueError as exc:
                    self.status_message.emit(str(exc))
            layer = self._inline_layer
            position = QPointF(self._inline_position)
            self._teardown_inline_text()
        finally:
            self._inline_finishing = False
        if commit and properties is not None:
            self.inline_text_finished.emit(
                layer.id if layer is not None else "", properties, position
            )
        elif commit:
            self.status_message.emit("Ô gõ chữ trống — đã đóng, chưa tạo văn bản.")
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _teardown_inline_text(self) -> None:
        editor = self._inline_editor
        self._inline_editor = None
        self._inline_layer = None
        self._inline_backdrop = None
        if editor is not None:
            editor.close_editor()
            editor.blockSignals(True)
            editor.hide()
            editor.setParent(None)
            editor.deleteLater()
        self.update()

    def _sync_inline_geometry(self) -> None:
        editor = self._inline_editor
        if editor is None:
            return
        if abs(editor.zoom - self._zoom) > 1e-9:
            editor.set_zoom(self._zoom)
        origin = self.image_to_widget(self._inline_position)
        editor.move(round(origin.x()), round(origin.y()))
        self.update()

    def _text_layer_at(self, position: QPointF) -> Layer | None:
        for layer in reversed(self.document.layers.layers):
            if layer.kind != LayerKind.TEXT or not layer.visible or layer.text is None:
                continue
            x0, y0, x1, y1 = layer.bounds()
            if x0 <= position.x() < x1 and y0 <= position.y() < y1:
                return layer
        return None

    # ------------------------------------------------------------------ pan
    def begin_pan(self, position: QPointF) -> None:
        self._panning = True
        self._last_mouse_pos = QPointF(position)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def update_pan(self, position: QPointF) -> None:
        if not self._panning:
            return
        delta = position - self._last_mouse_pos
        self._last_mouse_pos = QPointF(position)
        self._pan = self._pan + delta
        self._fit_mode = False
        self._sync_inline_geometry()
        self.update()

    def end_pan(self) -> None:
        self._panning = False
        self._apply_cursor()

    # ------------------------------------------------------------------ theme
    def _make_checker(self) -> None:
        theme = current_theme()
        pixmap = QPixmap(CHECKER_CELL * 2, CHECKER_CELL * 2)
        pixmap.fill(QColor(theme.checker_a))
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, CHECKER_CELL, CHECKER_CELL, QColor(theme.checker_b))
        painter.fillRect(
            CHECKER_CELL, CHECKER_CELL, CHECKER_CELL, CHECKER_CELL, QColor(theme.checker_b)
        )
        painter.end()
        self._checker = pixmap

    def refresh_theme(self) -> None:
        self._make_checker()
        self._apply_cursor()
        self.update()

    # ------------------------------------------------------------------ vẽ
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        theme = current_theme()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.canvas_bg))

        image_rect = self.image_rect()
        if image_rect.width() < 1.0 or image_rect.height() < 1.0:
            painter.end()
            return

        # Đổ bóng nhẹ để tách canvas khỏi nền.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(image_rect.translated(0, 2.5).adjusted(-1, -1, 1, 1), 2, 2)

        painter.setBrushOrigin(image_rect.topLeft().toPoint())
        painter.fillRect(image_rect, QBrush(self._checker))
        painter.setBrushOrigin(QPoint(0, 0))

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 1.0)
        painter.setClipRect(image_rect)
        self._paint_document(painter, image_rect)
        self._draw_selection_preview(painter, image_rect)
        if self._quick_mask:
            self._draw_quick_mask(painter, image_rect)
        else:
            self._draw_selection(painter, image_rect)
        self._draw_crop_overlay(painter, image_rect)
        self._draw_shape_preview(painter, image_rect)
        self._draw_inline_outline(painter)
        painter.setClipping(False)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(theme.border))
        painter.drawRect(image_rect.adjusted(0, 0, -1, -1))
        painter.end()

    def _visible_image_rect(self) -> QRectF:
        """Phần tài liệu đang thực sự nằm trong khung nhìn (toạ độ ảnh)."""
        clip = QRectF(self.rect()).intersected(self.image_rect())
        if clip.width() < 1.0 or clip.height() < 1.0:
            return QRectF()
        top_left = self.widget_to_image(clip.topLeft())
        bottom_right = self.widget_to_image(clip.bottomRight())
        visible = QRectF(top_left, bottom_right).normalized()
        bounds = QRectF(
            0.0, 0.0, float(self.document.width), float(self.document.height)
        )
        return visible.intersected(bounds)

    def _paint_document(self, painter: QPainter, image_rect: QRectF) -> None:
        if self._inline_backdrop is not None:
            self._render_mode = "inline"
            painter.drawImage(image_rect, self._inline_backdrop)
            return

        visible = self._visible_image_rect()
        if visible.width() < 1.0 or visible.height() < 1.0:
            return

        tiles = self._tile_cache.tiles_for_rect(
            visible.left(), visible.top(), visible.right(), visible.bottom()
        )
        if self._zoom < TILE_ZOOM_THRESHOLD or len(tiles) > self._tile_cache.max_tiles:
            side = int(math.ceil(max(image_rect.width(), image_rect.height()) * 1.1))
            side = max(64, min(PREVIEW_MAX_SIDE, side))
            side = min(side, max(self.document.width, self.document.height))
            painter.drawImage(image_rect, self.document.preview_image(side))
            self._render_mode = "preview"
            return

        self._render_mode = "tiles"
        size = self._tile_cache.tile_size
        zoom = self._zoom
        for tx, ty in tiles:
            image = self._tile_cache.tile(tx, ty)
            width = image.width()
            height = image.height()
            target = QRectF(
                self._pan.x() + tx * size * zoom,
                self._pan.y() + ty * size * zoom,
                width * zoom,
                height * zoom,
            )
            painter.drawImage(target, image, QRectF(0.0, 0.0, float(width), float(height)))

    def _draw_inline_outline(self, painter: QPainter) -> None:
        editor = self._inline_editor
        if editor is None or not editor.isVisible():
            return
        rect = QRectF(editor.geometry()).adjusted(0.5, 0.5, -0.5, -0.5)
        pen = QPen(QColor(current_theme().accent))
        pen.setCosmetic(True)
        pen.setWidthF(1.2)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.restore()

    def _draw_selection(self, painter: QPainter, image_rect: QRectF) -> None:
        selection = self.document.selection
        if selection is None or selection.is_empty:
            return
        transform = QTransform()
        transform.translate(self._pan.x(), self._pan.y())
        transform.scale(self._zoom, self._zoom)
        path = transform.map(selection.path)

        painter.save()
        painter.setClipRect(image_rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        dark_pen = QPen(QColor(0, 0, 0, 220))
        dark_pen.setCosmetic(True)
        dark_pen.setWidthF(1.0)
        painter.setPen(dark_pen)
        painter.drawPath(path)

        light_pen = QPen(QColor(255, 255, 255, 235))
        light_pen.setCosmetic(True)
        light_pen.setWidthF(1.0)
        light_pen.setStyle(Qt.PenStyle.DashLine)
        light_pen.setDashPattern([4.0, 4.0])
        light_pen.setDashOffset(-float(self._ants_offset))
        painter.setPen(light_pen)
        painter.drawPath(path)
        painter.restore()

    def _draw_selection_preview(self, painter: QPainter, image_rect: QRectF) -> None:
        image = self._selection_preview_image
        if image is None or image.isNull():
            return
        painter.save()
        painter.setClipRect(image_rect)
        painter.drawImage(image_rect, image)
        painter.restore()

    def _draw_quick_mask(self, painter: QPainter, image_rect: QRectF) -> None:
        image = self._quick_mask_image
        if image is None or image.isNull():
            return
        painter.save()
        painter.setClipRect(image_rect)
        painter.drawImage(image_rect, image)
        painter.restore()

    def _draw_crop_overlay(self, painter: QPainter, image_rect: QRectF) -> None:
        rect = self._crop_rect
        if rect is None or rect.width() < 1.0 or rect.height() < 1.0:
            return
        widget_rect = QRectF(
            self.image_to_widget(rect.topLeft()),
            QSizeF(rect.width() * self._zoom, rect.height() * self._zoom),
        ).intersected(image_rect)
        if widget_rect.width() < 1.0 or widget_rect.height() < 1.0:
            return

        shade = QColor(0, 0, 0, 130)
        painter.save()
        painter.setClipRect(image_rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shade)
        if widget_rect.top() > image_rect.top():
            painter.drawRect(
                QRectF(
                    image_rect.left(),
                    image_rect.top(),
                    image_rect.width(),
                    widget_rect.top() - image_rect.top(),
                )
            )
        if widget_rect.bottom() < image_rect.bottom():
            painter.drawRect(
                QRectF(
                    image_rect.left(),
                    widget_rect.bottom(),
                    image_rect.width(),
                    image_rect.bottom() - widget_rect.bottom(),
                )
            )
        if widget_rect.left() > image_rect.left():
            painter.drawRect(
                QRectF(
                    image_rect.left(),
                    widget_rect.top(),
                    widget_rect.left() - image_rect.left(),
                    widget_rect.height(),
                )
            )
        if widget_rect.right() < image_rect.right():
            painter.drawRect(
                QRectF(
                    widget_rect.right(),
                    widget_rect.top(),
                    image_rect.right() - widget_rect.right(),
                    widget_rect.height(),
                )
            )
        painter.restore()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        border_pen = QPen(QColor(255, 255, 255, 235))
        border_pen.setCosmetic(True)
        border_pen.setWidthF(1.0)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(widget_rect)

        grid_pen = QPen(QColor(255, 255, 255, 110))
        grid_pen.setCosmetic(True)
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        for step in (1, 2):
            x = widget_rect.left() + widget_rect.width() * step / 3.0
            painter.drawLine(QPointF(x, widget_rect.top()), QPointF(x, widget_rect.bottom()))
            y = widget_rect.top() + widget_rect.height() * step / 3.0
            painter.drawLine(QPointF(widget_rect.left(), y), QPointF(widget_rect.right(), y))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 235))
        handle = 6.0
        half = handle / 2.0
        for corner in (
            widget_rect.topLeft(),
            widget_rect.topRight(),
            widget_rect.bottomLeft(),
            widget_rect.bottomRight(),
        ):
            painter.drawRect(QRectF(corner.x() - half, corner.y() - half, handle, handle))
        painter.restore()

    def _draw_shape_preview(self, painter: QPainter, image_rect: QRectF) -> None:
        rect = self._shape_preview
        if rect is None or rect.width() < 1.0 or rect.height() < 1.0:
            return
        widget_rect = QRectF(
            self.image_to_widget(rect.topLeft()),
            QSizeF(rect.width() * self._zoom, rect.height() * self._zoom),
        ).intersected(image_rect)
        if widget_rect.width() < 1.0 or widget_rect.height() < 1.0:
            return

        tool = self._tools["shape"]
        path = QPainterPath()
        if tool.kind == "ellipse":
            path.addEllipse(widget_rect)
        elif tool.kind == "rounded_rectangle":
            radius = min(
                tool.corner_radius * self._zoom,
                widget_rect.width() / 2.0,
                widget_rect.height() / 2.0,
            )
            path.addRoundedRect(widget_rect, radius, radius)
        else:
            path.addRect(widget_rect)

        painter.save()
        painter.setClipRect(image_rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if tool.fill_color is not None:
            fill = QColor(*tool.fill_color)
            fill.setAlpha(min(fill.alpha(), 140))
            painter.setBrush(fill)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        outline = QPen(QColor(255, 255, 255, 235))
        outline.setCosmetic(True)
        outline.setWidthF(1.2)
        outline.setStyle(Qt.PenStyle.DashLine)
        outline.setDashPattern([4.0, 4.0])
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(outline)
        painter.drawPath(path)
        painter.restore()

    # ------------------------------------------------------------- sự kiện chuột
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._inline_editor is not None and event.button() == Qt.MouseButton.LeftButton:
            self.commit_inline_text()
            event.accept()
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        position = mouse_event_position(event)
        start_pan = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_held
        )
        if start_pan:
            self.begin_pan(position)
            event.accept()
            return
        image_pos = self.widget_to_image(position)
        self.current_tool.mouse_press(self, event, image_pos)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        position = mouse_event_position(event)
        image_pos = self.widget_to_image(position)
        inside = self.image_rect().contains(position)
        self.cursor_moved.emit(image_pos, inside)

        if self._panning:
            self.update_pan(position)
            event.accept()
            return
        self.current_tool.mouse_move(self, event, image_pos)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        position = mouse_event_position(event)
        if self._panning and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        ):
            self.end_pan()
            event.accept()
            return
        self.current_tool.mouse_release(self, event, self.widget_to_image(position))
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.cursor_moved.emit(QPointF(-1.0, -1.0), False)
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            event.ignore()
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._pan = self._pan + QPointF(delta * 0.45, 0.0)
            self._fit_mode = False
            self.update()
        else:
            self.set_zoom(self._zoom * (1.0018**delta), wheel_event_position(event))
        event.accept()

    # ------------------------------------------------------------- sự kiện phím
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self._apply_cursor()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._panning:
            self.end_pan()
            event.accept()
            return
        if self.current_tool.key_press(self, event):
            event.accept()
            return
        if (
            event.key() == Qt.Key.Key_E
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
        ):
            self.set_tool("eraser")
            event.accept()
            return
        if (
            event.key() == Qt.Key.Key_W
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
        ):
            self.set_tool("quick_select")
            event.accept()
            return
        if (
            event.key() == Qt.Key.Key_Q
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.toggle_quick_mask()
            event.accept()
            return
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_X:
                self.color_shortcut.emit("swap")
                event.accept()
                return
            if event.key() == Qt.Key.Key_D:
                self.color_shortcut.emit("reset")
                event.accept()
                return
            if event.key() in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight):
                if self._tool_id in ("brush", "eraser"):
                    self.step_brush_size(1 if event.key() == Qt.Key.Key_BracketRight else -1)
                    event.accept()
                    return
            shortcut_map = {
                Qt.Key.Key_V: "move",
                Qt.Key.Key_M: "rect_select",
                Qt.Key.Key_E: "ellipse_select",
                Qt.Key.Key_L: "lasso",
                Qt.Key.Key_W: "magic_wand",
                Qt.Key.Key_C: "crop",
                Qt.Key.Key_T: "text",
                Qt.Key.Key_U: "shape",
                Qt.Key.Key_B: "brush",
                Qt.Key.Key_G: "gradient",
                Qt.Key.Key_I: "eyedropper",
                Qt.Key.Key_H: "hand",
                Qt.Key.Key_Z: "zoom",
            }
            tool_id = shortcut_map.get(event.key())
            if tool_id is not None:
                self.set_tool(tool_id)
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self._apply_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _apply_cursor(self) -> None:
        if self._panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._space_held:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif hasattr(self.current_tool, "cursor_for"):
            self.setCursor(self.current_tool.cursor_for(self))
        else:
            self.setCursor(self.current_tool.cursor)

    # --------------------------------------------------------- vòng đời widget
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._fit_on_show:
            self._fit_on_show = False
            QTimer.singleShot(0, self.fit_to_window)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_to_window()
        else:
            self._sync_inline_geometry()
