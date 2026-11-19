"""Options Bar — điều khiển ngữ cảnh theo công cụ đang chọn."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolBar,
    QWidget,
)

from core.layer import LayerKind
from core.paint import MAX_BRUSH_SIZE, MIN_BRUSH_SIZE, color_luminance
from core.selection import MAX_FEATHER_RADIUS
from core.shape_layer import (
    MAX_CORNER_RADIUS,
    MAX_STROKE_WIDTH,
    SHAPE_LABELS,
)
from ui import icons
from ui.formatting import format_zoom


class OptionsBar(QToolBar):
    text_layer_requested = Signal()
    shape_layer_requested = Signal()
    brush_state_changed = Signal()
    gradient_state_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Options", parent)
        self.setObjectName("OptionsBar")
        self.setMovable(False)
        self.setFloatable(False)

        self._container = QWidget(self)
        self._container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(8)
        self.addWidget(self._container)

        self._view = None
        self._tool_id = "move"
        self._view_connections: list[tuple[object, object]] = []
        self._context_connections: list[tuple[object, object]] = []
        self._doc_info: QLabel | None = None
        self._move_x: QSpinBox | None = None
        self._move_y: QSpinBox | None = None
        self._move_layer_label: QLabel | None = None
        self._selection_info: QLabel | None = None
        self._selection_feather: QSpinBox | None = None
        self._selection_antialias: QCheckBox | None = None
        self._wand_tolerance: QSpinBox | None = None
        self._wand_contiguous: QCheckBox | None = None
        self._quick_size: QSpinBox | None = None
        self._quick_tolerance: QSpinBox | None = None
        self._crop_info: QLabel | None = None
        self._crop_apply: QPushButton | None = None
        self._crop_cancel: QPushButton | None = None
        self._shape_kind: QComboBox | None = None
        self._shape_fill_check: QCheckBox | None = None
        self._shape_fill_swatch: QLabel | None = None
        self._shape_fill_button: QPushButton | None = None
        self._shape_stroke_spin: QSpinBox | None = None
        self._shape_stroke_swatch: QLabel | None = None
        self._shape_stroke_button: QPushButton | None = None
        self._shape_radius_spin: QDoubleSpinBox | None = None
        self._shape_fill_color = QColor(59, 110, 165, 255)
        self._shape_stroke_color = QColor(255, 255, 255, 255)
        self._brush_size: QSpinBox | None = None
        self._brush_hardness: QSpinBox | None = None
        self._brush_opacity: QSpinBox | None = None
        self._brush_target: QComboBox | None = None
        self._brush_swatch: QLabel | None = None
        self._brush_info: QLabel | None = None
        self._brush_color = QColor(0, 0, 0, 255)
        self._gradient_type: QComboBox | None = None
        self._gradient_preset: QComboBox | None = None
        self._gradient_swatch: QLabel | None = None
        self._gradient_target: QComboBox | None = None
        self._gradient_info: QLabel | None = None
        self._syncing = False

        self._build_empty()

    # --------------------------------------------------------------- vòng đời
    def bind_view(self, view) -> None:
        self._disconnect_view_signals()
        self._disconnect_context()
        self._view = view
        if view is not None:
            self._connect_view(view.tool_changed, lambda tool_id: self._rebuild(tool_id))
            self._connect_view(view.zoom_changed, lambda _zoom: self._update_info())
            self._connect_view(view.document.title_changed, self._update_info)
            self._tool_id = view.tool_id
        self._rebuild()

    def set_tool(self, tool_id: str) -> None:
        self._tool_id = tool_id
        self._rebuild()

    def refresh_theme(self) -> None:
        self._rebuild()

    def _connect_view(self, signal, slot) -> None:
        signal.connect(slot)
        self._view_connections.append((signal, slot))

    def _connect_context(self, signal, slot) -> None:
        signal.connect(slot)
        self._context_connections.append((signal, slot))

    def _disconnect_view_signals(self) -> None:
        for signal, slot in self._view_connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._view_connections.clear()

    def _disconnect_context(self) -> None:
        for signal, slot in self._context_connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._context_connections.clear()

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._doc_info = None
        self._move_x = None
        self._move_y = None
        self._move_layer_label = None
        self._selection_info = None
        self._selection_feather = None
        self._selection_antialias = None
        self._wand_tolerance = None
        self._wand_contiguous = None
        self._quick_size = None
        self._quick_tolerance = None
        self._crop_info = None
        self._crop_apply = None
        self._crop_cancel = None
        self._shape_kind = None
        self._shape_fill_check = None
        self._shape_fill_swatch = None
        self._shape_fill_button = None
        self._shape_stroke_spin = None
        self._shape_stroke_swatch = None
        self._shape_stroke_button = None
        self._shape_radius_spin = None
        self._brush_size = None
        self._brush_hardness = None
        self._brush_opacity = None
        self._brush_target = None
        self._brush_swatch = None
        self._brush_info = None
        self._gradient_type = None
        self._gradient_preset = None
        self._gradient_swatch = None
        self._gradient_target = None
        self._gradient_info = None

    # ------------------------------------------------------------------ build
    def _build_empty(self) -> None:
        self._clear_layout()
        label = QLabel("Không có tài liệu đang mở.", self._container)
        label.setObjectName("OptionsHint")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def _rebuild(self, tool_id: str | None = None) -> None:
        if tool_id is not None:
            self._tool_id = tool_id
        self._disconnect_context()
        self._clear_layout()
        if self._view is None:
            self._build_empty()
            return

        view = self._view
        document = view.document

        icon_label = QLabel(self._container)
        icon_label.setPixmap(icons.pixmap(self._tool_id, 20))
        icon_label.setFixedSize(20, 20)
        self._layout.addWidget(icon_label)

        name_label = QLabel(view.current_tool.name, self._container)
        name_label.setObjectName("OptionsToolName")
        self._layout.addWidget(name_label)
        self._layout.addWidget(self._separator())

        if self._tool_id == "move":
            self._build_move_options(view)
        elif self._tool_id in ("rect_select", "ellipse_select", "lasso"):
            self._build_selection_options(view)
        elif self._tool_id == "magic_wand":
            self._build_wand_options(view)
        elif self._tool_id == "quick_select":
            self._build_quick_select_options(view)
        elif self._tool_id == "crop":
            self._build_crop_options(view)
        elif self._tool_id == "text":
            self._build_text_options(view)
        elif self._tool_id == "shape":
            self._build_shape_options(view)
        elif self._tool_id in ("brush", "eraser"):
            self._build_brush_options(view, eraser=self._tool_id == "eraser")
        elif self._tool_id == "gradient":
            self._build_gradient_options(view)
        elif self._tool_id in ("hand", "zoom"):
            self._build_navigation_options(view)
        else:
            hint = QLabel(view.current_tool.hint, self._container)
            hint.setObjectName("OptionsHint")
            self._layout.addWidget(hint)

        self._layout.addStretch(1)
        self._doc_info = QLabel(self._container)
        self._doc_info.setObjectName("OptionsDocInfo")
        self._layout.addWidget(self._doc_info)

        self._connect_context(document.structure_changed, self._update_info)
        self._connect_context(document.active_layer_changed, self._sync_move_fields)
        self._connect_context(document.content_changed, self._sync_move_fields)
        self._update_info()

    def _separator(self) -> QFrame:
        frame = QFrame(self._container)
        frame.setObjectName("ToolSeparator")
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setFixedWidth(1)
        frame.setFixedHeight(20)
        return frame

    def _build_move_options(self, view) -> None:
        document = view.document
        layer = document.active_layer

        key_label = QLabel("Layer:", self._container)
        key_label.setObjectName("OptionsHint")
        self._layout.addWidget(key_label)
        self._move_layer_label = QLabel(layer.name if layer else "—", self._container)
        self._move_layer_label.setMinimumWidth(90)
        self._layout.addWidget(self._move_layer_label)

        self._layout.addWidget(self._separator())
        self._layout.addWidget(QLabel("X", self._container))
        self._move_x = QSpinBox(self._container)
        self._move_x.setRange(-30000, 30000)
        self._move_x.setFixedWidth(72)
        self._move_x.valueChanged.connect(self._on_move_offset_changed)
        self._layout.addWidget(self._move_x)

        self._layout.addWidget(QLabel("Y", self._container))
        self._move_y = QSpinBox(self._container)
        self._move_y.setRange(-30000, 30000)
        self._move_y.setFixedWidth(72)
        self._move_y.valueChanged.connect(self._on_move_offset_changed)
        self._layout.addWidget(self._move_y)

        hint = QLabel(view.current_tool.hint, self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._sync_move_fields()

    def _build_selection_options(self, view) -> None:
        options = view.selection_options()

        hint = QLabel("Shift cộng · Alt trừ", self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        feather_label = QLabel("Feather", self._container)
        feather_label.setObjectName("OptionsHint")
        self._layout.addWidget(feather_label)
        self._selection_feather = QSpinBox(self._container)
        self._selection_feather.setRange(0, int(MAX_FEATHER_RADIUS))
        self._selection_feather.setSuffix(" px")
        self._selection_feather.setFixedWidth(76)
        self._selection_feather.setValue(int(round(float(options.get("feather", 0.0)))))
        self._selection_feather.setToolTip(
            "Làm mềm biên vùng chọn sẽ vẽ (0 px = biên cứng)."
        )
        self._layout.addWidget(self._selection_feather)

        self._selection_antialias = QCheckBox("Anti-alias", self._container)
        self._selection_antialias.setChecked(bool(options.get("antialias", True)))
        self._selection_antialias.setToolTip(
            "Bật để biên ellipse/chữ nhật lẻ pixel mượt; tắt để giữ biên răng cưa."
        )
        self._layout.addWidget(self._selection_antialias)

        self._selection_feather.valueChanged.connect(self._apply_selection_options)
        self._selection_antialias.toggled.connect(self._apply_selection_options)

        self._layout.addWidget(self._separator())
        self._add_selection_actions(view)

    def _add_selection_actions(self, view) -> None:
        document = view.document

        select_all = QPushButton("Select All", self._container)
        select_all.setToolTip("Chọn toàn bộ canvas (Ctrl+A)")
        select_all.clicked.connect(document.select_all)
        self._layout.addWidget(select_all)

        deselect = QPushButton("Deselect", self._container)
        deselect.setToolTip("Bỏ vùng chọn (Ctrl+D)")
        deselect.clicked.connect(document.deselect)
        self._layout.addWidget(deselect)

        invert = QPushButton("Inverse", self._container)
        invert.setToolTip("Đảo vùng chọn (Ctrl+Shift+I)")
        invert.clicked.connect(document.invert_selection)
        self._layout.addWidget(invert)

        self._selection_info = QLabel(self._container)
        self._selection_info.setObjectName("OptionsHint")
        self._layout.addWidget(self._selection_info)
        self._connect_context(document.selection_changed, self._sync_selection_fields)
        self._sync_selection_fields()

    def _build_wand_options(self, view) -> None:
        options = view.magic_wand_options()

        hint = QLabel("Nhấp để chọn vùng màu tương tự · Shift cộng · Alt trừ", self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        tolerance_label = QLabel("Dung sai", self._container)
        tolerance_label.setObjectName("OptionsHint")
        self._layout.addWidget(tolerance_label)
        self._wand_tolerance = QSpinBox(self._container)
        self._wand_tolerance.setRange(0, 255)
        self._wand_tolerance.setValue(int(options.get("tolerance", 32)))
        self._wand_tolerance.setFixedWidth(64)
        self._wand_tolerance.setToolTip(
            "Mức lệch màu tối đa cho phép trên từng kênh RGBA (0 = giống hệt)."
        )
        self._layout.addWidget(self._wand_tolerance)

        self._wand_contiguous = QCheckBox("Liền mạch", self._container)
        self._wand_contiguous.setChecked(bool(options.get("contiguous", True)))
        self._wand_contiguous.setToolTip(
            "Bật: chỉ chọn vùng thông nhau với điểm nhấp; tắt: chọn mọi pixel giống màu."
        )
        self._layout.addWidget(self._wand_contiguous)

        self._layout.addWidget(QLabel("Feather", self._container))
        self._selection_feather = QSpinBox(self._container)
        self._selection_feather.setRange(0, int(MAX_FEATHER_RADIUS))
        self._selection_feather.setSuffix(" px")
        self._selection_feather.setFixedWidth(76)
        self._selection_feather.setValue(
            int(round(float(options.get("feather", 0.0))))
        )
        self._selection_feather.setToolTip("Làm mềm biên vùng chọn sẽ tạo.")
        self._layout.addWidget(self._selection_feather)

        self._layout.addWidget(self._separator())
        self._add_selection_actions(view)

        self._wand_tolerance.valueChanged.connect(self._apply_wand_options)
        self._wand_contiguous.toggled.connect(self._apply_wand_options)
        self._selection_feather.valueChanged.connect(self._apply_wand_options)

    def _apply_wand_options(self, _value: object = None) -> None:
        if (
            self._view is None
            or self._wand_tolerance is None
            or self._wand_contiguous is None
            or self._selection_feather is None
        ):
            return
        self._view.set_magic_wand_options(
            tolerance=self._wand_tolerance.value(),
            contiguous=self._wand_contiguous.isChecked(),
            feather=float(self._selection_feather.value()),
        )

    def _build_quick_select_options(self, view) -> None:
        options = view.quick_select_options()

        hint = QLabel("Kéo qua vùng cần chọn · Shift cộng · Alt trừ", self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        self._layout.addWidget(QLabel("Cỡ", self._container))
        self._quick_size = QSpinBox(self._container)
        self._quick_size.setRange(1, 400)
        self._quick_size.setValue(int(options.get("size", 40)))
        self._quick_size.setSuffix(" px")
        self._quick_size.setFixedWidth(82)
        self._quick_size.setToolTip("Đường kính vùng tự lan quanh con trỏ.")
        self._layout.addWidget(self._quick_size)

        self._layout.addWidget(QLabel("Dung sai", self._container))
        self._quick_tolerance = QSpinBox(self._container)
        self._quick_tolerance.setRange(0, 255)
        self._quick_tolerance.setValue(int(options.get("tolerance", 32)))
        self._quick_tolerance.setFixedWidth(64)
        self._quick_tolerance.setToolTip(
            "Mức lệch màu tối đa khi lan vùng chọn (0 = giống hệt)."
        )
        self._layout.addWidget(self._quick_tolerance)

        self._layout.addWidget(QLabel("Feather", self._container))
        self._selection_feather = QSpinBox(self._container)
        self._selection_feather.setRange(0, int(MAX_FEATHER_RADIUS))
        self._selection_feather.setSuffix(" px")
        self._selection_feather.setFixedWidth(76)
        self._selection_feather.setValue(
            int(round(float(options.get("feather", 0.0))))
        )
        self._selection_feather.setToolTip("Làm mềm biên vùng chọn sau khi thả chuột.")
        self._layout.addWidget(self._selection_feather)

        self._layout.addWidget(self._separator())
        self._add_selection_actions(view)

        self._quick_size.valueChanged.connect(self._apply_quick_select_options)
        self._quick_tolerance.valueChanged.connect(self._apply_quick_select_options)
        self._selection_feather.valueChanged.connect(
            self._apply_quick_select_options
        )

    def _apply_quick_select_options(self, _value: object = None) -> None:
        if (
            self._view is None
            or self._quick_size is None
            or self._quick_tolerance is None
            or self._selection_feather is None
        ):
            return
        self._view.set_quick_select_options(
            size=self._quick_size.value(),
            tolerance=self._quick_tolerance.value(),
            feather=float(self._selection_feather.value()),
        )

    def _apply_selection_options(self, _value: object = None) -> None:
        if self._view is None or self._selection_feather is None:
            return
        antialias = bool(
            self._selection_antialias is not None
            and self._selection_antialias.isChecked()
        )
        self._view.set_selection_options(
            feather=float(self._selection_feather.value()),
            antialias=antialias,
        )

    def _build_crop_options(self, view) -> None:
        hint = QLabel(view.current_tool.hint, self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        self._crop_apply = QPushButton("Apply Crop", self._container)
        self._crop_apply.setToolTip("Cắt ảnh theo vùng đã chọn (Enter)")
        self._crop_apply.clicked.connect(view.apply_crop)
        self._layout.addWidget(self._crop_apply)

        self._crop_cancel = QPushButton("Cancel", self._container)
        self._crop_cancel.setToolTip("Huỷ vùng crop (Esc)")
        self._crop_cancel.clicked.connect(view.clear_crop_rect)
        self._layout.addWidget(self._crop_cancel)

        self._crop_info = QLabel(self._container)
        self._crop_info.setObjectName("OptionsHint")
        self._layout.addWidget(self._crop_info)
        self._connect_context(view.crop_changed, self._sync_crop_fields)
        self._sync_crop_fields()

    def _sync_selection_fields(self) -> None:
        if self._selection_info is None or self._view is None:
            return
        selection = self._view.document.selection
        if selection is None or selection.is_empty:
            self._selection_info.setText("Chưa có vùng chọn")
            return
        bounds = selection.bounds()
        text = f"{bounds.width()} × {bounds.height()} px"
        if selection.feather > 0:
            text += f" · Feather {selection.feather:g} px"
        if not selection.antialias:
            text += " · Không anti-alias"
        self._selection_info.setText(text)

    def _sync_crop_fields(self) -> None:
        if self._view is None:
            return
        rect = self._view.crop_rect
        has_rect = rect is not None and rect.width() >= 1.0 and rect.height() >= 1.0
        if self._crop_apply is not None:
            self._crop_apply.setEnabled(has_rect)
        if self._crop_cancel is not None:
            self._crop_cancel.setEnabled(rect is not None)
        if self._crop_info is not None:
            if has_rect:
                self._crop_info.setText(
                    f"{int(rect.width())} × {int(rect.height())} px"
                )
            else:
                self._crop_info.setText("Kéo trên canvas để chọn vùng crop")

    def _build_text_options(self, view) -> None:
        hint = QLabel(view.current_tool.hint, self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        new_button = QPushButton("New Text Layer…", self._container)
        new_button.setToolTip("Tạo layer văn bản ở giữa canvas (Ctrl+Shift+T)")
        new_button.clicked.connect(lambda: self.text_layer_requested.emit())
        self._layout.addWidget(new_button)

    def _build_shape_options(self, view) -> None:
        options = view.shape_options()
        hint = QLabel("Kéo trên canvas để vẽ. Giữ Shift để tạo hình vuông/tròn.", self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        self._shape_kind = QComboBox(self._container)
        for kind, label in SHAPE_LABELS.items():
            self._shape_kind.addItem(label, kind)
        self._shape_kind.setCurrentIndex(
            max(0, self._shape_kind.findData(options.get("kind")))
        )
        self._shape_kind.setToolTip("Loại hình sẽ vẽ")
        self._layout.addWidget(self._shape_kind)

        self._shape_fill_check = QCheckBox("Tô", self._container)
        self._shape_fill_check.setChecked(options.get("fill_color") is not None)
        self._shape_fill_check.setToolTip("Bật/tắt màu tô")
        self._layout.addWidget(self._shape_fill_check)

        fill_color = options.get("fill_color") or (59, 110, 165, 255)
        self._shape_fill_color = QColor(*tuple(fill_color))
        self._shape_fill_swatch = QLabel(self._container)
        self._shape_fill_swatch.setFixedSize(24, 20)
        self._layout.addWidget(self._shape_fill_swatch)
        self._shape_fill_button = QPushButton("Màu tô…", self._container)
        self._shape_fill_button.clicked.connect(self._choose_shape_fill_color)
        self._layout.addWidget(self._shape_fill_button)

        self._layout.addWidget(QLabel("Viền", self._container))
        self._shape_stroke_spin = QSpinBox(self._container)
        self._shape_stroke_spin.setRange(0, MAX_STROKE_WIDTH)
        self._shape_stroke_spin.setValue(int(options.get("stroke_width", 0)))
        self._shape_stroke_spin.setSuffix(" px")
        self._shape_stroke_spin.setFixedWidth(78)
        self._layout.addWidget(self._shape_stroke_spin)

        self._shape_stroke_color = QColor(*tuple(options.get("stroke_color", (255, 255, 255, 255))))
        self._shape_stroke_swatch = QLabel(self._container)
        self._shape_stroke_swatch.setFixedSize(24, 20)
        self._layout.addWidget(self._shape_stroke_swatch)
        self._shape_stroke_button = QPushButton("Màu viền…", self._container)
        self._shape_stroke_button.clicked.connect(self._choose_shape_stroke_color)
        self._layout.addWidget(self._shape_stroke_button)

        self._layout.addWidget(QLabel("Bo góc", self._container))
        self._shape_radius_spin = QDoubleSpinBox(self._container)
        self._shape_radius_spin.setRange(0.0, MAX_CORNER_RADIUS)
        self._shape_radius_spin.setDecimals(1)
        self._shape_radius_spin.setSingleStep(2.0)
        self._shape_radius_spin.setValue(float(options.get("corner_radius", 0.0)))
        self._shape_radius_spin.setSuffix(" px")
        self._shape_radius_spin.setFixedWidth(86)
        self._layout.addWidget(self._shape_radius_spin)

        new_button = QPushButton("New Shape Layer…", self._container)
        new_button.setToolTip("Tạo layer hình khối ở giữa canvas")
        new_button.clicked.connect(lambda: self.shape_layer_requested.emit())
        self._layout.addWidget(new_button)

        self._shape_kind.currentIndexChanged.connect(self._on_shape_kind_changed)
        self._shape_fill_check.toggled.connect(self._on_shape_fill_toggled)
        self._shape_stroke_spin.valueChanged.connect(self._on_shape_stroke_changed)
        self._shape_radius_spin.valueChanged.connect(self._on_shape_radius_changed)

        self._update_shape_swatches()
        self._update_shape_controls()

    def _update_shape_swatches(self) -> None:
        for swatch, color in (
            (self._shape_fill_swatch, self._shape_fill_color),
            (self._shape_stroke_swatch, self._shape_stroke_color),
        ):
            if swatch is None:
                continue
            swatch.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, "
                f"{color.blue()}, {color.alpha()}); "
                "border: 1px solid #555a63; border-radius: 3px;"
            )
            swatch.setToolTip(
                f"RGBA({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
            )

    def _update_shape_controls(self) -> None:
        if self._shape_kind is not None and self._shape_radius_spin is not None:
            self._shape_radius_spin.setEnabled(
                str(self._shape_kind.currentData()) == "rounded_rectangle"
            )
        if self._shape_fill_check is not None:
            has_fill = self._shape_fill_check.isChecked()
            if self._shape_fill_swatch is not None:
                self._shape_fill_swatch.setEnabled(has_fill)
            if self._shape_fill_button is not None:
                self._shape_fill_button.setEnabled(has_fill)
        if self._shape_stroke_spin is not None:
            has_stroke = self._shape_stroke_spin.value() > 0
            if self._shape_stroke_swatch is not None:
                self._shape_stroke_swatch.setEnabled(has_stroke)
            if self._shape_stroke_button is not None:
                self._shape_stroke_button.setEnabled(has_stroke)

    def _on_shape_kind_changed(self, _index: int) -> None:
        self._update_shape_controls()
        self._apply_shape_options()

    def _on_shape_fill_toggled(self, _checked: bool) -> None:
        self._update_shape_controls()
        self._apply_shape_options()

    def _on_shape_stroke_changed(self, _value: int) -> None:
        self._update_shape_controls()
        self._apply_shape_options()

    def _on_shape_radius_changed(self, _value: float) -> None:
        self._apply_shape_options()

    def _choose_shape_fill_color(self) -> None:
        color = QColorDialog.getColor(
            self._shape_fill_color,
            self,
            "Chọn màu tô của hình",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        self._shape_fill_color = color
        self._update_shape_swatches()
        self._apply_shape_options()

    def _choose_shape_stroke_color(self) -> None:
        color = QColorDialog.getColor(
            self._shape_stroke_color,
            self,
            "Chọn màu viền của hình",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        self._shape_stroke_color = color
        self._update_shape_swatches()
        self._apply_shape_options()

    def _apply_shape_options(self) -> None:
        if self._syncing or self._view is None:
            return
        if (
            self._shape_kind is None
            or self._shape_fill_check is None
            or self._shape_fill_swatch is None
            or self._shape_stroke_spin is None
            or self._shape_radius_spin is None
        ):
            return
        fill = (
            tuple(self._shape_fill_color.getRgb())
            if self._shape_fill_check.isChecked()
            else None
        )
        self._view.set_shape_options(
            kind=str(self._shape_kind.currentData()),
            fill_color=fill,
            stroke_color=tuple(self._shape_stroke_color.getRgb()),
            stroke_width=self._shape_stroke_spin.value(),
            corner_radius=self._shape_radius_spin.value(),
        )

    def _build_brush_options(self, view, *, eraser: bool) -> None:
        options = view.eraser_options() if eraser else view.brush_options()
        hint = QLabel(view.current_tool.hint, self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        self._layout.addWidget(QLabel("Cỡ", self._container))
        self._brush_size = QSpinBox(self._container)
        self._brush_size.setRange(MIN_BRUSH_SIZE, MAX_BRUSH_SIZE)
        self._brush_size.setValue(int(options.get("size", 40)))
        self._brush_size.setSuffix(" px")
        self._brush_size.setFixedWidth(84)
        self._brush_size.setToolTip("Đường kính đầu cọ tính bằng pixel")
        self._layout.addWidget(self._brush_size)

        self._layout.addWidget(QLabel("Cứng", self._container))
        self._brush_hardness = QSpinBox(self._container)
        self._brush_hardness.setRange(0, 100)
        self._brush_hardness.setValue(int(round(float(options.get("hardness", 0.8)) * 100)))
        self._brush_hardness.setSuffix(" %")
        self._brush_hardness.setFixedWidth(74)
        self._brush_hardness.setToolTip("0 % = mép mềm, 100 % = mép cứng")
        self._layout.addWidget(self._brush_hardness)

        self._layout.addWidget(QLabel("Đục", self._container))
        self._brush_opacity = QSpinBox(self._container)
        self._brush_opacity.setRange(1, 100)
        self._brush_opacity.setValue(
            max(1, int(round(float(options.get("opacity", 1.0)) * 100)))
        )
        self._brush_opacity.setSuffix(" %")
        self._brush_opacity.setFixedWidth(74)
        self._brush_opacity.setToolTip("Độ đục tối đa của cả nét vẽ")
        self._layout.addWidget(self._brush_opacity)

        self._brush_swatch = QLabel(self._container)
        self._brush_swatch.setFixedSize(24, 20)
        self._layout.addWidget(self._brush_swatch)

        if not eraser:
            self._layout.addWidget(QLabel("Vẽ lên", self._container))
            self._brush_target = QComboBox(self._container)
            self._brush_target.addItem("Layer", "pixels")
            self._brush_target.addItem("Layer Mask", "mask")
            self._brush_target.setToolTip(
                "Vẽ lên pixel của layer hoặc lên layer mask của layer đang chọn"
            )
            self._layout.addWidget(self._brush_target)

        self._brush_info = QLabel(self._container)
        self._brush_info.setObjectName("OptionsHint")
        self._layout.addWidget(self._brush_info)

        self._brush_size.valueChanged.connect(self._on_brush_size_changed)
        self._brush_hardness.valueChanged.connect(self._on_brush_size_changed)
        self._brush_opacity.valueChanged.connect(self._on_brush_size_changed)
        if self._brush_target is not None:
            self._brush_target.currentIndexChanged.connect(
                self._on_brush_target_changed
            )

        self._connect_context(view.document.active_layer_changed, self._sync_brush_fields)
        self._connect_context(view.document.structure_changed, self._sync_brush_fields)
        self._sync_brush_fields()

    def _update_brush_swatch(self) -> None:
        if self._brush_swatch is None:
            return
        color = self._brush_color
        self._brush_swatch.setStyleSheet(
            f"background-color: rgba({color.red()}, {color.green()}, "
            f"{color.blue()}, {color.alpha()}); "
            "border: 1px solid #555a63; border-radius: 3px;"
        )
        self._brush_swatch.setToolTip(
            f"Màu Foreground: RGBA({color.red()}, {color.green()}, "
            f"{color.blue()}, {color.alpha()})"
        )

    def _sync_brush_fields(self) -> None:
        if self._view is None:
            return
        eraser = self._tool_id == "eraser"
        options = self._view.eraser_options() if eraser else self._view.brush_options()
        self._brush_color = QColor(*tuple(options.get("color", (0, 0, 0, 255))))
        self._update_brush_swatch()

        layer = self._view.document.active_layer
        has_mask = bool(layer is not None and layer.mask is not None)
        paint_mask = bool(options.get("paint_mask")) and has_mask
        if not eraser and not has_mask and options.get("paint_mask"):
            self._view.set_paint_mask(False)
            paint_mask = False
        self._syncing = True
        try:
            if self._brush_size is not None:
                self._brush_size.setValue(int(options.get("size", 40)))
            if self._brush_hardness is not None:
                self._brush_hardness.setValue(
                    int(round(float(options.get("hardness", 0.8)) * 100))
                )
            if self._brush_opacity is not None:
                self._brush_opacity.setValue(
                    max(1, int(round(float(options.get("opacity", 1.0)) * 100)))
                )
            if self._brush_target is not None:
                self._brush_target.setEnabled(has_mask)
                self._brush_target.setCurrentIndex(1 if paint_mask else 0)
        finally:
            self._syncing = False
        if self._brush_info is not None:
            if paint_mask:
                value = color_luminance(tuple(self._brush_color.getRgb()))
                self._brush_info.setText(
                    f"Mask · giá trị {value} (đen = ẩn, trắng = hiện)"
                )
            elif eraser:
                self._brush_info.setText(
                    "Tẩy làm giảm độ đục; vùng chọn giới hạn phạm vi."
                )
            else:
                self._brush_info.setText(
                    "Màu cọ lấy từ ô Foreground (Toolbox)."
                )

    def _on_brush_size_changed(self, _value: int) -> None:
        self._apply_brush_options()

    def _on_brush_target_changed(self, _index: int) -> None:
        self._apply_brush_options()

    def _apply_brush_options(self) -> None:
        if self._syncing or self._view is None:
            return
        if (
            self._brush_size is None
            or self._brush_hardness is None
            or self._brush_opacity is None
        ):
            return
        values = {
            "size": self._brush_size.value(),
            "hardness": self._brush_hardness.value() / 100.0,
            "opacity": self._brush_opacity.value() / 100.0,
        }
        if self._tool_id == "eraser":
            self._view.set_eraser_options(**values)
        else:
            paint_mask = bool(
                self._brush_target is not None
                and self._brush_target.currentData() == "mask"
            )
            self._view.set_paint_mask(paint_mask)
            self._view.set_brush_options(**values)
        self.brush_state_changed.emit()

    def _build_gradient_options(self, view) -> None:
        options = view.gradient_options()
        hint = QLabel(view.current_tool.hint, self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)
        self._layout.addWidget(self._separator())

        self._layout.addWidget(QLabel("Kiểu", self._container))
        self._gradient_type = QComboBox(self._container)
        self._gradient_type.addItem("Tuyến tính", "linear")
        self._gradient_type.addItem("Hình tròn", "radial")
        self._gradient_type.setFixedWidth(112)
        self._gradient_type.setToolTip(
            "Tuyến tính: màu chạy dọc theo hướng kéo; Hình tròn: toả từ điểm bắt đầu"
        )
        self._layout.addWidget(self._gradient_type)

        self._layout.addWidget(QLabel("Mẫu", self._container))
        self._gradient_preset = QComboBox(self._container)
        self._gradient_preset.addItem("Foreground → Background", "fg_bg")
        self._gradient_preset.addItem("Foreground → Trong suốt", "fg_transparent")
        self._gradient_preset.addItem("Đen → Trắng", "black_white")
        self._gradient_preset.addItem("Trắng → Đen", "white_black")
        self._gradient_preset.setMinimumWidth(190)
        self._gradient_preset.setToolTip("Cặp màu đầu/cuối của dải gradient")
        self._layout.addWidget(self._gradient_preset)

        self._gradient_swatch = QLabel(self._container)
        self._gradient_swatch.setFixedSize(72, 20)
        self._layout.addWidget(self._gradient_swatch)

        self._layout.addWidget(QLabel("Tô lên", self._container))
        self._gradient_target = QComboBox(self._container)
        self._gradient_target.addItem("Layer", "pixels")
        self._gradient_target.addItem("Layer Mask", "mask")
        self._gradient_target.setToolTip(
            "Tô lên pixel của layer hoặc lên layer mask của layer đang chọn"
        )
        self._layout.addWidget(self._gradient_target)

        self._gradient_info = QLabel(self._container)
        self._gradient_info.setObjectName("OptionsHint")
        self._layout.addWidget(self._gradient_info)

        self._gradient_type.currentIndexChanged.connect(self._apply_gradient_options)
        self._gradient_preset.currentIndexChanged.connect(self._apply_gradient_options)
        self._gradient_target.currentIndexChanged.connect(self._apply_gradient_options)
        self._connect_context(
            view.document.active_layer_changed, self._sync_gradient_fields
        )
        self._connect_context(view.document.structure_changed, self._sync_gradient_fields)
        self._sync_gradient_fields()

    def _apply_gradient_options(self) -> None:
        if self._syncing or self._view is None:
            return
        if self._gradient_type is None or self._gradient_preset is None:
            return
        self._view.set_gradient_options(
            gradient_type=str(self._gradient_type.currentData()),
            preset=str(self._gradient_preset.currentData()),
        )
        if self._gradient_target is not None:
            paint_mask = self._gradient_target.currentData() == "mask"
            if not self._view.set_paint_mask(paint_mask):
                self._view.set_gradient_options(paint_mask=False)
                self._syncing = True
                try:
                    self._gradient_target.setCurrentIndex(0)
                finally:
                    self._syncing = False
        self._update_gradient_swatch()
        self.gradient_state_changed.emit()

    def _sync_gradient_fields(self) -> None:
        if self._view is None:
            return
        options = self._view.gradient_options()
        layer = self._view.document.active_layer
        has_mask = bool(layer is not None and layer.mask is not None)
        paint_mask = bool(options.get("paint_mask")) and has_mask
        if not has_mask and options.get("paint_mask"):
            self._view.set_paint_mask(False)
        self._syncing = True
        try:
            if self._gradient_type is not None:
                index = self._gradient_type.findData(
                    str(options.get("gradient_type", "linear"))
                )
                if index >= 0:
                    self._gradient_type.setCurrentIndex(index)
            if self._gradient_preset is not None:
                index = self._gradient_preset.findData(str(options.get("preset", "fg_bg")))
                if index >= 0:
                    self._gradient_preset.setCurrentIndex(index)
            if self._gradient_target is not None:
                self._gradient_target.setEnabled(has_mask)
                self._gradient_target.setCurrentIndex(1 if paint_mask else 0)
        finally:
            self._syncing = False
        self._update_gradient_swatch(options)
        if self._gradient_info is not None:
            if paint_mask:
                start, end = options.get(
                    "colors", ((0, 0, 0, 255), (255, 255, 255, 255))
                )
                self._gradient_info.setText(
                    f"Mask · {color_luminance(tuple(start))} → "
                    f"{color_luminance(tuple(end))} (đen = ẩn, trắng = hiện)"
                )
            else:
                self._gradient_info.setText(
                    "Kéo từ điểm đầu tới điểm cuối; vùng chọn giới hạn phạm vi."
                )

    def _update_gradient_swatch(self, options: dict | None = None) -> None:
        if self._gradient_swatch is None or self._view is None:
            return
        if options is None:
            options = self._view.gradient_options()
        start, end = options.get("colors", ((0, 0, 0, 255), (255, 255, 255, 255)))
        start = tuple(int(channel) for channel in start)
        end = tuple(int(channel) for channel in end)
        self._gradient_swatch.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 rgba({start[0]}, {start[1]}, {start[2]}, {start[3]}), "
            f"stop:1 rgba({end[0]}, {end[1]}, {end[2]}, {end[3]})); "
            "border: 1px solid #555a63; border-radius: 3px;"
        )
        self._gradient_swatch.setToolTip(
            f"RGBA({start[0]}, {start[1]}, {start[2]}, {start[3]}) → "
            f"RGBA({end[0]}, {end[1]}, {end[2]}, {end[3]})"
        )

    def refresh_paint_colors(self) -> None:
        if self._tool_id in ("brush", "eraser"):
            self._sync_brush_fields()
        elif self._tool_id == "gradient":
            self._sync_gradient_fields()

    def sync_paint_state(self) -> None:
        """Đồng bộ lại toàn bộ widget khi trạng thái mask thay đổi từ menu."""
        if self._tool_id in ("brush", "eraser", "gradient") and self._view is not None:
            self._rebuild()

    def _build_navigation_options(self, view) -> None:
        hint = QLabel(view.current_tool.hint, self._container)
        hint.setObjectName("OptionsHint")
        self._layout.addWidget(hint)

        fit_button = QPushButton("Fit", self._container)
        fit_button.setToolTip("Vừa khung nhìn (Ctrl+0)")
        fit_button.clicked.connect(view.fit_to_window)
        self._layout.addWidget(fit_button)

        actual_button = QPushButton("100%", self._container)
        actual_button.setToolTip("Tỷ lệ thực (Ctrl+1)")
        actual_button.clicked.connect(view.zoom_actual)
        self._layout.addWidget(actual_button)

    # ------------------------------------------------------------------- sync
    def _sync_move_fields(self) -> None:
        if self._move_x is None or self._move_y is None or self._view is None:
            return
        layer = self._view.document.active_layer
        self._syncing = True
        try:
            if self._move_layer_label is not None:
                self._move_layer_label.setText(layer.name if layer else "—")
            enabled = (
                layer is not None
                and not layer.locked
                and layer.kind != LayerKind.ADJUSTMENT
            )
            self._move_x.setEnabled(enabled)
            self._move_y.setEnabled(enabled)
            self._move_x.setToolTip(
                "Layer điều chỉnh không có pixel để di chuyển."
                if layer is not None and layer.kind == LayerKind.ADJUSTMENT
                else ""
            )
            self._move_x.setValue(layer.offset_x if layer else 0)
            self._move_y.setValue(layer.offset_y if layer else 0)
        finally:
            self._syncing = False

    def _on_move_offset_changed(self, _value: int) -> None:
        if self._syncing or self._view is None:
            return
        if self._move_x is None or self._move_y is None:
            return
        layer = self._view.document.active_layer
        if layer is None or layer.locked or layer.kind == LayerKind.ADJUSTMENT:
            return
        self._view.document.set_layer_offset(layer, self._move_x.value(), self._move_y.value())

    def _update_info(self) -> None:
        if self._doc_info is None or self._view is None:
            return
        document = self._view.document
        self._doc_info.setText(
            f"RGB · {document.width} × {document.height} px · {format_zoom(self._view.zoom)}"
        )
