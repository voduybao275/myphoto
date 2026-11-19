"""Vùng chọn vector (rect/ellipse) và chuyển sang mask 8-bit.

QPainterPath là nguồn dữ liệu chính vì hỗ trợ cộng/trừ/giao chính xác và vẽ
đường kiến (marching ants) mượt ở mọi mức zoom. Khi cần thao tác pixel (layer
mask, crop) vùng chọn được raster hoá thành mảng uint8 0..255.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QTransform

SELECTION_MODES = ("replace", "add", "subtract", "intersect")
MAX_FEATHER_RADIUS = 250.0


def _document_path(width: int, height: int) -> QPainterPath:
    path = QPainterPath()
    path.addRect(QRectF(0.0, 0.0, float(width), float(height)))
    return path


def _box_blur_zero(channel: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Box blur một trục với biên bằng 0 (ngoài vùng chọn luôn trong suốt)."""
    if radius <= 0:
        return channel
    if axis == 1:
        padded = np.pad(channel, ((0, 0), (radius, radius)), mode="constant")
    else:
        padded = np.pad(channel, ((radius, radius), (0, 0)), mode="constant")
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


def feather_mask(mask: np.ndarray, feather: float) -> np.ndarray:
    """Làm mềm mask uint8 bằng 3 lượt box blur (xấp xỉ Gaussian)."""
    radius = int(round(float(feather) / 2.0))
    if radius <= 0:
        return mask.copy()
    pad = radius * 3
    work = np.pad(
        mask.astype(np.float32), ((pad, pad), (pad, pad)), mode="constant"
    )
    for _ in range(3):
        work = _box_blur_zero(work, radius, 1)
        work = _box_blur_zero(work, radius, 0)
    work = work[pad : pad + mask.shape[0], pad : pad + mask.shape[1]]
    return np.clip(np.rint(work), 0.0, 255.0).astype(np.uint8)


