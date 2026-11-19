"""Kiểm thử layer tô không phá huỷ và smart object (phần 16)."""

from __future__ import annotations

import json
import zipfile

import numpy as np
import pytest

from core.document import Document
from core.fill_layer import (
    FILL_LABELS,
    FillProperties,
    render_fill,
    render_fill_band,
)
from core.layer import Layer, LayerKind
from core.smart_object import (
    SmartObjectProperties,
    render_smart_object,
    transform_operation,
    validate_source,
)
from formats.native_project import load_project, save_project


def _source(width: int = 24, height: int = 16) -> np.ndarray:
    array = np.zeros((height, width, 4), dtype=np.uint8)
    array[..., 0] = 220
    array[..., 1] = 40
    array[..., 2] = 90
    array[..., 3] = 255
    array[0, 0] = (0, 255, 0, 255)
    return array


def _document(size=(40, 30)) -> Document:
    document = Document(*size)
    document.add_layer(name="Background", color=(10, 20, 30, 255), record=False)
    return document


# --------------------------------------------------------------- FillProperties
def test_fill_properties_defaults_and_validation():
    props = FillProperties()
    assert props.fill_type == "solid"
    assert props.summary == "RGBA(59, 110, 165, 255)"
    assert FillProperties(fill_type="gradient", angle=-30).angle == 330
    assert FILL_LABELS["solid"] == "Tô đặc"
    with pytest.raises(ValueError):
        FillProperties(fill_type="pattern")
    with pytest.raises(ValueError):
        FillProperties(color=(0, 0, 300, 255))
    with pytest.raises(ValueError):
        FillProperties(gradient_type="diagonal")
    restored = FillProperties.from_dict(props.to_dict())
    assert restored == props
    with pytest.raises(ValueError):
        FillProperties.from_dict("bad")


def test_render_fill_solid_and_bands_match():
    props = FillProperties(color=(12, 34, 56, 200))
    pixels = render_fill(props, 10, 6)
    assert pixels.shape == (6, 10, 4)
    assert np.all(pixels[..., :3] == (12, 34, 56))
    assert np.all(pixels[..., 3] == 200)
    gradient = FillProperties(
        fill_type="gradient",
        color=(0, 0, 0, 255),
        color2=(255, 255, 255, 255),
        angle=0,
    )
    full = render_fill(gradient, 20, 8)
    joined = np.concatenate(
        [
            np.clip(render_fill_band(gradient, y, y + 3, 20, 8) * 255 + 0.5, 0, 255)
            .astype(np.uint8)
            for y in (0, 3, 6)
        ]
    )
    assert np.array_equal(full, joined)
    assert full[0, 0, 0] < full[0, -1, 0]


def test_render_fill_radial_brightens_center():
    props = FillProperties(
        fill_type="gradient",
        color=(255, 255, 255, 255),
        color2=(0, 0, 0, 255),
        gradient_type="radial",
    )
    pixels = render_fill(props, 21, 21)
    assert pixels[10, 10, 0] > pixels[0, 0, 0]
    assert pixels[10, 10, 0] >= 240
    assert pixels[0, 0, 0] <= 80


# ------------------------------------------------------------ Document: fill
def test_add_fill_layer_kind_and_composite():
    document = _document((12, 8))
    layer = document.add_fill_layer(FillProperties(color=(250, 10, 10, 255)))
    assert layer.kind == LayerKind.FILL
    assert (layer.width, layer.height) == (1, 1)
    assert layer.fill_props is not None
    composite = document.get_composite().array
    assert tuple(composite[0, 0]) == (250, 10, 10, 255)


def test_update_fill_layer_undo_redo():
    document = _document((10, 10))
    layer = document.add_fill_layer(FillProperties(color=(0, 0, 0, 255)))
    assert document.update_fill_layer(
        FillProperties(color=(0, 200, 0, 255)), layer
    )
    assert tuple(document.get_composite().array[4, 4]) == (0, 200, 0, 255)
    assert document.undo()
    assert tuple(document.get_composite().array[4, 4]) == (0, 0, 0, 255)
    assert document.redo()
    assert tuple(document.get_composite().array[4, 4]) == (0, 200, 0, 255)
    assert not document.update_fill_layer(layer.fill_props, layer)


