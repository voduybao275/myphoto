"""Panel Layers: danh sách layer, thumbnail, blend mode, opacity và sắp xếp kéo thả."""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.adjustment_layer import ADJUSTMENT_LABELS
from core.canvas import downsample_rgba, numpy_rgba_to_qimage
from core.document import Document
from core.fill_layer import FILL_LABELS, render_fill
from core.layer import BLEND_MODES, BLEND_MODE_LABELS, Layer, LayerKind
from core.shape_layer import SHAPE_LABELS
from core.text_layer import WARP_LABELS
from compat.qt import mouse_event_position
from ui import icons
from ui.theme import current_theme

ROLE_LAYER_ID = int(Qt.ItemDataRole.UserRole)
ROLE_THUMB = ROLE_LAYER_ID + 1
ROLE_VISIBLE = ROLE_LAYER_ID + 2
ROLE_SUBTITLE = ROLE_LAYER_ID + 3
ROLE_MASK_THUMB = ROLE_LAYER_ID + 4
ROLE_MASK_ENABLED = ROLE_LAYER_ID + 5
ROLE_KIND = ROLE_LAYER_ID + 6
ROLE_DEPTH = ROLE_LAYER_ID + 7

ROW_HEIGHT = 48
THUMB_SIZE = 36
MASK_SIZE = 28
EYE_ZONE_WIDTH = 28
INDENT_STEP = 14


class LayerItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        theme = current_theme()
        rect = option.rect.adjusted(2, 1, -2, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if selected:
            background = QColor(theme.selected_bg)
        elif hovered:
            background = QColor(theme.hover_bg)
        else:
            background = QColor(theme.panel_alt)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 5, 5)

        visible = bool(index.data(ROLE_VISIBLE))
        eye_color = QColor(theme.icon if visible else theme.text_disabled)
        eye_pixmap = icons.pixmap("eye" if visible else "eye_off", 16, eye_color)
        eye_y = rect.y() + (rect.height() - 16) // 2
        painter.drawPixmap(QPoint(rect.x() + 7, eye_y), eye_pixmap)

        depth = int(index.data(ROLE_DEPTH) or 0)
        indent = depth * INDENT_STEP
        if depth > 0:
            guide_x = rect.x() + 20 + (depth - 1) * INDENT_STEP
            painter.setPen(QColor(theme.border))
            painter.drawLine(
                QPoint(guide_x, rect.y() + 6), QPoint(guide_x, rect.bottom() - 6)
            )

        thumb = index.data(ROLE_THUMB)
        thumb_x = rect.x() + 30 + indent
        thumb_y = rect.y() + (rect.height() - THUMB_SIZE) // 2
        thumb_rect = QRect(thumb_x, thumb_y, THUMB_SIZE, THUMB_SIZE)
        if isinstance(thumb, QPixmap):
            painter.drawPixmap(thumb_rect, thumb)
        painter.setPen(QColor(theme.border))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(thumb_rect.adjusted(-1, -1, 0, 0))

        text_x = thumb_rect.right() + 10
        mask_thumb = index.data(ROLE_MASK_THUMB)
        if isinstance(mask_thumb, QPixmap):
            mask_x = thumb_rect.right() + 6
            mask_rect = QRect(
                mask_x,
                rect.y() + (rect.height() - MASK_SIZE) // 2,
                MASK_SIZE,
                MASK_SIZE,
            )
            painter.drawPixmap(mask_rect, mask_thumb)
            painter.setPen(QColor(theme.border))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(mask_rect.adjusted(-1, -1, 0, 0))
            if not bool(index.data(ROLE_MASK_ENABLED)):
                painter.setPen(QColor(theme.text_disabled))
                painter.drawLine(mask_rect.topLeft(), mask_rect.bottomRight())
            text_x = mask_rect.right() + 10

        name_font = QFont(option.font)
        name_font.setPointSizeF(9.0)
        name_font.setBold(index.data(ROLE_KIND) == LayerKind.GROUP)
        painter.setFont(name_font)
        name_color = QColor(theme.text if visible else theme.text_dim)
        painter.setPen(name_color)
        text_width = max(10, rect.right() - text_x - 6)
        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        elided = QFontMetrics(name_font).elidedText(name, Qt.TextElideMode.ElideRight, text_width)
        subtitle = str(index.data(ROLE_SUBTITLE) or "")
        if subtitle:
            painter.drawText(
                QRect(text_x, rect.y() + 7, text_width, 17),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                elided,
            )
            sub_font = QFont(option.font)
            sub_font.setPointSizeF(7.5)
            painter.setFont(sub_font)
            painter.setPen(QColor(theme.text_dim))
            painter.drawText(
                QRect(text_x, rect.y() + 24, text_width, 14),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                subtitle,
            )
        else:
            painter.drawText(
                QRect(text_x, rect.y(), text_width, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                elided,
            )
        painter.restore()


class LayerListWidget(QListWidget):
    eye_clicked = Signal(str)
    layer_selected = Signal(str)
    rename_requested = Signal(str)
    adjustment_requested = Signal(str)
    fill_requested = Signal(str)
    smart_requested = Signal(str)
    order_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemDelegate(LayerItemDelegate(self))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self._updating = False
        self.currentItemChanged.connect(self._on_current_item_changed)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _layer_id(self, index) -> str | None:
        item = self.item(index)
        return item.data(ROLE_LAYER_ID) if item else None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            position = mouse_event_position(event)
            item = self.itemAt(position.toPoint())
            if item is not None and position.x() <= EYE_ZONE_WIDTH:
                self.eye_clicked.emit(str(item.data(ROLE_LAYER_ID)))
                event.accept()
                return
        super().mousePressEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        before = [self._layer_id(index) for index in range(self.count())]
        super().dropEvent(event)
        after = [self._layer_id(index) for index in range(self.count())]
        if after != before and all(after):
            QTimer.singleShot(0, lambda ids=list(after): self.order_changed.emit(ids))

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if self._updating or current is None:
            return
        self.layer_selected.emit(str(current.data(ROLE_LAYER_ID)))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        layer_id = str(item.data(ROLE_LAYER_ID))
        kind = item.data(ROLE_KIND)
        if kind == LayerKind.ADJUSTMENT:
            self.adjustment_requested.emit(layer_id)
        elif kind == LayerKind.FILL:
            self.fill_requested.emit(layer_id)
        elif kind == LayerKind.SMART:
            self.smart_requested.emit(layer_id)
        else:
            self.rename_requested.emit(layer_id)


class LayersPanel(QWidget):
    message = Signal(str)
    text_requested = Signal()
    shape_requested = Signal()
    adjustment_edit_requested = Signal(str)
    fill_edit_requested = Signal(str)
    smart_edit_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LayersPanel")
        self.document: Document | None = None
        self._connections: list[tuple[object, object]] = []
        self._thumb_cache: dict[str, tuple[int, QPixmap]] = {}
        self._mask_cache: dict[str, tuple[int, QPixmap]] = {}
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(2)
        title = QLabel("LAYERS")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._new_button = self._make_button("layer_new", "New Layer (Ctrl+Shift+N)")
        self._new_button.clicked.connect(self._on_new_layer)
        self._group_button = self._make_button("folder", "New Group")
        self._group_button.clicked.connect(self._on_new_group)
        self._text_button = self._make_button("text", "New Text Layer (Ctrl+Shift+T)")
        self._text_button.clicked.connect(lambda: self.text_requested.emit())
        self._shape_button = self._make_button("shape", "New Shape Layer")
        self._shape_button.clicked.connect(lambda: self.shape_requested.emit())
        self._duplicate_button = self._make_button("layer_duplicate", "Duplicate Layer (Ctrl+J)")
        self._duplicate_button.clicked.connect(self._on_duplicate_layer)
        self._delete_button = self._make_button("layer_delete", "Delete Layer")
        self._delete_button.clicked.connect(self._on_delete_layer)
        self._merge_button = self._make_button("merge_down", "Merge Down (Ctrl+E)")
        self._merge_button.clicked.connect(self._on_merge_down)
        for button in (
            self._new_button,
            self._group_button,
            self._text_button,
            self._shape_button,
            self._duplicate_button,
            self._delete_button,
            self._merge_button,
        ):
            header.addWidget(button)
        layout.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.blend_combo = QComboBox()
        self.blend_combo.setToolTip("Blend mode của layer đang chọn")
        for mode_id, label in BLEND_MODES:
            self.blend_combo.addItem(label, mode_id)
        self.blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        controls.addWidget(self.blend_combo, 1)

        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(0, 100)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setFixedWidth(70)
        self.opacity_spin.setToolTip("Opacity của layer đang chọn")
        self.opacity_spin.valueChanged.connect(self._on_opacity_changed)
        controls.addWidget(self.opacity_spin)
        layout.addLayout(controls)

        self.layer_list = LayerListWidget(self)
        self.layer_list.eye_clicked.connect(self._on_eye_clicked)
        self.layer_list.layer_selected.connect(self._on_layer_selected)
        self.layer_list.rename_requested.connect(self._on_rename_requested)
        self.layer_list.adjustment_requested.connect(self.adjustment_edit_requested)
        self.layer_list.fill_requested.connect(self.fill_edit_requested)
        self.layer_list.smart_requested.connect(self.smart_edit_requested)
        self.layer_list.order_changed.connect(self._on_order_changed)
        layout.addWidget(self.layer_list, 1)

        self._set_controls_enabled(False)

    # ------------------------------------------------------------------ setup
    def _make_button(self, icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("PanelIconButton")
        button.setIcon(icons.icon(icon_name, 16))
        button.setIconSize(QSize(16, 16))
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        return button

    def bind_document(self, document: Document | None) -> None:
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()
        self.document = document
        if document is not None:
            self._connect(document.structure_changed, self.refresh)
            self._connect(document.active_layer_changed, self.refresh_selection)
            self._connect(document.content_changed, self.refresh_thumbnails)
        self.refresh()

    def _connect(self, signal, slot) -> None:
        signal.connect(slot)
        self._connections.append((signal, slot))

    # ------------------------------------------------------------------ build
    def refresh(self) -> None:
        document = self.document
        previous = self._updating
        self._updating = True
        try:
            self.layer_list.clear()
            if document is None:
                self._set_controls_enabled(False)
                return
            group_ids = {
                layer.id
                for layer in document.layers
                if layer.kind == LayerKind.GROUP
            }
            self._populate_rows(None, 0, group_ids, set())
            self.refresh_selection()
        finally:
            self._updating = previous

    def _populate_rows(
        self, parent_id: str | None, depth: int, group_ids: set[str], visited: set[str]
    ) -> None:
        document = self.document
        if document is None:
            return
        members = [
            layer
            for layer in document.layers
            if (layer.group_id if layer.group_id in group_ids else None) == parent_id
            and layer.id not in visited
        ]
        for layer in reversed(members):
            visited.add(layer.id)
            self.layer_list.addItem(self._make_layer_item(layer, depth))
            if layer.kind == LayerKind.GROUP:
                self._populate_rows(layer.id, depth + 1, group_ids, visited)

    def _make_layer_item(self, layer: Layer, depth: int) -> QListWidgetItem:
        item = QListWidgetItem(layer.name)
        item.setData(ROLE_LAYER_ID, layer.id)
        item.setData(ROLE_KIND, layer.kind)
        item.setData(ROLE_VISIBLE, layer.visible)
        item.setData(ROLE_DEPTH, depth)
        item.setData(ROLE_THUMB, self._thumbnail(layer))
        item.setData(ROLE_SUBTITLE, self._subtitle(layer))
        item.setData(ROLE_MASK_THUMB, self._mask_thumbnail(layer))
        item.setData(ROLE_MASK_ENABLED, layer.mask_enabled)
        item.setSizeHint(QSize(0, ROW_HEIGHT))
        tooltip = f"{layer.name}\n"
        if layer.kind == LayerKind.GROUP:
            count = len(self.document.layers.children_of(layer.id)) if self.document else 0
            tooltip += f"Nhóm · {count} layer trực tiếp\n"
            if layer.mask is not None:
                tooltip += "Mask phủ toàn tài liệu (trắng = hiện, đen = ẩn)."
            else:
                tooltip += "Opacity/blend của nhóm áp lên toàn bộ layer con."
        elif layer.kind == LayerKind.ADJUSTMENT and layer.adjustment is not None:
            tooltip += (
                f"Layer điều chỉnh · "
                f"{ADJUSTMENT_LABELS.get(layer.adjustment.kind, 'Điều chỉnh')}\n"
                f"{layer.adjustment.summary()}\n"
                "Áp lên toàn bộ layer nằm bên dưới (nhấp đôi để sửa)."
            )
        elif layer.kind == LayerKind.FILL and layer.fill_props is not None:
            tooltip += (
                f"Layer tô · {FILL_LABELS.get(layer.fill_props.fill_type, 'Tô')}\n"
                f"{layer.fill_props.summary}\n"
                "Phủ toàn canvas, không giữ pixel riêng (nhấp đôi để sửa)."
            )
        elif layer.kind == LayerKind.SMART and layer.smart_props is not None:
            smart = layer.smart_props
            tooltip += (
                f"Smart object · {smart.source_name}\n"
                f"Ảnh gốc {smart.source_width} × {smart.source_height} px · "
                f"{smart.summary}\n"
                "Xoay/lật/đổi tỉ lệ giữ chất lượng gốc (nhấp đôi để biến đổi)."
            )
        else:
            tooltip += (
                f"{layer.width} × {layer.height} px · "
                f"offset ({layer.offset_x}, {layer.offset_y})"
            )
        if layer.text is not None:
            tooltip += f"\nVăn bản: {layer.text.text.replace(chr(10), ' ')[:60]}"
        item.setToolTip(tooltip)
        return item

    def refresh_selection(self) -> None:
        document = self.document
        previous = self._updating
        self._updating = True
        try:
            active = document.active_layer if document else None
            row = -1
            for index in range(self.layer_list.count()):
                item = self.layer_list.item(index)
                if active is not None and item.data(ROLE_LAYER_ID) == active.id:
                    row = index
                    break
            if row >= 0:
                self.layer_list.setCurrentRow(row)
            else:
                self.layer_list.setCurrentRow(-1)
            if active is None:
                self._set_controls_enabled(False)
                return
            self._set_controls_enabled(True)
            is_adjustment = active.kind == LayerKind.ADJUSTMENT
            self.blend_combo.setEnabled(not is_adjustment)
            self.blend_combo.setToolTip(
                "Layer điều chỉnh không dùng blend mode; hãy đổi Opacity để "
                "giảm độ mạnh hiệu ứng."
                if is_adjustment
                else "Blend mode của layer đang chọn"
            )
            self.blend_combo.setCurrentIndex(
                max(0, self.blend_combo.findData(active.blend_mode))
            )
            self.opacity_spin.setValue(int(round(active.opacity * 100)))
        finally:
            self._updating = previous

    def refresh_thumbnails(self) -> None:
        document = self.document
        if document is None:
            return
        for index in range(self.layer_list.count()):
            item = self.layer_list.item(index)
            layer = document.layers.get(str(item.data(ROLE_LAYER_ID)))
            if layer is None:
                continue
            item.setData(ROLE_VISIBLE, layer.visible)
            item.setData(ROLE_THUMB, self._thumbnail(layer))
            item.setData(ROLE_SUBTITLE, self._subtitle(layer))
            item.setData(ROLE_MASK_THUMB, self._mask_thumbnail(layer))
            item.setData(ROLE_MASK_ENABLED, layer.mask_enabled)
        self.layer_list.viewport().update()

    def refresh_theme(self) -> None:
        self._thumb_cache.clear()
        self._mask_cache.clear()
        for icon_name, button in (
            ("layer_new", self._new_button),
            ("folder", self._group_button),
            ("text", self._text_button),
            ("layer_duplicate", self._duplicate_button),
            ("layer_delete", self._delete_button),
            ("merge_down", self._merge_button),
        ):
            button.setIcon(icons.icon(icon_name, 16))
        self.refresh()

    # --------------------------------------------------------------- thumbnail
    def _thumbnail(self, layer: Layer) -> QPixmap:
        cached = self._thumb_cache.get(layer.id)
        if cached is not None and cached[0] == layer.pixel_revision:
            return cached[1]
        theme = current_theme()
        pixmap = QPixmap(THUMB_SIZE, THUMB_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        cell = 6
        for row in range(THUMB_SIZE // cell + 1):
            for col in range(THUMB_SIZE // cell + 1):
                color = theme.checker_a if (row + col) % 2 == 0 else theme.checker_b
                painter.fillRect(
                    col * cell, row * cell, cell, cell, QColor(color)
                )
        if layer.kind == LayerKind.GROUP:
            icon_size = 22
            icon = icons.pixmap("folder", icon_size, QColor(theme.accent))
            painter.drawPixmap(
                (THUMB_SIZE - icon_size) // 2,
                (THUMB_SIZE - icon_size) // 2,
                icon,
            )
            painter.end()
            self._thumb_cache[layer.id] = (layer.pixel_revision, pixmap)
            return pixmap
        if layer.kind == LayerKind.FILL and layer.fill_props is not None:
            preview = render_fill(layer.fill_props, THUMB_SIZE, THUMB_SIZE)
            painter.drawImage(0, 0, numpy_rgba_to_qimage(preview))
            painter.end()
            self._thumb_cache[layer.id] = (layer.pixel_revision, pixmap)
            return pixmap
        if layer.kind == LayerKind.ADJUSTMENT:
            badge_font = QFont(painter.font())
            badge_font.setPointSizeF(10.0)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.setPen(QColor(theme.accent))
            painter.drawText(
                QRect(0, 0, THUMB_SIZE, THUMB_SIZE),
                int(Qt.AlignmentFlag.AlignCenter),
                "fx",
            )
            painter.end()
            self._thumb_cache[layer.id] = (layer.pixel_revision, pixmap)
            return pixmap
        preview = downsample_rgba(layer.pixels, max_side=96)
        image = numpy_rgba_to_qimage(preview)
        scaled = image.scaled(
            THUMB_SIZE,
            THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (THUMB_SIZE - scaled.width()) // 2
        y = (THUMB_SIZE - scaled.height()) // 2
        painter.drawImage(x, y, scaled)
        painter.end()
        self._thumb_cache[layer.id] = (layer.pixel_revision, pixmap)
        return pixmap

    def _mask_thumbnail(self, layer: Layer) -> QPixmap | None:
        if layer.mask is None:
            self._mask_cache.pop(layer.id, None)
            return None
        cached = self._mask_cache.get(layer.id)
        if cached is not None and cached[0] == layer.pixel_revision:
            return cached[1]
        theme = current_theme()
        pixmap = QPixmap(MASK_SIZE, MASK_SIZE)
        pixmap.fill(QColor(theme.checker_a))
        mask_height, mask_width = layer.mask.shape[:2]
        image = QImage(
            layer.mask.data,
            mask_width,
            mask_height,
            int(layer.mask.strides[0]),
            QImage.Format.Format_Grayscale8,
        )
        scaled = image.scaled(
            MASK_SIZE,
            MASK_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(pixmap)
        x = (MASK_SIZE - scaled.width()) // 2
        y = (MASK_SIZE - scaled.height()) // 2
        painter.drawImage(x, y, scaled)
        painter.end()
        self._mask_cache[layer.id] = (layer.pixel_revision, pixmap)
        return pixmap

    def _subtitle(self, layer: Layer) -> str:
        parts: list[str] = []
        if layer.kind == LayerKind.GROUP:
            count = len(self.document.layers.children_of(layer.id)) if self.document else 0
            parts.append(f"Nhóm · {count} layer")
        if layer.kind == LayerKind.ADJUSTMENT and layer.adjustment is not None:
            label = ADJUSTMENT_LABELS.get(layer.adjustment.kind, "Điều chỉnh")
            parts.append(f"Điều chỉnh · {label} · {layer.adjustment.summary()}")
        if layer.kind == LayerKind.FILL and layer.fill_props is not None:
            label = FILL_LABELS.get(
                layer.fill_props.fill_type, layer.fill_props.fill_type
            )
            summary = (
                f" · {layer.fill_props.angle}°"
                if layer.fill_props.fill_type == "gradient"
                else ""
            )
            parts.append(f"Tô · {label}{summary}")
        if layer.kind == LayerKind.SMART and layer.smart_props is not None:
            parts.append(f"Smart object · {layer.smart_props.summary}")
        if layer.kind == "text" and layer.text is not None:
            subtitle = f"Văn bản · {layer.text.font_size} px"
            if len(layer.text.runs) > 1:
                subtitle += f" · {len(layer.text.runs)} kiểu"
            if layer.text.warp_style != "none" and layer.text.warp_bend:
                label = WARP_LABELS.get(layer.text.warp_style, layer.text.warp_style)
                subtitle += f" · uốn {label.lower()}"
            parts.append(subtitle)
        if layer.kind == "shape" and layer.shape is not None:
            parts.append(SHAPE_LABELS.get(layer.shape.kind, "Hình khối"))
        if layer.mask is not None:
            parts.append("Mask" if layer.mask_enabled else "Mask tắt")
        if layer.blend_mode != "normal" and layer.kind != LayerKind.ADJUSTMENT:
            parts.append(BLEND_MODE_LABELS.get(layer.blend_mode, "Normal"))
        if layer.opacity < 0.999:
            parts.append(f"{int(round(layer.opacity * 100))}%")
        if not layer.visible:
            parts.append("Ẩn")
        return " · ".join(parts)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.blend_combo.setEnabled(enabled)
        self.opacity_spin.setEnabled(enabled)

    # --------------------------------------------------------------- handlers
    def _on_layer_selected(self, layer_id: str) -> None:
        if self._updating or self.document is None:
            return
        layer = self.document.layers.get(layer_id)
        if layer is not None:
            self.document.set_active_layer(layer)

    def _on_eye_clicked(self, layer_id: str) -> None:
        if self.document is None:
            return
        layer = self.document.layers.get(layer_id)
        if layer is not None:
            self.document.set_layer_visible(layer, not layer.visible)

    def _on_rename_requested(self, layer_id: str) -> None:
        if self.document is None:
            return
        layer = self.document.layers.get(layer_id)
        if layer is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Đổi tên layer", "Tên layer:", text=layer.name
        )
        if accepted and name.strip():
            self.document.rename_layer(layer, name)

    def _on_order_changed(self, order_ids: list[str]) -> None:
        document = self.document
        if document is None:
            return
        layers = [document.layers.get(layer_id) for layer_id in order_ids]
        if any(layer is None for layer in layers) or len(layers) != len(document.layers):
            self.refresh()
            return
        self._updating = True
        try:
            document.reorder_layers(list(reversed(layers)))
        finally:
            self._updating = False

    def _on_blend_changed(self, index: int) -> None:
        if self._updating or self.document is None:
            return
        layer = self.document.active_layer
        if layer is None:
            return
        mode = self.blend_combo.itemData(index)
        if mode:
            self.document.set_layer_blend_mode(layer, str(mode))

    def _on_opacity_changed(self, value: int) -> None:
        if self._updating or self.document is None:
            return
        layer = self.document.active_layer
        if layer is not None:
            self.document.set_layer_opacity(layer, value / 100.0)

    def _on_new_layer(self) -> None:
        if self.document is None:
            return
        self.document.add_layer()
        self.message.emit("Đã thêm layer mới.")

    def _on_new_group(self) -> None:
        if self.document is None:
            return
        group = self.document.add_group()
        self.message.emit(f"Đã thêm nhóm '{group.name}'.")

    def _on_duplicate_layer(self) -> None:
        if self.document is None or self.document.active_layer is None:
            self.message.emit("Chưa chọn layer để nhân bản.")
            return
        self.document.duplicate_layer()
        self.message.emit("Đã nhân bản layer.")

    def _on_delete_layer(self) -> None:
        if self.document is None or self.document.active_layer is None:
            self.message.emit("Chưa chọn layer để xoá.")
            return
        self.document.remove_layer()
        self.message.emit("Đã xoá layer (Ctrl+Z để hoàn tác).")

    def _on_merge_down(self) -> None:
        if self.document is None:
            return
        if self.document.merge_down():
            self.message.emit("Đã Merge Down.")
        else:
            self.message.emit("Merge Down cần layer nằm trên ít nhất một layer khác.")
