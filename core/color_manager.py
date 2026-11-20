"""Màu foreground/background dùng chung cho các công cụ."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


DEFAULT_FOREGROUND = "#ffffff"
DEFAULT_BACKGROUND = "#000000"


class ColorManager(QObject):
    colors_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._foreground = QColor(DEFAULT_FOREGROUND)
        self._background = QColor(DEFAULT_BACKGROUND)

    @property
    def foreground(self) -> QColor:
        return QColor(self._foreground)

    @property
    def background(self) -> QColor:
        return QColor(self._background)

    def set_foreground(self, color: QColor) -> None:
        if not color.isValid() or color == self._foreground:
            return
        self._foreground = QColor(color)
        self.colors_changed.emit()

    def set_background(self, color: QColor) -> None:
        if not color.isValid() or color == self._background:
            return
        self._background = QColor(color)
        self.colors_changed.emit()

    def swap(self) -> None:
        self._foreground, self._background = self._background, self._foreground
        self.colors_changed.emit()

    def reset_defaults(self) -> None:
        foreground = QColor(DEFAULT_FOREGROUND)
        background = QColor(DEFAULT_BACKGROUND)
        if foreground == self._foreground and background == self._background:
            return
        self._foreground = foreground
        self._background = background
        self.colors_changed.emit()

    @staticmethod
    def _to_rgba(color: QColor) -> tuple[int, int, int, int]:
        return (color.red(), color.green(), color.blue(), color.alpha())

    def foreground_rgba(self) -> tuple[int, int, int, int]:
        return self._to_rgba(self._foreground)

    def background_rgba(self) -> tuple[int, int, int, int]:
        return self._to_rgba(self._background)
