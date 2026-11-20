"""Xuất nhanh một layer thành CSS, SVG hoặc PNG (dùng cho menu ngữ cảnh)."""

from __future__ import annotations

import base64
import io
import re

import numpy as np
from PIL import Image

from core.fill_layer import render_fill
from core.layer import Layer, LayerKind

_CSS_BLEND_MODES = {
    "normal": "normal",
    "multiply": "multiply",
    "screen": "screen",
    "overlay": "overlay",
    "soft_light": "soft-light",
    "hard_light": "hard-light",
    "darken": "darken",
    "lighten": "lighten",
    "color_dodge": "color-dodge",
    "color_burn": "color-burn",
    "difference": "difference",
    "hue": "hue",
    "saturation": "saturation",
    "color": "color",
    "luminosity": "luminosity",
}


def _unsupported(layer: Layer) -> bool:
    return layer.kind in (LayerKind.GROUP, LayerKind.ADJUSTMENT)


def render_layer_rgba(
    layer: Layer, document_width: int, document_height: int
) -> np.ndarray:
    """Nội dung RGBA của layer, đã áp layer mask (nếu đang bật)."""
    if _unsupported(layer):
        raise ValueError("Nhóm và layer điều chỉnh không có pixel riêng để xuất.")
    if layer.kind == LayerKind.FILL and layer.fill_props is not None:
        pixels = render_fill(layer.fill_props, document_width, document_height)
    else:
        pixels = layer.pixels.copy()
    if (
        layer.mask is not None
        and layer.mask_enabled
        and layer.mask.shape == pixels.shape[:2]
    ):
        alpha = pixels[..., 3].astype(np.uint16)
        mask = layer.mask.astype(np.uint16)
        pixels[..., 3] = ((alpha * mask + 127) // 255).astype(np.uint8)
    return pixels


def _layer_size(
    layer: Layer, document_width: int, document_height: int
) -> tuple[int, int]:
    if layer.kind == LayerKind.FILL:
        return document_width, document_height
    return layer.width, layer.height


def _css_identifier(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-_")
    return f"layer-{slug or 'unnamed'}"


def _css_color(color: tuple[int, int, int, int]) -> str:
    red, green, blue, alpha = (int(value) for value in color)
    if alpha >= 255:
        return f"rgb({red}, {green}, {blue})"
    return f"rgba({red}, {green}, {blue}, {alpha / 255:.3f})"


def _css_value(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _png_data_uri(rgba: np.ndarray) -> str:
    buffer = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgba), "RGBA").save(
        buffer, format="PNG", compress_level=6
    )
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _css_declarations(
    layer: Layer, document_width: int, document_height: int
) -> list[tuple[str, str]]:
    width, height = _layer_size(layer, document_width, document_height)
    left = 0 if layer.kind == LayerKind.FILL else layer.offset_x
    top = 0 if layer.kind == LayerKind.FILL else layer.offset_y
    declarations: list[tuple[str, str]] = [
        ("position", "absolute"),
        ("left", f"{left}px"),
        ("top", f"{top}px"),
        ("width", f"{width}px"),
        ("height", f"{height}px"),
    ]
    if layer.opacity < 0.999:
        declarations.append(("opacity", _css_value(layer.opacity)))
    blend = _CSS_BLEND_MODES.get(layer.blend_mode)
    if blend and blend != "normal" and layer.kind != LayerKind.ADJUSTMENT:
        declarations.append(("mix-blend-mode", blend))

    if layer.kind == LayerKind.TEXT and layer.text is not None:
        text = layer.text
        run = text.runs[0]
        family = run.font_family or "sans-serif"
        declarations.extend(
            [
                ("font-family", f'"{family}"'),
                ("font-size", f"{run.font_size}px"),
                ("color", _css_color(run.color)),
                ("text-align", text.alignment),
                ("line-height", f"{run.font_size * text.line_spacing:.1f}px"),
            ]
        )
        if run.bold:
            declarations.append(("font-weight", "700"))
        if run.italic:
            declarations.append(("font-style", "italic"))
        if text.letter_spacing:
            declarations.append(("letter-spacing", f"{text.letter_spacing}px"))
    elif layer.kind == LayerKind.SHAPE and layer.shape is not None:
        shape = layer.shape
        if shape.fill_color is not None:
            declarations.append(("background-color", _css_color(shape.fill_color)))
        if shape.stroke_width > 0:
            declarations.append(
                ("border", f"{shape.stroke_width}px solid {_css_color(shape.stroke_color)}")
            )
        if shape.kind == "ellipse":
            declarations.append(("border-radius", "50%"))
        elif shape.kind == "rounded_rectangle":
            declarations.append(("border-radius", f"{shape.corner_radius:g}px"))
    elif layer.kind == LayerKind.FILL and layer.fill_props is not None:
        fill = layer.fill_props
        if fill.fill_type == "solid":
            declarations.append(("background", _css_color(fill.color)))
        elif fill.gradient_type == "radial":
            declarations.append(
                (
                    "background",
                    f"radial-gradient(circle, {_css_color(fill.color)}, "
                    f"{_css_color(fill.color2)})",
                )
            )
        else:
            declarations.append(
                (
                    "background",
                    f"linear-gradient({fill.angle}deg, {_css_color(fill.color)}, "
                    f"{_css_color(fill.color2)})",
                )
            )
    else:
        pixels = render_layer_rgba(layer, document_width, document_height)
        if pixels.size and bool(np.any(pixels[..., 3])):
            declarations.extend(
                [
                    ("background-image", f'url("{_png_data_uri(pixels)}")'),
                    ("background-repeat", "no-repeat"),
                    ("background-size", "100% 100%"),
                ]
            )
    return declarations


def layer_to_css(
    layer: Layer, document_width: int, document_height: int
) -> str:
    """CSS cho layer: hình học, opacity, blend mode và nội dung màu/hình/chữ."""
    if _unsupported(layer):
        raise ValueError("Copy CSS không hỗ trợ nhóm hoặc layer điều chỉnh.")
    declarations = _css_declarations(layer, document_width, document_height)
    body = "\n".join(f"  {name}: {value};" for name, value in declarations)
    return f".{_css_identifier(layer.name)} {{\n{body}\n}}\n"


def layer_to_svg(
    layer: Layer, document_width: int, document_height: int
) -> str:
    """SVG tự chứa: nhúng nội dung layer dưới dạng PNG base64."""
    if _unsupported(layer):
        raise ValueError("Copy SVG không hỗ trợ nhóm hoặc layer điều chỉnh.")
    pixels = render_layer_rgba(layer, document_width, document_height)
    width, height = _layer_size(layer, document_width, document_height)
    href = _png_data_uri(pixels)
    attributes = [f'width="{width}"', f'height="{height}"']
    style_parts: list[str] = []
    if layer.opacity < 0.999:
        style_parts.append(f"opacity:{_css_value(layer.opacity)}")
    blend = _CSS_BLEND_MODES.get(layer.blend_mode)
    if blend and blend != "normal" and layer.kind != LayerKind.ADJUSTMENT:
        style_parts.append(f"mix-blend-mode:{blend}")
    style = (
        f' style="{";".join(style_parts)}"' if style_parts else ""
    )
    image = (
        f'  <image x="0" y="0" width="{width}" height="{height}" '
        f'preserveAspectRatio="none" href="{href}"/>'
    )
    if style:
        image = f"  <g{style}>\n{image}\n  </g>"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        + " ".join(attributes)
        + f' viewBox="0 0 {width} {height}">\n'
        + image
        + "\n</svg>\n"
    )
