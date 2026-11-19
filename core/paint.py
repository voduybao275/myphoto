"""Cọ vẽ và tẩy: tính toán điểm ảnh/mask trên mảng NumPy.

Mỗi nét cọ được gom thành một "phiên" (session): trong lúc kéo chuột, kết quả
được vẽ trực tiếp vào layer để xem trước; khi thả chuột mới ghi đúng một bước
Undo/Redo. Vùng chọn (nếu có) giới hạn phạm vi vẽ theo đúng biên của nó.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from core.command_manager import LayerSnapshot, LayerTransformCommand, SetLayerMaskCommand
from core.layer import LayerKind

if TYPE_CHECKING:  # pragma: no cover
    from core.document import Document
    from core.layer import Layer

MIN_BRUSH_SIZE = 1
MAX_BRUSH_SIZE = 2000
PAINT_TARGETS = ("pixels", "mask")


@dataclass(frozen=True)
class BrushSettings:
    """Thông số nét cọ: đường kính (px), độ cứng 0..1, độ đục 0..1, màu RGBA."""

    size: int = 40
    hardness: float = 0.8
    opacity: float = 1.0
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    erase: bool = False

    def __post_init__(self) -> None:
        size = int(round(float(self.size)))
        object.__setattr__(self, "size", max(MIN_BRUSH_SIZE, min(MAX_BRUSH_SIZE, size)))
        object.__setattr__(
            self, "hardness", max(0.0, min(1.0, float(self.hardness)))
        )
        object.__setattr__(self, "opacity", max(0.0, min(1.0, float(self.opacity))))
        color = tuple(int(channel) for channel in self.color)
        if len(color) != 4:
            raise ValueError("Màu cọ phải có 4 thành phần RGBA.")
        object.__setattr__(
            self, "color", tuple(max(0, min(255, channel)) for channel in color)
        )

    @property
    def radius(self) -> float:
        return self.size / 2.0

    @property
    def spacing(self) -> float:
        """Khoảng cách giữa hai lần đóng dấu, đủ dày để nét liền mạch."""
        return max(1.0, self.size * 0.1)


def color_luminance(color: tuple[int, int, int, int]) -> int:
    """Giá trị xám 0..255 của màu (dùng khi vẽ lên layer mask)."""
    red, green, blue = color[:3]
    return int(round(0.299 * red + 0.587 * green + 0.114 * blue))


def stamp_coverage(
    coverage: np.ndarray,
    x: float,
    y: float,
    radius: float,
    hardness: float,
    *,
    strength: np.ndarray | None = None,
    opacity: float = 1.0,
) -> tuple[int, int, int, int] | None:
    """Đóng dấu một đầu cọ vào bản đồ độ phủ (uint8) và trả về hình chữ nhật đã đổi."""
    height, width = coverage.shape
    if radius <= 0.0:
        return None
    x0 = max(0, int(math.floor(x - radius)))
    x1 = min(width, int(math.ceil(x + radius)) + 1)
    y0 = max(0, int(math.floor(y - radius)))
    y1 = min(height, int(math.ceil(y + radius)) + 1)
    if x1 <= x0 or y1 <= y0:
        return None

    x_axis = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
    y_axis = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
    distance = np.sqrt((x_axis - x) ** 2 + (y_axis - y) ** 2) / radius
    inner = max(0.0, min(float(hardness), max(0.0, 1.0 - 1.0 / radius)))
    if inner <= 0.0:
        ramp = np.clip(1.0 - distance, 0.0, 1.0)
    else:
        ramp = np.clip((1.0 - distance) / (1.0 - inner), 0.0, 1.0)
    alpha = ramp * ramp * (3.0 - 2.0 * ramp)
    if strength is not None:
        alpha = alpha * (strength[y0:y1, x0:x1].astype(np.float32) / 255.0)
    alpha = alpha * max(0.0, min(1.0, float(opacity)))
    values = (alpha * 255.0 + 0.5).astype(np.uint8)
    region = coverage[y0:y1, x0:x1]
    np.maximum(region, values, out=region)
    return (x0, y0, x1, y1)


def dot_points(
    start: tuple[float, float], end: tuple[float, float], spacing: float
) -> list[tuple[float, float]]:
    """Các điểm đóng dấu dọc đoạn thẳng, không bao gồm điểm bắt đầu."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance <= 0.0:
        return []
    spacing = max(0.25, float(spacing))
    steps = max(1, int(math.ceil(distance / spacing)))
    return [
        (start[0] + dx * index / steps, start[1] + dy * index / steps)
        for index in range(1, steps + 1)
    ]


