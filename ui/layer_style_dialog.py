"""Hộp thoại Layer Style: Blending Options nâng cao và 10 hiệu ứng layer.

Hộp thoại sửa trên một bản sao bất biến của ``LayerStyle`` nên có thể xem
trước trực tiếp, còn tài liệu chỉ đổi khi bấm OK (một bước Undo duy nhất).
"""

from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.canvas import composite_region, numpy_rgba_to_qimage
from core.layer import BLEND_MODES, LayerKind
from core.layer_style import (
    BEVEL_DIRECTIONS,
    BEVEL_STYLES,
    BLEND_IF_CHANNELS,
    EFFECT_KINDS,
    EFFECT_LABELS,
    GLOW_SOURCES,
    KNOCKOUT_MODES,
    PATTERN_KINDS,
    PATTERN_LABELS,
    STROKE_POSITIONS,
    BlendChannelRange,
    BlendIf,
    LayerEffect,
    LayerStyle,
    effect_margin,
    default_effect,
)
from core.presets import PresetError, PresetStore
from ui.dialogs import SliderField

COLOR_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2

PREVIEW_SIZE = 170
STYLE_PRESET_KIND = "layer_style"


class ColorButton(QPushButton):
    """Nút chọn màu RGBA, hiển thị mã hex và độ đục."""

    colorChanged = Signal(tuple)

    def __init__(self, color: tuple[int, int, int, int], parent=None) -> None:
        super().__init__(parent)
        self._color = tuple(int(channel) for channel in color)
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick_color)
        self._sync_style()

    def color(self) -> tuple[int, int, int, int]:
        return self._color

    def set_color(self, color: tuple[int, int, int, int]) -> None:
        self._color = tuple(int(channel) for channel in color)
        self._sync_style()

    def _sync_style(self) -> None:
        red, green, blue, alpha = self._color
        luminance = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#111111" if luminance > 150 else "#f5f5f5"
        opacity = round(alpha / 255.0 * 100)
        self.setText(f"#{red:02x}{green:02x}{blue:02x} · {opacity}%")
        self.setStyleSheet(
            "QPushButton {"
            f" background-color: rgba({red},{green},{blue},{alpha});"
            f" color: {text_color}; border: 1px solid #5a6068;"
            " border-radius: 4px; padding: 2px 8px; text-align: left; }"
        )

    def _pick_color(self) -> None:
        red, green, blue, alpha = self._color
        picked = QColorDialog.getColor(
            QColor(red, green, blue, alpha),
            self,
            "Chọn màu",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if picked.isValid():
            self._color = (
                picked.red(),
                picked.green(),
                picked.blue(),
                picked.alpha(),
            )
            self._sync_style()
            self.colorChanged.emit(self._color)


class BlendIfSlider(QWidget):
    """Thanh dải đen–trắng với bốn tay nắm (hai đen, hai trắng)."""

    valuesChanged = Signal(tuple)

    def __init__(self, values=(0, 0, 255, 255), parent=None) -> None:
        super().__init__(parent)
        self._values = [0, 0, 255, 255]
        self._drag_index: int | None = None
        self.setMinimumHeight(46)
        self.setMinimumWidth(180)
        self.setMouseTracking(True)
        self.setValues(values)

    def values(self) -> tuple[int, int, int, int]:
        return tuple(self._values)  # type: ignore[return-value]

    def setValues(self, values) -> None:
        self._values = _normalize_blend_values(values)
        self.update()

    def _bar_rect(self) -> QRect:
        return QRect(10, 10, max(1, self.width() - 20), 10)

    def _x_for(self, value: int) -> int:
        bar = self._bar_rect()
        return bar.left() + round(value / 255.0 * max(1, bar.width() - 1))

    def _value_for(self, x: int) -> int:
        bar = self._bar_rect()
        ratio = (x - bar.left()) / max(1, bar.width() - 1)
        return max(0, min(255, round(ratio * 255)))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bar = self._bar_rect()
        gradient = QLinearGradient(bar.topLeft(), bar.topRight())
        gradient.setColorAt(0.0, QColor("#000000"))
        gradient.setColorAt(1.0, QColor("#ffffff"))
        painter.fillRect(bar, gradient)
        painter.setPen(QPen(QColor("#5a6068"), 1))
        painter.drawRect(bar.adjusted(0, 0, -1, -1))

        for index, value in enumerate(self._values):
            x = self._x_for(value)
            color = QColor("#101010") if index < 2 else QColor("#f2f2f2")
            border = QColor("#f2f2f2") if index < 2 else QColor("#101010")
            points = [
                QPoint(x, 21),
                QPoint(x - 6, 21),
                QPoint(x, 32),
                QPoint(x + 6, 21),
            ]
            painter.setPen(QPen(border, 1))
            painter.setBrush(color)
            painter.drawPolygon(points)
        painter.end()

    def _nearest_handle(self, x: int) -> int | None:
        best = None
        best_distance = 12
        for index, value in enumerate(self._values):
            distance = abs(self._x_for(value) - x)
            if distance <= best_distance:
                best = index
                best_distance = distance
        return best

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_index = self._nearest_handle(round(event.position().x()))
        if self._drag_index is not None:
            self._update_from_handle(round(event.position().x()))
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_index is None:
            return
        self._update_from_handle(round(event.position().x()))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_index = None
        super().mouseReleaseEvent(event)

    def _update_from_handle(self, x: int) -> None:
        index = self._drag_index
        if index is None:
            return
        value = self._value_for(x)
        values = list(self._values)
        if index == 0:
            value = min(value, values[1])
        elif index == 1:
            value = max(values[0], min(value, values[2]))
        elif index == 2:
            value = max(values[1], min(value, values[3]))
        else:
            value = max(value, values[2])
        if value == values[index]:
            return
        values[index] = value
        self._values = values
        self.setToolTip(
            f"Đen {values[0]}–{values[1]} · Trắng {values[2]}–{values[3]}"
        )
        self.valuesChanged.emit(tuple(values))
        self.update()


def _normalize_blend_values(values) -> list[int]:
    try:
        low_black, high_black, low_white, high_white = (
            max(0, min(255, int(value))) for value in values
        )
    except (TypeError, ValueError):
        low_black, high_black, low_white, high_white = 0, 0, 255, 255
    high_black = max(low_black, high_black)
    low_white = max(high_black, low_white)
    high_white = max(low_white, high_white)
    return [low_black, high_black, low_white, high_white]


EFFECT_HINTS = {
    "drop_shadow": "Đổ bóng ra ngoài silhouette của layer; đặt bên dưới nội dung.",
    "inner_shadow": "Bóng đổ vào bên trong, cắt theo vùng đục của layer.",
    "outer_glow": "Quầng sáng lan ra ngoài mép layer.",
    "inner_glow": "Quầng sáng bên trong mép layer (hoặc toả từ tâm).",
    "bevel_emboss": "Tạo cảm giác nổi/khắc bằng vùng sáng và vùng tối quanh mép.",
    "satin": "Dải mềm tạo vân sa-tanh trên vùng đục của layer.",
    "color_overlay": "Phủ một màu lên toàn bộ vùng đục của layer.",
    "gradient_overlay": "Phủ gradient tuyến tính theo góc đặt trước.",
    "pattern_overlay": "Phủ hoa văn dựng sẵn: ca-rô, sọc, chấm hoặc lưới.",
    "stroke": "Viền màu đặc quanh mép layer (ngoài, trong hoặc giữa).",
}


class LayerStyleDialog(QDialog):
    """Hộp thoại Layer Style giống bố cục Photoshop nhưng dùng hiệu ứng thật."""

    def __init__(
        self,
        parent: QWidget | None,
        document,
        layer,
        *,
        preset_store: PresetStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.layer = layer
        self.preset_store = preset_store
        self.setWindowTitle("Layer Style")
        self.setModal(True)
        self.setMinimumSize(860, 620)

        self._updating = False
        self._style: LayerStyle = layer.style or LayerStyle()
        self._effect_widgets: dict[tuple[str, str], QWidget] = {}
        self._effect_attrs: dict[str, tuple[str, ...]] = {}
        self._effect_pages: dict[str, QWidget] = {}
        self._result_style: LayerStyle | None = None
        self._result_blend = layer.blend_mode
        self._result_opacity = layer.opacity
        self._blend_ranges = {
            "this_layer": [BlendChannelRange() for _ in range(4)],
            "underlying": [BlendChannelRange() for _ in range(4)],
        }
        if not self._style.blend_if.is_identity:
            for index in range(4):
                self._blend_ranges["this_layer"][index] = self._style.blend_if.this_layer[index]
                self._blend_ranges["underlying"][index] = self._style.blend_if.underlying[index]

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._build_layout()
        self._load_style_into_widgets(self._style)
        self._refresh_preset_list()
        self._refresh_preview()

    # ------------------------------------------------------------------ layout
    def _build_layout(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        root.addWidget(self._build_left_column())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_blending_page())
        for kind in EFFECT_KINDS:
            page = self._build_effect_page(kind)
            self._effect_pages[kind] = page
            self.pages.addWidget(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.pages)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        root.addWidget(self._build_right_column())

        if self.layer.kind in (LayerKind.GROUP, LayerKind.ADJUSTMENT):
            reason = (
                "Layer điều chỉnh không có pixel riêng"
                if self.layer.kind == LayerKind.ADJUSTMENT
                else "Hiệu ứng lên nhóm layer chưa được hỗ trợ"
            )
            self.note_label.setText(
                f"{reason}; chỉ Blend Mode và Opacity được áp dụng."
            )
        else:
            self.note_label.setText(
                "Giữ phím này để xem trước trực tiếp; OK áp toàn bộ trong một bước Undo."
            )

    def _build_left_column(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(232)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        styles_title = QLabel("Styles")
        styles_title.setObjectName("PanelTitle")
        layout.addWidget(styles_title)
        self.preset_list = QListWidget()
        self.preset_list.setMaximumHeight(92)
        self.preset_list.itemDoubleClicked.connect(self._apply_selected_preset)
        layout.addWidget(self.preset_list)
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        self.delete_preset_button = QPushButton("Xoá preset")
        self.delete_preset_button.setEnabled(False)
        self.delete_preset_button.clicked.connect(self._delete_selected_preset)
        self.preset_list.itemSelectionChanged.connect(
            lambda: self.delete_preset_button.setEnabled(
                self.preset_list.currentRow() > 0
            )
        )
        preset_row.addWidget(self.delete_preset_button)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        effects_title = QLabel("Effects")
        effects_title.setObjectName("PanelTitle")
        layout.addWidget(effects_title)
        self.effect_list = QListWidget()
        self.effect_list.currentRowChanged.connect(self._on_effect_row_changed)
        self.effect_list.itemChanged.connect(self._on_effect_item_changed)
        layout.addWidget(self.effect_list, 1)

        self.preset_status = QLabel("")
        self.preset_status.setObjectName("OptionsHint")
        self.preset_status.setWordWrap(True)
        layout.addWidget(self.preset_status)

        self._effect_items: dict[str, QListWidgetItem] = {}
        blending = QListWidgetItem("Blending Options")
        blending.setData(KIND_ROLE, "")
        self.effect_list.addItem(blending)
        for kind in EFFECT_KINDS:
            item = QListWidgetItem(EFFECT_LABELS[kind])
            item.setData(KIND_ROLE, kind)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            if self.layer.kind in (LayerKind.GROUP, LayerKind.ADJUSTMENT):
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(
                    "Layer này không có pixel riêng nên không nhận hiệu ứng."
                )
            self.effect_list.addItem(item)
            self._effect_items[kind] = item
        self.effect_list.setCurrentRow(0)
        return column

    def _build_right_column(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(190)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.new_style_button = QPushButton("New Style…")
        self.new_style_button.clicked.connect(self._save_new_style)
        layout.addWidget(self.new_style_button)

        self.preview_check = QCheckBox("Preview")
        self.preview_check.setChecked(True)
        self.preview_check.toggled.connect(self._schedule_preview)
        layout.addWidget(self.preview_check)

        self.preview_label = QLabel()
        self.preview_label.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background-color: #23262c; border: 1px solid #4a4f57; border-radius: 4px;"
        )
        layout.addWidget(self.preview_label)
        layout.addStretch(1)

        self.note_label = QLabel(
            "Giữ phím này để xem trước trực tiếp; OK áp toàn bộ trong một bước Undo."
        )
        self.note_label.setObjectName("OptionsHint")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)
        return column

    def _build_blending_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        general = QGroupBox("General Blending")
        form = QFormLayout(general)
        self.blend_combo = QComboBox()
        for mode_id, label in BLEND_MODES:
            self.blend_combo.addItem(label, mode_id)
        self.blend_combo.setCurrentIndex(
            max(0, self.blend_combo.findData(self.layer.blend_mode))
        )
        self.blend_combo.currentIndexChanged.connect(self._schedule_preview)
        if self.layer.kind == LayerKind.ADJUSTMENT:
            self.blend_combo.setEnabled(False)
            self.blend_combo.setToolTip("Layer điều chỉnh không dùng blend mode.")
        form.addRow("Blend Mode:", self.blend_combo)

        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(0, 100)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setValue(round(self.layer.opacity * 100))
        self.opacity_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Opacity:", self.opacity_spin)
        layout.addWidget(general)

        advanced = QGroupBox("Advanced Blending")
        form = QFormLayout(advanced)
        self.fill_opacity_spin = QSpinBox()
        self.fill_opacity_spin.setRange(0, 100)
        self.fill_opacity_spin.setSuffix(" %")
        self.fill_opacity_spin.setValue(round(self._style.fill_opacity * 100))
        self.fill_opacity_spin.valueChanged.connect(self._on_advanced_changed)
        form.addRow("Fill Opacity:", self.fill_opacity_spin)

        self.knockout_combo = QComboBox()
        for mode_id, label in KNOCKOUT_MODES:
            self.knockout_combo.addItem(label, mode_id)
        self.knockout_combo.currentIndexChanged.connect(self._on_advanced_changed)
        form.addRow("Knockout:", self.knockout_combo)

        self.interior_group_check = QCheckBox("Blend Interior Effects as Group")
        self.clipped_group_check = QCheckBox("Blend Clipped Layers as Group")
        self.transparency_check = QCheckBox("Transparency Shapes Layer")
        self.mask_hides_check = QCheckBox("Layer Mask Hides Effects")
        self.vector_mask_check = QCheckBox("Vector Mask Hides Effects")
        self.vector_mask_check.setEnabled(False)
        self.vector_mask_check.setToolTip(
            "Ứng dụng chưa có vector mask nên tuỳ chọn này chỉ được lưu làm metadata."
        )
        for widget in (
            self.interior_group_check,
            self.clipped_group_check,
            self.transparency_check,
            self.mask_hides_check,
        ):
            widget.toggled.connect(self._on_advanced_changed)
            form.addRow("", widget)
        form.addRow("", self.vector_mask_check)
        layout.addWidget(advanced)

        blend_if = QGroupBox("Blend If")
        form = QFormLayout(blend_if)
        self.blend_channel_combo = QComboBox()
        for key, label in BLEND_IF_CHANNELS:
            self.blend_channel_combo.addItem(label, key)
        self.blend_channel_combo.currentIndexChanged.connect(
            self._on_blend_channel_changed
        )
        form.addRow("Channel:", self.blend_channel_combo)
        self.this_slider = BlendIfSlider()
        self.underlying_slider = BlendIfSlider()
        self.this_slider.valuesChanged.connect(
            lambda values: self._on_blend_slider("this_layer", values)
        )
        self.underlying_slider.valuesChanged.connect(
            lambda values: self._on_blend_slider("underlying", values)
        )
        form.addRow("This Layer:", self.this_slider)
        form.addRow("Underlying Layer:", self.underlying_slider)
        hint = QLabel(
            "Kéo tam giác để thu hẹp dải hiển thị; cặp tam giác cùng màu tạo mép mềm."
        )
        hint.setObjectName("OptionsHint")
        hint.setWordWrap(True)
        form.addRow(hint)
        layout.addWidget(blend_if)
        layout.addStretch(1)
        return page

    def _build_effect_page(self, kind: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        header = QLabel(EFFECT_LABELS[kind].upper())
        header.setObjectName("PanelTitle")
        layout.addWidget(header)
        hint = QLabel(EFFECT_HINTS[kind])
        hint.setObjectName("OptionsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        box = QGroupBox(EFFECT_LABELS[kind])
        form = QFormLayout(box)
        self._effect_attrs[kind] = tuple(attr for attr, _, _ in self._field_specs(kind))
        for attr, label, spec in self._field_specs(kind):
            widget = self._create_field_widget(kind, attr, spec)
            self._effect_widgets[(kind, attr)] = widget
            form.addRow(label + ":", widget)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    @staticmethod
    def _field_specs(kind: str) -> tuple[tuple[str, str, tuple], ...]:
        if kind == "drop_shadow":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("color", "Color", ("color",)),
                ("opacity", "Opacity", ("percent",)),
                ("angle", "Angle", ("angle",)),
                ("distance", "Distance", ("px", 0.0, 3000.0)),
                ("spread", "Spread", ("px", 0.0, 250.0)),
                ("size", "Size", ("px", 0.0, 250.0)),
            )
        if kind == "inner_shadow":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("color", "Color", ("color",)),
                ("opacity", "Opacity", ("percent",)),
                ("angle", "Angle", ("angle",)),
                ("distance", "Distance", ("px", 0.0, 3000.0)),
                ("choke", "Choke", ("px", 0.0, 250.0)),
                ("size", "Size", ("px", 0.0, 250.0)),
            )
        if kind == "outer_glow":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("color", "Color", ("color",)),
                ("opacity", "Opacity", ("percent",)),
                ("spread", "Spread", ("px", 0.0, 250.0)),
                ("size", "Size", ("px", 0.0, 250.0)),
            )
        if kind == "inner_glow":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("color", "Color", ("color",)),
                ("opacity", "Opacity", ("percent",)),
                ("choke", "Choke", ("px", 0.0, 250.0)),
                ("size", "Size", ("px", 0.0, 250.0)),
                ("source", "Source", ("combo", GLOW_SOURCES)),
            )
        if kind == "bevel_emboss":
            return (
                ("style", "Style", ("combo", BEVEL_STYLES)),
                ("depth", "Depth", ("percent_deep",)),
                ("direction", "Direction", ("combo", BEVEL_DIRECTIONS)),
                ("size", "Size", ("px", 0.0, 250.0)),
                ("soften", "Soften", ("px", 0.0, 100.0)),
                ("angle", "Angle", ("angle",)),
                ("altitude", "Altitude", ("angle",)),
                ("highlight_color", "Highlight", ("color",)),
                ("highlight_mode", "Highlight Mode", ("blend",)),
                ("highlight_opacity", "Highlight Opacity", ("percent",)),
                ("shadow_color", "Shadow", ("color",)),
                ("shadow_mode", "Shadow Mode", ("blend",)),
                ("shadow_opacity", "Shadow Opacity", ("percent",)),
            )
        if kind == "satin":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("color", "Color", ("color",)),
                ("opacity", "Opacity", ("percent",)),
                ("angle", "Angle", ("angle",)),
                ("distance", "Distance", ("px", 0.0, 3000.0)),
                ("size", "Size", ("px", 0.0, 250.0)),
                ("invert", "Invert", ("check",)),
            )
        if kind == "color_overlay":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("color", "Color", ("color",)),
                ("opacity", "Opacity", ("percent",)),
            )
        if kind == "gradient_overlay":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("start_color", "Gradient", ("color",)),
                ("end_color", "Đến màu", ("color",)),
                ("angle", "Angle", ("angle",)),
                ("scale", "Scale", ("percent_scale",)),
                ("reverse", "Reverse", ("check",)),
                ("opacity", "Opacity", ("percent",)),
            )
        if kind == "pattern_overlay":
            return (
                ("blend_mode", "Blend Mode", ("blend",)),
                ("pattern", "Pattern", ("pattern",)),
                ("color", "Foreground", ("color",)),
                ("background", "Background", ("color",)),
                ("scale", "Scale", ("percent_scale",)),
                ("opacity", "Opacity", ("percent",)),
            )
        return (
            ("blend_mode", "Blend Mode", ("blend",)),
            ("color", "Color", ("color",)),
            ("size", "Size", ("px", 1.0, 250.0)),
            ("position", "Position", ("combo", STROKE_POSITIONS)),
            ("opacity", "Opacity", ("percent",)),
        )  # stroke

    def _create_field_widget(self, kind: str, attr: str, spec: tuple) -> QWidget:
        field_kind = spec[0]
        effect = self._style.effect(kind) or default_effect(kind)
        value = getattr(effect, attr)
        if field_kind == "blend":
            widget = QComboBox()
            for mode_id, label in BLEND_MODES:
                widget.addItem(label, mode_id)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.currentIndexChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "color":
            widget = ColorButton(value)
            widget.colorChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "percent":
            widget = SliderField(0, 100, round(float(value) * 100), " %")
            widget.valueChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "percent_deep":
            widget = SliderField(0, 1000, round(float(value)), " %")
            widget.valueChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "percent_scale":
            widget = SliderField(10, 400, round(float(value)), " %")
            widget.valueChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "angle":
            widget = QDoubleSpinBox()
            widget.setRange(-180.0, 360.0)
            widget.setDecimals(0)
            widget.setSuffix("°")
            widget.setValue(float(value))
            widget.valueChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "px":
            widget = QDoubleSpinBox()
            widget.setRange(float(spec[1]), float(spec[2]))
            widget.setDecimals(1)
            widget.setSingleStep(0.5)
            widget.setSuffix(" px")
            widget.setValue(float(value))
            widget.valueChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "check":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.toggled.connect(lambda *_: self._on_effect_field(kind))
            return widget
        if field_kind == "combo":
            widget = QComboBox()
            for item_id, label in spec[1]:
                widget.addItem(label, item_id)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.currentIndexChanged.connect(lambda *_: self._on_effect_field(kind))
            return widget
        widget = QComboBox()  # pattern
        for pattern in PATTERN_KINDS:
            widget.addItem(PATTERN_LABELS[pattern], pattern)
        widget.setCurrentIndex(max(0, widget.findData(value)))
        widget.currentIndexChanged.connect(lambda *_: self._on_effect_field(kind))
        return widget

    # ------------------------------------------------------ đọc/ghi widget
    @staticmethod
    def _widget_value(widget: QWidget):
        if isinstance(widget, ColorButton):
            return widget.color()
        if isinstance(widget, SliderField):
            return widget.value()
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return None

    def _on_effect_field(self, kind: str) -> None:
        if self._updating:
            return
        effect = self._style.effect(kind) or default_effect(kind)
        values = {}
        for attr in self._effect_attrs[kind]:
            raw = self._widget_value(self._effect_widgets[(kind, attr)])
            if attr in ("opacity", "highlight_opacity", "shadow_opacity"):
                values[attr] = raw / 100.0
            elif attr in ("depth",):
                values[attr] = float(raw)
            else:
                values[attr] = raw
        try:
            effect = type(effect)(
                **{**{key: item for key, item in effect.to_dict().items() if key != "kind"}, **values}
            )
        except (TypeError, ValueError):
            return
        self._style = self._style.with_effect(effect)
        self._schedule_preview()

    def _on_advanced_changed(self) -> None:
        if self._updating:
            return
        self._schedule_preview()

    def _on_effect_row_changed(self, row: int) -> None:
        if row < 0 or not hasattr(self, "pages"):
            return
        kind = self.effect_list.item(row).data(KIND_ROLE)
        self.pages.setCurrentIndex(0 if not kind else 1 + EFFECT_KINDS.index(kind))

    def _on_effect_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        kind = item.data(KIND_ROLE)
        if not kind:
            return
        enabled = item.checkState() == Qt.CheckState.Checked
        effect = self._style.effect(kind) or default_effect(kind)
        effect = type(effect)(
            **{
                **{key: value for key, value in effect.to_dict().items() if key != "kind"},
                "enabled": enabled,
            }
        )
        self._style = self._style.with_effect(effect)
        self._schedule_preview()

    def _on_blend_channel_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        self._load_blend_sliders(index)

    def _load_blend_sliders(self, index: int) -> None:
        previous = self._updating
        self._updating = True
        try:
            this_range = self._blend_ranges["this_layer"][index]
            under_range = self._blend_ranges["underlying"][index]
            self.this_slider.setValues(
                (
                    this_range.black_low,
                    this_range.black_high,
                    this_range.white_low,
                    this_range.white_high,
                )
            )
            self.underlying_slider.setValues(
                (
                    under_range.black_low,
                    under_range.black_high,
                    under_range.white_low,
                    under_range.white_high,
                )
            )
        finally:
            self._updating = previous

    def _on_blend_slider(self, side: str, values) -> None:
        if self._updating:
            return
        index = max(0, self.blend_channel_combo.currentIndex())
        self._blend_ranges[side][index] = BlendChannelRange(*values)
        self._schedule_preview()

    def _current_blend_if(self) -> BlendIf:
        return BlendIf(
            this_layer=tuple(self._blend_ranges["this_layer"]),
            underlying=tuple(self._blend_ranges["underlying"]),
        )

    def _build_style(self) -> LayerStyle | None:
        style = LayerStyle(
            fill_opacity=self.fill_opacity_spin.value() / 100.0,
            knockout=str(self.knockout_combo.currentData()),
            blend_interior_as_group=self.interior_group_check.isChecked(),
            blend_clipped_as_group=self.clipped_group_check.isChecked(),
            transparency_shapes_layer=self.transparency_check.isChecked(),
            layer_mask_hides_effects=self.mask_hides_check.isChecked(),
            vector_mask_hides_effects=self.vector_mask_check.isChecked(),
            blend_if=self._current_blend_if(),
            effects=self._style.effects,
        )
        if self.layer.kind in (LayerKind.GROUP, LayerKind.ADJUSTMENT):
            style = LayerStyle(
                fill_opacity=1.0,
                knockout="none",
                blend_if=BlendIf(),
                effects=(),
            )
        return None if style.is_identity else style

    # --------------------------------------------------------- nạp vào widget
    def _load_style_into_widgets(self, style: LayerStyle) -> None:
        self._updating = True
        try:
            self.fill_opacity_spin.setValue(round(style.fill_opacity * 100))
            self.knockout_combo.setCurrentIndex(
                max(0, self.knockout_combo.findData(style.knockout))
            )
            self.interior_group_check.setChecked(style.blend_interior_as_group)
            self.clipped_group_check.setChecked(style.blend_clipped_as_group)
            self.transparency_check.setChecked(style.transparency_shapes_layer)
            self.mask_hides_check.setChecked(style.layer_mask_hides_effects)
            self.vector_mask_check.setChecked(style.vector_mask_hides_effects)
            for index in range(4):
                self._blend_ranges["this_layer"][index] = style.blend_if.this_layer[index]
                self._blend_ranges["underlying"][index] = style.blend_if.underlying[index]
            self._load_blend_sliders(max(0, self.blend_channel_combo.currentIndex()))
            for kind in EFFECT_KINDS:
                effect = style.effect(kind) or default_effect(kind)
                self._load_effect_widgets(kind, effect)
                item = self._effect_items[kind]
                item.setCheckState(
                    Qt.CheckState.Checked if effect.enabled else Qt.CheckState.Unchecked
                )
        finally:
            self._updating = False

    def _load_effect_widgets(self, kind: str, effect: LayerEffect) -> None:
        for attr in self._effect_attrs[kind]:
            widget = self._effect_widgets[(kind, attr)]
            value = getattr(effect, attr)
            if isinstance(widget, ColorButton):
                widget.set_color(value)
            elif isinstance(widget, SliderField):
                if attr in ("opacity", "highlight_opacity", "shadow_opacity"):
                    widget.setValue(round(float(value) * 100))
                else:
                    widget.setValue(round(float(value)))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))

    # -------------------------------------------------------------- preview
    def _schedule_preview(self) -> None:
        if hasattr(self, "_preview_timer"):
            self._preview_timer.start()

    def _preview_region(self, style: LayerStyle | None):
        document = self.document
        if document is None:
            return None
        margin = effect_margin(style) + 16
        if self.layer.kind in (LayerKind.GROUP, LayerKind.ADJUSTMENT, LayerKind.FILL):
            width = min(document.width, 520)
            height = min(document.height, 520)
            center_x = document.width / 2.0
            center_y = document.height / 2.0
        else:
            width = min(
                document.width,
                max(160, min(560, self.layer.width + margin * 2)),
            )
            height = min(
                document.height,
                max(160, min(560, self.layer.height + margin * 2)),
            )
            center_x = self.layer.offset_x + self.layer.width / 2.0
            center_y = self.layer.offset_y + self.layer.height / 2.0
        width = max(1, int(width))
        height = max(1, int(height))
        x0 = int(max(0, min(document.width - width, round(center_x - width / 2))))
        y0 = int(max(0, min(document.height - height, round(center_y - height / 2))))
        return x0, y0, x0 + width, y0 + height

    def _refresh_preview(self) -> None:
        document = self.document
        if document is None or self.layer is None:
            return
        region = self._preview_region(self._build_style())
        if region is None:
            return
        style = self._build_style() if self.preview_check.isChecked() else None
        blend_mode = str(self.blend_combo.currentData())
        opacity = self.opacity_spin.value() / 100.0
        layers = []
        for layer in document.layers:
            clone = copy.copy(layer)
            if clone.id == self.layer.id:
                clone.style = style
                if self.layer.kind != LayerKind.ADJUSTMENT:
                    clone.blend_mode = blend_mode
                clone.opacity = opacity
            layers.append(clone)
        try:
            pixels = composite_region(
                layers,
                document.width,
                document.height,
                *region,
            )
        except (ValueError, MemoryError):
            return
        x0, y0, x1, y1 = region
        image = numpy_rgba_to_qimage(pixels)
        canvas = QPixmap(max(1, x1 - x0), max(1, y1 - y0))
        canvas.fill(QColor("#00000000"))
        painter = QPainter(canvas)
        cell = 8
        for row in range(0, canvas.height(), cell):
            for column in range(0, canvas.width(), cell):
                color = "#3a3d44" if (row // cell + column // cell) % 2 == 0 else "#2b2e35"
                painter.fillRect(column, row, cell, cell, QColor(color))
        painter.drawImage(0, 0, image)
        painter.end()
        scaled = canvas.scaled(
            PREVIEW_SIZE,
            PREVIEW_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    # --------------------------------------------------------------- preset
    def _refresh_preset_list(self) -> None:
        self.preset_list.blockSignals(True)
        try:
            self.preset_list.clear()
            self.preset_list.addItem("Mặc định (không hiệu ứng)")
            if self.preset_store is not None:
                try:
                    presets = self.preset_store.list(STYLE_PRESET_KIND)
                except PresetError as exc:
                    self.preset_status.setText(str(exc))
                    presets = []
                for preset in presets:
                    item = QListWidgetItem(preset.name)
                    item.setData(COLOR_ROLE, preset.payload)
                    self.preset_list.addItem(item)
        finally:
            self.preset_list.blockSignals(False)
        self.delete_preset_button.setEnabled(False)

    def _apply_selected_preset(self, item: QListWidgetItem) -> None:
        if self.preset_list.row(item) == 0:
            style = LayerStyle()
        else:
            payload = item.data(COLOR_ROLE)
            try:
                style = LayerStyle.from_dict(payload)
            except ValueError as exc:
                self.preset_status.setText(f"Preset hỏng: {exc}")
                return
        self._style = style
        self._load_style_into_widgets(style)
        self._schedule_preview()

    def _delete_selected_preset(self) -> None:
        row = self.preset_list.currentRow()
        if row <= 0 or self.preset_store is None:
            return
        name = self.preset_list.item(row).text()
        if (
            QMessageBox.question(
                self,
                "Xoá preset",
                f"Xoá preset layer style '{name}'?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.preset_store.delete(STYLE_PRESET_KIND, name)
        except PresetError as exc:
            self.preset_status.setText(str(exc))
            return
        self.preset_status.setText(f"Đã xoá preset '{name}'.")
        self._refresh_preset_list()

    def _save_new_style(self) -> None:
        if self.preset_store is None:
            self.preset_status.setText("Chưa có thư viện preset để lưu style.")
            return
        name, accepted = QInputDialog.getText(self, "New Style", "Tên style:")
        name = name.strip()
        if not accepted or not name:
            return
        style = self._build_style() or LayerStyle()
        overwrite = False
        try:
            existing = self.preset_store.get(STYLE_PRESET_KIND, name)
        except PresetError as exc:
            self.preset_status.setText(str(exc))
            return
        if existing is not None:
            overwrite = (
                QMessageBox.question(
                    self,
                    "Ghi đè style",
                    f"Style '{name}' đã tồn tại. Ghi đè?",
                )
                == QMessageBox.StandardButton.Yes
            )
            if not overwrite:
                return
        try:
            self.preset_store.save(
                STYLE_PRESET_KIND,
                name,
                style.to_dict(),
                overwrite=overwrite,
            )
        except PresetError as exc:
            self.preset_status.setText(str(exc))
            return
        self.preset_status.setText(f"Đã lưu style '{name}'.")
        self._refresh_preset_list()

    # --------------------------------------------------------------- kết quả
    @property
    def style(self) -> LayerStyle | None:
        return self._result_style

    @property
    def blend_mode(self) -> str:
        return self._result_blend

    @property
    def opacity(self) -> float:
        return self._result_opacity

    def accept(self) -> None:  # noqa: D401 - Qt override
        self._result_style = self._build_style()
        self._result_blend = str(self.blend_combo.currentData())
        self._result_opacity = self.opacity_spin.value() / 100.0
        super().accept()
