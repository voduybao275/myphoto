"""Kiểm thử layer văn bản: thuộc tính, render, Document API, Undo/Redo và mask."""

from __future__ import annotations

import numpy as np
import pytest

from core.document import Document
from core.layer import LayerKind
from core.text_layer import (
    MAX_FONT_SIZE,
    MAX_KERNING,
    MAX_LETTER_SPACING,
    MAX_LINE_SPACING,
    MAX_LINES,
    MAX_PATH_BEND,
    MAX_TEXT_LENGTH,
    MAX_WARP_BEND,
    MIN_KERNING,
    MIN_LETTER_SPACING,
    MIN_LINE_SPACING,
    MIN_PATH_BEND,
    MIN_WARP_BEND,
    PATH_STYLES,
    WARP_STYLES,
    TextProperties,
    TextRun,
    format_kerning_pairs,
    parse_kerning_pairs,
    render_text,
    text_size,
)


def make_document(width=400, height=300):
    return Document(width, height, dpi=72, name="Text")


def sample(**overrides) -> TextProperties:
    data = {"text": "Hello", "font_size": 40, "color": (220, 80, 40, 255)}
    data.update(overrides)
    return TextProperties(**data)


# ------------------------------------------------------------------ properties
@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_text_rejected(text):
    with pytest.raises(ValueError):
        TextProperties(text)


def test_text_limits_rejected():
    with pytest.raises(ValueError):
        TextProperties("a" * (MAX_TEXT_LENGTH + 1))
    with pytest.raises(ValueError):
        TextProperties("\n".join(["a"] * (MAX_LINES + 1)))


@pytest.mark.parametrize("size", [0, -1, MAX_FONT_SIZE + 1, "abc"])
def test_invalid_font_size_rejected(size):
    with pytest.raises(ValueError):
        TextProperties("Hello", font_size=size)


@pytest.mark.parametrize(
    "color", [(255, 0, 0), (255, 0, 0, 300), (255, 0, 0, -1), "red"]
)
def test_invalid_color_rejected(color):
    with pytest.raises(ValueError):
        TextProperties("Hello", color=color)


def test_invalid_alignment_rejected():
    with pytest.raises(ValueError):
        TextProperties("Hello", alignment="justify")


@pytest.mark.parametrize("spacing", [MIN_LINE_SPACING - 0.1, MAX_LINE_SPACING + 0.1, 0, "abc", None])
def test_invalid_line_spacing_rejected(spacing):
    with pytest.raises(ValueError):
        TextProperties("Hello", line_spacing=spacing)


@pytest.mark.parametrize(
    "spacing", [MIN_LETTER_SPACING - 1, MAX_LETTER_SPACING + 1, "abc", None]
)
def test_invalid_letter_spacing_rejected(spacing):
    with pytest.raises(ValueError):
        TextProperties("Hello", letter_spacing=spacing)


def test_spacing_normalized_and_defaults_for_old_projects():
    properties = TextProperties(
        text="Hi",
        line_spacing="1.456",
        letter_spacing="6.4",
    )
    assert properties.line_spacing == 1.46
    assert properties.letter_spacing == 6

    legacy = TextProperties.from_dict({"text": "Hi", "font_size": 24})
    assert legacy.line_spacing == 1.0
    assert legacy.letter_spacing == 0


def test_properties_normalized_and_serialized():
    properties = TextProperties(
        text="  Xin chào\n",
        font_family="  Arial ",
        font_size="36",
        color=(1, 2, 3, 4),
        bold=1,
        alignment="CENTER",
        line_spacing=1.4,
        letter_spacing=3,
    )
    assert properties.font_family == "Arial"
    assert properties.font_size == 36
    assert properties.color == (1, 2, 3, 4)
    assert properties.bold is True
    assert properties.alignment == "center"
    assert properties.line_spacing == 1.4
    assert properties.letter_spacing == 3
    assert properties.default_name == "Xin chào"

    restored = TextProperties.from_dict(properties.to_dict())
    assert restored == properties


