"""Chuyển đổi giữa TextRun và định dạng QTextCharFormat.

Dùng chung cho hộp thoại văn bản và trình soạn chữ ngay trên canvas. Cỡ chữ thật
được lưu trong thuộc tính người dùng vì QTextCharFormat chỉ hỗ trợ cỡ theo point.
"""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextFormat

from core.text_layer import MAX_FONT_SIZE, TextRun

RUN_PIXEL_SIZE = int(QTextFormat.Property.UserProperty) + 1
RUN_FONT_FAMILY = int(QTextFormat.Property.UserProperty) + 2


def format_from_run(run: TextRun, display_scale: float = 1.0) -> QTextCharFormat:
    """Tạo định dạng hiển thị cho một đoạn; ``display_scale`` dùng khi soạn trên canvas."""
    fmt = QTextCharFormat()
    fmt.setProperty(RUN_FONT_FAMILY, run.font_family)
    if run.font_family:
        fmt.setFontFamily(run.font_family)
    fmt.setFontPointSize(max(0.75, run.font_size * 0.75 * display_scale))
    fmt.setProperty(RUN_PIXEL_SIZE, int(run.font_size))
    fmt.setFontWeight(QFont.Weight.Bold if run.bold else QFont.Weight.Normal)
    fmt.setFontItalic(run.italic)
    fmt.setForeground(QColor(*run.color))
    return fmt


def run_from_format(
    fmt: QTextCharFormat,
    text: str,
    fallback: TextRun,
) -> TextRun:
    pixel = fmt.property(RUN_PIXEL_SIZE)
    if pixel is None:
        point = float(fmt.fontPointSize())
        size = int(round(point * 4 / 3)) if point > 0 else fallback.font_size
    else:
        try:
            size = int(pixel)
        except (TypeError, ValueError):
            size = fallback.font_size
    size = max(1, min(MAX_FONT_SIZE, size))

    if fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
        color = fmt.foreground().color()
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
    else:
        rgba = fallback.color

    family = fmt.property(RUN_FONT_FAMILY)
    if family is None:
        family = fmt.font().family() or fallback.font_family
    elif not isinstance(family, str):
        # PySide6 trả [] cho chuỗi rỗng lưu trong thuộc tính người dùng.
        family = ""

    return TextRun(
        text=text,
        font_family=str(family),
        font_size=size,
        color=rgba,
        bold=int(fmt.fontWeight()) >= int(QFont.Weight.Bold),
        italic=fmt.fontItalic(),
    )
