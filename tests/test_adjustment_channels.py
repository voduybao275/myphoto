"""Kiểm thử Curves tách kênh, histogram và eyedropper (phần 13)."""

from __future__ import annotations

import json
import zipfile

import numpy as np
import pytest

from PySide6.QtCore import QPointF

from core.adjustment_layer import AdjustmentProperties, apply_adjustment_rgb
from core.document import Document
from core.histogram import compute_histogram
from formats.native_project import load_project, save_project
from ui.dialogs import AdjustmentLayerDialog


def _pixels(*values: tuple[float, float, float]) -> np.ndarray:
    return np.array([values], dtype=np.float32)


def _solid_document(color=(100, 80, 60, 255), size=(10, 8)) -> Document:
    document = Document(*size)
    document.add_layer(name="Background", color=color, record=False)
    return document


def _gradient_rgba(width=80, height=60) -> np.ndarray:
    array = np.zeros((height, width, 4), dtype=np.uint8)
    array[..., 0] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    array[..., 1] = 90
    array[..., 2] = 160
    array[..., 3] = 255
    return array


# ------------------------------------------------------------ Curves kênh
def test_channel_curve_changes_only_its_channel():
    properties = AdjustmentProperties(
        kind="curves", curve_red=((0, 255), (255, 0))
    )
    result = apply_adjustment_rgb(
        _pixels((0.2, 0.5, 0.8)), properties
    )
    assert np.allclose(result[0, 0], (0.8, 0.5, 0.8), atol=1e-5)


def test_channel_curve_runs_before_composite_curve():
    properties = AdjustmentProperties(
        kind="curves",
        curve_points=((0, 0), (255, 128)),
        curve_red=((0, 255), (255, 0)),
    )
    result = apply_adjustment_rgb(_pixels((0.2, 0.5, 0.2)), properties)
    assert result[0, 0, 0] == pytest.approx(0.4016, abs=2e-3)
    assert result[0, 0, 1] == pytest.approx(0.2510, abs=2e-3)
    assert result[0, 0, 2] == pytest.approx(0.1004, abs=2e-3)


def test_channel_curve_validation_and_clamping():
    clamped = AdjustmentProperties(
        kind="curves", curve_blue=((-10, 300), (300, -5))
    )
    assert clamped.curve_blue == ((0, 255), (255, 0))
    with pytest.raises(ValueError, match="hoành độ"):
        AdjustmentProperties(
            kind="curves", curve_green=((10, 0), (10, 255))
        )
    with pytest.raises(ValueError, match="từ 2 đến 16"):
        AdjustmentProperties(
            kind="curves", curve_red=((0, 0),)
        )
    with pytest.raises(ValueError, match="không hợp lệ"):
        AdjustmentProperties.from_dict(
            {"kind": "curves", "curve_blue": [[0, 0], [0, 255]]}
        )


def test_channel_curve_identity_summary_and_serialization():
    identity = AdjustmentProperties(kind="curves")
    assert identity.is_identity

    red_only = AdjustmentProperties(
        kind="curves", curve_red=((0, 255), (255, 0))
    )
    assert not red_only.is_identity
    assert red_only.summary() == "Đường cong R"

    combined = AdjustmentProperties(
        kind="curves",
        curve_points=((0, 0), (128, 90), (255, 255)),
        curve_blue=((0, 255), (255, 0)),
    )
    assert combined.summary() == "Đường cong 3 điểm · B"

    restored = AdjustmentProperties.from_dict(combined.to_dict())
    assert restored == combined
    payload = combined.to_dict()
    assert payload["curve_green"] == [[0, 0], [255, 255]]
    assert payload["curve_blue"] == [[0, 255], [255, 0]]


# -------------------------------------------------------------- histogram
def test_histogram_counts_per_channel_and_luma():
    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[0, 0] = (10, 5, 200, 255)
    rgba[0, 1] = (20, 5, 210, 255)
    rgba[1, 0] = (30, 5, 220, 255)
    rgba[1, 1] = (40, 5, 230, 255)
    histogram = compute_histogram(rgba)
    assert set(histogram) == {"rgb", "red", "green", "blue"}
    for values in histogram.values():
        assert values.shape == (256,)
        assert int(values.sum()) == 4
    assert histogram["red"][10] == 1
    assert histogram["red"][40] == 1
    assert histogram["green"][5] == 4
    assert histogram["blue"][230] == 1


def test_histogram_ignores_transparent_pixels_and_supports_bins():
    rgba = np.zeros((1, 3, 4), dtype=np.uint8)
    rgba[0, 0] = (0, 0, 0, 255)
    rgba[0, 1] = (85, 85, 85, 255)
    rgba[0, 2] = (200, 200, 200, 0)
    histogram = compute_histogram(rgba, bins=4)
    assert int(histogram["red"].sum()) == 2
    assert histogram["red"].tolist() == [1, 1, 0, 0]
    assert int(histogram["rgb"].sum()) == 2


def test_histogram_validation():
    with pytest.raises(ValueError, match="uint8"):
        compute_histogram(np.zeros((4, 4, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="uint8"):
        compute_histogram(np.zeros((4, 4, 4), dtype=np.float32))
    with pytest.raises(ValueError, match="2..4096"):
        compute_histogram(np.zeros((4, 4, 4), dtype=np.uint8), bins=1)


# ---------------------------------------------------------------- tài liệu
def test_document_channel_curve_composite_and_undo():
    document = _solid_document((100, 80, 60, 255))
    base = document.get_composite().array[0, 0].tolist()

    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="curves", curve_green=((0, 255), (255, 0))
        )
    )
    adjusted = document.get_composite().array[0, 0].tolist()
    assert adjusted[0] == base[0]
    assert adjusted[1] == 175
    assert adjusted[2] == base[2]

    assert document.undo()
    assert document.get_composite().array[0, 0].tolist() == base


