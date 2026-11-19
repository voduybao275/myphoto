"""Kiểm thử layer điều chỉnh nâng cao: Levels, Curves và Color Balance."""

from __future__ import annotations

import json
import zipfile

import numpy as np
import pytest

from core.adjustment_layer import (
    ADJUSTMENT_LABELS,
    MAX_CURVE_POINTS,
    MAX_GAMMA,
    MIN_GAMMA,
    AdjustmentProperties,
    apply_adjustment_rgb,
)
from core.document import Document
from formats.native_project import ProjectFormatError, load_project, save_project


def _pixels(*values: tuple[float, float, float]) -> np.ndarray:
    return np.array([values], dtype=np.float32)


def _solid_document(color=(40, 80, 160, 255), size=(10, 8)) -> Document:
    document = Document(*size)
    document.add_layer(name="Background", color=color, record=False)
    return document


# ------------------------------------------------------------------- Levels
def test_levels_identity_and_gamma_clamp():
    assert AdjustmentProperties(kind="levels").is_identity
    assert AdjustmentProperties(kind="levels").summary() == "Không thay đổi"

    low = AdjustmentProperties(kind="levels", levels_gamma=0.01)
    high = AdjustmentProperties(kind="levels", levels_gamma=99.0)
    assert low.levels_gamma == pytest.approx(MIN_GAMMA)
    assert high.levels_gamma == pytest.approx(MAX_GAMMA)
    assert not AdjustmentProperties(kind="levels", levels_gamma=1.5).is_identity


