"""Mô hình layer tô (fill) không phá huỷ.

Layer tô không giữ pixel riêng: compositor dựng dải màu trực tiếp từ
``FillProperties`` cho từng dải quét, nên đổi màu/kiểu chỉ cần render lại và
không tốn bộ nhớ theo kích thước tài liệu. Hai kiểu được hỗ trợ: tô đặc và
gradient hai màu (tuyến tính theo góc hoặc hình tròn từ tâm).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

FILL_TYPES = ("solid", "gradient")
FILL_LABELS = {
    "solid": "Tô đặc",
    "gradient": "Gradient",
}
GRADIENT_TYPES = ("linear", "radial")
GRADIENT_LABELS = {
    "linear": "Tuyến tính",
    "radial": "Hình tròn",
}
MAX_ANGLE = 360
MIN_ANGLE = 0

Rgba = tuple[int, int, int, int]


def _validate_color(value: object, label: str) -> Rgba:
    try:
        channels = tuple(int(channel) for channel in value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} phải là RGBA trong khoảng 0..255.") from exc
    if len(channels) != 4 or any(not 0 <= channel <= 255 for channel in channels):
        raise ValueError(f"{label} phải là RGBA trong khoảng 0..255.")
    return channels  # type: ignore[return-value]


@dataclass(frozen=True)
class FillProperties:
    """Thuộc tính layer tô: màu đặc hoặc gradient hai màu."""

    fill_type: str = "solid"
    color: Rgba = (59, 110, 165, 255)
    color2: Rgba = (255, 255, 255, 255)
    gradient_type: str = "linear"
    angle: int = 0

    def __post_init__(self) -> None:
        fill_type = str(self.fill_type).strip().lower()
        if fill_type not in FILL_TYPES:
            raise ValueError(f"Kiểu tô không hợp lệ: {self.fill_type}")
        color = _validate_color(self.color, "Màu tô")
        color2 = _validate_color(self.color2, "Màu cuối")
        gradient_type = str(self.gradient_type).strip().lower()
        if gradient_type not in GRADIENT_TYPES:
            raise ValueError(f"Kiểu gradient không hợp lệ: {self.gradient_type}")
        try:
            angle = int(round(float(self.angle))) % 360
        except (TypeError, ValueError) as exc:
            raise ValueError("Góc gradient không hợp lệ.") from exc
        object.__setattr__(self, "fill_type", fill_type)
        object.__setattr__(self, "color", color)
        object.__setattr__(self, "color2", color2)
        object.__setattr__(self, "gradient_type", gradient_type)
        object.__setattr__(self, "angle", angle)

    @property
    def default_name(self) -> str:
        return FILL_LABELS[self.fill_type]

    @property
    def summary(self) -> str:
        if self.fill_type == "solid":
            return f"RGBA{self.color}"
        return (
            f"{GRADIENT_LABELS[self.gradient_type]} {self.angle}° "
            f"RGBA{self.color} → RGBA{self.color2}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "fill_type": self.fill_type,
            "color": list(self.color),
            "color2": list(self.color2),
            "gradient_type": self.gradient_type,
            "angle": self.angle,
        }

    @classmethod
    def from_dict(cls, data: object) -> "FillProperties":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu layer tô không hợp lệ.")
        try:
            return cls(
                fill_type=str(data.get("fill_type", "solid")),
                color=tuple(data.get("color", (59, 110, 165, 255))),  # type: ignore[arg-type]
                color2=tuple(data.get("color2", (255, 255, 255, 255))),  # type: ignore[arg-type]
                gradient_type=str(data.get("gradient_type", "linear")),
                angle=int(data.get("angle", 0)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thuộc tính layer tô không hợp lệ: {exc}") from exc


def _gradient_axis(width: int, height: int, angle: int) -> tuple[float, float, float]:
    radians = math.radians(float(angle))
    cosine = math.cos(radians)
    sine = math.sin(radians)
    span = max(1.0, float(max(width, height)))
    return cosine, sine, span


def render_fill(
    properties: FillProperties, width: int, height: int
) -> np.ndarray:
    """Render toàn bộ layer tô thành mảng RGBA uint8 (dùng cho rasterize/xem trước)."""
    if width < 1 or height < 1:
        raise ValueError("Kích thước vùng tô phải >= 1 px.")
    band = render_fill_band(properties, 0, height, width, height)
    return np.clip(band * 255.0 + 0.5, 0, 255).astype(np.uint8)


def render_fill_band(
    properties: FillProperties,
    band_y0: int,
    band_y1: int,
    canvas_width: int,
    canvas_height: int,
    *,
    x0: int = 0,
    x1: int | None = None,
) -> np.ndarray:
    """Dựng dải pixel RGBA float 0..1 cho compositor.

    ``x0``/``x1`` giới hạn cột cần dựng để tile cache chỉ tính vùng nhìn thấy.
    """
    band_y0 = max(0, int(band_y0))
    band_y1 = min(int(canvas_height), int(band_y1))
    if band_y1 <= band_y0:
        raise ValueError("Dải tô không hợp lệ.")
    width = max(1, int(canvas_width))
    height = max(1, int(canvas_height))
    x0 = max(0, int(x0))
    x1 = width if x1 is None else min(width, int(x1))
    if x1 <= x0:
        raise ValueError("Dải tô không hợp lệ.")
    output = np.empty((band_y1 - band_y0, x1 - x0, 4), dtype=np.float32)
    color1 = np.asarray(properties.color, dtype=np.float32) / 255.0
    color2 = np.asarray(properties.color2, dtype=np.float32) / 255.0

    if properties.fill_type == "solid":
        output[...] = color1
        return output

    xs = np.arange(x0, x1, dtype=np.float32) + 0.5
    ys = np.arange(band_y0, band_y1, dtype=np.float32) + 0.5
    if properties.gradient_type == "radial":
        radius = max(1.0, min(width, height) / 2.0)
        dx = xs - width / 2.0
        dy = ys - height / 2.0
        distance = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2) / radius
        t = np.clip(distance, 0.0, 1.0)
    else:
        cosine, sine, span = _gradient_axis(width, height, properties.angle)
        dx = xs - width / 2.0
        dy = ys - height / 2.0
        projection = dx[None, :] * cosine + dy[:, None] * sine
        t = np.clip(0.5 + projection / span, 0.0, 1.0)

    alpha = t[..., None]
    output[...] = color1 + (color2 - color1) * alpha
    return output