def test_from_dict_rejects_invalid_data():
    with pytest.raises(ValueError):
        TextProperties.from_dict("not-a-dict")
    with pytest.raises(ValueError):
        TextProperties.from_dict({"text": ""})
    with pytest.raises(ValueError):
        TextProperties.from_dict({"text": "Hi", "alignment": "diagonal"})


def test_default_name_truncated():
    properties = TextProperties("a" * 100, font_size=20)
    assert properties.default_name == "a" * 40


# ---------------------------------------------------------------------- render
def test_render_text_is_transparent_background_with_ink():
    properties = sample(text="Hello", font_size=48)
    width, height = text_size(properties)
    pixels = render_text(properties)

    assert pixels.dtype == np.uint8
    assert pixels.shape == (height, width, 4)
    assert 0 in pixels[..., 3]
    assert pixels[..., 3].max() == 255
    # Góc trên trái nằm trong phần padding nên phải trong suốt.
    assert pixels[0, 0, 3] == 0

    opaque = pixels[pixels[..., 3] == 255]
    assert opaque.size
    assert tuple(opaque[0][:3]) == (220, 80, 40)


def test_multiline_render_is_taller():
    single = sample(text="One line")
    multiple = sample(text="One\nTwo\nThree")
    assert text_size(multiple)[1] > text_size(single)[1]


def test_line_spacing_increases_height():
    base = sample(text="One\nTwo\nThree")
    wide = sample(text="One\nTwo\nThree", line_spacing=2.0)
    assert text_size(wide)[1] > text_size(base)[1]
    pixels = render_text(wide)
    assert pixels.shape[:2] == (text_size(wide)[1], text_size(wide)[0])
    assert pixels[..., 3].max() == 255


def test_letter_spacing_increases_width():
    plain = sample(text="ABCDE", letter_spacing=0)
    spaced = sample(text="ABCDE", letter_spacing=6)
    assert text_size(spaced)[0] > text_size(plain)[0]
    pixels = render_text(spaced)
    assert pixels.shape[:2] == (text_size(spaced)[1], text_size(spaced)[0])
    assert pixels[..., 3].max() == 255


def test_single_line_height_unchanged_by_line_spacing():
    base = sample(text="Hello")
    wide = sample(text="Hello", line_spacing=2.0)
    assert text_size(wide)[1] == text_size(base)[1]


@pytest.mark.parametrize("alignment", ["left", "center", "right"])
def test_spacing_with_alignment_renders(alignment):
    pixels = render_text(
        sample(text="Align\nline", alignment=alignment, line_spacing=1.6, letter_spacing=2)
    )
    assert pixels[..., 3].max() == 255


@pytest.mark.parametrize("alignment", ["left", "center", "right"])
def test_alignment_variants_render(alignment):
    pixels = render_text(sample(text="Align", alignment=alignment))
    assert pixels[..., 3].max() == 255


# --------------------------------------------------------------- document API
def test_add_text_layer_centered_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Hi"))

    assert layer.kind == LayerKind.TEXT
    assert layer.text == sample(text="Hi")
    assert (layer.width, layer.height) == text_size(layer.text)
    assert layer.offset_x == (document.width - layer.width) // 2
    assert layer.offset_y == (document.height - layer.height) // 2
    assert document.active_layer is layer
    assert document.history.can_undo
    assert layer.pixels[..., 3].max() == 255

    assert document.undo()
    assert len(document.layers) == 0
    assert document.redo()
    restored = document.layers[0]
    assert restored.kind == LayerKind.TEXT
    assert restored.text == sample(text="Hi")


def test_add_text_layer_at_position_without_history():
    document = make_document()
    document.add_layer(name="Background", color=(0, 0, 0, 255), record=False)
    layer = document.add_text_layer(sample(text="Pin"), x=12, y=30, record=False)

    assert (layer.offset_x, layer.offset_y) == (12, 30)
    assert not document.history.can_undo
    assert not document.modified


def test_add_text_layer_rejects_bad_type():
    document = make_document()
    with pytest.raises(TypeError):
        document.add_text_layer("Hello")


