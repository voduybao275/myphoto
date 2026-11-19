"""Kiểm thử cọ vẽ, tẩy và vẽ lên layer mask."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRectF

from core.document import Document
from core.paint import (
    MAX_BRUSH_SIZE,
    BrushSettings,
    color_luminance,
    dot_points,
    erase_pixels,
    paint_mask_values,
    paint_pixels,
    stamp_coverage,
)
from core.selection import Selection
from core.shape_layer import ShapeProperties


def _document(width: int = 80, height: int = 60) -> tuple[Document, object]:
    document = Document(width, height, name="Brush")
    layer = document.add_layer(
        name="Background", color=(255, 255, 255, 255), record=False
    )
    document.mark_clean()
    return document, layer


def test_brush_settings_clamp_values():
    settings = BrushSettings(size=99999, hardness=2.0, opacity=-1.0, color=(300, -5, 12, 255))
    assert settings.size == MAX_BRUSH_SIZE
    assert settings.hardness == 1.0
    assert settings.opacity == 0.0
    assert settings.color == (255, 0, 12, 255)
    assert BrushSettings(size=0).size == 1
    with pytest.raises(ValueError):
        BrushSettings(color=(1, 2, 3))  # type: ignore[arg-type]


def test_stamp_coverage_hard_center_and_outside():
    coverage = np.zeros((40, 40), dtype=np.uint8)
    stamp_coverage(coverage, 20.0, 20.0, 8.0, 1.0)
    assert coverage[20, 20] == 255
    assert coverage[20, 29] == 0
    assert coverage[0, 0] == 0
    coverage = np.zeros((40, 40), dtype=np.uint8)
    assert stamp_coverage(coverage, -20.0, -20.0, 4.0, 1.0) is None


def test_soft_brush_has_falloff():
    coverage = np.zeros((40, 40), dtype=np.uint8)
    stamp_coverage(coverage, 20.0, 20.0, 12.0, 0.0)
    assert coverage[20, 20] >= 250
    assert 0 < coverage[20, 28] < coverage[20, 20]


def test_stamp_coverage_respects_strength():
    coverage = np.zeros((20, 20), dtype=np.uint8)
    strength = np.zeros((20, 20), dtype=np.uint8)
    strength[:, 10:] = 255
    stamp_coverage(coverage, 10.0, 10.0, 6.0, 1.0, strength=strength)
    assert coverage[10, 12] == 255
    assert coverage[10, 8] == 0


def test_dot_points_cover_segment():
    points = dot_points((0.0, 0.0), (10.0, 0.0), 3.0)
    assert points[-1] == (10.0, 0.0)
    xs = [0.0] + [point[0] for point in points]
    assert all(second - first <= 3.0 + 1e-6 for first, second in zip(xs, xs[1:]))
    assert dot_points((5.0, 5.0), (5.0, 5.0), 2.0) == []


def test_paint_pixels_blends_with_straight_alpha():
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    coverage = np.full((4, 4), 128, dtype=np.uint8)
    paint_pixels(pixels, coverage, (255, 0, 0, 255))
    assert tuple(pixels[0, 0, :3]) == (255, 0, 0)
    assert 120 <= pixels[0, 0, 3] <= 135


def test_paint_pixels_semi_transparent_color():
    pixels = np.zeros((2, 2, 4), dtype=np.uint8)
    coverage = np.full((2, 2), 255, dtype=np.uint8)
    paint_pixels(pixels, coverage, (0, 0, 255, 128))
    assert 125 <= pixels[1, 1, 3] <= 130
    assert tuple(pixels[1, 1, :3]) == (0, 0, 255)


def test_erase_pixels_reduces_alpha_only():
    pixels = np.full((2, 2, 4), 255, dtype=np.uint8)
    coverage = np.zeros((2, 2), dtype=np.uint8)
    coverage[0, 0] = 255
    erase_pixels(pixels, coverage)
    assert pixels[0, 0, 3] == 0
    assert tuple(pixels[0, 0, :3]) == (255, 255, 255)
    assert pixels[1, 1, 3] == 255


def test_paint_mask_values_interpolates_to_target():
    mask = np.full((2, 2), 255, dtype=np.uint8)
    coverage = np.zeros((2, 2), dtype=np.uint8)
    coverage[0, 0] = 255
    coverage[0, 1] = 128
    paint_mask_values(mask, coverage, 0)
    assert mask[0, 0] == 0
    assert 120 <= mask[0, 1] <= 135
    assert mask[1, 1] == 255


def test_color_luminance():
    assert color_luminance((0, 0, 0, 255)) == 0
    assert color_luminance((255, 255, 255, 255)) == 255
    assert color_luminance((255, 0, 0, 255)) == 76


def test_stroke_paints_layer_and_undo_redo():
    document, layer = _document()
    session = document.begin_brush_stroke(
        BrushSettings(size=16, hardness=1.0, color=(20, 140, 220, 255))
    )
    session.stroke_to(10.0, 10.0)
    session.stroke_to(60.0, 40.0)
    assert session.finish() is True
    assert tuple(layer.pixels[10, 10]) == (20, 140, 220, 255)
    assert tuple(layer.pixels[40, 60]) == (20, 140, 220, 255)
    assert tuple(layer.pixels[59, 1]) == (255, 255, 255, 255)
    assert document.history.can_undo

    assert document.undo()
    assert tuple(layer.pixels[10, 10]) == (255, 255, 255, 255)
    assert document.redo()
    assert tuple(layer.pixels[10, 10]) == (20, 140, 220, 255)


def test_stroke_opacity_does_not_accumulate_within_stroke():
    document, layer = _document()
    session = document.begin_brush_stroke(
        BrushSettings(size=10, hardness=1.0, opacity=0.5, color=(255, 0, 0, 255))
    )
    session.stroke_to(20.0, 20.0)
    session.stroke_to(21.0, 20.0)
    session.stroke_to(20.0, 21.0)
    session.finish()
    red, green, _blue, alpha = layer.pixels[20, 20]
    assert alpha == 255
    assert red >= 250
    assert 118 <= green <= 138


def test_stroke_respects_selection():
    document, layer = _document(60, 40)
    document.set_selection(
        Selection.from_rect(document.width, document.height, QRectF(10, 10, 20, 20)),
        "Chọn vùng",
    )
    session = document.begin_brush_stroke(
        BrushSettings(size=8, hardness=1.0, color=(0, 0, 0, 255))
    )
    session.stroke_to(45.0, 30.0)
    session.stroke_to(11.0, 11.0)
    session.finish()
    assert tuple(layer.pixels[30, 45]) == (255, 255, 255, 255)
    assert tuple(layer.pixels[11, 11]) == (0, 0, 0, 255)
    assert tuple(layer.pixels[0, 0]) == (255, 255, 255, 255)


def test_eraser_stroke_reduces_alpha():
    document, layer = _document(40, 30)
    session = document.begin_brush_stroke(
        BrushSettings(size=12, hardness=1.0, erase=True)
    )
    session.stroke_to(20.0, 15.0)
    assert session.finish() is True
    assert layer.pixels[15, 20, 3] == 0
    assert layer.pixels[1, 1, 3] == 255
    document.undo()
    assert layer.pixels[15, 20, 3] == 255


def test_mask_stroke_changes_mask_and_undo():
    document, layer = _document()
    document.add_layer_mask(record=False)
    session = document.begin_brush_stroke(
        BrushSettings(size=20, hardness=1.0, color=(0, 0, 0, 255)), target="mask"
    )
    session.stroke_to(40.0, 30.0)
    assert session.finish() is True
    assert layer.mask[30, 40] == 0
    assert layer.mask[1, 1] == 255
    document.undo()
    assert layer.mask[30, 40] == 255
    document.redo()
    assert layer.mask[30, 40] == 0


def test_mask_value_uses_foreground_luminance():
    document, layer = _document()
    document.add_layer_mask(record=False)
    layer.mask[...] = 0
    session = document.begin_brush_stroke(
        BrushSettings(size=12, hardness=1.0, color=(255, 255, 255, 255)),
        target="mask",
    )
    session.stroke_to(40.0, 30.0)
    session.finish()
    assert layer.mask[30, 40] == 255


def test_stroke_requires_layer_and_rejects_locked():
    document = Document(40, 30)
    with pytest.raises(ValueError):
        document.begin_brush_stroke(BrushSettings())
    layer = document.add_layer(name="Layer", color=(255, 255, 255, 255), record=False)
    layer.locked = True
    with pytest.raises(ValueError, match="khoá"):
        document.begin_brush_stroke(BrushSettings())


def test_mask_stroke_requires_mask_and_eraser_not_allowed():
    document, _layer = _document()
    with pytest.raises(ValueError, match="chưa có mask"):
        document.begin_brush_stroke(BrushSettings(), target="mask")
    with pytest.raises(ValueError):
        document.begin_brush_stroke(BrushSettings(), target="unknown")
    document.add_layer_mask(record=False)
    with pytest.raises(ValueError, match="tẩy"):
        document.begin_brush_stroke(
            BrushSettings(erase=True), target="mask"
        )


def test_cancel_restores_pixels_and_history():
    document, layer = _document()
    session = document.begin_brush_stroke(
        BrushSettings(size=16, hardness=1.0, color=(255, 0, 0, 255))
    )
    session.stroke_to(20.0, 20.0)
    assert tuple(layer.pixels[20, 20]) == (255, 0, 0, 255)
    session.cancel()
    assert tuple(layer.pixels[20, 20]) == (255, 255, 255, 255)
    assert not document.history.can_undo
    assert not document.modified


def test_stroke_outside_layer_records_nothing():
    document, layer = _document(60, 40)
    layer.offset_x = 100
    layer.offset_y = 100
    session = document.begin_brush_stroke(BrushSettings(size=8))
    session.stroke_to(10.0, 10.0)
    assert session.finish() is False
    assert not document.history.can_undo


def test_painting_on_shape_layer_rasterizes_and_undo_restores():
    document = Document(80, 60)
    document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    shape = document.add_shape_layer(
        ShapeProperties(kind="rectangle", width=60, height=40, fill_color=(0, 0, 0, 255)),
        x=10,
        y=10,
        record=False,
    )
    document.mark_clean()
    assert shape.kind == "shape"
    session = document.begin_brush_stroke(
        BrushSettings(size=10, hardness=1.0, color=(255, 0, 0, 255))
    )
    session.stroke_to(40.0, 30.0)
    session.finish()
    assert shape.kind == "pixel"
    assert shape.shape is None
    assert tuple(shape.pixels[20, 30]) == (255, 0, 0, 255)
    document.undo()
    assert shape.kind == "shape"
    assert shape.shape is not None
    assert tuple(shape.pixels[20, 30]) == (0, 0, 0, 255)
