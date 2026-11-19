"""Kiểm thử layer điều chỉnh: phép biến đổi màu, compositor, Undo và dự án."""

from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pytest
from PIL import Image

from core.adjustment_layer import (
    ADJUSTMENT_LABELS,
    AdjustmentProperties,
    apply_adjustment_rgb,
    apply_adjustment_rgba,
)
from core.document import Document
from core.gradient import GradientSettings
from core.layer import LayerKind
from core.paint import BrushSettings
from core.shape_layer import ShapeProperties
from formats.native_project import ProjectFormatError, load_project, save_project


def _pixels(values: list[tuple[float, float, float]]) -> np.ndarray:
    return np.array([values], dtype=np.float32)


def _solid_document(color=(40, 80, 160, 255), size=(20, 16)) -> Document:
    document = Document(*size)
    document.add_layer(name="Background", color=color, record=False)
    return document


# ------------------------------------------------------------------ phép màu
def test_identity_copies_without_change():
    properties = AdjustmentProperties()
    assert properties.is_identity
    assert properties.summary() == "Không thay đổi"
    rgb = _pixels([(0.2, 0.4, 0.6)])
    assert np.allclose(apply_adjustment_rgb(rgb, properties), rgb)


def test_invert_and_rgba_alpha_preserved():
    rgba = np.full((4, 5, 4), 40, dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 3] = 128
    result = apply_adjustment_rgba(rgba, AdjustmentProperties(kind="invert"))
    assert result.dtype == np.uint8
    assert result.shape == rgba.shape
    assert np.all(result[..., 0] == 0)
    assert np.all(result[..., 1] == 215)
    assert np.all(result[..., 2] == 215)
    assert np.all(result[..., 3] == 128)


def test_desaturate_uses_luma_weights():
    rgb = _pixels([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)])
    result = apply_adjustment_rgb(rgb, AdjustmentProperties(kind="desaturate"))
    assert np.allclose(result[0, 0], [0.2126] * 3, atol=1e-4)
    assert np.allclose(result[0, 1], [0.7152] * 3, atol=1e-4)
    assert np.allclose(result[0, 2], [0.0722] * 3, atol=1e-4)


def test_brightness_and_negative_contrast_math():
    rgb = _pixels([(0.5, 0.5, 0.5)])
    bright = AdjustmentProperties(brightness=20)
    assert np.allclose(apply_adjustment_rgb(rgb, bright), [[0.7] * 3], atol=1e-4)

    flat = AdjustmentProperties(contrast=-100)
    mixed = apply_adjustment_rgb(_pixels([(0.2, 0.6, 0.9)]), flat)
    assert np.allclose(mixed, [[128.0 / 255.0] * 3], atol=1e-4)


def test_hue_rotation_and_saturation_drop():
    red = _pixels([(1.0, 0.0, 0.0)])
    rotated = apply_adjustment_rgb(
        red, AdjustmentProperties(kind="hue_saturation", hue=120)
    )
    assert np.allclose(rotated[0, 0], (0.0, 1.0, 0.0), atol=2e-3)

    gray = apply_adjustment_rgb(
        _pixels([(0.9, 0.3, 0.2)]),
        AdjustmentProperties(kind="hue_saturation", saturation=-100),
    )
    assert np.allclose(gray[0, 0, 0], gray[0, 0, 1])
    assert np.allclose(gray[0, 0, 1], gray[0, 0, 2])


def test_properties_validate_clamp_and_roundtrip():
    with pytest.raises(ValueError, match="Loại điều chỉnh"):
        AdjustmentProperties(kind="vibrance")
    clamped = AdjustmentProperties(brightness=500, hue=-999)
    assert clamped.brightness == 100
    assert clamped.hue == -180
    properties = AdjustmentProperties(
        kind="hue_saturation", hue=30, saturation=-20, lightness=15
    )
    assert AdjustmentProperties.from_dict(properties.to_dict()) == properties
    assert properties.default_name == "Hue/Saturation"
    assert ADJUSTMENT_LABELS["invert"] == "Invert"
    with pytest.raises(ValueError, match="không hợp lệ"):
        AdjustmentProperties.from_dict("bad")


# ------------------------------------------------------------------ compositor
def test_composite_applies_invert_and_undo_redo():
    document = _solid_document()
    layer = document.add_adjustment_layer(AdjustmentProperties(kind="invert"))
    assert layer.kind == LayerKind.ADJUSTMENT
    assert (layer.width, layer.height) == (1, 1)
    assert document.get_composite().array[0, 0].tolist() == [215, 175, 95, 255]

    assert document.undo()
    assert document.get_composite().array[0, 0].tolist() == [40, 80, 160, 255]
    assert document.redo()
    assert document.get_composite().array[0, 0].tolist() == [215, 175, 95, 255]


def test_adjustment_respects_visibility_and_opacity():
    document = _solid_document()
    layer = document.add_adjustment_layer(AdjustmentProperties(kind="invert"))
    document.set_layer_visible(layer, False)
    assert document.get_composite().array[0, 0].tolist() == [40, 80, 160, 255]

    document.set_layer_visible(layer, True)
    document.set_layer_opacity(layer, 0.5)
    middle = document.get_composite().array[0, 0].tolist()
    assert middle == [128, 128, 128, 255]


