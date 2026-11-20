"""Lớp dữ liệu Layer và danh sách blend mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator
from uuid import uuid4

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from core.adjustment_layer import AdjustmentProperties
    from core.fill_layer import FillProperties
    from core.layer_style import LayerStyle
    from core.shape_layer import ShapeProperties
    from core.smart_object import SmartObjectProperties
    from core.text_layer import TextProperties

# (id, nhãn hiển thị) — thứ tự giống nhóm blend mode quen thuộc của Photoshop.
BLEND_MODES: list[tuple[str, str]] = [
    ("normal", "Normal"),
    ("multiply", "Multiply"),
    ("screen", "Screen"),
    ("overlay", "Overlay"),
    ("soft_light", "Soft Light"),
    ("hard_light", "Hard Light"),
    ("darken", "Darken"),
    ("lighten", "Lighten"),
    ("color_dodge", "Color Dodge"),
    ("color_burn", "Color Burn"),
    ("difference", "Difference"),
    ("hue", "Hue"),
    ("saturation", "Saturation"),
    ("color", "Color"),
    ("luminosity", "Luminosity"),
]

BLEND_MODE_IDS: list[str] = [mode for mode, _ in BLEND_MODES]
BLEND_MODE_LABELS: dict[str, str] = dict(BLEND_MODES)

# Nhãn màu layer giống Photoshop; chỉ là metadata, không ảnh hưởng pixel.
LAYER_COLOR_LABELS: list[tuple[str, str]] = [
    ("none", "No Color"),
    ("red", "Red"),
    ("orange", "Orange"),
    ("yellow", "Yellow"),
    ("green", "Green"),
    ("blue", "Blue"),
    ("violet", "Violet"),
    ("gray", "Gray"),
]
LAYER_COLOR_IDS: list[str] = [label for label, _ in LAYER_COLOR_LABELS]


class LayerKind:
    PIXEL = "pixel"
    TEXT = "text"
    SHAPE = "shape"
    ADJUSTMENT = "adjustment"
    GROUP = "group"
    FILL = "fill"
    SMART = "smart"

    # Layer không có pixel riêng và dùng mask phủ toàn tài liệu.
    CANVAS_MASK_KINDS = (ADJUSTMENT, GROUP, FILL)


class Layer:
    """Một layer pixel: mảng RGBA uint8 có kích thước riêng và offset trên canvas."""

    def __init__(
        self,
        width: int,
        height: int,
        name: str = "Layer",
        layer_id: str | None = None,
    ) -> None:
        if width < 1 or height < 1:
            raise ValueError("Kích thước layer phải >= 1 px.")
        self.id: str = layer_id or uuid4().hex
        self.name: str = name
        self.kind: str = LayerKind.PIXEL
        self.text: TextProperties | None = None
        self.shape: ShapeProperties | None = None
        self.adjustment: AdjustmentProperties | None = None
        self.fill_props: FillProperties | None = None
        self.smart_props: SmartObjectProperties | None = None
        self.smart_source: np.ndarray | None = None
        self.style: LayerStyle | None = None
        self.group_id: str | None = None
        self.width: int = int(width)
        self.height: int = int(height)
        self.pixels: np.ndarray = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        self.offset_x: int = 0
        self.offset_y: int = 0
        self.visible: bool = True
        self.opacity: float = 1.0
        self.blend_mode: str = "normal"
        self.locked: bool = False
        self.clipping: bool = False
        self.color_label: str = "none"
        self.mask: np.ndarray | None = None
        self.mask_enabled: bool = True
        self.pixel_revision: int = 0

    # ------------------------------------------------------------------ dữ liệu
    def fill(self, rgba: tuple[int, int, int, int]) -> None:
        self.pixels[...] = rgba
        self.touch()

    @property
    def has_mask(self) -> bool:
        return self.mask is not None

    @property
    def uses_canvas_mask(self) -> bool:
        return self.kind in LayerKind.CANVAS_MASK_KINDS

    def set_mask(self, mask: np.ndarray | None) -> None:
        if mask is None:
            self.mask = None
            self.touch()
            return
        arr = np.asarray(mask)
        if arr.dtype != np.uint8:
            raise ValueError("Dữ liệu layer mask phải có dtype uint8.")
        if arr.ndim != 2:
            raise ValueError("Dữ liệu layer mask phải là mảng 2 chiều.")
        # Mask của layer điều chỉnh/nhóm là mask cấp tài liệu (canvas-size),
        # không theo kích thước 1 × 1 của layer.
        if not self.uses_canvas_mask and arr.shape != (self.height, self.width):
            raise ValueError("Kích thước layer mask không khớp layer.")
        self.mask = np.ascontiguousarray(arr).copy()
        self.touch()

    def set_pixels(self, array: np.ndarray) -> None:
        arr = np.asarray(array)
        if arr.dtype != np.uint8:
            raise ValueError("Dữ liệu pixel phải có dtype uint8.")
        if arr.ndim != 3 or arr.shape[2] != 4:
            raise ValueError("Dữ liệu pixel phải có dạng (cao, rộng, 4).")
        if arr.shape[0] != self.height or arr.shape[1] != self.width:
            raise ValueError("Kích thước dữ liệu pixel không khớp layer.")
        self.pixels = np.ascontiguousarray(arr)
        self.touch()

    def touch(self) -> None:
        """Đánh dấu nội dung pixel đã đổi (dùng để làm mới thumbnail/cache)."""
        self.pixel_revision += 1

    def copy(self, name: str | None = None) -> "Layer":
        clone = Layer(self.width, self.height, name or f"{self.name} copy")
        clone.kind = self.kind
        clone.text = self.text
        clone.shape = self.shape
        clone.adjustment = self.adjustment
        clone.fill_props = self.fill_props
        clone.smart_props = self.smart_props
        clone.smart_source = (
            self.smart_source.copy() if self.smart_source is not None else None
        )
        clone.style = self.style
        clone.group_id = self.group_id
        clone.pixels = self.pixels.copy()
        clone.offset_x = self.offset_x
        clone.offset_y = self.offset_y
        clone.visible = self.visible
        clone.opacity = self.opacity
        clone.blend_mode = self.blend_mode
        clone.locked = self.locked
        clone.clipping = self.clipping
        clone.color_label = self.color_label
        clone.mask = self.mask.copy() if self.mask is not None else None
        clone.mask_enabled = self.mask_enabled
        return clone

    def bounds(self) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) theo toạ độ canvas, không cắt theo biên tài liệu."""
        return (self.offset_x, self.offset_y, self.offset_x + self.width, self.offset_y + self.height)

    def has_pixels(self) -> bool:
        return bool(self.pixels.size) and bool(np.any(self.pixels[..., 3]))

    def __repr__(self) -> str:  # pragma: no cover - chẩn đoán
        return f"<Layer {self.name!r} {self.width}x{self.height} opacity={self.opacity:.2f}>"


