"""Kiểm thử Document: layer, undo/redo, merge, flatten, offset và composite cache."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRectF

from core.adjustment_layer import AdjustmentProperties
from core.document import Document
from core.fill_layer import FillProperties
from core.layer import LayerKind
from core.selection import Selection


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


def test_set_layer_locked_is_undoable_and_blocks_filters():
    document = make_document(2, 2)
    layer = solid_layer(document, (255, 0, 0, 255))
    assert document.set_layer_locked(layer, True)
    assert layer.locked
    assert not document.set_layer_locked(layer, True)
    with pytest.raises(ValueError, match="khoá"):
        document.apply_layer_filter(np.zeros_like(layer.pixels), "Thử", layer)
    document.undo()
    assert not layer.locked
    document.redo()
    assert layer.locked


def test_clear_selection_pixels_respects_selection_and_undo():
    document = make_document(8, 8)
    layer = solid_layer(document, (10, 20, 30, 255))
    document.set_selection(Selection.from_rect(8, 8, QRectF(2, 2, 3, 3)))
    assert document.clear_selection_pixels()
    assert np.all(layer.pixels[2:5, 2:5, 3] == 0)
    assert layer.pixels[0, 0, 3] == 255
    assert not document.clear_selection_pixels()
    document.undo()
    assert np.all(layer.pixels[..., 3] == 255)


def test_clear_without_selection_clears_whole_layer():
    document = make_document(4, 4)
    layer = solid_layer(document, (10, 20, 30, 255))
    assert document.clear_selection_pixels()
    assert np.all(layer.pixels[..., 3] == 0)


def test_fill_selection_composites_over_and_rejects_non_pixel_layers():
    document = make_document(6, 6)
    layer = solid_layer(document, (0, 0, 0, 0))
    document.set_selection(Selection.from_rect(6, 6, QRectF(0, 0, 3, 6)))
    assert document.fill_selection((255, 0, 0, 255))
    assert tuple(layer.pixels[0, 0]) == (255, 0, 0, 255)
    assert tuple(layer.pixels[0, 5]) == (0, 0, 0, 0)
    document.deselect()
    assert document.fill_selection((0, 0, 255, 128))
    red, green, blue, alpha = layer.pixels[0, 0]
    assert alpha == 255 and blue > 120 and red < 140
    assert layer.pixels[0, 5, 3] == 128
    document.set_layer_locked(layer, True)
    with pytest.raises(ValueError, match="khoá"):
        document.fill_selection((1, 2, 3, 255))
    group = document.add_group()
    with pytest.raises(ValueError, match="không phải layer ảnh"):
        document.clear_selection_pixels(group)


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


def test_copy_pixels_crops_to_selection_and_masks_alpha():
    document = make_document(10, 10)
    layer = solid_layer(document, (10, 20, 30, 255))
    assert document.copy_pixels() is not None
    array, offset = document.copy_pixels()
    assert array.shape == (10, 10, 4) and offset == (0, 0)
    document.set_selection(
        Selection.from_rect(10, 10, QRectF(2, 3, 4, 5)), "Chọn vùng"
    )
    array, offset = document.copy_pixels()
    assert offset == (2, 3)
    assert array.shape == (5, 4, 4)
    assert tuple(array[0, 0]) == (10, 20, 30, 255)
    layer.offset_x = 8
    document.deselect()
    document.set_selection(
        Selection.from_rect(10, 10, QRectF(0, 0, 4, 4)), "Chọn vùng"
    )
    assert document.copy_pixels() is None
    group = document.add_group()
    with pytest.raises(ValueError, match="Copy Merged"):
        document.copy_pixels(group)
    assert document.copy_pixels(group, merged=True) is None
    document.deselect()
    merged, merged_offset = document.copy_pixels(group, merged=True)
    assert merged.shape == (10, 10, 4) and merged_offset == (0, 0)
    assert tuple(merged[5, 9]) == (10, 20, 30, 255)
    assert merged[5, 0, 3] == 0


def test_paste_pixels_creates_layer_at_offset_or_centered():
    document = make_document(20, 10)
    solid_layer(document)
    patch = np.full((4, 6, 4), 200, dtype=np.uint8)
    layer = document.paste_pixels(patch, (3, 2))
    assert document.active_layer is layer
    assert (layer.width, layer.height) == (6, 4)
    assert (layer.offset_x, layer.offset_y) == (3, 2)
    assert document.history.can_undo
    centered = document.paste_pixels(patch)
    assert (centered.offset_x, centered.offset_y) == (7, 3)
    with pytest.raises(ValueError):
        document.paste_pixels(np.zeros((2, 2, 3), dtype=np.uint8))


def test_clipping_mask_requires_base_and_is_undoable():
    document = make_document()
    base = solid_layer(document)
    with pytest.raises(ValueError, match="layer nền"):
        document.set_layer_clipping(base, True)

    upper = solid_layer(document, rgba=(9, 8, 7, 255), name="Upper")
    assert document.set_layer_clipping(upper, True)
    assert upper.clipping
    assert document.history.undo_label == "Tạo Clipping Mask"
    assert document.undo()
    assert not upper.clipping
    assert document.redo()
    assert upper.clipping

    assert document.set_layer_clipping(upper, False)
    assert not upper.clipping
    assert document.history.undo_label == "Giải phóng Clipping Mask"
    assert document.undo()
    assert upper.clipping


def test_clipping_mask_rejects_adjustment_base():
    document = make_document()
    document.add_adjustment_layer(AdjustmentProperties(kind="invert"), record=False)
    upper = solid_layer(document, name="Upper")
    with pytest.raises(ValueError, match="điều chỉnh"):
        document.set_layer_clipping(upper, True)
    assert not upper.clipping


def test_color_label_is_undoable():
    document = make_document()
    layer = solid_layer(document)
    assert document.set_layer_color_label(layer, "red")
    assert layer.color_label == "red"
    assert document.history.undo_label == "Đổi màu nhãn layer"
    assert document.undo()
    assert layer.color_label == "none"
    assert document.redo()
    assert layer.color_label == "red"
    with pytest.raises(ValueError, match="Nhãn màu"):
        document.set_layer_color_label(layer, "pink")


def test_blending_options_apply_as_one_undo_step():
    document = make_document()
    layer = solid_layer(document)
    assert document.set_layer_blending(layer, "multiply", 0.4)
    assert layer.blend_mode == "multiply"
    assert layer.opacity == pytest.approx(0.4)
    assert document.history.undo_label == "Blending Options"
    assert document.undo()
    assert layer.blend_mode == "normal"
    assert layer.opacity == 1.0
    assert document.redo()
    assert layer.blend_mode == "multiply"
    assert layer.opacity == pytest.approx(0.4)

    adjustment = document.add_adjustment_layer(
        AdjustmentProperties(kind="invert"), record=False
    )
    with pytest.raises(ValueError, match="blend mode"):
        document.set_layer_blending(adjustment, "screen", None)
    assert document.set_layer_blending(adjustment, None, 0.5)
    assert adjustment.opacity == pytest.approx(0.5)


def test_merge_visible_keeps_hidden_layers():
    document = make_document(4, 4)
    red = solid_layer(document, (255, 0, 0, 255), name="Red")
    blue = solid_layer(document, (0, 0, 255, 255), name="Blue")
    hidden = solid_layer(document, (0, 255, 0, 255), name="Hidden")
    document.set_layer_visible(hidden, False)

    assert document.merge_visible()
    assert len(document.layers) == 2
    merged = document.active_layer
    assert merged is not None and merged.name == "Merged"
    assert hidden in document.layers.layers
    assert tuple(int(value) for value in merged.pixels[0, 0]) == (0, 0, 255, 255)
    assert document.history.undo_label == "Merge Visible"
    assert document.undo()
    assert [layer.name for layer in document.layers] == ["Red", "Blue", "Hidden"]
    assert document.redo()
    assert len(document.layers) == 2


def test_convert_pixel_layer_to_smart_object_and_back():
    document = make_document(4, 4)
    layer = solid_layer(document, (12, 34, 56, 255), name="Source")
    original = layer.pixels.copy()
    assert document.convert_to_smart_object(layer)
    assert layer.kind == LayerKind.SMART
    assert layer.smart_props is not None
    assert (layer.smart_props.source_width, layer.smart_props.source_height) == (4, 4)
    assert np.array_equal(layer.smart_source, original)
    assert document.history.undo_label == "Chuyển thành Smart Object"
    assert document.undo()
    assert layer.kind == LayerKind.PIXEL
    assert document.redo()
    assert layer.kind == LayerKind.SMART


def test_convert_fill_to_smart_object_uses_canvas_size():
    document = make_document(6, 4)
    layer = document.add_fill_layer(FillProperties(fill_type="solid"), record=False)
    assert document.convert_to_smart_object(layer)
    assert layer.kind == LayerKind.SMART
    assert (layer.width, layer.height) == (6, 4)
    assert (layer.offset_x, layer.offset_y) == (0, 0)
    assert layer.pixels.shape == (4, 6, 4)


def test_rasterize_layer_dispatches_by_kind():
    document = make_document(4, 4)
    layer = solid_layer(document)
    assert document.convert_to_smart_object(layer)
    assert layer.kind == LayerKind.SMART
    assert document.rasterize_layer(layer)
    assert layer.kind == LayerKind.PIXEL
    assert document.history.undo_label == "Rasterize smart object"
    assert document.undo()
    assert layer.kind == LayerKind.SMART
    assert document.redo()
    assert not document.rasterize_layer(layer)

    adjustment = document.add_adjustment_layer(
        AdjustmentProperties(kind="invert"), record=False
    )
    with pytest.raises(ValueError, match="rasterize"):
        document.rasterize_layer(adjustment)