def test_adjustment_only_affects_layers_below():
    document = _solid_document()
    document.add_adjustment_layer(AdjustmentProperties(kind="invert"))
    document.add_shape_layer(
        ShapeProperties(
            kind="ellipse",
            width=8,
            height=8,
            fill_color=(0, 0, 255, 255),
            stroke_width=0,
        ),
        x=6,
        y=4,
    )
    composite = document.get_composite().array
    assert composite[0, 0].tolist() == [215, 175, 95, 255]
    assert composite[7, 9].tolist() == [0, 0, 255, 255]


def test_update_adjustment_with_undo_and_noop():
    document = _solid_document()
    layer = document.add_adjustment_layer(AdjustmentProperties(kind="invert"))
    with pytest.raises(ValueError, match="không phải layer điều chỉnh"):
        document.update_adjustment_layer(AdjustmentProperties(), document.layers[0])

    assert not document.update_adjustment_layer(AdjustmentProperties(kind="invert"), layer)
    updated = AdjustmentProperties(kind="brightness_contrast", brightness=20)
    assert document.update_adjustment_layer(updated, layer)
    assert layer.adjustment == updated
    assert document.get_composite().array[0, 0].tolist() == [91, 131, 211, 255]

    assert document.undo()
    assert layer.adjustment.kind == "invert"
    assert document.get_composite().array[0, 0].tolist() == [215, 175, 95, 255]
    assert document.redo()
    assert layer.adjustment == updated


# ------------------------------------------------------------------- hình học
def test_geometry_preserves_adjustment_layers():
    document = _solid_document(size=(20, 16))
    layer = document.add_adjustment_layer(AdjustmentProperties(kind="desaturate"))

    assert document.resize_image(40, 32)
    assert (layer.width, layer.height) == (1, 1)
    assert layer.kind == LayerKind.ADJUSTMENT
    assert layer.adjustment.kind == "desaturate"
    gray = document.get_composite().array[0, 0].tolist()
    assert gray[0] == gray[1] == gray[2]

    assert document.crop(4, 4, 12, 10)
    assert (layer.width, layer.height) == (1, 1)
    assert (layer.offset_x, layer.offset_y) == (0, 0)

    assert document.canvas_size(30, 24)
    assert (layer.offset_x, layer.offset_y) == (0, 0)

    assert document.rotate_canvas("cw")
    assert (layer.width, layer.height) == (1, 1)
    assert (layer.offset_x, layer.offset_y) == (0, 0)
    assert layer.adjustment.kind == "desaturate"

    assert document.flip_canvas(True)
    assert layer.kind == LayerKind.ADJUSTMENT
    assert (layer.width, layer.height) == (1, 1)
    assert document.undo()
    assert layer.kind == LayerKind.ADJUSTMENT


def test_destructive_operations_are_blocked():
    document = _solid_document()
    layer = document.add_adjustment_layer(AdjustmentProperties(kind="invert"))

    with pytest.raises(ValueError, match="không có pixel để vẽ"):
        document.begin_brush_stroke(BrushSettings(), layer=layer)
    with pytest.raises(ValueError, match="không có pixel để tô"):
        document.begin_gradient(GradientSettings(), (0.0, 0.0), layer=layer)
    with pytest.raises(ValueError, match="không hỗ trợ xoay/lật"):
        document.transform_layer("flip_h", layer)
    with pytest.raises(ValueError, match="không hỗ trợ xoay/lật"):
        document.rotate_layer_arbitrary(15, layer)
    with pytest.raises(ValueError, match="Không thể áp bộ lọc"):
        document.apply_layer_filter(layer.pixels.copy(), "Test", layer)
    assert layer.kind == LayerKind.ADJUSTMENT


# -------------------------------------------------------------------- dự án
def test_project_roundtrip_saves_adjustment_metadata(tmp_path):
    document = _solid_document(size=(12, 9))
    properties = AdjustmentProperties(
        kind="hue_saturation", hue=45, saturation=-10, lightness=5
    )
    document.add_adjustment_layer(properties, name="Chỉnh màu")
    document.set_layer_opacity(document.active_layer, 0.4)

    target = save_project(document, tmp_path / "adjust")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    entry = next(
        item for item in manifest["layers"] if item["kind"] == LayerKind.ADJUSTMENT
    )
    assert entry["adjustment"] == properties.to_dict()
    assert entry["opacity"] == pytest.approx(0.4, abs=1e-6)

    loaded = load_project(target)
    adjustment_layer = loaded.layers[-1]
    assert adjustment_layer.kind == LayerKind.ADJUSTMENT
    assert adjustment_layer.adjustment == properties
    assert np.array_equal(
        loaded.get_composite().array, document.get_composite().array
    )


def test_project_rejects_adjustment_mask_with_wrong_size(tmp_path):
    document = _solid_document(size=(8, 6))
    document.add_adjustment_layer(AdjustmentProperties(kind="invert"))
    document.add_layer_mask()
    target = save_project(document, tmp_path / "bad")

    with zipfile.ZipFile(target) as archive:
        entries = {info.filename: archive.read(info) for info in archive.infolist()}
    manifest = json.loads(entries["manifest.json"])
    entry = next(
        item for item in manifest["layers"] if item["kind"] == LayerKind.ADJUSTMENT
    )
    buffer = io.BytesIO()
    Image.fromarray(np.zeros((1, 1), dtype=np.uint8), "L").save(
        buffer, format="PNG"
    )
    entries[entry["mask_file"]] = buffer.getvalue()
    entries["manifest.json"] = json.dumps(manifest).encode("utf-8")
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    with pytest.raises(ProjectFormatError, match="không khớp"):
        load_project(target)
