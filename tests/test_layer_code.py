"""Kiểm thử xuất CSS/SVG và ảnh RGBA của một layer."""

from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image

from core.adjustment_layer import AdjustmentProperties
from core.document import Document
from core.fill_layer import FillProperties
from core.shape_layer import ShapeProperties
from core.text_layer import TextProperties
from formats.layer_code import layer_to_css, layer_to_svg, render_layer_rgba


def test_shape_css_contains_geometry_and_border():
    document = Document(100, 80)
    layer = document.add_shape_layer(
        ShapeProperties(
            kind="rounded_rectangle",
            width=40,
            height=30,
            fill_color=(10, 20, 30, 255),
            stroke_color=(200, 100, 50, 255),
            stroke_width=2,
            corner_radius=6,
        ),
        x=7,
        y=9,
        record=False,
    )
    css = layer_to_css(layer, document.width, document.height)
    assert css.startswith(".layer-")
    assert "left: 7px;" in css
    assert "top: 9px;" in css
    assert "width: 40px;" in css
    assert "height: 30px;" in css
    assert "background-color: rgb(10, 20, 30);" in css
    assert "border: 2px solid rgb(200, 100, 50);" in css
    assert "border-radius: 6px;" in css


def test_text_css_contains_font_and_alignment():
    document = Document(120, 60)
    layer = document.add_text_layer(
        TextProperties(
            text="Hello",
            font_family="Arial",
            font_size=24,
            color=(220, 80, 40, 255),
            alignment="center",
            bold=True,
        ),
        record=False,
    )
    css = layer_to_css(layer, document.width, document.height)
    assert 'font-family: "Arial";' in css
    assert "font-size: 24px;" in css
    assert "color: rgb(220, 80, 40);" in css
    assert "text-align: center;" in css
    assert "font-weight: 700;" in css


def test_gradient_fill_css_and_opacity_blend():
    document = Document(50, 40)
    layer = document.add_fill_layer(
        FillProperties(
            fill_type="gradient",
            color=(255, 0, 0, 255),
            color2=(0, 0, 255, 255),
            gradient_type="linear",
            angle=45,
        ),
        record=False,
    )
    layer.opacity = 0.5
    layer.blend_mode = "multiply"
    css = layer_to_css(layer, document.width, document.height)
    assert "background: linear-gradient(45deg, rgb(255, 0, 0), rgb(0, 0, 255));" in css
    assert "opacity: 0.5;" in css
    assert "mix-blend-mode: multiply;" in css


def test_svg_embeds_png_with_layer_size():
    document = Document(20, 10)
    layer = document.add_shape_layer(
        ShapeProperties(width=4, height=3, fill_color=(1, 2, 3, 255)),
        record=False,
    )
    svg = layer_to_svg(layer, document.width, document.height)
    assert svg.startswith("<svg ")
    assert 'width="4"' in svg
    assert 'height="3"' in svg
    assert 'viewBox="0 0 4 3"' in svg
    payload = svg.split("base64,", 1)[1].split('"', 1)[0]
    with Image.open(io.BytesIO(base64.b64decode(payload))) as image:
        assert image.size == (4, 3)
        assert image.mode == "RGBA"


def test_render_layer_rgba_applies_enabled_mask():
    document = Document(3, 2)
    layer = document.add_layer(color=(10, 20, 30, 255), record=False)
    mask = np.full((2, 3), 255, dtype=np.uint8)
    mask[0, :] = 0
    layer.set_mask(mask)
    pixels = render_layer_rgba(layer, document.width, document.height)
    assert np.all(pixels[0, :, 3] == 0)
    assert np.all(pixels[1, :, 3] == 255)
    layer.mask_enabled = False
    pixels = render_layer_rgba(layer, document.width, document.height)
    assert np.all(pixels[..., 3] == 255)


def test_group_and_adjustment_cannot_be_exported_as_code():
    document = Document(10, 10)
    group = document.add_group(record=False)
    adjustment = document.add_adjustment_layer(
        AdjustmentProperties(kind="invert"), record=False
    )
    with pytest.raises(ValueError, match="hỗ trợ"):
        layer_to_css(group, 10, 10)
    with pytest.raises(ValueError, match="hỗ trợ"):
        layer_to_svg(group, 10, 10)
    with pytest.raises(ValueError, match="pixel"):
        render_layer_rgba(adjustment, 10, 10)
