"""Command pattern cho Undo/Redo.

Các command chỉ thao tác trên trạng thái tài liệu thông qua các phương thức
"_raw" (không phát signal, không ghi history) để tránh đệ quy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from core.layer import Layer

if TYPE_CHECKING:  # pragma: no cover
    from core.adjustment_layer import AdjustmentProperties
    from core.document import Document
    from core.fill_layer import FillProperties
    from core.selection import Selection
    from core.shape_layer import ShapeProperties
    from core.smart_object import SmartObjectProperties
    from core.text_layer import TextProperties


class Command:
    label: str = "Thao tác"

    def redo(self, document: "Document") -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def undo(self, document: "Document") -> None:  # pragma: no cover - interface
        raise NotImplementedError


class AddLayerCommand(Command):
    def __init__(self, layer: Layer, index: int, label: str = "Thêm layer") -> None:
        self.layer = layer
        self.index = index
        self.label = label

    def redo(self, document: "Document") -> None:
        document._insert_layer_raw(self.layer, self.index)

    def undo(self, document: "Document") -> None:
        document._remove_layer_raw(self.layer)


class RemoveLayerCommand(Command):
    def __init__(self, layer: Layer, index: int, label: str = "Xoá layer") -> None:
        self.layer = layer
        self.index = index
        self.label = label

    def redo(self, document: "Document") -> None:
        document._remove_layer_raw(self.layer)

    def undo(self, document: "Document") -> None:
        document._insert_layer_raw(self.layer, self.index)


class SetLayerPropertyCommand(Command):
    """Đổi thuộc tính đơn giản: visible, opacity, blend_mode, name, locked, clipping, color_label."""

    def __init__(
        self,
        layer: Layer,
        attribute: str,
        old_value: object,
        new_value: object,
        label: str,
    ) -> None:
        self.layer = layer
        self.attribute = attribute
        self.old_value = old_value
        self.new_value = new_value
        self.label = label

    def redo(self, document: "Document") -> None:
        document._apply_layer_property_raw(self.layer, self.attribute, self.new_value)

    def undo(self, document: "Document") -> None:
        document._apply_layer_property_raw(self.layer, self.attribute, self.old_value)


class SetLayerOffsetCommand(Command):
    def __init__(
        self,
        layer: Layer,
        old_offset: tuple[int, int],
        new_offset: tuple[int, int],
    ) -> None:
        self.layer = layer
        self.old_offset = old_offset
        self.new_offset = new_offset
        self.label = "Di chuyển layer"

    def redo(self, document: "Document") -> None:
        document._apply_layer_offset_raw(self.layer, *self.new_offset)

    def undo(self, document: "Document") -> None:
        document._apply_layer_offset_raw(self.layer, *self.old_offset)


class SetLayerOrderCommand(Command):
    def __init__(
        self,
        old_order: list[Layer],
        new_order: list[Layer],
        label: str = "Sắp xếp layer",
    ) -> None:
        self.old_order = list(old_order)
        self.new_order = list(new_order)
        self.label = label

    def redo(self, document: "Document") -> None:
        document._apply_layer_order_raw(self.new_order)

    def undo(self, document: "Document") -> None:
        document._apply_layer_order_raw(self.old_order)


class GroupLayersCommand(Command):
    """Đưa các layer vào một nhóm mới (một bước Undo duy nhất)."""

    def __init__(
        self,
        group: Layer,
        index: int,
        old_order: list[Layer],
        new_order: list[Layer],
        members: list[tuple[Layer, str | None]],
        label: str = "Nhóm layer",
    ) -> None:
        self.group = group
        self.index = int(index)
        self.old_order = list(old_order)
        self.new_order = list(new_order)
        self.members = list(members)
        self.label = label

    def redo(self, document: "Document") -> None:
        document._insert_layer_raw(self.group, self.index)
        document._apply_layer_order_raw(self.new_order)
        for layer, _old_group_id in self.members:
            document._apply_layer_group_raw(layer, self.group.id)

    def undo(self, document: "Document") -> None:
        for layer, old_group_id in self.members:
            document._apply_layer_group_raw(layer, old_group_id)
        document._remove_layer_raw(self.group)
        document._apply_layer_order_raw(self.old_order)


class UngroupLayersCommand(Command):
    """Bỏ một nhóm: các con trực tiếp được chuyển lên nhóm cha."""

    def __init__(
        self,
        group: Layer,
        index: int,
        children: list[Layer],
        old_order: list[Layer],
        new_order: list[Layer],
        label: str = "Bỏ nhóm",
    ) -> None:
        self.group = group
        self.index = int(index)
        self.children = list(children)
        self.old_order = list(old_order)
        self.new_order = list(new_order)
        self.parent_id = group.group_id
        self.label = label

    def redo(self, document: "Document") -> None:
        for layer in self.children:
            document._apply_layer_group_raw(layer, self.parent_id)
        document._remove_layer_raw(self.group)
        document._apply_layer_order_raw(self.new_order)

    def undo(self, document: "Document") -> None:
        document._insert_layer_raw(self.group, self.index)
        document._apply_layer_order_raw(self.old_order)
        for layer in self.children:
            document._apply_layer_group_raw(layer, self.group.id)


class SetSelectionCommand(Command):
    """Thay đổi vùng chọn (đã được tạo sẵn, Selection là bất biến theo quy ước)."""

    def __init__(
        self,
        old_selection: "Selection | None",
        new_selection: "Selection | None",
        label: str = "Thay đổi vùng chọn",
    ) -> None:
        self.old_selection = old_selection
        self.new_selection = new_selection
        self.label = label

    def redo(self, document: "Document") -> None:
        document._restore_selection_raw(self.new_selection)

    def undo(self, document: "Document") -> None:
        document._restore_selection_raw(self.old_selection)


class SetLayerMaskCommand(Command):
    """Thêm / xoá / bật-tắt layer mask."""

    def __init__(
        self,
        layer: Layer,
        old_mask: np.ndarray | None,
        old_enabled: bool,
        new_mask: np.ndarray | None,
        new_enabled: bool,
        label: str,
    ) -> None:
        self.layer = layer
        self.old_mask = old_mask
        self.old_enabled = bool(old_enabled)
        self.new_mask = new_mask
        self.new_enabled = bool(new_enabled)
        self.label = label

    def redo(self, document: "Document") -> None:
        document._apply_layer_mask_raw(self.layer, self.new_mask, self.new_enabled)

    def undo(self, document: "Document") -> None:
        document._apply_layer_mask_raw(self.layer, self.old_mask, self.old_enabled)


class ApplyLayerMaskCommand(Command):
    """Áp mask vào alpha của pixel rồi xoá mask."""

    def __init__(
        self,
        layer: Layer,
        old_pixels: np.ndarray,
        old_mask: np.ndarray,
        old_mask_enabled: bool,
        new_pixels: np.ndarray,
        label: str = "Áp layer mask",
    ) -> None:
        self.layer = layer
        self.old_pixels = old_pixels
        self.old_mask = old_mask
        self.old_mask_enabled = bool(old_mask_enabled)
        self.old_kind = layer.kind
        self.old_text = layer.text
        self.old_shape = layer.shape
        self.old_adjustment = layer.adjustment
        self.old_fill = layer.fill_props
        self.old_smart = layer.smart_props
        self.old_smart_source = layer.smart_source
        self.new_pixels = new_pixels
        self.label = label

    def redo(self, document: "Document") -> None:
        document._restore_layer_content_raw(
            self.layer, self.new_pixels, None, True, "pixel", None, None
        )

    def undo(self, document: "Document") -> None:
        document._restore_layer_content_raw(
            self.layer,
            self.old_pixels,
            self.old_mask,
            self.old_mask_enabled,
            self.old_kind,
            self.old_text,
            self.old_shape,
            self.old_adjustment,
            self.old_fill,
            self.old_smart,
            self.old_smart_source,
        )


class GeometryCommand(Command):
    """Crop / Canvas Size: đổi kích thước tài liệu và dịch offset layer.

    Dữ liệu pixel và mask của layer được giữ nguyên, chỉ thay đổi khung nhìn.
    """

    def __init__(
        self,
        old_width: int,
        old_height: int,
        new_width: int,
        new_height: int,
        old_offsets: list[tuple[Layer, int, int]],
        new_offsets: list[tuple[Layer, int, int]],
        old_selection: "Selection | None",
        new_selection: "Selection | None",
        label: str,
        *,
        old_masks: list[tuple[Layer, np.ndarray | None]] | None = None,
        new_masks: list[tuple[Layer, np.ndarray | None]] | None = None,
    ) -> None:
        self.old_width = int(old_width)
        self.old_height = int(old_height)
        self.new_width = int(new_width)
        self.new_height = int(new_height)
        self.old_offsets = list(old_offsets)
        self.new_offsets = list(new_offsets)
        self.old_selection = old_selection
        self.new_selection = new_selection
        self.old_masks = list(old_masks or [])
        self.new_masks = list(new_masks or [])
        self.label = label

    def redo(self, document: "Document") -> None:
        document._apply_geometry_raw(
            self.new_width,
            self.new_height,
            self.new_offsets,
            self.new_selection,
            self.new_masks,
        )

    def undo(self, document: "Document") -> None:
        document._apply_geometry_raw(
            self.old_width,
            self.old_height,
            self.old_offsets,
            self.old_selection,
            self.old_masks,
        )


@dataclass
class LayerSnapshot:
    """Ảnh chụp toàn bộ trạng thái pixel của một layer (dùng cho Image Size)."""

    layer: Layer
    pixels: np.ndarray
    width: int
    height: int
    offset_x: int
    offset_y: int
    mask: np.ndarray | None
    mask_enabled: bool
    kind: str = "pixel"
    text: "TextProperties | None" = None
    shape: "ShapeProperties | None" = None
    adjustment: "AdjustmentProperties | None" = None
    fill: "FillProperties | None" = None
    smart: "SmartObjectProperties | None" = None
    smart_source: np.ndarray | None = None

    @classmethod
    def capture(cls, layer: Layer) -> "LayerSnapshot":
        return cls(
            layer=layer,
            pixels=layer.pixels,
            width=layer.width,
            height=layer.height,
            offset_x=layer.offset_x,
            offset_y=layer.offset_y,
            mask=layer.mask,
            mask_enabled=layer.mask_enabled,
            kind=layer.kind,
            text=layer.text,
            shape=layer.shape,
            adjustment=layer.adjustment,
            fill=layer.fill_props,
            smart=layer.smart_props,
            smart_source=layer.smart_source,
        )


class TransformDocumentCommand(Command):
    """Image Size / xoay / lật canvas: thay kích thước tài liệu và toàn bộ layer."""

    def __init__(
        self,
        old_width: int,
        old_height: int,
        new_width: int,
        new_height: int,
        old_states: list[LayerSnapshot],
        new_states: list[LayerSnapshot],
        old_selection: "Selection | None",
        new_selection: "Selection | None",
        label: str = "Thay đổi kích thước ảnh",
    ) -> None:
        self.old_width = int(old_width)
        self.old_height = int(old_height)
        self.new_width = int(new_width)
        self.new_height = int(new_height)
        self.old_states = list(old_states)
        self.new_states = list(new_states)
        self.old_selection = old_selection
        self.new_selection = new_selection
        self.label = label

    def redo(self, document: "Document") -> None:
        document._apply_document_states_raw(
            self.new_width, self.new_height, self.new_states, self.new_selection
        )

    def undo(self, document: "Document") -> None:
        document._apply_document_states_raw(
            self.old_width, self.old_height, self.old_states, self.old_selection
        )


class LayerTransformCommand(Command):
    """Xoay/lật một layer: khôi phục toàn bộ ảnh chụp của layer."""

    def __init__(
        self,
        old_state: "LayerSnapshot",
        new_state: "LayerSnapshot",
        label: str,
    ) -> None:
        self.old_state = old_state
        self.new_state = new_state
        self.label = label

    def redo(self, document: "Document") -> None:
        document._apply_layer_snapshot_raw(self.new_state)

    def undo(self, document: "Document") -> None:
        document._apply_layer_snapshot_raw(self.old_state)


class MacroCommand(Command):
    """Gộp nhiều command để một lần Undo hoàn tác toàn bộ."""

    def __init__(self, commands: list[Command], label: str) -> None:
        self.commands = list(commands)
        self.label = label

    def redo(self, document: "Document") -> None:
        for command in self.commands:
            command.redo(document)

    def undo(self, document: "Document") -> None:
        for command in reversed(self.commands):
            command.undo(document)
