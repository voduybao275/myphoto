"""Kiểm thử compositor theo vùng, preview thu nhỏ, dirty log và tile cache."""

from __future__ import annotations

import numpy as np
import pytest

from core.adjustment_layer import AdjustmentProperties
from core.canvas import (
    composite_layers,
    composite_region,
    qimage_to_rgba,
    scale_layers_for_preview,
)
from core.document import Document
from core.fill_layer import FillProperties
from core.layer import Layer, LayerKind
from core.tiles import TileCache


def make_layer(width, height, rgba, *, offset=(0, 0), opacity=1.0, mode="normal"):
    layer = Layer(width, height)
    layer.fill(rgba)
    layer.offset_x, layer.offset_y = offset
    layer.opacity = opacity
    layer.blend_mode = mode
    return layer


def make_fill(rgba, rgba2=(240, 240, 255, 255), angle=35):
    layer = Layer(1, 1)
    layer.kind = LayerKind.FILL
    layer.fill_props = FillProperties(
        fill_type="gradient",
        color=rgba,
        color2=rgba2,
        gradient_type="linear",
        angle=angle,
    )
    return layer


def make_adjustment(hue=25):
    layer = Layer(1, 1)
    layer.kind = LayerKind.ADJUSTMENT
    layer.adjustment = AdjustmentProperties(
        kind="hue_saturation", hue=hue, saturation=20
    )
    return layer


# --------------------------------------------------------------- vùng hợp nhất
def test_region_matches_full_composite_pixels_and_masks():
    base = make_layer(40, 30, (40, 90, 160, 255))
    top = make_layer(24, 18, (220, 60, 90, 200), offset=(9, 7), mode="multiply")
    top.opacity = 0.85
    mask = np.full((18, 24), 255, dtype=np.uint8)
    mask[:, :10] = 0
    top.set_mask(mask)
    layers = [base, top]
    full = composite_layers(layers, 40, 30)
    region = composite_region(layers, 40, 30, 5, 4, 33, 26)
    assert np.array_equal(region, full[4:26, 5:33])


def test_region_matches_full_for_fill_adjustment_and_group():
    document = Document(46, 34)
    background = document.add_layer(color=(60, 60, 60, 255), name="Background")
    background.visible = True
    child = document.add_layer(color=(255, 120, 30, 200), name="Child")
    child.opacity = 0.7
    child.blend_mode = "screen"
    group = document.add_group(name="Group")
    group.opacity = 0.9
    group.mask = np.full((34, 46), 200, dtype=np.uint8)
    child.group_id = group.id
    document.add_adjustment_layer(
        AdjustmentProperties(kind="levels", levels_gamma=1.3), name="Levels"
    )
    document.add_layer(make_fill((20, 120, 200, 255)), name="Fill")

    full = composite_layers(document.layers.layers, 46, 34)
    region = composite_region(document.layers.layers, 46, 34, 7, 3, 41, 29)
    assert np.array_equal(region, full[3:29, 7:41])


def test_region_validation():
    layer = make_layer(8, 8, (1, 2, 3, 255))
    assert composite_region([layer], 8, 8, 0, 0, 8, 8).shape == (8, 8, 4)
    with pytest.raises(ValueError):
        composite_region([layer], 8, 8, 5, 5, 5, 8)
    with pytest.raises(ValueError):
        composite_region([layer], 0, 8, 0, 0, 8, 8)


def test_region_fast_path_single_layer_with_negative_offset():
    layer = make_layer(6, 6, (10, 200, 40, 255), offset=(-2, -3))
    region = composite_region([layer], 6, 6, 0, 0, 6, 6)
    assert np.all(region[:3, :4, 3] == 255)
    assert np.all(region[3:, :, 3] == 0)
    assert np.all(region[:, 4:, 3] == 0)


# ------------------------------------------------------------------- preview
def test_scale_layers_for_preview_downsamples_and_preserves_source():
    document = Document(400, 300)
    layer = document.add_layer(color=(200, 40, 60, 255), name="Base")
    before = layer.pixels.copy()
    scaled, width, height = scale_layers_for_preview(
        document.layers.layers, 400, 300, 100
    )
    assert (width, height) == (100, 75)
    assert scaled[0].pixels.shape == (75, 100, 4)
    assert np.array_equal(layer.pixels, before)


def test_preview_image_is_cached_per_revision_and_side():
    document = Document(320, 240)
    document.add_layer(color=(30, 160, 90, 255))
    image = document.preview_image(80)
    assert (image.width(), image.height()) == (80, 60)
    again = document.preview_image(80)
    assert again is image
    document.invalidate((0, 0, 10, 10))
    rebuilt = document.preview_image(80)
    assert rebuilt is not image
    document.invalidate((0, 0, 5, 5))
    larger = document.preview_image(160)
    assert larger is not rebuilt
    assert (larger.width(), larger.height()) == (160, 120)