def test_rasterize_fill_bakes_mask_and_undo_restores():
    document = _document((10, 8))
    layer = document.add_fill_layer(FillProperties(color=(20, 40, 60, 255)))
    mask = np.zeros((8, 10), dtype=np.uint8)
    mask[:, :5] = 255
    layer.set_mask(mask)
    assert document.rasterize_fill_layer(layer)
    assert layer.kind == LayerKind.PIXEL
    assert layer.mask is None
    assert (layer.width, layer.height) == (10, 8)
    assert layer.pixels[0, 0, 3] == 255
    assert layer.pixels[0, 9, 3] == 0
    assert document.undo()
    assert layer.kind == LayerKind.FILL
    assert layer.fill_props is not None
    assert layer.mask is not None
    assert (layer.width, layer.height) == (1, 1)


def test_fill_rejects_layer_transform_but_allows_pixels_mask_size():
    document = _document((10, 8))
    layer = document.add_fill_layer(FillProperties())
    with pytest.raises(ValueError):
        document.transform_layer("rotate_cw")
    with pytest.raises(ValueError):
        document.rotate_layer_arbitrary(15)
    layer.set_mask(np.zeros((8, 10), dtype=np.uint8))
    assert layer.mask is not None


def test_fill_blend_and_opacity():
    document = _document((4, 4))
    document.add_fill_layer(FillProperties(color=(0, 0, 0, 255)))
    layer = document.add_fill_layer(FillProperties(color=(200, 200, 200, 255)))
    layer.opacity = 0.5
    layer.blend_mode = "multiply"
    composite = document.get_composite().array
    assert composite[0, 0, 0] < 100


# ------------------------------------------------------- SmartObjectProperties
def test_smart_properties_validation_and_summary():
    props = SmartObjectProperties(
        source_name="logo.png",
        source_width=30,
        source_height=20,
        angle=380,
        scale=120,
        flip_h=True,
    )
    assert props.angle == pytest.approx(20)
    assert props.default_name == "logo"
    assert "120 %" in props.summary
    assert "lật ngang" in props.summary
    assert not props.is_identity
    assert SmartObjectProperties().is_identity
    with pytest.raises(ValueError):
        SmartObjectProperties(source_width=0)
    with pytest.raises(ValueError):
        SmartObjectProperties(scale=900)
    with pytest.raises(ValueError):
        SmartObjectProperties.from_dict({"source_width": "x"})
    assert SmartObjectProperties.from_dict(props.to_dict()) == props


def test_transform_operation_math():
    props = SmartObjectProperties(source_width=10, source_height=10, angle=10)
    assert transform_operation(props, "rotate_cw").angle == pytest.approx(100)
    assert transform_operation(props, "rotate_ccw").angle == pytest.approx(-80)
    assert transform_operation(props, "rotate_180").angle == pytest.approx(-170)
    flipped = transform_operation(props, "flip_h")
    assert flipped.flip_h and flipped.angle == pytest.approx(-10)
    flipped_v = transform_operation(props, "flip_v")
    assert flipped_v.flip_v and flipped_v.angle == pytest.approx(-10)
    with pytest.raises(ValueError):
        transform_operation(props, "skew")


def test_validate_source_rejects_bad_arrays():
    with pytest.raises(ValueError):
        validate_source(np.zeros((4, 4), dtype=np.uint8))
    with pytest.raises(ValueError):
        validate_source(np.zeros((4, 4, 4), dtype=np.float32))
    with pytest.raises(ValueError):
        validate_source(np.zeros((0, 4, 4), dtype=np.uint8))


def test_render_smart_object_identity_scale_rotation_flip():
    source = _source(24, 16)
    identity = SmartObjectProperties(
        source_name="x.png", source_width=24, source_height=16
    )
    rendered = render_smart_object(source, identity)
    assert np.array_equal(rendered, source)
    scaled = render_smart_object(
        source, SmartObjectProperties(source_width=24, source_height=16, scale=200)
    )
    assert scaled.shape == (32, 48, 4)
    rotated = render_smart_object(
        source, SmartObjectProperties(source_width=24, source_height=16, angle=90)
    )
    assert rotated.shape == (24, 16, 4)
    flipped = render_smart_object(
        source,
        SmartObjectProperties(
            source_width=24, source_height=16, flip_h=True
        ),
    )
    assert flipped.shape == source.shape
    assert not np.array_equal(flipped, source)
    assert np.mean(flipped[..., 0]) == pytest.approx(
        np.mean(source[..., 0]), rel=0.05
    )