def test_update_text_layer_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Old", font_size=30), record=False)
    old_size = (layer.width, layer.height)
    old_pixels = layer.pixels.copy()

    new_properties = sample(text="New content", font_size=52, bold=True)
    assert document.update_text_layer(new_properties)
    assert layer.kind == LayerKind.TEXT
    assert layer.text == new_properties
    assert (layer.width, layer.height) == text_size(new_properties)
    assert (layer.width, layer.height) != old_size

    assert document.undo()
    assert layer.text == sample(text="Old", font_size=30)
    assert (layer.width, layer.height) == old_size
    assert np.array_equal(layer.pixels, old_pixels)

    assert document.redo()
    assert layer.text == new_properties


def test_update_text_spacing_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Line one\nLine two"), record=False)
    old_size = (layer.width, layer.height)

    new_properties = sample(
        text="Line one\nLine two", line_spacing=1.8, letter_spacing=4
    )
    assert document.update_text_layer(new_properties)
    assert layer.text == new_properties
    assert layer.text.line_spacing == 1.8
    assert layer.text.letter_spacing == 4
    assert (layer.width, layer.height) == text_size(new_properties)
    assert layer.height > old_size[1]

    assert document.undo()
    assert layer.text == sample(text="Line one\nLine two")
    assert (layer.width, layer.height) == old_size


def test_update_text_layer_without_changes_returns_false():
    document = make_document()
    properties = sample(text="Same")
    document.add_text_layer(properties, record=False)
    assert not document.update_text_layer(properties)
    assert not document.history.can_undo


def test_update_requires_text_layer():
    document = make_document()
    document.add_layer(name="Pixel", color=(0, 0, 0, 255), record=False)
    with pytest.raises(ValueError):
        document.update_text_layer(sample())
    document.remove_layer(record=False)
    with pytest.raises(ValueError):
        document.update_text_layer(sample())


def test_rasterize_text_layer_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Raster"))
    pixels_before = layer.pixels.copy()

    assert document.rasterize_text_layer()
    assert layer.kind == LayerKind.PIXEL
    assert layer.text is None
    assert np.array_equal(layer.pixels, pixels_before)
    assert not document.rasterize_text_layer()  # đã là pixel

    assert document.undo()
    assert layer.kind == LayerKind.TEXT
    assert layer.text == sample(text="Raster")


def test_duplicate_text_layer_keeps_metadata():
    document = make_document()
    layer = document.add_text_layer(sample(text="Copy me"), record=False)
    clone = document.duplicate_layer(layer, record=False)

    assert clone is not layer
    assert clone.kind == LayerKind.TEXT
    assert clone.text == layer.text

    document.rasterize_text_layer(clone, record=False)
    assert clone.kind == LayerKind.PIXEL
    assert layer.kind == LayerKind.TEXT


def test_mask_blocks_editing_and_apply_rasterizes():
    document = make_document()
    layer = document.add_text_layer(sample(text="Masked"))
    assert document.add_layer_mask(layer)

    with pytest.raises(ValueError):
        document.update_text_layer(sample(text="Nope"), layer)

    assert document.apply_layer_mask(layer)
    assert layer.kind == LayerKind.PIXEL
    assert layer.text is None
    assert not document.rasterize_text_layer(layer)

    assert document.undo()
    assert layer.kind == LayerKind.TEXT
    assert layer.text == sample(text="Masked")
    assert layer.mask is not None


def test_pixel_transform_rasterizes_text_and_undo_restores():
    document = make_document()
    layer = document.add_text_layer(sample(text="Spin"), record=False)
    old_size = (layer.width, layer.height)

    assert document.transform_layer("rotate_cw", layer)
    assert layer.kind == LayerKind.PIXEL
    assert layer.text is None
    assert (layer.width, layer.height) == (old_size[1], old_size[0])

    assert document.undo()
    assert layer.kind == LayerKind.TEXT
    assert layer.text == sample(text="Spin")
    assert (layer.width, layer.height) == old_size


def test_canvas_rotate_rasterizes_text():
    document = make_document()
    layer = document.add_text_layer(sample(text="Canvas"))
    assert document.rotate_canvas("cw")
    assert layer.kind == LayerKind.PIXEL
    assert layer.text is None
    assert document.undo()
    assert layer.kind == LayerKind.TEXT


