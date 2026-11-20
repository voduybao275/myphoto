"""Kiểm thử chọn nhiều layer (Shift/Ctrl) và thao tác hàng loạt."""

from __future__ import annotations

import compat.qt  # noqa: F401
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from config.settings import SettingsStore
from core.document import Document
from core.layer import LayerKind
from ui.layers_panel import ROLE_LAYER_ID, LayersPanel
from ui.main_window import MainWindow


def _document(count: int = 3) -> tuple[Document, list]:
    document = Document(40, 30, name="Multi Select")
    layers = []
    for index in range(count):
        layers.append(
            document.add_layer(
                name=f"Layer {index + 1}",
                color=(30 * (index + 1), 10, 0, 255),
                record=False,
            )
        )
    return document, layers


def _panel(document: Document) -> LayersPanel:
    panel = LayersPanel()
    panel.resize(280, 400)
    panel.show()
    panel.bind_document(document)
    return panel


def _click_row(panel: LayersPanel, row: int, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    item = panel.layer_list.item(row)
    position = panel.layer_list.visualItemRect(item).center()
    QTest.mouseClick(
        panel.layer_list.viewport(),
        Qt.MouseButton.LeftButton,
        modifier,
        position,
    )


# ------------------------------------------------------------------ Document API
def test_set_selected_layers_keeps_set_and_leader():
    document, layers = _document()
    changes: list[int] = []
    document.layer_selection_changed.connect(
        lambda: changes.append(document.selected_layer_count)
    )

    document.set_selected_layers(layers, active=layers[1])

    assert [layer.id for layer in document.selected_layers] == [
        layer.id for layer in layers
    ]
    assert document.active_layer is layers[1]
    assert changes == [3]

    document.set_active_layer(layers[2])
    assert document.selected_layer_count == 1
    assert document.active_layer is layers[2]

    with pytest.raises(ValueError):
        document.set_selected_layers(["missing-layer"])


def test_duplicate_and_remove_multiple_layers_with_undo():
    document, layers = _document()
    document.set_selected_layers(layers, active=layers[-1])

    clones = document.duplicate_layers()
    assert len(clones) == 3
    assert len(document.layers) == 6
    assert {layer.id for layer in document.selected_layers} == {
        clone.id for clone in clones
    }
    assert document.active_layer is clones[0]

    document.undo()
    assert [layer.id for layer in document.layers] == [layer.id for layer in layers]

    document.set_selected_layers([layers[0], layers[1]], active=layers[0])
    assert document.remove_layers() == 2
    assert [layer.name for layer in document.layers] == ["Layer 3"]
    assert document.active_layer is layers[2]

    document.undo()
    assert len(document.layers) == 3
    assert {layer.id for layer in document.selected_layers} == {layers[2].id}


def test_remove_selected_group_removes_its_children():
    document, layers = _document(2)
    group = document.group_layers(layers, name="Folder")
    child = document.add_layer(name="Child", color=(1, 2, 3, 255), record=False)
    assert child.group_id == group.id

    document.set_selected_layers([group])
    assert document.remove_layers() == 4
    assert len(document.layers) == 0


def test_merge_selected_layers_into_one_and_reject_mixed_groups():
    document, layers = _document()
    document.set_selected_layers([layers[0], layers[2]], active=layers[2])

    assert document.merge_layers()
    assert len(document.layers) == 2
    assert document.active_layer is not None
    assert document.active_layer.name == layers[0].name
    assert document.active_layer.pixels[..., 3].max() > 0

    document.undo()
    assert len(document.layers) == 3

    group = document.group_layers([layers[0]], name="Folder")
    document.set_selected_layers([layers[0], layers[1]])
    assert not document.merge_layers()
    assert group.kind == LayerKind.GROUP


def test_batch_properties_apply_to_every_selected_layer():
    document, layers = _document()
    document.set_selected_layers(layers)

    assert document.set_layers_locked(True) == 3
    assert all(layer.locked for layer in layers)

    assert document.set_layers_opacity(0.4) == 3
    assert all(abs(layer.opacity - 0.4) < 1e-6 for layer in layers)

    assert document.set_layers_blend_mode("multiply") == 3
    assert all(layer.blend_mode == "multiply" for layer in layers)

    assert document.set_layers_visible(False) == 3
    assert all(not layer.visible for layer in layers)

    document.undo()
    document.undo()
    document.undo()
    document.undo()
    assert all(layer.visible for layer in layers)
    assert all(layer.blend_mode == "normal" for layer in layers)


# --------------------------------------------------------------------------- UI
def test_shift_click_selects_range_and_ctrl_click_toggles(qapp):
    document, layers = _document()
    panel = _panel(document)
    qapp.processEvents()

    _click_row(panel, 0)
    qapp.processEvents()
    assert [layer.id for layer in document.selected_layers] == [layers[-1].id]

    _click_row(panel, 2, Qt.KeyboardModifier.ShiftModifier)
    qapp.processEvents()
    assert {layer.id for layer in document.selected_layers} == {
        layer.id for layer in layers
    }
    assert document.active_layer is layers[0]
    assert len(panel.layer_list.selectedItems()) == 3

    _click_row(panel, 1, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    assert {layer.id for layer in document.selected_layers} == {
        layers[0].id,
        layers[2].id,
    }
    assert len(panel.layer_list.selectedItems()) == 2
    panel.close()


def test_eye_click_keeps_multi_selection(qapp):
    document, layers = _document()
    panel = _panel(document)
    qapp.processEvents()
    panel._on_selection_changed([layer.id for layer in layers], layers[0].id)
    qapp.processEvents()
    assert document.selected_layer_count == 3

    item = panel.layer_list.item(1)
    row_layer_id = str(item.data(ROLE_LAYER_ID))
    rect = panel.layer_list.visualItemRect(item)
    QTest.mouseClick(
        panel.layer_list.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(rect.x() + 6, rect.center().y()),
    )
    qapp.processEvents()

    assert document.selected_layer_count == 3
    row_layer = document.layers.get(row_layer_id)
    assert row_layer is not None
    assert not row_layer.visible
    panel.close()


def test_context_menu_keeps_selection_and_changes_leader(qapp):
    document, layers = _document()
    panel = _panel(document)
    qapp.processEvents()
    panel._on_selection_changed([layer.id for layer in layers], layers[0].id)
    qapp.processEvents()

    received: list[str] = []
    panel.layer_list.context_requested.connect(
        lambda layer_id, _position: received.append(layer_id)
    )
    item = panel.layer_list.item(1)
    panel.layer_list._on_context_menu(
        panel.layer_list.visualItemRect(item).center()
    )
    qapp.processEvents()

    assert len(panel.layer_list.selectedItems()) == 3
    assert document.active_layer is layers[1]
    assert received == [layers[1].id]
    panel.close()


def test_panel_actions_apply_to_whole_selection(qapp):
    document, layers = _document()
    panel = _panel(document)
    panel._on_selection_changed([layer.id for layer in layers], layers[0].id)
    qapp.processEvents()

    panel._on_duplicate_layer()
    assert len(document.layers) == 6
    assert document.selected_layer_count == 3

    panel._on_delete_layer()
    assert len(document.layers) == 3
    assert document.selected_layer_count == 1

    document.set_selected_layers(layers, active=layers[0])
    panel._on_lock_clicked(True)
    assert all(layer.locked for layer in layers)

    panel.blend_combo.setCurrentIndex(panel.blend_combo.findData("screen"))
    assert all(layer.blend_mode == "screen" for layer in layers)

    panel.opacity_spin.setValue(55)
    assert all(abs(layer.opacity - 0.55) < 1e-6 for layer in layers)
    panel.close()


def test_main_window_group_and_merge_use_selection(qapp, tmp_path):
    document, layers = _document()
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    window._add_document_tab(document)
    qapp.processEvents()

    document.set_selected_layers(layers, active=layers[0])
    qapp.processEvents()
    window._on_group_layers()
    qapp.processEvents()

    group = document.active_layer
    assert group is not None and group.kind == LayerKind.GROUP
    assert all(layer.group_id == group.id for layer in layers)

    document.set_selected_layers(layers, active=layers[0])
    qapp.processEvents()
    window._on_merge_down()
    qapp.processEvents()
    assert len(document.layers) == 2
    assert document.active_layer is not None
    assert document.active_layer.kind == LayerKind.PIXEL
    assert document.active_layer.group_id == group.id

    window.tabs.removeTab(0)
    window.close()
