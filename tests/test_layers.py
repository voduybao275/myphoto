"""Kiểm thử Layer và LayerManager."""

from __future__ import annotations

import numpy as np
import pytest

from core.layer import BLEND_MODES, BLEND_MODE_IDS, Layer, LayerManager


def test_layer_defaults():
    layer = Layer(4, 3, "Test")
    assert layer.pixels.shape == (3, 4, 4)
    assert layer.pixels.dtype == np.uint8
    assert not layer.has_pixels()
    assert layer.bounds() == (0, 0, 4, 3)


def test_fill_and_touch():
    layer = Layer(2, 2)
    layer.fill((10, 20, 30, 255))
    assert layer.has_pixels()
    assert layer.pixel_revision == 1
    assert tuple(int(v) for v in layer.pixels[0, 0]) == (10, 20, 30, 255)


def test_set_pixels_validation():
    layer = Layer(2, 2)
    with pytest.raises(ValueError):
        layer.set_pixels(np.zeros((2, 2, 4), dtype=np.float32))
    with pytest.raises(ValueError):
        layer.set_pixels(np.zeros((2, 2, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        layer.set_pixels(np.zeros((3, 3, 4), dtype=np.uint8))
    layer.set_pixels(np.zeros((2, 2, 4), dtype=np.uint8))
    assert layer.pixel_revision == 1


def test_copy_is_independent():
    layer = Layer(2, 2, "Gốc")
    layer.fill((255, 0, 0, 255))
    layer.offset_x = 3
    layer.opacity = 0.5
    layer.blend_mode = "multiply"
    layer.clipping = True
    layer.color_label = "violet"
    clone = layer.copy()
    assert clone.name == "Gốc copy"
    assert clone.offset_x == 3
    assert clone.opacity == 0.5
    assert clone.blend_mode == "multiply"
    assert clone.clipping
    assert clone.color_label == "violet"
    clone.pixels[0, 0] = (0, 255, 0, 255)
    assert layer.pixels[0, 0, 0] == 255
    assert clone.id != layer.id


def test_blend_mode_catalog():
    assert len(BLEND_MODES) == 15
    assert len(set(BLEND_MODE_IDS)) == 15
    assert "normal" in BLEND_MODE_IDS
    assert "luminosity" in BLEND_MODE_IDS


def test_manager_insert_order_and_get():
    manager = LayerManager()
    first = Layer(1, 1, "A")
    second = Layer(1, 1, "B")
    third = Layer(1, 1, "C")
    manager.insert(first)
    manager.insert(second, 0)
    manager.insert(third, 1)
    assert [layer.name for layer in manager] == ["B", "C", "A"]
    assert manager.get(first.id) is first
    assert manager.get("missing") is None
    assert manager.index_of(third) == 1


def test_manager_rejects_duplicate_id():
    manager = LayerManager()
    layer = Layer(1, 1)
    manager.insert(layer)
    with pytest.raises(ValueError):
        manager.insert(layer)


def test_manager_set_order_validation():
    manager = LayerManager()
    first = Layer(1, 1)
    second = Layer(1, 1)
    manager.insert(first)
    manager.insert(second)
    manager.set_order([second, first])
    assert [layer.id for layer in manager] == [second.id, first.id]
    with pytest.raises(ValueError):
        manager.set_order([first])