def test_crop_keeps_text_editable():
    document = make_document()
    layer = document.add_text_layer(sample(text="Crop"))
    assert document.crop(0, 0, document.width - 20, document.height - 20)
    assert layer.kind == LayerKind.TEXT
    assert layer.text is not None
    assert document.update_text_layer(sample(text="Still editable")) is True


# ------------------------------------------------------------------ text runs
def test_runs_default_to_single_run_from_flat_fields():
    properties = sample(text="Hello", font_size=32, color=(10, 20, 30, 255), bold=True)
    assert len(properties.runs) == 1
    run = properties.runs[0]
    assert run.text == "Hello"
    assert run.font_size == 32
    assert run.color == (10, 20, 30, 255)
    assert run.bold is True


def test_runs_derive_text_and_normalize():
    properties = TextProperties(
        runs=(
            TextRun("Đậm ", font_size="36", color=(255, 0, 0, 255), bold=1),
            TextRun("nghiêng", font_size=24, color=(0, 0, 255, 255), italic=True),
        ),
        alignment="center",
        line_spacing=1.3,
        letter_spacing=2,
    )
    assert properties.text == "Đậm nghiêng"
    assert properties.alignment == "center"
    assert properties.runs[0].font_size == 36
    assert properties.runs[0].bold is True
    assert properties.runs[1].italic is True
    assert properties.default_name == "Đậm nghiêng"

    restored = TextProperties.from_dict(properties.to_dict())
    assert restored == properties
    assert len(restored.runs) == 2


def test_runs_only_properties_require_visible_text():
    with pytest.raises(ValueError):
        TextProperties(runs=(TextRun(""), TextRun("   ")))
    with pytest.raises(ValueError):
        TextProperties(runs=(TextRun("a" * (MAX_TEXT_LENGTH + 1)),))


@pytest.mark.parametrize("size", [0, -5, MAX_FONT_SIZE + 1, "abc"])
def test_text_run_invalid_size_rejected(size):
    with pytest.raises(ValueError):
        TextRun("Hi", font_size=size)


@pytest.mark.parametrize("color", [(1, 2, 3), (0, 0, 0, 999), "red"])
def test_text_run_invalid_color_rejected(color):
    with pytest.raises(ValueError):
        TextRun("Hi", color=color)


def test_text_run_dict_roundtrip_and_validation():
    run = TextRun("Xin", font_family=" Arial ", font_size=28, bold=True)
    assert run.font_family == "Arial"
    assert TextRun.from_dict(run.to_dict()) == run
    with pytest.raises(ValueError):
        TextRun.from_dict("nope")
    with pytest.raises(TypeError):
        TextProperties(runs=("not-a-run",))


def test_from_dict_accepts_runs_and_legacy_payload():
    legacy = TextProperties.from_dict({"text": "Cũ", "font_size": 22})
    assert len(legacy.runs) == 1
    assert legacy.runs[0].font_size == 22

    modern = TextProperties.from_dict(
        {
            "text": "A B",
            "runs": [
                {"text": "A ", "font_size": 48, "color": [255, 0, 0, 255]},
                {"text": "B", "font_size": 20, "color": [0, 0, 255, 255]},
            ],
        }
    )
    assert modern.text == "A B"
    assert modern.runs[1].font_size == 20

    with pytest.raises(ValueError):
        TextProperties.from_dict({"runs": "không-phải-list"})


def test_multi_run_render_contains_each_color():
    properties = TextProperties(
        runs=(
            TextRun("Đỏ ", font_size=48, color=(255, 40, 40, 255), bold=True),
            TextRun("Xanh", font_size=48, color=(40, 40, 255, 255)),
        )
    )
    pixels = render_text(properties)
    red = ((pixels[..., 0] > 180) & (pixels[..., 1] < 140)).sum()
    blue = ((pixels[..., 2] > 180) & (pixels[..., 0] < 140)).sum()
    assert red > 0
    assert blue > 0


