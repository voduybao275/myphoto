"""Kiểm thử bộ lọc ảnh và tích hợp Document (vùng chọn, undo, layer văn bản)."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRectF

from core import filters
from core.document import Document
from core.layer import LayerKind
from core.selection import Selection
from core.text_layer import TextProperties


def solid(color=(100, 120, 140, 255), width=8, height=6) -> np.ndarray:
    array = np.empty((height, width, 4), dtype=np.uint8)
    array[...] = color
    return array


def make_document(width=16, height=12) -> Document:
    return Document(width, height, dpi=72, name="Filters")


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize(
    "array",
    [
        np.zeros((4, 4, 3), dtype=np.uint8),
        np.zeros((4, 4, 4), dtype=np.float32),
        np.zeros((4, 4), dtype=np.uint8),
    ],
)
def test_invalid_pixel_array(array):
    with pytest.raises(ValueError):
        filters.invert(array)


# ------------------------------------------------------------------ point ops
def test_invert_keeps_alpha():
    result = filters.invert(solid((10, 20, 30, 200)))
    assert tuple(result[0, 0]) == (245, 235, 225, 200)


def test_brightness_and_contrast():
    image = solid((100, 128, 200, 255), 2, 2)
    brighter = filters.brightness_contrast(image, brightness=50)
    assert tuple(brighter[0, 0, :3]) == (228, 255, 255)

    maximum = filters.brightness_contrast(solid((1, 2, 3, 255)), brightness=100)
    assert tuple(maximum[0, 0, :3]) == (255, 255, 255)
    minimum = filters.brightness_contrast(solid((254, 253, 252, 255)), brightness=-100)
    assert tuple(minimum[0, 0, :3]) == (0, 0, 0)

    strong = filters.brightness_contrast(solid((64, 128, 192, 255)), contrast=100)
    assert tuple(strong[0, 0, :3]) == (0, 128, 255)


def test_brightness_neutral_returns_copy():
    image = solid()
    result = filters.brightness_contrast(image)
    assert np.array_equal(result, image)
    assert result is not image


def test_desaturate_uses_luma_and_keeps_alpha():
    red = filters.desaturate(solid((255, 0, 0, 200)))
    assert tuple(red[0, 0]) == (54, 54, 54, 200)
    green = filters.desaturate(solid((0, 255, 0, 255)))
    assert tuple(green[0, 0, :3]) == (182, 182, 182)
    blue = filters.desaturate(solid((0, 0, 255, 255)))
    assert tuple(blue[0, 0, :3]) == (18, 18, 18)


def test_auto_contrast_stretches_range():
    ramp = np.linspace(100, 150, 64, dtype=np.uint8)
    image = np.empty((4, 64, 4), dtype=np.uint8)
    image[..., 0] = ramp
    image[..., 1] = ramp
    image[..., 2] = ramp
    image[..., 3] = 255
    result = filters.auto_contrast(image)
    assert result[..., 0].min() < 10
    assert result[..., 0].max() > 245
    assert np.all(result[..., 3] == 255)
    assert filters.auto_contrast(solid()).shape == solid().shape


def test_auto_contrast_uniform_image_unchanged():
    image = solid((120, 120, 120, 255))
    assert np.array_equal(filters.auto_contrast(image), image)


@pytest.mark.parametrize(
    "source, hue, expected",
    [
        ((255, 0, 0), 120.0, (0, 255, 0)),
        ((0, 255, 0), -120.0, (255, 0, 0)),
        ((0, 0, 255), 120.0, (255, 0, 0)),
        ((255, 0, 0), 180.0, (0, 255, 255)),
    ],
)
def test_hue_rotation(source, hue, expected):
    image = solid((*source, 255), 1, 1)
    result = filters.hue_saturation(image, hue=hue)
    assert np.abs(result[0, 0, :3].astype(int) - np.array(expected)).max() <= 1
    assert result[0, 0, 3] == 255


def test_saturation_and_lightness():
    image = solid((255, 0, 0, 255), 1, 1)
    gray = filters.hue_saturation(image, saturation=-100)
    assert tuple(gray[0, 0, :3]) == (128, 128, 128)
    black = filters.hue_saturation(image, lightness=-100)
    assert tuple(black[0, 0, :3]) == (0, 0, 0)
    white = filters.hue_saturation(image, lightness=100)
    assert tuple(white[0, 0, :3]) == (255, 255, 255)


def test_hue_saturation_neutral_returns_copy():
    image = solid()
    result = filters.hue_saturation(image)
    assert np.array_equal(result, image)
    assert result is not image


# -------------------------------------------------------------- blur/sharpen
def test_gaussian_blur_spreads_alpha_without_dark_halo():
    image = np.zeros((15, 15, 4), dtype=np.uint8)
    image[7, 7] = (255, 255, 255, 255)
    result = filters.gaussian_blur(image, 2.0)

    assert result.shape == image.shape
    assert result.dtype == np.uint8
    assert result[7, 7, 3] > result[7, 9, 3]
    assert result[7, 8, 3] > 0
    assert tuple(result[7, 7, :3]) == (255, 255, 255)
    assert result[7, 7, 3] < 255
    assert 200 <= int(result[..., 3].sum()) <= 255


def test_gaussian_blur_zero_radius_returns_copy():
    image = solid()
    result = filters.gaussian_blur(image, 0.0)
    assert np.array_equal(result, image)
    assert result is not image


def test_unsharp_mask_sharpens_edges_and_preserves_alpha():
    image = np.zeros((7, 7, 4), dtype=np.uint8)
    image[..., :3] = 100
    image[..., 3] = 200
    image[3, 3, :3] = 200

    result = filters.unsharp_mask(image, amount=150, radius=1.0, threshold=0)
    assert result[3, 3, 0] >= 200
    assert result[3, 4, 0] <= 100
    assert np.all(result[..., 3] == 200)


def test_unsharp_mask_threshold_and_flat_image():
    flat = solid((120, 120, 120, 255))
    assert np.array_equal(filters.unsharp_mask(flat), flat)

    image = np.zeros((7, 7, 4), dtype=np.uint8)
    image[..., :3] = 100
    image[..., 3] = 255
    image[3, 3, :3] = 140
    untouched = filters.unsharp_mask(image, amount=100, radius=1.0, threshold=255)
    assert np.array_equal(untouched, image)
    assert np.array_equal(filters.unsharp_mask(image, amount=0), image)


# ---------------------------------------------------------------- document
def test_document_apply_filter_undo_redo():
    document = make_document()
    layer = document.add_layer(name="Layer", color=(10, 20, 30, 255), record=False)
    document.mark_clean()

    result = filters.invert(layer.pixels)
    assert document.apply_layer_filter(result, "Invert", layer)
    assert tuple(layer.pixels[0, 0]) == (245, 235, 225, 255)
    assert document.modified
    assert document.history.can_undo

    assert document.undo()
    assert tuple(layer.pixels[0, 0]) == (10, 20, 30, 255)
    assert document.redo()
    assert tuple(layer.pixels[0, 0]) == (245, 235, 225, 255)


def test_document_filter_respects_selection():
    document = make_document(10, 10)
    layer = document.add_layer(name="Layer", color=(100, 100, 100, 255), record=False)
    document.set_selection(Selection.from_rect(10, 10, QRectF(2, 2, 4, 4)))

    result = filters.invert(layer.pixels)
    assert document.apply_layer_filter(result, "Invert", layer)
    assert tuple(layer.pixels[0, 0]) == (100, 100, 100, 255)
    assert tuple(layer.pixels[3, 3]) == (155, 155, 155, 255)

    assert document.undo()
    assert tuple(layer.pixels[3, 3]) == (100, 100, 100, 255)


def test_document_filter_rasterizes_text_and_undo_restores():
    document = make_document(200, 100)
    layer = document.add_text_layer(TextProperties("Filter", font_size=24), record=False)
    assert layer.kind == LayerKind.TEXT

    assert document.apply_layer_filter(filters.invert(layer.pixels), "Invert", layer)
    assert layer.kind == LayerKind.PIXEL
    assert layer.text is None

    assert document.undo()
    assert layer.kind == LayerKind.TEXT
    assert layer.text == TextProperties("Filter", font_size=24)


def test_document_filter_keeps_mask_and_blocks_locked_layer():
    document = make_document()
    layer = document.add_layer(name="Layer", color=(100, 100, 100, 255), record=False)
    document.add_layer_mask(layer, record=False)
    mask_before = layer.mask.copy()

    assert document.apply_layer_filter(
        filters.invert(layer.pixels), "Invert", layer
    )
    assert np.array_equal(layer.mask, mask_before)

    layer.locked = True
    with pytest.raises(ValueError):
        document.apply_layer_filter(layer.pixels, "Invert", layer)


def test_document_filter_validates_input_and_no_active_layer():
    document = make_document()
    with pytest.raises(ValueError):
        document.apply_layer_filter(np.zeros((2, 2, 4), dtype=np.uint8), "Invert")

    layer = document.add_layer(name="Layer", color=(1, 2, 3, 255), record=False)
    with pytest.raises(ValueError):
        document.apply_layer_filter(np.zeros((2, 2, 4), dtype=np.uint8), "Invert", layer)
    assert not document.apply_layer_filter(layer.pixels.copy(), "Invert", layer)
    assert not document.history.can_undo
