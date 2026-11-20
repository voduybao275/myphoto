"""Document: tài liệu ảnh gồm nhiều layer, history và cache composite."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QTransform

from core.adjustment_layer import AdjustmentProperties
from core.canvas import (
    composite_layers,
    numpy_rgba_to_qimage,
    scale_layers_for_preview,
)
from core.fill_layer import FillProperties, render_fill
from core.smart_object import (
    SmartObjectProperties,
    render_smart_object,
    transform_operation,
    validate_source,
)
from core.command_manager import (
    AddLayerCommand,
    ApplyLayerMaskCommand,
    GeometryCommand,
    GroupLayersCommand,
    LayerSnapshot,
    LayerTransformCommand,
    MacroCommand,
    RemoveLayerCommand,
    SetLayerMaskCommand,
    SetLayerOffsetCommand,
    SetLayerOrderCommand,
    SetLayerPropertyCommand,
    SetSelectionCommand,
    TransformDocumentCommand,
    UngroupLayersCommand,
)
from core.history_manager import HistoryManager
from core.layer import BLEND_MODE_IDS, Layer, LayerKind, LayerManager
from core.paint import BrushSettings, BrushStrokeSession, PAINT_TARGETS
from core.gradient import GradientSession, GradientSettings
from core.selection import MAX_FEATHER_RADIUS, Selection
from core.shape_layer import ShapeProperties, render_shape
from core.text_layer import TextProperties, render_text

try:  # Pillow >= 9.1 dùng enum Resampling, bản cũ dùng hằng số trên Image.
    _RESAMPLING = Image.Resampling
except AttributeError:  # pragma: no cover - tương thích Pillow cũ
    _RESAMPLING = Image

RESAMPLE_FILTERS: dict[str, object] = {
    "nearest": _RESAMPLING.NEAREST,
    "bilinear": _RESAMPLING.BILINEAR,
    "bicubic": _RESAMPLING.BICUBIC,
    "lanczos": _RESAMPLING.LANCZOS,
}

CANVAS_ANCHORS: dict[str, tuple[float, float]] = {
    "top_left": (0.0, 0.0),
    "top_center": (0.5, 0.0),
    "top_right": (1.0, 0.0),
    "middle_left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "middle_right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0),
    "bottom_center": (0.5, 1.0),
    "bottom_right": (1.0, 1.0),
}


def _same_selection(a: Selection | None, b: Selection | None) -> bool:
    if a is b:
        return True
    if a is None or b is None:
        return False
    return a == b


def _resample_rgba(
    pixels: np.ndarray, width: int, height: int, resample: object
) -> np.ndarray:
    image = Image.fromarray(np.ascontiguousarray(pixels), mode="RGBA")
    result = image.resize((int(width), int(height)), resample)
    return np.asarray(result, dtype=np.uint8).copy()


def _resample_mask(mask: np.ndarray, width: int, height: int, resample: object) -> np.ndarray:
    image = Image.fromarray(np.ascontiguousarray(mask), mode="L")
    result = image.resize((int(width), int(height)), resample)
    return np.asarray(result, dtype=np.uint8).copy()


def _rotate_array(array: np.ndarray, direction: str) -> np.ndarray:
    turns = {"cw": -1, "ccw": 1, "180": 2}.get(direction)
    if turns is None:
        raise ValueError(f"Hướng xoay không hợp lệ: {direction}")
    return np.ascontiguousarray(np.rot90(array, turns))


def _flip_array(array: np.ndarray, horizontal: bool) -> np.ndarray:
    return np.ascontiguousarray(np.flip(array, axis=1 if horizontal else 0))


def _move_canvas_mask(
    mask: np.ndarray, width: int, height: int, dx: int, dy: int
) -> np.ndarray:
    """Dịch mask cấp tài liệu theo phép Crop / Canvas Size; vùng mới điền 0."""
    result = np.zeros((int(height), int(width)), dtype=np.uint8)
    source_height, source_width = mask.shape[:2]
    x0 = max(0, dx)
    x1 = min(width, dx + source_width)
    y0 = max(0, dy)
    y1 = min(height, dy + source_height)
    if x1 > x0 and y1 > y0:
        result[y0:y1, x0:x1] = mask[
            y0 - dy : y1 - dy,
            x0 - dx : x1 - dx,
        ]
    return result


def rotated_dimensions(width: int, height: int, angle: float) -> tuple[int, int]:
    """Kích thước ảnh sau khi xoay theo góc (độ; dương = chiều kim đồng hồ)."""
    if not math.isfinite(angle):
        raise ValueError("Góc xoay không hợp lệ.")
    width = max(1, int(width))
    height = max(1, int(height))
    radians = math.radians(float(angle))
    cosine = abs(math.cos(radians))
    sine = abs(math.sin(radians))
    return (
        max(1, math.ceil(width * cosine + height * sine - 1e-9)),
        max(1, math.ceil(width * sine + height * cosine - 1e-9)),
    )


def _normalize_angle(angle: float) -> float:
    value = float(angle)
    if not math.isfinite(value):
        raise ValueError("Góc xoay không hợp lệ.")
    value = value % 360.0
    if value > 180.0:
        value -= 360.0
    return value


def _rotation_matrix(
    width: int, height: int, new_width: int, new_height: int, angle: float
) -> tuple[float, float, float, float, float, float]:
    """Ma trận affine (đích → nguồn) để Pillow xoay quanh tâm ảnh."""
    radians = math.radians(float(angle))
    cosine = round(math.cos(radians), 15)
    sine = round(math.sin(radians), 15)
    return (
        cosine,
        sine,
        width / 2.0 - cosine * new_width / 2.0 - sine * new_height / 2.0,
        -sine,
        cosine,
        height / 2.0 + sine * new_width / 2.0 - cosine * new_height / 2.0,
    )


def _rotate_rgba_free(
    pixels: np.ndarray, angle: float, resample: object
) -> np.ndarray:
    height, width = pixels.shape[:2]
    new_width, new_height = rotated_dimensions(width, height, angle)
    matrix = _rotation_matrix(width, height, new_width, new_height, angle)
    image = Image.fromarray(np.ascontiguousarray(pixels), mode="RGBA")
    result = image.transform(
        (new_width, new_height),
        Image.Transform.AFFINE,
        matrix,
        resample=resample,
        fillcolor=(0, 0, 0, 0),
    )
    return np.asarray(result, dtype=np.uint8).copy()


def _rotate_mask_free(mask: np.ndarray, angle: float, resample: object) -> np.ndarray:
    height, width = mask.shape[:2]
    new_width, new_height = rotated_dimensions(width, height, angle)
    matrix = _rotation_matrix(width, height, new_width, new_height, angle)
    image = Image.fromarray(np.ascontiguousarray(mask), mode="L")
    result = image.transform(
        (new_width, new_height),
        Image.Transform.AFFINE,
        matrix,
        resample=resample,
        fillcolor=0,
    )
    return np.asarray(result, dtype=np.uint8).copy()


@dataclass
class CompositeImage:
    """Giữ cả mảng NumPy (chủ sở hữu bộ nhớ) và QImage trỏ vào mảng đó."""

    array: np.ndarray
    image: QImage


class Document(QObject):
    content_changed = Signal()
    structure_changed = Signal()
    active_layer_changed = Signal()
    modified_changed = Signal(bool)
    title_changed = Signal()
    history_changed = Signal()
    selection_changed = Signal()

    MAX_DIMENSION = 30_000
    MAX_PIXELS = 400_000_000  # ~400 MP, chặn mở file bất thường

    def __init__(
        self,
        width: int,
        height: int,
        dpi: float = 72.0,
        name: str = "Untitled",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not (1 <= int(width) <= self.MAX_DIMENSION):
            raise ValueError(f"Chiều rộng phải trong khoảng 1..{self.MAX_DIMENSION} px.")
        if not (1 <= int(height) <= self.MAX_DIMENSION):
            raise ValueError(f"Chiều cao phải trong khoảng 1..{self.MAX_DIMENSION} px.")
        if int(width) * int(height) > self.MAX_PIXELS:
            raise ValueError("Kích thước ảnh vượt giới hạn an toàn (400 megapixel).")

        self.width = int(width)
        self.height = int(height)
        self.dpi = float(dpi) if dpi and dpi > 0 else 72.0
        self.layers = LayerManager()
        self.history = HistoryManager()
        self.file_path: str | None = None

        self._name = name
        self._active_layer_id: str | None = None
        self._selection: Selection | None = None
        self._modified = False
        self._revision = 0
        self._composite_rev = -1
        self._composite: CompositeImage | None = None
        self._dirty_log: list[tuple[int, tuple[int, int, int, int] | None]] = []
        self._preview_key: tuple[int, int] | None = None
        self._preview_array: np.ndarray | None = None
        self._preview_image: QImage | None = None
        self._layer_counter = 1

    # ------------------------------------------------------------ thông tin chung
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        value = str(value).strip() or "Untitled"
        if value != self._name:
            self._name = value
            self.title_changed.emit()

    @property
    def base_title(self) -> str:
        return Path(self.file_path).name if self.file_path else self._name

    @property
    def title(self) -> str:
        return self.base_title + ("*" if self._modified else "")

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def active_layer(self) -> Layer | None:
        return self.layers.get(self._active_layer_id)

    @property
    def history_index(self) -> int:
        return len(self.history)

    def memory_estimate(self) -> int:
        total = sum(layer.pixels.nbytes for layer in self.layers)
        total += sum(layer.mask.nbytes for layer in self.layers if layer.mask is not None)
        if self._composite is not None:
            total += self._composite.array.nbytes
        if self._preview_array is not None:
            total += self._preview_array.nbytes
        return total

    # --------------------------------------------------------------- active layer
    def set_active_layer(self, layer: Layer | str | None) -> None:
        if isinstance(layer, str):
            target = self.layers.get(layer)
            if target is None:
                raise ValueError("Không tìm thấy layer.")
        elif layer is not None:
            self.layers.index_of(layer)  # xác thực layer thuộc tài liệu
            target = layer
        else:
            target = None
        new_id = target.id if target is not None else None
        if new_id != self._active_layer_id:
            self._active_layer_id = new_id
            self.active_layer_changed.emit()

    # ------------------------------------------------------------------- layers
    def _insert_index_above_active(self) -> int:
        active = self.active_layer
        if active is None:
            return len(self.layers)
        index = self.layers.index_of(active)
        if active.kind == LayerKind.GROUP:
            # Chèn ngay dưới nhóm = trên cùng các layer con.
            return index
        return index + 1

    def _insert_parent_for_active(self) -> str | None:
        active = self.active_layer
        if active is None:
            return None
        if active.kind == LayerKind.GROUP:
            return active.id
        return active.group_id

    def _next_layer_name(self) -> str:
        used = {layer.name for layer in self.layers}
        while f"Layer {self._layer_counter}" in used:
            self._layer_counter += 1
        name = f"Layer {self._layer_counter}"
        self._layer_counter += 1
        return name

    def add_layer(
        self,
        layer: Layer | None = None,
        *,
        name: str | None = None,
        color: tuple[int, int, int, int] | None = None,
        index: int | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        if layer is None:
            layer = Layer(self.width, self.height, name or self._next_layer_name())
            if color is not None:
                layer.fill(color)
        else:
            if layer.width < 1 or layer.height < 1:
                raise ValueError("Layer không hợp lệ.")
            if name:
                layer.name = name
        auto_index = index is None
        insert_at = self._insert_index_above_active() if auto_index else index
        if auto_index and layer.group_id is None:
            layer.group_id = self._insert_parent_for_active()
        command = AddLayerCommand(layer, insert_at)
        self._apply_command(command, record=record)
        if select:
            self.set_active_layer(layer)
        return layer

    def add_text_layer(
        self,
        properties: TextProperties,
        x: int | None = None,
        y: int | None = None,
        *,
        name: str | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        """Tạo layer văn bản (vẫn chỉnh sửa được cho tới khi rasterize)."""
        if not isinstance(properties, TextProperties):
            raise TypeError("Thuộc tính văn bản phải là TextProperties.")
        pixels = render_text(properties)
        layer = Layer(pixels.shape[1], pixels.shape[0], name or properties.default_name)
        layer.kind = LayerKind.TEXT
        layer.text = properties
        layer.set_pixels(pixels)
        offset_x = (self.width - layer.width) // 2 if x is None else int(x)
        offset_y = (self.height - layer.height) // 2 if y is None else int(y)
        layer.offset_x = offset_x
        layer.offset_y = offset_y
        return self.add_layer(
            layer, name=name, select=select, record=record
        )

    def add_shape_layer(
        self,
        properties: ShapeProperties,
        x: int | None = None,
        y: int | None = None,
        *,
        name: str | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        """Tạo layer hình khối (vẫn chỉnh sửa được cho tới khi rasterize)."""
        if not isinstance(properties, ShapeProperties):
            raise TypeError("Thuộc tính hình khối phải là ShapeProperties.")
        pixels = render_shape(properties)
        layer = Layer(pixels.shape[1], pixels.shape[0], name or properties.default_name)
        layer.kind = LayerKind.SHAPE
        layer.shape = properties
        layer.set_pixels(pixels)
        offset_x = (self.width - layer.width) // 2 if x is None else int(x)
        offset_y = (self.height - layer.height) // 2 if y is None else int(y)
        layer.offset_x = offset_x
        layer.offset_y = offset_y
        return self.add_layer(
            layer, name=name, select=select, record=record
        )

    def _next_adjustment_name(self, base: str) -> str:
        used = {layer.name for layer in self.layers}
        if base not in used:
            return base
        suffix = 2
        while f"{base} {suffix}" in used:
            suffix += 1
        return f"{base} {suffix}"

    def add_adjustment_layer(
        self,
        properties: AdjustmentProperties,
        *,
        name: str | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        """Tạo layer điều chỉnh áp lên toàn bộ layer nằm bên dưới."""
        if not isinstance(properties, AdjustmentProperties):
            raise TypeError("Thuộc tính điều chỉnh phải là AdjustmentProperties.")
        layer = Layer(1, 1, name or self._next_adjustment_name(properties.default_name))
        layer.kind = LayerKind.ADJUSTMENT
        layer.adjustment = properties
        return self.add_layer(layer, name=name, select=select, record=record)

    def _next_group_name(self) -> str:
        used = {layer.name for layer in self.layers}
        counter = 1
        while f"Group {counter}" in used:
            counter += 1
        return f"Group {counter}"

    def add_group(
        self,
        *,
        name: str | None = None,
        index: int | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        """Tạo nhóm rỗng; nếu đang chọn nhóm thì nhóm mới nằm lồng bên trong."""
        layer = Layer(1, 1, name or self._next_group_name())
        layer.kind = LayerKind.GROUP
        return self.add_layer(
            layer, name=name, index=index, select=select, record=record
        )

    def _subtree_layers(self, group: Layer) -> list[Layer]:
        """Nhóm và toàn bộ layer con/cháu, theo thứ tự tài liệu từ dưới lên."""
        ids = {group.id}
        pending = [group.id]
        while pending:
            parent_id = pending.pop()
            for child in self.layers.children_of(parent_id):
                if child.id not in ids:
                    ids.add(child.id)
                    if child.kind == LayerKind.GROUP:
                        pending.append(child.id)
        return [layer for layer in self.layers if layer.id in ids]

    def group_layers(
        self,
        layers: list[Layer] | None = None,
        *,
        name: str | None = None,
        record: bool = True,
    ) -> Layer | None:
        """Đưa layer (mặc định layer đang chọn) vào một nhóm mới."""
        members = (
            list(layers)
            if layers is not None
            else ([self.active_layer] if self.active_layer is not None else [])
        )
        ordered: list[Layer] = []
        seen: set[str] = set()
        for layer in members:
            if layer is None:
                continue
            self.layers.index_of(layer)
            if layer.id not in seen:
                seen.add(layer.id)
                ordered.append(layer)
        if not ordered:
            return None
        member_ids = {layer.id for layer in ordered}
        for layer in ordered:
            parent_id = layer.group_id
            while parent_id:
                if parent_id in member_ids:
                    raise ValueError(
                        "Không thể nhóm một layer cùng lúc với nhóm cha của nó."
                    )
                parent = self.layers.get(parent_id)
                parent_id = parent.group_id if parent is not None else None

        ordered = [layer for layer in self.layers if layer.id in member_ids]
        top_index = max(self.layers.index_of(layer) for layer in ordered)
        old_order = list(self.layers)
        remaining = [layer for layer in old_order if layer.id not in member_ids]
        insert_at = sum(
            1 for layer in remaining if old_order.index(layer) < top_index
        )
        group = Layer(1, 1, name or self._next_group_name())
        group.kind = LayerKind.GROUP
        group.group_id = ordered[-1].group_id
        new_order = (
            remaining[:insert_at] + ordered + [group] + remaining[insert_at:]
        )
        members_state = [(layer, layer.group_id) for layer in ordered]
        command = GroupLayersCommand(
            group,
            insert_at + len(ordered),
            old_order,
            new_order,
            members_state,
        )
        self._apply_command(command, record=record)
        self.set_active_layer(group)
        return group

    def ungroup_layer(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Bỏ một cấp nhóm; các layer con trực tiếp chuyển lên nhóm cha."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.GROUP:
            return False
        if target.mask is not None:
            raise ValueError(
                "Nhóm đang có layer mask. Hãy xoá mask trước khi bỏ nhóm."
            )
        children = self.layers.children_of(target.id)
        old_order = list(self.layers)
        index = self.layers.index_of(target)
        new_order = [item for item in old_order if item is not target]
        command = UngroupLayersCommand(
            target, index, children, old_order, new_order
        )
        self._apply_command(command, record=record)
        if children:
            self.set_active_layer(children[-1])
        return True

    def duplicate_layer(self, layer: Layer | None = None, *, record: bool = True) -> Layer:
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Không có layer để nhân bản.")
        if target.kind == LayerKind.GROUP:
            subtree = self._subtree_layers(target)
            clones = {item.id: item.copy() for item in subtree}
            for item in subtree:
                parent_id = item.group_id
                clones[item.id].group_id = (
                    clones[parent_id].id if parent_id in clones else parent_id
                )
            base = self.layers.index_of(subtree[-1]) + 1
            commands = [
                AddLayerCommand(
                    clones[item.id], base + offset, label="Nhân bản nhóm"
                )
                for offset, item in enumerate(subtree)
            ]
            self._apply_command(
                MacroCommand(commands, label="Nhân bản nhóm"), record=record
            )
            clone = clones[target.id]
        else:
            index = self.layers.index_of(target)
            clone = target.copy()
            command = AddLayerCommand(clone, index + 1, label="Nhân bản layer")
            self._apply_command(command, record=record)
        self.set_active_layer(clone)
        return clone

    def remove_layer(self, layer: Layer | None = None, *, record: bool = True) -> bool:
        target = layer or self.active_layer
        if target is None or target not in self.layers.layers:
            return False
        if target.kind == LayerKind.GROUP:
            subtree = self._subtree_layers(target)
            commands = [
                RemoveLayerCommand(item, self.layers.index_of(item))
                for item in reversed(subtree)
            ]
            self._apply_command(
                MacroCommand(commands, label="Xoá nhóm"), record=record
            )
            return True
        index = self.layers.index_of(target)
        command = RemoveLayerCommand(target, index)
        self._apply_command(command, record=record)
        return True

    def rename_layer(self, layer: Layer | None, new_name: str) -> bool:
        target = layer or self.active_layer
        if target is None:
            return False
        cleaned = str(new_name).strip()
        if not cleaned or cleaned == target.name:
            return False
        command = SetLayerPropertyCommand(
            target, "name", target.name, cleaned, label="Đổi tên layer"
        )
        self._apply_command(command)
        return True

    def set_layer_visible(self, layer: Layer, visible: bool) -> bool:
        visible = bool(visible)
        if layer.visible == visible:
            return False
        command = SetLayerPropertyCommand(
            layer,
            "visible",
            layer.visible,
            visible,
            label="Hiện layer" if visible else "Ẩn layer",
        )
        self._apply_command(command)
        return True

    def set_layer_locked(self, layer: Layer, locked: bool) -> bool:
        locked = bool(locked)
        if layer.locked == locked:
            return False
        command = SetLayerPropertyCommand(
            layer,
            "locked",
            layer.locked,
            locked,
            label="Khoá layer" if locked else "Mở khoá layer",
        )
        self._apply_command(command)
        return True

    def set_layer_opacity(self, layer: Layer, opacity: float) -> bool:
        opacity = float(max(0.0, min(1.0, opacity)))
        if abs(layer.opacity - opacity) < 1e-6:
            return False
        command = SetLayerPropertyCommand(
            layer, "opacity", layer.opacity, opacity, label="Đổi độ mờ layer"
        )
        self._apply_command(command)
        return True

    def set_layer_blend_mode(self, layer: Layer, blend_mode: str) -> bool:
        if blend_mode not in BLEND_MODE_IDS:
            raise ValueError(f"Blend mode không hợp lệ: {blend_mode}")
        if layer.blend_mode == blend_mode:
            return False
        command = SetLayerPropertyCommand(
            layer, "blend_mode", layer.blend_mode, blend_mode, label="Đổi chế độ trộn"
        )
        self._apply_command(command)
        return True

    def set_layer_offset(self, layer: Layer, x: int, y: int) -> bool:
        x, y = int(x), int(y)
        if layer.offset_x == x and layer.offset_y == y:
            return False
        command = SetLayerOffsetCommand(layer, (layer.offset_x, layer.offset_y), (x, y))
        self._apply_command(command)
        return True

    def preview_layer_offset(self, layer: Layer, x: int, y: int) -> None:
        """Cập nhật offset trong lúc kéo (chưa ghi history)."""
        x, y = int(x), int(y)
        if layer.offset_x == x and layer.offset_y == y:
            return
        self._apply_layer_offset_raw(layer, x, y)
        self.mark_modified()
        self.invalidate()

    def commit_layer_offset(
        self, layer: Layer, old_offset: tuple[int, int], new_offset: tuple[int, int]
    ) -> None:
        old_offset = (int(old_offset[0]), int(old_offset[1]))
        new_offset = (int(new_offset[0]), int(new_offset[1]))
        if old_offset == new_offset:
            return
        self.history.push(SetLayerOffsetCommand(layer, old_offset, new_offset))
        self.history_changed.emit()

    def reorder_layers(self, new_order: list[Layer]) -> bool:
        old_order = list(self.layers)
        if len(new_order) != len(old_order):
            raise ValueError("Danh sách layer mới không hợp lệ.")
        if all(a is b for a, b in zip(old_order, new_order)):
            return False
        command = SetLayerOrderCommand(old_order, new_order)
        self._apply_command(command)
        return True

    def move_layer(self, layer: Layer, new_index: int) -> bool:
        old_order = list(self.layers)
        new_order = list(old_order)
        new_order.remove(layer)
        new_index = max(0, min(int(new_index), len(new_order)))
        new_order.insert(new_index, layer)
        return self.reorder_layers(new_order)

    # ----------------------------------------------------------- merge / flatten
    def merge_down(self, layer: Layer | None = None) -> bool:
        upper = layer or self.active_layer
        if upper is None:
            return False
        index = self.layers.index_of(upper)
        if index == 0:
            return False
        lower = self.layers[index - 1]
        if (
            upper.kind == LayerKind.GROUP
            or lower.kind == LayerKind.GROUP
            or upper.group_id != lower.group_id
        ):
            return False

        merged_pixels = composite_layers([lower, upper], self.width, self.height)
        merged = Layer(self.width, self.height, f"{lower.name}")
        merged.set_pixels(merged_pixels)
        merged.group_id = upper.group_id

        commands = [
            RemoveLayerCommand(upper, index, label="Merge Down"),
            RemoveLayerCommand(lower, index - 1, label="Merge Down"),
            AddLayerCommand(merged, index - 1, label="Merge Down"),
        ]
        self._apply_command(MacroCommand(commands, label="Merge Down"))
        self.set_active_layer(merged)
        return True

    def flatten_image(self) -> bool:
        if len(self.layers) == 0:
            return False
        merged_pixels = composite_layers(list(self.layers), self.width, self.height)
        merged = Layer(self.width, self.height, "Flattened")
        merged.set_pixels(merged_pixels)

        commands: list = []
        for index in range(len(self.layers) - 1, -1, -1):
            commands.append(RemoveLayerCommand(self.layers[index], index, label="Flatten Image"))
        commands.append(AddLayerCommand(merged, 0, label="Flatten Image"))
        self._apply_command(MacroCommand(commands, label="Flatten Image"))
        self.set_active_layer(merged)
        return True

    # --------------------------------------------------------------- vùng chọn
    @property
    def selection(self) -> Selection | None:
        return self._selection

    def has_selection(self) -> bool:
        return self._selection is not None and not self._selection.is_empty

    def selection_mask(self) -> np.ndarray | None:
        if not self.has_selection():
            return None
        return self._selection.mask()

    def _normalize_selection(self, selection: Selection | None) -> Selection | None:
        if selection is None:
            return None
        if not isinstance(selection, Selection):
            raise TypeError("Vùng chọn phải là đối tượng Selection.")
        if (selection.width, selection.height) != (self.width, self.height):
            raise ValueError("Vùng chọn không khớp kích thước tài liệu.")
        return None if selection.is_empty else selection

    def preview_selection(self, selection: Selection | None) -> None:
        """Cập nhật vùng chọn trong lúc kéo chuột (chưa ghi history)."""
        normalized = self._normalize_selection(selection)
        if _same_selection(self._selection, normalized):
            return
        self._selection = normalized
        self.selection_changed.emit()

    def set_selection(
        self, selection: Selection | None, label: str = "Thay đổi vùng chọn"
    ) -> bool:
        normalized = self._normalize_selection(selection)
        old = self._selection
        if _same_selection(old, normalized):
            return False
        self._selection = normalized
        self.selection_changed.emit()
        self.history.push(SetSelectionCommand(old, normalized, label))
        self.history_changed.emit()
        self.mark_modified()
        return True

    def commit_selection(
        self,
        old_selection: Selection | None,
        new_selection: Selection | None,
        label: str = "Thay đổi vùng chọn",
    ) -> None:
        """Ghi history sau khi công cụ đã preview vùng chọn mới."""
        old = self._normalize_selection(old_selection)
        new = self._normalize_selection(new_selection)
        if not _same_selection(self._selection, new):
            self._selection = new
            self.selection_changed.emit()
        if _same_selection(old, new):
            return
        self.history.push(SetSelectionCommand(old, new, label))
        self.history_changed.emit()
        self.mark_modified()

    def select_all(self) -> bool:
        return self.set_selection(
            Selection.all(self.width, self.height), "Chọn tất cả"
        )

    def deselect(self) -> bool:
        return self.set_selection(None, "Bỏ chọn")

    def invert_selection(self) -> bool:
        if not self.has_selection():
            return self.select_all()
        return self.set_selection(self._selection.inverted(), "Đảo vùng chọn")

    def feather_selection(self, radius: float) -> bool:
        """Làm mềm biên vùng chọn hiện tại; 0 px trả lại biên cứng."""
        if not self.has_selection():
            return False
        value = float(radius)
        if not math.isfinite(value) or not (0.0 <= value <= MAX_FEATHER_RADIUS):
            raise ValueError(
                f"Bán kính feather phải trong khoảng 0..{MAX_FEATHER_RADIUS:g} px."
            )
        return self.set_selection(
            self._selection.with_feather(value), "Feather vùng chọn"
        )

    # -------------------------------------------------------------- layer mask
    def _mask_from_selection(self, layer: Layer, invert: bool = False) -> np.ndarray:
        if layer.uses_canvas_mask:
            # Mask của layer điều chỉnh/nhóm phủ toàn tài liệu để giới hạn
            # hiệu ứng hoặc độ hiện của cả nhóm theo từng điểm ảnh.
            if self.has_selection():
                result = np.ascontiguousarray(self._selection.mask())
            else:
                result = np.full((self.height, self.width), 255, dtype=np.uint8)
            if invert:
                result = 255 - result
            return result
        if self.has_selection():
            document_mask = self._selection.mask()
            result = np.zeros((layer.height, layer.width), dtype=np.uint8)
            x0 = max(0, layer.offset_x)
            x1 = min(self.width, layer.offset_x + layer.width)
            y0 = max(0, layer.offset_y)
            y1 = min(self.height, layer.offset_y + layer.height)
            if x1 > x0 and y1 > y0:
                result[
                    y0 - layer.offset_y : y1 - layer.offset_y,
                    x0 - layer.offset_x : x1 - layer.offset_x,
                ] = document_mask[y0:y1, x0:x1]
        else:
            result = np.full((layer.height, layer.width), 255, dtype=np.uint8)
        if invert:
            result = 255 - result
        return result

    def add_layer_mask(
        self,
        layer: Layer | None = None,
        *,
        invert: bool = False,
        record: bool = True,
    ) -> bool:
        """Tạo mask: để trắng phần nằm trong vùng chọn (hoặc toàn bộ nếu không chọn)."""
        target = layer or self.active_layer
        if target is None:
            return False
        mask = self._mask_from_selection(target, invert=invert)
        command = SetLayerMaskCommand(
            target, target.mask, target.mask_enabled, mask, True, "Thêm layer mask"
        )
        self._apply_command(command, record=record)
        return True

    def remove_layer_mask(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        target = layer or self.active_layer
        if target is None or target.mask is None:
            return False
        command = SetLayerMaskCommand(
            target, target.mask, target.mask_enabled, None, True, "Xoá layer mask"
        )
        self._apply_command(command, record=record)
        return True

    def set_layer_mask_enabled(
        self, layer: Layer | None, enabled: bool, *, record: bool = True
    ) -> bool:
        target = layer or self.active_layer
        if target is None or target.mask is None:
            return False
        enabled = bool(enabled)
        if target.mask_enabled == enabled:
            return False
        command = SetLayerMaskCommand(
            target,
            target.mask,
            target.mask_enabled,
            target.mask,
            enabled,
            "Bật layer mask" if enabled else "Tắt layer mask",
        )
        self._apply_command(command, record=record)
        return True

    def apply_layer_mask(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        target = layer or self.active_layer
        if target is None or target.mask is None:
            return False
        if target.uses_canvas_mask:
            raise ValueError(
                "Layer điều chỉnh/nhóm không có pixel để áp mask.\n"
                "Hãy giữ mask hoặc xoá mask thay vì áp vào pixel."
            )
        new_pixels = target.pixels.copy()
        if target.mask_enabled:
            alpha = new_pixels[..., 3].astype(np.uint16)
            scaled = (alpha * target.mask.astype(np.uint16) + 127) // 255
            new_pixels[..., 3] = scaled.astype(np.uint8)
        command = ApplyLayerMaskCommand(
            target,
            target.pixels,
            target.mask,
            target.mask_enabled,
            new_pixels,
        )
        self._apply_command(command, record=record)
        return True

    # ----------------------------------------------------- hình học tài liệu
    def _validate_dimensions(self, width: int, height: int) -> tuple[int, int]:
        width, height = int(width), int(height)
        if not (1 <= width <= self.MAX_DIMENSION):
            raise ValueError(f"Chiều rộng phải trong khoảng 1..{self.MAX_DIMENSION} px.")
        if not (1 <= height <= self.MAX_DIMENSION):
            raise ValueError(f"Chiều cao phải trong khoảng 1..{self.MAX_DIMENSION} px.")
        if width * height > self.MAX_PIXELS:
            raise ValueError("Kích thước ảnh vượt giới hạn an toàn (400 megapixel).")
        return width, height

    def crop(self, x: int, y: int, width: int, height: int, *, record: bool = True) -> bool:
        x, y, width, height = int(x), int(y), int(width), int(height)
        if width < 1 or height < 1:
            raise ValueError("Vùng crop phải có kích thước >= 1 px.")
        if x < 0 or y < 0 or x + width > self.width or y + height > self.height:
            raise ValueError("Vùng crop phải nằm trong tài liệu.")
        if (x, y, width, height) == (0, 0, self.width, self.height):
            return False
        return self._apply_geometry(
            width, height, -x, -y, None, "Crop", record=record
        )

    def crop_to_selection(self, *, record: bool = True) -> bool:
        if not self.has_selection():
            return False
        bounds = self._selection.bounds()
        if bounds.width() < 1 or bounds.height() < 1:
            return False
        return self.crop(
            bounds.x(), bounds.y(), bounds.width(), bounds.height(), record=record
        )

    def canvas_size(
        self,
        width: int,
        height: int,
        anchor: str = "center",
        *,
        record: bool = True,
    ) -> bool:
        width, height = self._validate_dimensions(width, height)
        if anchor not in CANVAS_ANCHORS:
            raise ValueError(f"Anchor không hợp lệ: {anchor}")
        if (width, height) == (self.width, self.height):
            return False
        ax, ay = CANVAS_ANCHORS[anchor]
        dx = int(round((width - self.width) * ax))
        dy = int(round((height - self.height) * ay))
        new_selection = None
        if self.has_selection():
            new_selection = self._selection.placed(width, height, dx, dy)
        return self._apply_geometry(
            width, height, dx, dy, new_selection, "Canvas Size", record=record
        )

    def _apply_geometry(
        self,
        width: int,
        height: int,
        dx: int,
        dy: int,
        selection: Selection | None,
        label: str,
        *,
        record: bool,
    ) -> bool:
        old_offsets = [
            (layer, layer.offset_x, layer.offset_y) for layer in self.layers
        ]
        new_offsets = [
            (
                layer,
                offset_x if layer.uses_canvas_mask else offset_x + dx,
                offset_y if layer.uses_canvas_mask else offset_y + dy,
            )
            for layer, offset_x, offset_y in old_offsets
        ]
        old_masks = [
            (layer, layer.mask)
            for layer in self.layers
            if layer.uses_canvas_mask and layer.mask is not None
        ]
        new_masks = [
            (layer, _move_canvas_mask(mask, width, height, dx, dy))
            for layer, mask in old_masks
        ]
        command = GeometryCommand(
            self.width,
            self.height,
            width,
            height,
            old_offsets,
            new_offsets,
            self._selection,
            selection,
            label,
            old_masks=old_masks,
            new_masks=new_masks,
        )
        self._apply_command(command, record=record)
        return True

    def resize_image(
        self,
        width: int,
        height: int,
        method: str = "bicubic",
        *,
        record: bool = True,
    ) -> bool:
        width, height = self._validate_dimensions(width, height)
        resample = RESAMPLE_FILTERS.get(method)
        if resample is None:
            raise ValueError(f"Phương pháp resample không hỗ trợ: {method}")
        if (width, height) == (self.width, self.height):
            return False
        sx = width / self.width
        sy = height / self.height

        old_states: list[LayerSnapshot] = []
        new_states: list[LayerSnapshot] = []
        for layer in self.layers:
            old_states.append(LayerSnapshot.capture(layer))
            if layer.uses_canvas_mask:
                mask = (
                    _resample_mask(layer.mask, width, height, resample)
                    if layer.mask is not None
                    else None
                )
                new_states.append(
                    LayerSnapshot(
                        layer=layer,
                        pixels=layer.pixels,
                        width=layer.width,
                        height=layer.height,
                        offset_x=0,
                        offset_y=0,
                        mask=mask,
                        mask_enabled=layer.mask_enabled,
                        kind=layer.kind,
                        adjustment=layer.adjustment,
                    )
                )
                continue
            layer_width = max(1, int(round(layer.width * sx)))
            layer_height = max(1, int(round(layer.height * sy)))
            pixels = _resample_rgba(layer.pixels, layer_width, layer_height, resample)
            mask = None
            if layer.mask is not None:
                mask = _resample_mask(layer.mask, layer_width, layer_height, resample)
            new_states.append(
                LayerSnapshot(
                    layer=layer,
                    pixels=pixels,
                    width=layer_width,
                    height=layer_height,
                    offset_x=int(round(layer.offset_x * sx)),
                    offset_y=int(round(layer.offset_y * sy)),
                    mask=mask,
                    mask_enabled=layer.mask_enabled,
                )
            )

        new_selection = None
        if self.has_selection():
            new_selection = self._selection.scaled(sx, sy, width, height)

        command = TransformDocumentCommand(
            self.width,
            self.height,
            width,
            height,
            old_states,
            new_states,
            self._selection,
            new_selection,
        )
        self._apply_command(command, record=record)
        return True

    # ------------------------------------------------------- xoay / lật canvas
    def rotate_canvas(self, direction: str, *, record: bool = True) -> bool:
        """Xoay toàn bộ canvas 90° theo chiều kim đồng hồ, ngược lại hoặc 180°."""
        if direction not in ("cw", "ccw", "180"):
            raise ValueError(f"Hướng xoay không hợp lệ: {direction}")
        if direction == "180":
            new_width, new_height = self.width, self.height
        else:
            new_width, new_height = self.height, self.width

        old_states: list[LayerSnapshot] = []
        new_states: list[LayerSnapshot] = []
        for layer in self.layers:
            old_states.append(LayerSnapshot.capture(layer))
            if layer.uses_canvas_mask:
                mask = (
                    _rotate_array(layer.mask, direction)
                    if layer.mask is not None
                    else None
                )
                new_states.append(
                    LayerSnapshot(
                        layer=layer,
                        pixels=layer.pixels,
                        width=layer.width,
                        height=layer.height,
                        offset_x=0,
                        offset_y=0,
                        mask=mask,
                        mask_enabled=layer.mask_enabled,
                        kind=layer.kind,
                        adjustment=layer.adjustment,
                    )
                )
                continue
            pixels = _rotate_array(layer.pixels, direction)
            mask = (
                _rotate_array(layer.mask, direction)
                if layer.mask is not None
                else None
            )
            if direction == "cw":
                offset_x = self.height - layer.offset_y - layer.height
                offset_y = layer.offset_x
            elif direction == "ccw":
                offset_x = layer.offset_y
                offset_y = self.width - layer.offset_x - layer.width
            else:
                offset_x = self.width - layer.offset_x - layer.width
                offset_y = self.height - layer.offset_y - layer.height
            new_states.append(
                LayerSnapshot(
                    layer=layer,
                    pixels=pixels,
                    width=pixels.shape[1],
                    height=pixels.shape[0],
                    offset_x=offset_x,
                    offset_y=offset_y,
                    mask=mask,
                    mask_enabled=layer.mask_enabled,
                )
            )

        new_selection = None
        if self.has_selection():
            if direction == "cw":
                new_selection = self._selection.rotated_clockwise()
            elif direction == "ccw":
                new_selection = self._selection.rotated_counter_clockwise()
            else:
                new_selection = self._selection.rotated_180()

        labels = {
            "cw": "Xoay canvas 90° theo chiều kim đồng hồ",
            "ccw": "Xoay canvas 90° ngược chiều kim đồng hồ",
            "180": "Xoay canvas 180°",
        }
        command = TransformDocumentCommand(
            self.width,
            self.height,
            new_width,
            new_height,
            old_states,
            new_states,
            self._selection,
            new_selection,
            labels[direction],
        )
        self._apply_command(command, record=record)
        return True

    def rotate_canvas_arbitrary(
        self,
        angle: float,
        method: str = "bicubic",
        *,
        record: bool = True,
    ) -> bool:
        """Xoay toàn bộ canvas theo góc bất kỳ (độ; dương = kim đồng hồ)."""
        resample = RESAMPLE_FILTERS.get(method)
        if resample is None:
            raise ValueError(f"Phương pháp resample không hỗ trợ: {method}")
        angle = _normalize_angle(angle)
        if abs(angle) < 1e-9:
            return False
        if abs(angle - 90.0) < 1e-9:
            return self.rotate_canvas("cw", record=record)
        if abs(angle + 90.0) < 1e-9:
            return self.rotate_canvas("ccw", record=record)
        if abs(abs(angle) - 180.0) < 1e-9:
            return self.rotate_canvas("180", record=record)

        new_width, new_height = rotated_dimensions(self.width, self.height, angle)
        new_width, new_height = self._validate_dimensions(new_width, new_height)
        radians = math.radians(angle)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        center_x = self.width / 2.0
        center_y = self.height / 2.0

        old_states: list[LayerSnapshot] = []
        new_states: list[LayerSnapshot] = []
        for layer in self.layers:
            old_states.append(LayerSnapshot.capture(layer))
            if layer.uses_canvas_mask:
                mask = (
                    _rotate_mask_free(layer.mask, angle, resample)
                    if layer.mask is not None
                    else None
                )
                new_states.append(
                    LayerSnapshot(
                        layer=layer,
                        pixels=layer.pixels,
                        width=layer.width,
                        height=layer.height,
                        offset_x=0,
                        offset_y=0,
                        mask=mask,
                        mask_enabled=layer.mask_enabled,
                        kind=layer.kind,
                        adjustment=layer.adjustment,
                    )
                )
                continue
            pixels = _rotate_rgba_free(layer.pixels, angle, resample)
            layer_width, layer_height = pixels.shape[1], pixels.shape[0]
            mask = (
                _rotate_mask_free(layer.mask, angle, resample)
                if layer.mask is not None
                else None
            )
            dx = layer.offset_x + layer.width / 2.0 - center_x
            dy = layer.offset_y + layer.height / 2.0 - center_y
            new_center_x = cosine * dx - sine * dy + new_width / 2.0
            new_center_y = sine * dx + cosine * dy + new_height / 2.0
            new_states.append(
                LayerSnapshot(
                    layer=layer,
                    pixels=pixels,
                    width=layer_width,
                    height=layer_height,
                    offset_x=int(round(new_center_x - layer_width / 2.0)),
                    offset_y=int(round(new_center_y - layer_height / 2.0)),
                    mask=mask,
                    mask_enabled=layer.mask_enabled,
                )
            )

        new_selection = None
        if self.has_selection():
            transform = QTransform()
            transform.translate(new_width / 2.0, new_height / 2.0)
            transform.rotate(angle)
            transform.translate(-center_x, -center_y)
            new_selection = self._selection.transformed(
                transform, new_width, new_height
            )

        command = TransformDocumentCommand(
            self.width,
            self.height,
            new_width,
            new_height,
            old_states,
            new_states,
            self._selection,
            new_selection,
            f"Xoay canvas {angle:g}°",
        )
        self._apply_command(command, record=record)
        return True

    def flip_canvas(self, horizontal: bool = True, *, record: bool = True) -> bool:
        """Lật toàn bộ canvas theo chiều ngang hoặc dọc."""
        old_states: list[LayerSnapshot] = []
        new_states: list[LayerSnapshot] = []
        for layer in self.layers:
            old_states.append(LayerSnapshot.capture(layer))
            if layer.uses_canvas_mask:
                mask = (
                    _flip_array(layer.mask, horizontal)
                    if layer.mask is not None
                    else None
                )
                new_states.append(
                    LayerSnapshot(
                        layer=layer,
                        pixels=layer.pixels,
                        width=layer.width,
                        height=layer.height,
                        offset_x=0,
                        offset_y=0,
                        mask=mask,
                        mask_enabled=layer.mask_enabled,
                        kind=layer.kind,
                        adjustment=layer.adjustment,
                    )
                )
                continue
            pixels = _flip_array(layer.pixels, horizontal)
            mask = (
                _flip_array(layer.mask, horizontal)
                if layer.mask is not None
                else None
            )
            offset_x = (
                self.width - layer.offset_x - layer.width
                if horizontal
                else layer.offset_x
            )
            offset_y = (
                layer.offset_y
                if horizontal
                else self.height - layer.offset_y - layer.height
            )
            new_states.append(
                LayerSnapshot(
                    layer=layer,
                    pixels=pixels,
                    width=layer.width,
                    height=layer.height,
                    offset_x=offset_x,
                    offset_y=offset_y,
                    mask=mask,
                    mask_enabled=layer.mask_enabled,
                )
            )

        new_selection = None
        if self.has_selection():
            new_selection = (
                self._selection.flipped_horizontal()
                if horizontal
                else self._selection.flipped_vertical()
            )

        label = "Lật canvas theo chiều ngang" if horizontal else "Lật canvas theo chiều dọc"
        command = TransformDocumentCommand(
            self.width,
            self.height,
            self.width,
            self.height,
            old_states,
            new_states,
            self._selection,
            new_selection,
            label,
        )
        self._apply_command(command, record=record)
        return True

    # -------------------------------------------------------- xoay / lật layer
    def transform_layer(
        self,
        operation: str,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Xoay/lật một layer quanh tâm của nó; vùng chọn không đổi."""
        labels = {
            "rotate_cw": "Xoay layer 90° theo chiều kim đồng hồ",
            "rotate_ccw": "Xoay layer 90° ngược chiều kim đồng hồ",
            "rotate_180": "Xoay layer 180°",
            "flip_h": "Lật layer theo chiều ngang",
            "flip_v": "Lật layer theo chiều dọc",
        }
        if operation not in labels:
            raise ValueError(f"Thao tác layer không hỗ trợ: {operation}")
        target = layer or self.active_layer
        if target is None:
            return False
        if target.locked:
            raise ValueError(f"Layer '{target.name}' đang bị khoá.")
        if target.uses_canvas_mask:
            raise ValueError(
                "Layer điều chỉnh/nhóm/layer tô không hỗ trợ xoay/lật trực tiếp.\n"
                "Hãy xoay/lật các layer con hoặc toàn canvas thay vì biến đổi."
            )

        if target.kind == LayerKind.SMART and target.smart_props is not None:
            if target.mask is not None:
                raise ValueError(
                    "Không thể xoay/lật smart object khi layer đang có mask.\n"
                    "Hãy áp hoặc xoá mask trước."
                )
            properties = transform_operation(target.smart_props, operation)
            return self._apply_smart_properties(
                target, properties, labels[operation], record=record
            )

        old_state = LayerSnapshot.capture(target)
        if operation == "rotate_cw":
            pixels = _rotate_array(target.pixels, "cw")
        elif operation == "rotate_ccw":
            pixels = _rotate_array(target.pixels, "ccw")
        elif operation == "rotate_180":
            pixels = _rotate_array(target.pixels, "180")
        elif operation == "flip_h":
            pixels = _flip_array(target.pixels, True)
        else:
            pixels = _flip_array(target.pixels, False)

        if target.mask is None:
            mask = None
        elif operation == "rotate_cw":
            mask = _rotate_array(target.mask, "cw")
        elif operation == "rotate_ccw":
            mask = _rotate_array(target.mask, "ccw")
        elif operation == "rotate_180":
            mask = _rotate_array(target.mask, "180")
        elif operation == "flip_h":
            mask = _flip_array(target.mask, True)
        else:
            mask = _flip_array(target.mask, False)

        if operation in ("rotate_cw", "rotate_ccw"):
            new_width, new_height = target.height, target.width
            offset_x = int(round(target.offset_x + (target.width - new_width) / 2))
            offset_y = int(round(target.offset_y + (target.height - new_height) / 2))
        else:
            new_width, new_height = target.width, target.height
            offset_x, offset_y = target.offset_x, target.offset_y

        new_state = LayerSnapshot(
            layer=target,
            pixels=pixels,
            width=new_width,
            height=new_height,
            offset_x=offset_x,
            offset_y=offset_y,
            mask=mask,
            mask_enabled=target.mask_enabled,
        )
        command = LayerTransformCommand(old_state, new_state, labels[operation])
        self._apply_command(command, record=record)
        return True

    def rotate_layer_arbitrary(
        self,
        angle: float,
        layer: Layer | None = None,
        method: str = "bicubic",
        *,
        record: bool = True,
    ) -> bool:
        """Xoay một layer theo góc bất kỳ quanh tâm layer (dương = kim đồng hồ)."""
        resample = RESAMPLE_FILTERS.get(method)
        if resample is None:
            raise ValueError(f"Phương pháp resample không hỗ trợ: {method}")
        angle = _normalize_angle(angle)
        if abs(angle) < 1e-9:
            return False
        target = layer or self.active_layer
        if target is None:
            return False
        if target.locked:
            raise ValueError(f"Layer '{target.name}' đang bị khoá.")
        if target.uses_canvas_mask:
            raise ValueError(
                "Layer điều chỉnh/nhóm/layer tô không hỗ trợ xoay/lật trực tiếp.\n"
                "Hãy xoay/lật các layer con hoặc toàn canvas thay vì biến đổi."
            )
        if abs(angle - 90.0) < 1e-9:
            return self.transform_layer("rotate_cw", target, record=record)
        if abs(angle + 90.0) < 1e-9:
            return self.transform_layer("rotate_ccw", target, record=record)
        if abs(abs(angle) - 180.0) < 1e-9:
            return self.transform_layer("rotate_180", target, record=record)

        if target.kind == LayerKind.SMART and target.smart_props is not None:
            if target.mask is not None:
                raise ValueError(
                    "Không thể xoay smart object khi layer đang có mask.\n"
                    "Hãy áp hoặc xoá mask trước."
                )
            from dataclasses import replace

            properties = replace(target.smart_props, angle=target.smart_props.angle + angle)
            return self._apply_smart_properties(
                target,
                properties,
                f"Xoay smart object {angle:g}°",
                record=record,
            )

        old_state = LayerSnapshot.capture(target)
        pixels = _rotate_rgba_free(target.pixels, angle, resample)
        mask = (
            _rotate_mask_free(target.mask, angle, resample)
            if target.mask is not None
            else None
        )
        new_width, new_height = pixels.shape[1], pixels.shape[0]
        center_x = target.offset_x + target.width / 2.0
        center_y = target.offset_y + target.height / 2.0
        new_state = LayerSnapshot(
            layer=target,
            pixels=pixels,
            width=new_width,
            height=new_height,
            offset_x=int(round(center_x - new_width / 2.0)),
            offset_y=int(round(center_y - new_height / 2.0)),
            mask=mask,
            mask_enabled=target.mask_enabled,
        )
        command = LayerTransformCommand(
            old_state, new_state, f"Xoay layer {angle:g}°"
        )
        self._apply_command(command, record=record)
        return True

    # -------------------------------------------------------- layer văn bản
    def update_text_layer(
        self,
        properties: TextProperties,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Sửa nội dung/thuộc tính của layer văn bản và render lại."""
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Không có layer để sửa văn bản.")
        if target.kind != LayerKind.TEXT or target.text is None:
            raise ValueError("Layer đang chọn không phải layer văn bản.")
        if not isinstance(properties, TextProperties):
            raise TypeError("Thuộc tính văn bản phải là TextProperties.")
        if target.mask is not None:
            raise ValueError(
                "Không thể sửa văn bản khi layer đang có mask.\n"
                "Hãy áp hoặc xoá mask trước khi chỉnh nội dung."
            )
        if properties == target.text:
            return False
        pixels = render_text(properties)
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=pixels,
            width=pixels.shape[1],
            height=pixels.shape[0],
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=None,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.TEXT,
            text=properties,
        )
        command = LayerTransformCommand(old_state, new_state, "Sửa văn bản")
        self._apply_command(command, record=record)
        return True

    def rasterize_text_layer(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Chuyển layer văn bản thành layer pixel thường (không sửa chữ được nữa)."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.TEXT:
            return False
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=target.pixels,
            width=target.width,
            height=target.height,
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=target.mask,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.PIXEL,
            text=None,
        )
        command = LayerTransformCommand(old_state, new_state, "Rasterize văn bản")
        self._apply_command(command, record=record)
        return True

    # -------------------------------------------------------- layer hình khối
    def update_shape_layer(
        self,
        properties: ShapeProperties,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Sửa thuộc tính của layer hình khối và render lại."""
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Không có layer để sửa hình khối.")
        if target.kind != LayerKind.SHAPE or target.shape is None:
            raise ValueError("Layer đang chọn không phải layer hình khối.")
        if not isinstance(properties, ShapeProperties):
            raise TypeError("Thuộc tính hình khối phải là ShapeProperties.")
        if target.mask is not None:
            raise ValueError(
                "Không thể sửa hình khối khi layer đang có mask.\n"
                "Hãy áp hoặc xoá mask trước khi chỉnh hình khối."
            )
        if properties == target.shape:
            return False
        pixels = render_shape(properties)
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=pixels,
            width=pixels.shape[1],
            height=pixels.shape[0],
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=None,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.SHAPE,
            shape=properties,
        )
        command = LayerTransformCommand(old_state, new_state, "Sửa hình khối")
        self._apply_command(command, record=record)
        return True

    def rasterize_shape_layer(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Chuyển layer hình khối thành layer pixel thường."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.SHAPE:
            return False
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=target.pixels,
            width=target.width,
            height=target.height,
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=target.mask,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.PIXEL,
            shape=None,
        )
        command = LayerTransformCommand(old_state, new_state, "Rasterize hình khối")
        self._apply_command(command, record=record)
        return True

    # ------------------------------------------------------- layer tô màu
    def add_fill_layer(
        self,
        properties: FillProperties,
        *,
        name: str | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        """Tạo layer tô không phá huỷ phủ toàn canvas (compositor tự dựng màu)."""
        if not isinstance(properties, FillProperties):
            raise TypeError("Thuộc tính layer tô phải là FillProperties.")
        layer = Layer(1, 1, name or self._next_adjustment_name(properties.default_name))
        layer.kind = LayerKind.FILL
        layer.fill_props = properties
        layer.offset_x = 0
        layer.offset_y = 0
        return self.add_layer(layer, name=name, select=select, record=record)

    def update_fill_layer(
        self,
        properties: FillProperties,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Đổi màu/kiểu tô của layer fill; composite tự dựng lại."""
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Không có layer để sửa màu tô.")
        if target.kind != LayerKind.FILL or target.fill_props is None:
            raise ValueError("Layer đang chọn không phải layer tô.")
        if not isinstance(properties, FillProperties):
            raise TypeError("Thuộc tính layer tô phải là FillProperties.")
        if properties == target.fill_props:
            return False
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=target.pixels,
            width=target.width,
            height=target.height,
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=target.mask,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.FILL,
            fill=properties,
        )
        command = LayerTransformCommand(old_state, new_state, "Sửa layer tô")
        self._apply_command(command, record=record)
        return True

    def rasterize_fill_layer(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Nướng màu tô (và mask) thành layer pixel kích thước tài liệu."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.FILL or target.fill_props is None:
            return False
        pixels = render_fill(target.fill_props, self.width, self.height)
        if target.mask is not None and target.mask_enabled:
            alpha = pixels[..., 3].astype(np.uint16)
            mask = target.mask.astype(np.uint16)
            pixels[..., 3] = ((alpha * mask + 127) // 255).astype(np.uint8)
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=pixels,
            width=self.width,
            height=self.height,
            offset_x=0,
            offset_y=0,
            mask=None,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.PIXEL,
        )
        command = LayerTransformCommand(old_state, new_state, "Rasterize layer tô")
        self._apply_command(command, record=record)
        return True

    # ------------------------------------------------------- smart object
    def _apply_smart_properties(
        self,
        target: Layer,
        properties: SmartObjectProperties,
        label: str,
        *,
        record: bool,
        source: np.ndarray | None = None,
    ) -> bool:
        source_array = target.smart_source if source is None else source
        if source_array is None:
            raise ValueError("Smart object không còn dữ liệu ảnh nguồn.")
        pixels = render_smart_object(source_array, properties)
        center_x = target.offset_x + target.width / 2.0
        center_y = target.offset_y + target.height / 2.0
        new_width = pixels.shape[1]
        new_height = pixels.shape[0]
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=pixels,
            width=new_width,
            height=new_height,
            offset_x=int(round(center_x - new_width / 2.0)),
            offset_y=int(round(center_y - new_height / 2.0)),
            mask=None,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.SMART,
            smart=properties,
            smart_source=source_array,
        )
        command = LayerTransformCommand(old_state, new_state, label)
        self._apply_command(command, record=record)
        return True

    def add_smart_object_layer(
        self,
        source: np.ndarray,
        properties: SmartObjectProperties | None = None,
        *,
        name: str | None = None,
        x: int | None = None,
        y: int | None = None,
        select: bool = True,
        record: bool = True,
    ) -> Layer:
        """Đặt ảnh làm smart object, giữ bản sao nguồn để biến đổi lại."""
        source_array = validate_source(source)
        height, width = source_array.shape[:2]
        if properties is None:
            properties = SmartObjectProperties(
                source_name=name or "Smart Object",
                source_width=width,
                source_height=height,
            )
        elif not isinstance(properties, SmartObjectProperties):
            raise TypeError("Thuộc tính smart object phải là SmartObjectProperties.")
        if (properties.source_width, properties.source_height) != (width, height):
            raise ValueError("Kích thước thuộc tính không khớp ảnh nguồn.")
        pixels = render_smart_object(source_array, properties)
        layer = Layer(pixels.shape[1], pixels.shape[0], name or properties.default_name)
        layer.kind = LayerKind.SMART
        layer.smart_props = properties
        layer.smart_source = source_array.copy()
        layer.set_pixels(pixels)
        layer.offset_x = (
            (self.width - layer.width) // 2 if x is None else int(x)
        )
        layer.offset_y = (
            (self.height - layer.height) // 2 if y is None else int(y)
        )
        return self.add_layer(layer, name=name, select=select, record=record)

    def update_smart_object(
        self,
        properties: SmartObjectProperties,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Đổi góc/tỉ lệ/lật của smart object và dựng lại pixel từ nguồn."""
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Không có smart object để biến đổi.")
        if target.kind != LayerKind.SMART or target.smart_props is None:
            raise ValueError("Layer đang chọn không phải smart object.")
        if not isinstance(properties, SmartObjectProperties):
            raise TypeError("Thuộc tính smart object phải là SmartObjectProperties.")
        if target.mask is not None:
            raise ValueError(
                "Không thể biến đổi smart object khi layer đang có mask.\n"
                "Hãy áp hoặc xoá mask trước."
            )
        if properties == target.smart_props:
            return False
        return self._apply_smart_properties(
            target, properties, "Biến đổi smart object", record=record
        )

    def replace_smart_contents(
        self,
        source: np.ndarray,
        layer: Layer | None = None,
        *,
        name: str | None = None,
        record: bool = True,
    ) -> bool:
        """Thay ảnh nguồn của smart object, giữ nguyên biến đổi hiện tại."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.SMART or target.smart_props is None:
            raise ValueError("Layer đang chọn không phải smart object.")
        if target.mask is not None:
            raise ValueError(
                "Không thể thay nội dung khi smart object đang có mask.\n"
                "Hãy áp hoặc xoá mask trước."
            )
        source_array = validate_source(source)
        height, width = source_array.shape[:2]
        from dataclasses import replace

        properties = replace(
            target.smart_props,
            source_name=name or target.smart_props.source_name,
            source_width=width,
            source_height=height,
        )
        return self._apply_smart_properties(
            target,
            properties,
            "Thay nội dung smart object",
            record=record,
            source=source_array,
        )

    def reset_smart_object(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Đưa smart object về ảnh gốc không xoay/lật/đổi tỉ lệ."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.SMART or target.smart_props is None:
            return False
        from dataclasses import replace

        properties = replace(
            target.smart_props, angle=0.0, scale=100.0, flip_h=False, flip_v=False
        )
        if properties == target.smart_props:
            return False
        if target.mask is not None:
            raise ValueError(
                "Không thể đặt lại smart object khi layer đang có mask.\n"
                "Hãy áp hoặc xoá mask trước."
            )
        return self._apply_smart_properties(
            target, properties, "Đặt lại smart object", record=record
        )

    def rasterize_smart_layer(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Chuyển smart object thành layer pixel (mất khả năng biến đổi lại)."""
        target = layer or self.active_layer
        if target is None or target.kind != LayerKind.SMART:
            return False
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=target.pixels,
            width=target.width,
            height=target.height,
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=target.mask,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.PIXEL,
        )
        command = LayerTransformCommand(old_state, new_state, "Rasterize smart object")
        self._apply_command(command, record=record)
        return True

    # ---------------------------------------------------- layer điều chỉnh
    def update_adjustment_layer(
        self,
        properties: AdjustmentProperties,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Sửa tham số của layer điều chỉnh; composite tự tính lại."""
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Không có layer để sửa điều chỉnh.")
        if target.kind != LayerKind.ADJUSTMENT or target.adjustment is None:
            raise ValueError("Layer đang chọn không phải layer điều chỉnh.")
        if not isinstance(properties, AdjustmentProperties):
            raise TypeError("Thuộc tính điều chỉnh phải là AdjustmentProperties.")
        if properties == target.adjustment:
            return False
        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=target.pixels,
            width=target.width,
            height=target.height,
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=target.mask,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.ADJUSTMENT,
            adjustment=properties,
        )
        command = LayerTransformCommand(old_state, new_state, "Sửa layer điều chỉnh")
        self._apply_command(command, record=record)
        return True

    def begin_brush_stroke(
        self,
        settings: BrushSettings,
        *,
        target: str = "pixels",
        layer: Layer | None = None,
    ) -> BrushStrokeSession:
        """Bắt đầu một nét cọ trên layer hoặc layer mask của layer đang chọn."""
        if not isinstance(settings, BrushSettings):
            raise TypeError("Thông số cọ phải là BrushSettings.")
        if target not in PAINT_TARGETS:
            raise ValueError(f"Đích vẽ không hợp lệ: {target}")
        target_layer = layer or self.active_layer
        if target_layer is None:
            raise ValueError("Chưa chọn layer nào để vẽ.")
        if target_layer.uses_canvas_mask and target == "pixels":
            raise ValueError(
                "Layer điều chỉnh/nhóm không có pixel để vẽ. "
                "Hãy chọn layer ảnh khác."
            )
        if target_layer.locked:
            raise ValueError(f"Layer '{target_layer.name}' đang bị khoá.")
        if target == "mask" and target_layer.mask is None:
            raise ValueError(
                f"Layer '{target_layer.name}' chưa có mask. "
                "Hãy thêm Layer Mask trước khi vẽ lên mask."
            )
        return BrushStrokeSession(self, target_layer, settings, target=target)

    def begin_gradient(
        self,
        settings: GradientSettings,
        start: tuple[float, float],
        *,
        target: str = "pixels",
        layer: Layer | None = None,
    ) -> GradientSession:
        """Bắt đầu kéo gradient trên layer hoặc layer mask của layer đang chọn."""
        if not isinstance(settings, GradientSettings):
            raise TypeError("Thông số gradient phải là GradientSettings.")
        if target not in PAINT_TARGETS:
            raise ValueError(f"Đích tô không hợp lệ: {target}")
        if len(tuple(start)) != 2 or not all(
            math.isfinite(float(value)) for value in start
        ):
            raise ValueError("Điểm bắt đầu gradient không hợp lệ.")
        target_layer = layer or self.active_layer
        if target_layer is None:
            raise ValueError("Chưa chọn layer nào để tô gradient.")
        if target_layer.uses_canvas_mask and target == "pixels":
            raise ValueError(
                "Layer điều chỉnh/nhóm không có pixel để tô. "
                "Hãy chọn layer ảnh khác."
            )
        if target_layer.locked:
            raise ValueError(f"Layer '{target_layer.name}' đang bị khoá.")
        if target == "mask" and target_layer.mask is None:
            raise ValueError(
                f"Layer '{target_layer.name}' chưa có mask. "
                "Hãy thêm Layer Mask trước khi tô lên mask."
            )
        return GradientSession(
            self, target_layer, settings, (float(start[0]), float(start[1])), target=target
        )

    def apply_layer_filter(
        self,
        pixels: np.ndarray,
        label: str,
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Áp kết quả bộ lọc vào một layer, giới hạn theo vùng chọn nếu có."""
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Chưa có layer nào để áp dụng bộ lọc.")
        if target.uses_canvas_mask:
            raise ValueError(
                "Không thể áp bộ lọc lên layer điều chỉnh/nhóm.\n"
                "Hãy chọn layer ảnh hoặc sửa tham số điều chỉnh."
            )
        if target.locked:
            raise ValueError(f"Layer '{target.name}' đang bị khoá.")
        new_pixels = np.asarray(pixels)
        if new_pixels.shape != target.pixels.shape or new_pixels.dtype != np.uint8:
            raise ValueError("Kết quả bộ lọc không khớp kích thước layer.")

        if self.has_selection():
            selection = self._mask_from_selection(target)
            if not np.all(selection == 255):
                strength = selection.astype(np.uint16)[..., None]
                original = target.pixels.astype(np.uint16)
                filtered = new_pixels.astype(np.uint16)
                new_pixels = (
                    (filtered * strength + original * (255 - strength) + 127) // 255
                ).astype(np.uint8)
        new_pixels = np.ascontiguousarray(new_pixels)
        if np.array_equal(new_pixels, target.pixels):
            return False

        old_state = LayerSnapshot.capture(target)
        new_state = LayerSnapshot(
            layer=target,
            pixels=new_pixels,
            width=target.width,
            height=target.height,
            offset_x=target.offset_x,
            offset_y=target.offset_y,
            mask=target.mask,
            mask_enabled=target.mask_enabled,
            kind=LayerKind.PIXEL,
            text=None,
            shape=None,
            adjustment=None,
            fill=None,
            smart=None,
            smart_source=None,
        )
        command = LayerTransformCommand(old_state, new_state, label)
        self._apply_command(command, record=record)
        return True

    def _pixel_edit_target(self, layer: Layer | None) -> Layer:
        target = layer or self.active_layer
        if target is None:
            raise ValueError("Chưa chọn layer nào.")
        if target.kind != LayerKind.PIXEL:
            raise ValueError(
                f"Layer '{target.name}' không phải layer ảnh.\n"
                "Hãy rasterize layer trước khi xoá hoặc tô trực tiếp."
            )
        if target.locked:
            raise ValueError(f"Layer '{target.name}' đang bị khoá.")
        return target

    def clear_selection_pixels(
        self, layer: Layer | None = None, *, record: bool = True
    ) -> bool:
        """Xoá (làm trong suốt) pixel trong vùng chọn; không có vùng chọn thì xoá cả layer."""
        target = self._pixel_edit_target(layer)
        cleared = target.pixels.copy()
        cleared[..., 3] = 0
        return self.apply_layer_filter(cleared, "Xoá vùng chọn", target, record=record)

    def fill_selection(
        self,
        color: tuple[int, int, int, int],
        layer: Layer | None = None,
        *,
        record: bool = True,
    ) -> bool:
        """Tô màu (phủ lên trên) vào vùng chọn của layer ảnh; không có vùng chọn thì tô cả layer."""
        target = self._pixel_edit_target(layer)
        if len(tuple(color)) != 4:
            raise ValueError("Màu tô phải gồm 4 kênh RGBA.")
        red, green, blue, alpha = (int(max(0, min(255, c))) for c in color)
        src_alpha = alpha / 255.0
        pixels = target.pixels.astype(np.float32)
        dst_alpha = pixels[..., 3:4] / 255.0
        out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
        src_rgb = np.array([red, green, blue], dtype=np.float32)
        weighted = src_rgb * src_alpha + pixels[..., :3] * dst_alpha * (1.0 - src_alpha)
        safe_alpha = np.where(out_alpha > 0, out_alpha, 1.0)
        result = np.empty_like(target.pixels)
        result[..., :3] = np.clip(np.rint(weighted / safe_alpha), 0, 255).astype(np.uint8)
        result[..., 3] = np.clip(np.rint(out_alpha[..., 0] * 255.0), 0, 255).astype(np.uint8)
        return self.apply_layer_filter(result, "Tô vùng chọn", target, record=record)

    def copy_pixels(
        self, layer: Layer | None = None, *, merged: bool = False
    ) -> tuple[np.ndarray, tuple[int, int]] | None:
        """Trích pixel RGBA trong vùng chọn (hoặc toàn bộ) kèm toạ độ góc trái trên.

        merged=True lấy từ ảnh ghép của toàn tài liệu; ngược lại lấy từ layer.
        Trả về None khi không có gì để sao chép.
        """
        if merged:
            source = self.get_composite().array
            source_x, source_y = 0, 0
        else:
            target = layer or self.active_layer
            if target is None:
                return None
            if target.uses_canvas_mask:
                raise ValueError(
                    f"Layer '{target.name}' không có pixel riêng.\n"
                    "Hãy dùng Copy Merged để sao chép ảnh ghép."
                )
            source = target.pixels
            source_x, source_y = target.offset_x, target.offset_y
        source_h, source_w = source.shape[:2]

        if self.has_selection():
            bounds = self._selection.bounds()
            if bounds.isEmpty():
                return None
            x0 = max(bounds.left(), source_x)
            y0 = max(bounds.top(), source_y)
            x1 = min(bounds.left() + bounds.width(), source_x + source_w)
            y1 = min(bounds.top() + bounds.height(), source_y + source_h)
            if x1 <= x0 or y1 <= y0:
                return None
            crop = source[y0 - source_y : y1 - source_y, x0 - source_x : x1 - source_x].copy()
            mask = self._selection.mask()[y0:y1, x0:x1]
            crop[..., 3] = ((crop[..., 3].astype(np.uint16) * mask + 127) // 255).astype(np.uint8)
            if not np.any(crop[..., 3]):
                return None
            return np.ascontiguousarray(crop), (x0, y0)
        return np.ascontiguousarray(source.copy()), (source_x, source_y)

    def paste_pixels(
        self,
        rgba: np.ndarray,
        offset: tuple[int, int] | None = None,
        *,
        name: str | None = None,
        record: bool = True,
    ) -> Layer:
        """Dán mảng RGBA thành layer mới; không có offset thì đặt giữa canvas."""
        array = np.asarray(rgba)
        if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
            raise ValueError("Dữ liệu dán phải là mảng RGBA uint8.")
        height, width = array.shape[:2]
        if width < 1 or height < 1:
            raise ValueError("Dữ liệu dán rỗng.")
        if width > self.MAX_DIMENSION or height > self.MAX_DIMENSION:
            raise ValueError("Ảnh dán vượt quá kích thước cho phép.")
        if offset is None:
            offset = ((self.width - width) // 2, (self.height - height) // 2)
        layer = Layer(width, height, name or self._next_layer_name())
        layer.set_pixels(np.ascontiguousarray(array))
        layer.offset_x = int(offset[0])
        layer.offset_y = int(offset[1])
        return self.add_layer(layer=layer, record=record)

    # -------------------------------------------------------------- undo / redo
    def undo(self) -> bool:
        command = self.history.undo(self)
        if command is None:
            return False
        self._after_history_jump()
        return True

    def redo(self) -> bool:
        command = self.history.redo(self)
        if command is None:
            return False
        self._after_history_jump()
        return True

    def _after_history_jump(self) -> None:
        self._ensure_active_valid()
        self.invalidate()
        self.structure_changed.emit()
        self.active_layer_changed.emit()
        self.selection_changed.emit()
        self.history_changed.emit()
        self.mark_modified()

    # ------------------------------------------------------------ trạng thái file
    def mark_modified(self) -> None:
        self._set_modified(True)

    def mark_clean(self) -> None:
        self.history.clear()
        self._set_modified(False)
        self.history_changed.emit()

    def mark_saved(self, path: str | None) -> None:
        """Đánh dấu đã lưu. Giữ nguyên history để người dùng vẫn Undo được sau khi lưu."""
        self.file_path = str(path) if path else None
        self._set_modified(False)
        self.history_changed.emit()
        self.title_changed.emit()

    def _set_modified(self, value: bool) -> None:
        if self._modified != value:
            self._modified = value
            self.modified_changed.emit(value)
            self.title_changed.emit()

    # ------------------------------------------------------------------ composite
    @property
    def revision(self) -> int:
        """Số phiên bản nội dung; tăng mỗi lần ``invalidate``."""
        return self._revision

    def invalidate(self, rect: tuple[int, int, int, int] | None = None) -> None:
        """Báo nội dung đã đổi.

        ``rect`` là vùng chữ nhật (x0, y0, x1, y1) theo pixel tài liệu bị thay
        đổi. Tile cache chỉ bỏ các tile giao với vùng này; truyền ``None`` khi
        thay đổi ảnh hưởng toàn tài liệu (thêm/xoá layer, đổi blend, ...).
        """
        self._revision += 1
        self._composite = None
        self._composite_rev = -1
        self._preview_key = None
        self._preview_array = None
        self._preview_image = None
        clipped: tuple[int, int, int, int] | None = None
        if rect is not None:
            x0, y0, x1, y1 = (int(value) for value in rect)
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(self.width, x1)
            y1 = min(self.height, y1)
            if x1 > x0 and y1 > y0:
                clipped = (x0, y0, x1, y1)
            else:
                clipped = (0, 0, 0, 0)
        self._dirty_log.append((self._revision, clipped))
        if len(self._dirty_log) > 64:
            del self._dirty_log[:-64]
        self.content_changed.emit()

    def changes_since(
        self, revision: int
    ) -> list[tuple[int, int, int, int] | None] | None:
        """Danh sách vùng bẩn sau ``revision``.

        Trả về ``None`` khi cache đã quá cũ hoặc có thay đổi toàn tài liệu —
        bên gọi phải xoá toàn bộ cache. Danh sách rỗng nghĩa là không đổi.
        """
        revision = int(revision)
        if revision < 0:
            return None
        if revision == self._revision:
            return []
        if not self._dirty_log:
            return None
        earliest = self._dirty_log[0][0]
        if revision < earliest - 1:
            return None
        entries = [rect for rev, rect in self._dirty_log if rev > revision]
        if len(entries) != self._revision - revision:
            return None
        if any(rect is None for rect in entries):
            return None
        return entries

    def get_composite(self) -> CompositeImage:
        if self._composite is not None and self._composite_rev == self._revision:
            return self._composite
        array = composite_layers(self.layers.layers, self.width, self.height)
        image = numpy_rgba_to_qimage(array)
        self._composite = CompositeImage(array=array, image=image)
        self._composite_rev = self._revision
        return self._composite

    def preview_image(self, max_side: int) -> QImage:
        """Ảnh xem trước nhẹ, cạnh lớn nhất ``max_side``, cache theo revision.

        Layer được lấy mẫu thưa trước khi hợp nhất nên chi phí và bộ nhớ giảm
        theo bình phương tỉ lệ thu nhỏ — dùng cho chế độ xem toàn ảnh.
        """
        max_side = int(max_side)
        if max_side < 1:
            raise ValueError("max_side phải >= 1.")
        key = (self._revision, max_side)
        if (
            self._preview_key == key
            and self._preview_image is not None
            and not self._preview_image.isNull()
        ):
            return self._preview_image
        scaled, preview_w, preview_h = scale_layers_for_preview(
            self.layers.layers, self.width, self.height, max_side
        )
        array = composite_layers(scaled, preview_w, preview_h)
        image = numpy_rgba_to_qimage(array)
        self._preview_key = key
        self._preview_array = array
        self._preview_image = image
        return image

    # ------------------------------------------- thao tác raw (chỉ command gọi)
    def _insert_layer_raw(self, layer: Layer, index: int) -> None:
        self.layers.insert(layer, index)
        if self._active_layer_id is None:
            self._active_layer_id = layer.id

    def _remove_layer_raw(self, layer: Layer) -> None:
        index = self.layers.index_of(layer)
        was_active = layer.id == self._active_layer_id
        self.layers.remove(layer)
        if was_active:
            if len(self.layers) == 0:
                self._active_layer_id = None
            else:
                self._active_layer_id = self.layers[min(index, len(self.layers) - 1)].id

    def _apply_layer_property_raw(self, layer: Layer, attribute: str, value: object) -> None:
        if attribute == "opacity":
            layer.opacity = float(max(0.0, min(1.0, float(value))))  # type: ignore[arg-type]
        elif attribute == "blend_mode":
            if value not in BLEND_MODE_IDS:
                raise ValueError(f"Blend mode không hợp lệ: {value}")
            layer.blend_mode = str(value)
        elif attribute == "visible":
            layer.visible = bool(value)
        elif attribute == "name":
            layer.name = str(value)
        elif attribute == "locked":
            layer.locked = bool(value)
        elif attribute == "group_id":
            layer.group_id = str(value) if value else None
        else:
            raise ValueError(f"Thuộc tính layer không hỗ trợ: {attribute}")

    def _apply_layer_group_raw(self, layer: Layer, group_id: str | None) -> None:
        layer.group_id = group_id

    def _apply_layer_offset_raw(self, layer: Layer, x: int, y: int) -> None:
        layer.offset_x = int(x)
        layer.offset_y = int(y)

    def _apply_layer_mask_raw(
        self, layer: Layer, mask: np.ndarray | None, enabled: bool
    ) -> None:
        layer.mask = mask
        layer.mask_enabled = bool(enabled)
        layer.touch()

    def _restore_layer_content_raw(
        self,
        layer: Layer,
        pixels: np.ndarray,
        mask: np.ndarray | None,
        mask_enabled: bool,
        kind: str = LayerKind.PIXEL,
        text: TextProperties | None = None,
        shape: ShapeProperties | None = None,
        adjustment: AdjustmentProperties | None = None,
        fill: FillProperties | None = None,
        smart: SmartObjectProperties | None = None,
        smart_source: np.ndarray | None = None,
    ) -> None:
        layer.pixels = np.ascontiguousarray(pixels)
        layer.mask = mask
        layer.mask_enabled = bool(mask_enabled)
        layer.kind = kind
        layer.text = text
        layer.shape = shape
        layer.adjustment = adjustment
        layer.fill_props = fill
        layer.smart_props = smart
        layer.smart_source = (
            np.ascontiguousarray(smart_source) if smart_source is not None else None
        )
        layer.touch()

    def _restore_selection_raw(self, selection: Selection | None) -> None:
        self._selection = selection

    def _apply_geometry_raw(
        self,
        width: int,
        height: int,
        offsets: list[tuple[Layer, int, int]],
        selection: Selection | None,
        masks: list[tuple[Layer, np.ndarray | None]] | None = None,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        for layer, offset_x, offset_y in offsets:
            layer.offset_x = int(offset_x)
            layer.offset_y = int(offset_y)
        for layer, mask in masks or []:
            layer.mask = mask
            layer.touch()
        self._selection = selection

    def _apply_document_states_raw(
        self,
        width: int,
        height: int,
        states: list[LayerSnapshot],
        selection: Selection | None,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        for state in states:
            self._apply_layer_snapshot_raw(state)
        self._selection = selection

    def _apply_layer_snapshot_raw(self, state: LayerSnapshot) -> None:
        layer = state.layer
        layer.width = int(state.width)
        layer.height = int(state.height)
        layer.pixels = np.ascontiguousarray(state.pixels)
        layer.offset_x = int(state.offset_x)
        layer.offset_y = int(state.offset_y)
        layer.mask = (
            np.ascontiguousarray(state.mask) if state.mask is not None else None
        )
        layer.mask_enabled = bool(state.mask_enabled)
        layer.kind = state.kind
        layer.text = state.text
        layer.shape = state.shape
        layer.adjustment = state.adjustment
        layer.fill_props = state.fill
        layer.smart_props = state.smart
        layer.smart_source = (
            np.ascontiguousarray(state.smart_source)
            if state.smart_source is not None
            else None
        )
        layer.touch()

    def _apply_layer_order_raw(self, order: list[Layer]) -> None:
        self.layers.set_order(list(order))

    # ------------------------------------------------------------------ helpers
    def _ensure_active_valid(self) -> None:
        if self._active_layer_id is not None and self.layers.get(self._active_layer_id) is None:
            if len(self.layers):
                self._active_layer_id = self.layers[len(self.layers) - 1].id
            else:
                self._active_layer_id = None

    def _apply_command(self, command, record: bool = True) -> None:
        old_selection = self._selection
        command.redo(self)
        if record:
            self.history.push(command)
        self._ensure_active_valid()
        self.invalidate()
        self.structure_changed.emit()
        self.active_layer_changed.emit()
        if not _same_selection(old_selection, self._selection):
            self.selection_changed.emit()
        if record:
            self.history_changed.emit()
            self.mark_modified()