def test_mixed_font_sizes_share_line_and_raise_height():
    small = TextProperties(runs=(TextRun("Nhỏ", font_size=20),))
    large = TextProperties(runs=(TextRun("Lớn", font_size=64),))
    mixed = TextProperties(
        runs=(TextRun("Nhỏ ", font_size=20), TextRun("Lớn", font_size=64))
    )
    small_width, small_height = text_size(small)
    _, large_height = text_size(large)
    mixed_width, mixed_height = text_size(mixed)

    assert mixed_height >= large_height
    assert mixed_height > small_height
    assert mixed_width > small_width


def test_runs_survive_newlines_and_alignment():
    properties = TextProperties(
        runs=(TextRun("Một\n", font_size=30), TextRun("Hai", font_size=30)),
        alignment="right",
    )
    assert properties.text == "Một\nHai"
    assert render_text(properties).shape[0] > text_size(sample(text="Một"))[1]


def test_update_text_layer_with_runs_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Plain"))
    rich = TextProperties(
        runs=(
            TextRun("Rich ", font_size=48, color=(255, 0, 0, 255), bold=True),
            TextRun("text", font_size=24, color=(0, 128, 255, 255), italic=True),
        ),
        alignment="center",
    )
    assert document.update_text_layer(rich) is True
    assert layer.text == rich
    assert layer.text.text == "Rich text"
    assert np.array_equal(layer.pixels, render_text(rich))

    assert document.undo()
    assert layer.text == sample(text="Plain")
    assert np.array_equal(layer.pixels, render_text(sample(text="Plain")))


# ------------------------------------------------------------------ uốn chữ
def test_invalid_warp_style_and_bend_rejected():
    with pytest.raises(ValueError):
        TextProperties("Warp", warp_style="spiral")
    for bend in (MIN_WARP_BEND - 1, MAX_WARP_BEND + 1, "abc", None):
        with pytest.raises(ValueError):
            TextProperties("Warp", warp_style="arc", warp_bend=bend)


def test_warp_none_normalizes_bend_and_zero_bend_is_plain():
    normalized = TextProperties("Warp", warp_style="none", warp_bend=75)
    assert normalized.warp_style == "none"
    assert normalized.warp_bend == 0

    plain = sample(text="Warp")
    zero_bend = sample(text="Warp", warp_style="wave", warp_bend=0)
    assert np.array_equal(render_text(plain), render_text(zero_bend))
    assert text_size(plain) == text_size(zero_bend)


def test_warp_dict_roundtrip_and_legacy_defaults():
    properties = sample(text="Warp", warp_style="Wave", warp_bend="40")
    assert properties.warp_style == "wave"
    assert properties.warp_bend == 40
    assert TextProperties.from_dict(properties.to_dict()) == properties

    legacy = TextProperties.from_dict({"text": "Cũ", "font_size": 24})
    assert legacy.warp_style == "none"
    assert legacy.warp_bend == 0


@pytest.mark.parametrize("style", WARP_STYLES[1:])
def test_each_warp_style_renders_and_matches_size(style):
    properties = sample(text="MY PHOTO", font_size=48, warp_style=style, warp_bend=70)
    pixels = render_text(properties)
    assert pixels.ndim == 3 and pixels.shape[2] == 4
    assert (pixels.shape[1], pixels.shape[0]) == text_size(properties)
    assert (pixels[..., 3] > 0).sum() > 0


