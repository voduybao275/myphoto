"""Kiểm thử xử lý hàng loạt: bước xử lý, runner và giao diện."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from core.batch import (
    MAX_BATCH_FILES,
    BatchAction,
    BatchError,
    BatchRunner,
    BatchStep,
    apply_step,
    apply_steps,
)
from formats.export_manager import export_image
from formats.import_manager import load_image_rgba


def _image(width=24, height=16, color=(90, 120, 160, 255)) -> np.ndarray:
    array = np.empty((height, width, 4), dtype=np.uint8)
    array[...] = color
    array[..., 0] = np.linspace(20, 220, width, dtype=np.uint8)[None, :]
    return array


def _source_file(path, width=24, height=16) -> None:
    export_image(path, _image(width, height))


# ------------------------------------------------------------------ bước
def test_step_validation_and_clamping():
    with pytest.raises(ValueError):
        BatchStep("không tồn tại")
    step = BatchStep(
        "brightness_contrast", brightness=500, contrast=-500
    )
    assert step.brightness == 100
    assert step.contrast == -100
    levels = BatchStep("levels", levels_black=240, levels_white=200)
    assert levels.levels_white == 241
    resize = BatchStep("resize_percent", percent=1)
    assert resize.percent == 10
    assert BatchStep("resize_max", max_size=1).max_size == 16


def test_step_dict_roundtrip_and_summary():
    step = BatchStep("unsharp_mask", amount=150, radius=1.5, threshold=8)
    assert BatchStep.from_dict(step.to_dict()) == step
    assert "150" in step.summary()
    assert BatchStep("resize_max", max_size=1280).summary() == "Cạnh dài 1280 px"
    assert BatchStep("levels", levels_gamma=1.4).summary().startswith("Đen 0")
    with pytest.raises(ValueError):
        BatchStep.from_dict("sai")
    with pytest.raises(ValueError):
        BatchStep.from_dict({"kind": "resize_max", "max_size": "abc"})


def test_action_validation_and_roundtrip():
    with pytest.raises(ValueError):
        BatchAction(name="Rỗng", steps=())
    with pytest.raises(ValueError):
        BatchAction(name="x" * 60, steps=(BatchStep("invert"),))
    with pytest.raises(ValueError):
        BatchAction(name="Sai", steps=("invert",))
    action = BatchAction(
        name="Web", steps=(BatchStep("auto_levels"), BatchStep("resize_max"))
    )
    assert BatchAction.from_dict(action.to_dict()) == action
    assert "2 bước" in action.summary()
    with pytest.raises(ValueError):
        BatchAction.from_dict({"steps": "sai"})


def test_apply_steps_color_and_resize():
    source = _image(40, 20)
    gray = apply_step(source, BatchStep("grayscale"))
    assert np.array_equal(gray[..., 0], gray[..., 1])
    assert np.array_equal(gray[..., 3], source[..., 3])

    inverted = apply_step(source, BatchStep("invert"))
    assert np.array_equal(inverted[..., 0], 255 - source[..., 0])
    assert np.array_equal(inverted[..., 3], source[..., 3])

    half = apply_step(source, BatchStep("resize_percent", percent=50))
    assert half.shape[:2] == (10, 20)

    limited = apply_step(source, BatchStep("resize_max", max_size=16))
    assert limited.shape[:2] == (8, 16)
    unchanged = apply_step(limited, BatchStep("resize_max", max_size=64))
    assert np.array_equal(unchanged, limited)

    brighter = apply_step(source, BatchStep("brightness_contrast", brightness=40))
    assert int(brighter[..., :3].mean()) > int(source[..., :3].mean())

    levels = apply_step(
        source,
        BatchStep("levels", levels_black=20, levels_white=200, levels_gamma=0.8),
    )
    assert levels.dtype == np.uint8
    assert levels.shape == source.shape

    blurred = apply_step(source, BatchStep("gaussian_blur", radius=2.0))
    assert blurred.shape == source.shape
    sharpened = apply_step(source, BatchStep("unsharp_mask", amount=80))
    assert sharpened.shape == source.shape


def test_apply_auto_levels_and_auto_contrast():
    narrow = _image(30, 10, (100, 100, 100, 255))
    narrow[..., 0] = np.linspace(60, 180, 30, dtype=np.uint8)[None, :]
    stretched = apply_step(narrow, BatchStep("auto_levels"))
    values = stretched[..., 0]
    assert values.min() < 10 and values.max() > 245

    contrast = apply_step(narrow, BatchStep("auto_contrast"))
    assert contrast[..., 0].max() > narrow[..., 0].max()


def test_apply_step_rejects_bad_arrays():
    with pytest.raises(BatchError):
        apply_step(np.zeros((4, 4, 3), np.uint8), BatchStep("invert"))
    with pytest.raises(BatchError):
        apply_step(np.zeros((4, 4, 4), np.float32), BatchStep("invert"))
    with pytest.raises(BatchError):
        apply_steps(_image(), ["invert"])


# ----------------------------------------------------------------- runner
def test_runner_writes_suffixed_output_and_keeps_original(tmp_path):
    source = tmp_path / "photo.png"
    _source_file(source)
    original = source.read_bytes()
    runner = BatchRunner(
        [BatchStep("grayscale"), BatchStep("resize_percent", percent=50)],
        tmp_path,
    )
    results = runner.run([source])
    assert [item.status for item in results] == ["ok"]
    output = results[0].output
    assert output is not None and output.name == "photo_edited.png"
    assert source.read_bytes() == original
    with Image.open(output) as image:
        assert image.size == (12, 8)


def test_runner_never_overwrites_original_when_suffix_matches(tmp_path):
    source = tmp_path / "photo_edited.png"
    _source_file(source)
    original = source.read_bytes()
    runner = BatchRunner([BatchStep("invert")], tmp_path)
    results = runner.run([source])
    assert results[0].status == "ok"
    assert results[0].output.name == "photo_edited (2).png"
    assert source.read_bytes() == original


def test_runner_collision_and_overwrite(tmp_path):
    source = tmp_path / "photo.png"
    _source_file(source)
    (tmp_path / "photo_edited.png").write_bytes(b"old")
    runner = BatchRunner([BatchStep("invert")], tmp_path)
    results = runner.run([source])
    assert results[0].output.name == "photo_edited (2).png"

    overwrite = BatchRunner([BatchStep("invert")], tmp_path, overwrite=True)
    second = overwrite.run([source])
    assert second[0].output.name == "photo_edited.png"
    with Image.open(second[0].output) as image:
        assert image.mode == "RGBA"


def test_runner_formats_and_quality(tmp_path):
    source = tmp_path / "ảnh.png"
    _source_file(source)
    runner = BatchRunner(
        [BatchStep("auto_contrast")],
        tmp_path / "out",
        output_format="jpeg",
        quality=70,
    )
    results = runner.run([source])
    assert results[0].status == "ok"
    assert results[0].output.suffix == ".jpg"
    with Image.open(results[0].output) as image:
        assert image.mode == "RGB"

    webp = BatchRunner([BatchStep("invert")], tmp_path / "web", output_format="webp")
    result = webp.run([source])[0]
    assert result.output.suffix == ".webp"
    with Image.open(result.output) as image:
        assert image.mode in ("RGB", "RGBA")


def test_runner_reports_failures_and_continues(tmp_path, monkeypatch):
    good = tmp_path / "good.png"
    _source_file(good)
    corrupt = tmp_path / "bad.png"
    corrupt.write_bytes(b"not an image")
    missing = tmp_path / "missing.png"
    runner = BatchRunner([BatchStep("invert")], tmp_path / "out")
    results = runner.run([missing, corrupt, good])
    assert [item.status for item in results] == ["failed", "failed", "ok"]
    assert results[2].output is not None
    assert "Không tìm thấy" in results[0].message


def test_runner_progress_and_cancel_between_files(tmp_path):
    sources = []
    for index in range(3):
        path = tmp_path / f"image{index}.png"
        _source_file(path)
        sources.append(path)
    seen: list[tuple[int, int, str]] = []
    runner = BatchRunner([BatchStep("resize_percent", percent=50)], tmp_path / "out")
    cancel = {"value": False}

    def progress(done, total, source):
        seen.append((done, total, source.name))
        if done == 1:
            cancel["value"] = True

    results = runner.run(sources, progress=progress, cancel=lambda: cancel["value"])
    assert seen == [(1, 3, "image0.png")]
    assert [item.status for item in results] == ["ok", "cancelled", "cancelled"]
    assert len(list((tmp_path / "out").iterdir())) == 1


def test_runner_validation(tmp_path):
    with pytest.raises(BatchError):
        BatchRunner([], tmp_path)
    with pytest.raises(BatchError):
        BatchRunner([BatchStep("invert")], tmp_path, output_format="gif")
    with pytest.raises(BatchError):
        BatchRunner([BatchStep("invert")], tmp_path, suffix="  ")
    with pytest.raises(BatchError):
        BatchRunner([BatchStep("invert")], tmp_path, suffix="a/b")
    with pytest.raises(BatchError):
        BatchRunner([BatchStep("invert")], "")
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(BatchError):
        BatchRunner([BatchStep("invert")], file_path)
    runner = BatchRunner([BatchStep("invert")], tmp_path)
    with pytest.raises(BatchError):
        runner.run([])
    with pytest.raises(BatchError):
        runner.run([tmp_path / f"x{i}.png" for i in range(MAX_BATCH_FILES + 1)])


# ---------------------------------------------------------------- giao diện
def test_batch_step_dialog_switches_parameters(qapp):
    from ui.dialogs import BatchStepDialog

    dialog = BatchStepDialog()
    assert dialog.step.kind == "auto_levels"
    dialog.kind_combo.setCurrentIndex(
        dialog.kind_combo.findData("brightness_contrast")
    )
    assert dialog._stack.currentWidget() is dialog._pages["brightness_contrast"]
    dialog.brightness_spin.setValue(35)
    dialog.contrast_spin.setValue(-12)
    step = dialog.step
    assert step.kind == "brightness_contrast"
    assert step.brightness == 35 and step.contrast == -12

    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData("resize_max"))
    dialog.max_size_spin.setValue(1280)
    assert dialog.step.max_size == 1280
    dialog.deleteLater()

    blur = BatchStepDialog(BatchStep("gaussian_blur", radius=4.0))
    assert blur.kind_combo.currentData() == "gaussian_blur"
    assert blur.step.radius == pytest.approx(4.0)
    blur.deleteLater()


def test_batch_dialog_inputs_steps_and_run(tmp_path, qapp):
    from core.presets import PresetStore
    from ui.dialogs import BatchDialog

    store = PresetStore(tmp_path / "presets.sqlite3")
    first = tmp_path / "one.png"
    second = tmp_path / "two.png"
    _source_file(first)
    _source_file(second)
    ignored = tmp_path / "notes.txt"
    ignored.write_text("x", encoding="utf-8")

    dialog = BatchDialog(preset_store=store, start_directory=str(tmp_path))
    assert dialog.add_inputs([first, second, first, ignored]) == 2
    assert len(dialog.inputs()) == 2

    dialog.set_steps([BatchStep("grayscale"), BatchStep("resize_max", max_size=16)])
    assert len(dialog.steps()) == 2
    dialog.step_list.setCurrentRow(0)
    dialog._move_step(1)
    assert dialog.steps()[0].kind == "resize_max"
    dialog.step_list.setCurrentRow(0)
    dialog._on_remove_step()
    assert [step.kind for step in dialog.steps()] == ["grayscale"]

    dialog.output_dir_edit.setText(str(tmp_path / "out"))
    dialog.run_button.click()
    assert len(dialog.last_results) == 2
    assert all(item.status == "ok" for item in dialog.last_results)
    assert len(list((tmp_path / "out").iterdir())) == 2
    assert "thành công" in dialog.status_label.text()
    dialog.deleteLater()


def test_batch_dialog_action_save_and_load(tmp_path, qapp, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from core.presets import PresetStore
    from ui.dialogs import BatchDialog

    monkeypatch.setattr(
        QInputDialog, "getText", lambda *args, **kwargs: ("Action web", True)
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    store = PresetStore(tmp_path / "presets.sqlite3")
    dialog = BatchDialog(preset_store=store)
    dialog.set_steps([BatchStep("auto_levels"), BatchStep("gaussian_blur", radius=1.5)])
    dialog._on_save_action()
    saved = store.load_action("Action web")
    assert saved is not None and len(saved.steps) == 2

    dialog.set_steps([])
    assert dialog.apply_action("Action web")
    assert [step.kind for step in dialog.steps()] == [
        "auto_levels",
        "gaussian_blur",
    ]
    dialog._on_delete_action()
    assert store.load_action("Action web") is None
    dialog.deleteLater()


def test_batch_dialog_warns_without_inputs(tmp_path, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from ui.dialogs import BatchDialog

    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text, *args, **kwargs: warnings.append(title),
    )
    dialog = BatchDialog()
    dialog.set_steps([BatchStep("invert")])
    dialog.output_dir_edit.setText(str(tmp_path))
    dialog._on_run()
    assert warnings == ["Chưa có ảnh"]

    dialog.add_inputs([])
    dialog.set_steps([])
    source = tmp_path / "a.png"
    _source_file(source)
    dialog.add_inputs([source])
    dialog._on_run()
    assert warnings == ["Chưa có ảnh", "Chưa có bước"]
    dialog.deleteLater()
