"""Histogram màu dùng cho hộp thoại điều chỉnh."""

from __future__ import annotations

import numpy as np

HISTOGRAM_CHANNELS = ("rgb", "red", "green", "blue")
DEFAULT_BINS = 256


def compute_histogram(
    rgba: np.ndarray, bins: int = DEFAULT_BINS
) -> dict[str, np.ndarray]:
    """Đếm số điểm ảnh theo độ sáng; bỏ qua pixel trong suốt hoàn toàn."""
    array = np.asarray(rgba)
    if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
        raise ValueError("Ảnh phải là mảng (cao, rộng, 4) uint8.")
    bin_count = int(bins)
    if not 2 <= bin_count <= 4096:
        raise ValueError("Số cột histogram phải trong khoảng 2..4096.")
    rgb = array[..., :3].astype(np.float32)
    opaque = array[..., 3] > 0
    if not opaque.any():
        opaque = np.ones(array.shape[:2], dtype=bool)
    luma = (
        0.2126 * rgb[..., 0]
        + 0.7152 * rgb[..., 1]
        + 0.0722 * rgb[..., 2]
    )
    return {
        "rgb": _bin(luma[opaque], bin_count),
        "red": _bin(rgb[..., 0][opaque], bin_count),
        "green": _bin(rgb[..., 1][opaque], bin_count),
        "blue": _bin(rgb[..., 2][opaque], bin_count),
    }


def _bin(values: np.ndarray, bins: int) -> np.ndarray:
    indices = np.rint(
        np.clip(values, 0.0, 255.0) * (bins - 1) / 255.0
    ).astype(np.intp)
    return np.bincount(indices, minlength=bins)[:bins].astype(np.int64)
