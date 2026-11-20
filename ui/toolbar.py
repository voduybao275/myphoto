"""Thanh công cụ bên trái và ô màu Foreground/Background."""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QSizePolicy,
    QToolBar,
    QWidget,
)

from core.color_manager import ColorManager
from compat.qt import mouse_event_position
from ui import icons
from ui.theme import current_theme

TOOL_DEFINITIONS: list[tuple[str, str, str, str]] = [
    ("move", "Move", "V", "Di chuyển layer đang chọn. Giữ Shift để khoá theo trục."),
    (
        "rect_select",
        "Rectangular Marquee",
        "M",
        "Kéo để chọn chữ nhật. Shift cộng, Alt trừ, Shift+Alt giao vùng chọn.",
    ),
    (
        "ellipse_select",
        "Elliptical Marquee",
        "E",
        "Kéo để chọn ellipse. Shift cộng, Alt trừ, Shift+Alt giao vùng chọn.",
    ),
    (
        "lasso",
        "Lasso",
        "L",
        "Kéo để vẽ đường chọn tự do. Shift cộng, Alt trừ, Esc để huỷ.",
    ),
    (
        "magic_wand",
        "Magic Wand",
        "W",
        "Nhấp để chọn vùng màu tương tự trên layer đang chọn. Shift cộng, Alt trừ.",
    ),
    (
        "quick_select",
        "Quick Selection",
        "Shift+W",
        "Kéo qua vùng cần chọn; công cụ tự lan theo màu tương tự. Shift cộng, Alt trừ.",
    ),
    ("crop", "Crop", "C", "Kéo chọn vùng cần giữ. Enter để cắt ảnh, Esc để huỷ."),
    ("text", "Text", "T", "Nhấp vào canvas để đặt layer văn bản mới."),
    (
        "shape",
        "Shape",
        "U",
        "Kéo để vẽ hình khối. Giữ Shift để tạo hình vuông/tròn, Esc để huỷ.",
    ),
    (
        "brush",
        "Brush",
        "B",
        "Kéo để vẽ bằng màu Foreground. [ / ] đổi cỡ cọ. Có thể vẽ lên layer mask. Esc để huỷ nét.",
    ),
    (
        "eraser",
        "Eraser",
        "Shift+E",
        "Kéo để tẩy pixel (giảm độ đục). [ / ] đổi cỡ cọ. Esc để huỷ nét.",
    ),
    (
        "gradient",
        "Gradient",
        "G",
        "Kéo để tô dải màu tuyến tính/hình tròn. Có thể tô lên layer mask.",
    ),
    (
        "eyedropper",
        "Eyedropper",
        "I",
        "Nhấp để lấy màu Foreground từ ảnh ghép. Alt+Click để lấy màu Background.",
    ),
    ("hand", "Hand", "H", "Di chuyển khung nhìn. Giữ Space tại bất kỳ công cụ nào."),
    ("zoom", "Zoom", "Z", "Phóng to / thu nhỏ. Alt+Click để thu nhỏ."),
]

_TOOL_HINTS = {tool_id: hint for tool_id, _, _, hint in TOOL_DEFINITIONS}


class ColorSwatches(QWidget):
    """Hai ô màu chồng nhau kiểu hộp màu quen thuộc, có nút hoán đổi."""

    def __init__(self, color_manager: ColorManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color_manager = color_manager
        self.setFixedSize(62, 66)
        self.setToolTip(
            "Foreground / Background\n"
            "Nhấp ô trước để chọn màu, nhấp ô sau để chọn màu nền, nhấp mũi tên để hoán đổi.\n"
            "X: hoán đổi màu · D: về màu mặc định · I: Eyedropper."
        )
        self._fg_rect = QRectF(6, 8, 30, 30)
        self._bg_rect = QRectF(24, 28, 30, 30)
        self._swap_rect = QRectF(40, 2, 18, 18)
        color_manager.colors_changed.connect(self.update)

    def _paint_swatch(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        theme = current_theme()
        painter.save()
        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.checker_a))
        painter.drawRect(rect)
        cell = 5
        painter.setBrush(QColor(theme.checker_b))
        rows = int(rect.height() // cell) + 1
        cols = int(rect.width() // cell) + 1
        for row in range(rows):
            for col in range(cols):
                if (row + col) % 2 == 0:
                    x = rect.x() + col * cell
                    y = rect.y() + row * cell
                    painter.drawRect(QRectF(x, y, cell, cell))
        painter.setBrush(color)
        painter.drawRect(rect)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(0, 0, 0, 110))
        painter.drawRect(rect)
        painter.setPen(QColor(255, 255, 255, 70))
        painter.drawRect(rect.adjusted(1, 1, 0, 0))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_swatch(painter, self._bg_rect, self.color_manager.background)
        self._paint_swatch(painter, self._fg_rect, self.color_manager.foreground)
        swap_pixmap = icons.pixmap("swap", 16)
        painter.drawPixmap(self._swap_rect.topLeft().toPoint(), swap_pixmap)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = mouse_event_position(event)
        if self._swap_rect.contains(position):
            self.color_manager.swap()
            return
        if self._fg_rect.contains(position):
            self._choose_color(is_foreground=True)
            return
        if self._bg_rect.contains(position):
            self._choose_color(is_foreground=False)

    def _choose_color(self, is_foreground: bool) -> None:
        current = (
            self.color_manager.foreground if is_foreground else self.color_manager.background
        )
        title = "Chọn màu Foreground" if is_foreground else "Chọn màu Background"
        color = QColorDialog.getColor(
            current,
            self,
            title,
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        if is_foreground:
            self.color_manager.set_foreground(color)
        else:
            self.color_manager.set_background(color)


class ToolBox(QToolBar):
    tool_selected = Signal(str)

    def __init__(self, color_manager: ColorManager, parent: QWidget | None = None) -> None:
        super().__init__("Tools", parent)
        self.setObjectName("ToolBox")
        self.setOrientation(Qt.Orientation.Vertical)
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(24, 24))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        self._actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for tool_id, name, shortcut, hint in TOOL_DEFINITIONS:
            action = QAction(icons.icon(tool_id), name, self)
            action.setCheckable(True)
            action.setActionGroup(group)
            # Không gắn shortcut cấp ứng dụng cho phím đơn: CanvasView xử lý
            # V/H/Z khi canvas có focus để không cướp phím khi gõ văn bản.
            action.setToolTip(f"{name} ({shortcut})\n{hint}")
            action.triggered.connect(
                lambda checked=False, current=tool_id: self.tool_selected.emit(current)
            )
            self.addAction(action)
            self._actions[tool_id] = action
        self._actions["move"].setChecked(True)

        self.addSeparator()
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.addWidget(spacer)
        self.swatches = ColorSwatches(color_manager, self)
        self.addWidget(self.swatches)

    def set_current_tool(self, tool_id: str) -> None:
        action = self._actions.get(tool_id)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def refresh_theme(self) -> None:
        for tool_id, action in self._actions.items():
            action.setIcon(icons.icon(tool_id))
        self.swatches.update()

    def tool_tip(self, tool_id: str) -> str:
        return _TOOL_HINTS.get(tool_id, "")
