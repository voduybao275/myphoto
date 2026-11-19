"""Kiểm thử Document: layer, undo/redo, merge, flatten, offset và composite cache."""

from __future__ import annotations

import numpy as np
import pytest

from core.document import Document


def make_document(width=8, height=8):
    return Document(width, height, dpi=72, name="Test")


def solid_layer(document, rgba=(1, 2, 3, 255), name="Layer"):
    layer = document.add_layer(name=name, color=rgba, record=False)
    return layer


def test_invalid_document_size():
    with pytest.raises(ValueError):
        Document(0, 10)
    with pytest.raises(ValueError):
        Document(10, 30_001)
    with pytest.raises(ValueError):
        Document(30_000, 20_000)


def test_add_layer_records_history_and_selects():
    document = make_document()
    assert document.active_layer is None
    layer = document.add_layer(name="Layer 1", color=(255, 0, 0, 255))
    assert len(document.layers) == 1
    assert document.active_layer is layer
    assert document.modified
    assert document.history.can_undo

    assert document.undo()
    assert len(document.layers) == 0
    assert document.active_layer is None
    assert document.history.can_redo

    assert document.redo()
    assert len(document.layers) == 1
    assert document.layers[0] is layer


def test_property_change_undo_redo():
    document = make_document()
    layer = solid_layer(document, (10, 20, 30, 255))
    assert document.set_layer_opacity(layer, 0.5)
    assert layer.opacity == 0.5
    assert document.undo()
    assert layer.opacity == 1.0
    assert document.redo()
    assert layer.opacity == 0.5

    assert document.set_layer_visible(layer, False)
    assert not layer.visible
    assert document.undo()
    assert layer.visible

    assert document.set_layer_blend_mode(layer, "multiply")
    assert layer.blend_mode == "multiply"
    assert document.undo()
    assert layer.blend_mode == "normal"


def test_invalid_blend_mode_rejected():
    document = make_document()
    layer = solid_layer(document, (1, 2, 3, 255))
    with pytest.raises(ValueError):
        document.set_layer_blend_mode(layer, "not-a-mode")


def test_rename_layer():
    document = make_document()
    layer = solid_layer(document)
    assert document.rename_layer(layer, "Nền")
    assert layer.name == "Nền"
    assert not document.rename_layer(layer, "   ")
    assert document.undo()
    assert layer.name == "Layer"


def test_duplicate_and_remove():
    document = make_document()
    layer = solid_layer(document, (1, 2, 3, 255))
    clone = document.duplicate_layer()
    assert len(document.layers) == 2
    assert document.active_layer is clone
    assert clone.name == "Layer copy"
    assert np.array_equal(clone.pixels, layer.pixels)

    assert document.remove_layer()
    assert len(document.layers) == 1
    assert document.active_layer is layer


def test_remove_active_layer_selects_neighbour():
    document = make_document()
    first = solid_layer(document, (1, 2, 3, 255), name="A")
    second = solid_layer(document, (4, 5, 6, 255), name="B")
    document.set_active_layer(second)
    assert document.remove_layer(second)
    assert document.active_layer is first


def test_merge_down():
    document = make_document()
    solid_layer(document, (255, 0, 0, 255), name="Bottom")
    top = document.add_layer(name="Top", record=False)
    top.fill((0, 0, 255, 128))
    document.set_active_layer(top)
    assert document.merge_down()
    assert len(document.layers) == 1
    merged = document.layers[0]
    assert merged.name == "Bottom"
    assert tuple(int(v) for v in merged.pixels[0, 0]) == (127, 0, 128, 255)

    assert document.undo()
    assert len(document.layers) == 2


def test_merge_down_requires_layer_below():
    document = make_document()
    solid_layer(document, (1, 2, 3, 255))
    assert not document.merge_down()


def test_flatten_image():
    document = make_document()
    solid_layer(document, (10, 0, 0, 255), name="A")
    solid_layer(document, (0, 200, 0, 255), name="B")
    assert document.flatten_image()
    assert len(document.layers) == 1
    flattened = document.layers[0]
    assert flattened.name == "Flattened"
    assert np.all(flattened.pixels[..., :3] == (0, 200, 0))
    assert document.undo()
    assert len(document.layers) == 2


def test_reorder_layers_and_undo():
    document = make_document()
    first = solid_layer(document, (1, 0, 0, 255), name="A")
    second = solid_layer(document, (2, 0, 0, 255), name="B")
    third = solid_layer(document, (3, 0, 0, 255), name="C")
    assert document.reorder_layers([third, first, second])
    assert [layer.name for layer in document.layers] == ["C", "A", "B"]
    assert document.undo()
    assert [layer.name for layer in document.layers] == ["A", "B", "C"]


def test_preview_and_commit_offset():
    document = make_document()
    layer = solid_layer(document, (1, 2, 3, 255))
    document.preview_layer_offset(layer, 5, 7)
    assert (layer.offset_x, layer.offset_y) == (5, 7)
    document.commit_layer_offset(layer, (0, 0), (5, 7))
    assert document.history.can_undo
    assert document.undo()
    assert (layer.offset_x, layer.offset_y) == (0, 0)
    assert document.redo()
    assert (layer.offset_x, layer.offset_y) == (5, 7)


def test_composite_cache_invalidation():
    document = make_document()
    solid_layer(document, (1, 2, 3, 255))
    first = document.get_composite()
    second = document.get_composite()
    assert first is second
    document.invalidate()
    third = document.get_composite()
    assert third is not first
    assert np.array_equal(third.array, first.array)


def test_get_composite_reflects_visibility_and_opacity():
    document = make_document(2, 2)
    layer = solid_layer(document, (255, 0, 0, 255))
    assert document.get_composite().array[0, 0, 3] == 255
    document.set_layer_visible(layer, False)
    assert document.get_composite().array[0, 0, 3] == 0
    document.undo()
    document.set_layer_opacity(layer, 0.0)
    assert document.get_composite().array[0, 0, 3] == 0


def test_mark_saved_keeps_history():
    document = make_document()
    solid_layer(document, (1, 2, 3, 255))
    document.add_layer()
    assert document.modified
    document.mark_saved("C:/tmp/test.mps")
    assert not document.modified
    assert document.file_path.endswith("test.mps")
    assert document.history.can_undo
    document.undo()
    assert document.modified


def test_memory_estimate_positive():
    document = make_document(16, 16)
    solid_layer(document, (1, 2, 3, 255))
    document.get_composite()
    assert document.memory_estimate() >= 16 * 16 * 4 * 2


def test_set_active_layer_validation():
    document = make_document()
    with pytest.raises(ValueError):
        document.set_active_layer("missing")
    solid_layer(document)
    document.set_active_layer(None)
    assert document.active_layer is None
