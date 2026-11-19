"""Kiểm thử layer hình khối: render, thuộc tính, Document API và Undo."""

from __future__ import annotations

import numpy as np
import pytest

from core.document import Document
from core.shape_layer import ShapeProperties, render_shape


def test_rectangle_fill_and_transparent_outside():
    properties = ShapeProperties(
        width=40,
        height=30,
        fill_color=(10, 20, 30, 255),
        stroke_width=0,
    )
    pixels = render_shape(properties)
    assert pixels.shape == (30, 40, 4)
    assert pixels.dtype == np.uint8
    assert tuple(pixels[15, 20]) == (10, 20, 30, 255)


def test_ellipse_is_transparent_in_corners():
    properties = ShapeProperties(
        kind="ellipse",
        width=40,
        height=30,
        fill_color=(200, 60, 40, 255),
    )
    pixels = render_shape(properties)
    assert tuple(pixels[15, 20]) == (200, 60, 40, 255)
    assert pixels[0, 0, 3] == 0


def test_rounded_rectangle_rounds_corner():
    straight = render_shape(
        ShapeProperties(width=40, height=30, fill_color=(80, 80, 80, 255))
    )
    rounded = render_shape(
        ShapeProperties(
            kind="rounded_rectangle",
            width=40,
            height=30,
            fill_color=(80, 80, 80, 255),
            corner_radius=12.0,
        )
    )
    assert straight[1, 1, 3] == 255
    assert rounded[1, 1, 3] == 0
    assert tuple(rounded[15, 20]) == (80, 80, 80, 255)


def test_stroke_only_shape_keeps_center_transparent():
    properties = ShapeProperties(
        width=40,
        height=30,
        fill_color=None,
        stroke_color=(255, 255, 255, 255),
        stroke_width=4,
    )
    pixels = render_shape(properties)
    assert pixels[15, 20, 3] == 0
    assert pixels[15, 2, 3] > 200


def test_rejects_hidden_shape_without_fill_or_stroke():
    with pytest.raises(ValueError, match="màu tô hoặc viền"):
        ShapeProperties(fill_color=None, stroke_width=0)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"kind": "triangle"}, "Loại hình"),
        ({"width": 0}, "Kích thước"),
        ({"height": 40000}, "Kích thước"),
        ({"width": 20000, "height": 20000}, "giới hạn"),
        ({"stroke_width": 800}, "Độ dày"),
        ({"width": 20, "height": 20, "stroke_width": 15}, "quá dày"),
        ({"corner_radius": -1.0}, "Bán kính"),
        ({"fill_color": (300, 0, 0, 255)}, "Màu tô"),
    ],
)
def test_invalid_properties_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ShapeProperties(**kwargs)


def test_radius_is_clamped_and_ignored_for_other_kinds():
    rounded = ShapeProperties(
        kind="rounded_rectangle", width=40, height=30, corner_radius=100.0
    )
    assert rounded.corner_radius == 15.0
    rectangle = ShapeProperties(kind="rectangle", width=40, height=30, corner_radius=8.0)
    assert rectangle.corner_radius == 0.0


def test_dict_roundtrip_and_defaults():
    properties = ShapeProperties(
        kind="ellipse",
        width=90,
        height=70,
        fill_color=None,
        stroke_color=(1, 2, 3, 4),
        stroke_width=3,
    )
    assert ShapeProperties.from_dict(properties.to_dict()) == properties
    legacy = ShapeProperties.from_dict({"kind": "rectangle", "width": 10, "height": 10})
    assert legacy.fill_color == (59, 110, 165, 255)


def test_document_add_update_rasterize_with_undo():
    document = Document(200, 150)
    original = ShapeProperties(
        kind="rounded_rectangle", width=80, height=50, corner_radius=10.0
    )
    layer = document.add_shape_layer(original, x=12, y=14)
    assert layer.kind == "shape"
    assert layer.shape == original
    assert (layer.offset_x, layer.offset_y) == (12, 14)
    assert layer.has_pixels()

    updated = ShapeProperties(kind="ellipse", width=60, height=40)
    assert document.update_shape_layer(updated, layer)
    assert layer.kind == "shape"
    assert layer.shape == updated
    assert (layer.width, layer.height) == (60, 40)

    assert document.undo()
    assert layer.shape == original
    assert (layer.width, layer.height) == (80, 50)

    assert document.redo()
    assert layer.shape == updated

    assert document.rasterize_shape_layer(layer)
    assert layer.kind == "pixel"
    assert layer.shape is None
    assert document.undo()
    assert layer.kind == "shape"
    assert layer.shape == updated


def test_update_shape_is_blocked_by_mask():
    document = Document(100, 80)
    layer = document.add_shape_layer(ShapeProperties(width=40, height=30))
    layer.set_mask(np.full((layer.height, layer.width), 255, dtype=np.uint8))
    with pytest.raises(ValueError, match="mask"):
        document.update_shape_layer(ShapeProperties(kind="ellipse"), layer)


def test_transform_and_filter_rasterize_shape():
    document = Document(100, 80)
    layer = document.add_shape_layer(ShapeProperties(width=40, height=30))
    assert document.transform_layer("rotate_cw", layer)
    assert layer.kind == "pixel"
    assert layer.shape is None
    assert document.undo()
    assert layer.kind == "shape"
    assert layer.shape is not None

    filtered = layer.pixels.copy()
    filtered[..., 3] = 128
    assert document.apply_layer_filter(filtered, "Test", layer)
    assert layer.kind == "pixel"
    assert layer.shape is None
    assert document.undo()
    assert layer.kind == "shape"
