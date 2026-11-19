"""Kiểm thử gradient: ramp, tô pixel, tô mask, vùng chọn và Undo/Redo."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRectF

from core.document import Document
from core.gradient import GradientSettings, gradient_ramp
from core.selection import Selection
from core.shape_layer import ShapeProperties


def _document(width: int = 40, height: int = 30) -> tuple[Document, object]:
    document = Document(width, height, name="Gradient")
    layer = document.add_layer(
        name="Background", color=(255, 255, 255, 255), record=False
    )
    document.mark_clean()
    return document, layer


def _settings(
    start=(0, 0, 0, 255), end=(255, 255, 255, 255), gradient_type="linear"
) -> GradientSettings:
    return GradientSettings(
        gradient_type=gradient_type, start_color=start, end_color=end
    )


def test_gradient_settings_validate_and_clamp():
    settings = GradientSettings(gradient_type="RADIAL")
    assert settings.gradient_type == "radial"
    clamped = GradientSettings(
        start_color=(300, -4, 12, 999), end_color=(1, 2, 3, 4)
    )
    assert clamped.start_color == (255, 0, 12, 255)
    with pytest.raises(ValueError):
        GradientSettings(gradient_type="diagonal")
    with pytest.raises(ValueError):
        GradientSettings(start_color=(1, 2, 3))  # type: ignore[arg-type]


def test_linear_ramp_increases_and_clamps():
    ramp = gradient_ramp(5, 1, (0.0, 0.5), (5.0, 0.5))
    assert ramp.shape == (1, 5)
    assert ramp[0, 0] < ramp[0, 2] < ramp[0, 4]
    assert 0 < ramp[0, 0] < 0.2
    assert 0.8 < ramp[0, 4] < 1.0

    inside = gradient_ramp(9, 1, (3.0, 0.5), (5.0, 0.5))
    assert inside[0, 0] == 0.0
    assert inside[0, 8] == 1.0
    assert np.all((inside >= 0.0) & (inside <= 1.0))


def test_radial_ramp_grows_from_center():
    ramp = gradient_ramp(9, 9, (4.5, 4.5), (8.5, 4.5), "radial")
    assert ramp[4, 4] < 0.1
    assert ramp[4, 8] > 0.7
    assert ramp[0, 0] == 1.0
    zero = gradient_ramp(9, 9, (4.5, 4.5), (4.5, 4.5), "radial")
    assert not zero.any()


def test_gradient_fills_pixels_with_undo_and_redo():
    document, layer = _document(5, 1)
    session = document.begin_gradient(_settings(), (0.0, 0.5))
    assert session.update(5.0, 0.5) is True
    assert session.finish() is True

    pixels = layer.pixels
    assert pixels[0, 0, 0] < 40
    assert 118 <= pixels[0, 2, 0] <= 138
    assert pixels[0, 4, 0] > 220
    assert pixels[0, 0, 3] == 255
    assert document.modified

    document.undo()
    assert tuple(layer.pixels[0, 0]) == (255, 255, 255, 255)
    assert tuple(layer.pixels[0, 4]) == (255, 255, 255, 255)
    document.redo()
    assert layer.pixels[0, 4, 0] > 220


def test_gradient_respects_selection():
    document, layer = _document(40, 20)
    document.set_selection(
        Selection.from_rect(document.width, document.height, QRectF(0, 0, 20, 20)),
        "Chọn nửa trái",
    )
    session = document.begin_gradient(_settings(), (0.0, 10.0))
    session.update(40.0, 10.0)
    assert session.finish() is True

    assert layer.pixels[10, 1, 0] < 40
    assert layer.pixels[10, 19, 0] < 160
    assert tuple(layer.pixels[10, 35]) == (255, 255, 255, 255)


def test_radial_gradient_darkens_center_only():
    document, layer = _document(9, 9)
    session = document.begin_gradient(_settings(gradient_type="radial"), (4.5, 4.5))
    session.update(8.5, 4.5)
    assert session.finish() is True
    assert layer.pixels[4, 4, 0] < 60
    assert layer.pixels[0, 0, 0] > 200


def test_transparent_end_fades_alpha():
    document, layer = _document(5, 1)
    session = document.begin_gradient(
        _settings(start=(255, 0, 0, 255), end=(255, 0, 0, 0)), (0.0, 0.5)
    )
    session.update(5.0, 0.5)
    session.finish()
    assert layer.pixels[0, 0, 3] > 200
    assert layer.pixels[0, 4, 3] < 50
    assert layer.pixels[0, 0, 0] == 255
    assert layer.pixels[0, 4, 0] == 255


def test_gradient_on_mask_uses_luminance_and_undo():
    document, layer = _document()
    document.add_layer_mask(record=False)
    session = document.begin_gradient(_settings(), (0.0, 15.0), target="mask")
    session.update(40.0, 15.0)
    assert session.finish() is True

    assert layer.mask[15, 0] < 30
    assert layer.mask[15, 39] > 225
    document.undo()
    assert layer.mask[15, 0] == 255
    assert layer.mask[15, 39] == 255
    document.redo()
    assert layer.mask[15, 39] > 225


def test_gradient_mask_respects_selection():
    document, layer = _document(40, 20)
    document.add_layer_mask(record=False)
    document.set_selection(
        Selection.from_rect(document.width, document.height, QRectF(20, 0, 20, 20)),
        "Nửa phải",
    )
    session = document.begin_gradient(
        _settings(start=(0, 0, 0, 255), end=(0, 0, 0, 255)), (0.0, 10.0), target="mask"
    )
    session.update(40.0, 10.0)
    session.finish()
    assert layer.mask[10, 5] == 255
    assert layer.mask[10, 35] == 0


def test_click_without_drag_records_nothing():
    document, layer = _document()
    session = document.begin_gradient(_settings(), (10.0, 10.0))
    assert session.update(10.2, 10.1) is False
    assert session.finish() is False
    assert tuple(layer.pixels[10, 10]) == (255, 255, 255, 255)
    assert not document.history.can_undo
    assert not document.modified


def test_cancel_restores_pixels_and_history():
    document, layer = _document()
    session = document.begin_gradient(_settings(), (0.0, 15.0))
    session.update(40.0, 15.0)
    assert layer.pixels[15, 0, 0] < 30
    session.cancel()
    assert tuple(layer.pixels[15, 0]) == (255, 255, 255, 255)
    assert not document.history.can_undo
    assert not document.modified


def test_gradient_requires_layer_and_rejects_locked_or_missing_mask():
    document = Document(40, 30)
    with pytest.raises(ValueError):
        document.begin_gradient(_settings(), (0.0, 0.0))
    layer = document.add_layer(name="Layer", color=(255, 255, 255, 255), record=False)
    layer.locked = True
    with pytest.raises(ValueError, match="khoá"):
        document.begin_gradient(_settings(), (0.0, 0.0))
    layer.locked = False
    with pytest.raises(ValueError, match="chưa có mask"):
        document.begin_gradient(_settings(), (0.0, 0.0), target="mask")
    with pytest.raises(ValueError):
        document.begin_gradient(_settings(), (0.0, 0.0), target="unknown")
    with pytest.raises(TypeError):
        document.begin_gradient("linear", (0.0, 0.0))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        document.begin_gradient(_settings(), (0.0, float("nan")))


def test_gradient_on_shape_layer_rasterizes_and_undo_restores():
    document = Document(80, 60)
    document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    shape = document.add_shape_layer(
        ShapeProperties(kind="rectangle", width=60, height=40, fill_color=(0, 0, 0, 255)),
        x=10,
        y=10,
        record=False,
    )
    document.mark_clean()
    session = document.begin_gradient(_settings(), (10.0, 30.0))
    session.update(70.0, 30.0)
    assert session.finish() is True
    assert shape.kind == "pixel"
    assert shape.shape is None
    assert shape.pixels[10, 55, 0] > 200
    document.undo()
    assert shape.kind == "shape"
    assert shape.shape is not None
    assert tuple(shape.pixels[10, 55]) == (0, 0, 0, 255)
