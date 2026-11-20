"""Kiểm thử lưu/đọc định dạng dự án .mps và bảo vệ file lỗi."""

from __future__ import annotations

import json
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from core.document import Document
from core.shape_layer import ShapeProperties
from core.text_layer import TextProperties, TextRun
from formats.native_project import (
    ProjectFormatError,
    ensure_project_extension,
    load_project,
    save_project,
)


def build_document():
    document = Document(12, 9, dpi=144, name="Dự án thử")
    background = document.add_layer(name="Background", color=(250, 240, 230, 255), record=False)
    background.offset_x = 1
    background.offset_y = 2

    accent = document.add_layer(name="Accent", color=(10, 200, 30, 255), record=False)
    accent.offset_x = 4
    accent.offset_y = 3
    accent.opacity = 0.65
    accent.blend_mode = "multiply"
    accent.color_label = "blue"
    accent.visible = True
    mask = np.zeros((accent.height, accent.width), dtype=np.uint8)
    mask[2:6, 2:8] = 255
    accent.set_mask(mask)

    hidden = document.add_layer(name="Hidden", color=(0, 0, 255, 255), record=False)
    hidden.visible = False
    hidden.locked = True
    document.set_active_layer(accent)
    document.mark_clean()
    return document


def test_ensure_project_extension(tmp_path):
    assert ensure_project_extension(tmp_path / "a") == tmp_path / "a.mps"
    assert ensure_project_extension(tmp_path / "a.mps") == tmp_path / "a.mps"
    assert ensure_project_extension(tmp_path / "a.PNG") == tmp_path / "a.mps"


def test_roundtrip_preserves_layers_and_properties(tmp_path):
    document = build_document()
    target = save_project(document, tmp_path / "du-an")
    assert target.suffix == ".mps"
    assert target.exists()
    assert Path(document.file_path) == target
    assert not document.modified

    loaded = load_project(target)
    assert (loaded.width, loaded.height) == (12, 9)
    assert loaded.dpi == 144
    assert loaded.name == "Dự án thử"
    assert len(loaded.layers) == 3
    assert [layer.name for layer in loaded.layers] == ["Background", "Accent", "Hidden"]

    background, accent, hidden = loaded.layers
    assert (background.offset_x, background.offset_y) == (1, 2)
    assert (accent.offset_x, accent.offset_y) == (4, 3)
    assert accent.opacity == pytest.approx(0.65, abs=1e-6)
    assert accent.blend_mode == "multiply"
    assert accent.color_label == "blue"
    assert background.color_label == "none"
    assert accent.mask is not None
    expected_mask = np.zeros((9, 12), dtype=np.uint8)
    expected_mask[2:6, 2:8] = 255
    assert np.array_equal(accent.mask, expected_mask)
    assert accent.mask_enabled
    assert not hidden.visible
    assert hidden.locked
    assert not accent.locked
    assert loaded.active_layer is not None
    assert loaded.active_layer.name == "Accent"
    assert np.array_equal(loaded.get_composite().array, document.get_composite().array)


def test_saved_archive_contains_manifest(tmp_path):
    document = build_document()
    target = save_project(document, tmp_path / "du-an.mps")
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["format"] == "myphoto-project"
    assert manifest["version"] == 9
    assert len(manifest["layers"]) == 3
    entries = {entry["name"]: entry for entry in manifest["layers"]}
    assert entries["Accent"]["color_label"] == "blue"
    for entry in manifest["layers"]:
        assert entry["file"].startswith("layers/")
        assert entry["file"] in names
        if entry["mask_file"]:
            assert entry["mask_file"].startswith("masks/")
            assert entry["mask_file"] in names


def test_version_too_new_is_rejected(tmp_path):
    target = tmp_path / "future.mps"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "myphoto-project",
                    "version": 999,
                    "document": {"width": 4, "height": 4},
                    "layers": [],
                }
            ),
        )
    with pytest.raises(ProjectFormatError, match="mới hơn"):
        load_project(target)


def test_wrong_format_is_rejected(tmp_path):
    target = tmp_path / "other.mps"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "photoshop"}))
    with pytest.raises(ProjectFormatError):
        load_project(target)


def test_corrupt_zip_is_rejected(tmp_path):
    target = tmp_path / "broken.mps"
    target.write_bytes(b"this is not a zip file")
    with pytest.raises(ProjectFormatError, match="ZIP"):
        load_project(target)