def test_levels_math_input_output_and_gamma():
    properties = AdjustmentProperties(
        kind="levels",
        levels_black=64,
        levels_white=192,
        levels_gamma=2.0,
        levels_out_black=10,
        levels_out_white=245,
    )
    result = apply_adjustment_rgb(
        _pixels((0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (1.0, 1.0, 1.0)),
        properties,
    )
    assert np.allclose(result[0, 0], 10 / 255.0, atol=1e-4)
    assert np.allclose(result[0, 2], 245 / 255.0, atol=1e-4)
    assert np.allclose(result[0, 1], 0.6883, atol=2e-3)

    flat = AdjustmentProperties(
        kind="levels", levels_out_black=128, levels_out_white=128
    )
    assert np.allclose(
        apply_adjustment_rgb(_pixels((0.2, 0.6, 0.9)), flat),
        [[128 / 255.0] * 3],
        atol=1e-4,
    )


def test_levels_summary_order_and_roundtrip():
    properties = AdjustmentProperties(
        kind="levels",
        levels_black=20,
        levels_white=230,
        levels_gamma=1.5,
        levels_out_black=5,
        levels_out_white=250,
    )
    summary = properties.summary()
    assert "Đen 20" in summary
    assert "Gamma 1.50" in summary
    assert "Trắng 230" in summary
    assert "Ra 5..250" in summary
    assert AdjustmentProperties.from_dict(properties.to_dict()) == properties

    swapped = AdjustmentProperties(
        kind="levels", levels_black=200, levels_white=100
    )
    assert swapped.levels_white > swapped.levels_black


# ------------------------------------------------------------------- Curves
def test_curves_lut_identity_and_endpoints():
    identity = AdjustmentProperties(kind="curves")
    assert identity.is_identity
    assert np.allclose(
        apply_adjustment_rgb(_pixels((0.25, 0.5, 0.75)), identity),
        [[0.25, 0.5, 0.75]],
        atol=1e-6,
    )

    bright = AdjustmentProperties(
        kind="curves", curve_points=((0, 0), (128, 64), (255, 255))
    )
    result = apply_adjustment_rgb(_pixels((0.0, 0.5, 1.0)), bright)
    assert np.allclose(result[0, 0, 0], 0.0, atol=1e-4)
    assert np.allclose(result[0, 0, 1], 64 / 255.0, atol=2e-3)
    assert np.allclose(result[0, 0, 2], 1.0, atol=1e-4)

    clipped = AdjustmentProperties(
        kind="curves", curve_points=((64, 0), (192, 255))
    )
    values = apply_adjustment_rgb(
        _pixels((0.1, 0.1, 0.1), (0.9, 0.9, 0.9)), clipped
    )
    assert values[0, 0, 0] == 0.0
    assert values[0, 1, 0] == 1.0


def test_curves_validation_and_roundtrip():
    properties = AdjustmentProperties(
        kind="curves",
        curve_points=((0, 0), (64, 90), (192, 180), (255, 255)),
    )
    assert properties.summary() == "Đường cong 4 điểm"
    assert AdjustmentProperties.from_dict(properties.to_dict()) == properties

    with pytest.raises(ValueError, match="hoành độ"):
        AdjustmentProperties(kind="curves", curve_points=((10, 0), (10, 255)))
    with pytest.raises(ValueError, match="2 đến 16"):
        AdjustmentProperties(kind="curves", curve_points=((0, 0),))
    too_many = tuple((index * 16, index * 16) for index in range(17))
    with pytest.raises(ValueError, match=str(MAX_CURVE_POINTS)):
        AdjustmentProperties(kind="curves", curve_points=too_many)
    with pytest.raises(ValueError, match="không hợp lệ"):
        AdjustmentProperties.from_dict(
            {"kind": "curves", "curve_points": [[0, 0], [0, 255]]}
        )


# ----------------------------------------------------------- Color Balance
def test_color_balance_shadows_and_midtones():
    dark = _pixels((0.15, 0.15, 0.15))
    shadows = AdjustmentProperties(
        kind="color_balance",
        color_shadows=(60, -20, 0),
        preserve_luminosity=False,
    )
    result = apply_adjustment_rgb(dark, shadows)
    assert result[0, 0, 0] > 0.15
    assert result[0, 0, 1] < 0.15
    assert result[0, 0, 2] == pytest.approx(0.15, abs=1e-6)

    middle = _pixels((0.5, 0.5, 0.5))
    mids = AdjustmentProperties(
        kind="color_balance",
        color_midtones=(0, 40, -40),
        preserve_luminosity=False,
    )
    middle_result = apply_adjustment_rgb(middle, mids)
    assert middle_result[0, 0, 1] > 0.5
    assert middle_result[0, 0, 2] < 0.5


def test_color_balance_preserve_luminosity_and_summary():
    color = _pixels((0.5, 0.5, 0.5))
    properties = AdjustmentProperties(
        kind="color_balance", color_midtones=(60, -30, 20)
    )
    preserved = apply_adjustment_rgb(color, properties)[0, 0]
    original_luma = 0.2126 * 0.5 + 0.7152 * 0.5 + 0.0722 * 0.5
    new_luma = (
        0.2126 * preserved[0]
        + 0.7152 * preserved[1]
        + 0.0722 * preserved[2]
    )
    assert new_luma == pytest.approx(original_luma, abs=1e-3)

    properties_off = AdjustmentProperties(
        kind="color_balance",
        color_midtones=(60, -30, 20),
        preserve_luminosity=False,
    )
    free = apply_adjustment_rgb(color, properties_off)[0, 0]
    free_luma = 0.2126 * free[0] + 0.7152 * free[1] + 0.0722 * free[2]
    assert abs(free_luma - original_luma) > 1e-3

    summary = properties.summary()
    assert "Trung +60/-30/+20" in summary
    assert "giữ độ sáng" in summary


def test_color_balance_validation_roundtrip():
    properties = AdjustmentProperties(
        kind="color_balance",
        color_shadows=(10, -20, 30),
        color_midtones=(40, 0, -40),
        color_highlights=(-10, 10, 0),
        preserve_luminosity=False,
    )
    assert AdjustmentProperties.from_dict(properties.to_dict()) == properties
    clamped = AdjustmentProperties(
        kind="color_balance", color_shadows=(500, -500, 0)
    )
    assert clamped.color_shadows == (100, -100, 0)
    with pytest.raises(ValueError, match="3 số"):
        AdjustmentProperties(kind="color_balance", color_shadows=(1, 2))
    with pytest.raises(ValueError, match="không hợp lệ"):
        AdjustmentProperties.from_dict(
            {"kind": "color_balance", "color_shadows": [1, 2]}
        )
    assert ADJUSTMENT_LABELS["levels"] == "Levels"
    assert ADJUSTMENT_LABELS["curves"] == "Curves"
    assert ADJUSTMENT_LABELS["color_balance"] == "Color Balance"


# ------------------------------------------------------------- tài liệu
def test_document_composite_and_undo_for_advanced_adjustments():
    document = _solid_document((40, 80, 160, 255))
    base = document.get_composite().array[0, 0].tolist()

    levels = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="levels", levels_black=10, levels_white=240, levels_gamma=1.4
        )
    )
    after_levels = document.get_composite().array[0, 0].tolist()
    assert after_levels != base

    curves = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="curves", curve_points=((0, 0), (128, 96), (255, 255))
        )
    )
    after_curves = document.get_composite().array[0, 0].tolist()
    assert after_curves != after_levels

    balance = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="color_balance", color_midtones=(30, -10, 15)
        )
    )
    after_balance = document.get_composite().array[0, 0].tolist()
    assert after_balance != after_curves
    assert document.layers[-1] is balance
    assert levels.kind == curves.kind == balance.kind

    assert document.undo()
    assert document.get_composite().array[0, 0].tolist() == after_curves
    assert document.undo()
    assert document.get_composite().array[0, 0].tolist() == after_levels
    assert document.redo()
    assert document.get_composite().array[0, 0].tolist() == after_curves


