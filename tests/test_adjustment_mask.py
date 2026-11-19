"""Kiểm thử layer mask của layer điều chỉnh (mask cấp tài liệu)."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRectF

from core.adjustment_layer import AdjustmentProperties
from core.command_manager import SetLayerMaskCommand
from core.document import Document
from core.gradient import GradientSettings
from core.layer import LayerKind
from core.paint import BrushSettings
from core.selection import Selection
from formats.native_project import load_project, save_project


BASE = (200, 50, 40, 255)
INVERTED = (55, 205, 215, 255)


def _document(size=(20, 16)) -> Document:
    document = Document(*size)
    document.add_layer(name="Background", color=BASE, record=False)
    return document


def _adjustment_document(size=(20, 16)) -> tuple[Document, object]:
    document = _document(size)
    layer = document.add_adjustment_layer(
        AdjustmentProperties(kind="invert"), record=False
    )
    return document, layer


def _set_mask(
    document: Document, layer, mask: np.ndarray, *, record: bool = False
) -> None:
    document._apply_command(
        SetLayerMaskCommand(layer, layer.mask, True, mask, True, "Test mask"),
        record=record,
    )


def _left_mask(height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[:, : width // 2] = 255
    return mask


# ------------------------------------------------------------ tạo và compositor
def test_add_layer_mask_creates_canvas_sized_white_mask_with_undo():
    document, layer = _adjustment_document((12, 8))
    assert document.add_layer_mask(layer) is True
    assert layer.mask is not None
    assert layer.mask.shape == (8, 12)
    assert layer.mask.dtype == np.uint8
    assert np.all(layer.mask == 255)
    assert layer.mask_enabled

    assert document.undo() is True
    assert layer.mask is None

    assert document.redo() is True
    assert layer.mask is not None and layer.mask.shape == (8, 12)


def test_add_layer_mask_from_selection_uses_document_mask():
    document, layer = _adjustment_document((20, 16))
    document.set_selection(Selection.from_rect(20, 16, QRectF(4, 3, 6, 5)))
    assert document.add_layer_mask(layer) is True

    assert layer.mask.shape == (16, 20)
    assert np.all(layer.mask[5, 6] == 255)
    assert np.all(layer.mask[0, 0] == 0)
    bounds = document.selection.bounds()
    assert layer.mask[bounds.y(), bounds.x()] == 255


def test_mask_limits_adjustment_per_pixel():
    document, layer = _adjustment_document((10, 4))
    document.add_layer_mask(layer, record=False)
    _set_mask(document, layer, _left_mask(4, 10), record=True)

    composite = document.get_composite().array
    assert tuple(composite[2, 1]) == INVERTED
    assert tuple(composite[2, 8]) == BASE

    document.set_layer_mask_enabled(layer, False, record=False)
    all_inverted = document.get_composite().array
    assert tuple(all_inverted[2, 8]) == INVERTED

    document.set_layer_mask_enabled(layer, True, record=False)
    assert tuple(document.get_composite().array[2, 8]) == BASE

    document.undo()
    assert np.all(layer.mask == 255)
    assert tuple(document.get_composite().array[2, 8]) == INVERTED
    document.redo()
    assert tuple(document.get_composite().array[2, 8]) == BASE


def test_opacity_multiplies_with_mask():
    document, layer = _adjustment_document((4, 2))
    document.add_layer_mask(layer, record=False)
    _set_mask(document, layer, np.full((2, 4), 128, dtype=np.uint8))
    document.set_layer_opacity(layer, 0.5)

    pixel = document.get_composite().array[0, 0]
    expected = np.array(BASE[:3], dtype=np.float32) + (
        np.array(INVERTED[:3], dtype=np.float32) - np.array(BASE[:3], dtype=np.float32)
    ) * (128.0 / 255.0) * 0.5
    assert np.allclose(pixel[:3], expected, atol=1.5)


# ------------------------------------------------------------------ cọ và gradient
def test_brush_paints_on_adjustment_mask_and_undo():
    document, layer = _adjustment_document((30, 20))
    document.add_layer_mask(layer, record=False)
    assert np.all(layer.mask == 255)

    session = document.begin_brush_stroke(
        BrushSettings(size=12, hardness=1.0, color=(0, 0, 0, 255)),
        target="mask",
        layer=layer,
    )
    session.stroke_to(10.0, 10.0)
    assert session.finish() is True
    assert layer.mask[10, 10] == 0
    assert tuple(document.get_composite().array[10, 10]) == BASE
    assert tuple(document.get_composite().array[2, 25]) == INVERTED

    document.undo()
    assert np.all(layer.mask == 255)
    assert tuple(document.get_composite().array[10, 10]) == INVERTED


def test_brush_on_adjustment_mask_respects_selection():
    document, layer = _adjustment_document((30, 20))
    document.add_layer_mask(layer, record=False)
    document.set_selection(Selection.from_rect(30, 20, QRectF(5, 5, 10, 10)))
    session = document.begin_brush_stroke(
        BrushSettings(size=8, hardness=1.0, color=(0, 0, 0, 255)),
        target="mask",
        layer=layer,
    )
    session.stroke_to(10.0, 10.0)
    session.stroke_to(25.0, 25.0)
    session.finish()

    assert layer.mask[10, 10] == 0
    assert layer.mask[19, 29] == 255


def test_gradient_paints_on_adjustment_mask():
    document, layer = _adjustment_document((20, 10))
    document.add_layer_mask(layer, record=False)
    session = document.begin_gradient(
        GradientSettings(
            gradient_type="linear",
            start_color=(0, 0, 0, 255),
            end_color=(255, 255, 255, 255),
        ),
        (0.0, 5.0),
        target="mask",
        layer=layer,
    )
    session.update(19.0, 5.0)
    assert session.finish() is True

    assert layer.mask.shape == (10, 20)
    assert layer.mask[5, 0] < 20
    assert layer.mask[5, 19] > 235
    composite = document.get_composite().array
    assert np.allclose(composite[5, 0], BASE, atol=8)
    assert np.allclose(composite[5, 19], INVERTED, atol=2)

    document.undo()
    assert np.all(layer.mask == 255)


# --------------------------------------------------------------------- hình học
def test_crop_moves_canvas_mask_and_undo():
    document, layer = _adjustment_document((10, 8))
    document.add_layer_mask(layer, record=False)
    original = np.full((8, 10), 255, dtype=np.uint8)
    original[:, 2] = 7
    _set_mask(document, layer, original)

    assert document.crop(2, 1, 6, 5, record=True) is True
    assert layer.mask.shape == (5, 6)
    assert np.array_equal(layer.mask, original[1:6, 2:8])

    document.undo()
    assert layer.mask.shape == (8, 10)
    assert np.array_equal(layer.mask, original)


def test_canvas_size_places_mask_and_fills_new_area_black():
    document, layer = _adjustment_document((10, 8))
    document.add_layer_mask(layer, record=False)
    assert document.canvas_size(12, 10, anchor="top_left") is True
    assert layer.mask.shape == (10, 12)
    assert np.all(layer.mask[:8, :10] == 255)
    assert np.all(layer.mask[8:, :] == 0)
    assert np.all(layer.mask[:, 10:] == 0)

    document.undo()
    assert layer.mask.shape == (8, 10)


def test_resize_resamples_canvas_mask():
    document, layer = _adjustment_document((20, 16))
    document.add_layer_mask(layer, record=False)
    _set_mask(document, layer, _left_mask(16, 20))

    assert document.resize_image(10, 8, method="nearest") is True
    assert layer.mask.shape == (8, 10)
    assert layer.mask[4, 1] == 255
    assert layer.mask[4, 8] == 0

    document.undo()
    assert layer.mask.shape == (16, 20)
    assert layer.mask[8, 1] == 255 and layer.mask[8, 18] == 0


def test_rotate_and_flip_canvas_transform_mask_with_undo():
    document, layer = _adjustment_document((6, 4))
    document.add_layer_mask(layer, record=False)
    original = np.zeros((4, 6), dtype=np.uint8)
    original[1, 1] = 255
    _set_mask(document, layer, original)

    assert document.rotate_canvas("cw") is True
    assert layer.mask.shape == (6, 4)
    assert np.array_equal(layer.mask, np.rot90(original, -1))

    document.undo()
    assert layer.mask.shape == (4, 6)
    assert np.array_equal(layer.mask, original)

    document.redo()
    assert document.flip_canvas(True) is True
    assert layer.mask.shape == (6, 4)
    assert np.array_equal(layer.mask, np.flip(np.rot90(original, -1), axis=1))

    document.undo()
    document.undo()
    assert layer.mask.shape == (4, 6)
    assert np.array_equal(layer.mask, original)


# ----------------------------------------------------------------------- dự án
def test_project_roundtrip_preserves_adjustment_mask(tmp_path):
    document, layer = _adjustment_document((12, 9))
    document.add_layer_mask(layer, record=False)
    _set_mask(document, layer, _left_mask(9, 12))
    expected = document.get_composite().array.copy()

    target = save_project(document, tmp_path / "masked")
    loaded = load_project(target)
    loaded_layer = loaded.layers[-1]
    assert loaded_layer.kind == LayerKind.ADJUSTMENT
    assert loaded_layer.mask is not None
    assert loaded_layer.mask.shape == (9, 12)
    assert np.array_equal(loaded_layer.mask, layer.mask)
    assert np.array_equal(loaded.get_composite().array, expected)


def test_apply_layer_mask_blocked_for_adjustment():
    document, layer = _adjustment_document((8, 6))
    document.add_layer_mask(layer, record=False)
    with pytest.raises(ValueError, match="không có pixel để áp mask"):
        document.apply_layer_mask(layer)
    assert layer.mask is not None
