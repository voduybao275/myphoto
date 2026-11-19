"""Kiểm thử vùng chọn, layer mask, crop/canvas size và Image Size."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QTransform

from core.canvas import composite_layers
from core.document import Document
from core.layer import Layer
from core.selection import MAX_FEATHER_RADIUS, Selection


def make_document(width=10, height=10):
    return Document(width, height, dpi=72, name="Selection Test")


def solid_layer(document, rgba=(200, 40, 10, 255), name="Layer"):
    return document.add_layer(name=name, color=rgba, record=False)


# --------------------------------------------------------------------- Selection
def test_rect_selection_bounds_and_mask():
    selection = Selection.from_rect(20, 10, QRectF(2, 3, 4, 5))
    assert selection.bounds() == QRect(2, 3, 4, 5)
    mask = selection.mask()
    assert mask.shape == (10, 20)
    assert mask[3, 2] == 255
    assert mask[7, 5] == 255
    assert mask[2, 2] == 0
    assert mask[3, 1] == 0
    assert int((mask == 255).sum()) == 20


def test_selection_is_clipped_to_document():
    selection = Selection.from_rect(10, 10, QRectF(-4, -4, 8, 8))
    assert selection.bounds() == QRect(0, 0, 4, 4)
    assert selection.mask()[0, 0] == 255
    assert selection.mask()[4, 4] == 0


def test_ellipse_selection_mask():
    selection = Selection.from_ellipse(10, 10, QRectF(0, 0, 10, 10))
    mask = selection.mask()
    assert mask[5, 5] == 255
    assert mask[0, 0] == 0


def test_combine_modes():
    left = Selection.from_rect(10, 10, QRectF(0, 0, 5, 10))
    right = Selection.from_rect(10, 10, QRectF(5, 0, 5, 10))
    overlap = Selection.from_rect(10, 10, QRectF(3, 0, 4, 10))

    added = left.combine(right, "add")
    assert added.bounds() == QRect(0, 0, 10, 10)

    union = left.combine(overlap, "add")
    assert union.bounds() == QRect(0, 0, 7, 10)

    subtracted = union.combine(overlap, "subtract")
    assert subtracted.bounds() == QRect(0, 0, 3, 10)

    intersected = left.combine(overlap, "intersect")
    assert intersected.bounds() == QRect(3, 0, 2, 10)

    replaced = left.combine(right, "replace")
    assert replaced.bounds() == QRect(5, 0, 5, 10)


def test_invert_selection():
    selection = Selection.from_rect(10, 10, QRectF(2, 2, 3, 3))
    inverted = selection.inverted()
    mask = inverted.mask()
    assert mask[0, 0] == 255
    assert mask[3, 3] == 0
    assert inverted.inverted() == selection

    empty = Selection.empty(10, 10)
    assert empty.inverted() == Selection.all(10, 10)


def test_selection_equality_and_translate():
    first = Selection.from_rect(10, 10, QRectF(1, 1, 2, 2))
    second = Selection.from_rect(10, 10, QRectF(1, 1, 2, 2))
    assert first == second
    moved = first.translated(3, 4)
    assert moved.bounds() == QRect(4, 5, 2, 2)
    assert first != moved


def test_selection_scaled():
    selection = Selection.from_rect(10, 20, QRectF(2, 4, 4, 8))
    scaled = selection.scaled(2.0, 0.5, 20, 10)
    assert (scaled.width, scaled.height) == (20, 10)
    assert scaled.bounds() == QRect(4, 2, 8, 4)


def test_invalid_combine_mode():
    selection = Selection.empty(4, 4)
    with pytest.raises(ValueError):
        selection.combine(selection, "xor")


# ------------------------------------------------------------ Document selection
def test_document_selection_history():
    document = make_document()
    assert document.selection is None
    assert document.select_all()
    assert document.has_selection()
    assert document.selection.bounds() == QRect(0, 0, 10, 10)

    assert document.deselect()
    assert document.selection is None

    assert document.undo()
    assert document.has_selection()
    assert document.redo()
    assert document.selection is None


def test_document_invert_selection():
    document = make_document()
    document.set_selection(Selection.from_rect(10, 10, QRectF(2, 2, 3, 3)))
    assert document.invert_selection()
    assert document.selection.mask()[0, 0] == 255
    assert document.selection.mask()[3, 3] == 0
    assert document.undo()
    assert document.selection.mask()[3, 3] == 255


def test_document_preview_and_commit_selection():
    document = make_document()
    original = Selection.from_rect(10, 10, QRectF(0, 0, 2, 2))
    document.set_selection(original)
    history_before = len(document.history)

    preview = Selection.from_rect(10, 10, QRectF(1, 1, 4, 4))
    document.preview_selection(preview)
    assert document.selection == preview
    assert len(document.history) == history_before

    document.commit_selection(original, preview, "Kéo vùng chọn")
    assert len(document.history) == history_before + 1
    assert document.undo()
    assert document.selection == original


def test_selection_must_match_document_size():
    document = make_document()
    with pytest.raises(ValueError):
        document.set_selection(Selection.all(5, 5))


# ------------------------------------------------------------------- layer mask
def test_add_mask_from_selection_and_composite():
    document = make_document()
    layer = solid_layer(document, (255, 0, 0, 255))
    document.set_selection(Selection.from_rect(10, 10, QRectF(2, 2, 4, 4)))
    assert document.add_layer_mask()
    assert layer.mask is not None
    assert layer.mask.shape == (10, 10)
    assert layer.mask[3, 3] == 255
    assert layer.mask[0, 0] == 0

    composite = composite_layers([layer], 10, 10)
    assert composite[3, 3, 3] == 255
    assert composite[0, 0, 3] == 0


def test_add_mask_without_selection_reveals_all():
    document = make_document()
    layer = solid_layer(document)
    assert document.add_layer_mask()
    assert np.all(layer.mask == 255)
    composite = composite_layers([layer], 10, 10)
    assert composite[0, 0, 3] == 255


def test_mask_disabled_composites_fully():
    document = make_document()
    layer = solid_layer(document, (255, 0, 0, 255))
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:6, 2:6] = 255
    document._apply_layer_mask_raw(layer, mask, True)
    assert composite_layers([layer], 10, 10)[0, 0, 3] == 0

    assert document.set_layer_mask_enabled(layer, False)
    assert composite_layers([layer], 10, 10)[0, 0, 3] == 255
    assert document.undo()
    assert composite_layers([layer], 10, 10)[0, 0, 3] == 0


def test_mask_aligned_to_layer_offset():
    document = make_document()
    layer = Layer(4, 4, "Offset")
    layer.fill((0, 0, 255, 255))
    layer.offset_x, layer.offset_y = 3, 3
    document.add_layer(layer, record=False)
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[0, 0] = 255
    layer.set_mask(mask)
    composite = composite_layers([layer], 10, 10)
    assert composite[3, 3, 3] == 255
    assert composite[4, 4, 3] == 0


def test_apply_mask_multiplies_alpha_and_undo():
    document = make_document()
    layer = document.add_layer(color=(10, 20, 30, 200), record=False)
    mask = np.full((10, 10), 128, dtype=np.uint8)
    layer.set_mask(mask)
    assert document.apply_layer_mask()
    assert layer.mask is None
    assert np.all(layer.pixels[..., 3] == 100)

    assert document.undo()
    assert layer.mask is not None
    assert np.all(layer.pixels[..., 3] == 200)
    assert document.redo()
    assert layer.mask is None


def test_remove_mask_and_undo():
    document = make_document()
    layer = solid_layer(document)
    layer.set_mask(np.full((10, 10), 200, dtype=np.uint8))
    assert document.remove_layer_mask()
    assert layer.mask is None
    assert document.undo()
    assert layer.mask is not None


def test_memory_estimate_includes_mask():
    document = make_document(10, 10)
    layer = solid_layer(document)
    without_mask = document.memory_estimate()
    layer.set_mask(np.full((10, 10), 255, dtype=np.uint8))
    assert document.memory_estimate() == without_mask + 100


# ------------------------------------------------------------ crop / canvas size
def test_crop_shifts_offsets_and_undo():
    document = make_document(10, 10)
    layer = solid_layer(document)
    document.set_selection(Selection.from_rect(10, 10, QRectF(0, 0, 3, 3)))
    assert document.crop(2, 2, 6, 5)
    assert (document.width, document.height) == (6, 5)
    assert (layer.offset_x, layer.offset_y) == (-2, -2)
    assert document.selection is None

    assert document.undo()
    assert (document.width, document.height) == (10, 10)
    assert (layer.offset_x, layer.offset_y) == (0, 0)
    assert document.has_selection()
    assert document.redo()
    assert (document.width, document.height) == (6, 5)


def test_crop_preserves_layer_pixels():
    document = make_document(10, 10)
    layer = solid_layer(document)
    before = layer.pixels.copy()
    document.crop(2, 2, 6, 5)
    assert np.array_equal(layer.pixels, before)


def test_crop_validation():
    document = make_document(10, 10)
    with pytest.raises(ValueError):
        document.crop(8, 8, 5, 5)
    with pytest.raises(ValueError):
        document.crop(0, 0, 0, 5)
    assert not document.crop(0, 0, 10, 10)


def test_crop_to_selection_uses_bounds():
    document = make_document(20, 20)
    solid_layer(document)
    document.set_selection(Selection.from_ellipse(20, 20, QRectF(4, 6, 8, 10)))
    assert document.crop_to_selection()
    assert (document.width, document.height) == (8, 10)
    assert document.undo()
    assert (document.width, document.height) == (20, 20)


def test_canvas_size_anchors_shift_layers_and_selection():
    document = make_document(10, 10)
    layer = solid_layer(document)
    layer.offset_x, layer.offset_y = 1, 1
    document.set_selection(Selection.from_rect(10, 10, QRectF(0, 0, 2, 2)))

    assert document.canvas_size(20, 20, "center")
    assert (layer.offset_x, layer.offset_y) == (6, 6)
    assert document.selection.bounds() == QRect(5, 5, 2, 2)

    assert document.undo()
    assert document.canvas_size(20, 20, "top_left")
    assert (layer.offset_x, layer.offset_y) == (1, 1)

    assert document.undo()
    assert document.canvas_size(4, 4, "bottom_right")
    assert (layer.offset_x, layer.offset_y) == (-5, -5)
    assert (document.width, document.height) == (4, 4)


def test_canvas_size_validation():
    document = make_document(10, 10)
    with pytest.raises(ValueError):
        document.canvas_size(0, 10)
    with pytest.raises(ValueError):
        document.canvas_size(10, 10, "middle")
    assert not document.canvas_size(10, 10)


# ------------------------------------------------------------------- Image Size
def test_resize_image_scales_layers_and_offsets():
    document = make_document(10, 20)
    layer = solid_layer(document)
    layer.offset_x, layer.offset_y = 2, 4
    assert document.resize_image(20, 10, "bilinear")
    assert (document.width, document.height) == (20, 10)
    assert (layer.width, layer.height) == (20, 10)
    assert (layer.offset_x, layer.offset_y) == (4, 2)
    assert layer.pixels.shape == (10, 20, 4)

    assert document.undo()
    assert (document.width, document.height) == (10, 20)
    assert (layer.width, layer.height) == (10, 20)
    assert (layer.offset_x, layer.offset_y) == (2, 4)
    assert document.redo()
    assert (document.width, document.height) == (20, 10)


def test_resize_image_scales_mask_and_selection():
    document = make_document(10, 10)
    layer = solid_layer(document)
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:8, 2:8] = 255
    layer.set_mask(mask)
    document.set_selection(Selection.from_rect(10, 10, QRectF(2, 2, 6, 6)))

    assert document.resize_image(20, 20, "nearest")
    assert layer.mask is not None
    assert layer.mask.shape == (20, 20)
    assert document.selection.bounds() == QRect(4, 4, 12, 12)

    assert document.undo()
    assert layer.mask.shape == (10, 10)
    assert document.selection.bounds() == QRect(2, 2, 6, 6)


def test_resize_image_nearest_preserves_colors():
    document = make_document(2, 2)
    layer = document.add_layer(record=False)
    layer.fill((0, 0, 0, 0))
    layer.pixels[0, 0] = (255, 0, 0, 255)
    assert document.resize_image(4, 4, "nearest")
    assert tuple(int(v) for v in layer.pixels[0, 0]) == (255, 0, 0, 255)
    assert tuple(int(v) for v in layer.pixels[1, 1]) == (255, 0, 0, 255)


def test_resize_image_validation():
    document = make_document(10, 10)
    with pytest.raises(ValueError):
        document.resize_image(0, 10)
    with pytest.raises(ValueError):
        document.resize_image(10, 10, "unknown")
    assert not document.resize_image(10, 10)


# ---------------------------------------------------- Feather và anti-alias
def test_feather_softens_edge_and_keeps_center_solid():
    selection = Selection.from_rect(100, 100, QRectF(30, 30, 40, 40), feather=10)
    mask = selection.mask()
    assert mask.shape == (100, 100)
    assert mask[50, 50] == 255
    assert 0 < int(mask[50, 29]) < 255
    assert 0 < int(mask[50, 70]) < 255
    assert mask[50, 15] == 0
    soft = np.count_nonzero((mask > 0) & (mask < 255))
    assert soft > 0


def test_feather_zero_matches_hard_rectangle():
    hard = Selection.from_rect(20, 20, QRectF(4, 4, 6, 6))
    feathered = Selection.from_rect(20, 20, QRectF(4, 4, 6, 6), feather=0)
    np.testing.assert_array_equal(hard.mask(), feathered.mask())
    assert set(np.unique(hard.mask())) <= {0, 255}


def test_feather_expands_bounds_and_stays_inside_document():
    selection = Selection.from_rect(100, 100, QRectF(2, 2, 10, 10), feather=10)
    bounds = selection.bounds()
    assert bounds.left() >= 0 and bounds.top() >= 0
    assert bounds.right() < 100 and bounds.bottom() < 100
    assert bounds.width() > 10 and bounds.height() > 10

    at_edge = Selection.from_rect(20, 20, QRectF(0, 0, 6, 6), feather=8)
    assert at_edge.bounds().left() == 0
    assert at_edge.bounds().top() == 0


def test_antialias_toggle_controls_soft_pixels():
    off = Selection.from_ellipse(
        80, 80, QRectF(10.5, 10.5, 50, 50), antialias=False
    )
    on = Selection.from_ellipse(80, 80, QRectF(10.5, 10.5, 50, 50), antialias=True)
    assert set(np.unique(off.mask())) <= {0, 255}
    assert len(np.unique(on.mask())) > 2


def test_selection_options_survive_transforms_and_combine():
    selection = Selection.from_rect(
        100, 100, QRectF(10, 10, 20, 20), feather=6, antialias=False
    )
    for changed in (
        selection.copy(),
        selection.translated(5, 0),
        selection.scaled(2, 2, 200, 200),
        selection.transformed(QTransform().rotate(90), 100, 100),
        selection.inverted(),
    ):
        assert changed.feather == 6
        assert not changed.antialias

    other = Selection.from_rect(
        100, 100, QRectF(40, 40, 10, 10), feather=3, antialias=True
    )
    combined = selection.combine(other, "add")
    assert combined.feather == 3
    assert combined.antialias


def test_feather_radius_is_clamped_and_validated():
    selection = Selection.from_rect(10, 10, QRectF(1, 1, 2, 2), feather=9999)
    assert selection.feather == MAX_FEATHER_RADIUS
    negative = Selection.from_rect(10, 10, QRectF(1, 1, 2, 2), feather=-5)
    assert negative.feather == 0.0
    with pytest.raises(ValueError):
        Selection.from_rect(10, 10, QRectF(1, 1, 2, 2), feather=float("nan"))


def test_document_feather_selection_and_undo():
    document = make_document(100, 100)
    document.set_selection(
        Selection.from_rect(100, 100, QRectF(30, 30, 40, 40), feather=4)
    )
    original = document.selection.copy()

    assert document.feather_selection(12)
    assert document.selection.feather == 12
    assert 0 < int(document.selection_mask()[50, 29]) < 255

    assert document.undo()
    assert document.selection == original
    assert document.selection.feather == 4

    assert document.redo()
    assert document.selection.feather == 12
    assert not document.feather_selection(12)
    with pytest.raises(ValueError):
        document.feather_selection(MAX_FEATHER_RADIUS + 1)


def test_feather_selection_requires_selection():
    document = make_document(20, 20)
    assert not document.feather_selection(8)


def test_feathered_selection_blends_filter_at_edge():
    document = make_document(40, 40)
    layer = solid_layer(document, (255, 255, 255, 255))
    document.set_selection(
        Selection.from_rect(40, 40, QRectF(10, 10, 20, 20), feather=6)
    )
    black = layer.pixels.copy()
    black[..., :3] = 0
    assert document.apply_layer_filter(black, "Invert")
    assert tuple(int(v) for v in layer.pixels[20, 20]) == (0, 0, 0, 255)
    edge = int(layer.pixels[20, 9, 0])
    assert 0 < edge < 255
    far = int(layer.pixels[20, 2, 0])
    assert far > 250


def test_feathered_selection_creates_soft_layer_mask():
    document = make_document(40, 40)
    layer = solid_layer(document, (255, 255, 255, 255))
    document.set_selection(
        Selection.from_rect(40, 40, QRectF(10, 10, 20, 20), feather=6)
    )
    assert document.add_layer_mask()
    assert layer.mask is not None
    assert layer.mask[20, 20] == 255
    assert 0 < int(layer.mask[20, 9]) < 255
    assert layer.mask[20, 0] == 0
