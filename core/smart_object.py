"""Smart object: giữ ảnh gốc và biến đổi không phá huỷ.

Layer smart object lưu bản sao ảnh nguồn riêng; pixel hiển thị được dựng lại
từ nguồn theo góc xoay, tỉ lệ và lật. Nhờ vậy có thể xoay/lật/đổi tỉ lệ nhiều
lần mà không mất chi tiết, đặt lại biến đổi hoặc thay nội dung mà vẫn giữ thiết
lập. Rasterize biến layer thành pixel thường.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter, QTransform

from core.canvas import qimage_to_rgba

MIN_SCALE = 10.0
MAX_SCALE = 800.0
MAX_SOURCE_SIDE = 30_000
MAX_SOURCE_PIXELS = 64_000_000
MAX_RENDER_PIXELS = 64_000_000
MAX_RENDER_SIDE = 30_000


def _normalize_angle(angle: float) -> float:
    normalized = math.fmod(float(angle), 360.0)
    if normalized <= -180.0:
        normalized += 360.0
    elif normalized > 180.0:
        normalized -= 360.0
    return round(normalized, 2)


@dataclass(frozen=True)
class SmartObjectProperties:
    """Ảnh nguồn cùng phép biến đổi không phá huỷ đang áp dụng."""

    source_name: str = "Smart Object"
    source_width: int = 1
    source_height: int = 1
    angle: float = 0.0
    scale: float = 100.0
    flip_h: bool = False
    flip_v: bool = False

    def __post_init__(self) -> None:
        name = str(self.source_name).strip() or "Smart Object"
        try:
            width = int(self.source_width)
            height = int(self.source_height)
            angle = _normalize_angle(float(self.angle))
            scale = float(self.scale)
        except (TypeError, ValueError) as exc:
            raise ValueError("Thuộc tính smart object không hợp lệ.") from exc
        if not (1 <= width <= MAX_SOURCE_SIDE and 1 <= height <= MAX_SOURCE_SIDE):
            raise ValueError(
                f"Kích thước ảnh nguồn phải trong khoảng 1..{MAX_SOURCE_SIDE} px."
            )
        if width * height > MAX_SOURCE_PIXELS:
            raise ValueError("Ảnh nguồn vượt giới hạn kích thước an toàn.")
        if not math.isfinite(scale) or not (MIN_SCALE <= scale <= MAX_SCALE):
            raise ValueError(
                f"Tỉ lệ smart object phải trong khoảng {MIN_SCALE:g}..{MAX_SCALE:g} %."
            )
        object.__setattr__(self, "source_name", name)
        object.__setattr__(self, "source_width", width)
        object.__setattr__(self, "source_height", height)
        object.__setattr__(self, "angle", angle)
        object.__setattr__(self, "scale", round(scale, 2))
        object.__setattr__(self, "flip_h", bool(self.flip_h))
        object.__setattr__(self, "flip_v", bool(self.flip_v))

    @property
    def default_name(self) -> str:
        stem = self.source_name.rsplit(".", 1)[0]
        return stem[:60] or "Smart Object"

    @property
    def is_identity(self) -> bool:
        return (
            abs(self.angle) < 1e-6
            and abs(self.scale - 100.0) < 1e-6
            and not self.flip_h
            and not self.flip_v
        )

    @property
    def summary(self) -> str:
        parts = [f"{self.scale:g} %"]
        if abs(self.angle) > 1e-6:
            parts.append(f"{self.angle:g}°")
        if self.flip_h:
            parts.append("lật ngang")
        if self.flip_v:
            parts.append("lật dọc")
        return " · ".join(parts)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "source_width": self.source_width,
            "source_height": self.source_height,
            "angle": self.angle,
            "scale": self.scale,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
        }

    @classmethod
    def from_dict(cls, data: object) -> "SmartObjectProperties":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu smart object không hợp lệ.")
        try:
            return cls(
                source_name=str(data.get("source_name", "Smart Object")),
                source_width=int(data.get("source_width", 1)),
                source_height=int(data.get("source_height", 1)),
                angle=float(data.get("angle", 0.0)),
                scale=float(data.get("scale", 100.0)),
                flip_h=bool(data.get("flip_h", False)),
                flip_v=bool(data.get("flip_v", False)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thuộc tính smart object không hợp lệ: {exc}") from exc


def validate_source(source: np.ndarray) -> np.ndarray:
    array = np.asarray(source)
    if array.dtype != np.uint8:
        raise ValueError("Ảnh nguồn smart object phải có dtype uint8.")
    if array.ndim != 3 or array.shape[2] != 4:
        raise ValueError("Ảnh nguồn smart object phải có dạng (cao, rộng, 4).")
    height, width = array.shape[:2]
    if not (1 <= width <= MAX_SOURCE_SIDE and 1 <= height <= MAX_SOURCE_SIDE):
        raise ValueError(
            f"Ảnh nguồn phải trong khoảng 1..{MAX_SOURCE_SIDE} px mỗi cạnh."
        )
    if width * height > MAX_SOURCE_PIXELS:
        raise ValueError("Ảnh nguồn vượt giới hạn kích thước an toàn.")
    return np.ascontiguousarray(array)


def render_smart_object(
    source: np.ndarray, properties: SmartObjectProperties
) -> np.ndarray:
    """Dựng pixel hiển thị từ ảnh nguồn theo phép biến đổi hiện tại."""
    array = validate_source(source)
    height, width = array.shape[:2]
    if properties.is_identity:
        return array.copy()

    image = QImage(
        array.tobytes(),
        width,
        height,
        width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()

    transform = QTransform()
    transform.translate(width / 2.0, height / 2.0)
    if abs(properties.angle) > 1e-6:
        transform.rotate(properties.angle)
    scale_x = properties.scale / 100.0 * (-1.0 if properties.flip_h else 1.0)
    scale_y = properties.scale / 100.0 * (-1.0 if properties.flip_v else 1.0)
    transform.scale(scale_x, scale_y)
    transform.translate(-width / 2.0, -height / 2.0)

    mapped = transform.mapRect(QRectF(0.0, 0.0, float(width), float(height)))
    out_width = max(1, int(math.ceil(mapped.width() - 1e-6)))
    out_height = max(1, int(math.ceil(mapped.height() - 1e-6)))
    if (
        out_width > MAX_RENDER_SIDE
        or out_height > MAX_RENDER_SIDE
        or out_width * out_height > MAX_RENDER_PIXELS
    ):
        raise ValueError(
            "Smart object sau khi biến đổi vượt giới hạn kích thước an toàn.\n"
            "Hãy giảm tỉ lệ hoặc góc xoay."
        )

    output = QImage(
        out_width, out_height, QImage.Format.Format_RGBA8888
    )
    output.fill(0)
    painter = QPainter(output)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(-mapped.left(), -mapped.top())
        painter.setTransform(transform, True)
        painter.drawImage(0, 0, image)
    finally:
        painter.end()
    return qimage_to_rgba(output)


def transform_operation(
    properties: SmartObjectProperties, operation: str
) -> SmartObjectProperties:
    """Áp một thao tác xoay/lật vào thuộc tính mà không đụng pixel."""
    from dataclasses import replace

    if operation == "rotate_cw":
        return replace(properties, angle=properties.angle + 90.0)
    if operation == "rotate_ccw":
        return replace(properties, angle=properties.angle - 90.0)
    if operation == "rotate_180":
        return replace(properties, angle=properties.angle + 180.0)
    if operation == "flip_h":
        return replace(
            properties,
            angle=-properties.angle,
            flip_h=not properties.flip_h,
        )
    if operation == "flip_v":
        return replace(
            properties,
            angle=-properties.angle,
            flip_v=not properties.flip_v,
        )
    raise ValueError(f"Thao tác smart object không hỗ trợ: {operation}")
