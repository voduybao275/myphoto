"""Kiểm thử compositor: blend mode, alpha, offset, band và thumbnail."""

from __future__ import annotations

import numpy as np
import pytest

from core.canvas import composite_layers, downsample_rgba
from core.layer import BLEND_MODE_IDS, Layer, LayerKind


def make_layer(width, height, rgba, *, offset=(0, 0), opacity=1.0, mode="normal"):
    layer = Layer(width, height)
    layer.fill(rgba)
    layer.offset_x, layer.offset_y = offset
    layer.opacity = opacity
    layer.blend_mode = mode
    return layer


def test_single_opaque_layer_fast_path():
    layer = make_layer(4, 3, (10, 20, 30, 255))
    result = composite_layers([layer], 4, 3)
    assert result.shape == (3, 4, 4)
    assert result.dtype == np.uint8
    assert np.all(result[..., :3] == (10, 20, 30))
    assert np.all(result[..., 3] == 255)


def test_empty_document_is_transparent():
    result = composite_layers([], 5, 2)
    assert result.shape == (2, 5, 4)
    assert not np.any(result)


def test_hidden_and_zero_opacity_layers_are_ignored():
    hidden = make_layer(3, 3, (255, 0, 0, 255))
    hidden.visible = False
    transparent = make_layer(3, 3, (0, 255, 0, 255), opacity=0.0)
    result = composite_layers([hidden, transparent], 3, 3)
    assert not np.any(result)


def test_offset_and_clipping():
    layer = make_layer(3, 3, (0, 0, 255, 255), offset=(5, 4))
    result = composite_layers([layer], 8, 8)
    assert np.all(result[:4, :, 3] == 0)
    assert np.all(result[:, :5, 3] == 0)
    assert np.all(result[4:7, 5:8, :3] == (0, 0, 255))
    assert np.all(result[4:7, 5:8, 3] == 255)


def test_negative_offset_is_clipped():
    layer = make_layer(4, 4, (255, 255, 255, 255), offset=(-2, -2))
    result = composite_layers([layer], 4, 4)
    assert np.all(result[:2, :2, 3] == 255)
    assert np.all(result[2:, :, 3] == 0)
    assert np.all(result[:, 2:, 3] == 0)


def test_partial_opacity_over_transparent():
    layer = make_layer(2, 2, (200, 100, 50, 255), opacity=0.5)
    result = composite_layers([layer], 2, 2)
    assert np.all(result[..., 3] == pytest.approx(128, abs=1))
    assert np.all(result[..., 0] == pytest.approx(200, abs=1))


def test_normal_alpha_over_opaque_backdrop():
    backdrop = make_layer(1, 1, (255, 0, 0, 255))
    source = make_layer(1, 1, (0, 0, 255, 128))
    result = composite_layers([backdrop, source], 1, 1)
    assert tuple(int(v) for v in result[0, 0]) == (127, 0, 128, 255)


def test_multiply_blend_mode():
    backdrop = make_layer(1, 1, (255, 0, 0, 255))
    source = make_layer(1, 1, (0, 255, 255, 255), mode="multiply")
    result = composite_layers([backdrop, source], 1, 1)
    assert tuple(int(v) for v in result[0, 0][:3]) == (0, 0, 0)


def test_screen_blend_mode():
    backdrop = make_layer(1, 1, (255, 0, 0, 255))
    source = make_layer(1, 1, (0, 0, 255, 255), mode="screen")
    result = composite_layers([backdrop, source], 1, 1)
    assert tuple(int(v) for v in result[0, 0][:3]) == (255, 0, 255)


@pytest.mark.parametrize("mode", BLEND_MODE_IDS)
def test_all_blend_modes_produce_valid_rgba(mode):
    layers = [
        make_layer(6, 5, (30, 120, 200, 255)),
        make_layer(6, 5, (200, 40, 90, 180), mode=mode, opacity=0.8),
    ]
    result = composite_layers(layers, 6, 5)
    assert result.shape == (5, 6, 4)
    assert result.dtype == np.uint8
    assert np.all(result[..., 3] == 255)
    assert result[..., :3].max() <= 255


