"""Gradient: tô dải màu tuyến tính/hình tròn lên pixel hoặc layer mask.

Mỗi lần kéo chuột là một "phiên" (session): trong lúc kéo, gradient được vẽ
trực tiếp vào layer để xem trước; khi thả chuột mới ghi đúng một bước Undo/Redo.
Vùng chọn (nếu có) giới hạn phạm vi tô, mép vùng chọn được trộn mượt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from core.command_manager import LayerSnapshot, LayerTransformCommand, SetLayerMaskCommand
from core.layer import LayerKind
from core.paint import PAINT_TARGETS, _layer_selection_strength, color_luminance

if TYPE_CHECKING:  # pragma: no cover
    from core.document import Document
    from core.layer import Layer

GRADIENT_TYPES = ("linear", "radial")
MAX_LIVE_PIXELS = 16_000_000
_BAND_PIXELS = 1_000_000


@dataclass(frozen=True)
class GradientSettings:
    """Kiểu gradient và hai màu đầu/cuối (RGBA)."""

    gradient_type: str = "linear"
    start_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    end_color: tuple[int, int, int, int] = (255, 255, 255, 255)

    def __post_init__(self) -> None:
        gradient_type = str(self.gradient_type).lower()
        if gradient_type not in GRADIENT_TYPES:
            raise ValueError(f"Kiểu gradient không hợp lệ: {self.gradient_type}")
        object.__setattr__(self, "gradient_type", gradient_type)
        for name in ("start_color", "end_color"):
            color = tuple(int(channel) for channel in getattr(self, name))
            if len(color) != 4:
                raise ValueError("Màu gradient phải có 4 thành phần RGBA.")
            object.__setattr__(
                self, name, tuple(max(0, min(255, channel)) for channel in color)
            )


def gradient_ramp(
    width: int,
    height: int,
    start: tuple[float, float],
    end: tuple[float, float],
    gradient_type: str = "linear",
    *,
    y0: int = 0,
    y1: int | None = None,
) -> np.ndarray:
    """Giá trị 0..1 dọc theo hướng gradient cho một dải hàng của layer."""
    if gradient_type not in GRADIENT_TYPES:
        raise ValueError(f"Kiểu gradient không hợp lệ: {gradient_type}")
    if y1 is None:
        y1 = height
    y0 = max(0, int(y0))
    y1 = min(int(height), int(y1))
    if y1 <= y0 or width <= 0:
        return np.zeros((max(0, y1 - y0), max(0, width)), dtype=np.float32)
    xs = np.arange(width, dtype=np.float32)[None, :] + 0.5
    ys = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
    dx = float(end[0]) - float(start[0])
    dy = float(end[1]) - float(start[1])
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-6:
        return np.zeros((y1 - y0, width), dtype=np.float32)
    if gradient_type == "radial":
        distance = np.sqrt((xs - start[0]) ** 2 + (ys - start[1]) ** 2)
        ramp = distance / math.sqrt(length_sq)
    else:
        ramp = (
            (xs - start[0]) * dx + (ys - start[1]) * dy
        ) / length_sq
    return np.clip(ramp, 0.0, 1.0).astype(np.float32)


class GradientSession:
    """Một lần kéo gradient từ lúc nhấn chuột tới lúc thả."""

    def __init__(
        self,
        document: "Document",
        layer: "Layer",
        settings: GradientSettings,
        start: tuple[float, float],
        *,
        target: str = "pixels",
    ) -> None:
        if target not in PAINT_TARGETS:
            raise ValueError(f"Đích tô không hợp lệ: {target}")
        if target == "mask" and layer.mask is None:
            raise ValueError("Layer này chưa có layer mask để tô gradient.")
        self.document = document
        self.layer = layer
        self.settings = settings
        self.target = target
        if target == "mask" and layer.mask is not None:
            self.target_height, self.target_width = layer.mask.shape[:2]
        else:
            self.target_height, self.target_width = layer.height, layer.width
        if target == "mask" and layer.uses_canvas_mask:
            local_x, local_y = float(start[0]), float(start[1])
            self.selection_strength = document.selection_mask()
        else:
            local_x = float(start[0]) - layer.offset_x
            local_y = float(start[1]) - layer.offset_y
            self.selection_strength = _layer_selection_strength(document, layer)
        self.start = (local_x, local_y)
        self.end: tuple[float, float] | None = None
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
        self.mask_start_value = color_luminance(settings.start_color)
        self.mask_end_value = color_luminance(settings.end_color)
        self.preview_deferred = (
            self.target_width * self.target_height > MAX_LIVE_PIXELS
        )
        self._finished = False

    # ---------------------------------------------------------------- vẽ
    @property
    def has_direction(self) -> bool:
        if self.end is None:
            return False
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return dx * dx + dy * dy >= 0.25

    def update(self, x: float, y: float) -> bool:
        """Cập nhật điểm cuối theo toạ độ tài liệu và vẽ lại preview."""
        if self._finished:
            return False
        if self.target == "mask" and self.layer.uses_canvas_mask:
            self.end = (float(x), float(y))
        else:
            self.end = (
                float(x) - self.layer.offset_x,
                float(y) - self.layer.offset_y,
            )
        if not self.has_direction:
            return False
        if self.preview_deferred:
            return True
        self._render()
        return True

    def _render(self) -> None:
        if self.end is None or not self.has_direction:
            return
        width = self.target_width
        height = self.target_height
        if width <= 0 or height <= 0:
            return
        band_height = max(1, _BAND_PIXELS // max(1, width))
        start_rgb = np.asarray(self.settings.start_color[:3], dtype=np.float32)
        end_rgb = np.asarray(self.settings.end_color[:3], dtype=np.float32)
        start_alpha = float(self.settings.start_color[3])
        end_alpha = float(self.settings.end_color[3])
        for y0 in range(0, height, band_height):
            y1 = min(height, y0 + band_height)
            ramp = gradient_ramp(
                width,
                height,
                self.start,
                self.end,
                self.settings.gradient_type,
                y0=y0,
                y1=y1,
            )
            if self.target == "pixels":
                self._fill_pixels_band(
                    y0, y1, ramp, start_rgb, end_rgb, start_alpha, end_alpha
                )
            else:
                self._fill_mask_band(y0, y1, ramp)
        self.layer.touch()
        self.document.invalidate(self._dirty_rect())

    def _dirty_rect(self) -> tuple[int, int, int, int]:
        if self.target == "mask" and self.layer.uses_canvas_mask:
            return (0, 0, self.document.width, self.document.height)
        return (
            self.layer.offset_x,
            self.layer.offset_y,
            self.layer.offset_x + self.target_width,
            self.layer.offset_y + self.target_height,
        )

    def _fill_pixels_band(
        self,
        y0: int,
        y1: int,
        ramp: np.ndarray,
        start_rgb: np.ndarray,
        end_rgb: np.ndarray,
        start_alpha: float,
        end_alpha: float,
    ) -> None:
        gradient_rgb = start_rgb + (end_rgb - start_rgb) * ramp[..., None]
        gradient_alpha = start_alpha + (end_alpha - start_alpha) * ramp
        before = self.pixels_before[y0:y1]
        if self.selection_strength is None:
            out_rgb = gradient_rgb
            out_alpha = gradient_alpha
        else:
            strength = (
                self.selection_strength[y0:y1].astype(np.float32) / 255.0
            )[..., None]
            out_rgb = before[..., :3].astype(np.float32) + (
                gradient_rgb - before[..., :3].astype(np.float32)
            ) * strength
            out_alpha = before[..., 3].astype(np.float32) + (
                gradient_alpha - before[..., 3].astype(np.float32)
            ) * strength[..., 0]
        target = self.layer.pixels[y0:y1]
        target[..., :3] = np.clip(out_rgb + 0.5, 0.0, 255.0).astype(np.uint8)
        target[..., 3] = np.clip(out_alpha + 0.5, 0.0, 255.0).astype(np.uint8)

    def _fill_mask_band(self, y0: int, y1: int, ramp: np.ndarray) -> None:
        gradient_value = self.mask_start_value + (
            self.mask_end_value - self.mask_start_value
        ) * ramp
        before = self.mask_before[y0:y1].astype(np.float32)
        if self.selection_strength is None:
            out = gradient_value
        else:
            strength = self.selection_strength[y0:y1].astype(np.float32) / 255.0
            out = before + (gradient_value - before) * strength
        if self.layer.mask is not None:
            self.layer.mask[y0:y1] = np.clip(out + 0.5, 0.0, 255.0).astype(np.uint8)

    # ------------------------------------------------------------- kết thúc
    def finish(self) -> bool:
        """Hoàn tất gradient và ghi một bước Undo; False nếu không đổi gì."""
        if self._finished:
            return False
        self._finished = True
        if not self.has_direction:
            self._restore()
            return False
        self._render()
        if self._unchanged():
            self._restore()
            return False
        if self.target == "mask":
            command = SetLayerMaskCommand(
                self.layer,
                self.mask_before,
                self.mask_enabled_before,
                self.layer.mask.copy(),
                self.mask_enabled_before,
                "Gradient lên layer mask",
            )
        else:
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
                    self.layer.mask.copy() if self.layer.mask is not None else None
                ),
                mask_enabled=self.layer.mask_enabled,
                kind=LayerKind.PIXEL,
                text=None,
                shape=None,
            )
            command = LayerTransformCommand(old_state, new_state, "Gradient")
        self.document._apply_command(command, record=True)
        return True

    def cancel(self) -> None:
        """Khôi phục trạng thái trước khi kéo (dùng khi nhấn Esc)."""
        if self._finished:
            return
        self._finished = True
        self._restore()

    def _restore(self) -> None:
        self.layer.pixels[...] = self.pixels_before
        if self.mask_before is not None and self.layer.mask is not None:
            self.layer.mask[...] = self.mask_before
        self.layer.touch()
        self.document.invalidate(self._dirty_rect())

    def _unchanged(self) -> bool:
        if self.target == "mask":
            return self.mask_before is None or np.array_equal(
                self.layer.mask, self.mask_before
            )
        return np.array_equal(self.layer.pixels, self.pixels_before)