def test_arc_bends_center_upward():
    properties = sample(text="MY PHOTO", font_size=48, warp_style="arc", warp_bend=80)
    alpha = render_text(properties)[..., 3]
    tops = np.full(alpha.shape[1], alpha.shape[0])
    for column in range(alpha.shape[1]):
        rows = np.flatnonzero(alpha[:, column] > 0)
        if rows.size:
            tops[column] = rows[0]
    width = alpha.shape[1]
    center_top = tops[width * 2 // 5 : width * 3 // 5].min()
    edge_top = min(tops[: width // 10].min(), tops[-width // 10 :].min())
    assert center_top < edge_top - 3


def test_warp_extreme_bend_keeps_ink_inside_canvas():
    for style in ("arc", "bulge", "squeeze", "wave", "flag", "fish", "rise", "twist"):
        pixels = render_text(
            sample(text="MY PHOTO", font_size=48, warp_style=style, warp_bend=100)
        )
        alpha = pixels[..., 3]
        border = np.concatenate(
            (alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1])
        )
        assert border.max() == 0, style


def test_warp_update_text_layer_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Warp me", font_size=36))
    plain_pixels = layer.pixels.copy()
    plain_size = (layer.width, layer.height)

    warped = sample(
        text="Warp me",
        font_size=36,
        warp_style="wave",
        warp_bend=60,
        alignment="center",
    )
    assert document.update_text_layer(warped) is True
    assert layer.text == warped
    assert np.array_equal(layer.pixels, render_text(warped))
    assert not np.array_equal(layer.pixels, plain_pixels)

    assert document.undo()
    assert layer.text == sample(text="Warp me", font_size=36)
    assert (layer.width, layer.height) == plain_size
    assert np.array_equal(layer.pixels, plain_pixels)


# ---------------------------------------------------- kerning và đường dẫn
def test_parse_and_format_kerning_pairs_roundtrip():
    pairs = parse_kerning_pairs("AV=-4; To=-2, WA=3")
    assert pairs == (("AV", -4), ("To", -2), ("WA", 3))
    assert parse_kerning_pairs(format_kerning_pairs(pairs)) == pairs
    assert parse_kerning_pairs("   ") == ()
    assert parse_kerning_pairs("AV = 5") == (("AV", 5),)


@pytest.mark.parametrize("value", ["AV", "ABC=-2", "AV=abc", "A=2"])
def test_parse_kerning_pairs_rejects_bad_entries(value):
    with pytest.raises(ValueError):
        parse_kerning_pairs(value)


def test_kerning_pair_limits_rejected():
    with pytest.raises(ValueError):
        parse_kerning_pairs(f"AV={MAX_KERNING + 1}")
    with pytest.raises(ValueError):
        parse_kerning_pairs(f"AV={MIN_KERNING - 1}")
    with pytest.raises(ValueError):
        TextProperties("AV", kerning_pairs=(("AV", MAX_KERNING + 1),))
    with pytest.raises(ValueError):
        TextProperties("AV", kerning_pairs=(("AV",),))


def test_kerning_pairs_normalized_deduplicated_and_serialized():
    properties = TextProperties(
        "AV To", kerning_pairs=(("AV", -4), ("AV", -7), ("To", 0), ["WA", "3"])
    )
    assert properties.kerning_pairs == (("AV", -7), ("WA", 3))
    restored = TextProperties.from_dict(properties.to_dict())
    assert restored == properties
    assert restored.kerning_pairs == (("AV", -7), ("WA", 3))

    legacy = TextProperties.from_dict({"text": "Cũ", "font_size": 20})
    assert legacy.kerning_pairs == ()
    assert legacy.path_style == "none"
    assert legacy.path_bend == 0


def test_manual_kerning_tightens_and_widens_text():
    plain = sample(text="AVATAR", font_size=64)
    tight = sample(
        text="AVATAR", font_size=64, kerning_pairs=(("AV", -30), ("VA", -30))
    )
    loose = sample(
        text="AVATAR", font_size=64, kerning_pairs=(("AV", 30), ("VA", 30))
    )
    plain_width, plain_height = text_size(plain)
    tight_width, _ = text_size(tight)
    loose_width, _ = text_size(loose)

    assert tight_width < plain_width
    assert loose_width > plain_width
    for properties, width in ((tight, tight_width), (loose, loose_width)):
        pixels = render_text(properties)
        assert (pixels.shape[1], pixels.shape[0]) == (width, plain_height)
        assert pixels.shape[:2] == (text_size(properties)[1], text_size(properties)[0])
        assert pixels[..., 3].max() == 255
        assert (pixels[..., 3] > 0).sum() > 0


def test_kerning_across_rich_runs_renders_each_color():
    properties = TextProperties(
        runs=(
            TextRun("AV", font_size=48, color=(255, 40, 40, 255)),
            TextRun("ATAR", font_size=48, color=(40, 40, 255, 255)),
        ),
        kerning_pairs=(("VA", -25),),
    )
    pixels = render_text(properties)
    red = ((pixels[..., 0] > 180) & (pixels[..., 1] < 140)).sum()
    blue = ((pixels[..., 2] > 180) & (pixels[..., 0] < 140)).sum()
    assert red > 0
    assert blue > 0


def test_invalid_path_style_and_bend_rejected():
    with pytest.raises(ValueError):
        TextProperties("Path", path_style="spiral")
    for bend in (MIN_PATH_BEND - 1, MAX_PATH_BEND + 1, "abc", None):
        with pytest.raises(ValueError):
            TextProperties("Path", path_style="arc", path_bend=bend)


def test_path_none_normalizes_bend_and_zero_bend_is_plain():
    normalized = TextProperties("Path", path_style="none", path_bend=70)
    assert normalized.path_style == "none"
    assert normalized.path_bend == 0

    plain = sample(text="Path")
    zero = sample(
        text="Path",
        path_style="arc",
        path_bend=0,
        warp_style="wave",
        warp_bend=70,
    )
    assert np.array_equal(render_text(plain), render_text(zero))
    assert text_size(plain) == text_size(zero)


def test_path_dict_roundtrip():
    properties = sample(
        text="Cong",
        path_style="Circle",
        path_bend="45",
        kerning_pairs=(("Co", -2),),
    )
    assert properties.path_style == "circle"
    assert properties.path_bend == 45
    assert TextProperties.from_dict(properties.to_dict()) == properties

    restored = TextProperties.from_dict(
        {
            "text": "Cong",
            "path_style": "arc",
            "path_bend": 30,
            "kerning_pairs": {"Co": -2},
        }
    )
    assert restored.kerning_pairs == (("Co", -2),)
    assert restored.path_style == "arc"


@pytest.mark.parametrize("style", PATH_STYLES[1:])
def test_each_path_style_renders_inside_canvas(style):
    properties = sample(
        text="MY PHOTO", font_size=48, path_style=style, path_bend=70
    )
    pixels = render_text(properties)
    assert pixels.ndim == 3 and pixels.shape[2] == 4
    assert (pixels.shape[1], pixels.shape[0]) == text_size(properties)
    assert (pixels[..., 3] > 0).sum() > 0
    border = np.concatenate(
        (pixels[..., 3][0], pixels[..., 3][-1], pixels[..., 3][:, 0], pixels[..., 3][:, -1])
    )
    assert border.max() == 0, style


def test_path_bend_direction_changes_ink_distribution():
    up = render_text(
        sample(text="MY PHOTO", font_size=48, path_style="arc", path_bend=80)
    )
    down = render_text(
        sample(text="MY PHOTO", font_size=48, path_style="arc", path_bend=-80)
    )
    assert up.shape != down.shape or not np.array_equal(up, down)


def test_path_takes_precedence_over_warp():
    path_only = sample(text="PATH", font_size=40, path_style="arc", path_bend=60)
    both = sample(
        text="PATH",
        font_size=40,
        path_style="arc",
        path_bend=60,
        warp_style="wave",
        warp_bend=80,
    )
    assert np.array_equal(render_text(path_only), render_text(both))


def test_path_flattens_newlines_to_spaces():
    properties = sample(
        text="MY\nPHOTO", font_size=40, path_style="arc", path_bend=50
    )
    pixels = render_text(properties)
    assert pixels[..., 3].max() == 255
    flattened = sample(
        text="MY PHOTO", font_size=40, path_style="arc", path_bend=50
    )
    assert pixels.shape == render_text(flattened).shape


def test_path_update_text_layer_and_undo():
    document = make_document()
    layer = document.add_text_layer(sample(text="Path me", font_size=36))
    plain_pixels = layer.pixels.copy()
    plain_size = (layer.width, layer.height)

    curved = sample(
        text="Path me",
        font_size=36,
        path_style="s_curve",
        path_bend=65,
        kerning_pairs=(("Pa", -3),),
    )
    assert document.update_text_layer(curved) is True
    assert layer.text == curved
    assert np.array_equal(layer.pixels, render_text(curved))
    assert (layer.width, layer.height) == text_size(curved)

    assert document.undo()
    assert layer.text == sample(text="Path me", font_size=36)
    assert (layer.width, layer.height) == plain_size
    assert np.array_equal(layer.pixels, plain_pixels)