# ------------------------------------------------------- Document: smart object
def test_add_smart_object_centered_and_undoable():
    document = _document((100, 80))
    source = _source(30, 20)
    layer = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="photo.png", source_width=30, source_height=20
        ),
        name="Photo",
    )
    assert layer.kind == LayerKind.SMART
    assert layer.name == "Photo"
    assert layer.smart_source is not None
    assert np.array_equal(layer.smart_source, source)
    assert (layer.offset_x, layer.offset_y) == (35, 30)
    composite = document.get_composite().array
    assert tuple(composite[40, 40]) == (220, 40, 90, 255)


def test_update_smart_object_undo_and_mask_guard():
    document = _document((100, 80))
    source = _source(30, 20)
    layer = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="photo.png", source_width=30, source_height=20
        ),
    )
    changed = document.update_smart_object(
        SmartObjectProperties(
            source_name="photo.png",
            source_width=30,
            source_height=20,
            angle=45,
            scale=150,
        ),
        layer,
    )
    assert changed
    assert layer.smart_props is not None
    assert layer.smart_props.angle == pytest.approx(45)
    assert layer.width > 30
    assert document.undo()
    assert layer.smart_props is not None
    assert layer.smart_props.angle == pytest.approx(0)
    assert (layer.width, layer.height) == (30, 20)

    layer.set_mask(np.full((layer.height, layer.width), 255, np.uint8))
    with pytest.raises(ValueError):
        document.update_smart_object(
            SmartObjectProperties(
                source_name="photo.png",
                source_width=30,
                source_height=20,
                angle=10,
            ),
            layer,
        )
    with pytest.raises(ValueError):
        document.replace_smart_contents(source, layer)


def test_smart_transform_actions_keep_source_quality():
    document = _document((100, 80))
    source = _source(30, 20)
    layer = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="photo.png", source_width=30, source_height=20
        ),
    )
    assert document.transform_layer("rotate_cw")
    assert layer.smart_props is not None
    assert layer.smart_props.angle == pytest.approx(90)
    assert (layer.width, layer.height) == (20, 30)
    assert document.transform_layer("flip_h")
    assert layer.smart_props.flip_h
    assert layer.smart_props.angle == pytest.approx(-90)
    assert document.rotate_layer_arbitrary(30)
    assert layer.smart_props.angle == pytest.approx(-60)
    assert document.undo()
    assert layer.smart_props.angle == pytest.approx(-90)


def test_replace_smart_contents_undo_restores_old_source():
    document = _document((80, 60))
    source = _source(20, 10)
    layer = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="a.png", source_width=20, source_height=10, angle=20
        ),
    )
    replacement = np.zeros((12, 18, 4), dtype=np.uint8)
    replacement[..., 2] = 255
    replacement[..., 3] = 255
    assert document.replace_smart_contents(replacement, layer, name="b.png")
    assert layer.smart_props is not None
    assert layer.smart_props.source_name == "b.png"
    assert layer.smart_props.angle == pytest.approx(20)
    assert layer.smart_source is not None
    assert layer.smart_source.shape == (12, 18, 4)
    assert document.undo()
    assert layer.smart_source is not None
    assert layer.smart_source.shape == (10, 20, 4)
    assert layer.smart_props is not None
    assert layer.smart_props.source_name == "a.png"


def test_reset_and_rasterize_smart_object():
    document = _document((80, 60))
    source = _source(20, 10)
    layer = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="a.png",
            source_width=20,
            source_height=10,
            angle=30,
            scale=150,
            flip_h=True,
        ),
    )
    assert document.reset_smart_object(layer)
    assert layer.smart_props is not None and layer.smart_props.is_identity
    assert not document.reset_smart_object(layer)
    assert document.rasterize_smart_layer(layer)
    assert layer.kind == LayerKind.PIXEL
    assert layer.smart_props is None and layer.smart_source is None
    assert document.undo()
    assert layer.kind == LayerKind.SMART
    assert layer.smart_source is not None


