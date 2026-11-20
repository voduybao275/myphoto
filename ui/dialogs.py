"""Hộp thoại tạo tài liệu mới."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QColorDialog,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config.settings import IMAGE_OPEN_FILTER
from core import filters
from core.batch import (
    BATCH_STEP_LABELS,
    BATCH_STEP_TYPES,
    DEFAULT_SUFFIX,
    MAX_BATCH_FILES,
    OUTPUT_FORMAT_LABELS,
    OUTPUT_FORMATS,
    BatchAction,
    BatchError,
    BatchRunner,
    BatchStep,
)
from core.presets import PresetError, PresetStore
from core.adjustment_layer import (
    ADJUSTMENT_LABELS,
    MAX_CURVE_POINTS,
    MAX_GAMMA,
    MIN_GAMMA,
    AdjustmentProperties,
    apply_adjustment_rgba,
    compute_auto_levels,
)
from core.canvas import downsample_mask, downsample_rgba, numpy_rgba_to_qimage
from core.document import Document, rotated_dimensions
from core.fill_layer import (
    FILL_LABELS,
    FILL_TYPES,
    GRADIENT_LABELS,
    GRADIENT_TYPES,
    FillProperties,
    render_fill,
)
from core.histogram import compute_histogram
from core.selection import MAX_FEATHER_RADIUS
from core.shape_layer import (
    MAX_CORNER_RADIUS,
    MAX_SHAPE_SIZE,
    MAX_STROKE_WIDTH,
    SHAPE_LABELS,
    ShapeProperties,
    render_shape,
)
from core.smart_object import (
    MAX_SCALE,
    MIN_SCALE,
    SmartObjectProperties,
    render_smart_object,
)
from core.text_layer import (
    ALIGNMENT_LABELS,
    MAX_LETTER_SPACING,
    MAX_LINE_SPACING,
    MAX_PATH_BEND,
    MAX_WARP_BEND,
    MIN_LETTER_SPACING,
    MIN_LINE_SPACING,
    MIN_PATH_BEND,
    MIN_WARP_BEND,
    PATH_LABELS,
    PATH_STYLES,
    WARP_LABELS,
    WARP_STYLES,
    TextProperties,
    TextRun,
    format_kerning_pairs,
    parse_kerning_pairs,
    render_text,
    text_size,
)
from ui.formatting import format_memory
from ui.text_format import format_from_run, run_from_format
from formats.import_manager import SUPPORTED_IMAGE_EXTENSIONS

PRESETS: list[tuple[str, tuple[int, int] | None]] = [
    ("Tùy chỉnh", None),
    ("Full HD — 1920 × 1080", (1920, 1080)),
    ("4K UHD — 3840 × 2160", (3840, 2160)),
    ("Ảnh vuông — 1080 × 1080", (1080, 1080)),
    ("Story dọc — 1080 × 1920", (1080, 1920)),
    ("A4 @ 300 ppi — 2480 × 3508", (2480, 3508)),
    ("Poster A3 @ 300 ppi — 3508 × 4961", (3508, 4961)),
]

BACKGROUNDS = [
    ("Trắng", "white"),
    ("Trong suốt", "transparent"),
    ("Đen", "black"),
    ("Màu tùy chọn", "custom"),
]

CURVE_CHANNEL_SPECS = (
    ("rgb", "RGB (tổng hợp)", None),
    ("red", "Đỏ", "#e06c75"),
    ("green", "Xanh lá", "#7ec699"),
    ("blue", "Xanh dương", "#79b8ff"),
)


class NewDocumentDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, suggested_name: str = "Untitled-1") -> None:
        super().__init__(parent)
        self.setWindowTitle("Tạo tài liệu mới")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._custom_color = QColor("#3b6ea5")
        self._applying_preset = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("TẠO TÀI LIỆU MỚI")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        self.name_edit = QLabel(suggested_name)
        self.name_edit.setObjectName("PropValue")
        form.addRow("Tên tài liệu", self.name_edit)

        self.preset_combo = QComboBox()
        for label, _ in PRESETS:
            self.preset_combo.addItem(label)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        form.addRow("Kích thước sẵn có", self.preset_combo)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 30000)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("×"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 30000)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        size_row.addWidget(self.height_spin)
        size_row.addStretch(1)
        form.addRow("Kích thước", size_row)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(1, 1200)
        self.dpi_spin.setValue(72)
        self.dpi_spin.setSuffix(" ppi")
        form.addRow("Độ phân giải", self.dpi_spin)

        background_row = QHBoxLayout()
        background_row.setSpacing(8)
        self.background_combo = QComboBox()
        for label, value in BACKGROUNDS:
            self.background_combo.addItem(label, value)
        self.background_combo.currentIndexChanged.connect(self._update_background_button)
        background_row.addWidget(self.background_combo, 1)
        self.color_button = QPushButton()
        self.color_button.setFixedSize(42, 26)
        self.color_button.setToolTip("Chọn màu nền tùy chỉnh")
        self.color_button.clicked.connect(self._choose_custom_color)
        background_row.addWidget(self.color_button)
        form.addRow("Nền ban đầu", background_row)

        layout.addLayout(form)

        self.memory_label = QLabel()
        self.memory_label.setObjectName("OptionsHint")
        layout.addWidget(self.memory_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Tạo tài liệu")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.width_spin.valueChanged.connect(self._update_memory_label)
        self.height_spin.valueChanged.connect(self._update_memory_label)
        self._update_background_button()
        self._update_memory_label()

    # ------------------------------------------------------------------ dữ liệu
    @property
    def document_width(self) -> int:
        return self.width_spin.value()

    @property
    def document_height(self) -> int:
        return self.height_spin.value()

    @property
    def resolution(self) -> float:
        return float(self.dpi_spin.value())

    @property
    def document_name(self) -> str:
        return self.name_edit.text().strip() or "Untitled"

    def background_rgba(self) -> tuple[int, int, int, int] | None:
        mode = self.background_combo.currentData()
        if mode == "transparent":
            return None
        if mode == "black":
            return (0, 0, 0, 255)
        if mode == "custom":
            color = self._custom_color
            return (color.red(), color.green(), color.blue(), 255)
        return (255, 255, 255, 255)

    # ------------------------------------------------------------------ helper
    def _apply_preset(self, index: int) -> None:
        dimensions = PRESETS[index][1]
        if dimensions is None:
            return
        self._applying_preset = True
        try:
            self.width_spin.setValue(dimensions[0])
            self.height_spin.setValue(dimensions[1])
        finally:
            self._applying_preset = False

    def _update_memory_label(self) -> None:
        pixels = self.document_width * self.document_height
        estimate = pixels * 4
        self.memory_label.setText(
            f"{self.document_width} × {self.document_height} px · "
            f"ước tính {format_memory(estimate)} cho một layer RGBA"
        )
        if pixels > Document.MAX_PIXELS:
            self.memory_label.setText("Kích thước vượt giới hạn an toàn của ứng dụng.")

    def _update_background_button(self) -> None:
        mode = self.background_combo.currentData()
        color = (
            self._custom_color
            if mode == "custom"
            else QColor("#ffffff")
            if mode == "white"
            else QColor("#000000")
            if mode == "black"
            else QColor("#8a8f98")
        )
        self.color_button.setEnabled(mode == "custom")
        self.color_button.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #555a63; border-radius: 4px;"
        )

    def _choose_custom_color(self) -> None:
        color = QColorDialog.getColor(self._custom_color, self, "Chọn màu nền")
        if color.isValid():
            self._custom_color = color
            self._update_background_button()

    def accept(self) -> None:
        pixels = self.document_width * self.document_height
        if pixels > Document.MAX_PIXELS:
            QMessageBox.warning(
                self,
                "Kích thước quá lớn",
                f"Tài liệu vượt giới hạn {Document.MAX_PIXELS // 1_000_000} megapixel.\n"
                "Hãy giảm kích thước.",
            )
            return
        if pixels > 80_000_000:
            answer = QMessageBox.question(
                self,
                "Tài liệu lớn",
                f"Tài liệu có {pixels / 1_000_000:.0f} megapixel, có thể dùng nhiều RAM.\n"
                "Bạn vẫn muốn tạo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()


ANCHOR_GRID: list[list[str]] = [
    ["top_left", "top_center", "top_right"],
    ["middle_left", "center", "middle_right"],
    ["bottom_left", "bottom_center", "bottom_right"],
]

RESAMPLE_OPTIONS: list[tuple[str, str]] = [
    ("Nearest Neighbor (giữ điểm ảnh)", "nearest"),
    ("Bilinear", "bilinear"),
    ("Bicubic (khuyến nghị)", "bicubic"),
    ("Lanczos", "lanczos"),
]


class AnchorPicker(QWidget):
    """Lưới 3×3 chọn điểm neo khi đổi Canvas Size."""

    changed = Signal(str)

    def __init__(self, selected: str = "center", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        valid = {anchor for row in ANCHOR_GRID for anchor in row}
        self._selected = selected if selected in valid else "center"
        self.setFixedSize(96, 96)
        self.setToolTip("Chọn vị trí neo của nội dung khi đổi kích thước canvas.")

    @property
    def anchor(self) -> str:
        return self._selected

    def set_anchor(self, anchor: str) -> None:
        valid = {value for row in ANCHOR_GRID for value in row}
        if anchor in valid:
            self._selected = anchor
            self.update()
            self.changed.emit(anchor)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.palette().base())
        cell = 30.0
        gap = 3.0
        for row, anchors in enumerate(ANCHOR_GRID):
            for column, anchor in enumerate(anchors):
                rect = QRectF(
                    2.0 + column * (cell + gap),
                    2.0 + row * (cell + gap),
                    cell,
                    cell,
                )
                if anchor == self._selected:
                    painter.setBrush(self.palette().highlight())
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(rect, 3.0, 3.0)
                else:
                    painter.setBrush(self.palette().alternateBase())
                    painter.setPen(QPen(self.palette().mid().color(), 1.0))
                    painter.drawRoundedRect(rect, 3.0, 3.0)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        from compat.qt import mouse_event_position

        position = mouse_event_position(event)
        cell = 30.0
        gap = 3.0
        column = int((position.x() - 2.0) // (cell + gap))
        row = int((position.y() - 2.0) // (cell + gap))
        if 0 <= row < 3 and 0 <= column < 3:
            self.set_anchor(ANCHOR_GRID[row][column])


class ImageSizeDialog(QDialog):
    """Image Size: đổi số pixel của toàn bộ tài liệu và các layer."""

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Image Size")
        self.setModal(True)
        self.setMinimumWidth(470)
        self._document = document
        self._aspect = document.width / document.height
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("IMAGE SIZE")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        current = QLabel(f"{document.width} × {document.height} px")
        current.setObjectName("PropValue")
        form.addRow("Kích thước hiện tại", current)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, Document.MAX_DIMENSION)
        self.width_spin.setValue(document.width)
        self.width_spin.setSuffix(" px")
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("×"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, Document.MAX_DIMENSION)
        self.height_spin.setValue(document.height)
        self.height_spin.setSuffix(" px")
        size_row.addWidget(self.height_spin)
        size_row.addStretch(1)
        form.addRow("Kích thước mới", size_row)

        self.lock_aspect = QCheckBox("Giữ tỉ lệ khung hình")
        self.lock_aspect.setChecked(True)
        form.addRow("", self.lock_aspect)

        self.method_combo = QComboBox()
        for label, value in RESAMPLE_OPTIONS:
            self.method_combo.addItem(label, value)
        self.method_combo.setCurrentIndex(2)
        form.addRow("Phương pháp resample", self.method_combo)

        layout.addLayout(form)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Resize")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.width_spin.valueChanged.connect(self._on_width_changed)
        self.height_spin.valueChanged.connect(self._on_height_changed)
        self.method_combo.currentIndexChanged.connect(self._update_info)
        self._update_info()

    @property
    def image_width(self) -> int:
        return self.width_spin.value()

    @property
    def image_height(self) -> int:
        return self.height_spin.value()

    @property
    def method(self) -> str:
        return str(self.method_combo.currentData())

    def _on_width_changed(self, value: int) -> None:
        if self._syncing:
            return
        if self.lock_aspect.isChecked():
            self._syncing = True
            try:
                self.height_spin.setValue(max(1, int(round(value / self._aspect))))
            finally:
                self._syncing = False
        self._update_info()

    def _on_height_changed(self, value: int) -> None:
        if self._syncing:
            return
        if self.lock_aspect.isChecked():
            self._syncing = True
            try:
                self.width_spin.setValue(max(1, int(round(value * self._aspect))))
            finally:
                self._syncing = False
        self._update_info()

    def _update_info(self) -> None:
        width = self.image_width
        height = self.image_height
        pixels = width * height
        layer_count = max(1, len(self._document.layers))
        estimate = pixels * 4 * layer_count
        scale_x = width / self._document.width * 100.0
        scale_y = height / self._document.height * 100.0
        self.info_label.setText(
            f"Tỉ lệ {scale_x:.1f}% × {scale_y:.1f}% · {layer_count} layer · "
            f"ước tính {format_memory(estimate)} (chưa gồm dữ liệu Undo)"
        )
        if pixels > Document.MAX_PIXELS:
            self.info_label.setText("Kích thước vượt giới hạn an toàn của ứng dụng.")

    def accept(self) -> None:
        pixels = self.image_width * self.image_height
        if pixels > Document.MAX_PIXELS:
            QMessageBox.warning(
                self,
                "Kích thước quá lớn",
                f"Ảnh vượt giới hạn {Document.MAX_PIXELS // 1_000_000} megapixel.\n"
                "Hãy giảm kích thước.",
            )
            return
        if pixels > 80_000_000:
            answer = QMessageBox.question(
                self,
                "Ảnh lớn",
                f"Ảnh mới có {pixels / 1_000_000:.0f} megapixel và có thể dùng nhiều RAM.\n"
                "Bạn vẫn muốn tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()


class CanvasSizeDialog(QDialog):
    """Canvas Size: đổi khung canvas và giữ nguyên dữ liệu pixel của layer."""

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Canvas Size")
        self.setModal(True)
        self.setMinimumWidth(470)
        self._document = document

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("CANVAS SIZE")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        current = QLabel(f"{document.width} × {document.height} px")
        current.setObjectName("PropValue")
        form.addRow("Canvas hiện tại", current)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, Document.MAX_DIMENSION)
        self.width_spin.setValue(document.width)
        self.width_spin.setSuffix(" px")
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("×"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, Document.MAX_DIMENSION)
        self.height_spin.setValue(document.height)
        self.height_spin.setSuffix(" px")
        size_row.addWidget(self.height_spin)
        size_row.addStretch(1)
        form.addRow("Canvas mới", size_row)

        anchor_row = QHBoxLayout()
        anchor_row.setSpacing(12)
        self.anchor_picker = AnchorPicker("center", self)
        anchor_row.addWidget(self.anchor_picker)
        anchor_hint = QLabel(
            "Chọn điểm neo để quyết định phần nội dung được giữ lại\n"
            "khi canvas to ra hoặc thu nhỏ.",
            self,
        )
        anchor_hint.setObjectName("OptionsHint")
        anchor_row.addWidget(anchor_hint, 1)
        form.addRow("Vị trí neo", anchor_row)

        layout.addLayout(form)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.width_spin.valueChanged.connect(self._update_info)
        self.height_spin.valueChanged.connect(self._update_info)
        self._update_info()

    @property
    def canvas_width(self) -> int:
        return self.width_spin.value()

    @property
    def canvas_height(self) -> int:
        return self.height_spin.value()

    @property
    def anchor(self) -> str:
        return self.anchor_picker.anchor

    def _update_info(self) -> None:
        width = self.canvas_width
        height = self.canvas_height
        pixels = width * height
        self.info_label.setText(
            f"{self._document.width} × {self._document.height} → {width} × {height} px · "
            f"ước tính {format_memory(pixels * 4)} cho composite"
        )
        if pixels > Document.MAX_PIXELS:
            self.info_label.setText("Kích thước vượt giới hạn an toàn của ứng dụng.")

    def accept(self) -> None:
        pixels = self.canvas_width * self.canvas_height
        if pixels > Document.MAX_PIXELS:
            QMessageBox.warning(
                self,
                "Kích thước quá lớn",
                f"Canvas vượt giới hạn {Document.MAX_PIXELS // 1_000_000} megapixel.\n"
                "Hãy giảm kích thước.",
            )
            return
        super().accept()


class RotateDialog(QDialog):
    """Xoay tự do theo góc bất kỳ cho canvas hoặc một layer."""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        subject: str = "canvas",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._width = max(1, int(width))
        self._height = max(1, int(height))
        suffix = "canvas" if subject == "canvas" else "layer"
        self.setWindowTitle(f"Xoay tự do {suffix}")
        self.setModal(True)
        self.setMinimumWidth(470)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel(f"XOAY TỰ DO {suffix.upper()}")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-180.0, 180.0)
        self.angle_spin.setDecimals(2)
        self.angle_spin.setSingleStep(1.0)
        self.angle_spin.setSuffix("°")
        self.angle_spin.setValue(15.0)
        self.angle_spin.setToolTip(
            "Góc dương xoay theo chiều kim đồng hồ, góc âm xoay ngược lại."
        )
        form.addRow("Góc xoay", self.angle_spin)

        self.method_combo = QComboBox()
        for label, value in RESAMPLE_OPTIONS:
            self.method_combo.addItem(label, value)
        self.method_combo.setCurrentIndex(
            max(0, self.method_combo.findData("bicubic"))
        )
        self.method_combo.setToolTip(
            "Bicubic cho kết quả mượt; Nearest giữ nguyên điểm ảnh (phù hợp pixel art)."
        )
        form.addRow("Phương pháp nội suy", self.method_combo)

        size_label = QLabel(f"{self._width} × {self._height} px")
        size_label.setObjectName("PropValue")
        form.addRow("Kích thước nguồn", size_label)

        layout.addLayout(form)

        hint = QLabel(
            "Góc dương xoay theo chiều kim đồng hồ. Vùng ngoài ảnh sau khi xoay\n"
            "sẽ trong suốt; kích thước canvas sẽ tự mở rộng để chứa toàn bộ nội dung."
        )
        hint.setObjectName("OptionsHint")
        layout.addWidget(hint)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Xoay")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.angle_spin.valueChanged.connect(self._update_info)
        self.method_combo.currentIndexChanged.connect(self._update_info)
        self._update_info()

    @property
    def angle(self) -> float:
        return float(self.angle_spin.value())

    @property
    def method(self) -> str:
        data = self.method_combo.currentData()
        return str(data) if data else "bicubic"

    def _update_info(self) -> None:
        angle = self.angle
        if abs(angle) < 1e-9:
            self.info_label.setText("Góc 0° không tạo thay đổi. Hãy nhập góc khác 0.")
            return
        new_width, new_height = rotated_dimensions(self._width, self._height, angle)
        pixels = new_width * new_height
        self.info_label.setText(
            f"Kích thước mới dự kiến {new_width} × {new_height} px · "
            f"ước tính {format_memory(pixels * 4)} cho dữ liệu ảnh"
        )
        if pixels > Document.MAX_PIXELS:
            self.info_label.setText("Kích thước vượt giới hạn an toàn của ứng dụng.")

    def accept(self) -> None:
        angle = self.angle
        if abs(angle) < 1e-9 or abs(abs(angle) - 360.0) < 1e-9:
            QMessageBox.warning(
                self,
                "Góc không hợp lệ",
                "Góc xoay phải khác 0°.\nHãy nhập một góc trong khoảng -180° đến 180°.",
            )
            return
        new_width, new_height = rotated_dimensions(self._width, self._height, angle)
        if (
            new_width > Document.MAX_DIMENSION
            or new_height > Document.MAX_DIMENSION
            or new_width * new_height > Document.MAX_PIXELS
        ):
            QMessageBox.warning(
                self,
                "Kích thước quá lớn",
                f"Sau khi xoay, ảnh sẽ thành {new_width} × {new_height} px và vượt\n"
                f"giới hạn an toàn {Document.MAX_PIXELS // 1_000_000} megapixel.\n"
                "Hãy chọn góc khác.",
            )
            return
        super().accept()


class FeatherDialog(QDialog):
    """Làm mềm biên vùng chọn hiện tại."""

    def __init__(
        self,
        current: float = 0.0,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Feather vùng chọn")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("FEATHER VÙNG CHỌN")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, int(MAX_FEATHER_RADIUS))
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setValue(int(round(float(current))))
        self.radius_spin.setToolTip(
            "0 px giữ biên cứng; giá trị lớn cho vùng chuyển tiếp rộng hơn."
        )
        form.addRow("Bán kính feather", self.radius_spin)
        layout.addLayout(form)

        hint = QLabel(
            "Áp dụng cho vùng chọn hiện tại; biên mềm được dùng khi tạo layer\n"
            "mask, vẽ, tô gradient và áp bộ lọc. Có thể Undo để trả lại biên cũ."
        )
        hint.setObjectName("OptionsHint")
        layout.addWidget(hint)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.radius_spin.valueChanged.connect(self._update_info)
        self._update_info()

    @property
    def radius(self) -> float:
        return float(self.radius_spin.value())

    def _update_info(self) -> None:
        radius = self.radius
        if radius <= 0:
            self.info_label.setText("Biên vùng chọn sẽ cứng (không feather).")
            return
        self.info_label.setText(
            f"Vùng chuyển tiếp rộng khoảng {radius:g} px tính từ biên vùng chọn."
        )


class TextDialog(QDialog):
    """Tạo hoặc sửa layer văn bản: nội dung, font, màu, căn lề, giãn và uốn chữ."""

    def __init__(
        self,
        parent: QWidget | None = None,
        properties: TextProperties | None = None,
        *,
        editing: bool = False,
        default_color: tuple[int, int, int, int] | None = None,
        default_size: int = 48,
    ) -> None:
        super().__init__(parent)
        self._editing = editing
        action = "SỬA" if editing else "TẠO"
        self.setWindowTitle(f"{action.title()} layer văn bản")
        self.setModal(True)
        self.setMinimumWidth(540)

        current = properties
        default_text = current.text if current is not None else ""
        default_family = current.font_family if current is not None else ""
        default_size = current.font_size if current is not None else max(1, int(default_size))
        default_line_spacing = current.line_spacing if current is not None else 1.0
        default_letter_spacing = current.letter_spacing if current is not None else 0
        default_warp_style = current.warp_style if current is not None else "none"
        default_warp_bend = current.warp_bend if current is not None else 0
        default_kerning = (
            format_kerning_pairs(current.kerning_pairs)
            if current is not None
            else ""
        )
        default_path_style = current.path_style if current is not None else "none"
        default_path_bend = current.path_bend if current is not None else 0
        default_color = (
            current.color
            if current is not None
            else default_color or (255, 255, 255, 255)
        )
        self._color = QColor(*default_color)
        self._syncing = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel(f"{action} LAYER VĂN BẢN")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("Nhập nội dung văn bản…")
        self.text_edit.setFixedHeight(96)
        self.text_edit.setToolTip(
            "Bôi đen một phần chữ rồi đổi font, cỡ, màu hoặc đậm/nghiêng để "
            "định dạng riêng đoạn đó. Không bôi đen thì áp dụng cho toàn bộ văn bản."
        )
        form.addRow("Nội dung", self.text_edit)

        self.font_combo = QFontComboBox()
        if default_family:
            self.font_combo.setCurrentFont(QFont(default_family))
        form.addRow("Font", self.font_combo)

        style_row = QHBoxLayout()
        style_row.setSpacing(10)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 1000)
        self.size_spin.setValue(default_size)
        self.size_spin.setSuffix(" px")
        style_row.addWidget(self.size_spin)
        self.bold_check = QCheckBox("Đậm")
        self.bold_check.setChecked(bool(current and current.bold))
        style_row.addWidget(self.bold_check)
        self.italic_check = QCheckBox("Nghiêng")
        self.italic_check.setChecked(bool(current and current.italic))
        style_row.addWidget(self.italic_check)
        style_row.addStretch(1)
        form.addRow("Cỡ chữ / kiểu", style_row)

        alignment_row = QHBoxLayout()
        alignment_row.setSpacing(10)
        self.alignment_combo = QComboBox()
        for alignment in ("left", "center", "right"):
            self.alignment_combo.addItem(ALIGNMENT_LABELS[alignment], alignment)
        self.alignment_combo.setCurrentIndex(
            max(
                0,
                self.alignment_combo.findData(
                    current.alignment if current is not None else "left"
                ),
            )
        )
        alignment_row.addWidget(self.alignment_combo, 1)
        self.color_swatch = QLabel()
        self.color_swatch.setFixedSize(30, 24)
        alignment_row.addWidget(self.color_swatch)
        self.color_button = QPushButton("Chọn màu…")
        self.color_button.clicked.connect(self._choose_color)
        alignment_row.addWidget(self.color_button)
        form.addRow("Căn lề / màu", alignment_row)

        spacing_row = QHBoxLayout()
        spacing_row.setSpacing(10)
        self.line_spacing_spin = QDoubleSpinBox()
        self.line_spacing_spin.setRange(MIN_LINE_SPACING, MAX_LINE_SPACING)
        self.line_spacing_spin.setDecimals(2)
        self.line_spacing_spin.setSingleStep(0.1)
        self.line_spacing_spin.setPrefix("Dòng ")
        self.line_spacing_spin.setSuffix(" ×")
        self.line_spacing_spin.setValue(default_line_spacing)
        self.line_spacing_spin.setToolTip(
            "Hệ số khoảng cách giữa các dòng: 1,00 là mặc định, lớn hơn để thoáng hơn."
        )
        spacing_row.addWidget(self.line_spacing_spin)
        self.letter_spacing_spin = QSpinBox()
        self.letter_spacing_spin.setRange(MIN_LETTER_SPACING, MAX_LETTER_SPACING)
        self.letter_spacing_spin.setPrefix("Chữ ")
        self.letter_spacing_spin.setSuffix(" px")
        self.letter_spacing_spin.setValue(default_letter_spacing)
        self.letter_spacing_spin.setToolTip(
            "Khoảng cách thêm giữa các ký tự: số dương giãn rộng, số âm thu hẹp."
        )
        spacing_row.addWidget(self.letter_spacing_spin)
        spacing_row.addStretch(1)
        form.addRow("Giãn dòng / chữ", spacing_row)

        self.kerning_edit = QLineEdit()
        self.kerning_edit.setPlaceholderText("Ví dụ: AV=-6, To=-3 (tuỳ chọn)")
        self.kerning_edit.setText(default_kerning)
        self.kerning_edit.setToolTip(
            "Kerning thủ công theo từng cặp ký tự: nhập AB=giá trị, "
            "cách nhau bằng dấu phẩy. Số âm kéo gần, số dương đẩy xa."
        )
        form.addRow("Kerning cặp", self.kerning_edit)

        warp_row = QHBoxLayout()
        warp_row.setSpacing(10)
        self.warp_combo = QComboBox()
        for style in WARP_STYLES:
            self.warp_combo.addItem(WARP_LABELS[style], style)
        self.warp_combo.setCurrentIndex(
            max(0, self.warp_combo.findData(default_warp_style))
        )
        self.warp_combo.setToolTip(
            "Uốn cả layer văn bản theo dạng cung, sóng, phồng… "
            "Nội dung vẫn sửa được sau khi uốn."
        )
        warp_row.addWidget(self.warp_combo, 1)
        self.warp_bend_spin = QSpinBox()
        self.warp_bend_spin.setRange(MIN_WARP_BEND, MAX_WARP_BEND)
        self.warp_bend_spin.setPrefix("Độ uốn ")
        self.warp_bend_spin.setSuffix(" %")
        self.warp_bend_spin.setValue(default_warp_bend)
        self.warp_bend_spin.setToolTip(
            "Độ mạnh của uốn: số dương cong lên/phồng, số âm cong xuống/ép."
        )
        self.warp_bend_spin.setEnabled(default_warp_style != "none")
        warp_row.addWidget(self.warp_bend_spin)
        form.addRow("Uốn chữ", warp_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.path_combo = QComboBox()
        for style in PATH_STYLES:
            self.path_combo.addItem(PATH_LABELS[style], style)
        self.path_combo.setCurrentIndex(
            max(0, self.path_combo.findData(default_path_style))
        )
        self.path_combo.setToolTip(
            "Đặt từng ký tự dọc theo đường cong: cung, vòng tròn, sóng hoặc chữ S. "
            "Chữ trên đường dẫn thay thế kiểu uốn chữ."
        )
        path_row.addWidget(self.path_combo, 1)
        self.path_bend_spin = QSpinBox()
        self.path_bend_spin.setRange(MIN_PATH_BEND, MAX_PATH_BEND)
        self.path_bend_spin.setPrefix("Độ cong ")
        self.path_bend_spin.setSuffix(" %")
        self.path_bend_spin.setValue(default_path_bend)
        self.path_bend_spin.setToolTip(
            "Mức độ cong của đường dẫn: số dương cong lên/ra ngoài, "
            "số âm cong xuống/vào trong."
        )
        self.path_bend_spin.setEnabled(default_path_style != "none")
        path_row.addWidget(self.path_bend_spin)
        form.addRow("Chữ trên đường dẫn", path_row)

        layout.addLayout(form)

        preview_title = QLabel("XEM TRƯỚC")
        preview_title.setObjectName("PanelTitle")
        layout.addWidget(preview_title)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(460, 130)
        self.preview_label.setStyleSheet(
            "background-color: #2b2e35; border: 1px solid #4a4f57; border-radius: 4px;"
        )
        layout.addWidget(self.preview_label)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Cập nhật" if editing else "Tạo văn bản"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._update_preview)
        self.text_edit.textChanged.connect(self._schedule_preview)
        self.text_edit.cursorPositionChanged.connect(self._sync_controls_from_cursor)
        self.font_combo.currentFontChanged.connect(self._on_style_control_changed)
        self.size_spin.valueChanged.connect(self._on_style_control_changed)
        self.bold_check.toggled.connect(self._on_style_control_changed)
        self.italic_check.toggled.connect(self._on_style_control_changed)
        self.alignment_combo.currentIndexChanged.connect(self._schedule_preview)
        self.line_spacing_spin.valueChanged.connect(self._schedule_preview)
        self.letter_spacing_spin.valueChanged.connect(self._schedule_preview)
        self.kerning_edit.textChanged.connect(self._schedule_preview)
        self.warp_combo.currentIndexChanged.connect(self._on_warp_style_changed)
        self.warp_bend_spin.valueChanged.connect(self._schedule_preview)
        self.path_combo.currentIndexChanged.connect(self._on_path_style_changed)
        self.path_bend_spin.valueChanged.connect(self._schedule_preview)

        self._load_document(
            current,
            default_text,
            default_family,
            default_size,
            bool(current.bold) if current is not None else False,
            bool(current.italic) if current is not None else False,
        )
        self._syncing = False
        self._sync_controls_from_cursor()
        self._update_color_swatch()
        self._update_warp_enabled()
        self._update_preview()
        self.text_edit.setFocus()

    # ------------------------------------------------------------------ dữ liệu
    @property
    def properties(self) -> TextProperties:
        runs = self._extract_runs()
        if not runs:
            raise ValueError("Nội dung văn bản không được để trống.")
        cursor_run = run_from_format(
            self.text_edit.currentCharFormat(), "", self._run_from_controls()
        )
        return TextProperties(
            runs=runs,
            font_family=cursor_run.font_family,
            font_size=cursor_run.font_size,
            color=cursor_run.color,
            bold=cursor_run.bold,
            italic=cursor_run.italic,
            alignment=str(self.alignment_combo.currentData()),
            line_spacing=float(self.line_spacing_spin.value()),
            letter_spacing=int(self.letter_spacing_spin.value()),
            warp_style=str(self.warp_combo.currentData()),
            warp_bend=int(self.warp_bend_spin.value()),
            kerning_pairs=parse_kerning_pairs(self.kerning_edit.text()),
            path_style=str(self.path_combo.currentData()),
            path_bend=int(self.path_bend_spin.value()),
        )

    # ------------------------------------------------------------------ helper
    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _update_warp_enabled(self) -> None:
        path_active = str(self.path_combo.currentData()) != "none"
        self.warp_combo.setEnabled(not path_active)
        self.warp_bend_spin.setEnabled(
            not path_active and str(self.warp_combo.currentData()) != "none"
        )

    def _on_warp_style_changed(self) -> None:
        style = str(self.warp_combo.currentData())
        if style != "none" and self.warp_bend_spin.value() == 0:
            self.warp_bend_spin.blockSignals(True)
            self.warp_bend_spin.setValue(50)
            self.warp_bend_spin.blockSignals(False)
        self._update_warp_enabled()
        self._schedule_preview()

    def _on_path_style_changed(self) -> None:
        style = str(self.path_combo.currentData())
        self.path_bend_spin.setEnabled(style != "none")
        if style != "none" and self.path_bend_spin.value() == 0:
            self.path_bend_spin.blockSignals(True)
            self.path_bend_spin.setValue(60)
            self.path_bend_spin.blockSignals(False)
        self._update_warp_enabled()
        self._schedule_preview()

    def _run_from_controls(self) -> TextRun:
        font = self.font_combo.currentFont()
        return TextRun(
            text="",
            font_family=font.family(),
            font_size=self.size_spin.value(),
            color=(
                self._color.red(),
                self._color.green(),
                self._color.blue(),
                self._color.alpha(),
            ),
            bold=self.bold_check.isChecked(),
            italic=self.italic_check.isChecked(),
        )

    def _load_document(
        self,
        current: TextProperties | None,
        text: str,
        family: str,
        size: int,
        bold: bool,
        italic: bool,
    ) -> None:
        cursor = QTextCursor(self.text_edit.document())
        cursor.beginEditBlock()
        if current is not None:
            for run in current.runs:
                if run.text:
                    cursor.insertText(run.text, format_from_run(run))
            base = current.runs[-1] if current.runs else self._run_from_controls()
        else:
            base = TextRun(
                text="",
                font_family=family,
                font_size=size,
                color=(
                    self._color.red(),
                    self._color.green(),
                    self._color.blue(),
                    self._color.alpha(),
                ),
                bold=bold,
                italic=italic,
            )
            if text:
                cursor.insertText(text, format_from_run(base))
        cursor.endEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
        if not text:
            self.text_edit.setCurrentCharFormat(format_from_run(base))

    def _extract_runs(self) -> tuple[TextRun, ...]:
        fallback = self._run_from_controls()
        document = self.text_edit.document()
        runs: list[TextRun] = []
        for block_index in range(document.blockCount()):
            if block_index:
                if runs:
                    runs[-1] = replace(runs[-1], text=runs[-1].text + "\n")
                else:
                    runs.append(replace(fallback, text="\n"))
            block = document.findBlockByNumber(block_index)
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                content = fragment.text()
                if content:
                    runs.append(
                        run_from_format(fragment.charFormat(), content, fallback)
                    )
                iterator += 1
        return tuple(runs)

    def _on_style_control_changed(self, *_: object) -> None:
        if self._syncing:
            return
        self._apply_style_to_text()
        self._schedule_preview()

    def _apply_style_to_text(self) -> None:
        fmt = format_from_run(self._run_from_controls())
        cursor = self.text_edit.textCursor()
        had_selection = cursor.hasSelection()
        anchor = cursor.anchor()
        position = cursor.position()
        previous = self._syncing
        self._syncing = True
        try:
            if not had_selection:
                cursor.select(QTextCursor.SelectionType.Document)
                self.text_edit.setTextCursor(cursor)
            self.text_edit.mergeCurrentCharFormat(fmt)
            if not had_selection:
                restored = QTextCursor(self.text_edit.document())
                restored.setPosition(anchor)
                restored.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
                self.text_edit.setTextCursor(restored)
            self.text_edit.setCurrentCharFormat(fmt)
        finally:
            self._syncing = previous

    def _sync_controls_from_cursor(self) -> None:
        if self._syncing:
            return
        run = run_from_format(
            self.text_edit.currentCharFormat(), "", self._run_from_controls()
        )
        self._syncing = True
        try:
            if run.font_family:
                self.font_combo.setCurrentFont(QFont(run.font_family))
            self.size_spin.setValue(run.font_size)
            self.bold_check.setChecked(run.bold)
            self.italic_check.setChecked(run.italic)
            color = QColor(*run.color)
            if color != self._color:
                self._color = color
                self._update_color_swatch()
        finally:
            self._syncing = False
        self._schedule_preview()

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(
            self._color,
            self,
            "Chọn màu văn bản",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._color = color
            self._update_color_swatch()
            self._apply_style_to_text()
            self._schedule_preview()

    def _update_color_swatch(self) -> None:
        self.color_swatch.setStyleSheet(
            f"background-color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha()}); "
            "border: 1px solid #555a63; border-radius: 4px;"
        )
        self.color_swatch.setToolTip(
            f"RGBA({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha()})"
        )

    def _update_preview(self) -> None:
        try:
            properties = self.properties
        except ValueError as exc:
            self.preview_label.setPixmap(QPixmap())
            if self.text_edit.toPlainText().strip():
                self.preview_label.setText(str(exc))
            else:
                self.preview_label.setText("Nhập nội dung văn bản để xem trước.")
            self.info_label.setText("")
            return
        try:
            width, height = text_size(properties)
        except ValueError as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(str(exc))
            self.info_label.setText("")
            return
        spacing_info = ""
        if abs(properties.line_spacing - 1.0) > 1e-9:
            spacing_info += f" · giãn dòng {properties.line_spacing:g}×"
        if properties.letter_spacing:
            spacing_info += f" · giãn chữ {properties.letter_spacing:+d} px"
        if properties.kerning_pairs:
            spacing_info += f" · kerning {len(properties.kerning_pairs)} cặp"
        if properties.path_style != "none" and properties.path_bend:
            spacing_info += (
                f" · đường dẫn {PATH_LABELS[properties.path_style].lower()}"
                f" {properties.path_bend:+d}%"
            )
        elif properties.warp_style != "none" and properties.warp_bend:
            spacing_info += (
                f" · uốn {WARP_LABELS[properties.warp_style].lower()}"
                f" {properties.warp_bend:+d}%"
            )
        style_info = (
            f"{len(properties.runs)} kiểu chữ"
            if len(properties.runs) > 1
            else f"cỡ chữ {properties.font_size} px"
        )
        self.info_label.setText(
            f"Layer dự kiến: {width} × {height} px · {style_info}{spacing_info}"
        )
        if width * height > 4_000_000:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Văn bản quá lớn để xem trước.")
            return
        image = numpy_rgba_to_qimage(render_text(properties))
        scale = min(1.0, 450.0 / max(1, width), 118.0 / max(1, height))
        target_width = max(1, int(round(width * scale)))
        target_height = max(1, int(round(height * scale)))
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            QPixmap.fromImage(image).scaled(
                target_width,
                target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def accept(self) -> None:
        try:
            properties = self.properties
            render_text(properties)
        except (ValueError, MemoryError) as exc:
            QMessageBox.warning(self, "Văn bản không hợp lệ", str(exc))
            return
        super().accept()


class ShapeDialog(QDialog):
    """Tạo hoặc sửa layer hình khối: loại, kích thước, màu tô, viền và bo góc."""

    def __init__(
        self,
        parent: QWidget | None = None,
        properties: ShapeProperties | None = None,
        *,
        editing: bool = False,
    ) -> None:
        super().__init__(parent)
        self._editing = editing
        action = "SỬA" if editing else "TẠO"
        self.setWindowTitle(f"{action.title()} layer hình khối")
        self.setModal(True)
        self.setMinimumWidth(560)

        current = properties or ShapeProperties()
        self._fill_color = QColor(*(current.fill_color or (59, 110, 165, 255)))
        self._stroke_color = QColor(*current.stroke_color)
        self._initial_radius = float(current.corner_radius)
        self._initial_corner_radii = current.corner_radii

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel(f"{action} LAYER HÌNH KHỐI")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        self.kind_combo = QComboBox()
        for kind, label in SHAPE_LABELS.items():
            self.kind_combo.addItem(label, kind)
        self.kind_combo.setCurrentIndex(max(0, self.kind_combo.findData(current.kind)))
        form.addRow("Loại hình", self.kind_combo)

        size_row = QHBoxLayout()
        size_row.setSpacing(10)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, MAX_SHAPE_SIZE)
        self.width_spin.setValue(current.width)
        self.width_spin.setSuffix(" px")
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("×"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, MAX_SHAPE_SIZE)
        self.height_spin.setValue(current.height)
        self.height_spin.setSuffix(" px")
        size_row.addWidget(self.height_spin)
        size_row.addStretch(1)
        form.addRow("Kích thước", size_row)

        fill_row = QHBoxLayout()
        fill_row.setSpacing(10)
        self.fill_check = QCheckBox("Tô màu")
        self.fill_check.setChecked(current.fill_color is not None)
        fill_row.addWidget(self.fill_check)
        self.fill_swatch = QLabel()
        self.fill_swatch.setFixedSize(30, 24)
        fill_row.addWidget(self.fill_swatch)
        self.fill_button = QPushButton("Chọn màu tô…")
        self.fill_button.clicked.connect(lambda: self._choose_color("fill"))
        fill_row.addWidget(self.fill_button)
        fill_row.addStretch(1)
        form.addRow("Màu tô", fill_row)

        stroke_row = QHBoxLayout()
        stroke_row.setSpacing(10)
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(0, MAX_STROKE_WIDTH)
        self.stroke_spin.setValue(current.stroke_width)
        self.stroke_spin.setSuffix(" px")
        stroke_row.addWidget(self.stroke_spin)
        self.stroke_swatch = QLabel()
        self.stroke_swatch.setFixedSize(30, 24)
        stroke_row.addWidget(self.stroke_swatch)
        self.stroke_button = QPushButton("Chọn màu viền…")
        self.stroke_button.clicked.connect(lambda: self._choose_color("stroke"))
        stroke_row.addWidget(self.stroke_button)
        stroke_row.addStretch(1)
        form.addRow("Viền", stroke_row)

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.0, MAX_CORNER_RADIUS)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSingleStep(2.0)
        self.radius_spin.setValue(current.corner_radius)
        self.radius_spin.setSuffix(" px")
        form.addRow("Bo góc", self.radius_spin)

        layout.addLayout(form)

        preview_title = QLabel("XEM TRƯỚC")
        preview_title.setObjectName("PanelTitle")
        layout.addWidget(preview_title)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(500, 140)
        self.preview_label.setStyleSheet(
            "background-color: #2b2e35; border: 1px solid #4a4f57; border-radius: 4px;"
        )
        layout.addWidget(self.preview_label)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Cập nhật" if editing else "Tạo hình khối"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._update_preview)
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        self.width_spin.valueChanged.connect(self._schedule_preview)
        self.height_spin.valueChanged.connect(self._schedule_preview)
        self.fill_check.toggled.connect(self._on_fill_toggled)
        self.stroke_spin.valueChanged.connect(self._on_stroke_changed)
        self.radius_spin.valueChanged.connect(self._schedule_preview)

        self._update_swatches()
        self._update_controls()
        self._update_preview()

    # ------------------------------------------------------------------ dữ liệu
    @property
    def properties(self) -> ShapeProperties:
        fill = self._fill_color.getRgb() if self.fill_check.isChecked() else None
        stroke = self._stroke_color.getRgb()
        radius = self.radius_spin.value()
        radii = None
        if (
            self._editing
            and self._initial_corner_radii is not None
            and abs(radius - self._initial_radius) < 1e-9
        ):
            radii = self._initial_corner_radii
        return ShapeProperties(
            kind=str(self.kind_combo.currentData()),
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            fill_color=fill,
            stroke_color=stroke,
            stroke_width=self.stroke_spin.value(),
            corner_radius=radius,
            corner_radii=radii,
        )

    # ------------------------------------------------------------------ helper
    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _on_kind_changed(self) -> None:
        self._update_controls()
        self._schedule_preview()

    def _on_fill_toggled(self, _checked: bool) -> None:
        self._update_controls()
        self._schedule_preview()

    def _on_stroke_changed(self) -> None:
        self._update_controls()
        self._schedule_preview()

    def _update_controls(self) -> None:
        rounded = str(self.kind_combo.currentData()) == "rounded_rectangle"
        self.radius_spin.setEnabled(rounded)
        has_fill = self.fill_check.isChecked()
        self.fill_swatch.setEnabled(has_fill)
        self.fill_button.setEnabled(has_fill)
        self.stroke_swatch.setEnabled(self.stroke_spin.value() > 0)
        self.stroke_button.setEnabled(self.stroke_spin.value() > 0)

    def _choose_color(self, which: str) -> None:
        target = self._fill_color if which == "fill" else self._stroke_color
        title = "Chọn màu tô" if which == "fill" else "Chọn màu viền"
        color = QColorDialog.getColor(
            target,
            self,
            title,
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        if which == "fill":
            self._fill_color = color
        else:
            self._stroke_color = color
        self._update_swatches()
        self._schedule_preview()

    def _update_swatches(self) -> None:
        for swatch, color in (
            (self.fill_swatch, self._fill_color),
            (self.stroke_swatch, self._stroke_color),
        ):
            swatch.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, "
                f"{color.blue()}, {color.alpha()}); "
                "border: 1px solid #555a63; border-radius: 4px;"
            )
            swatch.setToolTip(
                f"RGBA({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
            )

    def _update_preview(self) -> None:
        try:
            properties = self.properties
        except ValueError as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(str(exc))
            self.info_label.setText("")
            return
        self.info_label.setText(
            f"Layer dự kiến: {properties.width} × {properties.height} px · "
            f"{SHAPE_LABELS.get(properties.kind, properties.kind)}"
        )
        if properties.width * properties.height > 4_000_000:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Hình quá lớn để xem trước.")
            return
        image = numpy_rgba_to_qimage(render_shape(properties))
        scale = min(
            1.0,
            480.0 / max(1, properties.width),
            128.0 / max(1, properties.height),
        )
        target_width = max(1, int(round(properties.width * scale)))
        target_height = max(1, int(round(properties.height * scale)))
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            QPixmap.fromImage(image).scaled(
                target_width,
                target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def accept(self) -> None:
        try:
            properties = self.properties
            render_shape(properties)
        except (ValueError, MemoryError) as exc:
            QMessageBox.warning(self, "Hình khối không hợp lệ", str(exc))
            return
        super().accept()


class SliderField(QWidget):
    """Một slider kèm ô số đồng bộ, dùng cho tham số bộ lọc."""

    valueChanged = Signal(int)

    def __init__(
        self,
        minimum: int,
        maximum: int,
        value: int = 0,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        if suffix:
            self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(86)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.spin.valueChanged.connect(self.valueChanged)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)

    def value(self) -> int:
        return self.spin.value()

    def setValue(self, value: int) -> None:
        self.spin.setValue(int(value))


class FloatSliderField(QWidget):
    """Slider số thực (dùng cho gamma) kèm ô số thập phân."""

    valueChanged = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        value: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum * 100), round(maximum * 100))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(2)
        self.spin.setSingleStep(0.01)
        self.spin.setFixedWidth(86)
        self.spin.setValue(value)
        self.slider.setValue(round(value * 100))
        self.slider.valueChanged.connect(
            lambda value: self.spin.setValue(value / 100.0)
        )
        self.spin.valueChanged.connect(
            lambda value: self.slider.setValue(round(value * 100))
        )
        self.spin.valueChanged.connect(self.valueChanged)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, value: float) -> None:
        self.spin.setValue(float(value))


class PreviewLabel(QLabel):
    """Ảnh xem trước có thể nhấp để lấy mẫu màu bằng eyedropper."""

    clicked = Signal(object)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            from compat.qt import mouse_event_position

            self.clicked.emit(mouse_event_position(event))
        super().mousePressEvent(event)


class HistogramView(QWidget):
    """Biểu đồ tần suất độ sáng; Levels dùng thêm hai tay nắm đen/trắng."""

    rangeChanged = Signal(int, int)
    _HANDLE_WIDTH = 10.0
    _HANDLE_HEIGHT = 13.0
    _GRAB_RADIUS = 14.0

    def __init__(
        self, parent: QWidget | None = None, *, interactive: bool = False
    ) -> None:
        super().__init__(parent)
        self._values = np.zeros(256, dtype=np.float32)
        self._tint: QColor | None = None
        self._interactive = bool(interactive)
        self._black = 0
        self._white = 255
        self._drag_handle = ""
        self.setMinimumHeight(104)
        self.setToolTip(
            "Histogram của ảnh bên dưới layer điều chỉnh.\n"
            "Cột cao = nhiều điểm ảnh ở mức sáng đó."
        )
        if self._interactive:
            self.setCursor(Qt.CursorShape.SplitHCursor)
            self.setToolTip(
                "Kéo tay nắm đen/trắng trên histogram để chỉnh dải sáng.\n"
                "Cột cao = nhiều điểm ảnh ở mức sáng đó."
            )

    def set_values(
        self, values, tint: QColor | str | None = None
    ) -> None:
        array = np.asarray(values, dtype=np.float32).ravel()
        self._values = array if array.size else np.zeros(256, dtype=np.float32)
        if tint is not None:
            self._tint = QColor(tint)
        self.update()

    def black(self) -> int:
        return self._black

    def white(self) -> int:
        return self._white

    def set_range(self, black: int, white: int) -> None:
        black = max(0, min(254, int(black)))
        white = max(1, min(255, int(white)))
        if black >= white:
            black = max(0, white - 1)
        if (black, white) == (self._black, self._white):
            return
        self._black = black
        self._white = white
        self.update()

    def _value_to_x(self, value: int, rect: QRectF) -> float:
        return rect.left() + (float(value) / 255.0) * rect.width()

    def _x_to_value(self, x: float, rect: QRectF) -> int:
        span = max(rect.width(), 1.0)
        return int(round(max(0.0, min(1.0, (x - rect.left()) / span)) * 255.0))

    def _handle_rect(self, value: int, rect: QRectF) -> QRectF:
        x = self._value_to_x(value, rect)
        width = self._HANDLE_WIDTH
        left = min(
            max(x - width / 2.0, rect.left()),
            rect.right() - width,
        )
        return QRectF(
            left,
            rect.bottom() - self._HANDLE_HEIGHT,
            width,
            self._HANDLE_HEIGHT,
        )

    def _apply_handle_value(self, value: int) -> None:
        if self._drag_handle == "black":
            value = max(0, min(self._white - 1, value))
            if value == self._black:
                return
            self._black = value
        else:
            value = max(self._black + 1, min(255, value))
            if value == self._white:
                return
            self._white = value
        self.update()
        self.rangeChanged.emit(self._black, self._white)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            not self._interactive
            or event.button() != Qt.MouseButton.LeftButton
        ):
            super().mousePressEvent(event)
            return
        from compat.qt import mouse_event_position

        position = mouse_event_position(event)
        rect = QRectF(self.rect().adjusted(1, 1, -1, -1))
        black_x = self._value_to_x(self._black, rect)
        white_x = self._value_to_x(self._white, rect)
        distance_black = abs(position.x() - black_x)
        distance_white = abs(position.x() - white_x)
        near_handle = min(distance_black, distance_white) <= self._GRAB_RADIUS
        near_strip = position.y() >= rect.bottom() - self._HANDLE_HEIGHT - 6
        if not (near_handle or near_strip):
            return
        self._drag_handle = (
            "black" if distance_black <= distance_white else "white"
        )
        self._apply_handle_value(self._x_to_value(position.x(), rect))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._drag_handle:
            super().mouseMoveEvent(event)
            return
        from compat.qt import mouse_event_position

        position = mouse_event_position(event)
        rect = QRectF(self.rect().adjusted(1, 1, -1, -1))
        self._apply_handle_value(self._x_to_value(position.x(), rect))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_handle:
            self._drag_handle = ""
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self.palette().base())
        rect = QRectF(self.rect().adjusted(1, 1, -1, -1))
        color = self._tint or self.palette().midlight().color()
        color = QColor(color)
        color.setAlpha(170)
        peak = float(self._values.max()) if self._values.size else 0.0
        if peak > 0:
            width = rect.width() / self._values.size
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            for index, value in enumerate(self._values):
                height = (float(value) / peak) * (rect.height() - 2)
                if height <= 0.0:
                    continue
                painter.drawRect(
                    QRectF(
                        rect.left() + index * width,
                        rect.bottom() - height,
                        max(width, 1.0),
                        height,
                    )
                )
        painter.setPen(QPen(self.palette().mid().color(), 1.0))
        painter.drawRect(rect)
        if self._interactive:
            self._paint_handles(painter, rect)
        painter.end()

    def _paint_handles(self, painter: QPainter, rect: QRectF) -> None:
        font = QFont(painter.font())
        font.setPointSize(8)
        painter.setFont(font)
        label_color = self.palette().text().color()
        for value, fill in (
            (self._black, QColor("#15181d")),
            (self._white, QColor("#f2f4f7")),
        ):
            x = self._value_to_x(value, rect)
            painter.setPen(QPen(QColor("#8a929e"), 1.0))
            painter.drawLine(
                QPointF(x, rect.top()), QPointF(x, rect.bottom())
            )
            handle = self._handle_rect(value, rect)
            painter.setPen(QPen(QColor("#8a929e"), 1.0))
            painter.setBrush(fill)
            painter.drawRect(handle)
            label = str(value)
            metrics = painter.fontMetrics()
            label_width = metrics.horizontalAdvance(label)
            label_x = min(
                max(x - label_width / 2.0, rect.left() + 1.0),
                rect.right() - label_width - 1.0,
            )
            painter.setPen(QPen(label_color, 1.0))
            painter.drawText(
                QPointF(label_x, rect.bottom() - self._HANDLE_HEIGHT - 3.0),
                label,
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)


class CurveEditor(QWidget):
    """Đường cong từng kênh: nhấp thêm điểm, kéo chỉnh, chuột phải xoá."""

    pointsChanged = Signal(object)
    _MARGIN = 14.0
    _HIT_RADIUS = 9.0

    def __init__(
        self,
        points=((0, 0), (255, 255)),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._points = [tuple(int(v) for v in pair) for pair in points]
        self._drag_index = -1
        self._histogram: np.ndarray | None = None
        self._curve_color: QColor | None = None
        self.setMinimumSize(440, 240)
        self.setToolTip(
            "Nhấp để thêm điểm · kéo để chỉnh · chuột phải để xoá điểm.\n"
            "Trục ngang = giá trị vào, trục dọc = giá trị ra (0..255)."
        )

    def points(self) -> tuple[tuple[int, int], ...]:
        return tuple(self._points)

    def set_points(self, points) -> None:
        try:
            self._points = sorted(
                (int(x), int(y)) for x, y in points
            )
        except (TypeError, ValueError):
            return
        self._drag_index = -1
        self.update()
        self.pointsChanged.emit(self.points())

    def add_point(self, x: int, y: int) -> bool:
        """Thêm điểm (dùng cho eyedropper); thay thế nếu đã có hoành độ đó."""
        x = max(0, min(255, int(x)))
        y = max(0, min(255, int(y)))
        for index, (existing, _) in enumerate(self._points):
            if existing == x:
                self._points[index] = (x, y)
                self.update()
                self.pointsChanged.emit(self.points())
                return True
        if len(self._points) >= MAX_CURVE_POINTS:
            return False
        self._points.append((x, y))
        self._points.sort()
        self.update()
        self.pointsChanged.emit(self.points())
        return True

    def set_histogram(self, values) -> None:
        if values is None:
            self._histogram = None
        else:
            array = np.asarray(values, dtype=np.float32).ravel()
            self._histogram = array if array.size else None
        self.update()

    def set_curve_color(self, color) -> None:
        self._curve_color = QColor(color) if color is not None else None
        self.update()

    def reset(self) -> None:
        self.set_points(((0, 0), (255, 255)))

    def _plot_rect(self) -> QRectF:
        margin = self._MARGIN
        return QRectF(
            margin,
            margin,
            max(1.0, self.width() - margin * 2.0),
            max(1.0, self.height() - margin * 2.0),
        )

    def _to_screen(self, x: int, y: int) -> QPointF:
        rect = self._plot_rect()
        return QPointF(
            rect.left() + (x / 255.0) * rect.width(),
            rect.bottom() - (y / 255.0) * rect.height(),
        )

    def _from_screen(self, position: QPointF) -> tuple[int, int]:
        rect = self._plot_rect()
        x = (position.x() - rect.left()) / max(rect.width(), 1.0)
        y = (rect.bottom() - position.y()) / max(rect.height(), 1.0)
        return (
            max(0, min(255, round(x * 255.0))),
            max(0, min(255, round(y * 255.0))),
        )

    def _nearest_index(self, position: QPointF) -> int:
        best = -1
        best_distance = self._HIT_RADIUS
        for index, (x, y) in enumerate(self._points):
            screen = self._to_screen(x, y)
            distance = (
                (screen.x() - position.x()) ** 2
                + (screen.y() - position.y()) ** 2
            ) ** 0.5
            if distance <= best_distance:
                best = index
                best_distance = distance
        return best

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.palette().base())
        rect = self._plot_rect()
        if self._histogram is not None:
            peak = float(self._histogram.max())
            if peak > 0.0:
                fill = QColor(
                    self._curve_color or self.palette().midlight().color()
                )
                fill.setAlpha(60)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                width = rect.width() / self._histogram.size
                for index, value in enumerate(self._histogram):
                    height = (float(value) / peak) * rect.height()
                    if height <= 0.0:
                        continue
                    painter.drawRect(
                        QRectF(
                            rect.left() + index * width,
                            rect.bottom() - height,
                            max(width, 1.0),
                            height,
                        )
                    )
        grid_pen = QPen(self.palette().mid().color(), 1.0)
        for step in range(1, 4):
            offset = step / 4.0
            grid_pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(grid_pen)
            painter.drawLine(
                QPointF(rect.left() + rect.width() * offset, rect.top()),
                QPointF(rect.left() + rect.width() * offset, rect.bottom()),
            )
            painter.drawLine(
                QPointF(rect.left(), rect.top() + rect.height() * offset),
                QPointF(rect.right(), rect.top() + rect.height() * offset),
            )
        painter.setPen(QPen(self.palette().mid().color(), 1.0))
        painter.drawRect(rect)
        diagonal = QPen(self.palette().mid().color(), 1.0)
        diagonal.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(diagonal)
        painter.drawLine(rect.bottomLeft(), rect.topRight())

        xs = np.array([point[0] for point in self._points], dtype=np.float32)
        ys = np.array([point[1] for point in self._points], dtype=np.float32)
        samples = np.linspace(0.0, 255.0, 128)
        curve = np.interp(samples, xs, ys)
        curve_pen = QPen(
            self._curve_color or self.palette().highlight().color(), 2.0
        )
        painter.setPen(curve_pen)
        previous = self._to_screen(int(samples[0]), int(round(curve[0])))
        for sample, value in zip(samples[1:], curve[1:]):
            current = self._to_screen(int(round(sample)), int(round(value)))
            painter.drawLine(previous, current)
            previous = current

        for index, (x, y) in enumerate(self._points):
            screen = self._to_screen(x, y)
            radius = 5.0 if index == self._drag_index else 4.0
            painter.setBrush(
                self._curve_color or self.palette().highlight()
            )
            painter.setPen(QPen(self.palette().base().color(), 1.0))
            painter.drawEllipse(screen, radius, radius)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        from compat.qt import mouse_event_position

        position = mouse_event_position(event)
        if event.button() == Qt.MouseButton.RightButton:
            index = self._nearest_index(position)
            if 0 < index < len(self._points) - 1:
                del self._points[index]
                self.update()
                self.pointsChanged.emit(self.points())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._nearest_index(position)
        if index < 0:
            x, y = self._from_screen(position)
            while any(point[0] == x for point in self._points):
                x = min(255, x + 1)
                if x == 255 and any(point[0] == x for point in self._points):
                    return
            self._points.append((x, y))
            self._points.sort()
            index = self._points.index((x, y))
            self.pointsChanged.emit(self.points())
        self._drag_index = index
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_index < 0:
            return
        from compat.qt import mouse_event_position

        x, y = self._from_screen(mouse_event_position(event))
        index = self._drag_index
        minimum = self._points[index - 1][0] + 1 if index > 0 else 0
        maximum = (
            self._points[index + 1][0] - 1
            if index < len(self._points) - 1
            else 255
        )
        if minimum > maximum:
            return
        self._points[index] = (max(minimum, min(maximum, x)), y)
        self.update()
        self.pointsChanged.emit(self.points())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_index >= 0:
            self._drag_index = -1
            self.update()


class AdjustmentLayerDialog(QDialog):
    """Tạo hoặc sửa layer điều chỉnh, kèm xem trước trên ảnh bên dưới."""

    def __init__(
        self,
        properties: AdjustmentProperties,
        parent: QWidget | None = None,
        *,
        preview: np.ndarray | None = None,
        mask: np.ndarray | None = None,
        editing: bool = False,
        preset_store: PresetStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = properties.kind
        self._editing = editing
        self.preset_store = preset_store
        self.preset_combo: QComboBox | None = None
        self.preset_name_edit: QLineEdit | None = None
        self.preset_save_button: QPushButton | None = None
        self.preset_delete_button: QPushButton | None = None
        label = ADJUSTMENT_LABELS.get(properties.kind, properties.kind)
        self.setWindowTitle(
            f"{'Sửa' if editing else 'Tạo'} layer điều chỉnh — {label}"
        )
        self.setModal(True)
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(f"LAYER ĐIỀU CHỈNH · {label.upper()}")
        heading.setObjectName("PanelTitle")
        layout.addWidget(heading)

        description = QLabel(
            "Điều chỉnh áp lên toàn bộ layer nằm bên dưới và vẫn sửa được "
            "sau khi tạo. Độ mờ của layer dùng làm độ mạnh hiệu ứng."
        )
        description.setWordWrap(True)
        description.setObjectName("OptionsHint")
        layout.addWidget(description)

        self._source = self._prepare_preview(preview)
        self._mask = self._prepare_mask(mask)
        self._histograms = compute_histogram(self._source)
        self._preview_pixmap: QPixmap | None = None
        self._eyedropper_mode = ""
        self._sample_note = ""
        self._auto_note = ""

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self._fields: list[SliderField] = []
        if properties.kind == "brightness_contrast":
            self.brightness_field = SliderField(
                -100, 100, properties.brightness
            )
            self.contrast_field = SliderField(-100, 100, properties.contrast)
            self._fields = [self.brightness_field, self.contrast_field]
            form.addRow("Độ sáng", self.brightness_field)
            form.addRow("Tương phản", self.contrast_field)
        elif properties.kind == "hue_saturation":
            self.hue_field = SliderField(-180, 180, properties.hue, "°")
            self.saturation_field = SliderField(
                -100, 100, properties.saturation
            )
            self.lightness_field = SliderField(-100, 100, properties.lightness)
            self._fields = [
                self.hue_field,
                self.saturation_field,
                self.lightness_field,
            ]
            form.addRow("Dịch màu", self.hue_field)
            form.addRow("Độ bão hoà", self.saturation_field)
            form.addRow("Độ sáng", self.lightness_field)
        elif properties.kind == "levels":
            self.levels_black_field = SliderField(
                0, 254, properties.levels_black
            )
            self.levels_white_field = SliderField(
                1, 255, properties.levels_white
            )
            self.levels_gamma_field = FloatSliderField(
                MIN_GAMMA, MAX_GAMMA, properties.levels_gamma
            )
            self.levels_out_black_field = SliderField(
                0, 255, properties.levels_out_black
            )
            self.levels_out_white_field = SliderField(
                0, 255, properties.levels_out_white
            )
            self._fields = [
                self.levels_black_field,
                self.levels_white_field,
                self.levels_gamma_field,
                self.levels_out_black_field,
                self.levels_out_white_field,
            ]
            self.levels_histogram = HistogramView(interactive=True)
            self.levels_histogram.set_values(self._histograms["rgb"])
            self.levels_histogram.set_range(
                properties.levels_black, properties.levels_white
            )
            self.levels_histogram.rangeChanged.connect(
                self._on_histogram_range_changed
            )
            self.levels_black_field.valueChanged.connect(
                self._sync_histogram_range
            )
            self.levels_white_field.valueChanged.connect(
                self._sync_histogram_range
            )
            form.addRow("Histogram", self.levels_histogram)
            histogram_row = QHBoxLayout()
            histogram_row.setContentsMargins(0, 0, 0, 0)
            self.auto_levels_button = QPushButton("Auto Levels")
            self.auto_levels_button.setToolTip(
                "Tự tính điểm đen/trắng: cắt 0,5 % pixel tối nhất và sáng "
                "nhất, bỏ qua vùng trong suốt."
            )
            self.auto_levels_button.clicked.connect(self._on_auto_levels)
            histogram_row.addWidget(self.auto_levels_button)
            histogram_row.addWidget(
                QLabel("Kéo tay nắm đen/trắng ngay trên histogram."), 1
            )
            histogram_hint = QWidget()
            histogram_hint.setLayout(histogram_row)
            form.addRow(histogram_hint)
            form.addRow("Điểm đen vào", self.levels_black_field)
            form.addRow("Điểm trắng vào", self.levels_white_field)
            form.addRow("Gamma", self.levels_gamma_field)
            form.addRow("Điểm đen ra", self.levels_out_black_field)
            form.addRow("Điểm trắng ra", self.levels_out_white_field)
            form.addRow(self._build_eyedropper_row())
        elif properties.kind == "curves":
            self.curve_channel = "rgb"
            self._curve_values = {
                "rgb": properties.curve_points,
                "red": properties.curve_red,
                "green": properties.curve_green,
                "blue": properties.curve_blue,
            }
            self.curve_channel_combo = QComboBox()
            for key, label, _tint in CURVE_CHANNEL_SPECS:
                self.curve_channel_combo.addItem(label, key)
            form.addRow("Kênh", self.curve_channel_combo)
            self.curve_editor = CurveEditor(properties.curve_points)
            self.curve_editor.set_histogram(self._histograms["rgb"])
            self.curve_editor.pointsChanged.connect(
                self._on_curve_points_changed
            )
            self.reset_curve_button = QPushButton("Đặt lại đường 45°")
            self.reset_curve_button.clicked.connect(self.curve_editor.reset)
            self.curve_channel_combo.currentIndexChanged.connect(
                self._on_curve_channel_changed
            )
            form.addRow(self.curve_editor)
            reset_row = QHBoxLayout()
            reset_row.addWidget(
                QLabel("Nhấp thêm điểm · kéo chỉnh · chuột phải xoá."), 1
            )
            reset_row.addWidget(self.reset_curve_button)
            form.addRow(reset_row)
            form.addRow(self._build_eyedropper_row())
        elif properties.kind == "color_balance":
            self.preserve_luma_check = QCheckBox(
                "Giữ nguyên độ sáng (luminosity)"
            )
            self.preserve_luma_check.setChecked(properties.preserve_luminosity)
            self.preserve_luma_check.stateChanged.connect(
                lambda _state: self._update_preview()
            )
            balance_specs = (
                ("Vùng tối", "shadows", properties.color_shadows),
                ("Vùng trung gian", "midtones", properties.color_midtones),
                ("Vùng sáng", "highlights", properties.color_highlights),
            )
            self.balance_fields: dict[str, list[SliderField]] = {}
            for title, key, values in balance_specs:
                box = QGroupBox(title)
                grid = QGridLayout(box)
                grid.setHorizontalSpacing(10)
                grid.setVerticalSpacing(6)
                channel_labels = (
                    "Cyan ↔ Đỏ",
                    "Magenta ↔ Xanh lá",
                    "Vàng ↔ Xanh dương",
                )
                fields: list[SliderField] = []
                for row, (label, value) in enumerate(
                    zip(channel_labels, values)
                ):
                    field = SliderField(-100, 100, value)
                    fields.append(field)
                    self._fields.append(field)
                    grid.addWidget(QLabel(label), row, 0)
                    grid.addWidget(field, row, 1)
                grid.setColumnStretch(1, 1)
                self.balance_fields[key] = fields
                form.addRow(box)
            form.addRow("", self.preserve_luma_check)
        elif properties.kind == "invert":
            form.addRow("Hiệu ứng", QLabel("Đảo ngược màu RGB, giữ nguyên alpha."))
        else:
            form.addRow(
                "Hiệu ứng", QLabel("Chuyển ảnh sang xám theo độ sáng (luma).")
            )
        for field in self._fields:
            field.valueChanged.connect(self._update_preview)
        layout.addLayout(form)

        if self.preset_store is not None:
            layout.addWidget(self._build_preset_box())

        preview_title = QLabel("XEM TRƯỚC")
        preview_title.setObjectName("PanelTitle")
        layout.addWidget(preview_title)
        self.preview_label = PreviewLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 180)
        self.preview_label.setStyleSheet(
            "background-color: #2b2e35; border: 1px solid #4a4f57; border-radius: 4px;"
        )
        self.preview_label.clicked.connect(self._on_preview_clicked)
        layout.addWidget(self.preview_label)
        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Cập nhật" if editing else "Thêm layer"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_preview()

    # ------------------------------------------------------------- preset
    def _build_preset_box(self) -> QGroupBox:
        box = QGroupBox("Preset điều chỉnh")
        row = QHBoxLayout(box)
        row.setSpacing(8)
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(150)
        self.preset_combo.setToolTip(
            "Preset chỉ chứa điều chỉnh cùng loại với layer đang sửa."
        )
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        self.preset_combo.activated.connect(self._on_preset_selected)
        row.addWidget(self.preset_combo, 1)
        self.preset_name_edit = QLineEdit()
        self.preset_name_edit.setPlaceholderText("Tên preset…")
        self.preset_name_edit.setMaxLength(48)
        self.preset_name_edit.setFixedWidth(150)
        row.addWidget(self.preset_name_edit)
        self.preset_save_button = QPushButton("Lưu")
        self.preset_save_button.setToolTip("Lưu tham số hiện tại vào thư viện SQLite.")
        self.preset_save_button.clicked.connect(self._on_save_preset)
        row.addWidget(self.preset_save_button)
        self.preset_delete_button = QPushButton("Xoá")
        self.preset_delete_button.setToolTip("Xoá preset đang chọn khỏi thư viện.")
        self.preset_delete_button.clicked.connect(self._on_delete_preset)
        self.preset_delete_button.setEnabled(False)
        row.addWidget(self.preset_delete_button)
        self._refresh_presets()
        return box

    def _refresh_presets(self, select: str | None = None) -> None:
        combo = self.preset_combo
        if combo is None or self.preset_store is None:
            return
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— Chọn preset đã lưu —", "")
        try:
            presets = self.preset_store.list("adjustment")
        except PresetError:
            presets = []
        for preset in presets:
            if preset.payload.get("kind") != self._kind:
                continue
            combo.addItem(preset.name, preset.name)
        combo.blockSignals(False)
        if select:
            index = combo.findData(select)
            if index >= 0:
                combo.setCurrentIndex(index)
        if self.preset_delete_button is not None:
            self.preset_delete_button.setEnabled(bool(combo.currentData()))

    def _on_preset_selected(self, _index: int) -> None:
        if self.preset_store is None or self.preset_combo is None:
            return
        name = self.preset_combo.currentData()
        if self.preset_delete_button is not None:
            self.preset_delete_button.setEnabled(bool(name))
        if not name:
            return
        try:
            preset = self.preset_store.get("adjustment", str(name))
            if preset is None:
                raise PresetError(f"Không tìm thấy preset '{name}'.")
            properties = AdjustmentProperties.from_dict(preset.payload)
        except (PresetError, ValueError) as exc:
            QMessageBox.warning(self, "Preset không hợp lệ", str(exc))
            return
        if properties.kind != self._kind:
            QMessageBox.warning(
                self,
                "Preset không hợp loại",
                "Preset này thuộc loại điều chỉnh khác.",
            )
            return
        self._apply_properties(properties)
        if self.preset_name_edit is not None:
            self.preset_name_edit.setText(str(name))

    def _apply_properties(self, properties: AdjustmentProperties) -> None:
        self._auto_note = ""
        if properties.kind == "brightness_contrast":
            self.brightness_field.setValue(properties.brightness)
            self.contrast_field.setValue(properties.contrast)
        elif properties.kind == "hue_saturation":
            self.hue_field.setValue(properties.hue)
            self.saturation_field.setValue(properties.saturation)
            self.lightness_field.setValue(properties.lightness)
        elif properties.kind == "levels":
            self.levels_black_field.setValue(properties.levels_black)
            self.levels_white_field.setValue(properties.levels_white)
            self.levels_gamma_field.setValue(properties.levels_gamma)
            self.levels_out_black_field.setValue(properties.levels_out_black)
            self.levels_out_white_field.setValue(properties.levels_out_white)
            self.levels_histogram.set_range(
                properties.levels_black, properties.levels_white
            )
        elif properties.kind == "curves":
            self._curve_values = {
                "rgb": properties.curve_points,
                "red": properties.curve_red,
                "green": properties.curve_green,
                "blue": properties.curve_blue,
            }
            self.curve_channel = "rgb"
            self.curve_channel_combo.blockSignals(True)
            self.curve_channel_combo.setCurrentIndex(0)
            self.curve_channel_combo.blockSignals(False)
            self.curve_editor.set_points(properties.curve_points)
        elif properties.kind == "color_balance":
            for key, values in (
                ("shadows", properties.color_shadows),
                ("midtones", properties.color_midtones),
                ("highlights", properties.color_highlights),
            ):
                for field, value in zip(self.balance_fields[key], values):
                    field.setValue(value)
            self.preserve_luma_check.setChecked(
                properties.preserve_luminosity
            )
        self._update_preview()

    def _on_save_preset(self) -> None:
        if self.preset_store is None or self.preset_name_edit is None:
            return
        name = self.preset_name_edit.text().strip()
        if not name:
            QMessageBox.information(
                self, "Thiếu tên preset", "Hãy nhập tên trước khi lưu."
            )
            return
        if len(name) > 48:
            QMessageBox.warning(
                self, "Tên quá dài", "Tên preset tối đa 48 ký tự."
            )
            return
        existing = self.preset_store.get("adjustment", name)
        if existing is not None:
            answer = QMessageBox.question(
                self,
                "Ghi đè preset",
                f"Preset '{name}' đã tồn tại. Ghi đè bằng tham số hiện tại?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            saved = self.preset_store.save_adjustment(
                name, self.properties, overwrite=existing is not None
            )
        except PresetError as exc:
            QMessageBox.warning(self, "Không lưu được preset", str(exc))
            return
        self._refresh_presets(select=saved.name)
        self.preset_name_edit.setText(saved.name)

    def _on_delete_preset(self) -> None:
        if self.preset_store is None or self.preset_combo is None:
            return
        name = self.preset_combo.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Xoá preset",
            f"Xoá preset '{name}' khỏi thư viện?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.preset_store.delete("adjustment", str(name))
        except PresetError as exc:
            QMessageBox.warning(self, "Không xoá được preset", str(exc))
            return
        self._refresh_presets()

    @staticmethod
    def _prepare_mask(mask: np.ndarray | None) -> np.ndarray | None:
        if mask is None:
            return None
        array = np.asarray(mask)
        if array.ndim != 2 or array.dtype != np.uint8:
            return None
        return downsample_mask(array, 420)

    @staticmethod
    def _prepare_preview(preview: np.ndarray | None) -> np.ndarray:
        if preview is not None:
            array = np.asarray(preview)
            if array.ndim == 3 and array.shape[2] == 4 and array.dtype == np.uint8:
                return downsample_rgba(array, 420)
        width, height = 420, 170
        xs = np.linspace(0.0, 1.0, width, dtype=np.float32)
        shade = np.linspace(0.45, 1.0, height, dtype=np.float32)[:, None]
        rgb = np.stack(
            [
                80.0 + 160.0 * xs,
                200.0 - 80.0 * xs,
                220.0 - 150.0 * xs,
            ],
            axis=-1,
        )
        rgb = np.clip(rgb[None, :, :] * shade[..., None], 0, 255).astype(np.uint8)
        array = np.zeros((height, width, 4), dtype=np.uint8)
        array[..., :3] = rgb
        array[..., 3] = 255
        return array

    @property
    def properties(self) -> AdjustmentProperties:
        if self._kind == "brightness_contrast":
            return AdjustmentProperties(
                kind=self._kind,
                brightness=self.brightness_field.value(),
                contrast=self.contrast_field.value(),
            )
        if self._kind == "hue_saturation":
            return AdjustmentProperties(
                kind=self._kind,
                hue=self.hue_field.value(),
                saturation=self.saturation_field.value(),
                lightness=self.lightness_field.value(),
            )
        if self._kind == "levels":
            return AdjustmentProperties(
                kind=self._kind,
                levels_black=self.levels_black_field.value(),
                levels_white=self.levels_white_field.value(),
                levels_gamma=self.levels_gamma_field.value(),
                levels_out_black=self.levels_out_black_field.value(),
                levels_out_white=self.levels_out_white_field.value(),
            )
        if self._kind == "curves":
            self._curve_values[self.curve_channel] = self.curve_editor.points()
            return AdjustmentProperties(
                kind=self._kind,
                curve_points=self._curve_values["rgb"],
                curve_red=self._curve_values["red"],
                curve_green=self._curve_values["green"],
                curve_blue=self._curve_values["blue"],
            )
        if self._kind == "color_balance":
            def triple(fields: list[SliderField]) -> tuple[int, int, int]:
                return tuple(field.value() for field in fields)  # type: ignore[return-value]

            return AdjustmentProperties(
                kind=self._kind,
                color_shadows=triple(self.balance_fields["shadows"]),
                color_midtones=triple(self.balance_fields["midtones"]),
                color_highlights=triple(self.balance_fields["highlights"]),
                preserve_luminosity=self.preserve_luma_check.isChecked(),
            )
        return AdjustmentProperties(kind=self._kind)

    def _build_eyedropper_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.eyedropper_group = QButtonGroup(self)
        self.eyedropper_group.setExclusive(False)
        self.black_eyedropper_button = QToolButton()
        self.black_eyedropper_button.setText("Hút điểm đen")
        self.black_eyedropper_button.setCheckable(True)
        self.black_eyedropper_button.setToolTip(
            "Bật rồi nhấp vào ảnh xem trước để lấy mức sáng làm điểm đen."
        )
        self.white_eyedropper_button = QToolButton()
        self.white_eyedropper_button.setText("Hút điểm trắng")
        self.white_eyedropper_button.setCheckable(True)
        self.white_eyedropper_button.setToolTip(
            "Bật rồi nhấp vào ảnh xem trước để lấy mức sáng làm điểm trắng."
        )
        self.eyedropper_group.addButton(self.black_eyedropper_button)
        self.eyedropper_group.addButton(self.white_eyedropper_button)
        self.black_eyedropper_button.toggled.connect(
            lambda checked: self._set_eyedropper_mode("black", checked)
        )
        self.white_eyedropper_button.toggled.connect(
            lambda checked: self._set_eyedropper_mode("white", checked)
        )
        row.addWidget(self.black_eyedropper_button)
        row.addWidget(self.white_eyedropper_button)
        row.addWidget(
            QLabel("Bật nút rồi nhấp vào ảnh xem trước để lấy mẫu."), 1
        )
        return row

    def _set_eyedropper_mode(self, mode: str, active: bool) -> None:
        if active:
            other = (
                self.white_eyedropper_button
                if mode == "black"
                else self.black_eyedropper_button
            )
            if other.isChecked():
                other.blockSignals(True)
                other.setChecked(False)
                other.blockSignals(False)
            self._eyedropper_mode = mode
            self.preview_label.setCursor(Qt.CursorShape.CrossCursor)
        elif self._eyedropper_mode == mode:
            self._eyedropper_mode = ""
            self.preview_label.unsetCursor()

    def _on_preview_clicked(self, position) -> None:
        if not self._eyedropper_mode:
            return
        sample = self._sample_source_pixel(position)
        if sample is None:
            return
        red, green, blue = (int(value) for value in sample[:3])
        luma = round(0.2126 * red + 0.7152 * green + 0.0722 * blue)
        self._apply_eyedropper(luma)

    def _sample_source_pixel(self, position):
        pixmap = self._preview_pixmap
        if pixmap is None or pixmap.isNull():
            return None
        offset_x = (self.preview_label.width() - pixmap.width()) / 2.0
        offset_y = (self.preview_label.height() - pixmap.height()) / 2.0
        x = position.x() - offset_x
        y = position.y() - offset_y
        if x < 0 or y < 0 or x >= pixmap.width() or y >= pixmap.height():
            return None
        source = self._source
        sx = min(source.shape[1] - 1, int(x / pixmap.width() * source.shape[1]))
        sy = min(source.shape[0] - 1, int(y / pixmap.height() * source.shape[0]))
        return source[sy, sx]

    def _apply_eyedropper(self, luma: int) -> None:
        mode = self._eyedropper_mode
        if not mode:
            return
        luma = max(0, min(255, int(luma)))
        if self._kind == "levels":
            if mode == "black":
                self.levels_black_field.setValue(
                    min(luma, self.levels_white_field.value() - 1)
                )
            else:
                self.levels_white_field.setValue(
                    max(luma, self.levels_black_field.value() + 1)
                )
            self._sample_note = f" · mẫu {luma}"
            self._update_preview()
        elif self._kind == "curves":
            self._sample_note = f" · mẫu {luma}"
            self.curve_editor.add_point(luma, 0 if mode == "black" else 255)

    def _on_histogram_range_changed(self, black: int, white: int) -> None:
        if self.levels_black_field.value() != black:
            self.levels_black_field.setValue(black)
        if self.levels_white_field.value() != white:
            self.levels_white_field.setValue(white)
        self._update_preview()

    def _sync_histogram_range(self, _value: int = 0) -> None:
        self._auto_note = ""
        self.levels_histogram.set_range(
            self.levels_black_field.value(),
            self.levels_white_field.value(),
        )

    def _on_auto_levels(self) -> None:
        black, white = compute_auto_levels(self._source)
        self.levels_black_field.setValue(black)
        self.levels_white_field.setValue(white)
        self._auto_note = f" · Auto Levels {black}..{white}"
        self._update_preview()

    def _on_curve_points_changed(self, points) -> None:
        self._curve_values[self.curve_channel] = tuple(points)
        self._update_preview()

    def _on_curve_channel_changed(self, index: int) -> None:
        key = self.curve_channel_combo.itemData(index)
        if key is None or key == self.curve_channel:
            return
        self.curve_channel = key
        self._sample_note = ""
        tint = next(
            tint for channel, _label, tint in CURVE_CHANNEL_SPECS
            if channel == key
        )
        self.curve_editor.set_curve_color(tint)
        self.curve_editor.set_histogram(self._histograms[key])
        self.curve_editor.set_points(self._curve_values[key])
        self._update_preview()

    def _update_preview(self) -> None:
        result = apply_adjustment_rgba(self._source, self.properties)
        mask_note = ""
        if self._mask is not None and self._mask.shape == result.shape[:2]:
            strength = (
                self._mask[..., None].astype(np.float32) / 255.0
            )
            original = self._source[..., :3].astype(np.float32)
            result[..., :3] = np.clip(
                original
                + (result[..., :3].astype(np.float32) - original) * strength
                + 0.5,
                0.0,
                255.0,
            ).astype(np.uint8)
            mask_note = " · đã áp layer mask"
        image = numpy_rgba_to_qimage(np.ascontiguousarray(result))
        pixmap = QPixmap.fromImage(image)
        self._preview_pixmap = pixmap.scaled(
            480,
            180,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(self._preview_pixmap)
        self.info_label.setText(
            f"Xem trước {result.shape[1]} × {result.shape[0]} px · "
            f"{self.properties.summary()}{mask_note}{self._sample_note}"
            f"{self._auto_note}"
        )


class FillDialog(QDialog):
    """Tạo hoặc sửa layer tô: màu đặc hoặc gradient hai màu, có xem trước."""

    def __init__(
        self,
        properties: FillProperties | None = None,
        parent: QWidget | None = None,
        *,
        editing: bool = False,
    ) -> None:
        super().__init__(parent)
        self._editing = editing
        action = "SỬA" if editing else "TẠO"
        self.setWindowTitle(f"{action.title()} layer tô")
        self.setModal(True)
        self.setMinimumWidth(560)

        current = properties or FillProperties()
        self._color1 = QColor(*current.color)
        self._color2 = QColor(*current.color2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel(f"{action} LAYER TÔ")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        description = QLabel(
            "Layer tô phủ toàn canvas và không giữ pixel riêng: đổi màu hay "
            "gradient bất cứ lúc nào mà không mất chi tiết. Có thể dùng mask "
            "và blend mode như layer thường."
        )
        description.setWordWrap(True)
        description.setObjectName("OptionsHint")
        layout.addWidget(description)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        self.fill_type_combo = QComboBox()
        for key, label in FILL_LABELS.items():
            self.fill_type_combo.addItem(label, key)
        self.fill_type_combo.setCurrentIndex(
            max(0, self.fill_type_combo.findData(current.fill_type))
        )
        form.addRow("Kiểu tô", self.fill_type_combo)

        self.color1_row = self._build_color_row("Màu đầu", self._color1, "color1")
        form.addRow("Màu", self.color1_row)
        self.color2_row = self._build_color_row(
            "Màu cuối", self._color2, "color2"
        )
        form.addRow("Màu cuối", self.color2_row)

        self.gradient_type_combo = QComboBox()
        for key, label in GRADIENT_LABELS.items():
            self.gradient_type_combo.addItem(label, key)
        self.gradient_type_combo.setCurrentIndex(
            max(0, self.gradient_type_combo.findData(current.gradient_type))
        )
        form.addRow("Kiểu gradient", self.gradient_type_combo)

        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(0, 359)
        self.angle_spin.setValue(current.angle)
        self.angle_spin.setSuffix("°")
        form.addRow("Góc", self.angle_spin)
        layout.addLayout(form)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(160)
        self.preview_label.setObjectName("PreviewFrame")
        layout.addWidget(self.preview_label)
        self.info_label = QLabel("")
        self.info_label.setObjectName("OptionsHint")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.fill_type_combo.currentIndexChanged.connect(self._update_controls)
        self.gradient_type_combo.currentIndexChanged.connect(self._update_preview)
        self.angle_spin.valueChanged.connect(self._update_preview)
        self._update_controls()
        self._update_preview()

    def _build_color_row(
        self, title: str, color: QColor, which: str
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        swatch = QLabel()
        swatch.setFixedSize(30, 24)
        swatch.setStyleSheet(self._swatch_style(color))
        button = QPushButton(f"{title}…")
        button.clicked.connect(lambda: self._choose_color(which))
        layout.addWidget(swatch)
        layout.addWidget(button)
        layout.addStretch(1)
        if which == "color1":
            self.color1_swatch = swatch
        else:
            self.color2_swatch = swatch
        return row

    @staticmethod
    def _swatch_style(color: QColor) -> str:
        return (
            f"background-color: rgba({color.red()}, {color.green()}, "
            f"{color.blue()}, {color.alpha()}); "
            "border: 1px solid #555a63; border-radius: 4px;"
        )

    def _choose_color(self, which: str) -> None:
        target = self._color1 if which == "color1" else self._color2
        color = QColorDialog.getColor(
            target,
            self,
            "Chọn màu tô",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        if which == "color1":
            self._color1 = color
            self.color1_swatch.setStyleSheet(self._swatch_style(color))
        else:
            self._color2 = color
            self.color2_swatch.setStyleSheet(self._swatch_style(color))
        self._update_preview()

    def _update_controls(self) -> None:
        is_gradient = str(self.fill_type_combo.currentData()) == "gradient"
        self.color2_row.setEnabled(is_gradient)
        self.gradient_type_combo.setEnabled(is_gradient)
        self.angle_spin.setEnabled(is_gradient)
        self._update_preview()

    @property
    def properties(self) -> FillProperties:
        return FillProperties(
            fill_type=str(self.fill_type_combo.currentData()),
            color=tuple(self._color1.getRgb()),
            color2=tuple(self._color2.getRgb()),
            gradient_type=str(self.gradient_type_combo.currentData()),
            angle=self.angle_spin.value(),
        )

    def _update_preview(self) -> None:
        try:
            properties = self.properties
            pixels = render_fill(properties, 320, 160)
        except (ValueError, MemoryError) as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(str(exc))
            self.info_label.setText("")
            return
        image = numpy_rgba_to_qimage(pixels)
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            QPixmap.fromImage(image).scaled(
                420,
                200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.info_label.setText(
            f"{FILL_LABELS[properties.fill_type]} · {properties.summary}"
        )

    def accept(self) -> None:
        try:
            render_fill(self.properties, 32, 32)
        except (ValueError, MemoryError) as exc:
            QMessageBox.warning(self, "Màu tô không hợp lệ", str(exc))
            return
        super().accept()


class SmartObjectDialog(QDialog):
    """Sửa góc xoay, tỉ lệ và lật của smart object, kèm xem trước."""

    def __init__(
        self,
        source: np.ndarray,
        properties: SmartObjectProperties,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = np.ascontiguousarray(source)
        self._properties = properties
        self.setWindowTitle("Biến đổi smart object")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("BIẾN ĐỔI SMART OBJECT")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        description = QLabel(
            "Ảnh gốc được giữ riêng nên xoay/lật/đổi tỉ lệ nhiều lần vẫn "
            "không mất chi tiết. Rasterize chỉ khi chắc chắn không cần sửa tiếp."
        )
        description.setWordWrap(True)
        description.setObjectName("OptionsHint")
        layout.addWidget(description)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(10)
        self.source_label = QLabel(properties.source_name)
        self.source_label.setWordWrap(True)
        source_layout.addWidget(self.source_label, 1)
        source_hint = QLabel(
            "Dùng Layer ▸ Replace Contents… để đổi ảnh nguồn."
        )
        source_hint.setObjectName("OptionsHint")
        source_layout.addWidget(source_hint)
        form.addRow("Ảnh nguồn", source_row)

        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-180.0, 180.0)
        self.angle_spin.setDecimals(1)
        self.angle_spin.setSingleStep(1.0)
        self.angle_spin.setSuffix("°")
        self.angle_spin.setValue(properties.angle)
        form.addRow("Góc xoay", self.angle_spin)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(MIN_SCALE, MAX_SCALE)
        self.scale_spin.setDecimals(1)
        self.scale_spin.setSingleStep(5.0)
        self.scale_spin.setSuffix(" %")
        self.scale_spin.setValue(properties.scale)
        form.addRow("Tỉ lệ", self.scale_spin)

        flip_row = QWidget()
        flip_layout = QHBoxLayout(flip_row)
        flip_layout.setContentsMargins(0, 0, 0, 0)
        flip_layout.setSpacing(14)
        self.flip_h_check = QCheckBox("Lật ngang")
        self.flip_h_check.setChecked(properties.flip_h)
        self.flip_v_check = QCheckBox("Lật dọc")
        self.flip_v_check.setChecked(properties.flip_v)
        flip_layout.addWidget(self.flip_h_check)
        flip_layout.addWidget(self.flip_v_check)
        flip_layout.addStretch(1)
        form.addRow("Lật", flip_row)
        layout.addLayout(form)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setObjectName("PreviewFrame")
        layout.addWidget(self.preview_label)
        self.info_label = QLabel("")
        self.info_label.setObjectName("OptionsHint")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.angle_spin.valueChanged.connect(self._update_preview)
        self.scale_spin.valueChanged.connect(self._update_preview)
        self.flip_h_check.toggled.connect(self._update_preview)
        self.flip_v_check.toggled.connect(self._update_preview)
        self._update_preview()

    @property
    def properties(self) -> SmartObjectProperties:
        return replace(
            self._properties,
            angle=self.angle_spin.value(),
            scale=self.scale_spin.value(),
            flip_h=self.flip_h_check.isChecked(),
            flip_v=self.flip_v_check.isChecked(),
        )

    def _update_preview(self) -> None:
        source = downsample_rgba(self._source, 480)
        try:
            pixels = render_smart_object(source, self.properties)
        except (ValueError, MemoryError) as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(str(exc))
            self.info_label.setText("")
            return
        image = numpy_rgba_to_qimage(pixels)
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            QPixmap.fromImage(image).scaled(
                480,
                220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.info_label.setText(
            f"{self._properties.source_name} · "
            f"{self._properties.source_width} × "
            f"{self._properties.source_height} px gốc · "
            f"hiển thị {self.properties.summary}"
        )

    def accept(self) -> None:
        try:
            render_smart_object(self._source, self.properties)
        except (ValueError, MemoryError) as exc:
            QMessageBox.warning(self, "Smart object không hợp lệ", str(exc))
            return
        super().accept()


class FilterPreviewDialog(QDialog):
    """Khung chung cho hộp thoại bộ lọc có xem trước thu nhỏ và debounce."""

    def __init__(
        self,
        layer,
        parent: QWidget | None = None,
        *,
        title: str = "",
    ) -> None:
        super().__init__(parent)
        self.layer = layer
        self._source = downsample_rgba(layer.pixels, 420)
        self._preview_scale = max(
            self._source.shape[1] / max(1, layer.width),
            self._source.shape[0] / max(1, layer.height),
        )
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(title.upper())
        heading.setObjectName("PanelTitle")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self._build_controls(form)
        layout.addLayout(form)

        preview_title = QLabel("XEM TRƯỚC")
        preview_title.setObjectName("PanelTitle")
        layout.addWidget(preview_title)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(520, 220)
        self.preview_label.setStyleSheet(
            "background-color: #2b2e35; border: 1px solid #4a4f57; border-radius: 4px;"
        )
        layout.addWidget(self.preview_label)

        self.info_label = QLabel()
        self.info_label.setObjectName("OptionsHint")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._update_preview)
        self._connect_preview_signals()
        self._update_preview()

    # ------------------------------------------------------------- subclass API
    def _build_controls(self, form: QFormLayout) -> None:
        raise NotImplementedError

    def _connect_preview_signals(self) -> None:
        raise NotImplementedError

    def _filtered_preview(self):
        raise NotImplementedError

    def filtered_pixels(self):
        """Áp dụng bộ lọc ở độ phân giải đầy đủ (gọi khi bấm Áp dụng)."""
        raise NotImplementedError

    # ------------------------------------------------------------------ preview
    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _update_preview(self) -> None:
        try:
            result = self._filtered_preview()
        except (ValueError, MemoryError) as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(str(exc))
            self.info_label.setText("")
            return
        image = numpy_rgba_to_qimage(result)
        pixmap = QPixmap.fromImage(image)
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            pixmap.scaled(
                500,
                190,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.info_label.setText(
            f"Xem trước {result.shape[1]} × {result.shape[0]} px · "
            f"layer {self.layer.width} × {self.layer.height} px"
        )


class BrightnessContrastDialog(FilterPreviewDialog):
    label = "Brightness/Contrast"

    def __init__(self, layer, parent: QWidget | None = None) -> None:
        super().__init__(layer, parent, title="Brightness/Contrast")

    def _build_controls(self, form: QFormLayout) -> None:
        self.brightness_field = SliderField(-100, 100, 0)
        self.contrast_field = SliderField(-100, 100, 0)
        form.addRow("Độ sáng", self.brightness_field)
        form.addRow("Tương phản", self.contrast_field)

    def _connect_preview_signals(self) -> None:
        self.brightness_field.valueChanged.connect(self._schedule_preview)
        self.contrast_field.valueChanged.connect(self._schedule_preview)

    @property
    def brightness(self) -> int:
        return self.brightness_field.value()

    @property
    def contrast(self) -> int:
        return self.contrast_field.value()

    def _filtered_preview(self):
        return filters.brightness_contrast(
            self._source, self.brightness, self.contrast
        )

    def filtered_pixels(self):
        return filters.brightness_contrast(
            self.layer.pixels, self.brightness, self.contrast
        )


class HueSaturationDialog(FilterPreviewDialog):
    label = "Hue/Saturation"

    def __init__(self, layer, parent: QWidget | None = None) -> None:
        super().__init__(layer, parent, title="Hue/Saturation")

    def _build_controls(self, form: QFormLayout) -> None:
        self.hue_field = SliderField(-180, 180, 0, "°")
        self.saturation_field = SliderField(-100, 100, 0)
        self.lightness_field = SliderField(-100, 100, 0)
        form.addRow("Dịch màu", self.hue_field)
        form.addRow("Độ bão hoà", self.saturation_field)
        form.addRow("Độ sáng", self.lightness_field)

    def _connect_preview_signals(self) -> None:
        self.hue_field.valueChanged.connect(self._schedule_preview)
        self.saturation_field.valueChanged.connect(self._schedule_preview)
        self.lightness_field.valueChanged.connect(self._schedule_preview)

    @property
    def hue(self) -> int:
        return self.hue_field.value()

    @property
    def saturation(self) -> int:
        return self.saturation_field.value()

    @property
    def lightness(self) -> int:
        return self.lightness_field.value()

    def _filtered_preview(self):
        return filters.hue_saturation(
            self._source, self.hue, self.saturation, self.lightness
        )

    def filtered_pixels(self):
        return filters.hue_saturation(
            self.layer.pixels, self.hue, self.saturation, self.lightness
        )


class GaussianBlurDialog(FilterPreviewDialog):
    label = "Gaussian Blur"

    def __init__(self, layer, parent: QWidget | None = None) -> None:
        super().__init__(layer, parent, title="Gaussian Blur")

    def _build_controls(self, form: QFormLayout) -> None:
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.1, filters.MAX_BLUR_RADIUS)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSingleStep(0.5)
        self.radius_spin.setValue(2.0)
        self.radius_spin.setSuffix(" px")
        form.addRow("Bán kính", self.radius_spin)

    def _connect_preview_signals(self) -> None:
        self.radius_spin.valueChanged.connect(self._schedule_preview)

    @property
    def radius(self) -> float:
        return float(self.radius_spin.value())

    def _filtered_preview(self):
        return filters.gaussian_blur(
            self._source, self.radius * self._preview_scale
        )

    def filtered_pixels(self):
        return filters.gaussian_blur(self.layer.pixels, self.radius)


class UnsharpMaskDialog(FilterPreviewDialog):
    label = "Unsharp Mask"

    def __init__(self, layer, parent: QWidget | None = None) -> None:
        super().__init__(layer, parent, title="Unsharp Mask")

    def _build_controls(self, form: QFormLayout) -> None:
        self.amount_field = SliderField(0, 300, 100, " %")
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.1, 50.0)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSingleStep(0.5)
        self.radius_spin.setValue(2.0)
        self.radius_spin.setSuffix(" px")
        self.threshold_field = SliderField(0, 255, 0)
        form.addRow("Lượng làm nét", self.amount_field)
        form.addRow("Bán kính", self.radius_spin)
        form.addRow("Ngưỡng", self.threshold_field)

    def _connect_preview_signals(self) -> None:
        self.amount_field.valueChanged.connect(self._schedule_preview)
        self.radius_spin.valueChanged.connect(self._schedule_preview)
        self.threshold_field.valueChanged.connect(self._schedule_preview)

    @property
    def amount(self) -> int:
        return self.amount_field.value()

    @property
    def radius(self) -> float:
        return float(self.radius_spin.value())

    @property
    def threshold(self) -> int:
        return self.threshold_field.value()

    def _filtered_preview(self):
        return filters.unsharp_mask(
            self._source,
            self.amount,
            self.radius * self._preview_scale,
            self.threshold,
        )

    def filtered_pixels(self):
        return filters.unsharp_mask(
            self.layer.pixels, self.amount, self.radius, self.threshold
        )


class BatchStepDialog(QDialog):
    """Cấu hình một bước xử lý hàng loạt."""

    _NO_PARAMETER_KINDS = ("auto_levels", "auto_contrast", "grayscale", "invert")

    def __init__(
        self, step: BatchStep | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._editing = step is not None
        self.setWindowTitle("Sửa bước xử lý" if step else "Thêm bước xử lý")
        self.setModal(True)
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        heading = QLabel("BƯỚC XỬ LÝ HÀNG LOẠT")
        heading.setObjectName("PanelTitle")
        layout.addWidget(heading)

        self.kind_combo = QComboBox()
        for kind in BATCH_STEP_TYPES:
            self.kind_combo.addItem(BATCH_STEP_LABELS[kind], kind)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.addRow("Loại bước", self.kind_combo)
        self._stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}

        no_parameter = QWidget()
        no_layout = QVBoxLayout(no_parameter)
        no_layout.setContentsMargins(0, 4, 0, 4)
        no_layout.addWidget(
            QLabel("Bước này không có tham số, áp dụng trực tiếp lên ảnh.")
        )
        for kind in self._NO_PARAMETER_KINDS:
            self._pages[kind] = no_parameter

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.brightness_spin = QSpinBox()
        self.brightness_spin.setRange(-100, 100)
        self.contrast_spin = QSpinBox()
        self.contrast_spin.setRange(-100, 100)
        page_form.addRow("Độ sáng", self.brightness_spin)
        page_form.addRow("Tương phản", self.contrast_spin)
        self._pages["brightness_contrast"] = page

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.hue_spin = QSpinBox()
        self.hue_spin.setRange(-180, 180)
        self.hue_spin.setSuffix("°")
        self.saturation_spin = QSpinBox()
        self.saturation_spin.setRange(-100, 100)
        self.lightness_spin = QSpinBox()
        self.lightness_spin.setRange(-100, 100)
        page_form.addRow("Dịch màu", self.hue_spin)
        page_form.addRow("Bão hoà", self.saturation_spin)
        page_form.addRow("Độ sáng", self.lightness_spin)
        self._pages["hue_saturation"] = page

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.levels_black_spin = QSpinBox()
        self.levels_black_spin.setRange(0, 254)
        self.levels_white_spin = QSpinBox()
        self.levels_white_spin.setRange(1, 255)
        self.levels_white_spin.setValue(255)
        self.levels_gamma_spin = QDoubleSpinBox()
        self.levels_gamma_spin.setRange(0.1, 9.99)
        self.levels_gamma_spin.setDecimals(2)
        self.levels_gamma_spin.setSingleStep(0.05)
        self.levels_gamma_spin.setValue(1.0)
        page_form.addRow("Điểm đen", self.levels_black_spin)
        page_form.addRow("Điểm trắng", self.levels_white_spin)
        page_form.addRow("Gamma", self.levels_gamma_spin)
        self._pages["levels"] = page

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.blur_radius_spin = QDoubleSpinBox()
        self.blur_radius_spin.setRange(0.0, 100.0)
        self.blur_radius_spin.setDecimals(1)
        self.blur_radius_spin.setSingleStep(0.5)
        self.blur_radius_spin.setValue(2.0)
        self.blur_radius_spin.setSuffix(" px")
        page_form.addRow("Bán kính", self.blur_radius_spin)
        self._pages["gaussian_blur"] = page

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.unsharp_amount_spin = QSpinBox()
        self.unsharp_amount_spin.setRange(0, 300)
        self.unsharp_amount_spin.setValue(100)
        self.unsharp_radius_spin = QDoubleSpinBox()
        self.unsharp_radius_spin.setRange(0.0, 100.0)
        self.unsharp_radius_spin.setDecimals(1)
        self.unsharp_radius_spin.setSingleStep(0.5)
        self.unsharp_radius_spin.setValue(2.0)
        self.unsharp_radius_spin.setSuffix(" px")
        self.unsharp_threshold_spin = QSpinBox()
        self.unsharp_threshold_spin.setRange(0, 255)
        page_form.addRow("Mức làm nét", self.unsharp_amount_spin)
        page_form.addRow("Bán kính", self.unsharp_radius_spin)
        page_form.addRow("Ngưỡng", self.unsharp_threshold_spin)
        self._pages["unsharp_mask"] = page

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.percent_spin = QSpinBox()
        self.percent_spin.setRange(10, 400)
        self.percent_spin.setValue(100)
        self.percent_spin.setSuffix(" %")
        page_form.addRow("Tỉ lệ kích thước", self.percent_spin)
        self._pages["resize_percent"] = page

        page = QWidget()
        page_form = QFormLayout(page)
        page_form.setContentsMargins(0, 0, 0, 0)
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(16, 8000)
        self.max_size_spin.setValue(1920)
        self.max_size_spin.setSuffix(" px")
        page_form.addRow("Cạnh dài tối đa", self.max_size_spin)
        self._pages["resize_max"] = page

        for page_widget in set(self._pages.values()):
            self._stack.addWidget(page_widget)
        form.addRow(self._stack)
        layout.addLayout(form)

        hint = QLabel(
            "Ảnh nhỏ hơn cạnh dài tối đa sẽ được giữ nguyên, không phóng to."
        )
        hint.setObjectName("OptionsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Cập nhật" if self._editing else "Thêm bước"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if step is not None:
            self._load_step(step)
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        self._on_kind_changed()

    def _load_step(self, step: BatchStep) -> None:
        index = self.kind_combo.findData(step.kind)
        if index >= 0:
            self.kind_combo.setCurrentIndex(index)
        self.brightness_spin.setValue(step.brightness)
        self.contrast_spin.setValue(step.contrast)
        self.hue_spin.setValue(step.hue)
        self.saturation_spin.setValue(step.saturation)
        self.lightness_spin.setValue(step.lightness)
        self.levels_black_spin.setValue(step.levels_black)
        self.levels_white_spin.setValue(step.levels_white)
        self.levels_gamma_spin.setValue(step.levels_gamma)
        self.blur_radius_spin.setValue(step.radius)
        self.unsharp_amount_spin.setValue(step.amount)
        self.unsharp_radius_spin.setValue(step.radius)
        self.unsharp_threshold_spin.setValue(step.threshold)
        self.percent_spin.setValue(step.percent)
        self.max_size_spin.setValue(step.max_size)

    def _on_kind_changed(self, _index: int = 0) -> None:
        kind = self.kind_combo.currentData()
        page = self._pages.get(str(kind))
        if page is not None:
            self._stack.setCurrentWidget(page)

    @property
    def step(self) -> BatchStep:
        return BatchStep(
            kind=str(self.kind_combo.currentData()),
            brightness=self.brightness_spin.value(),
            contrast=self.contrast_spin.value(),
            hue=self.hue_spin.value(),
            saturation=self.saturation_spin.value(),
            lightness=self.lightness_spin.value(),
            levels_black=self.levels_black_spin.value(),
            levels_white=self.levels_white_spin.value(),
            levels_gamma=self.levels_gamma_spin.value(),
            radius=(
                self.blur_radius_spin.value()
                if self.kind_combo.currentData() == "gaussian_blur"
                else self.unsharp_radius_spin.value()
            ),
            amount=self.unsharp_amount_spin.value(),
            threshold=self.unsharp_threshold_spin.value(),
            percent=self.percent_spin.value(),
            max_size=self.max_size_spin.value(),
        )


class BatchDialog(QDialog):
    """Xử lý nhiều ảnh theo action, chạy hoàn toàn trên máy."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        preset_store: PresetStore | None = None,
        start_directory: str = "",
        inputs: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xử lý hàng loạt")
        self.setModal(True)
        self.setMinimumSize(820, 640)
        self.preset_store = preset_store
        self._steps: list[BatchStep] = []
        self.last_results: list = []
        self._cancel_requested = False
        self._running = False
        self._start_directory = start_directory or str(Path.home())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("XỬ LÝ HÀNG LOẠT · OFFLINE")
        heading.setObjectName("PanelTitle")
        layout.addWidget(heading)
        description = QLabel(
            "Áp một chuỗi bước lên nhiều ảnh. Ảnh gốc không bị ghi đè: "
            "file đầu ra thêm hậu tố và tự đánh số khi trùng tên. "
            "Mọi xử lý chạy trên máy, không gửi ảnh lên mạng."
        )
        description.setObjectName("OptionsHint")
        description.setWordWrap(True)
        layout.addWidget(description)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.input_box = self._build_input_box()
        self.steps_box = self._build_steps_box()
        body.addWidget(self.input_box, 1)
        body.addWidget(self.steps_box, 1)
        layout.addLayout(body, 1)
        self.options_box = self._build_options_box()
        layout.addWidget(self.options_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("%v/%m")
        self.status_label = QLabel("Sẵn sàng.")
        self.status_label.setObjectName("OptionsHint")
        self.status_label.setWordWrap(True)
        self.results_label = QLabel("")
        self.results_label.setObjectName("OptionsHint")
        self.results_label.setWordWrap(True)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_label)

        buttons = QHBoxLayout()
        self.cancel_run_button = QPushButton("Huỷ sau file hiện tại")
        self.cancel_run_button.setEnabled(False)
        self.cancel_run_button.clicked.connect(self._on_cancel_run)
        buttons.addWidget(self.cancel_run_button, 1)
        self.run_button = QPushButton("Bắt đầu xử lý")
        self.run_button.clicked.connect(self._on_run)
        buttons.addWidget(self.run_button)
        self.close_button = QPushButton("Đóng")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self._refresh_actions()
        if inputs:
            self.add_inputs(inputs)
        self._refresh_step_list()

    # ------------------------------------------------------------- dựng UI
    def _build_input_box(self) -> QGroupBox:
        box = QGroupBox("Ảnh đầu vào")
        column = QVBoxLayout(box)
        self.input_list = QListWidget()
        self.input_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self.input_list.setMinimumHeight(170)
        column.addWidget(self.input_list, 1)
        row = QHBoxLayout()
        add_files = QPushButton("Thêm file…")
        add_files.clicked.connect(self._on_add_files)
        add_folder = QPushButton("Thêm thư mục…")
        add_folder.clicked.connect(self._on_add_folder)
        remove = QPushButton("Bỏ chọn")
        remove.setToolTip("Bỏ các ảnh đang chọn khỏi danh sách (không xoá file).")
        remove.clicked.connect(self._remove_inputs)
        row.addWidget(add_files)
        row.addWidget(add_folder)
        row.addWidget(remove)
        column.addLayout(row)
        return box

    def _build_steps_box(self) -> QGroupBox:
        box = QGroupBox("Các bước xử lý")
        column = QVBoxLayout(box)
        self.step_list = QListWidget()
        self.step_list.setMinimumHeight(140)
        self.step_list.itemDoubleClicked.connect(
            lambda _item: self._on_edit_step()
        )
        column.addWidget(self.step_list, 1)
        row = QHBoxLayout()
        add = QPushButton("Thêm bước…")
        add.clicked.connect(self._on_add_step)
        edit = QPushButton("Sửa…")
        edit.clicked.connect(self._on_edit_step)
        remove = QPushButton("Xoá")
        remove.clicked.connect(self._on_remove_step)
        up = QPushButton("Lên")
        up.clicked.connect(lambda: self._move_step(-1))
        down = QPushButton("Xuống")
        down.clicked.connect(lambda: self._move_step(1))
        for widget in (add, edit, remove, up, down):
            row.addWidget(widget)
        column.addLayout(row)

        self.action_combo = QComboBox()
        self.action_combo.setMinimumWidth(150)
        self.action_combo.activated.connect(lambda _index: self._on_load_action())
        self.load_action_button = QPushButton("Tải action")
        self.load_action_button.clicked.connect(self._on_load_action)
        self.save_action_button = QPushButton("Lưu action…")
        self.save_action_button.clicked.connect(self._on_save_action)
        self.delete_action_button = QPushButton("Xoá action")
        self.delete_action_button.clicked.connect(self._on_delete_action)
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Action:"))
        action_row.addWidget(self.action_combo, 1)
        action_row.addWidget(self.load_action_button)
        action_row.addWidget(self.save_action_button)
        action_row.addWidget(self.delete_action_button)
        column.addLayout(action_row)
        if self.preset_store is None:
            for widget in (
                self.action_combo,
                self.load_action_button,
                self.save_action_button,
                self.delete_action_button,
            ):
                widget.setEnabled(False)
        return box

    def _build_options_box(self) -> QGroupBox:
        box = QGroupBox("Đầu ra")
        form = QFormLayout(box)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        folder_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(self._start_directory)
        self.output_dir_edit.setPlaceholderText("Thư mục nhận ảnh đã xử lý…")
        folder_row.addWidget(self.output_dir_edit, 1)
        browse = QPushButton("Chọn…")
        browse.clicked.connect(self._on_browse_output)
        folder_row.addWidget(browse)
        form.addRow("Thư mục đầu ra", folder_row)

        self.format_combo = QComboBox()
        for key, label in OUTPUT_FORMAT_LABELS.items():
            self.format_combo.addItem(label, key)
        self.format_combo.currentIndexChanged.connect(
            self._on_format_changed
        )
        form.addRow("Định dạng", self.format_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(92)
        self.quality_spin.setSuffix(" %")
        form.addRow("Chất lượng", self.quality_spin)

        self.suffix_edit = QLineEdit(DEFAULT_SUFFIX)
        self.suffix_edit.setMaxLength(24)
        form.addRow("Hậu tố tên file", self.suffix_edit)

        self.overwrite_check = QCheckBox(
            "Ghi đè file đầu ra đã có (không bao giờ ghi đè ảnh gốc)"
        )
        form.addRow("", self.overwrite_check)
        self._on_format_changed()
        return box

    # ------------------------------------------------------------- đầu vào
    def add_inputs(self, paths) -> int:
        existing: set[str] = set()
        for path in self.inputs():
            try:
                existing.add(str(path.resolve()))
            except OSError:
                existing.add(str(path))
        added = 0
        for item in paths:
            path = Path(item)
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                continue
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key in existing:
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.input_list.addItem(item)
            existing.add(key)
            added += 1
            if len(existing) >= MAX_BATCH_FILES:
                break
        self._refresh_summary()
        return added

    def inputs(self) -> list[Path]:
        paths: list[Path] = []
        for index in range(self.input_list.count()):
            item = self.input_list.item(index)
            stored = item.data(Qt.ItemDataRole.UserRole)
            paths.append(Path(str(stored)) if stored else Path(item.text()))
        return paths

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Thêm ảnh",
            self._start_directory,
            IMAGE_OPEN_FILTER,
        )
        if files:
            self.add_inputs(files)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Thêm thư mục ảnh", self._start_directory
        )
        if not folder:
            return
        try:
            paths = sorted(
                path
                for path in Path(folder).iterdir()
                if path.is_file()
                and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            )
        except OSError as exc:
            QMessageBox.warning(
                self, "Không đọc được thư mục", str(exc)
            )
            return
        self.add_inputs(paths)

    def _remove_inputs(self) -> None:
        for item in self.input_list.selectedItems():
            self.input_list.takeItem(self.input_list.row(item))
        self._refresh_summary()

    # --------------------------------------------------------------- bước
    def steps(self) -> tuple[BatchStep, ...]:
        return tuple(self._steps)

    def set_steps(self, steps) -> None:
        self._steps = [
            step for step in steps if isinstance(step, BatchStep)
        ]
        self._refresh_step_list()

    def _refresh_step_list(self) -> None:
        self.step_list.clear()
        for index, step in enumerate(self._steps, start=1):
            self.step_list.addItem(
                f"{index}. {step.label} — {step.summary()}"
            )
        self._refresh_summary()

    def _selected_step_index(self) -> int:
        row = self.step_list.currentRow()
        if 0 <= row < len(self._steps):
            return row
        return -1

    def _on_add_step(self) -> None:
        dialog = BatchStepDialog(parent=self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        self._steps.append(dialog.step)
        self._refresh_step_list()

    def _on_edit_step(self) -> None:
        index = self._selected_step_index()
        if index < 0:
            QMessageBox.information(
                self, "Chưa chọn bước", "Hãy chọn một bước để sửa."
            )
            return
        dialog = BatchStepDialog(self._steps[index], parent=self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        self._steps[index] = dialog.step
        self._refresh_step_list()

    def _on_remove_step(self) -> None:
        index = self._selected_step_index()
        if index >= 0:
            del self._steps[index]
            self._refresh_step_list()

    def _move_step(self, delta: int) -> None:
        index = self._selected_step_index()
        target = index + delta
        if index < 0 or not 0 <= target < len(self._steps):
            return
        self._steps[index], self._steps[target] = (
            self._steps[target],
            self._steps[index],
        )
        self._refresh_step_list()
        self.step_list.setCurrentRow(target)

    # -------------------------------------------------------------- action
    def _refresh_actions(self, select: str | None = None) -> None:
        combo = self.action_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— Action đã lưu —", "")
        if self.preset_store is not None:
            try:
                presets = self.preset_store.list("action")
            except PresetError:
                presets = []
            for preset in presets:
                combo.addItem(preset.name, preset.name)
        combo.blockSignals(False)
        if select:
            index = combo.findData(select)
            if index >= 0:
                combo.setCurrentIndex(index)
        if self.delete_action_button is not None:
            self.delete_action_button.setEnabled(bool(combo.currentData()))

    def apply_action(self, name: str) -> bool:
        if self.preset_store is None:
            return False
        try:
            action = self.preset_store.load_action(name)
        except PresetError as exc:
            QMessageBox.warning(self, "Không tải được action", str(exc))
            return False
        if action is None:
            return False
        self.set_steps(action.steps)
        index = self.action_combo.findData(name)
        if index >= 0:
            self.action_combo.setCurrentIndex(index)
        self.status_label.setText(f"Đã tải action '{name}': {action.summary()}")
        return True

    def _on_load_action(self) -> None:
        name = self.action_combo.currentData()
        if name:
            self.apply_action(str(name))

    def _on_save_action(self) -> None:
        if self.preset_store is None:
            return
        if not self._steps:
            QMessageBox.information(
                self, "Chưa có bước", "Hãy thêm ít nhất một bước trước khi lưu action."
            )
            return
        suggested = str(self.action_combo.currentData() or "Action hàng loạt")
        name, accepted = QInputDialog.getText(
            self, "Lưu action", "Tên action:", text=suggested
        )
        if not accepted:
            return
        name = name.strip()
        if not name:
            QMessageBox.information(
                self, "Thiếu tên", "Tên action không được để trống."
            )
            return
        existing = self.preset_store.get("action", name)
        if existing is not None:
            answer = QMessageBox.question(
                self,
                "Ghi đè action",
                f"Action '{name}' đã tồn tại. Ghi đè?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            saved = self.preset_store.save_action(
                name,
                BatchAction(name=name, steps=tuple(self._steps)),
                overwrite=existing is not None,
            )
        except (PresetError, ValueError) as exc:
            QMessageBox.warning(self, "Không lưu được action", str(exc))
            return
        self._refresh_actions(select=saved.name)
        self.status_label.setText(f"Đã lưu action '{saved.name}'.")

    def _on_delete_action(self) -> None:
        if self.preset_store is None:
            return
        name = self.action_combo.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Xoá action",
            f"Xoá action '{name}' khỏi thư viện?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.preset_store.delete("action", str(name))
        except PresetError as exc:
            QMessageBox.warning(self, "Không xoá được action", str(exc))
            return
        self._refresh_actions()

    # -------------------------------------------------------------- đầu ra
    def _on_browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục đầu ra", self.output_directory()
        )
        if folder:
            self.output_dir_edit.setText(folder)

    def output_directory(self) -> str:
        text = self.output_dir_edit.text().strip()
        return text or self._start_directory

    def _on_format_changed(self, _index: int = 0) -> None:
        fmt = self.format_combo.currentData()
        self.quality_spin.setEnabled(fmt in ("jpeg", "webp"))

    # ---------------------------------------------------------------- chạy
    def _refresh_summary(self) -> None:
        if self._running:
            return
        self.status_label.setText(
            f"{self.input_list.count()} ảnh đầu vào · "
            f"{len(self._steps)} bước xử lý."
        )

    def _set_running(self, running: bool) -> None:
        self._running = running
        for widget in (
            self.input_box,
            self.steps_box,
            self.options_box,
            self.run_button,
            self.close_button,
        ):
            widget.setEnabled(not running)
        self.cancel_run_button.setEnabled(running)
        if running:
            self._cancel_requested = False

    def _on_cancel_run(self) -> None:
        self._cancel_requested = True
        self.cancel_run_button.setEnabled(False)
        self.status_label.setText(
            "Sẽ dừng sau khi xử lý xong file hiện tại…"
        )

    def _on_progress(self, done: int, total: int, source: Path) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status_label.setText(f"Đang xử lý {done}/{total}: {source.name}")
        QApplication.processEvents()

    def _on_run(self) -> None:
        if self._running:
            return
        sources = self.inputs()
        if not sources:
            QMessageBox.warning(
                self,
                "Chưa có ảnh",
                "Hãy thêm ít nhất một ảnh đầu vào.",
            )
            return
        if not self._steps:
            QMessageBox.warning(
                self,
                "Chưa có bước",
                "Hãy thêm ít nhất một bước xử lý.",
            )
            return
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(
                self,
                "Chưa có thư mục",
                "Hãy chọn thư mục đầu ra.",
            )
            return
        try:
            runner = BatchRunner(
                self._steps,
                output_dir,
                output_format=str(self.format_combo.currentData()),
                quality=self.quality_spin.value(),
                suffix=self.suffix_edit.text(),
                overwrite=self.overwrite_check.isChecked(),
            )
        except BatchError as exc:
            QMessageBox.warning(self, "Chưa chạy được", str(exc))
            return

        self._set_running(True)
        self.progress.setRange(0, len(sources))
        self.progress.setValue(0)
        self.results_label.clear()
        try:
            results = runner.run(
                sources,
                progress=self._on_progress,
                cancel=lambda: self._cancel_requested,
            )
        except BatchError as exc:
            self._set_running(False)
            QMessageBox.warning(self, "Không chạy được", str(exc))
            return
        self.last_results = results
        self._set_running(False)
        self._show_results(results, output_dir)

    def _show_results(self, results, output_dir: str) -> None:
        succeeded = sum(1 for item in results if item.status == "ok")
        failed = [item for item in results if item.status == "failed"]
        cancelled = sum(1 for item in results if item.status == "cancelled")
        parts = [f"{succeeded} thành công"]
        if failed:
            parts.append(f"{len(failed)} lỗi")
        if cancelled:
            parts.append(f"{cancelled} đã huỷ")
        summary = (
            f"Hoàn tất: {', '.join(parts)}. "
            f"Thư mục đầu ra: {output_dir}"
        )
        self.status_label.setText(summary)
        lines = []
        for item in failed[:5]:
            lines.append(f"• {item.source.name}: {item.message}")
        if len(failed) > 5:
            lines.append(f"… và {len(failed) - 5} lỗi khác.")
        self.results_label.setText("\n".join(lines))

