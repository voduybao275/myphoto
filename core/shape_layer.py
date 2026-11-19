"""Mô hình và bộ render cho layer hình khối (shape).

Shape lưu loại hình, kích thước, màu tô, màu viền và bán kính bo góc trong
``ShapeProperties``. Khi tạo hoặc sửa, hình được render thành mảng RGBA bằng
QPainter để layer hoạt động như mọi layer pixel khác, đồng thời vẫn giữ dữ liệu
vector để có thể chỉnh sửa tiếp cho tới khi rasterize.
"""

from __future__ import annotations

from dataclasses import dataclass

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from core.canvas import qimage_to_rgba

SHAPE_KINDS = ("rectangle", "rounded_rectangle", "ellipse")
SHAPE_LABELS = {
    "rectangle": "Hình chữ nhật",
    "rounded_rectangle": "Chữ nhật bo góc",
    "ellipse": "Hình ellipse",
}
MAX_SHAPE_SIZE = 30_000
MAX_RENDER_PIXELS = 64_000_000
MAX_STROKE_WIDTH = 500
MAX_CORNER_RADIUS = 15_000

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
class ShapeProperties:
    """Thuộc tính của một layer hình khối (bất biến để chia sẻ với history)."""

    kind: str = "rectangle"
    width: int = 200
    height: int = 140
    fill_color: Rgba | None = (59, 110, 165, 255)
    stroke_color: Rgba = (255, 255, 255, 255)
    stroke_width: int = 0
    corner_radius: float = 0.0

    def __post_init__(self) -> None:
        kind = str(self.kind).lower()
        if kind not in SHAPE_KINDS:
            raise ValueError(f"Loại hình khối không hợp lệ: {self.kind}")
        try:
            width = int(self.width)
            height = int(self.height)
            stroke_width = int(self.stroke_width)
            radius = float(self.corner_radius)
        except (TypeError, ValueError) as exc:
            raise ValueError("Kích thước hoặc viền của hình khối không hợp lệ.") from exc
        if not (1 <= width <= MAX_SHAPE_SIZE and 1 <= height <= MAX_SHAPE_SIZE):
            raise ValueError(
                f"Kích thước hình khối phải trong khoảng 1..{MAX_SHAPE_SIZE} px."
            )
        if width * height > MAX_RENDER_PIXELS:
            raise ValueError(
                "Hình khối vượt giới hạn kích thước an toàn.\n"
                "Hãy giảm kích thước hình."
            )
        if not 0 <= stroke_width <= MAX_STROKE_WIDTH:
            raise ValueError(
                f"Độ dày viền phải trong khoảng 0..{MAX_STROKE_WIDTH} px."
            )
        if stroke_width > max(1, min(width, height) // 2):
            raise ValueError("Viền quá dày so với kích thước hình khối.")
        if not 0.0 <= radius <= MAX_CORNER_RADIUS:
            raise ValueError(
                f"Bán kính bo góc phải trong khoảng 0..{MAX_CORNER_RADIUS} px."
            )
        if kind != "rounded_rectangle":
            radius = 0.0
        else:
            radius = min(radius, min(width, height) / 2.0)
        fill_color = (
            None
            if self.fill_color is None
            else _validate_color(self.fill_color, "Màu tô")
        )
        stroke_color = _validate_color(self.stroke_color, "Màu viền")
        if fill_color is None and stroke_width == 0:
            raise ValueError("Hình khối cần có màu tô hoặc viền.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "fill_color", fill_color)
        object.__setattr__(self, "stroke_color", stroke_color)
        object.__setattr__(self, "stroke_width", stroke_width)
        object.__setattr__(self, "corner_radius", radius)

    @property
    def has_fill(self) -> bool:
        return self.fill_color is not None

    @property
    def has_stroke(self) -> bool:
        return self.stroke_width > 0

    @property
    def default_name(self) -> str:
        return SHAPE_LABELS.get(self.kind, "Hình khối")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "fill_color": list(self.fill_color) if self.fill_color else None,
            "stroke_color": list(self.stroke_color),
            "stroke_width": self.stroke_width,
            "corner_radius": round(float(self.corner_radius), 3),
        }

    @classmethod
    def from_dict(cls, data: object) -> "ShapeProperties":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu hình khối không hợp lệ.")
        fill = data["fill_color"] if "fill_color" in data else (59, 110, 165, 255)
        try:
            return cls(
                kind=str(data.get("kind", "rectangle")),
                width=int(data.get("width", 200)),
                height=int(data.get("height", 140)),
                fill_color=None if fill is None else tuple(fill),  # type: ignore[arg-type]
                stroke_color=tuple(  # type: ignore[arg-type]
                    data.get("stroke_color", (255, 255, 255, 255))
                ),
                stroke_width=int(data.get("stroke_width", 0)),
                corner_radius=float(data.get("corner_radius", 0.0)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thuộc tính hình khối không hợp lệ: {exc}") from exc


def render_shape(properties: ShapeProperties) -> np.ndarray:
    """Render hình khối thành mảng RGBA uint8 với nền trong suốt."""
    width = properties.width
    height = properties.height
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        stroke = float(properties.stroke_width)
        inset = stroke / 2.0 if stroke > 0.0 else 0.0
        rect = QRectF(
            inset,
            inset,
            max(1.0, width - stroke),
            max(1.0, height - stroke),
        )
        path = QPainterPath()
        if properties.kind == "ellipse":
            path.addEllipse(rect)
        elif properties.kind == "rounded_rectangle":
            radius = min(
                properties.corner_radius,
                rect.width() / 2.0,
                rect.height() / 2.0,
            )
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)

        if properties.fill_color is not None:
            painter.setBrush(QColor(*properties.fill_color))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if stroke > 0.0:
            pen = QPen(QColor(*properties.stroke_color), stroke)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)
    finally:
        painter.end()
    return qimage_to_rgba(image)
