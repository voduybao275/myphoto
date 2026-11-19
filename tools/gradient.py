"""Gradient Tool — kéo trên canvas để tô dải màu tuyến tính/hình tròn."""

from __future__ import annotations

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from core.gradient import GRADIENT_TYPES, GradientSettings
from tools.base import CanvasTool

_UNSET = object()

GRADIENT_PRESETS = ("fg_bg", "fg_transparent", "black_white", "white_black")


class GradientTool(CanvasTool):
    id = "gradient"
    name = "Gradient"
    shortcut = "G"
    hint = "Kéo để tô dải màu tuyến tính/hình tròn. Có thể tô lên layer mask."
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self) -> None:
        self.gradient_type = "linear"
        self.preset = "fg_bg"
        self.foreground: tuple[int, int, int, int] = (0, 0, 0, 255)
        self.background: tuple[int, int, int, int] = (255, 255, 255, 255)
        self.paint_mask = False
        self._session = None
        self._active = False
        self._moved = False

    # --------------------------------------------------------------- cấu hình
    def configure(
        self,
        *,
        gradient_type: str | None = None,
        preset: str | None = None,
        paint_mask: object = _UNSET,
    ) -> None:
        if gradient_type is not None:
            value = str(gradient_type).lower()
            if value not in GRADIENT_TYPES:
                raise ValueError(f"Kiểu gradient không hợp lệ: {gradient_type}")
            self.gradient_type = value
        if preset is not None:
            value = str(preset)
            if value not in GRADIENT_PRESETS:
                raise ValueError(f"Mẫu gradient không hợp lệ: {preset}")
            self.preset = value
        if paint_mask is not _UNSET:
            self.paint_mask = bool(paint_mask)

    def set_colors(
        self,
        foreground: tuple[int, int, int, int],
        background: tuple[int, int, int, int],
    ) -> None:
        self.foreground = tuple(int(channel) for channel in foreground)  # type: ignore[assignment]
        self.background = tuple(int(channel) for channel in background)  # type: ignore[assignment]

    def preset_colors(self) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        foreground = self.foreground
        if self.preset == "fg_transparent":
            return foreground, (foreground[0], foreground[1], foreground[2], 0)
        if self.preset == "black_white":
            return (0, 0, 0, 255), (255, 255, 255, 255)
        if self.preset == "white_black":
            return (255, 255, 255, 255), (0, 0, 0, 255)
        return foreground, self.background

    def options(self) -> dict[str, object]:
        return {
            "gradient_type": self.gradient_type,
            "preset": self.preset,
            "paint_mask": self.paint_mask,
            "colors": self.preset_colors(),
        }

    @property
    def paint_target(self) -> str:
        return "mask" if self.paint_mask else "pixels"

    # ------------------------------------------------------------ sự kiện chuột
    def mouse_press(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        settings = GradientSettings(
            gradient_type=self.gradient_type,
            start_color=self.preset_colors()[0],
            end_color=self.preset_colors()[1],
        )
        try:
            session = view.document.begin_gradient(
                settings,
                (image_pos.x(), image_pos.y()),
                target=self.paint_target,
            )
        except (ValueError, TypeError) as exc:
            view.status_message.emit(str(exc))
            return True
        self._session = session
        self._active = True
        self._moved = False
        return True

    def mouse_move(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active or self._session is None:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        if self._session.update(image_pos.x(), image_pos.y()):
            self._moved = True
        return True

    def mouse_release(self, view, event: QMouseEvent, image_pos: QPointF) -> bool:
        if not self._active:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        session = self._session
        target = self.paint_target
        self._active = False
        self._session = None
        if session is None:
            return True
        session.update(image_pos.x(), image_pos.y())
        if not session.has_direction:
            session.finish()
            view.status_message.emit(
                "Kéo chuột để tạo dải gradient (Esc để huỷ khi đang kéo)."
            )
            return True
        changed = session.finish()
        if not changed:
            view.status_message.emit("Gradient không tạo thay đổi nào.")
        elif target == "mask":
            view.status_message.emit(
                "Đã tô gradient lên layer mask (Ctrl+Z để hoàn tác)."
            )
        else:
            view.status_message.emit("Đã tô gradient (Ctrl+Z để hoàn tác).")
        return True

    def key_press(self, view, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._active:
            self.cancel(view)
            return True
        return False

    def reset(self, view) -> None:
        if self._session is not None:
            self._session.cancel()
        self._session = None
        self._active = False
        self._moved = False

    def cancel(self, view) -> None:
        if self._session is not None:
            self._session.cancel()
        self._session = None
        self._active = False
        self._moved = False
        view.status_message.emit("Đã huỷ gradient.")
