"""Kiểm thử thư viện preset SQLite và preset trong hộp thoại điều chỉnh."""

from __future__ import annotations

import sqlite3

import pytest

from core.adjustment_layer import AdjustmentProperties
from core.batch import BatchAction, BatchStep
from core.presets import MAX_PRESET_NAME, PresetError, PresetStore


def _store(tmp_path) -> PresetStore:
    return PresetStore(tmp_path / "presets.sqlite3")


# ------------------------------------------------------------------ lõi
def test_save_list_get_and_persistence(tmp_path):
    store = _store(tmp_path)
    saved = store.save(
        "adjustment", "Ấm áp", {"kind": "levels", "levels_black": 12}
    )
    assert saved.preset_id > 0
    assert saved.kind == "adjustment"
    assert saved.name == "Ấm áp"
    assert saved.payload["levels_black"] == 12

    reopened = _store(tmp_path)
    loaded = reopened.get("adjustment", "Ấm áp")
    assert loaded is not None
    assert loaded.payload == {"kind": "levels", "levels_black": 12}
    assert reopened.count("adjustment") == 1


def test_names_are_sorted_case_insensitively(tmp_path):
    store = _store(tmp_path)
    for name in ("beta", "Alpha", "gamma"):
        store.save("action", name, {"steps": []})
    assert [preset.name for preset in store.list("action")] == [
        "Alpha",
        "beta",
        "gamma",
    ]
    assert store.get("action", "ALPHA") is not None


def test_duplicate_name_requires_explicit_overwrite(tmp_path):
    store = _store(tmp_path)
    store.save("action", "Batch", {"steps": []})
    with pytest.raises(PresetError):
        store.save("action", "batch", {"steps": []})
    updated = store.save("action", "Batch", {"steps": [1]}, overwrite=True)
    assert updated.payload == {"steps": [1]}
    assert store.count("action") == 1


def test_invalid_name_kind_and_payload_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(PresetError):
        store.save("adjustment", "   ", {"kind": "levels"})
    with pytest.raises(PresetError):
        store.save("adjustment", "x" * (MAX_PRESET_NAME + 1), {"kind": "levels"})
    with pytest.raises(PresetError):
        store.save("unknown", "Tên", {"kind": "levels"})
    with pytest.raises(PresetError):
        store.save("adjustment", "Tên", ["không phải dict"])
    with pytest.raises(PresetError):
        store.save("adjustment", "Tên", {"bad": object()})


def test_delete_and_rename(tmp_path):
    store = _store(tmp_path)
    store.save("adjustment", "Cũ", {"kind": "invert"})
    renamed = store.rename("adjustment", "Cũ", "Mới")
    assert renamed.name == "Mới"
    assert store.get("adjustment", "Cũ") is None
    assert store.delete("adjustment", "mới") is True
    assert store.delete("adjustment", "mới") is False
    with pytest.raises(PresetError):
        store.rename("adjustment", "Mất", "X")


def test_adjustment_helpers_roundtrip(tmp_path):
    store = _store(tmp_path)
    properties = AdjustmentProperties(
        kind="levels",
        levels_black=10,
        levels_white=240,
        levels_gamma=1.3,
        curve_points=((0, 0), (128, 150), (255, 255)),
    )
    store.save_adjustment("Levels mềm", properties)
    loaded = store.load_adjustment("Levels mềm")
    assert loaded == properties
    assert store.load_adjustment("không có") is None
    with pytest.raises(PresetError):
        store.save_adjustment("Sai", {"kind": "levels"})


def test_action_helpers_roundtrip(tmp_path):
    store = _store(tmp_path)
    action = BatchAction(
        name="Ảnh web",
        steps=(BatchStep("auto_levels"), BatchStep("resize_max", max_size=1600)),
    )
    store.save_action("Ảnh web", action)
    loaded = store.load_action("Ảnh web")
    assert loaded == action
    assert store.load_action("khác") is None
    with pytest.raises(PresetError):
        store.save_action("Sai", ("auto_levels",))


def test_corrupt_payload_rows_are_skipped(tmp_path):
    store = _store(tmp_path)
    store.save("adjustment", "Tốt", {"kind": "invert"})
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "INSERT INTO presets(kind, name, payload, updated_at) "
            "VALUES('adjustment', 'Hỏng', '{không-phải-json', 'now')"
        )
    presets = store.list("adjustment")
    assert [preset.name for preset in presets] == ["Tốt"]


# ------------------------------------------------------------------ giao diện
def test_adjustment_dialog_preset_save_apply_delete(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from ui.dialogs import AdjustmentLayerDialog

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    store = _store(tmp_path)
    dialog = AdjustmentLayerDialog(
        AdjustmentProperties(
            kind="levels", levels_black=20, levels_white=220
        ),
        preset_store=store,
    )
    assert dialog.preset_combo.count() == 1
    dialog.preset_name_edit.setText("Levels ảnh cưới")
    dialog._on_save_preset()
    assert store.get("adjustment", "Levels ảnh cưới") is not None
    assert dialog.preset_combo.count() == 2
    assert dialog.preset_combo.currentData() == "Levels ảnh cưới"

    dialog.levels_black_field.setValue(0)
    dialog.levels_white_field.setValue(255)
    dialog.preset_combo.setCurrentIndex(0)
    dialog.preset_combo.setCurrentIndex(1)
    assert dialog.levels_black_field.value() == 20
    assert dialog.levels_white_field.value() == 220
    assert dialog.levels_histogram.black() == 20

    dialog._on_delete_preset()
    assert store.get("adjustment", "Levels ảnh cưới") is None
    assert dialog.preset_combo.count() == 1
    dialog.deleteLater()


def test_adjustment_dialog_filters_presets_by_kind(qapp, tmp_path):
    from ui.dialogs import AdjustmentLayerDialog

    store = _store(tmp_path)
    store.save_adjustment(
        "Sáng", AdjustmentProperties(kind="brightness_contrast", brightness=25)
    )
    dialog = AdjustmentLayerDialog(
        AdjustmentProperties(kind="levels"), preset_store=store
    )
    assert dialog.preset_combo.count() == 1

    other = AdjustmentLayerDialog(
        AdjustmentProperties(kind="brightness_contrast"), preset_store=store
    )
    assert other.preset_combo.count() == 2
    other.preset_combo.setCurrentIndex(1)
    assert other.brightness_field.value() == 25
    dialog.deleteLater()
    other.deleteLater()


def test_main_window_batch_action_and_preset_store(tmp_path, qapp):
    from config.settings import SettingsStore
    from ui.main_window import MainWindow

    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    assert window.action_batch_processing.isEnabled()
    assert window.preset_store.path == tmp_path / "presets.sqlite3"
    window.close()