class Selection:
    """Vùng chọn trong toạ độ pixel của tài liệu."""

    def __init__(
        self,
        width: int,
        height: int,
        path: QPainterPath | None = None,
        *,
        feather: float = 0.0,
        antialias: bool = True,
    ) -> None:
        if width < 1 or height < 1:
            raise ValueError("Kích thước vùng chọn phải >= 1 px.")
        feather_value = float(feather)
        if not math.isfinite(feather_value):
            raise ValueError("Bán kính feather phải là số hữu hạn.")
        self.width = int(width)
        self.height = int(height)
        self.feather = float(min(max(feather_value, 0.0), MAX_FEATHER_RADIUS))
        self.antialias = bool(antialias)
        self.path = QPainterPath(path) if path is not None else QPainterPath()
        if not self.path.isEmpty():
            self.path = self.path.intersected(_document_path(self.width, self.height))
        self._bounds_cache: QRect | None = None
        self._path_bounds_cache: QRect | None = None
        self._path_bounds_ready = False

    # ------------------------------------------------------------- constructor
    @classmethod
    def empty(cls, width: int, height: int) -> "Selection":
        return cls(width, height)

    @classmethod
    def all(cls, width: int, height: int) -> "Selection":
        return cls(width, height, _document_path(width, height))

    @classmethod
    def from_rect(
        cls,
        width: int,
        height: int,
        rect: QRectF | QRect,
        *,
        feather: float = 0.0,
        antialias: bool = True,
    ) -> "Selection":
        area = QRectF(rect).normalized()
        path = QPainterPath()
        if area.width() > 0.0 and area.height() > 0.0:
            path.addRect(area)
        return cls(width, height, path, feather=feather, antialias=antialias)

    @classmethod
    def from_ellipse(
        cls,
        width: int,
        height: int,
        rect: QRectF | QRect,
        *,
        feather: float = 0.0,
        antialias: bool = True,
    ) -> "Selection":
        area = QRectF(rect).normalized()
        path = QPainterPath()
        if area.width() > 0.0 and area.height() > 0.0:
            path.addEllipse(area)
        return cls(width, height, path, feather=feather, antialias=antialias)

    @classmethod
    def from_path(
        cls,
        width: int,
        height: int,
        path: QPainterPath,
        *,
        feather: float = 0.0,
        antialias: bool = True,
    ) -> "Selection":
        """Tạo vùng chọn từ đường bao có sẵn (Lasso, Magic Wand, Quick Selection)."""
        if not isinstance(path, QPainterPath):
            raise TypeError("Đường bao vùng chọn phải là QPainterPath.")
        return cls(width, height, path, feather=feather, antialias=antialias)

    # ----------------------------------------------------------------- tuỳ chọn
    def with_feather(self, feather: float) -> "Selection":
        value = float(feather)
        if not math.isfinite(value):
            raise ValueError("Bán kính feather phải là số hữu hạn.")
        result = self.copy()
        result.feather = float(min(max(value, 0.0), MAX_FEATHER_RADIUS))
        result._bounds_cache = None
        return result

    def with_antialias(self, antialias: bool) -> "Selection":
        result = self.copy()
        result.antialias = bool(antialias)
        result._bounds_cache = None
        return result

    # ------------------------------------------------------------------ dữ liệu
    def copy(self) -> "Selection":
        return Selection(
            self.width,
            self.height,
            self.path,
            feather=self.feather,
            antialias=self.antialias,
        )

    @property
    def is_empty(self) -> bool:
        return self.path.isEmpty()

    def _path_pixel_bounds(self) -> QRect | None:
        """Biên pixel thật của đường bao (chưa mở rộng do feather)."""
        if self._path_bounds_ready:
            cached = self._path_bounds_cache
            if cached is None or cached.isNull():
                return None
            return QRect(cached)
        self._path_bounds_ready = True
        if self.path.isEmpty():
            self._path_bounds_cache = QRect()
            return None
        area = self.path.boundingRect()
        x0 = max(0, int(np.floor(area.left())))
        y0 = max(0, int(np.floor(area.top())))
        x1 = min(self.width, int(np.ceil(area.right())))
        y1 = min(self.height, int(np.ceil(area.bottom())))
        if x1 <= x0 or y1 <= y0:
            self._path_bounds_cache = QRect()
            return None
        width, height = x1 - x0, y1 - y0
        image = QImage(width, height, QImage.Format.Format_Grayscale8)
        image.fill(0)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.translate(-x0, -y0)
            painter.drawPath(self.path)
        finally:
            painter.end()
        raw = np.frombuffer(
            image.constBits(), dtype=np.uint8, count=image.sizeInBytes()
        )
        rows = raw.reshape((height, image.bytesPerLine()))[:, :width]
        ys, xs = np.nonzero(rows)
        if xs.size == 0:
            result = QRect()
        else:
            result = QRect(
                x0 + int(xs.min()),
                y0 + int(ys.min()),
                int(xs.max() - xs.min()) + 1,
                int(ys.max() - ys.min()) + 1,
            )
        self._path_bounds_cache = result
        return QRect(result) if not result.isNull() else None

    def bounds(self) -> QRect:
        if self.path.isEmpty():
            return QRect()
        if self._bounds_cache is not None:
            return QRect(self._bounds_cache)
        path_bounds = self._path_pixel_bounds()
        if path_bounds is None:
            return QRect()
        grow = 0
        if self.feather > 0.0:
            grow = int(math.ceil(self.feather * 1.5)) + 1
        x0 = max(0, path_bounds.left() - grow)
        y0 = max(0, path_bounds.top() - grow)
        x1 = min(self.width, path_bounds.right() + 1 + grow)
        y1 = min(self.height, path_bounds.bottom() + 1 + grow)
        result = QRect(x0, y0, max(0, x1 - x0), max(0, y1 - y0))
        self._bounds_cache = result
        return QRect(result)

    def translated(self, dx: float, dy: float) -> "Selection":
        path = QPainterPath(self.path)
        path.translate(float(dx), float(dy))
        return Selection(
            self.width,
            self.height,
            path,
            feather=self.feather,
            antialias=self.antialias,
        )

    def placed(
        self, width: int, height: int, dx: float = 0.0, dy: float = 0.0
    ) -> "Selection":
        """Dịch vùng chọn sang kích thước tài liệu mới (dùng cho Canvas Size)."""
        path = QPainterPath(self.path)
        if dx or dy:
            path.translate(float(dx), float(dy))
        return Selection(
            int(width),
            int(height),
            path,
            feather=self.feather,
            antialias=self.antialias,
        )

    def scaled(
        self,
        sx: float,
        sy: float,
        width: int | None = None,
        height: int | None = None,
    ) -> "Selection":
        new_width = int(width) if width is not None else max(1, round(self.width * sx))
        new_height = int(height) if height is not None else max(1, round(self.height * sy))
        if self.path.isEmpty():
            return Selection.empty(new_width, new_height)
        path = QTransform.fromScale(float(sx), float(sy)).map(self.path)
        return Selection(
            new_width,
            new_height,
            path,
            feather=self.feather,
            antialias=self.antialias,
        )

    def transformed(
        self, transform: QTransform, width: int, height: int
    ) -> "Selection":
        """Biến đổi đường bao rồi đặt vào kích thước tài liệu mới."""
        if self.path.isEmpty():
            return Selection.empty(width, height)
        return Selection(
            int(width),
            int(height),
            transform.map(self.path),
            feather=self.feather,
            antialias=self.antialias,
        )

    def rotated_clockwise(self) -> "Selection":
        return self.transformed(
            QTransform(0.0, 1.0, -1.0, 0.0, float(self.height), 0.0),
            self.height,
            self.width,
        )

    def rotated_counter_clockwise(self) -> "Selection":
        return self.transformed(
            QTransform(0.0, -1.0, 1.0, 0.0, 0.0, float(self.width)),
            self.height,
            self.width,
        )

    def rotated_180(self) -> "Selection":
        return self.transformed(
            QTransform(-1.0, 0.0, 0.0, -1.0, float(self.width), float(self.height)),
            self.width,
            self.height,
        )

    def flipped_horizontal(self) -> "Selection":
        return self.transformed(
            QTransform(-1.0, 0.0, 0.0, 1.0, float(self.width), 0.0),
            self.width,
            self.height,
        )

    def flipped_vertical(self) -> "Selection":
        return self.transformed(
            QTransform(1.0, 0.0, 0.0, -1.0, 0.0, float(self.height)),
            self.width,
            self.height,
        )

    def combine(self, other: "Selection", mode: str) -> "Selection":
        if mode not in SELECTION_MODES:
            raise ValueError(f"Kiểu kết hợp vùng chọn không hợp lệ: {mode}")
        if mode == "replace":
            return other.copy()
        # Vùng chọn kết quả dùng tuỳ chọn feather/anti-alias của lần kéo mới nhất.
        options = {"feather": other.feather, "antialias": other.antialias}
        if mode == "add":
            path = self.path.united(other.path)
            # united() giữ fill rule OddEven, khiến phần chồng lấn bị khoét rỗng.
            path.setFillRule(Qt.FillRule.WindingFill)
            return Selection(self.width, self.height, path, **options)
        if mode == "subtract":
            return Selection(
                self.width,
                self.height,
                self.path.subtracted(other.path),
                **options,
            )
        if self.path.isEmpty() or other.path.isEmpty():
            return Selection.empty(self.width, self.height)
        return Selection(
            self.width,
            self.height,
            self.path.intersected(other.path),
            **options,
        )

    def inverted(self) -> "Selection":
        if self.path.isEmpty():
            return Selection.all(self.width, self.height)
        return Selection(
            self.width,
            self.height,
            _document_path(self.width, self.height).subtracted(self.path),
            feather=self.feather,
            antialias=self.antialias,
        )

    def _rasterize(self, area: QRect, antialias: bool) -> np.ndarray:
        if area.width() < 1 or area.height() < 1:
            return np.zeros((0, 0), dtype=np.uint8)
        image = QImage(area.width(), area.height(), QImage.Format.Format_Grayscale8)
        image.fill(0)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.translate(-area.x(), -area.y())
            painter.drawPath(self.path)
        finally:
            painter.end()
        raw = np.frombuffer(
            image.constBits(), dtype=np.uint8, count=image.sizeInBytes()
        )
        rows = raw.reshape((area.height(), image.bytesPerLine()))[:, : area.width()]
        return rows.copy()

    def mask(self) -> np.ndarray:
        """Raster hoá thành mảng uint8 (cao, rộng), 0 = ngoài, 255 = trong.

        Feather làm mềm biên bằng Gaussian xấp xỉ; biên được phép mở rộng ra
        ngoài đường bao nhưng luôn cắt trong phạm vi tài liệu.
        """
        output = np.zeros((self.height, self.width), dtype=np.uint8)
        if self.path.isEmpty():
            return output
        path_bounds = self._path_pixel_bounds()
        if path_bounds is None:
            return output
        if self.feather <= 0.0:
            region = self._rasterize(path_bounds, self.antialias)
            output[
                path_bounds.top() : path_bounds.bottom() + 1,
                path_bounds.left() : path_bounds.right() + 1,
            ] = region
            return output

        radius = int(round(self.feather / 2.0))
        grow = max(
            radius * 3 + 1, int(math.ceil(self.feather * 1.5)) + 1
        )
        x0 = max(0, path_bounds.left() - grow)
        y0 = max(0, path_bounds.top() - grow)
        x1 = min(self.width, path_bounds.right() + 1 + grow)
        y1 = min(self.height, path_bounds.bottom() + 1 + grow)
        area = QRect(x0, y0, x1 - x0, y1 - y0)
        region = self._rasterize(area, self.antialias)
        if radius > 0:
            region = feather_mask(region, self.feather)
        output[y0:y1, x0:x1] = region
        return output

    # ------------------------------------------------------------------ so sánh
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Selection):
            return NotImplemented
        if (self.width, self.height) != (other.width, other.height):
            return False
        if self.feather != other.feather or self.antialias != other.antialias:
            return False
        if self.path.isEmpty() and other.path.isEmpty():
            return True
        return self.path == other.path

    def __repr__(self) -> str:  # pragma: no cover - chẩn đoán
        state = "empty" if self.is_empty else f"bounds={self.bounds()}"
        options = ""
        if self.feather > 0:
            options += f" feather={self.feather:g}"
        if not self.antialias:
            options += " antialias=off"
        return f"<Selection {self.width}x{self.height} {state}{options}>"