def test_update_adjustment_switches_between_levels_and_curves():
    document = _solid_document()
    layer = document.add_adjustment_layer(
        AdjustmentProperties(kind="levels", levels_gamma=1.8)
    )
    updated = AdjustmentProperties(
        kind="curves", curve_points=((0, 0), (128, 80), (255, 255))
    )
    assert document.update_adjustment_layer(updated, layer)
    assert layer.adjustment.kind == "curves"
    assert document.undo()
    assert layer.adjustment.kind == "levels"
    assert document.redo()
    assert layer.adjustment == updated


def test_project_roundtrip_advanced_adjustments(tmp_path):
    document = _solid_document(size=(12, 9))
    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="levels",
            levels_black=16,
            levels_white=240,
            levels_gamma=1.25,
            levels_out_black=4,
            levels_out_white=250,
        )
    )
    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="curves",
            curve_points=((0, 0), (64, 84), (192, 200), (255, 255)),
        )
    )
    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="color_balance",
            color_shadows=(8, -4, 0),
            color_midtones=(-12, 6, 18),
            color_highlights=(0, -8, 8),
            preserve_luminosity=False,
        )
    )
    expected = document.get_composite().array.copy()

    target = save_project(document, tmp_path / "advanced")
    loaded = load_project(target)
    kinds = [layer.adjustment.kind for layer in loaded.layers if layer.adjustment]
    assert kinds == ["levels", "curves", "color_balance"]
    for original, restored in zip(
        [layer for layer in document.layers if layer.adjustment],
        [layer for layer in loaded.layers if layer.adjustment],
    ):
        assert restored.adjustment == original.adjustment
    assert np.array_equal(loaded.get_composite().array, expected)


def test_project_old_adjustment_metadata_uses_defaults(tmp_path):
    document = _solid_document(size=(8, 6))
    document.add_adjustment_layer(
        AdjustmentProperties(kind="levels", levels_gamma=1.6)
    )
    target = save_project(document, tmp_path / "old")
    with zipfile.ZipFile(target) as archive:
        entries = {info.filename: archive.read(info) for info in archive.infolist()}
    manifest = json.loads(entries["manifest.json"])
    entry = next(
        item for item in manifest["layers"] if "adjustment" in item
    )
    entry["adjustment"] = {"kind": "levels"}
    entries["manifest.json"] = json.dumps(manifest).encode("utf-8")
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    loaded = load_project(target)
    adjustment = next(
        layer.adjustment for layer in loaded.layers if layer.adjustment
    )
    assert adjustment.is_identity
    assert adjustment.levels_gamma == pytest.approx(1.0)


def test_invalid_curve_points_in_project_are_reported(tmp_path):
    document = _solid_document(size=(6, 5))
    document.add_adjustment_layer(AdjustmentProperties(kind="curves"))
    target = save_project(document, tmp_path / "badcurve")
    with zipfile.ZipFile(target) as archive:
        entries = {info.filename: archive.read(info) for info in archive.infolist()}
    manifest = json.loads(entries["manifest.json"])
    entry = next(
        item for item in manifest["layers"] if "adjustment" in item
    )
    entry["adjustment"]["curve_points"] = [[10, 0], [10, 255]]
    entries["manifest.json"] = json.dumps(manifest).encode("utf-8")
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    with pytest.raises(ProjectFormatError, match="không hợp lệ"):
        load_project(target)