def test_unsafe_layer_path_is_rejected(tmp_path):
    target = tmp_path / "unsafe.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 1,
        "document": {"width": 4, "height": 4, "name": "x"},
        "layers": [
            {"id": "a", "name": "A", "file": "layers/../../evil.png", "width": 4, "height": 4}
        ],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/../../evil.png", b"x")
    with pytest.raises(ProjectFormatError, match="Đường dẫn"):
        load_project(target)


def test_missing_layer_file_is_rejected(tmp_path):
    target = tmp_path / "missing.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 1,
        "document": {"width": 4, "height": 4, "name": "x"},
        "layers": [{"id": "a", "name": "A", "file": "layers/a.png", "width": 4, "height": 4}],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(ProjectFormatError):
        load_project(target)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ProjectFormatError, match="Không tìm thấy"):
        load_project(tmp_path / "khong-ton-tai.mps")


def _png_bytes(array: np.ndarray, mode: str = "RGBA") -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array, mode).save(buffer, format="PNG")
    return buffer.getvalue()


def test_version_1_project_without_masks_still_loads(tmp_path):
    target = tmp_path / "v1.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 1,
        "document": {"width": 4, "height": 4, "name": "Cũ"},
        "layers": [
            {"id": "a", "name": "A", "file": "layers/a.png", "width": 4, "height": 4}
        ],
    }
    pixels = np.full((4, 4, 4), 128, dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    loaded = load_project(target)
    assert len(loaded.layers) == 1
    assert loaded.layers[0].mask is None
    assert loaded.layers[0].kind == "pixel"
    assert loaded.layers[0].text is None


def test_mask_size_mismatch_is_rejected(tmp_path):
    target = tmp_path / "bad-mask.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 2,
        "document": {"width": 4, "height": 4, "name": "Lỗi"},
        "layers": [
            {
                "id": "a",
                "name": "A",
                "file": "layers/a.png",
                "mask_file": "masks/a.png",
                "width": 4,
                "height": 4,
            }
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
        archive.writestr("masks/a.png", _png_bytes(mask, "L"))
    with pytest.raises(ProjectFormatError, match="mask"):
        load_project(target)


def test_missing_mask_file_is_rejected(tmp_path):
    target = tmp_path / "missing-mask.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 2,
        "document": {"width": 4, "height": 4, "name": "Lỗi"},
        "layers": [
            {
                "id": "a",
                "name": "A",
                "file": "layers/a.png",
                "mask_file": "masks/a.png",
                "width": 4,
                "height": 4,
            }
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    with pytest.raises(ProjectFormatError, match="mask"):
        load_project(target)


def test_text_layer_roundtrip(tmp_path):
    document = Document(200, 120, name="Dự án chữ")
    properties = TextProperties(
        "Xin chào",
        font_family="Arial",
        font_size=28,
        color=(255, 210, 90, 255),
        bold=True,
        alignment="center",
        line_spacing=1.6,
        letter_spacing=3,
    )
    layer = document.add_text_layer(properties, x=10, y=12, record=False)
    assert layer.has_pixels()
    document.mark_clean()

    target = save_project(document, tmp_path / "van-ban.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["version"] == 9
    entry = manifest["layers"][-1]
    assert entry["kind"] == "text"
    assert entry["text"] == properties.to_dict()

    loaded = load_project(target)
    text_layer = loaded.layers[-1]
    assert text_layer.kind == "text"
    assert text_layer.text == properties
    assert (text_layer.offset_x, text_layer.offset_y) == (10, 12)
    assert np.array_equal(text_layer.pixels, layer.pixels)
    assert np.array_equal(loaded.get_composite().array, document.get_composite().array)
    assert loaded.active_layer is text_layer


def test_rich_text_runs_roundtrip(tmp_path):
    document = Document(240, 140, name="Chữ nhiều kiểu")
    properties = TextProperties(
        runs=(
            TextRun("Đậm ", font_family="Arial", font_size=32, color=(255, 80, 40, 255), bold=True),
            TextRun("nghiêng", font_family="Arial", font_size=22, color=(40, 120, 255, 255), italic=True),
        ),
        alignment="center",
        line_spacing=1.4,
        letter_spacing=2,
    )
    layer = document.add_text_layer(properties, x=6, y=8, record=False)
    document.mark_clean()

    target = save_project(document, tmp_path / "chu-nhieu-kieu.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    entry = manifest["layers"][-1]
    assert [run["text"] for run in entry["text"]["runs"]] == ["Đậm ", "nghiêng"]
    assert entry["text"]["runs"][1]["italic"] is True

    loaded = load_project(target)
    text_layer = loaded.layers[-1]
    assert text_layer.text == properties
    assert text_layer.text.text == "Đậm nghiêng"
    assert [run.font_size for run in text_layer.text.runs] == [32, 22]
    assert np.array_equal(text_layer.pixels, layer.pixels)


def test_warped_text_roundtrip(tmp_path):
    document = Document(320, 180, name="Chữ uốn")
    properties = TextProperties(
        "Uốn chữ", font_size=30, alignment="center", warp_style="wave", warp_bend=-55
    )
    layer = document.add_text_layer(properties, x=4, y=5, record=False)
    document.mark_clean()

    target = save_project(document, tmp_path / "chu-uon.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    payload = manifest["layers"][-1]["text"]
    assert payload["warp_style"] == "wave"
    assert payload["warp_bend"] == -55

    loaded = load_project(target)
    restored = loaded.layers[-1]
    assert restored.text == properties
    assert restored.text.warp_style == "wave"
    assert restored.text.warp_bend == -55
    assert np.array_equal(restored.pixels, layer.pixels)


def test_path_text_and_kerning_roundtrip(tmp_path):
    document = Document(360, 200, name="Chữ trên đường dẫn")
    properties = TextProperties(
        "VÒNG CHỮ",
        font_size=34,
        alignment="center",
        path_style="circle",
        path_bend=65,
        kerning_pairs=(("VÒ", -3), ("NG", -2)),
    )
    layer = document.add_text_layer(properties, x=8, y=9, record=False)
    document.mark_clean()

    target = save_project(document, tmp_path / "chu-duong-dan.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    payload = manifest["layers"][-1]["text"]
    assert payload["path_style"] == "circle"
    assert payload["path_bend"] == 65
    assert payload["kerning_pairs"] == [["VÒ", -3], ["NG", -2]]

    loaded = load_project(target)
    restored = loaded.layers[-1]
    assert restored.text == properties
    assert restored.text.path_style == "circle"
    assert restored.text.path_bend == 65
    assert restored.text.kerning_pairs == (("VÒ", -3), ("NG", -2))
    assert np.array_equal(restored.pixels, layer.pixels)


def test_legacy_text_without_runs_loads_as_single_run(tmp_path):
    document = Document(120, 80, name="Chữ cũ")
    layer = document.add_text_layer(
        TextProperties("Cũ", font_size=24, bold=True), record=False
    )
    document.mark_clean()

    target = save_project(document, tmp_path / "chu-cu.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    payload = manifest["layers"][-1]["text"]
    payload.pop("runs", None)
    manifest["layers"][-1]["text"] = payload
    entry_file = manifest["layers"][-1]["file"]
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        image = Image.fromarray(np.ascontiguousarray(layer.pixels), "RGBA")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        archive.writestr(entry_file, buffer.getvalue())

    loaded = load_project(target)
    restored = loaded.layers[-1]
    assert restored.kind == "text"
    assert len(restored.text.runs) == 1
    assert restored.text.runs[0].text == "Cũ"
    assert restored.text.runs[0].bold is True


def test_rasterized_text_saved_as_pixel(tmp_path):
    document = Document(100, 80)
    layer = document.add_text_layer(
        TextProperties("A", font_size=16), record=False
    )
    assert document.rasterize_text_layer(layer, record=False)
    target = save_project(document, tmp_path / "raster.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    entry = manifest["layers"][0]
    assert entry["kind"] == "pixel"
    assert "text" not in entry
    loaded = load_project(target)
    assert loaded.layers[0].kind == "pixel"
    assert loaded.layers[0].text is None


def test_text_layer_without_text_data_is_rejected(tmp_path):
    target = tmp_path / "thieu-chu.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 3,
        "document": {"width": 4, "height": 4, "name": "Lỗi"},
        "layers": [
            {"id": "a", "name": "A", "kind": "text", "file": "layers/a.png"}
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    with pytest.raises(ProjectFormatError, match="văn bản"):
        load_project(target)


def test_invalid_text_metadata_is_rejected(tmp_path):
    target = tmp_path / "chu-loi.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 3,
        "document": {"width": 4, "height": 4, "name": "Lỗi"},
        "layers": [
            {
                "id": "a",
                "name": "A",
                "kind": "text",
                "text": {"text": "", "font_size": 24},
                "file": "layers/a.png",
            }
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    with pytest.raises(ProjectFormatError, match="văn bản"):
        load_project(target)


def test_shape_layer_roundtrip(tmp_path):
    document = Document(160, 120, name="Dự án hình khối")
    properties = ShapeProperties(
        kind="rounded_rectangle",
        width=80,
        height=50,
        fill_color=(20, 140, 220, 230),
        stroke_color=(255, 255, 255, 255),
        stroke_width=4,
        corner_radius=12.0,
    )
    layer = document.add_shape_layer(properties, x=9, y=11, record=False)
    assert layer.kind == "shape"
    assert layer.shape == properties
    document.mark_clean()

    target = save_project(document, tmp_path / "hinh-khoi.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["version"] == 9
    entry = manifest["layers"][-1]
    assert entry["kind"] == "shape"
    assert entry["shape"] == properties.to_dict()

    loaded = load_project(target)
    shape_layer = loaded.layers[-1]
    assert shape_layer.kind == "shape"
    assert shape_layer.shape == properties
    assert (shape_layer.offset_x, shape_layer.offset_y) == (9, 11)
    assert np.array_equal(shape_layer.pixels, layer.pixels)
    assert np.array_equal(loaded.get_composite().array, document.get_composite().array)
    assert loaded.active_layer is shape_layer


def test_rasterized_shape_saved_as_pixel(tmp_path):
    document = Document(80, 60)
    layer = document.add_shape_layer(
        ShapeProperties(width=40, height=30), record=False
    )
    assert document.rasterize_shape_layer(layer, record=False)
    target = save_project(document, tmp_path / "raster-shape.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    entry = manifest["layers"][0]
    assert entry["kind"] == "pixel"
    assert "shape" not in entry
    loaded = load_project(target)
    assert loaded.layers[0].kind == "pixel"
    assert loaded.layers[0].shape is None


def test_shape_layer_without_shape_data_is_rejected(tmp_path):
    target = tmp_path / "thieu-hinh.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 4,
        "document": {"width": 4, "height": 4, "name": "Lỗi"},
        "layers": [
            {"id": "a", "name": "A", "kind": "shape", "file": "layers/a.png"}
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    with pytest.raises(ProjectFormatError, match="hình khối"):
        load_project(target)


def test_invalid_shape_metadata_is_rejected(tmp_path):
    target = tmp_path / "hinh-loi.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 4,
        "document": {"width": 4, "height": 4, "name": "Lỗi"},
        "layers": [
            {
                "id": "a",
                "name": "A",
                "kind": "shape",
                "shape": {"kind": "triangle", "width": 4, "height": 4},
                "file": "layers/a.png",
            }
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    with pytest.raises(ProjectFormatError, match="hình khối"):
        load_project(target)


def test_shape_size_mismatch_is_rejected(tmp_path):
    target = tmp_path / "hinh-lech.mps"
    manifest = {
        "format": "myphoto-project",
        "version": 4,
        "document": {"width": 8, "height": 8, "name": "Lỗi"},
        "layers": [
            {
                "id": "a",
                "name": "A",
                "kind": "shape",
                "shape": {"kind": "rectangle", "width": 6, "height": 6},
                "file": "layers/a.png",
            }
        ],
    }
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("layers/a.png", _png_bytes(pixels))
    with pytest.raises(ProjectFormatError, match="Kích thước hình khối"):
        load_project(target)


def test_clipping_mask_roundtrip(tmp_path):
    document = Document(6, 4, name="Clipping")
    base = document.add_layer(name="Base", color=(255, 0, 0, 255), record=False)
    base.pixels[2:, :, 3] = 0
    upper = document.add_layer(name="Clip", color=(0, 0, 255, 255), record=False)
    document.set_layer_clipping(upper, True)
    expected = document.get_composite().array.copy()
    document.mark_clean()

    target = save_project(document, tmp_path / "clipping.mps")
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["version"] == 9
    entries = {entry["name"]: entry for entry in manifest["layers"]}
    assert entries["Clip"]["clipping"] is True
    assert entries["Base"]["clipping"] is False

    loaded = load_project(target)
    by_name = {layer.name: layer for layer in loaded.layers}
    assert by_name["Clip"].clipping
    assert not by_name["Base"].clipping
    assert np.array_equal(loaded.get_composite().array, expected)


def test_clipping_without_base_is_cleared_on_load(tmp_path):
    document = Document(4, 4, name="Clip lỗi")
    layer = document.add_layer(name="Solo", color=(10, 20, 30, 255), record=False)
    layer.clipping = True
    document.mark_clean()

    target = save_project(document, tmp_path / "clipping-solo.mps")
    loaded = load_project(target)
    assert not loaded.layers[0].clipping
    assert np.all(loaded.get_composite().array[..., 3] == 255)