class LayerManager:
    """Bộ sưu tập layer, thứ tự từ dưới (index 0) lên trên (index cuối)."""

    def __init__(self) -> None:
        self._layers: list[Layer] = []

    def __len__(self) -> int:
        return len(self._layers)

    def __iter__(self) -> Iterator[Layer]:
        return iter(self._layers)

    def __getitem__(self, index: int) -> Layer:
        return self._layers[index]

    @property
    def layers(self) -> tuple[Layer, ...]:
        return tuple(self._layers)

    def index_of(self, layer: Layer) -> int:
        try:
            return self._layers.index(layer)
        except ValueError as exc:
            raise ValueError("Layer không thuộc tài liệu này.") from exc

    def get(self, layer_id: str | None) -> Layer | None:
        if layer_id is None:
            return None
        for layer in self._layers:
            if layer.id == layer_id:
                return layer
        return None

    def children_of(self, group_id: str | None) -> list[Layer]:
        """Các layer có cha trực tiếp là ``group_id`` (None = cấp gốc)."""
        return [layer for layer in self._layers if layer.group_id == group_id]

    def insert(self, layer: Layer, index: int | None = None) -> int:
        if index is None:
            index = len(self._layers)
        index = max(0, min(int(index), len(self._layers)))
        if any(existing.id == layer.id for existing in self._layers):
            raise ValueError("Layer id đã tồn tại trong tài liệu.")
        self._layers.insert(index, layer)
        return index

    def remove(self, layer: Layer) -> Layer:
        self._layers.remove(layer)
        return layer

    def move_to(self, layer: Layer, index: int) -> int:
        old = self.index_of(layer)
        index = max(0, min(int(index), len(self._layers) - 1))
        if index == old:
            return old
        self._layers.pop(old)
        self._layers.insert(index, layer)
        return index

    def set_order(self, layers: list[Layer]) -> None:
        if len(layers) != len(self._layers) or {id(layer) for layer in layers} != {
            id(layer) for layer in self._layers
        }:
            raise ValueError("Danh sách layer mới không khớp với tài liệu.")
        self._layers = list(layers)

    def clear(self) -> None:
        self._layers.clear()
