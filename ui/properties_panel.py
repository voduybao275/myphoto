"""Panel Properties: thông tin tài liệu và thuộc tính layer đang chọn."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config.settings import APP_VERSION
from core.adjustment_layer import ADJUSTMENT_LABELS
from core.document import Document
from core.fill_layer import FILL_LABELS, GRADIENT_LABELS
from core.layer import BLEND_MODE_LABELS, Layer, LayerKind
from core.shape_layer import (
    MAX_CORNER_RADIUS,
    MAX_SHAPE_SIZE,
    MAX_STROKE_WIDTH,
    SHAPE_LABELS,
)
from core.text_layer import (
    ALIGNMENT_LABELS,
    MAX_FONT_SIZE,
    MAX_LETTER_SPACING,
    MAX_LINE_SPACING,
    MIN_LETTER_SPACING,
    MIN_LINE_SPACING,
    PATH_LABELS,
    WARP_LABELS,
    TextProperties,
)
from ui import icons

_STYLE_OPTIONS = (
    ("Regular", "regular"),
    ("Bold", "bold"),
    ("Italic", "italic"),
    ("Bold Italic", "bold_italic"),
)
_LEADING_VALUES = (1.0, 0.5, 0.75, 0.9, 1.1, 1.2, 1.4, 1.6, 2.0, 3.0, 4.0, 5.0)
_SHAPE_CORNERS = (
    ("TL", "góc trên-trái"),
    ("TR", "góc trên-phải"),
    ("BR", "góc dưới-phải"),
    ("BL", "góc dưới-trái"),
)
_PATH_OPERATIONS = (
    ("Hợp", "Kết hợp đường dẫn (Union)"),
    ("Trừ", "Trừ đường dẫn (Subtract)"),
    ("Giao", "Giao đường dẫn (Intersect)"),
    ("Loại", "Loại trừ phần chồng (Exclude)"),
)


class _Section(QWidget):
    """Nhóm thuộc tính có tiêu đề bấm được để thu gọn/mở rộng."""

    def __init__(
        self,
        title: str,
        *,
        reset_tooltip: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        self.toggle = QToolButton()
        self.toggle.setObjectName("PropSection")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self._set_expanded)
        header_layout.addWidget(self.toggle)
        header_layout.addStretch(1)
        self.reset_button: QToolButton | None = None
        if reset_tooltip:
            self.reset_button = QToolButton()
            self.reset_button.setIcon(icons.icon("reset"))
            self.reset_button.setAutoRaise(True)
            self.reset_button.setEnabled(False)
            self.reset_button.setToolTip(reset_tooltip)
            header_layout.addWidget(self.reset_button)
        layout.addWidget(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        layout.addWidget(self.body)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(expanded)


class PropertiesPanel(QWidget):
    message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PropertiesPanel")
        self.document: Document | None = None
        self._connections: list[tuple[object, object]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("PropertiesScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        content.setObjectName("PropertiesContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self._scroll.setWidget(content)
        root.addWidget(self._scroll, 1)

        self.text_properties = self._build_text_properties()
        layout.addWidget(self.text_properties)
        self._set_text_properties_visible(False)

        self.shape_properties = self._build_shape_properties()
        layout.addWidget(self.shape_properties)
        self._set_shape_properties_visible(False)

        title = QLabel("DOCUMENT")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        self._values: dict[str, QLabel] = {}
        rows = [
            ("name", "Tên tài liệu"),
            ("size", "Kích thước"),
            ("resolution", "Độ phân giải"),
            ("mode", "Chế độ màu"),
            ("layers", "Số layer"),
            ("active", "Layer đang chọn"),
            ("layer_info", "Layer"),
            ("file", "File dự án"),
        ]
        for row, (key, label_text) in enumerate(rows):
            key_label = QLabel(label_text)
            key_label.setObjectName("PropKey")
            key_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            value_label = QLabel("—")
            value_label.setObjectName("PropValue")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(key_label, row, 0)
            grid.addWidget(value_label, row, 1)
            self._values[key] = value_label
        layout.addLayout(grid)
        layout.addStretch(1)

        footer_container = QWidget()
        footer_layout = QVBoxLayout(footer_container)
        footer_layout.setContentsMargins(12, 0, 12, 8)
        footer_layout.setSpacing(0)
        footer = QLabel(f"My Photo Studio {APP_VERSION}")
        footer.setObjectName("WelcomeVersion")
        footer_layout.addWidget(footer)
        root.addWidget(footer_container)

    # ------------------------------------------------------------- text panel
    def _build_text_properties(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(7)
        badge = QLabel()
        badge.setPixmap(icons.pixmap("text", 18))
        header_layout.addWidget(badge)
        title = QLabel("Type Layer")
        title.setObjectName("PropLayerType")
        title_font = QFont(title.font())
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title, 1)
        layout.addWidget(header)

        self.transform_section = _Section(
            "Transform",
            reset_tooltip=(
                "Chưa hỗ trợ đặt lại Transform của layer văn bản.\n"
                "Dùng Ctrl+Z để hoàn tác từng thay đổi."
            ),
        )
        self._build_transform(self.transform_section.body_layout)
        layout.addWidget(self.transform_section)

        self.character_section = _Section("Character")
        self._build_character(self.character_section.body_layout)
        layout.addWidget(self.character_section)
        return container

    def _build_transform(self, layout: QVBoxLayout) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        self.text_link_button = QToolButton()
        self.text_link_button.setIcon(icons.icon("link"))
        self.text_link_button.setCheckable(True)
        self.text_link_button.setEnabled(False)
        self.text_link_button.setToolTip(
            "Chưa hỗ trợ khoá tỉ lệ khi sửa kích thước trực tiếp.\n"
            "Đổi cỡ chữ để thay đổi kích thước layer văn bản."
        )
        grid.addWidget(self.text_link_button, 0, 0, 2, 1)

        self.text_width = self._make_readonly_spin(
            "Chiều rộng hiện tại của layer văn bản.\n"
            "Kích thước do nội dung và cỡ chữ quyết định."
        )
        self.text_height = self._make_readonly_spin(
            "Chiều cao hiện tại của layer văn bản.\n"
            "Kích thước do nội dung và cỡ chữ quyết định."
        )
        self.text_x = QSpinBox()
        self.text_x.setRange(-100_000, 100_000)
        self.text_x.setSuffix(" px")
        self.text_x.setKeyboardTracking(False)
        self.text_x.setToolTip("Toạ độ X của layer trên canvas (có Undo).")
        self.text_x.editingFinished.connect(self._apply_text_offset)
        self.text_y = QSpinBox()
        self.text_y.setRange(-100_000, 100_000)
        self.text_y.setSuffix(" px")
        self.text_y.setKeyboardTracking(False)
        self.text_y.setToolTip("Toạ độ Y của layer trên canvas (có Undo).")
        self.text_y.editingFinished.connect(self._apply_text_offset)

        for column, text in ((1, "W"), (3, "X")):
            label = QLabel(text)
            label.setObjectName("PropKey")
            grid.addWidget(label, 0, column)
        grid.addWidget(self.text_width, 0, 2)
        grid.addWidget(self.text_x, 0, 4)
        for column, text in ((1, "H"), (3, "Y")):
            label = QLabel(text)
            label.setObjectName("PropKey")
            grid.addWidget(label, 1, column)
        grid.addWidget(self.text_height, 1, 2)
        grid.addWidget(self.text_y, 1, 4)

        angle_label = QLabel("∠")
        angle_label.setObjectName("PropKey")
        angle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(angle_label, 2, 1)
        self.text_angle = QDoubleSpinBox()
        self.text_angle.setRange(-360.0, 360.0)
        self.text_angle.setDecimals(2)
        self.text_angle.setSuffix("°")
        self.text_angle.setReadOnly(True)
        self.text_angle.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.text_angle.setToolTip(
            "Layer văn bản chưa lưu góc xoay riêng.\n"
            "Dùng Edit ▸ Transform ▸ Rotate… (thao tác này sẽ rasterize layer)."
        )
        grid.addWidget(self.text_angle, 2, 2)

        self.text_flip_h = QToolButton()
        self.text_flip_h.setIcon(icons.icon("flip_h"))
        self.text_flip_h.setEnabled(False)
        self.text_flip_h.setToolTip(
            "Chưa hỗ trợ lật văn bản không phá huỷ.\n"
            "Dùng Edit ▸ Transform ▸ Flip Horizontal (sẽ rasterize layer)."
        )
        self.text_flip_v = QToolButton()
        self.text_flip_v.setIcon(icons.icon("flip_v"))
        self.text_flip_v.setEnabled(False)
        self.text_flip_v.setToolTip(
            "Chưa hỗ trợ lật văn bản không phá huỷ.\n"
            "Dùng Edit ▸ Transform ▸ Flip Vertical (sẽ rasterize layer)."
        )
        grid.addWidget(self.text_flip_h, 2, 3)
        grid.addWidget(self.text_flip_v, 2, 4)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(4, 1)
        layout.addLayout(grid)

    def _build_character(self, layout: QVBoxLayout) -> None:
        self.text_font = QFontComboBox()
        self.text_font.setToolTip(
            "Font áp dụng cho toàn bộ văn bản.\n"
            "Muốn định dạng từng đoạn, dùng Type ▸ Edit Text…"
        )
        self.text_font.currentFontChanged.connect(self._on_font_changed)
        layout.addWidget(self.text_font)

        self.text_style = QComboBox()
        for label, key in _STYLE_OPTIONS:
            self.text_style.addItem(label, key)
        self.text_style.setToolTip(
            "Kiểu chữ áp dụng cho toàn bộ văn bản (có Undo)."
        )
        self.text_style.currentIndexChanged.connect(self._on_style_changed)
        layout.addWidget(self.text_style)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(6)
        metrics.setVerticalSpacing(5)

        self.text_size = QSpinBox()
        self.text_size.setRange(1, MAX_FONT_SIZE)
        self.text_size.setSuffix(" px")
        self.text_size.setKeyboardTracking(False)
        self.text_size.setToolTip("Cỡ chữ áp dụng cho toàn bộ văn bản (có Undo).")
        self.text_size.editingFinished.connect(self._on_size_changed)
        self.text_leading = QComboBox()
        for value in _LEADING_VALUES:
            label = "(Auto)" if value == 1.0 else f"{value:g}×"
            self.text_leading.addItem(label, value)
        self.text_leading.setToolTip(
            "Giãn dòng cho toàn bộ văn bản; (Auto) tương đương 1,0×."
        )
        self.text_leading.currentIndexChanged.connect(self._on_leading_changed)
        metrics.addWidget(self._metric_label("Cỡ"), 0, 0)
        metrics.addWidget(self.text_size, 0, 1)
        metrics.addWidget(self._metric_label("Dòng"), 0, 2)
        metrics.addWidget(self.text_leading, 0, 3)

        self.text_kerning = QSpinBox()
        self.text_kerning.setRange(-200, 200)
        self.text_kerning.setValue(0)
        self.text_kerning.setEnabled(False)
        self.text_kerning.setToolTip(
            "Panel chưa hỗ trợ kerning cấp layer.\n"
            "Kerning theo cặp ký tự được chỉnh trong Type ▸ Edit Text…"
        )
        self.text_tracking = QSpinBox()
        self.text_tracking.setRange(MIN_LETTER_SPACING, MAX_LETTER_SPACING)
        self.text_tracking.setSuffix(" px")
        self.text_tracking.setKeyboardTracking(False)
        self.text_tracking.setToolTip(
            "Tracking (giãn chữ) áp dụng cho toàn bộ văn bản (có Undo)."
        )
        self.text_tracking.editingFinished.connect(self._on_tracking_changed)
        metrics.addWidget(self._metric_label("Kerning"), 1, 0)
        metrics.addWidget(self.text_kerning, 1, 1)
        metrics.addWidget(self._metric_label("Tracking"), 1, 2)
        metrics.addWidget(self.text_tracking, 1, 3)
        metrics.setColumnStretch(1, 1)
        metrics.setColumnStretch(3, 1)
        layout.addLayout(metrics)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(6)
        color_row.addWidget(self._metric_label("Color"))
        self.text_color_button = QPushButton()
        self.text_color_button.setFixedSize(64, 24)
        self.text_color_button.setToolTip("Nhấp để chọn màu văn bản (có Undo).")
        self.text_color_button.clicked.connect(self._choose_text_color)
        color_row.addWidget(self.text_color_button)
        color_row.addStretch(1)
        layout.addLayout(color_row)

    @staticmethod
    def _metric_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PropKey")
        return label

    @staticmethod
    def _make_readonly_spin(tooltip: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1_000_000.0)
        spin.setDecimals(2)
        spin.setSuffix(" px")
        spin.setReadOnly(True)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        spin.setToolTip(tooltip)
        return spin

    def _set_text_properties_visible(self, visible: bool) -> None:
        self.text_properties.setVisible(visible)

    def _refresh_text_properties(self, active: Layer | None) -> None:
        is_text = bool(
            active is not None
            and active.kind == LayerKind.TEXT
            and active.text is not None
        )
        self._set_text_properties_visible(is_text)
        if not is_text:
            return
        properties = active.text
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.text_x,
                self.text_y,
                self.text_font,
                self.text_style,
                self.text_size,
                self.text_leading,
                self.text_tracking,
            )
        ]
        try:
            self.text_width.setValue(float(active.width))
            self.text_height.setValue(float(active.height))
            self.text_x.setValue(active.offset_x)
            self.text_y.setValue(active.offset_y)
            self.text_angle.setValue(0.0)
            self.text_font.setCurrentFont(
                QFont(properties.font_family) if properties.font_family else QFont()
            )
            if properties.bold and properties.italic:
                style_key = "bold_italic"
            elif properties.bold:
                style_key = "bold"
            elif properties.italic:
                style_key = "italic"
            else:
                style_key = "regular"
            style_index = self.text_style.findData(style_key)
            self.text_style.setCurrentIndex(max(0, style_index))
            self.text_size.setValue(properties.font_size)
            self._set_leading_value(properties.line_spacing)
            self.text_tracking.setValue(properties.letter_spacing)
            color = QColor(*properties.color)
            border = self.palette().mid().color().name()
            self.text_color_button.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, "
                f"{color.blue()}, {color.alpha()}); "
                f"border: 1px solid {border}; border-radius: 4px;"
            )
            self.text_color_button.setToolTip(
                f"RGBA({color.red()}, {color.green()}, {color.blue()}, "
                f"{color.alpha()}) — nhấp để chọn màu."
            )
        finally:
            del blockers

    def _set_leading_value(self, value: float) -> None:
        index = -1
        for item_index in range(self.text_leading.count()):
            data = self.text_leading.itemData(item_index)
            if data is not None and abs(float(data) - float(value)) < 1e-6:
                index = item_index
                break
        if index < 0:
            self.text_leading.addItem(f"{value:g}×", float(value))
            index = self.text_leading.count() - 1
        self.text_leading.setCurrentIndex(index)

    def _current_text_layer(self) -> Layer | None:
        document = self.document
        if document is None:
            return None
        layer = document.active_layer
        if layer is None or layer.kind != LayerKind.TEXT or layer.text is None:
            return None
        return layer

    def _updated_text(self, **changes) -> TextProperties:
        layer = self._current_text_layer()
        properties = layer.text
        runs = properties.runs
        run_fields = {
            key: value
            for key, value in changes.items()
            if key in ("font_family", "font_size", "color", "bold", "italic")
        }
        if run_fields:
            runs = tuple(replace(run, **run_fields) for run in runs)
        property_fields = {
            key: value
            for key, value in changes.items()
            if key in ("line_spacing", "letter_spacing")
        }
        return replace(properties, runs=runs, **property_fields)

    def _apply_text_properties(self, properties, action_label: str) -> bool:
        document = self.document
        layer = self._current_text_layer()
        if document is None or layer is None:
            return False
        try:
            changed = document.update_text_layer(properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.warning(self, "Thuộc tính văn bản", str(exc))
            self.refresh()
            return False
        if changed:
            self.message.emit(
                f"Đã cập nhật {action_label} (Ctrl+Z để hoàn tác)."
            )
        return changed

    def _apply_text_offset(self) -> None:
        document = self.document
        layer = self._current_text_layer()
        if document is None or layer is None:
            return
        if document.set_layer_offset(
            layer, self.text_x.value(), self.text_y.value()
        ):
            self.message.emit(
                "Đã di chuyển layer văn bản (Ctrl+Z để hoàn tác)."
            )

    def _on_font_changed(self, font: QFont) -> None:
        layer = self._current_text_layer()
        if layer is None:
            return
        family = font.family().strip()
        if not family or family == layer.text.font_family:
            return
        self._apply_text_properties(
            self._updated_text(font_family=family), "font văn bản"
        )

    def _on_style_changed(self, _index: int) -> None:
        layer = self._current_text_layer()
        if layer is None:
            return
        kind = self.text_style.currentData()
        bold = kind in ("bold", "bold_italic")
        italic = kind in ("italic", "bold_italic")
        if bold == layer.text.bold and italic == layer.text.italic:
            return
        self._apply_text_properties(
            self._updated_text(bold=bold, italic=italic), "kiểu chữ"
        )

    def _on_size_changed(self) -> None:
        layer = self._current_text_layer()
        if layer is None:
            return
        size = self.text_size.value()
        if size == layer.text.font_size:
            return
        self._apply_text_properties(
            self._updated_text(font_size=size), "cỡ chữ"
        )

    def _on_leading_changed(self, _index: int) -> None:
        layer = self._current_text_layer()
        if layer is None:
            return
        data = self.text_leading.currentData()
        if data is None:
            return
        spacing = round(float(data), 2)
        if abs(spacing - layer.text.line_spacing) < 1e-9:
            return
        self._apply_text_properties(
            self._updated_text(line_spacing=spacing), "giãn dòng"
        )

    def _on_tracking_changed(self) -> None:
        layer = self._current_text_layer()
        if layer is None:
            return
        tracking = self.text_tracking.value()
        if tracking == layer.text.letter_spacing:
            return
        self._apply_text_properties(
            self._updated_text(letter_spacing=tracking), "tracking"
        )

    def _choose_text_color(self) -> None:
        layer = self._current_text_layer()
        if layer is None:
            return
        color = QColorDialog.getColor(
            QColor(*layer.text.color),
            self,
            "Chọn màu văn bản",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self.set_text_color(color)

    def set_text_color(self, color: QColor) -> bool:
        if not color.isValid() or self._current_text_layer() is None:
            return False
        return self._apply_text_properties(
            self._updated_text(
                color=(
                    color.red(),
                    color.green(),
                    color.blue(),
                    color.alpha(),
                )
            ),
            "màu văn bản",
        )

    # ------------------------------------------------------------ shape panel
    def _build_shape_properties(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(7)
        badge = QLabel()
        badge.setPixmap(icons.pixmap("shape", 18))
        header_layout.addWidget(badge)
        title = QLabel("Live Shape Properties")
        title.setObjectName("PropLayerType")
        title_font = QFont(title.font())
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title, 1)
        layout.addWidget(header)
        self.shape_kind_label = QLabel("")
        self.shape_kind_label.setObjectName("OptionsHint")
        layout.addWidget(self.shape_kind_label)

        transform = QGridLayout()
        transform.setContentsMargins(0, 0, 0, 0)
        transform.setHorizontalSpacing(6)
        transform.setVerticalSpacing(5)

        self.shape_link_button = QToolButton()
        self.shape_link_button.setIcon(icons.icon("link"))
        self.shape_link_button.setCheckable(True)
        self.shape_link_button.setToolTip(
            "Bật để giữ tỉ lệ khi sửa W/H.\n"
            "Tắt để đổi chiều rộng và chiều cao độc lập."
        )
        transform.addWidget(self.shape_link_button, 0, 0, 2, 1)

        self.shape_width = QSpinBox()
        self.shape_width.setRange(1, MAX_SHAPE_SIZE)
        self.shape_width.setSuffix(" px")
        self.shape_width.setKeyboardTracking(False)
        self.shape_width.setToolTip("Chiều rộng hình khối (có Undo).")
        self.shape_width.editingFinished.connect(
            lambda: self._apply_shape_size("width")
        )
        self.shape_height = QSpinBox()
        self.shape_height.setRange(1, MAX_SHAPE_SIZE)
        self.shape_height.setSuffix(" px")
        self.shape_height.setKeyboardTracking(False)
        self.shape_height.setToolTip("Chiều cao hình khối (có Undo).")
        self.shape_height.editingFinished.connect(
            lambda: self._apply_shape_size("height")
        )
        self.shape_x = QSpinBox()
        self.shape_x.setRange(-100_000, 100_000)
        self.shape_x.setSuffix(" px")
        self.shape_x.setKeyboardTracking(False)
        self.shape_x.setToolTip("Toạ độ X của layer trên canvas (có Undo).")
        self.shape_x.editingFinished.connect(self._apply_shape_offset)
        self.shape_y = QSpinBox()
        self.shape_y.setRange(-100_000, 100_000)
        self.shape_y.setSuffix(" px")
        self.shape_y.setKeyboardTracking(False)
        self.shape_y.setToolTip("Toạ độ Y của layer trên canvas (có Undo).")
        self.shape_y.editingFinished.connect(self._apply_shape_offset)

        for column, text in ((1, "W"), (3, "H")):
            label = QLabel(text)
            label.setObjectName("PropKey")
            transform.addWidget(label, 0, column)
        transform.addWidget(self.shape_width, 0, 2)
        transform.addWidget(self.shape_height, 0, 4)
        for column, text in ((1, "X"), (3, "Y")):
            label = QLabel(text)
            label.setObjectName("PropKey")
            transform.addWidget(label, 1, column)
        transform.addWidget(self.shape_x, 1, 2)
        transform.addWidget(self.shape_y, 1, 4)
        transform.setColumnStretch(2, 1)
        transform.setColumnStretch(4, 1)
        layout.addLayout(transform)

        appearance = QGridLayout()
        appearance.setContentsMargins(0, 0, 0, 0)
        appearance.setHorizontalSpacing(6)
        appearance.setVerticalSpacing(5)

        self._shape_fill_color = QColor(59, 110, 165, 255)
        self._shape_stroke_color = QColor(255, 255, 255, 255)
        self.shape_fill_check = QCheckBox("Tô")
        self.shape_fill_check.setToolTip(
            "Bật/tắt màu tô. Tắt tô khi chưa có viền sẽ tự bật viền 1 px."
        )
        self.shape_fill_check.toggled.connect(self._on_shape_fill_toggled)
        appearance.addWidget(self.shape_fill_check, 0, 0)
        self.shape_fill_button = QPushButton()
        self.shape_fill_button.setFixedSize(52, 22)
        self.shape_fill_button.setToolTip("Nhấp để chọn màu tô (có Undo).")
        self.shape_fill_button.clicked.connect(self._choose_shape_fill_color)
        appearance.addWidget(self.shape_fill_button, 0, 1, 1, 2)

        stroke_label = QLabel("Viền")
        stroke_label.setObjectName("PropKey")
        appearance.addWidget(stroke_label, 1, 0)
        self.shape_stroke_button = QPushButton()
        self.shape_stroke_button.setFixedSize(52, 22)
        self.shape_stroke_button.setToolTip(
            "Nhấp để chọn màu viền (có Undo).\nMàu chỉ hiển thị khi độ dày viền lớn hơn 0."
        )
        self.shape_stroke_button.clicked.connect(self._choose_shape_stroke_color)
        appearance.addWidget(self.shape_stroke_button, 1, 1)
        self.shape_stroke_width = QSpinBox()
        self.shape_stroke_width.setRange(0, MAX_STROKE_WIDTH)
        self.shape_stroke_width.setSuffix(" px")
        self.shape_stroke_width.setKeyboardTracking(False)
        self.shape_stroke_width.setToolTip(
            "Độ dày viền; 0 nghĩa là không có viền (có Undo)."
        )
        self.shape_stroke_width.editingFinished.connect(
            self._on_shape_stroke_width_changed
        )
        appearance.addWidget(self.shape_stroke_width, 1, 2)

        style_label = QLabel("Kiểu")
        style_label.setObjectName("PropKey")
        appearance.addWidget(style_label, 2, 0)
        self.shape_stroke_style = QComboBox()
        self.shape_stroke_style.addItem("Nét liền", "solid")
        self.shape_stroke_style.setEnabled(False)
        self.shape_stroke_style.setToolTip(
            "Chưa hỗ trợ nét đứt hoặc nét chấm cho layer hình khối.\n"
            "Hiện chỉ render viền liền."
        )
        appearance.addWidget(self.shape_stroke_style, 2, 1, 1, 2)
        appearance.setColumnStretch(1, 1)
        appearance.setColumnStretch(2, 1)
        layout.addLayout(appearance)

        self.shape_corner_section = _Section("Bo góc")
        corner_grid = QGridLayout()
        corner_grid.setContentsMargins(0, 0, 0, 0)
        corner_grid.setHorizontalSpacing(6)
        corner_grid.setVerticalSpacing(5)
        self.shape_radius_link = QToolButton()
        self.shape_radius_link.setIcon(icons.icon("link"))
        self.shape_radius_link.setCheckable(True)
        self.shape_radius_link.setToolTip(
            "Bật: sửa một góc sẽ áp dụng cho cả bốn góc.\n"
            "Tắt: cho phép bo bốn góc khác nhau."
        )
        corner_grid.addWidget(self.shape_radius_link, 0, 0, 2, 1)
        self.shape_radius_spins: list[QDoubleSpinBox] = []
        positions = ((0, 1, 2), (0, 3, 4), (1, 3, 4), (1, 1, 2))
        for index, ((short, description), (row, label_col, spin_col)) in enumerate(
            zip(_SHAPE_CORNERS, positions)
        ):
            label = QLabel(short)
            label.setObjectName("PropKey")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setToolTip(f"Bán kính {description}.")
            spin = QDoubleSpinBox()
            spin.setRange(0.0, MAX_CORNER_RADIUS)
            spin.setDecimals(1)
            spin.setSuffix(" px")
            spin.setKeyboardTracking(False)
            spin.setToolTip(
                f"Bán kính {description} (có Undo).\n"
                "Giá trị được giới hạn theo nửa cạnh ngắn của hình."
            )
            spin.editingFinished.connect(
                lambda index=index: self._on_shape_radius_edited(index)
            )
            corner_grid.addWidget(label, row, label_col)
            corner_grid.addWidget(spin, row, spin_col)
            self.shape_radius_spins.append(spin)
        corner_grid.setColumnStretch(2, 1)
        corner_grid.setColumnStretch(4, 1)
        self.shape_corner_section.body_layout.addLayout(corner_grid)
        layout.addWidget(self.shape_corner_section)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(5)
        path_label = QLabel("Đường dẫn")
        path_label.setObjectName("PropKey")
        path_row.addWidget(path_label)
        self.shape_path_buttons: list[QToolButton] = []
        for symbol, label in _PATH_OPERATIONS:
            button = QToolButton()
            button.setText(symbol)
            button.setFixedSize(36, 24)
            button.setEnabled(False)
            button.setToolTip(
                f"{label}: chưa hỗ trợ.\n"
                "Mỗi layer hình khối hiện chỉ có một đường dẫn duy nhất."
            )
            path_row.addWidget(button)
            self.shape_path_buttons.append(button)
        path_row.addStretch(1)
        layout.addLayout(path_row)
        return container

    def _set_shape_properties_visible(self, visible: bool) -> None:
        self.shape_properties.setVisible(visible)

    def _refresh_shape_properties(self, active: Layer | None) -> None:
        is_shape = bool(
            active is not None
            and active.kind == LayerKind.SHAPE
            and active.shape is not None
        )
        self._set_shape_properties_visible(is_shape)
        if not is_shape:
            return
        shape = active.shape
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.shape_width,
                self.shape_height,
                self.shape_x,
                self.shape_y,
                self.shape_fill_check,
                self.shape_stroke_width,
                *self.shape_radius_spins,
            )
        ]
        try:
            self.shape_kind_label.setText(
                SHAPE_LABELS.get(shape.kind, shape.kind)
            )
            self.shape_width.setValue(shape.width)
            self.shape_height.setValue(shape.height)
            self.shape_x.setValue(active.offset_x)
            self.shape_y.setValue(active.offset_y)
            max_stroke = min(
                MAX_STROKE_WIDTH, max(1, min(shape.width, shape.height) // 2)
            )
            self.shape_stroke_width.setRange(0, max_stroke)
            self.shape_stroke_width.setValue(shape.stroke_width)
            self.shape_fill_check.setChecked(shape.fill_color is not None)
            if shape.fill_color is not None:
                self._shape_fill_color = QColor(*shape.fill_color)
            self._shape_stroke_color = QColor(*shape.stroke_color)
            self.shape_fill_button.setEnabled(shape.fill_color is not None)
            self.shape_stroke_button.setEnabled(shape.stroke_width > 0)
            max_radius = min(
                MAX_CORNER_RADIUS, min(shape.width, shape.height) / 2.0
            )
            for spin, value in zip(
                self.shape_radius_spins,
                shape.corner_radii or (0.0, 0.0, 0.0, 0.0),
            ):
                spin.setRange(0.0, max_radius)
                spin.setValue(value)
            self.shape_corner_section.setVisible(
                shape.kind in ("rectangle", "rounded_rectangle")
            )
            self._update_shape_swatches(shape)
        finally:
            del blockers

    def _update_shape_swatches(self, shape) -> None:
        border = self.palette().mid().color().name()
        if shape.fill_color is None:
            self.shape_fill_button.setText("∅")
            self.shape_fill_button.setStyleSheet(
                "background: transparent; color: palette(mid); "
                f"border: 1px dashed {border}; border-radius: 4px;"
            )
            self.shape_fill_button.setToolTip(
                "Không tô. Bật ô 'Tô' bên trái rồi chọn màu."
            )
        else:
            color = QColor(*shape.fill_color)
            self.shape_fill_button.setText("")
            self.shape_fill_button.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, "
                f"{color.blue()}, {color.alpha()}); "
                f"border: 1px solid {border}; border-radius: 4px;"
            )
            self.shape_fill_button.setToolTip(
                f"RGBA({color.red()}, {color.green()}, {color.blue()}, "
                f"{color.alpha()}) — nhấp để chọn màu tô."
            )
        color = QColor(*shape.stroke_color)
        self.shape_stroke_button.setStyleSheet(
            f"background-color: rgba({color.red()}, {color.green()}, "
            f"{color.blue()}, {color.alpha()}); "
            f"border: 1px solid {border}; border-radius: 4px;"
        )
        self.shape_stroke_button.setToolTip(
            f"RGBA({color.red()}, {color.green()}, {color.blue()}, "
            f"{color.alpha()}) — nhấp để chọn màu viền."
        )

    def _current_shape_layer(self) -> Layer | None:
        document = self.document
        if document is None:
            return None
        layer = document.active_layer
        if layer is None or layer.kind != LayerKind.SHAPE or layer.shape is None:
            return None
        return layer

    def _apply_shape_properties(self, properties, action_label: str) -> bool:
        document = self.document
        layer = self._current_shape_layer()
        if document is None or layer is None:
            return False
        try:
            changed = document.update_shape_layer(properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.warning(self, "Thuộc tính hình khối", str(exc))
            self.refresh()
            return False
        if changed:
            self.message.emit(
                f"Đã cập nhật {action_label} (Ctrl+Z để hoàn tác)."
            )
        return changed

    def _apply_shape_offset(self) -> None:
        document = self.document
        layer = self._current_shape_layer()
        if document is None or layer is None:
            return
        if document.set_layer_offset(
            layer, self.shape_x.value(), self.shape_y.value()
        ):
            self.message.emit(
                "Đã di chuyển layer hình khối (Ctrl+Z để hoàn tác)."
            )

    def _apply_shape_size(self, source: str) -> None:
        layer = self._current_shape_layer()
        if layer is None:
            return
        shape = layer.shape
        width = shape.width
        height = shape.height
        if source == "width":
            width = self.shape_width.value()
        else:
            height = self.shape_height.value()
        if width == shape.width and height == shape.height:
            return
        if self.shape_link_button.isChecked():
            if source == "width":
                height = max(
                    1,
                    min(
                        MAX_SHAPE_SIZE,
                        int(round(shape.height * width / max(1, shape.width))),
                    ),
                )
            else:
                width = max(
                    1,
                    min(
                        MAX_SHAPE_SIZE,
                        int(round(shape.width * height / max(1, shape.height))),
                    ),
                )
        self._apply_shape_properties(
            replace(shape, width=width, height=height),
            "kích thước hình khối",
        )

    def _on_shape_fill_toggled(self, checked: bool) -> None:
        layer = self._current_shape_layer()
        if layer is None:
            return
        shape = layer.shape
        if checked and shape.fill_color is not None:
            return
        if not checked and shape.fill_color is None:
            return
        stroke_width = shape.stroke_width
        if not checked and stroke_width == 0:
            stroke_width = 1
        fill = self._shape_fill_color.getRgb() if checked else None
        self._apply_shape_properties(
            replace(shape, fill_color=fill, stroke_width=stroke_width),
            "màu tô",
        )

    def _on_shape_stroke_width_changed(self) -> None:
        layer = self._current_shape_layer()
        if layer is None:
            return
        shape = layer.shape
        width = self.shape_stroke_width.value()
        if width == shape.stroke_width:
            return
        fill = shape.fill_color
        if width == 0 and fill is None:
            fill = self._shape_fill_color.getRgb()
        self._apply_shape_properties(
            replace(shape, stroke_width=width, fill_color=fill),
            "độ dày viền",
        )

    def _on_shape_radius_edited(self, index: int) -> None:
        layer = self._current_shape_layer()
        if layer is None:
            return
        shape = layer.shape
        values = [spin.value() for spin in self.shape_radius_spins]
        if self.shape_radius_link.isChecked():
            values = [values[index]] * 4
        radii = tuple(values)
        if radii == shape.corner_radii:
            return
        kind = shape.kind
        if kind == "rectangle" and any(value > 0.0 for value in radii):
            kind = "rounded_rectangle"
        self._apply_shape_properties(
            replace(shape, kind=kind, corner_radii=radii),
            "bo góc hình khối",
        )

    def _choose_shape_fill_color(self) -> None:
        color = QColorDialog.getColor(
            self._shape_fill_color,
            self,
            "Chọn màu tô",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self.set_shape_fill_color(color)

    def _choose_shape_stroke_color(self) -> None:
        color = QColorDialog.getColor(
            self._shape_stroke_color,
            self,
            "Chọn màu viền",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self.set_shape_stroke_color(color)

    def set_shape_fill_color(self, color: QColor) -> bool:
        layer = self._current_shape_layer()
        if layer is None or not color.isValid():
            return False
        self._shape_fill_color = QColor(color)
        return self._apply_shape_properties(
            replace(layer.shape, fill_color=color.getRgb()),
            "màu tô hình khối",
        )

    def set_shape_stroke_color(self, color: QColor) -> bool:
        layer = self._current_shape_layer()
        if layer is None or not color.isValid():
            return False
        self._shape_stroke_color = QColor(color)
        return self._apply_shape_properties(
            replace(layer.shape, stroke_color=color.getRgb()),
            "màu viền hình khối",
        )

    # ------------------------------------------------------------- tài liệu
    def bind_document(self, document: Document | None) -> None:
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()
        self.document = document
        if document is not None:
            for signal in (
                document.structure_changed,
                document.active_layer_changed,
                document.title_changed,
                document.content_changed,
            ):
                signal.connect(self.refresh)
                self._connections.append((signal, self.refresh))
        self.refresh()

    def refresh(self) -> None:
        document = self.document
        if document is None:
            for label in self._values.values():
                label.setText("—")
            self._refresh_text_properties(None)
            self._refresh_shape_properties(None)
            return
        active = document.active_layer
        self._refresh_text_properties(active)
        self._refresh_shape_properties(active)
        self._values["name"].setText(document.base_title)
        self._values["size"].setText(f"{document.width} × {document.height} px")
        self._values["resolution"].setText(f"{document.dpi:g} ppi")
        self._values["mode"].setText("RGB · 8-bit")
        self._values["layers"].setText(str(len(document.layers)))
        self._values["active"].setText(active.name if active else "—")
        if active is not None:
            if active.kind == LayerKind.GROUP:
                child_count = len(document.layers.children_of(active.id))
                mask_note = "Mask: không có"
                if active.mask is not None:
                    mask_note = (
                        "Mask: bật (trắng = hiện, đen = ẩn)"
                        if active.mask_enabled
                        else "Mask: đang tắt"
                    )
                parent = (
                    document.layers.get(active.group_id)
                    if active.group_id
                    else None
                )
                info = (
                    f"Nhóm · {child_count} layer trực tiếp\n"
                    f"Độ mờ (opacity): {int(round(active.opacity * 100))}%\n"
                    f"Blend: "
                    f"{BLEND_MODE_LABELS.get(active.blend_mode, active.blend_mode)}\n"
                    f"{mask_note}"
                )
                if parent is not None:
                    info += f"\nNằm trong nhóm: {parent.name}"
                self._values["layer_info"].setText(info)
                self._update_file_row(document)
                return
            if active.kind == LayerKind.ADJUSTMENT and active.adjustment is not None:
                adjustment = active.adjustment
                mask_note = "Mask: không có"
                if active.mask is not None:
                    mask_note = (
                        "Mask: bật (trắng = áp hiệu ứng, đen = giữ nguyên)"
                        if active.mask_enabled
                        else "Mask: đang tắt"
                    )
                info = (
                    "Layer điều chỉnh · "
                    f"{ADJUSTMENT_LABELS.get(adjustment.kind, adjustment.kind)}\n"
                    f"{adjustment.summary()}\n"
                    f"Độ mạnh (opacity): {int(round(active.opacity * 100))}%\n"
                    f"{mask_note}\n"
                    "Áp lên toàn bộ layer nằm bên dưới."
                )
                self._values["layer_info"].setText(info)
                self._update_file_row(document)
                return
            if active.kind == LayerKind.FILL and active.fill_props is not None:
                fill = active.fill_props
                mask_note = "Mask: không có"
                if active.mask is not None:
                    mask_note = (
                        "Mask: bật (trắng = hiện, đen = ẩn)"
                        if active.mask_enabled
                        else "Mask: đang tắt"
                    )
                info = (
                    f"Layer tô · {FILL_LABELS.get(fill.fill_type, fill.fill_type)}\n"
                    f"{fill.summary}\n"
                    f"Độ mờ (opacity): {int(round(active.opacity * 100))}%\n"
                    f"{mask_note}\n"
                    "Phủ toàn canvas, không giữ pixel riêng."
                )
                if fill.fill_type == "gradient":
                    info += (
                        f"\nGradient: "
                        f"{GRADIENT_LABELS.get(fill.gradient_type, fill.gradient_type)}"
                        f" · {fill.angle}°"
                    )
                self._values["layer_info"].setText(info)
                self._update_file_row(document)
                return
            if active.kind == LayerKind.SMART and active.smart_props is not None:
                smart = active.smart_props
                mask_note = "Mask: không có"
                if active.mask is not None:
                    mask_note = (
                        "Mask: bật (trắng = hiện, đen = ẩn)"
                        if active.mask_enabled
                        else "Mask: đang tắt"
                    )
                info = (
                    f"Smart object · {smart.source_name}\n"
                    f"Ảnh gốc: {smart.source_width} × {smart.source_height} px\n"
                    f"Góc xoay: {smart.angle:g}° · Tỉ lệ: {smart.scale:g}%\n"
                    f"Lật ngang: {'có' if smart.flip_h else 'không'} · "
                    f"Lật dọc: {'có' if smart.flip_v else 'không'}\n"
                    f"{mask_note}\n"
                    "Xoay/lật/đổi tỉ lệ không phá huỷ ảnh gốc."
                )
                self._values["layer_info"].setText(info)
                self._update_file_row(document)
                return
            info = (
                f"{active.width} × {active.height} px\n"
                f"Offset: {active.offset_x}, {active.offset_y}"
            )
            if active.kind == LayerKind.TEXT and active.text is not None:
                snippet = active.text.text.replace("\n", " ")[:48]
                runs = active.text.runs
                info += f"\nVăn bản: {snippet}"
                if len(runs) > 1:
                    info += (
                        f"\nKiểu chữ: {len(runs)} đoạn riêng"
                        f"\nĐoạn đầu: {runs[0].font_family or 'mặc định'} "
                        f"{runs[0].font_size} px"
                    )
                else:
                    style = "Đậm" if active.text.bold else ""
                    if active.text.italic:
                        style = f"{style} Nghiêng".strip()
                    info += (
                        f"\nFont: {active.text.font_family or 'mặc định'} "
                        f"{active.text.font_size} px"
                    )
                    if style:
                        info += f" · {style}"
                info += (
                    f"\nCăn lề: "
                    f"{ALIGNMENT_LABELS.get(active.text.alignment, active.text.alignment)}"
                )
                if active.text.path_style != "none" and active.text.path_bend:
                    label = PATH_LABELS.get(
                        active.text.path_style, active.text.path_style
                    )
                    info += f" · Đường dẫn: {label} {active.text.path_bend:+d}%"
                elif active.text.warp_style != "none" and active.text.warp_bend:
                    label = WARP_LABELS.get(
                        active.text.warp_style, active.text.warp_style
                    )
                    info += f" · Uốn: {label} {active.text.warp_bend:+d}%"
                if (
                    abs(active.text.line_spacing - 1.0) > 1e-9
                    or active.text.letter_spacing
                ):
                    info += (
                        f"\nGiãn dòng: {active.text.line_spacing:g}×"
                        f" · Giãn chữ: {active.text.letter_spacing:+d} px"
                    )
                if active.text.kerning_pairs:
                    pairs = ", ".join(
                        f"{key}{amount:+d}"
                        for key, amount in active.text.kerning_pairs[:4]
                    )
                    if len(active.text.kerning_pairs) > 4:
                        pairs += ", …"
                    info += f"\nKerning: {pairs}"
            elif active.kind == LayerKind.SHAPE and active.shape is not None:
                shape = active.shape
                fill = (
                    "không tô"
                    if shape.fill_color is None
                    else "RGBA({}, {}, {}, {})".format(*shape.fill_color)
                )
                info += (
                    f"\nHình khối: {SHAPE_LABELS.get(shape.kind, shape.kind)}"
                    f"\nMàu tô: {fill}"
                )
                if shape.stroke_width > 0:
                    info += f"\nViền: {shape.stroke_width} px"
                if shape.kind == "rounded_rectangle":
                    info += f"\nBo góc: {shape.corner_radius:g} px"
            self._values["layer_info"].setText(info)
        else:
            self._values["layer_info"].setText("—")
        self._update_file_row(document)

    def _update_file_row(self, document: Document) -> None:
        if document.file_path:
            self._values["file"].setText(Path(document.file_path).name)
            self._values["file"].setToolTip(document.file_path)
        else:
            self._values["file"].setText("Chưa lưu (.mps)")
            self._values["file"].setToolTip("")
