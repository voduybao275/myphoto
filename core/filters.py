"""Bộ lọc ảnh thuần NumPy cho layer RGBA.

Mọi hàm nhận và trả về mảng ``(cao, rộng, 4)`` uint8, giữ nguyên alpha trừ các
bộ lọc làm mờ/làm nét (khi đó alpha được xử lý theo không gian tiền nhân alpha
để tránh quầng tối ở vùng trong suốt).
"""

from __future__ import annotations

import math

import numpy as np

MAX_FILTER_PIXELS = 64_000_000  # ~64 MP cho bộ lọc điểm ảnh
MAX_BLUR_PIXELS = 24_000_000  # ~24 MP cho blur/unsharp (cần mảng float32)
MAX_SHARPEN_PIXELS = 16_000_000
MAX_BLUR_RADIUS = 100.0
_CHUNK_PIXELS = 1 << 20


def _validate(rgba: np.ndarray, max_pixels: int = MAX_FILTER_PIXELS) -> np.ndarray:
    array = np.asarray(rgba)
    if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
        raise ValueError("Ảnh phải là mảng (cao, rộng, 4) uint8.")
    pixels = array.shape[0] * array.shape[1]
    if pixels > max_pixels:
        raise ValueError(
            f"Layer có {pixels / 1_000_000:.1f} megapixel, vượt giới hạn an toàn "
            f"{max_pixels // 1_000_000} MP cho bộ lọc này.\n"
            "Hãy thu nhỏ ảnh hoặc áp dụng trên vùng chọn nhỏ hơn."
        )
    return array


def _clamp_u8(values: np.ndarray) -> np.ndarray:
    return np.clip(values + 0.5, 0, 255).astype(np.uint8)


# --------------------------------------------------------------- điểm ảnh
def invert(rgba: np.ndarray) -> np.ndarray:
    """Đảo màu RGB, giữ nguyên alpha."""
    array = _validate(rgba)
    result = array.copy()
    result[..., :3] = 255 - result[..., :3]
    return result


def brightness_contrast(
    rgba: np.ndarray, brightness: float = 0.0, contrast: float = 0.0
) -> np.ndarray:
    """Điều chỉnh độ sáng (-100..100) và tương phản (-100..100)."""
    array = _validate(rgba)
    brightness = float(np.clip(brightness, -100.0, 100.0))
    contrast = float(np.clip(contrast, -100.0, 100.0))
    if brightness == 0.0 and contrast == 0.0:
        return array.copy()
    contrast_px = contrast * 2.55
    factor = (259.0 * (contrast_px + 255.0)) / (255.0 * (259.0 - contrast_px))
    levels = np.arange(256, dtype=np.float32)
    lut = _clamp_u8((levels - 128.0) * factor + 128.0 + brightness * 2.55)
    result = array.copy()
    result[..., :3] = lut[array[..., :3]]
    return result


def desaturate(rgba: np.ndarray) -> np.ndarray:
    """Chuyển sang ảnh xám theo luma Rec. 709, giữ alpha."""
    array = _validate(rgba)
    result = array.copy()
    flat = result.reshape(-1, 4)
    total = flat.shape[0]
    for start in range(0, total, _CHUNK_PIXELS):
        chunk = flat[start : start + _CHUNK_PIXELS]
        rgb = chunk[:, :3].astype(np.float32)
        luma = 0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]
        chunk[:, :3] = _clamp_u8(luma)[:, None]
    return result