def paint_pixels(
    pixels: np.ndarray,
    coverage: np.ndarray,
    color: tuple[int, int, int, int],
) -> None:
    """Trộn màu cọ (straight alpha) vào mảng RGBA theo độ phủ 0..255."""
    amount = coverage.astype(np.float32) * (1.0 / 255.0)
    src_alpha = amount * (color[3] / 255.0)
    dst_alpha = pixels[..., 3].astype(np.float32) * (1.0 / 255.0)
    out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
    src_rgb = np.asarray(color[:3], dtype=np.float32)
    dst_rgb = pixels[..., :3].astype(np.float32)
    safe = np.maximum(out_alpha, 1e-8)[..., None]
    out_rgb = (
        src_rgb[None, None, :] * src_alpha[..., None]
        + dst_rgb * (dst_alpha * (1.0 - src_alpha))[..., None]
    ) / safe
    out_rgb = np.where(out_alpha[..., None] > 0.0, out_rgb, 0.0)
    pixels[..., :3] = np.clip(out_rgb + 0.5, 0.0, 255.0).astype(np.uint8)
    pixels[..., 3] = np.clip(out_alpha * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)


def erase_pixels(pixels: np.ndarray, coverage: np.ndarray) -> None:
    """Giảm alpha theo độ phủ, giữ nguyên màu RGB (tẩy về trong suốt)."""
    factor = 1.0 - coverage.astype(np.float32) * (1.0 / 255.0)
    pixels[..., 3] = np.clip(
        pixels[..., 3].astype(np.float32) * factor + 0.5, 0.0, 255.0
    ).astype(np.uint8)


def paint_mask_values(mask: np.ndarray, coverage: np.ndarray, value: int) -> None:
    """Kéo giá trị mask về ``value`` theo độ phủ (0 = đen ẩn, 255 = trắng hiện)."""
    target = max(0, min(255, int(value)))
    amount = coverage.astype(np.float32) * (1.0 / 255.0)
    current = mask.astype(np.float32)
    blended = current + (target - current) * amount
    mask[...] = np.clip(blended + 0.5, 0.0, 255.0).astype(np.uint8)


def _layer_selection_strength(document: "Document", layer: "Layer") -> np.ndarray | None:
    """Cắt vùng chọn theo toạ độ layer; None nghĩa là không giới hạn."""
    if not document.has_selection():
        return None
    document_mask = document.selection_mask()
    if document_mask is None:
        return None
    strength = np.zeros((layer.height, layer.width), dtype=np.uint8)
    x0 = max(0, layer.offset_x)
    x1 = min(document.width, layer.offset_x + layer.width)
    y0 = max(0, layer.offset_y)
    y1 = min(document.height, layer.offset_y + layer.height)
    if x1 > x0 and y1 > y0:
        strength[
            y0 - layer.offset_y : y1 - layer.offset_y,
            x0 - layer.offset_x : x1 - layer.offset_x,
        ] = document_mask[y0:y1, x0:x1]
    return strength


