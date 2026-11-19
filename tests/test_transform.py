"""Kiểm thử xoay/lật canvas và layer: pixel, offset, mask, vùng chọn, undo."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRect, QRectF

from core.document import Document, rotated_dimensions
from core.layer import Layer
from core.selection import Selection


def pattern_layer(width: int = 4, height: int = 3) -> Layer:
    """Mỗi pixel có màu riêng để kiểm tra hướng xoay chính xác."""
    layer = Layer(width, height, name="Pattern")
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            pixels[y, x] = (x * 10 + 1, y * 10 + 2, x * 10 + y, 255)
    layer.set_pixels(pixels)
    layer.offset_x = 1
    layer.offset_y = 2
    return layer


def mask_pattern(width: int = 4, height: int = 3) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            mask[y, x] = x * 20 + y
    return mask


def build_document() -> tuple[Document, Layer]:
    document = Document(12, 9, name="Transform")
    layer = pattern_layer()
    layer.set_mask(mask_pattern())
    document.add_layer(layer=layer, index=0, record=False)
    document.mark_clean()
    return document, layer


def test_rotate_cw_swaps_dimensions_pixels_and_offset():
    document, layer = build_document()
    original = layer.pixels.copy()
    assert document.rotate_canvas("cw") is True

    assert (document.width, document.height) == (9, 12)
    assert (layer.width, layer.height) == (3, 4)
    assert (layer.offset_x, layer.offset_y) == (4, 1)
    assert np.array_equal(layer.pixels, np.rot90(original, -1))


def test_rotate_ccw_swaps_dimensions_pixels_and_offset():
    document, layer = build_document()
    original = layer.pixels.copy()
    assert document.rotate_canvas("ccw") is True

    assert (document.width, document.height) == (9, 12)
    assert (layer.width, layer.height) == (3, 4)
    assert (layer.offset_x, layer.offset_y) == (2, 7)
    assert np.array_equal(layer.pixels, np.rot90(original, 1))


def test_rotate_180_keeps_dimensions_and_mirrors_offset():
    document, layer = build_document()
    original = layer.pixels.copy()
    assert document.rotate_canvas("180") is True

    assert (document.width, document.height) == (12, 9)
    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == (7, 4)
    assert np.array_equal(layer.pixels, np.rot90(original, 2))


def test_rotate_canvas_rotates_mask_and_selection():
    document, layer = build_document()
    original_mask = layer.mask.copy()
    document.preview_selection(
        Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    )

    document.rotate_canvas("cw")
    assert np.array_equal(layer.mask, np.rot90(original_mask, -1))
    assert layer.mask_enabled
    assert document.selection.bounds() == QRect(2, 2, 4, 5)

    document.rotate_canvas("ccw")
    assert np.array_equal(layer.mask, original_mask)
    assert document.selection.bounds() == QRect(2, 3, 5, 4)


def test_rotate_canvas_undo_and_redo_restore_everything():
    document, layer = build_document()
    original_pixels = layer.pixels.copy()
    original_mask = layer.mask.copy()
    document.preview_selection(
        Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    )

    assert document.rotate_canvas("cw")
    assert document.history.can_undo
    assert document.undo()
    assert (document.width, document.height) == (12, 9)
    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == (1, 2)
    assert np.array_equal(layer.pixels, original_pixels)
    assert np.array_equal(layer.mask, original_mask)
    assert document.selection.bounds() == QRect(2, 3, 5, 4)

    assert document.redo()
    assert (document.width, document.height) == (9, 12)
    assert (layer.offset_x, layer.offset_y) == (4, 1)


def test_rotate_composite_matches_rotated_composite():
    document = Document(12, 9, name="Composite")
    background = Layer(12, 9, name="Background")
    gradient = np.zeros((9, 12, 4), dtype=np.uint8)
    gradient[..., 0] = np.arange(12, dtype=np.uint8)[None, :] * 20
    gradient[..., 1] = np.arange(9, dtype=np.uint8)[:, None] * 25
    gradient[..., 3] = 255
    background.set_pixels(gradient)
    document.add_layer(layer=background, index=0, record=False)

    accent = pattern_layer()
    document.add_layer(layer=accent, index=1, record=False)
    before = document.get_composite().array.copy()

    document.rotate_canvas("cw")
    after = document.get_composite().array
    assert after.shape == (12, 9, 4)
    assert np.array_equal(after, np.rot90(before, -1))


def test_flip_canvas_horizontal_mirrors_pixels_offsets_mask_selection():
    document, layer = build_document()
    original = layer.pixels.copy()
    original_mask = layer.mask.copy()
    document.preview_selection(
        Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    )

    assert document.flip_canvas(horizontal=True) is True
    assert (document.width, document.height) == (12, 9)
    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == (7, 2)
    assert np.array_equal(layer.pixels, np.flip(original, axis=1))
    assert np.array_equal(layer.mask, np.flip(original_mask, axis=1))
    assert document.selection.bounds() == QRect(5, 3, 5, 4)


def test_flip_canvas_vertical_mirrors_pixels_offsets_mask_selection():
    document, layer = build_document()
    original = layer.pixels.copy()
    original_mask = layer.mask.copy()
    document.preview_selection(
        Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    )

    assert document.flip_canvas(horizontal=False) is True
    assert (layer.offset_x, layer.offset_y) == (1, 4)
    assert np.array_equal(layer.pixels, np.flip(original, axis=0))
    assert np.array_equal(layer.mask, np.flip(original_mask, axis=0))
    assert document.selection.bounds() == QRect(2, 2, 5, 4)


def test_flip_canvas_undo_restores_original():
    document, layer = build_document()
    original = layer.pixels.copy()
    original_offset = (layer.offset_x, layer.offset_y)
    assert document.flip_canvas(True)
    assert document.undo()
    assert np.array_equal(layer.pixels, original)
    assert (layer.offset_x, layer.offset_y) == original_offset


def test_flip_composite_matches_mirrored_composite():
    document = Document(12, 9, name="Composite")
    background = Layer(12, 9, name="Background")
    gradient = np.zeros((9, 12, 4), dtype=np.uint8)
    gradient[..., 0] = np.arange(12, dtype=np.uint8)[None, :] * 20
    gradient[..., 1] = np.arange(9, dtype=np.uint8)[:, None] * 25
    gradient[..., 3] = 255
    background.set_pixels(gradient)
    document.add_layer(layer=background, index=0, record=False)
    accent = pattern_layer()
    document.add_layer(layer=accent, index=1, record=False)
    before = document.get_composite().array.copy()

    document.flip_canvas(True)
    assert np.array_equal(document.get_composite().array, np.flip(before, axis=1))


def test_transform_layer_rotates_around_its_center():
    document, layer = build_document()
    original = layer.pixels.copy()
    original_mask = layer.mask.copy()
    assert document.transform_layer("rotate_cw", layer) is True

    assert (layer.width, layer.height) == (3, 4)
    # Tâm layer trong toạ độ tài liệu không đổi: (3, 3.5)
    assert abs(layer.offset_x + layer.width / 2 - 3.0) <= 0.5
    assert abs(layer.offset_y + layer.height / 2 - 3.5) <= 0.5
    assert np.array_equal(layer.pixels, np.rot90(original, -1))
    assert np.array_equal(layer.mask, np.rot90(original_mask, -1))
    assert (document.width, document.height) == (12, 9)


def test_transform_layer_flip_keeps_size_and_offset():
    document, layer = build_document()
    original = layer.pixels.copy()
    original_mask = layer.mask.copy()
    assert document.transform_layer("flip_h") is True

    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == (1, 2)
    assert np.array_equal(layer.pixels, np.flip(original, axis=1))
    assert np.array_equal(layer.mask, np.flip(original_mask, axis=1))


def test_transform_layer_does_not_change_selection():
    document, layer = build_document()
    selection = Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    document.preview_selection(selection)
    document.transform_layer("rotate_180", layer)
    assert document.selection.bounds() == QRect(2, 3, 5, 4)


def test_transform_layer_undo_restores_pixels_size_and_offset():
    document, layer = build_document()
    original = layer.pixels.copy()
    original_mask = layer.mask.copy()
    assert document.transform_layer("rotate_cw")
    assert document.undo()
    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == (1, 2)
    assert np.array_equal(layer.pixels, original)
    assert np.array_equal(layer.mask, original_mask)


def test_invalid_direction_and_operation_raise():
    document, layer = build_document()
    with pytest.raises(ValueError):
        document.rotate_canvas("sideways")
    with pytest.raises(ValueError):
        document.transform_layer("skew", layer)


def test_transform_layer_without_active_layer_returns_false():
    document = Document(4, 4, name="Empty")
    assert document.transform_layer("rotate_cw") is False


def test_rotated_dimensions_formula():
    assert rotated_dimensions(12, 9, 0) == (12, 9)
    assert rotated_dimensions(12, 9, 90) == (9, 12)
    assert rotated_dimensions(12, 9, 180) == (12, 9)
    assert rotated_dimensions(12, 9, 30) == (15, 14)
    assert rotated_dimensions(12, 9, 45) == (15, 15)
    assert rotated_dimensions(4, 3, 30) == (5, 5)


def test_rotate_canvas_arbitrary_30_degrees():
    document, layer = build_document()
    original_pixels = layer.pixels.copy()

    assert document.rotate_canvas_arbitrary(30.0) is True
    assert (document.width, document.height) == (15, 14)
    assert (layer.width, layer.height) == rotated_dimensions(4, 3, 30)
    assert layer.mask.shape == (layer.height, layer.width)
    assert layer.pixels.shape == (layer.height, layer.width, 4)
    # Góc xoay quanh tâm canvas, layer nhỏ hơn canvas nên tâm layer dịch theo.
    assert abs(layer.offset_x + layer.width / 2 - 5.402) <= 0.75
    assert abs(layer.offset_y + layer.height / 2 - 4.634) <= 0.75
    assert not np.array_equal(layer.pixels, original_pixels)


def test_rotate_canvas_arbitrary_45_degrees_and_transparency():
    document, layer = build_document()
    assert document.rotate_canvas_arbitrary(45.0) is True
    assert (document.width, document.height) == (15, 15)
    assert layer.pixels.shape == (layer.height, layer.width, 4)
    # Góc trên-trái của layer sau khi xoay nằm ngoài vùng có dữ liệu.
    assert layer.pixels[0, 0, 3] == 0
    assert layer.pixels[..., 3].max() == 255


def test_rotate_canvas_arbitrary_rotates_selection():
    document, _layer = build_document()
    document.preview_selection(
        Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    )

    assert document.rotate_canvas_arbitrary(30.0) is True
    assert document.has_selection()
    bounds = document.selection.bounds()
    assert bounds.width() >= 5 and bounds.height() >= 4
    assert bounds.width() <= document.width
    assert bounds.height() <= document.height
    center_x = bounds.x() + bounds.width() / 2
    center_y = bounds.y() + bounds.height() / 2
    assert abs(center_x - 5.951) <= 1.0
    assert abs(center_y - 6.683) <= 1.0


def test_rotate_canvas_arbitrary_undo_redo_restores_everything():
    document, layer = build_document()
    original_pixels = layer.pixels.copy()
    original_mask = layer.mask.copy()
    original_offset = (layer.offset_x, layer.offset_y)
    document.preview_selection(
        Selection.from_rect(document.width, document.height, QRectF(2, 3, 5, 4))
    )

    assert document.rotate_canvas_arbitrary(30.0) is True
    assert document.undo()
    assert (document.width, document.height) == (12, 9)
    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == original_offset
    assert np.array_equal(layer.pixels, original_pixels)
    assert np.array_equal(layer.mask, original_mask)
    assert document.selection.bounds() == QRect(2, 3, 5, 4)

    assert document.redo()
    assert (document.width, document.height) == (15, 14)


def test_rotate_canvas_arbitrary_quarter_angles_use_exact_path():
    document, layer = build_document()
    original = layer.pixels.copy()
    assert document.rotate_canvas_arbitrary(90.0) is True
    assert (document.width, document.height) == (9, 12)
    assert np.array_equal(layer.pixels, np.rot90(original, -1))
    document.undo()
    assert document.rotate_canvas_arbitrary(-90.0) is True
    assert np.array_equal(layer.pixels, np.rot90(original, 1))
    document.undo()
    assert document.rotate_canvas_arbitrary(180.0) is True
    assert np.array_equal(layer.pixels, np.rot90(original, 2))


def test_rotate_canvas_arbitrary_zero_returns_false_without_history():
    document, _layer = build_document()
    assert document.rotate_canvas_arbitrary(0.0) is False
    assert document.rotate_canvas_arbitrary(360.0) is False
    assert not document.history.can_undo
    assert (document.width, document.height) == (12, 9)


def test_rotate_layer_arbitrary_keeps_center_and_undo():
    document, layer = build_document()
    original_pixels = layer.pixels.copy()
    original_mask = layer.mask.copy()
    assert document.rotate_layer_arbitrary(45.0) is True

    assert (document.width, document.height) == (12, 9)
    assert (layer.width, layer.height) == rotated_dimensions(4, 3, 45)
    assert layer.mask.shape == (layer.height, layer.width)
    assert abs(layer.offset_x + layer.width / 2 - 3.0) <= 0.5
    assert abs(layer.offset_y + layer.height / 2 - 3.5) <= 0.5

    assert document.undo()
    assert (layer.width, layer.height) == (4, 3)
    assert (layer.offset_x, layer.offset_y) == (1, 2)
    assert np.array_equal(layer.pixels, original_pixels)
    assert np.array_equal(layer.mask, original_mask)


def test_rotate_layer_arbitrary_quarter_angle_is_exact():
    document, layer = build_document()
    original = layer.pixels.copy()
    assert document.rotate_layer_arbitrary(-90.0) is True
    assert (layer.width, layer.height) == (3, 4)
    assert np.array_equal(layer.pixels, np.rot90(original, 1))
    assert document.history.can_undo


def test_rotate_arbitrary_invalid_input_raises_or_returns_false():
    document, _layer = build_document()
    assert document.rotate_canvas_arbitrary(0.0) is False
    with pytest.raises(ValueError):
        document.rotate_canvas_arbitrary(30.0, method="magic")
    with pytest.raises(ValueError):
        document.rotate_canvas_arbitrary(float("nan"))
    with pytest.raises(ValueError):
        document.rotate_layer_arbitrary(30.0, method="magic")

    empty = Document(4, 4, name="Empty")
    assert empty.rotate_layer_arbitrary(30.0) is False
