"""Bộ icon vector được vẽ bằng QPainter (không phụ thuộc file ảnh bản quyền).

Mỗi icon được thiết kế trên lưới 24x24 và render ở nhiều kích thước để hiển thị
sắc nét trên màn hình High-DPI. Màu icon lấy theo theme hiện hành.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from ui.theme import current_theme

_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64)
_pixmap_cache: dict[tuple[str, int, str], QPixmap] = {}
_icon_cache: dict[tuple[str, str], QIcon] = {}
_app_icon: QIcon | None = None


def _pen(color: QColor, width: float = 1.7) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_move(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.5))
    painter.drawLine(QPointF(12, 4.0), QPointF(12, 20.0))
    painter.drawLine(QPointF(4.0, 12), QPointF(20.0, 12))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([QPointF(12, 1.6), QPointF(8.8, 5.4), QPointF(15.2, 5.4)]))
    painter.drawPolygon(
        QPolygonF([QPointF(12, 22.4), QPointF(8.8, 18.6), QPointF(15.2, 18.6)])
    )
    painter.drawPolygon(QPolygonF([QPointF(1.6, 12), QPointF(5.4, 8.8), QPointF(5.4, 15.2)]))
    painter.drawPolygon(
        QPolygonF([QPointF(22.4, 12), QPointF(18.6, 8.8), QPointF(18.6, 15.2)])
    )


def _draw_hand(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(7.4, 10.2, 9.2, 9.4), 3.0, 3.0)
    for x in (9.0, 11.1, 13.2, 15.2):
        painter.drawLine(QPointF(x, 11.4), QPointF(x, 6.0))
    painter.drawLine(QPointF(7.6, 13.0), QPointF(5.0, 16.4))


def _draw_zoom(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(10.4, 10.4), 6.0, 6.0)
    painter.drawLine(QPointF(15.0, 15.0), QPointF(20.2, 20.2))
    painter.setPen(_pen(color, 1.5))
    painter.drawLine(QPointF(7.6, 10.4), QPointF(13.2, 10.4))
    painter.drawLine(QPointF(10.4, 7.6), QPointF(10.4, 13.2))


def _draw_text(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(5.0, 4.8), QPointF(19.0, 4.8))
    painter.drawLine(QPointF(12.0, 4.8), QPointF(12.0, 19.4))
    painter.drawLine(QPointF(8.4, 19.4), QPointF(15.6, 19.4))


def _draw_rect_select(painter: QPainter, color: QColor) -> None:
    pen = _pen(color, 1.5)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([2.4, 1.8])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(4.0, 5.0, 16.0, 14.0))


def _draw_ellipse_select(painter: QPainter, color: QColor) -> None:
    pen = _pen(color, 1.5)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([2.4, 1.8])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(4.0, 5.0, 16.0, 14.0))


def _draw_lasso(painter: QPainter, color: QColor) -> None:
    pen = _pen(color, 1.5)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([2.4, 1.8])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(9.0, 5.2)
    path.cubicTo(4.0, 6.4, 3.0, 12.2, 7.2, 15.6)
    path.cubicTo(11.0, 18.7, 19.0, 17.6, 19.6, 12.0)
    path.cubicTo(20.1, 7.4, 15.4, 4.4, 11.6, 5.8)
    painter.drawPath(path)
    painter.setPen(_pen(color, 1.6))
    painter.drawLine(QPointF(11.4, 6.0), QPointF(15.4, 19.4))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(15.6, 19.9), 1.5, 1.5)


def _draw_magic_wand(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.9))
    painter.drawLine(QPointF(7.2, 19.4), QPointF(15.4, 8.2))
    painter.setPen(_pen(color, 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(9.0, 16.8), QPointF(11.6, 17.6))
    painter.setPen(_pen(color, 1.5))
    for cx, cy, length in ((17.6, 5.0, 2.2), (20.4, 9.4, 1.6), (13.4, 4.2, 1.5)):
        painter.drawLine(
            QPointF(cx - length, cy), QPointF(cx + length, cy)
        )
        painter.drawLine(
            QPointF(cx, cy - length), QPointF(cx, cy + length)
        )


def _draw_quick_select(painter: QPainter, color: QColor) -> None:
    pen = _pen(color, 1.5)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([2.2, 1.8])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(4.0, 5.0, 15.0, 13.0))
    painter.setPen(_pen(color, 1.6))
    painter.drawLine(QPointF(12.0, 9.4), QPointF(12.0, 16.2))
    painter.drawLine(QPointF(8.6, 12.8), QPointF(15.4, 12.8))


def _draw_crop(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    first = QPainterPath()
    first.moveTo(7.0, 3.0)
    first.lineTo(7.0, 17.0)
    first.lineTo(21.0, 17.0)
    painter.drawPath(first)
    second = QPainterPath()
    second.moveTo(3.0, 7.0)
    second.lineTo(17.0, 7.0)
    second.lineTo(17.0, 21.0)
    painter.drawPath(second)


def _draw_shape(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(3.6, 4.8, 12.6, 11.6), 1.8, 1.8)
    painter.drawEllipse(QRectF(10.4, 8.8, 10.0, 10.0))


def _draw_brush(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 2.2))
    painter.drawLine(QPointF(18.6, 5.2), QPointF(11.8, 12.0))
    painter.setPen(_pen(color, 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(13.4, 10.4), QPointF(16.0, 13.0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF([QPointF(11.9, 12.1), QPointF(6.4, 17.0), QPointF(10.9, 17.6)])
    )


def _draw_eraser(painter: QPainter, color: QColor) -> None:
    painter.save()
    painter.translate(11.4, 11.4)
    painter.rotate(-28.0)
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(-7.2, -4.6, 14.4, 9.2), 2.2, 2.2)
    painter.restore()
    painter.setPen(_pen(color, 1.6))
    painter.drawLine(QPointF(4.8, 20.2), QPointF(19.2, 20.2))


def _draw_gradient(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(3.8, 4.8, 16.4, 14.4), 2.2, 2.2)
    start = QColor(color)
    start.setAlpha(240)
    end = QColor(color)
    end.setAlpha(20)
    gradient = QLinearGradient(5.2, 12.0, 18.8, 12.0)
    gradient.setColorAt(0.0, start)
    gradient.setColorAt(1.0, end)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(5.4, 6.4, 13.2, 11.2), 1.4, 1.4)


def _draw_eye(painter: QPainter, color: QColor, off: bool = False) -> None:
    painter.setPen(_pen(color, 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(2.6, 12.0)
    path.quadTo(12.0, 4.6, 21.4, 12.0)
    path.quadTo(12.0, 19.4, 2.6, 12.0)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawEllipse(QPointF(12.0, 12.0), 2.9, 2.9)
    if off:
        painter.setPen(_pen(color, 1.9))
        painter.drawLine(QPointF(4.4, 19.6), QPointF(19.6, 4.4))


def _draw_layer_new(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(4.0, 4.0, 12.0, 12.0), 2.4, 2.4)
    painter.drawLine(QPointF(19.2, 14.2), QPointF(19.2, 21.0))
    painter.drawLine(QPointF(15.8, 17.6), QPointF(22.6, 17.6))


def _draw_layer_duplicate(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(4.0, 7.4, 11.2, 11.2), 2.2, 2.2)
    painter.drawRoundedRect(QRectF(8.8, 4.0, 11.2, 11.2), 2.2, 2.2)


def _draw_layer_delete(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(4.8, 7.0), QPointF(19.2, 7.0))
    painter.drawLine(QPointF(9.6, 7.0), QPointF(9.6, 4.6))
    painter.drawLine(QPointF(9.6, 4.6), QPointF(14.4, 4.6))
    painter.drawLine(QPointF(14.4, 4.6), QPointF(14.4, 7.0))
    painter.drawRoundedRect(QRectF(6.4, 7.0, 11.2, 13.0), 1.6, 1.6)
    painter.drawLine(QPointF(10.2, 10.4), QPointF(10.2, 16.8))
    painter.drawLine(QPointF(13.8, 10.4), QPointF(13.8, 16.8))


def _draw_merge_down(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(12.0, 3.6), QPointF(12.0, 14.6))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([QPointF(12.0, 17.6), QPointF(8.6, 13.2), QPointF(15.4, 13.2)]))
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(4.8, 16.2)
    path.lineTo(4.8, 20.4)
    path.lineTo(19.2, 20.4)
    path.lineTo(19.2, 16.2)
    painter.drawPath(path)


def _draw_folder(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(3.2, 7.2)
    path.lineTo(9.8, 7.2)
    path.lineTo(11.6, 9.4)
    path.lineTo(20.8, 9.4)
    path.lineTo(20.8, 19.0)
    path.lineTo(3.2, 19.0)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(3.2, 11.0), QPointF(20.8, 11.0))


def _draw_clipping(painter: QPainter, color: QColor) -> None:
    """Mũi tên gập xuống layer nền, giống ký hiệu clipping của Photoshop."""
    painter.setPen(_pen(color, 1.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(6.4, 4.2)
    path.lineTo(6.4, 13.2)
    path.lineTo(17.4, 13.2)
    path.lineTo(17.4, 16.4)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF([QPointF(17.4, 20.6), QPointF(14.2, 16.0), QPointF(20.6, 16.0)])
    )


def _draw_link(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(3.2, 8.2, 10.0, 7.6), 3.8, 3.8)
    painter.drawRoundedRect(QRectF(10.8, 8.2, 10.0, 7.6), 3.8, 3.8)


def _draw_flip_h(painter: QPainter, color: QColor) -> None:
    pen = _pen(color, 1.4)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.drawLine(QPointF(12.0, 3.4), QPointF(12.0, 20.6))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF([QPointF(9.2, 6.0), QPointF(4.0, 12.0), QPointF(9.2, 18.0)])
    )
    painter.drawPolygon(
        QPolygonF([QPointF(14.8, 6.0), QPointF(20.0, 12.0), QPointF(14.8, 18.0)])
    )


def _draw_flip_v(painter: QPainter, color: QColor) -> None:
    pen = _pen(color, 1.4)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.drawLine(QPointF(3.4, 12.0), QPointF(20.6, 12.0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF([QPointF(6.0, 9.2), QPointF(12.0, 4.0), QPointF(18.0, 9.2)])
    )
    painter.drawPolygon(
        QPolygonF([QPointF(6.0, 14.8), QPointF(12.0, 20.0), QPointF(18.0, 14.8)])
    )


def _draw_reset(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(4.5, 4.5, 15.0, 15.0), 40 * 16, 280 * 16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF([QPointF(17.8, 3.4), QPointF(18.6, 9.2), QPointF(13.2, 7.0)])
    )


def _draw_close(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.8))
    painter.drawLine(QPointF(6.0, 6.0), QPointF(18.0, 18.0))
    painter.drawLine(QPointF(18.0, 6.0), QPointF(6.0, 18.0))


def _draw_swap(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.5))
    path = QPainterPath()
    path.moveTo(6.0, 7.5)
    path.quadTo(12.0, 3.6, 18.0, 7.5)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([QPointF(18.6, 8.4), QPointF(13.8, 8.6), QPointF(17.2, 4.4)]))
    painter.setPen(_pen(color, 1.5))
    path = QPainterPath()
    path.moveTo(18.0, 16.5)
    path.quadTo(12.0, 20.4, 6.0, 16.5)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(QPolygonF([QPointF(5.4, 15.6), QPointF(10.2, 15.4), QPointF(6.8, 19.6)]))


def _draw_lock(painter: QPainter, color: QColor, open_: bool = False) -> None:
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    if open_:
        path.moveTo(8.4, 11.0)
        path.lineTo(8.4, 7.6)
        path.arcTo(QRectF(8.4, 3.6, 7.2, 8.0), 180.0, -180.0)
        path.lineTo(15.6, 5.4)
    else:
        path.moveTo(8.4, 11.0)
        path.lineTo(8.4, 7.6)
        path.arcTo(QRectF(8.4, 3.6, 7.2, 8.0), 180.0, -180.0)
        path.lineTo(15.6, 11.0)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(5.6, 11.0, 12.8, 9.6), 2.0, 2.0)


def _draw_eyedropper(painter: QPainter, color: QColor) -> None:
    painter.setPen(_pen(color, 1.8))
    painter.drawLine(QPointF(5.2, 18.8), QPointF(13.6, 10.4))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    path = QPainterPath()
    path.moveTo(12.4, 8.0)
    path.lineTo(16.0, 11.6)
    path.lineTo(19.6, 8.0)
    path.arcTo(QRectF(14.4, 2.8, 5.2, 5.2), 0.0, 180.0)
    path.closeSubpath()
    painter.drawPath(path)
    painter.setPen(_pen(color, 1.4))
    painter.drawLine(QPointF(10.8, 9.6), QPointF(14.4, 13.2))
    painter.drawLine(QPointF(4.4, 20.2), QPointF(3.6, 21.0))


def _draw_app(painter: QPainter, color: QColor) -> None:
    gradient = QLinearGradient(0, 0, 24, 24)
    gradient.setColorAt(0.0, QColor("#343a44"))
    gradient.setColorAt(1.0, QColor("#13151a"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0.5, 0.5, 23.0, 23.0), 5.4, 5.4)

    accent = QColor("#e0a052")
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(accent, 1.5))
    painter.drawEllipse(QPointF(12.0, 12.0), 6.6, 6.6)

    painter.setPen(_pen(accent, 1.3))
    for index in range(6):
        angle = math.radians(index * 60 + 15)
        inner = 2.4
        outer = 6.2
        painter.drawLine(
            QPointF(12 + inner * math.cos(angle), 12 + inner * math.sin(angle)),
            QPointF(12 + outer * math.cos(angle), 12 + outer * math.sin(angle)),
        )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#f2c384"))
    painter.drawEllipse(QPointF(12.0, 12.0), 1.35, 1.35)
    painter.setBrush(accent)
    painter.drawEllipse(QPointF(18.4, 18.4), 1.0, 1.0)


_DRAWERS: dict[str, Callable[[QPainter, QColor], None]] = {
    "move": _draw_move,
    "rect_select": _draw_rect_select,
    "ellipse_select": _draw_ellipse_select,
    "lasso": _draw_lasso,
    "magic_wand": _draw_magic_wand,
    "quick_select": _draw_quick_select,
    "crop": _draw_crop,
    "text": _draw_text,
    "shape": _draw_shape,
    "brush": _draw_brush,
    "eraser": _draw_eraser,
    "gradient": _draw_gradient,
    "hand": _draw_hand,
    "zoom": _draw_zoom,
    "eye": lambda p, c: _draw_eye(p, c, off=False),
    "eye_off": lambda p, c: _draw_eye(p, c, off=True),
    "layer_new": _draw_layer_new,
    "layer_duplicate": _draw_layer_duplicate,
    "layer_delete": _draw_layer_delete,
    "merge_down": _draw_merge_down,
    "folder": _draw_folder,
    "clipping": _draw_clipping,
    "link": _draw_link,
    "flip_h": _draw_flip_h,
    "flip_v": _draw_flip_v,
    "reset": _draw_reset,
    "close": _draw_close,
    "swap": _draw_swap,
    "lock": lambda p, c: _draw_lock(p, c, open_=False),
    "lock_open": lambda p, c: _draw_lock(p, c, open_=True),
    "eyedropper": _draw_eyedropper,
    "app": _draw_app,
}


def pixmap(name: str, size: int = 24, color: QColor | str | None = None) -> QPixmap:
    theme = current_theme()
    resolved = QColor(color) if color is not None else QColor(theme.icon)
    key = (name, int(size), resolved.name(QColor.NameFormat.HexArgb))
    cached = _pixmap_cache.get(key)
    if cached is not None:
        return cached
    drawer = _DRAWERS.get(name)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    if drawer is not None:
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(size / 24.0, size / 24.0)
        drawer(painter, resolved)
        painter.end()
    _pixmap_cache[key] = result
    return result


def icon(name: str, color: QColor | str | None = None) -> QIcon:
    theme = current_theme()
    resolved = QColor(color) if color is not None else QColor(theme.icon)
    key = (name, resolved.name(QColor.NameFormat.HexArgb))
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    for size in _ICON_SIZES:
        result.addPixmap(pixmap(name, size, resolved))
    _icon_cache[key] = result
    return result


def clear_cache() -> None:
    _pixmap_cache.clear()
    _icon_cache.clear()


def app_icon() -> QIcon:
    global _app_icon
    if _app_icon is None:
        _app_icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            _app_icon.addPixmap(pixmap("app", size, QColor("#e0a052")))
    return _app_icon