# --------------------------------------------------------------- .mps dự án
def test_project_roundtrip_v6_preserves_fill_and_smart(tmp_path):
    document = _document((60, 40))
    document.add_fill_layer(
        FillProperties(
            fill_type="gradient",
            color=(10, 20, 30, 255),
            color2=(200, 220, 240, 255),
            gradient_type="radial",
            angle=90,
        ),
        name="Nền gradient",
    )
    source = _source(24, 16)
    smart = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="logo.png",
            source_width=24,
            source_height=16,
            angle=30,
            scale=120,
            flip_v=True,
        ),
        name="Logo",
    )
    expected_composite = document.get_composite().array.copy()
    path = save_project(document, tmp_path / "fill-smart.mps")

    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["version"] == 6
        names = {entry["name"]: entry for entry in manifest["layers"]}
        assert names["Nền gradient"]["kind"] == "fill"
        assert names["Logo"]["kind"] == "smart"
        assert f"sources/{smart.id}.png" in archive.namelist()

    loaded = load_project(path)
    by_name = {layer.name: layer for layer in loaded.layers}
    fill = by_name["Nền gradient"]
    assert fill.kind == LayerKind.FILL
    assert fill.fill_props is not None
    assert fill.fill_props.gradient_type == "radial"
    assert fill.fill_props.angle == 90
    logo = by_name["Logo"]
    assert logo.kind == LayerKind.SMART
    assert logo.smart_props is not None
    assert logo.smart_props.angle == pytest.approx(30)
    assert logo.smart_props.flip_v
    assert logo.smart_source is not None
    assert logo.smart_source.shape == (16, 24, 4)
    assert np.array_equal(logo.smart_source, source)
    assert np.array_equal(loaded.get_composite().array, expected_composite)


def test_fill_mask_roundtrip(tmp_path):
    document = _document((20, 12))
    layer = document.add_fill_layer(FillProperties(color=(0, 0, 255, 255)))
    mask = np.zeros((12, 20), dtype=np.uint8)
    mask[:6] = 255
    layer.set_mask(mask)
    path = save_project(document, tmp_path / "fill-mask.mps")
    loaded = load_project(path)
    restored = loaded.layers[-1]
    assert restored.kind == LayerKind.FILL
    assert restored.mask is not None
    assert restored.mask.shape == (12, 20)
    assert np.array_equal(restored.mask, mask)


# ------------------------------------------------------------------ giao diện
def _window(tmp_path, size=(40, 30)):
    from config.settings import SettingsStore
    from ui.main_window import MainWindow

    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    document = Document(*size)
    document.add_layer(name="Background", color=(5, 5, 5, 255), record=False)
    window._add_document_tab(document)
    return window, document


def test_fill_dialog_properties_and_controls(qapp):
    from PySide6.QtWidgets import QDialog

    from ui.dialogs import FillDialog

    dialog = FillDialog(FillProperties(fill_type="solid"), editing=False)
    assert dialog.properties.fill_type == "solid"
    assert not dialog.angle_spin.isEnabled()
    assert dialog.fill_type_combo.findData("gradient") >= 0
    dialog.fill_type_combo.setCurrentIndex(
        dialog.fill_type_combo.findData("gradient")
    )
    dialog.gradient_type_combo.setCurrentIndex(
        dialog.gradient_type_combo.findData("radial")
    )
    dialog.angle_spin.setValue(135)
    assert dialog.angle_spin.isEnabled()
    props = dialog.properties
    assert props.fill_type == "gradient"
    assert props.gradient_type == "radial"
    assert props.angle == 135
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.deleteLater()


def test_smart_dialog_properties_preview(qapp):
    from ui.dialogs import SmartObjectDialog

    source = _source(30, 20)
    props = SmartObjectProperties(
        source_name="logo.png", source_width=30, source_height=20
    )
    dialog = SmartObjectDialog(source, props)
    dialog.angle_spin.setValue(25)
    dialog.scale_spin.setValue(140)
    dialog.flip_h_check.setChecked(True)
    result = dialog.properties
    assert result.angle == pytest.approx(25)
    assert result.scale == pytest.approx(140)
    assert result.flip_h
    assert result.source_name == "logo.png"
    assert dialog.preview_label.pixmap() is not None
    dialog.reject()
    dialog.deleteLater()