def test_preview_step_one_matches_full_composite():
    document = Document(40, 20)
    document.add_layer(color=(10, 20, 30, 255))
    image = document.preview_image(80)
    full = document.get_composite().array
    assert (image.width(), image.height()) == (40, 20)
    assert np.array_equal(qimage_to_rgba(image), full)


# --------------------------------------------------------------- dirty log
def test_changes_since_tracks_rectangles_and_full_invalidation():
    document = Document(100, 80)
    start = document.revision
    document.invalidate((10, 10, 30, 20))
    document.invalidate((50, 40, 70, 60))
    assert document.changes_since(start) == [
        (10, 10, 30, 20),
        (50, 40, 70, 60),
    ]
    assert document.changes_since(document.revision) == []
    document.invalidate()
    assert document.changes_since(start) is None


def test_changes_since_clips_rectangles_and_handles_empty():
    document = Document(50, 40)
    start = document.revision
    document.invalidate((-10, -5, 20, 15))
    assert document.changes_since(start) == [(0, 0, 20, 15)]
    start = document.revision
    document.invalidate((60, 50, 90, 90))
    assert document.changes_since(start) == [(0, 0, 0, 0)]


def test_changes_since_reports_none_for_trimmed_history():
    document = Document(10, 10)
    for index in range(80):
        document.invalidate((0, 0, 1, 1))
    assert document.changes_since(0) is None


# --------------------------------------------------------------- tile cache
def test_tile_cache_builds_edge_tile_and_matches_region():
    document = Document(300, 140)
    document.add_layer(color=(12, 34, 56, 255))
    cache = TileCache(document, tile_size=256, max_tiles=4)
    edge = cache.tile(1, 0)
    assert (edge.width(), edge.height()) == (44, 140)
    expected = composite_region(
        document.layers.layers, 300, 140, 256, 0, 300, 140
    )
    from core.canvas import qimage_to_rgba

    assert np.array_equal(qimage_to_rgba(edge), expected)
    assert cache.composites == 1


def test_tile_cache_hits_lru_and_counters():
    document = Document(600, 300)
    document.add_layer(color=(90, 20, 200, 255))
    cache = TileCache(document, tile_size=256, max_tiles=2)
    first = cache.tile(0, 0)
    same = cache.tile(0, 0)
    assert same is first
    assert cache.hits == 1 and cache.misses == 1
    cache.tile(1, 0)
    assert cache.count == 2
    cache.tile(2, 0)
    assert cache.count == 2
    assert (0, 0) not in cache.cached_keys()


def test_tile_cache_drops_only_tiles_overlapping_dirty_rect():
    document = Document(512, 512)
    document.add_layer(color=(200, 200, 40, 255))
    cache = TileCache(document, tile_size=256, max_tiles=8)
    for key in ((0, 0), (1, 0), (0, 1), (1, 1)):
        cache.tile(*key)
    assert cache.count == 4
    document.invalidate((10, 10, 20, 20))
    cache.sync()
    assert cache.cached_keys() == [(1, 0), (0, 1), (1, 1)]
    cache.tile(0, 0)
    assert cache.composites == 5


def test_tile_cache_clears_on_full_invalidation_and_reports_tiles_for_rect():
    document = Document(520, 300)
    document.add_layer(color=(10, 10, 10, 255))
    cache = TileCache(document, tile_size=256, max_tiles=8)
    assert cache.tiles_for_rect(0, 0, 1, 1) == [(0, 0)]
    assert cache.tiles_for_rect(250, 10, 510, 260) == [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
    ]
    cache.tile(0, 0)
    document.invalidate()
    cache.sync()
    assert cache.count == 0


def test_tile_cache_validation():
    document = Document(10, 10)
    with pytest.raises(ValueError):
        TileCache(document, tile_size=8)
    with pytest.raises(ValueError):
        TileCache(document, max_tiles=0)
    cache = TileCache(document)
    with pytest.raises(ValueError):
        cache.tile(-1, 0)
    with pytest.raises(ValueError):
        cache.tile(1, 0)


# ------------------------------------------------------------------ canvas
def test_canvas_view_uses_preview_and_tiles(qapp):
    from ui.canvas_view import CanvasView

    document = Document(900, 700)
    document.add_layer(color=(120, 60, 20, 255), name="Background")
    view = CanvasView(document)
    view.resize(360, 280)
    view.fit_to_window()
    assert view.zoom < 0.5
    view.grab()
    assert view.render_mode == "preview"

    view.zoom_actual()
    view.grab()
    assert view.render_mode == "tiles"
    assert 0 < view.tile_cache.count <= view.tile_cache.max_tiles
    before = view.tile_cache.hits
    view.grab()
    assert view.tile_cache.hits > before

    document.invalidate()
    view.grab()
    assert view.render_mode == "tiles"
    view.dispose()
