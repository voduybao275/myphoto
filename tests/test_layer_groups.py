"""Kiểm thử layer group: compositor, Document API, Undo, định dạng .mps và UI."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from config.settings import SettingsStore
from core.adjustment_layer import AdjustmentProperties
from core.canvas import composite_layers
from core.document import Document
from core.layer import Layer, LayerKind
from formats.native_project import ProjectFormatError, load_project, save_project
from ui.layers_panel import ROLE_DEPTH, ROLE_KIND, ROLE_LAYER_ID, LayersPanel
from ui.main_window import MainWindow


def _document(size=(4, 4), color=(0, 0, 0, 255)) -> Document:
    document = Document(*size)
    document.add_layer(name="Background", color=color, record=False)
    return document


def _pixel(document: Document, x: int = 0, y: int = 0):
    return composite_layers(document.layers.layers, document.width, document.height)[
        y, x
    ]


# ------------------------------------------------------------------ compositor
def test_group_opacity_applies_to_whole_subtree():
    document = _document((4, 4), color=(0, 0, 0, 255))
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group(record=False)
    red.group_id = group.id
    group.opacity = 0.5

    pixel = _pixel(document)
    # Nhóm 50% trên nền đen đục cho đỏ 128, alpha cuối vẫn 255.
    assert pixel.tolist() == [128, 0, 0, 255]


def test_group_blend_mode_applies_to_merged_content():
    document = _document((4, 4), color=(100, 150, 200, 255))
    green = document.add_layer(name="Green", color=(0, 255, 0, 255), record=False)
    group = document.add_group(record=False)
    green.group_id = group.id
    group.blend_mode = "multiply"

    pixel = _pixel(document)
    assert pixel.tolist() == [0, 150, 0, 255]


def test_group_mask_hides_part_of_subtree():
    document = _document((4, 2), color=(0, 0, 0, 255))
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group(record=False)
    red.group_id = group.id
    mask = np.zeros((2, 4), dtype=np.uint8)
    mask[:, :2] = 255
    group.set_mask(mask)

    result = composite_layers(document.layers.layers, 4, 2)
    assert result[0, 0].tolist() == [255, 0, 0, 255]
    assert result[0, 3].tolist() == [0, 0, 0, 255]


def test_adjustment_inside_group_does_not_affect_layers_below():
    document = _document((2, 1), color=(100, 100, 100, 255))
    inside = document.add_layer(name="Inside", color=(255, 0, 0, 255), record=False)
    inside.width = 1
    inside.set_pixels(np.zeros((1, 1, 4), dtype=np.uint8))
    inside.pixels[0, 0] = (255, 0, 0, 255)
    group = document.add_group(record=False)
    inside.group_id = group.id
    adjustment = document.add_adjustment_layer(
        AdjustmentProperties(kind="invert"), record=False
    )
    adjustment.group_id = group.id

    result = composite_layers(document.layers.layers, 2, 1)
    # Vùng có layer đỏ bị đảo thành cyan; vùng nền bên ngoài nhóm giữ nguyên.
    assert result[0, 0].tolist() == [0, 255, 255, 255]
    assert result[0, 1].tolist() == [100, 100, 100, 255]


def test_group_mask_does_not_hide_sibling_layer_outside_group():
    document = _document((2, 1), color=(0, 0, 0, 255))
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group(record=False)
    red.group_id = group.id
    group.set_mask(np.zeros((1, 2), dtype=np.uint8))

    document.set_active_layer(document.layers[0])
    green = document.add_layer(
        layer=Layer(1, 1, "Green"), select=False, record=False
    )
    green.fill((0, 255, 0, 255))
    green.offset_x = 1

    result = composite_layers(document.layers.layers, 2, 1)
    assert result[0, 0].tolist() == [0, 0, 0, 255]
    assert result[0, 1].tolist() == [0, 255, 0, 255]


def test_nested_group_hidden_outer_hides_inner():
    document = _document((2, 2), color=(0, 0, 0, 255))
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    inner = document.add_group(name="Inner", record=False)
    red.group_id = inner.id
    outer = document.add_group(name="Outer", record=False)
    inner.group_id = outer.id
    outer.visible = False

    assert _pixel(document).tolist() == [0, 0, 0, 255]


# ------------------------------------------------------------------ Document API
def test_group_layers_puts_members_in_group_and_undo_restores():
    document = _document()
    lower = document.add_layer(name="Lower", color=(0, 255, 0, 255), record=False)
    upper = document.add_layer(name="Upper", color=(0, 0, 255, 255), record=False)
    document.set_active_layer(upper)

    group = document.group_layers()
    assert group is not None
    assert group.kind == LayerKind.GROUP
    assert group.name == "Group 1"
    assert document.active_layer is group
    assert upper.group_id == group.id
    assert lower.group_id is None
    assert document.layers.children_of(group.id) == [upper]

    document.undo()
    assert document.layers.get(group.id) is None
    assert upper.group_id is None
    assert [layer.name for layer in document.layers] == [
        "Background",
        "Lower",
        "Upper",
    ]
    assert document.active_layer is upper

    document.redo()
    assert document.layers.get(group.id) is group
    assert upper.group_id == group.id


def test_group_selected_layers_and_inherit_parent():
    document = _document()
    first = document.add_layer(name="One", color=(1, 2, 3, 255), record=False)
    second = document.add_layer(name="Two", color=(4, 5, 6, 255), record=False)
    document.set_active_layer(second)
    outer = document.group_layers([first, second])
    assert outer is not None

    third = document.add_layer(name="Three", color=(7, 8, 9, 255), record=False)
    document.set_active_layer(third)
    inner = document.group_layers()
    assert inner is not None
    assert inner.group_id == outer.id
    assert third.group_id == inner.id

    outer_children = document.layers.children_of(outer.id)
    assert [layer.name for layer in outer_children] == ["One", "Two", "Group 2"]


def test_add_layer_inside_active_group_and_add_nested_group():
    document = _document()
    group = document.add_group()
    layer = document.add_layer(name="Child", color=(255, 255, 255, 255))
    assert layer.group_id == group.id
    assert document.layers.children_of(group.id) == [layer]

    nested = document.add_group()
    assert nested.group_id == group.id
    assert document.layers.children_of(group.id)[-1] is nested


def test_ungroup_moves_children_to_parent_and_undo():
    document = _document()
    outer = document.add_group(name="Outer")
    inner = document.add_group(name="Inner")
    one = document.add_layer(name="One", color=(1, 1, 1, 255), record=False)
    two = document.add_layer(name="Two", color=(2, 2, 2, 255), record=False)
    assert inner.group_id == outer.id
    assert one.group_id == inner.id
    assert two.group_id == inner.id

    assert document.ungroup_layer(inner) is True
    assert document.layers.get(inner.id) is None
    assert one.group_id == outer.id
    assert two.group_id == outer.id

    document.undo()
    assert document.layers.get(inner.id) is inner
    assert one.group_id == inner.id
    assert two.group_id == inner.id


def test_ungroup_refuses_group_with_mask():
    document = _document()
    group = document.add_group()
    group.set_mask(np.full((document.height, document.width), 255, dtype=np.uint8))
    with pytest.raises(ValueError):
        document.ungroup_layer(group)
    assert document.layers.get(group.id) is group


def test_duplicate_group_copies_subtree_and_remaps_ids():
    document = _document()
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group()
    red.group_id = group.id
    document.set_active_layer(group)

    clone = document.duplicate_layer(group)
    assert clone is not group
    assert clone.kind == LayerKind.GROUP
    assert clone.group_id is None
    children = document.layers.children_of(clone.id)
    assert len(children) == 1
    assert children[0].id != red.id
    assert children[0].group_id == clone.id
    assert red.group_id == group.id

    document.undo()
    assert len(document.layers) == 3


def test_remove_group_removes_subtree_and_undo():
    document = _document()
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group()
    red.group_id = group.id

    assert document.remove_layer(group) is True
    assert document.layers.get(group.id) is None
    assert document.layers.get(red.id) is None
    assert [layer.name for layer in document.layers] == ["Background"]

    document.undo()
    assert document.layers.get(group.id) is group
    assert document.layers.get(red.id) is red
    assert red.group_id == group.id


def test_merge_down_guards_against_groups_and_cross_group():
    document = _document()
    lower = document.add_layer(name="Lower", color=(0, 255, 0, 255), record=False)
    upper = document.add_layer(name="Upper", color=(0, 0, 255, 255), record=False)
    assert document.merge_down() is True
    assert [layer.name for layer in document.layers] == ["Background", "Lower"]

    group = document.add_group(name="G")
    child = document.add_layer(name="Child", color=(255, 255, 0, 255))
    assert child.group_id == group.id
    assert document.merge_down() is False  # nhóm không merge trực tiếp

    document.set_active_layer(group)
    assert document.merge_down() is False


def test_group_mask_uses_canvas_size_and_geometry_keeps_group():
    document = _document((8, 6))
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group()
    red.group_id = group.id
    document.set_active_layer(group)

    assert document.add_layer_mask() is True
    assert group.mask.shape == (6, 8)

    document.resize_image(12, 9)
    # Nhóm là layer canvas-size: giữ khung 1x1, mask co giãn theo tài liệu.
    assert group.width == 1
    assert group.height == 1
    assert group.mask.shape == (9, 12)
    assert group.group_id is None
    assert document.layers.get(group.id) is group
    assert red.group_id == group.id


def test_transform_group_is_rejected():
    document = _document()
    group = document.add_group()
    document.set_active_layer(group)
    with pytest.raises(ValueError):
        document.transform_layer("rotate_cw")


# ------------------------------------------------------------------ .mps
def _nested_project() -> Document:
    document = _document((8, 6))
    document.name = "Nhóm"
    red = document.add_layer(name="Red", color=(200, 10, 20, 255), record=False)
    outer = document.add_group(name="Outer", record=False)
    red.group_id = outer.id
    inner = document.add_group(name="Inner", record=False)
    inner.group_id = outer.id
    blue = document.add_layer(name="Blue", color=(10, 20, 200, 255), record=False)
    blue.group_id = inner.id
    outer.opacity = 0.8
    outer.blend_mode = "multiply"
    outer.set_mask(np.full((6, 8), 255, dtype=np.uint8))
    blue.offset_x = 2
    blue.offset_y = 1
    document.mark_clean()
    return document


def test_project_roundtrip_preserves_group_hierarchy(tmp_path):
    document = _nested_project()
    target = save_project(document, tmp_path / "nhom.mps")

    loaded = load_project(target)
    assert loaded.width == 8 and loaded.height == 6
    names = [layer.name for layer in loaded.layers]
    assert names == ["Background", "Red", "Blue", "Inner", "Outer"]
    by_name = {layer.name: layer for layer in loaded.layers}
    loaded_outer = by_name["Outer"]
    assert loaded_outer.kind == LayerKind.GROUP
    assert loaded_outer.mask is not None
    assert loaded_outer.mask.shape == (6, 8)
    assert loaded_outer.opacity == pytest.approx(0.8)
    assert loaded_outer.blend_mode == "multiply"
    loaded_red = by_name["Red"]
    loaded_inner = by_name["Inner"]
    loaded_blue = by_name["Blue"]
    assert loaded_red.group_id == loaded_outer.id
    assert loaded_inner.group_id == loaded_outer.id
    assert loaded_blue.group_id == loaded_inner.id
    assert loaded_blue.offset_x == 2 and loaded_blue.offset_y == 1

    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["version"] == 9
    entries = {entry["name"]: entry for entry in manifest["layers"]}
    assert entries["Blue"]["group_id"] == entries["Inner"]["id"]
    assert entries["Background"]["group_id"] is None


def _rewrite_manifest(source: Path, destination: Path, mutate) -> Path:
    with zipfile.ZipFile(source) as archive:
        items = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(items["manifest.json"].decode("utf-8"))
    mutate(manifest)
    items["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in items.items():
            archive.writestr(name, data)
    return destination


def test_project_rejects_missing_group_parent(tmp_path):
    source = save_project(_nested_project(), tmp_path / "goc.mps")

    def mutate(manifest):
        for entry in manifest["layers"]:
            if entry["name"] == "Red":
                entry["group_id"] = "khong-ton-tai"
                return

    broken = _rewrite_manifest(source, tmp_path / "thieu-cha.mps", mutate)
    with pytest.raises(ProjectFormatError):
        load_project(broken)


def test_project_rejects_group_cycle(tmp_path):
    source = save_project(_nested_project(), tmp_path / "goc2.mps")

    def mutate(manifest):
        ids = {entry["name"]: entry["id"] for entry in manifest["layers"]}
        for entry in manifest["layers"]:
            if entry["name"] == "Outer":
                entry["group_id"] = ids["Inner"]
            elif entry["name"] == "Inner":
                entry["group_id"] = ids["Outer"]

    broken = _rewrite_manifest(source, tmp_path / "vong-lap.mps", mutate)
    with pytest.raises(ProjectFormatError):
        load_project(broken)


def test_project_v4_without_group_id_loads_as_roots(tmp_path):
    source = save_project(_nested_project(), tmp_path / "v5.mps")

    def mutate(manifest):
        manifest["version"] = 4
        for entry in manifest["layers"]:
            entry.pop("group_id", None)

    legacy = _rewrite_manifest(source, tmp_path / "v4.mps", mutate)
    loaded = load_project(legacy)
    assert all(layer.group_id is None for layer in loaded.layers)


# ------------------------------------------------------------------ UI
def _window_with(document: Document, tmp_path) -> MainWindow:
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window._add_document_tab(document)
    return window


def test_panel_shows_hierarchy_and_actions(qapp, tmp_path):
    document = _document()
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group(name="Folder", record=False)
    red.group_id = group.id
    document.set_active_layer(group)
    window = _window_with(document, tmp_path)

    panel = window.layers_panel
    rows = [
        (panel.layer_list.item(i).text(), panel.layer_list.item(i).data(ROLE_DEPTH))
        for i in range(panel.layer_list.count())
    ]
    assert ("Folder", 0) in rows
    assert ("Red", 1) in rows
    assert panel.layer_list.item(0).data(ROLE_KIND) == LayerKind.GROUP
    assert panel._group_button.isEnabled()
    assert window.action_ungroup_layers.isEnabled()

    info = window.properties_panel._values["layer_info"].text()
    assert "Nhóm · 1 layer trực tiếp" in info

    panel._on_new_group()
    assert document.active_layer.kind == LayerKind.GROUP
    assert document.active_layer.group_id == group.id


def test_ui_new_layer_inside_group_and_actions_disable_for_group(
    qapp, tmp_path
):
    document = _document()
    red = document.add_layer(name="Red", color=(255, 0, 0, 255), record=False)
    group = document.add_group(name="Folder", record=False)
    red.group_id = group.id
    document.set_active_layer(group)
    window = _window_with(document, tmp_path)
    panel = window.layers_panel

    window._update_action_states()
    assert window.action_new_group.isEnabled()
    assert window.action_group_layers.isEnabled()
    assert window.action_ungroup_layers.isEnabled()
    assert not window.action_layer_rotate_cw.isEnabled()
    assert not window.action_filter_invert.isEnabled()

    window._on_new_layer()
    new_layer = document.active_layer
    assert new_layer.group_id == group.id
    item_depths = {
        panel.layer_list.item(i).data(ROLE_LAYER_ID): panel.layer_list.item(i).data(
            ROLE_DEPTH
        )
        for i in range(panel.layer_list.count())
    }
    assert item_depths[group.id] == 0
    assert item_depths[red.id] == 1
    assert item_depths[new_layer.id] == 1

    window._on_undo()
    assert len(document.layers) == 3