def test_large_image_uses_multiple_bands():
    width, height = 700, 2600
    layer = make_layer(width, height, (12, 34, 56, 255))
    # Layer thứ hai buộc compositor đi qua đường xử lý theo dải (không dùng fast path).
    accent = make_layer(10, 10, (12, 34, 56, 255), opacity=0.5)
    result = composite_layers([layer, accent], width, height)
    assert result.shape == (height, width, 4)
    assert np.all(result[..., :3] == (12, 34, 56))


def test_downsample_rgba_bounds():
    array = np.zeros((400, 800, 4), dtype=np.uint8)
    small = downsample_rgba(array, max_side=100)
    assert small.shape[0] <= 100
    assert small.shape[1] <= 100


def test_invalid_canvas_size():
    with pytest.raises(ValueError):
        composite_layers([], 0, 5)


def test_clipping_mask_uses_base_alpha():
    base = make_layer(4, 4, (255, 0, 0, 255))
    base.pixels[2:, :, 3] = 0
    clipped = make_layer(4, 4, (0, 0, 255, 255))
    clipped.clipping = True
    result = composite_layers([base, clipped], 4, 4)
    assert np.all(result[:2, :, :3] == (0, 0, 255))
    assert np.all(result[:2, :, 3] == 255)
    assert np.all(result[2:, :, 3] == 0)


def test_clipped_layer_does_not_show_over_lower_layer():
    lower = make_layer(4, 4, (0, 255, 0, 255))
    base = make_layer(4, 4, (255, 0, 0, 255))
    base.pixels[2:, :, 3] = 0
    clipped = make_layer(4, 4, (0, 0, 255, 255))
    clipped.clipping = True
    result = composite_layers([lower, base, clipped], 4, 4)
    assert np.all(result[:2, :, :3] == (0, 0, 255))
    assert np.all(result[2:, :, :3] == (0, 255, 0))
    assert np.all(result[..., 3] == 255)


def test_clipping_mask_respects_base_offset():
    base = make_layer(2, 2, (255, 0, 0, 255), offset=(1, 1))
    clipped = make_layer(4, 4, (0, 0, 255, 255))
    clipped.clipping = True
    result = composite_layers([base, clipped], 4, 4)
    assert np.all(result[1:3, 1:3, :3] == (0, 0, 255))
    mask = np.ones((4, 4), dtype=bool)
    mask[1:3, 1:3] = False
    assert np.all(result[mask, 3] == 0)


def test_clipping_mask_respects_base_layer_mask():
    base = make_layer(4, 4, (255, 255, 255, 255))
    mask = np.full((4, 4), 255, dtype=np.uint8)
    mask[0, :] = 0
    base.set_mask(mask)
    clipped = make_layer(4, 4, (255, 0, 0, 255))
    clipped.clipping = True
    result = composite_layers([base, clipped], 4, 4)
    assert np.all(result[0, :, 3] == 0)
    assert np.all(result[1:, :, :3] == (255, 0, 0))


def test_layer_can_clip_to_group_alpha():
    group = Layer(1, 1, "Group")
    group.kind = LayerKind.GROUP
    child = make_layer(2, 2, (255, 0, 0, 255))
    child.group_id = group.id
    clipped = make_layer(4, 4, (0, 0, 255, 255))
    clipped.clipping = True
    result = composite_layers([group, child, clipped], 4, 4)
    assert np.all(result[:2, :2, :3] == (0, 0, 255))
    assert np.all(result[2:, :, 3] == 0)
    assert np.all(result[:, 2:, 3] == 0)


def test_clipped_layers_share_the_same_base():
    base = make_layer(4, 4, (255, 0, 0, 255))
    base.pixels[2:, :, 3] = 0
    first = make_layer(4, 4, (0, 0, 255, 255))
    first.clipping = True
    second = make_layer(4, 4, (0, 255, 0, 255))
    second.clipping = True
    result = composite_layers([base, first, second], 4, 4)
    assert np.all(result[:2, :, :3] == (0, 255, 0))
    assert np.all(result[2:, :, 3] == 0)


def test_clipping_flag_without_base_is_ignored():
    layer = make_layer(2, 2, (10, 20, 30, 255))
    layer.clipping = True
    result = composite_layers([layer], 2, 2)
    assert np.all(result[..., :3] == (10, 20, 30))
    assert np.all(result[..., 3] == 255)