def auto_contrast(rgba: np.ndarray, clip_percent: float = 0.5) -> np.ndarray:
    """Kéo giãn mỗi kênh RGB theo phân vị, bỏ qua một tỉ lệ điểm ảnh hai đầu."""
    array = _validate(rgba)
    clip_percent = float(np.clip(clip_percent, 0.0, 10.0))
    flat = array[..., :3].reshape(-1, 3)
    step = max(1, flat.shape[0] // 500_000)
    sample = flat[::step]
    low = np.percentile(sample, clip_percent, axis=0)
    high = np.percentile(sample, 100.0 - clip_percent, axis=0)
    levels = np.arange(256, dtype=np.float32)
    result = array.copy()
    for channel in range(3):
        if high[channel] - low[channel] <= 1e-6:
            continue
        scale = 255.0 / (high[channel] - low[channel])
        lut = _clamp_u8((levels - low[channel]) * scale)
        result[..., channel] = lut[array[..., channel]]
    return result


# ------------------------------------------------------------------- HSL
def _rgb_to_hsl(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    maxc = rgb.max(axis=1)
    minc = rgb.min(axis=1)
    delta = maxc - minc
    lightness = (maxc + minc) * 0.5
    denominator = 1.0 - np.abs(2.0 * lightness - 1.0)
    saturation = np.where(delta > 1e-6, delta / np.maximum(denominator, 1e-6), 0.0)

    hue = np.zeros_like(maxc)
    red, green, blue = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    chromatic = delta > 1e-6
    safe_delta = np.where(chromatic, delta, 1.0)
    red_mask = chromatic & (maxc == red)
    green_mask = chromatic & (maxc == green) & ~red_mask
    blue_mask = chromatic & ~red_mask & ~green_mask
    hue[red_mask] = ((green[red_mask] - blue[red_mask]) / safe_delta[red_mask]) % 6.0
    hue[green_mask] = (
        (blue[green_mask] - red[green_mask]) / safe_delta[green_mask] + 2.0
    )
    hue[blue_mask] = (
        (red[blue_mask] - green[blue_mask]) / safe_delta[blue_mask] + 4.0
    )
    hue = (hue / 6.0) % 1.0
    return hue, saturation.astype(np.float32), lightness.astype(np.float32)


def _hsl_to_rgb(
    hue: np.ndarray, saturation: np.ndarray, lightness: np.ndarray
) -> np.ndarray:
    chroma = (1.0 - np.abs(2.0 * lightness - 1.0)) * saturation
    sector = (hue % 1.0) * 6.0
    secondary = chroma * (1.0 - np.abs(sector % 2.0 - 1.0))
    middle = lightness - chroma * 0.5

    red = np.zeros_like(hue)
    green = np.zeros_like(hue)
    blue = np.zeros_like(hue)
    index = np.floor(sector).astype(np.int32) % 6
    for value, channel in (
        (0, red),
        (1, green),
        (2, green),
        (3, blue),
        (4, blue),
        (5, red),
    ):
        mask = index == value
        channel[mask] = chroma[mask]
    for value, channel in (
        (0, green),
        (1, red),
        (2, blue),
        (3, green),
        (4, red),
        (5, blue),
    ):
        mask = index == value
        channel[mask] = secondary[mask]
    return np.stack(
        [red + middle, green + middle, blue + middle], axis=1
    ).clip(0.0, 1.0)


def hue_saturation(
    rgba: np.ndarray,
    hue: float = 0.0,
    saturation: float = 0.0,
    lightness: float = 0.0,
) -> np.ndarray:
    """Dịch màu (-180..180°), đổi độ bão hoà và độ sáng (-100..100)."""
    array = _validate(rgba)
    hue = float(np.clip(hue, -180.0, 180.0))
    saturation = float(np.clip(saturation, -100.0, 100.0))
    lightness = float(np.clip(lightness, -100.0, 100.0))
    if hue == 0.0 and saturation == 0.0 and lightness == 0.0:
        return array.copy()

    result = array.copy()
    flat_in = array.reshape(-1, 4)
    flat_out = result.reshape(-1, 4)
    total = flat_in.shape[0]
    for start in range(0, total, _CHUNK_PIXELS):
        end = min(start + _CHUNK_PIXELS, total)
        rgb = flat_in[start:end, :3].astype(np.float32) / 255.0
        channels, saturation_values, lightness_values = _rgb_to_hsl(rgb)
        channels = (channels + hue / 360.0) % 1.0
        saturation_values = np.clip(
            saturation_values * (1.0 + saturation / 100.0), 0.0, 1.0
        )
        if lightness < 0.0:
            lightness_values = lightness_values * (1.0 + lightness / 100.0)
        elif lightness > 0.0:
            lightness_values = lightness_values + (
                1.0 - lightness_values
            ) * (lightness / 100.0)
        converted = _hsl_to_rgb(channels, saturation_values, lightness_values)
        flat_out[start:end, :3] = _clamp_u8(converted * 255.0)
    return result


# ------------------------------------------------------------ blur / sharpen
def _gaussian_box_radii(sigma: float, passes: int = 3) -> list[int]:
    if sigma <= 0.05:
        return [0] * passes
    ideal_width = math.sqrt(12.0 * sigma * sigma / passes + 1.0)
    lower = int(math.floor(ideal_width))
    if lower % 2 == 0:
        lower -= 1
    lower = max(1, lower)
    upper = lower + 2
    numerator = (
        12.0 * sigma * sigma
        - passes * lower * lower
        - 4.0 * passes * lower
        - 3.0 * passes
    )
    denominator = -4.0 * lower - 4.0
    ideal_passes = int(round(numerator / denominator)) if denominator else passes
    ideal_passes = max(0, min(passes, ideal_passes))
    widths = [lower if index < ideal_passes else upper for index in range(passes)]
    return [(width - 1) // 2 for width in widths]


def _box_blur_1d(channel: np.ndarray, radius: int, axis: int) -> np.ndarray:
    if radius <= 0:
        return channel
    if axis == 1:
        padded = np.pad(channel, ((0, 0), (radius, radius)), mode="edge")
    else:
        padded = np.pad(channel, ((radius, radius), (0, 0)), mode="edge")
    cumulative = np.cumsum(padded, axis=axis, dtype=np.float32)
    zeros_shape = list(cumulative.shape)
    zeros_shape[axis] = 1
    cumulative = np.concatenate(
        [np.zeros(zeros_shape, dtype=np.float32), cumulative], axis=axis
    )
    window = radius * 2 + 1
    if axis == 1:
        return (cumulative[:, window:] - cumulative[:, :-window]) / window
    return (cumulative[window:, :] - cumulative[:-window, :]) / window


def _blur_premultiplied(array: np.ndarray, radius: float) -> np.ndarray:
    work = array.astype(np.float32)
    alpha_scale = work[..., 3:4] / 255.0
    work[..., :3] *= alpha_scale

    for box_radius in _gaussian_box_radii(radius):
        for channel in range(4):
            blurred = _box_blur_1d(work[..., channel], box_radius, 1)
            blurred = _box_blur_1d(blurred, box_radius, 0)
            work[..., channel] = blurred

    alpha = np.clip(work[..., 3], 0.0, 255.0)
    safe_alpha = np.maximum(alpha, 1e-6)
    rgb = work[..., :3] * (255.0 / safe_alpha[..., None])
    result = np.empty_like(array)
    result[..., :3] = _clamp_u8(rgb)
    result[..., 3] = _clamp_u8(alpha)
    return result


def gaussian_blur(rgba: np.ndarray, radius: float = 2.0) -> np.ndarray:
    """Làm mờ Gaussian xấp xỉ 3 lần box blur, xử lý alpha tiền nhân."""
    array = _validate(rgba, MAX_BLUR_PIXELS)
    radius = float(np.clip(radius, 0.0, MAX_BLUR_RADIUS))
    if radius <= 0.05:
        return array.copy()
    return _blur_premultiplied(array, radius)


def unsharp_mask(
    rgba: np.ndarray,
    amount: float = 100.0,
    radius: float = 2.0,
    threshold: int = 0,
) -> np.ndarray:
    """Làm nét bằng unsharp mask; ngưỡng 0..255 giữ vùng ít tương phản yên."""
    array = _validate(rgba, MAX_SHARPEN_PIXELS)
    amount = float(np.clip(amount, 0.0, 300.0))
    radius = float(np.clip(radius, 0.0, MAX_BLUR_RADIUS))
    threshold = int(np.clip(threshold, 0, 255))
    if amount <= 0.0 or radius <= 0.05:
        return array.copy()

    blurred = _blur_premultiplied(array, radius)
    original = array[..., :3].astype(np.float32)
    low = blurred[..., :3].astype(np.float32)
    difference = original - low
    sharpened = original + difference * (amount / 100.0)
    sharpened_u8 = _clamp_u8(sharpened)

    result = array.copy()
    target = result[..., :3]
    if threshold > 0:
        mask = np.max(np.abs(difference), axis=2) > threshold
        target[mask] = sharpened_u8[mask]
    else:
        target[...] = sharpened_u8
    return result
