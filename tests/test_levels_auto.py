"""Kiểm thử Auto Levels và kéo tay nắm đen/trắng trên histogram (phần 17)."""

from __future__ import annotations

import numpy as np
import pytest

from PySide6.QtCore import QPointF, QRectF, Qt

from core.adjustment_layer import (
    AUTO_LEVELS_CLIP_PERCENT,
    AdjustmentProperties,
    apply_adjustment_rgba,
    compute_auto_levels,
)
from ui.dialogs import AdjustmentLayerDialog, HistogramView


def _gradient(width=256, height=8, low=0, high=255) -> np.ndarray:
    array = np.zeros((height, width, 4), dtype=np.uint8)
    values = np.linspace(low, high, width).astype(np.uint8)
    array[..., 0] = values[None, :]
    array[..., 1] = values[None, :]
    array[..., 2] = values[None, :]
    array[..., 3] = 255
    return array


# ------------------------------------------------------------------- core
def test_auto_levels_full_gradient_and_zero_clip():
    source = _gradient()
    black, white = compute_auto_levels(source)
    assert (black, white) == (1, 254)
    assert compute_auto_levels(source, 0.0) == (0, 255)
    assert AUTO_LEVELS_CLIP_PERCENT == 0.5


def test_auto_levels_ignores_transparent_pixels():
    source = _gradient(width=200, height=10, low=50, high=150)
    source[0, 0] = (0, 0, 0, 0)
    source[0, 199] = (255, 255, 255, 0)
    black, white = compute_auto_levels(source)
    assert 50 <= black <= 52
    assert 148 <= white <= 150


def test_auto_levels_flat_and_empty_images_are_identity():
    flat = np.full((6, 6, 4), 90, dtype=np.uint8)
    flat[..., 3] = 255
    assert compute_auto_levels(flat) == (0, 255)
    transparent = np.zeros((4, 4, 4), dtype=np.uint8)
    assert compute_auto_levels(transparent) == (0, 255)


def test_auto_levels_validation():
    with pytest.raises(ValueError):
        compute_auto_levels(np.zeros((4, 4), dtype=np.uint8))
    with pytest.raises(ValueError):
        compute_auto_levels(np.zeros((4, 4, 4), dtype=np.float32))
    source = _gradient()
    with pytest.raises(ValueError):
        compute_auto_levels(source, -1.0)
    with pytest.raises(ValueError):
        compute_auto_levels(source, 50.0)
    with pytest.raises(ValueError):
        compute_auto_levels(source, float("nan"))


def test_auto_levels_stretches_visible_range():
    source = _gradient(width=200, height=6, low=40, high=210)
    black, white = compute_auto_levels(source)
    adjusted = apply_adjustment_rgba(
        source,
        AdjustmentProperties(
            kind="levels", levels_black=black, levels_white=white
        ),
    )
    luma = adjusted[..., 0][adjusted[..., 3] > 0]
    assert int(luma.min()) == 0
    assert int(luma.max()) == 255


# --------------------------------------------------------------------- UI
def test_levels_dialog_auto_button_and_histogram_sync(qapp):
    source = _gradient(width=200, height=40, low=40, high=210)
    dialog = AdjustmentLayerDialog(
        AdjustmentProperties(kind="levels"), preview=source
    )
    assert dialog.levels_histogram.black() == 0
    assert dialog.levels_histogram.white() == 255

    dialog.auto_levels_button.click()
    properties = dialog.properties
    assert properties.levels_black == 40
    assert properties.levels_white == 209
    assert dialog.levels_histogram.black() == 40
    assert dialog.levels_histogram.white() == 209
    assert "Auto Levels 40..209" in dialog.info_label.text()

    dialog.levels_black_field.setValue(55)
    assert dialog.levels_histogram.black() == 55
    assert "Auto Levels" not in dialog.info_label.text()
    dialog.close()


class _MouseEvent:
    """Sự kiện chuột tối giản, hoạt động giống nhau trên Qt 5 và Qt 6."""

    def __init__(self, x: float, y: float) -> None:
        self._position = QPointF(x, y)

    def position(self) -> QPointF:
        return self._position

    def localPos(self) -> QPointF:
        return self._position

    def pos(self) -> QPointF:
        return self._position

    def button(self):
        return Qt.MouseButton.LeftButton


def _drag(view: HistogramView, start: tuple[float, float], end: tuple[float, float]):
    view.mousePressEvent(_MouseEvent(*start))
    view.mouseMoveEvent(_MouseEvent(*end))
    view.mouseReleaseEvent(_MouseEvent(*end))


def test_histogram_handles_drag_updates_range(qapp):
    view = HistogramView(interactive=True)
    view.resize(300, 130)
    view.set_values(np.ones(256))
    view.set_range(0, 255)
    changes: list[tuple[int, int]] = []
    view.rangeChanged.connect(lambda black, white: changes.append((black, white)))
    view.show()
    qapp.processEvents()

    rect = QRectF(view.rect().adjusted(1, 1, -1, -1))
    strip_y = rect.bottom() - 4
    black_x = rect.left() + rect.width() * 60 / 255
    _drag(view, (rect.left() + 1, strip_y), (black_x, strip_y))
    assert 57 <= view.black() <= 63
    assert changes and changes[-1][0] == view.black()

    white_x = rect.left() + rect.width() * 210 / 255
    _drag(view, (rect.right(), strip_y), (white_x, strip_y))
    assert 207 <= view.white() <= 213
    assert view.black() < view.white()

    view._drag_handle = "black"
    view._apply_handle_value(255)
    view._drag_handle = "white"
    view._apply_handle_value(0)
    assert view.black() < view.white()
    view.close()


def test_histogram_handles_ignore_clicks_away_from_strip(qapp):
    view = HistogramView(interactive=True)
    view.resize(300, 130)
    view.set_values(np.ones(256))
    view.set_range(10, 240)
    view.show()
    qapp.processEvents()
    rect = QRectF(view.rect().adjusted(1, 1, -1, -1))
    view.mousePressEvent(
        _MouseEvent(rect.left() + rect.width() * 0.5, rect.top() + 8)
    )
    assert view._drag_handle == ""
    assert (view.black(), view.white()) == (10, 240)
    view.close()


def test_levels_dialog_histogram_drag_updates_fields(qapp):
    source = _gradient(width=200, height=40, low=20, high=230)
    dialog = AdjustmentLayerDialog(
        AdjustmentProperties(kind="levels", levels_black=20, levels_white=230),
        preview=source,
    )
    dialog.show()
    qapp.processEvents()
    dialog.levels_histogram._drag_handle = "black"
    dialog.levels_histogram._apply_handle_value(80)
    dialog.levels_histogram._drag_handle = ""
    properties = dialog.properties
    assert properties.levels_black == 80
    assert properties.levels_white == 230
    assert dialog.levels_histogram.black() == 80
    assert "80" in dialog.info_label.text()
    dialog.close()