def test_project_roundtrip_preserves_channel_curves(tmp_path):
    document = _solid_document(size=(9, 7))
    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="curves",
            curve_points=((0, 0), (96, 64), (255, 255)),
            curve_red=((0, 20), (255, 235)),
            curve_blue=((0, 0), (128, 90), (255, 255)),
        )
    )
    expected = document.get_composite().array.copy()

    target = save_project(document, tmp_path / "channels")
    loaded = load_project(target)
    original = next(layer for layer in document.layers if layer.adjustment)
    restored = next(layer for layer in loaded.layers if layer.adjustment)
    assert restored.adjustment == original.adjustment
    assert np.array_equal(loaded.get_composite().array, expected)


def test_project_old_curves_metadata_defaults_channels(tmp_path):
    document = _solid_document(size=(8, 6))
    document.add_adjustment_layer(AdjustmentProperties(kind="curves"))
    target = save_project(document, tmp_path / "old_channels")
    with zipfile.ZipFile(target) as archive:
        entries = {
            info.filename: archive.read(info) for info in archive.infolist()
        }
    manifest = json.loads(entries["manifest.json"])
    entry = next(item for item in manifest["layers"] if "adjustment" in item)
    entry["adjustment"] = {
        "kind": "curves",
        "curve_points": [[0, 0], [128, 64], [255, 255]],
    }
    entries["manifest.json"] = json.dumps(manifest).encode("utf-8")
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    loaded = load_project(target)
    adjustment = next(
        layer.adjustment for layer in loaded.layers if layer.adjustment
    )
    assert adjustment.curve_points == ((0, 0), (128, 64), (255, 255))
    assert adjustment.curve_red == ((0, 0), (255, 255))
    assert adjustment.curve_green == ((0, 0), (255, 255))
    assert adjustment.curve_blue == ((0, 0), (255, 255))


# --------------------------------------------------------------------- UI
def test_curve_dialog_channel_switch_histogram_and_eyedropper(qapp):
    source = _gradient_rgba()
    dialog = AdjustmentLayerDialog(
        AdjustmentProperties(kind="curves"), preview=source
    )
    assert dialog.curve_channel_combo.count() == 4
    assert dialog.curve_channel == "rgb"
    assert dialog.curve_editor._histogram is not None
    assert int(dialog._histograms["rgb"].sum()) == source.shape[0] * source.shape[1]
    assert dialog.properties == AdjustmentProperties(kind="curves")

    dialog.curve_channel_combo.setCurrentIndex(1)
    assert dialog.curve_channel == "red"
    assert dialog.curve_editor._curve_color is not None
    assert np.count_nonzero(dialog._histograms["red"]) == source.shape[1]
    dialog.curve_editor.add_point(48, 12)
    assert dialog.properties.curve_red == ((0, 0), (48, 12), (255, 255))
    assert dialog.properties.curve_points == ((0, 0), (255, 255))

    dialog.black_eyedropper_button.setChecked(True)
    assert dialog._eyedropper_mode == "black"
    dialog._apply_eyedropper(30)
    assert (30, 0) in dialog.properties.curve_red
    assert "mẫu 30" in dialog.info_label.text()

    dialog.curve_editor.reset()
    assert dialog.properties.curve_red == ((0, 0), (255, 255))
    assert dialog.properties.curve_points == ((0, 0), (255, 255))

    dialog.curve_channel_combo.setCurrentIndex(0)
    assert dialog.curve_editor.points() == ((0, 0), (255, 255))
    dialog.close()


def test_levels_dialog_histogram_and_eyedropper(qapp):
    source = _gradient_rgba()
    dialog = AdjustmentLayerDialog(
        AdjustmentProperties(kind="levels"), preview=source
    )
    assert int(dialog.levels_histogram._values.sum()) == (
        source.shape[0] * source.shape[1]
    )
    assert dialog.properties == AdjustmentProperties(kind="levels")

    dialog.show()
    qapp.processEvents()
    center = QPointF(
        dialog.preview_label.width() / 2.0,
        dialog.preview_label.height() / 2.0,
    )
    assert dialog._sample_source_pixel(center) is not None

    dialog.black_eyedropper_button.setChecked(True)
    dialog._on_preview_clicked(center)
    black = dialog.properties.levels_black
    assert 0 <= black < 255
    assert "mẫu" in dialog.info_label.text()

    pixmap = dialog._preview_pixmap
    offset = (dialog.preview_label.width() - pixmap.width()) / 2.0
    right = QPointF(
        offset + pixmap.width() * 0.9,
        dialog.preview_label.height() / 2.0,
    )
    dialog._on_preview_clicked(right)
    assert dialog.properties.levels_black > black
    black = dialog.properties.levels_black

    dialog.white_eyedropper_button.setChecked(True)
    assert not dialog.black_eyedropper_button.isChecked()
    assert dialog._eyedropper_mode == "white"
    dialog._apply_eyedropper(250)
    assert dialog.properties.levels_white == 250
    assert dialog.properties.levels_black == black

    dialog.white_eyedropper_button.setChecked(False)
    assert dialog._eyedropper_mode == ""
    dialog.close()
