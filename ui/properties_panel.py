"""Panel Properties: thông tin tài liệu và layer đang chọn."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from config.settings import APP_VERSION
from core.adjustment_layer import ADJUSTMENT_LABELS
from core.document import Document
from core.fill_layer import FILL_LABELS, GRADIENT_LABELS
from core.layer import BLEND_MODE_LABELS, LayerKind
from core.shape_layer import SHAPE_LABELS
from core.text_layer import ALIGNMENT_LABELS, PATH_LABELS, WARP_LABELS


class PropertiesPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PropertiesPanel")
        self.document: Document | None = None
        self._connections: list[tuple[object, object]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

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

        footer = QLabel(f"My Photo Studio {APP_VERSION}")
        footer.setObjectName("WelcomeVersion")
        layout.addWidget(footer)

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
            return
        active = document.active_layer
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
            if active.kind == "text" and active.text is not None:
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
            elif active.kind == "shape" and active.shape is not None:
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