def test_main_window_fill_and_smart_actions(tmp_path, qapp):
    from core.fill_layer import FillProperties
    from ui.layers_panel import ROLE_SUBTITLE

    window, document = _window(tmp_path)
    fill = document.add_fill_layer(FillProperties(color=(0, 100, 0, 255)))
    window._update_action_states()
    assert window.action_edit_fill.isEnabled()
    assert window.action_rasterize_fill.isEnabled()
    assert not window.action_edit_smart_object.isEnabled()
    assert window.action_new_fill_solid.isEnabled()
    assert window.action_new_fill_gradient.isEnabled()
    assert window.action_place_smart_object.isEnabled()
    assert document.rasterize_fill_layer(fill)
    window._update_action_states()
    assert not window.action_edit_fill.isEnabled()

    source = _source(20, 12)
    smart = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="logo.png", source_width=20, source_height=12
        ),
    )
    window._update_action_states()
    assert window.action_edit_smart_object.isEnabled()
    assert window.action_replace_smart_contents.isEnabled()
    assert window.action_reset_smart_object.isEnabled()
    assert window.action_rasterize_smart.isEnabled()

    smart.set_mask(np.full((smart.height, smart.width), 255, np.uint8))
    window._update_action_states()
    assert not window.action_edit_smart_object.isEnabled()
    assert not window.action_replace_smart_contents.isEnabled()
    assert not window.action_reset_smart_object.isEnabled()
    assert window.action_rasterize_smart.isEnabled()

    document.add_fill_layer(FillProperties(color=(30, 60, 90, 255)))
    window.layers_panel.refresh()
    subtitles = {}
    for index in range(window.layers_panel.layer_list.count()):
        item = window.layers_panel.layer_list.item(index)
        subtitles[item.text()] = str(item.data(ROLE_SUBTITLE))
    assert any(
        "Tô" in value for value in subtitles.values()
    )
    assert any("Smart object" in value for value in subtitles.values())
    document.mark_clean()
    window.close()
    window.deleteLater()


def test_layers_panel_double_click_requests_editors(qapp):
    from core.fill_layer import FillProperties
    from ui.layers_panel import LayersPanel

    document = _document((30, 20))
    fill = document.add_fill_layer(FillProperties())
    smart = document.add_smart_object_layer(
        _source(10, 8),
        SmartObjectProperties(
            source_name="s.png", source_width=10, source_height=8
        ),
    )
    panel = LayersPanel()
    panel.bind_document(document)
    panel.refresh()
    calls: list[tuple[str, str]] = []
    panel.fill_edit_requested.connect(
        lambda layer_id: calls.append(("fill", layer_id))
    )
    panel.smart_edit_requested.connect(
        lambda layer_id: calls.append(("smart", layer_id))
    )
    for index in range(panel.layer_list.count()):
        item = panel.layer_list.item(index)
        if item.text() == fill.name:
            panel.layer_list._on_item_double_clicked(item)
        if item.text() == smart.name:
            panel.layer_list._on_item_double_clicked(item)
    assert ("fill", fill.id) in calls
    assert ("smart", smart.id) in calls
    panel.deleteLater()


def test_properties_panel_shows_fill_and_smart(tmp_path, qapp):
    from core.fill_layer import FillProperties

    window, document = _window(tmp_path)
    document.add_fill_layer(FillProperties(fill_type="gradient", angle=45))
    window.properties_panel.refresh()
    info = window.properties_panel._values["layer_info"].text()
    assert "Layer tô" in info and "45°" in info
    document.add_smart_object_layer(
        _source(12, 8),
        SmartObjectProperties(
            source_name="sky.png",
            source_width=12,
            source_height=8,
            angle=15,
            scale=110,
        ),
    )
    window.properties_panel.refresh()
    info = window.properties_panel._values["layer_info"].text()
    assert "Smart object" in info
    assert "sky.png" in info
    assert "15°" in info
    document.mark_clean()
    window.close()
    window.deleteLater()