class BrushStrokeSession:
    """Một nét cọ từ lúc nhấn chuột tới lúc thả; chỉ ghi history khi kết thúc."""

    def __init__(
        self,
        document: "Document",
        layer: "Layer",
        settings: BrushSettings,
        *,
        target: str = "pixels",
    ) -> None:
        if target not in PAINT_TARGETS:
            raise ValueError(f"Đích vẽ không hợp lệ: {target}")
        if target == "mask" and layer.mask is None:
            raise ValueError("Layer này chưa có layer mask để vẽ lên.")
        if target == "mask" and settings.erase:
            raise ValueError("Công cụ tẩy không vẽ lên layer mask.")
        self.document = document
        self.layer = layer
        self.settings = settings
        self.target = target
        self.pixels_before = layer.pixels.copy()
        self.mask_before = layer.mask.copy() if layer.mask is not None else None
        self.mask_enabled_before = bool(layer.mask_enabled)
        self.kind_before = layer.kind
        self.text_before = layer.text
        self.shape_before = layer.shape
        self.adjustment_before = layer.adjustment
        self.fill_before = layer.fill_props
        self.smart_before = layer.smart_props
        self.smart_source_before = layer.smart_source
        if target == "mask" and layer.mask is not None:
            self.target_height, self.target_width = layer.mask.shape[:2]
        else:
            self.target_height, self.target_width = layer.height, layer.width
        self.coverage = np.zeros(
            (self.target_height, self.target_width), dtype=np.uint8
        )
        if target == "mask" and layer.uses_canvas_mask:
            self.selection_strength = document.selection_mask()
        else:
            self.selection_strength = _layer_selection_strength(document, layer)
        self.mask_value = color_luminance(settings.color)
        self.changed = False
        self._last: tuple[float, float] | None = None
        self._pending: tuple[int, int, int, int] | None = None
        self._finished = False

    # ------------------------------------------------------------------ vẽ
    def stroke_to(self, x: float, y: float) -> bool:
        """Nối từ điểm trước tới (x, y) theo toạ độ tài liệu."""
        if self._finished:
            return False
        if self.target == "mask" and self.layer.uses_canvas_mask:
            local_x = float(x)
            local_y = float(y)
        else:
            local_x = float(x) - self.layer.offset_x
            local_y = float(y) - self.layer.offset_y
        if self._last is None:
            points = [(local_x, local_y)]
        else:
            points = dot_points(
                self._last, (local_x, local_y), self.settings.spacing
            )
        self._last = (local_x, local_y)
        for point_x, point_y in points:
            self._stamp(point_x, point_y)
        if self._pending is not None:
            self._refresh()
        return self.changed

    def _stamp(self, x: float, y: float) -> None:
        rect = stamp_coverage(
            self.coverage,
            x,
            y,
            self.settings.radius,
            self.settings.hardness,
            strength=self.selection_strength,
            opacity=self.settings.opacity,
        )
        if rect is None:
            return
        self.changed = True
        self._pending = _union_rect(self._pending, rect)

    def _refresh(self) -> None:
        if self._pending is None:
            return
        x0, y0, x1, y1 = self._pending
        self._pending = None
        coverage = self.coverage[y0:y1, x0:x1]
        if self.target == "pixels":
            dst = self.pixels_before[y0:y1, x0:x1].copy()
            if self.settings.erase:
                erase_pixels(dst, coverage)
            else:
                paint_pixels(dst, coverage, self.settings.color)
            self.layer.pixels[y0:y1, x0:x1] = dst
        else:
            dst = self.mask_before[y0:y1, x0:x1].copy()
            paint_mask_values(dst, coverage, self.mask_value)
            self.layer.mask[y0:y1, x0:x1] = dst
        self.layer.touch()
        self.document.invalidate(
            (
                self.layer.offset_x + x0,
                self.layer.offset_y + y0,
                self.layer.offset_x + x1,
                self.layer.offset_y + y1,
            )
        )

    # --------------------------------------------------------------- kết thúc
    def finish(self) -> bool:
        """Ghi một bước Undo; trả về False nếu nét không đổi điểm ảnh nào."""
        if self._finished:
            return False
        self._finished = True
        if not self.changed:
            self.cancel()
            return False
        if self.target == "mask":
            command = SetLayerMaskCommand(
                self.layer,
                self.mask_before,
                self.mask_enabled_before,
                self.layer.mask.copy(),
                self.mask_enabled_before,
                "Vẽ lên layer mask",
            )
        else:
            label = "Tẩy" if self.settings.erase else "Vẽ cọ"
            old_state = LayerSnapshot(
                layer=self.layer,
                pixels=self.pixels_before,
                width=self.layer.width,
                height=self.layer.height,
                offset_x=self.layer.offset_x,
                offset_y=self.layer.offset_y,
                mask=self.mask_before,
                mask_enabled=self.mask_enabled_before,
                kind=self.kind_before,
                text=self.text_before,
                shape=self.shape_before,
                adjustment=self.adjustment_before,
                fill=self.fill_before,
                smart=self.smart_before,
                smart_source=self.smart_source_before,
            )
            new_state = LayerSnapshot(
                layer=self.layer,
                pixels=self.layer.pixels.copy(),
                width=self.layer.width,
                height=self.layer.height,
                offset_x=self.layer.offset_x,
                offset_y=self.layer.offset_y,
                mask=(
                    self.layer.mask.copy()
                    if self.layer.mask is not None
                    else None
                ),
                mask_enabled=self.layer.mask_enabled,
                kind=LayerKind.PIXEL,
                text=None,
                shape=None,
            )
            command = LayerTransformCommand(old_state, new_state, label)
        self.document._apply_command(command, record=True)
        return True

    def cancel(self) -> None:
        """Khôi phục trạng thái trước khi bắt đầu nét (dùng khi nhấn Esc)."""
        if self._finished:
            return
        self._finished = True
        self.layer.pixels[...] = self.pixels_before
        if self.mask_before is not None and self.layer.mask is not None:
            self.layer.mask[...] = self.mask_before
        self.layer.touch()
        self.document.invalidate()


def _union_rect(
    first: tuple[int, int, int, int] | None,
    second: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    if first is None:
        return second
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )
