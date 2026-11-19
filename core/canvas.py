"""Compositing layer bằng NumPy và chuyển kết quả sang QImage.

Bộ compositor xử lý theo dải (band) để giới hạn bộ nhớ tạm khi làm việc với
ảnh lớn, phù hợp mục tiêu máy RAM 8GB. Mọi layer đều dùng alpha thẳng
(straight alpha) với công thức trộn theo chuẩn W3C Compositing.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterable

import numpy as np
from PySide6.QtGui import QImage

from core.adjustment_layer import apply_adjustment_rgb
from core.fill_layer import render_fill_band
from core.layer import Layer, LayerKind

# Mục tiêu dung lượng bộ nhớ tạm cho mỗi dải ~ 16 MB (float32 x 4 kênh).
_BAND_PIXEL_BUDGET = 1_000_000


def _lum(color: np.ndarray) -> np.ndarray:
    return 0.3 * color[..., 0] + 0.59 * color[..., 1] + 0.11 * color[..., 2]


def _sat(color: np.ndarray) -> np.ndarray:
    return color.max(axis=-1) - color.min(axis=-1)


def _clip_color(color: np.ndarray) -> np.ndarray:
    lum = _lum(color)[..., None]
    low = color.min(axis=-1)[..., None]
    high = color.max(axis=-1)[..., None]
    out = color.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(low < 0.0, lum + (color - lum) * lum / (lum - low), out)
        out = np.where(high > 1.0, lum + (color - lum) * (1.0 - lum) / (high - lum), out)
    return np.clip(out, 0.0, 1.0)


def _set_lum(color: np.ndarray, lum: np.ndarray) -> np.ndarray:
    return _clip_color(color + (lum - _lum(color))[..., None])


def _set_sat(color: np.ndarray, sat: np.ndarray) -> np.ndarray:
    indices = np.argsort(color, axis=-1)
    c_min = np.take_along_axis(color, indices[..., 0:1], axis=-1)
    c_mid = np.take_along_axis(color, indices[..., 1:2], axis=-1)
    c_max = np.take_along_axis(color, indices[..., 2:3], axis=-1)
    sat = sat[..., None]
    span = c_max - c_min
    with np.errstate(divide="ignore", invalid="ignore"):
        mid_out = np.where(span > 0.0, (c_mid - c_min) * sat / span, 0.0)
    max_out = np.where(span > 0.0, sat, 0.0)
    out = np.empty_like(color)
    np.put_along_axis(out, indices[..., 0:1], np.zeros_like(c_min), axis=-1)
    np.put_along_axis(out, indices[..., 1:2], mid_out, axis=-1)
    np.put_along_axis(out, indices[..., 2:3], max_out, axis=-1)
    return out


def blend_rgb(backdrop: np.ndarray, source: np.ndarray, mode: str) -> np.ndarray:
    """Trộn màu RGB (0..1, chưa nhân alpha) theo blend mode."""
    if mode == "normal":
        return source
    if mode == "multiply":
        return backdrop * source
    if mode == "screen":
        return 1.0 - (1.0 - backdrop) * (1.0 - source)
    if mode == "overlay":
        return np.where(
            backdrop <= 0.5,
            2.0 * backdrop * source,
            1.0 - 2.0 * (1.0 - backdrop) * (1.0 - source),
        )
    if mode == "hard_light":
        return np.where(
            source <= 0.5,
            2.0 * backdrop * source,
            1.0 - 2.0 * (1.0 - backdrop) * (1.0 - source),
        )
    if mode == "soft_light":
        soft = np.where(
            backdrop <= 0.25,
            ((16.0 * backdrop - 12.0) * backdrop + 4.0) * backdrop,
            np.sqrt(np.maximum(backdrop, 0.0)),
        )
        return np.where(
            source <= 0.5,
            backdrop - (1.0 - 2.0 * source) * backdrop * (1.0 - backdrop),
            backdrop + (2.0 * source - 1.0) * (soft - backdrop),
        )
    if mode == "darken":
        return np.minimum(backdrop, source)
    if mode == "lighten":
        return np.maximum(backdrop, source)
    if mode == "color_dodge":
        with np.errstate(divide="ignore", invalid="ignore"):
            dodge = np.minimum(1.0, backdrop / (1.0 - source))
        return np.where(source >= 1.0, 1.0, np.where(backdrop <= 0.0, 0.0, dodge))
    if mode == "color_burn":
        with np.errstate(divide="ignore", invalid="ignore"):
            burn = 1.0 - np.minimum(1.0, (1.0 - backdrop) / np.maximum(source, 1e-8))
        return np.where(source <= 0.0, 0.0, np.where(backdrop >= 1.0, 1.0, burn))
    if mode == "difference":
        return np.abs(backdrop - source)
    if mode == "hue":
        return _set_lum(_set_sat(source, _sat(backdrop)), _lum(backdrop))
    if mode == "saturation":
        return _set_lum(_set_sat(backdrop, _sat(source)), _lum(backdrop))
    if mode == "color":
        return _set_lum(source, _lum(backdrop))
    if mode == "luminosity":
        return _set_lum(backdrop, _lum(source))
    return source


def _apply_adjustment_rect(
    accumulator: np.ndarray,
    layer: Layer,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    canvas_width: int,
) -> None:
    properties = layer.adjustment
    if properties is None or properties.is_identity:
        return
    strength = float(layer.opacity)
    if strength <= 0.0:
        return
    rgb = accumulator[..., :3]
    adjusted = apply_adjustment_rgb(rgb, properties)
    factor: float | np.ndarray = strength
    mask = layer.mask
    if (
        mask is not None
        and layer.mask_enabled
        and mask.shape[1] == canvas_width
        and mask.shape[0] >= y1
    ):
        mask_rect = mask[y0:y1, x0:x1].astype(np.float32) * (1.0 / 255.0)
        factor = mask_rect * strength if strength < 0.999 else mask_rect
    if not (isinstance(factor, float) and factor >= 0.999):
        weights = factor if isinstance(factor, float) else factor[..., None]
        adjusted = rgb + (adjusted - rgb) * weights
    accumulator[..., :3] = np.clip(adjusted, 0.0, 1.0)


_BLEND_MODES = {
    "multiply",
    "screen",
    "overlay",
    "soft_light",
    "hard_light",
    "darken",
    "lighten",
    "color_dodge",
    "color_burn",
    "difference",
    "hue",
    "saturation",
    "color",
    "luminosity",
}


def _composite_source_band(
    dest: np.ndarray,
    src_rgb: np.ndarray,
    src_alpha: np.ndarray,
    blend_mode: str,
) -> None:
    """Trộn một nguồn RGB thẳng alpha vào vùng đích (đã cắt theo dải)."""
    dst_alpha = dest[..., 3]
    out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
    norm = np.maximum(out_alpha, 1e-8)[..., None]
    dst_rgb = dest[..., :3]

    if blend_mode == "normal" or blend_mode not in _BLEND_MODES:
        out_rgb = (
            src_alpha[..., None] * src_rgb
            + dst_alpha[..., None] * (1.0 - src_alpha[..., None]) * dst_rgb
        ) / norm
    else:
        blended = blend_rgb(dst_rgb, src_rgb, blend_mode)
        out_rgb = (
            src_alpha[..., None] * (1.0 - dst_alpha[..., None]) * src_rgb
            + (src_alpha * dst_alpha)[..., None] * blended
            + (1.0 - src_alpha[..., None]) * dst_alpha[..., None] * dst_rgb
        ) / norm

    dest[..., :3] = np.clip(out_rgb, 0.0, 1.0)
    dest[..., 3] = np.clip(out_alpha, 0.0, 1.0)


def _blend_rect(
    accumulator: np.ndarray,
    layer: Layer,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    canvas_width: int,
    canvas_height: int,
) -> None:
    if not layer.visible or layer.opacity <= 0.0:
        return

    if layer.kind == LayerKind.ADJUSTMENT:
        _apply_adjustment_rect(accumulator, layer, x0, y0, x1, y1, canvas_width)
        return

    if layer.kind == LayerKind.FILL:
        if layer.fill_props is None:
            return
        src = render_fill_band(
            layer.fill_props,
            y0,
            y1,
            canvas_width,
            canvas_height,
            x0=x0,
            x1=x1,
        )
        src_alpha = src[..., 3] * float(layer.opacity)
        mask = layer.mask
        if (
            mask is not None
            and layer.mask_enabled
            and mask.ndim == 2
            and mask.shape[1] == canvas_width
            and mask.shape[0] >= y1
        ):
            mask_rect = mask[y0:y1, x0:x1].astype(np.float32) * (1.0 / 255.0)
            src_alpha = src_alpha * mask_rect
        _composite_source_band(
            accumulator, src[..., :3], src_alpha, layer.blend_mode
        )
        return

    ix0 = max(x0, max(0, layer.offset_x))
    ix1 = min(x1, min(canvas_width, layer.offset_x + layer.width))
    iy0 = max(y0, max(0, layer.offset_y))
    iy1 = min(y1, min(canvas_height, layer.offset_y + layer.height))
    if ix1 <= ix0 or iy1 <= iy0:
        return

    local_x0 = ix0 - layer.offset_x
    local_x1 = ix1 - layer.offset_x
    local_y0 = iy0 - layer.offset_y
    local_y1 = iy1 - layer.offset_y
    src = layer.pixels[local_y0:local_y1, local_x0:local_x1].astype(np.float32)
    src *= 1.0 / 255.0
    dest = accumulator[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0]

    src_alpha = src[..., 3] * float(layer.opacity)
    if layer.mask is not None and layer.mask_enabled:
        mask_crop = layer.mask[local_y0:local_y1, local_x0:local_x1]
        src_alpha = src_alpha * (mask_crop.astype(np.float32) * (1.0 / 255.0))

    _composite_source_band(dest, src[..., :3], src_alpha, layer.blend_mode)


def _blend_group_rect(
    accumulator: np.ndarray,
    layer: Layer,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    canvas_width: int,
    canvas_height: int,
    parent_map: dict[str | None, list[Layer]],
    stack: frozenset[str],
) -> None:
    """Hợp nhất các layer con vào buffer riêng rồi trộn cả nhóm như một layer."""
    if not layer.visible or layer.opacity <= 0.0 or layer.id in stack:
        return
    group = np.zeros_like(accumulator)
    _composite_children_rect(
        group,
        parent_map.get(layer.id, []),
        x0,
        y0,
        x1,
        y1,
        canvas_width,
        canvas_height,
        parent_map,
        stack | {layer.id},
    )
    if not np.any(group[..., 3] > 0.0):
        return

    src_alpha = group[..., 3] * float(layer.opacity)
    mask = layer.mask
    if (
        mask is not None
        and layer.mask_enabled
        and mask.ndim == 2
        and mask.shape[1] == canvas_width
        and mask.shape[0] >= y1
    ):
        mask_rect = mask[y0:y1, x0:x1].astype(np.float32) * (1.0 / 255.0)
        src_alpha = src_alpha * mask_rect

    _composite_source_band(
        accumulator, group[..., :3], src_alpha, layer.blend_mode
    )


def _composite_children_rect(
    accumulator: np.ndarray,
    children: list[Layer],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    canvas_width: int,
    canvas_height: int,
    parent_map: dict[str | None, list[Layer]],
    stack: frozenset[str] = frozenset(),
) -> None:
    for layer in children:
        if layer.kind == LayerKind.GROUP:
            _blend_group_rect(
                accumulator,
                layer,
                x0,
                y0,
                x1,
                y1,
                canvas_width,
                canvas_height,
                parent_map,
                stack,
            )
        else:
            _blend_rect(
                accumulator,
                layer,
                x0,
                y0,
                x1,
                y1,
                canvas_width,
                canvas_height,
            )


def composite_region(
    layers: Iterable[Layer],
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> np.ndarray:
    """Hợp nhất một vùng chữ nhật của tài liệu thành RGBA uint8.

    Đây là lõi cho tile cache: chỉ vùng được yêu cầu mới được tính, nên ảnh lớn
    không cần hợp nhất toàn bộ mỗi lần vẽ lại. Toạ độ tính theo pixel tài liệu.
    """
    if width < 1 or height < 1:
        raise ValueError("Kích thước canvas phải >= 1 px.")
    x0 = max(0, int(x0))
    y0 = max(0, int(y0))
    x1 = min(int(width), int(x1))
    y1 = min(int(height), int(y1))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Vùng hợp nhất không hợp lệ.")

    layers = list(layers)
    output = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
    visible = [layer for layer in layers if layer.visible and layer.opacity > 0.0]
    if not visible:
        return output

    known_ids = {layer.id for layer in layers}
    parent_map: dict[str | None, list[Layer]] = {}
    for layer in layers:
        parent = layer.group_id if layer.group_id in known_ids else None
        parent_map.setdefault(parent, []).append(layer)

    if (
        len(visible) == 1
        and visible[0].kind not in LayerKind.CANVAS_MASK_KINDS
        and visible[0].group_id is None
        and visible[0].blend_mode == "normal"
        and visible[0].opacity >= 0.999
        and visible[0].pixels is not None
        and not (visible[0].mask is not None and visible[0].mask_enabled)
    ):
        only = visible[0]
        cx0 = max(x0, max(0, only.offset_x))
        cx1 = min(x1, min(width, only.offset_x + only.width))
        cy0 = max(y0, max(0, only.offset_y))
        cy1 = min(y1, min(height, only.offset_y + only.height))
        if cx1 > cx0 and cy1 > cy0:
            output[cy0 - y0 : cy1 - y0, cx0 - x0 : cx1 - x0] = only.pixels[
                cy0 - only.offset_y : cy1 - only.offset_y,
                cx0 - only.offset_x : cx1 - only.offset_x,
            ]
        return output

    accumulator = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.float32)
    _composite_children_rect(
        accumulator,
        parent_map.get(None, []),
        x0,
        y0,
        x1,
        y1,
        width,
        height,
        parent_map,
    )
    output[...] = np.clip(accumulator * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return output


def composite_layers(layers: Iterable[Layer], width: int, height: int) -> np.ndarray:
    """Hợp nhất các layer thành ảnh RGBA uint8 kích thước (height, width, 4)."""
    if width < 1 or height < 1:
        raise ValueError("Kích thước canvas phải >= 1 px.")

    layers = list(layers)
    output = np.zeros((height, width, 4), dtype=np.uint8)
    if not any(layer.visible and layer.opacity > 0.0 for layer in layers):
        return output

    band_rows = max(16, min(1024, _BAND_PIXEL_BUDGET // max(1, width)))
    for band_y0 in range(0, height, band_rows):
        band_y1 = min(height, band_y0 + band_rows)
        output[band_y0:band_y1] = composite_region(
            layers, width, height, 0, band_y0, width, band_y1
        )
    return output


def scale_layers_for_preview(
    layers: Iterable[Layer], width: int, height: int, max_side: int
) -> tuple[list[Layer], int, int]:
    """Tạo bản sao layer đã lấy mẫu thưa để dựng ảnh xem trước nhẹ.

    Trả về (layers, rộng, cao) ở độ phân giải xem trước. Chỉ pixel/mask bị lấy
    mẫu; thuộc tính điều chỉnh, nhóm và fill giữ nguyên nên ảnh xem trước vẫn
    phản ánh đúng cấu trúc tài liệu.
    """
    if max_side < 1:
        raise ValueError("max_side phải >= 1.")
    if width < 1 or height < 1:
        raise ValueError("Kích thước canvas phải >= 1 px.")
    step = max(1, int(math.ceil(max(width, height) / max_side)))
    if step == 1:
        return list(layers), width, height

    preview_width = max(1, (width + step - 1) // step)
    preview_height = max(1, (height + step - 1) // step)
    scaled: list[Layer] = []
    for layer in layers:
        clone = copy.copy(layer)
        clone.offset_x = layer.offset_x // step
        clone.offset_y = layer.offset_y // step
        if layer.pixels is not None and layer.kind not in LayerKind.CANVAS_MASK_KINDS:
            clone.pixels = np.ascontiguousarray(layer.pixels[::step, ::step])
            clone.height, clone.width = clone.pixels.shape[:2]
        if layer.mask is not None:
            clone.mask = np.ascontiguousarray(layer.mask[::step, ::step])
        scaled.append(clone)
    return scaled, preview_width, preview_height


def numpy_rgba_to_qimage(array: np.ndarray) -> QImage:
    """Tạo QImage dùng trực tiếp bộ nhớ của mảng NumPy.

    LƯU Ý: người gọi phải giữ mảng gốc còn sống chừng nào QImage còn được dùng.
    """
    arr = np.ascontiguousarray(array)
    if arr.ndim != 3 or arr.shape[2] != 4 or arr.dtype != np.uint8:
        raise ValueError("Mảng phải có dạng (cao, rộng, 4) uint8.")
    height, width = arr.shape[:2]
    image = QImage(arr.data, width, height, int(arr.strides[0]), QImage.Format.Format_RGBA8888)
    if image.isNull():
        raise RuntimeError("Không thể tạo QImage từ dữ liệu pixel.")
    try:  # Giữ tham chiếu phòng trường hợp người gọi quên.
        image._numpy_ref = arr  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        pass
    return image


def downsample_rgba(array: np.ndarray, max_side: int = 128) -> np.ndarray:
    """Thu nhỏ bằng lấy mẫu stride (nhanh và đủ tốt cho thumbnail)."""
    if max_side < 1:
        raise ValueError("max_side phải >= 1.")
    height, width = array.shape[:2]
    step = max(1, int(np.ceil(max(height, width) / max_side)))
    return np.ascontiguousarray(array[::step, ::step])


def downsample_mask(mask: np.ndarray, max_side: int = 128) -> np.ndarray:
    """Thu nhỏ mask 2 chiều bằng cùng quy tắc stride với ảnh xem trước."""
    array = np.asarray(mask)
    if array.ndim != 2:
        raise ValueError("Mask phải là mảng 2 chiều.")
    if max_side < 1:
        raise ValueError("max_side phải >= 1.")
    height, width = array.shape
    step = max(1, int(np.ceil(max(height, width) / max_side)))
    return np.ascontiguousarray(array[::step, ::step])


def qimage_to_rgba(image: QImage) -> np.ndarray:
    """Chuyển QImage sang mảng RGBA uint8 (bản sao độc lập với QImage)."""
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = converted.width()
    height = converted.height()
    line_bytes = converted.bytesPerLine()
    pointer = converted.constBits()
    if hasattr(pointer, "setsize"):  # PySide2 trả về sip.voidptr
        pointer.setsize(line_bytes * height)
    try:
        buffer = bytes(pointer)
    except TypeError:  # pragma: no cover - PySide6 trả memoryview
        buffer = memoryview(pointer).tobytes()
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape((height, line_bytes))
    array = rows[:, : width * 4].reshape((height, width, 4))
    return np.ascontiguousarray(array).copy()
