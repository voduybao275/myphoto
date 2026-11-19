"""Kiểm thử xuất ảnh PNG/JPEG/BMP/TIFF/WebP."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from formats.export_manager import ExportError, export_image


def sample_rgba(width=6, height=4):
    array = np.zeros((height, width, 4), dtype=np.uint8)
    array[..., 0] = 200
    array[..., 1] = 30
    array[..., 2] = 60
    array[..., 3] = 255
    array[0, 0] = (0, 0, 0, 0)
    return array


def test_export_png_preserves_alpha(tmp_path):
    array = sample_rgba()
    target = export_image(tmp_path / "out.png", array)
    assert target.exists()
    with Image.open(target) as image:
        assert image.mode == "RGBA"
        assert image.size == (6, 4)
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((1, 1)) == (200, 30, 60, 255)


@pytest.mark.parametrize("extension", [".jpg", ".bmp"])
def test_export_flattens_on_white(tmp_path, extension):
    transparent = np.zeros((8, 8, 4), dtype=np.uint8)
    target = export_image(tmp_path / f"out{extension}", transparent)
    with Image.open(target) as image:
        assert image.mode == "RGB"
        pixel = image.getpixel((4, 4))
        assert all(channel >= 250 for channel in pixel)


def test_export_tiff_and_webp(tmp_path):
    array = sample_rgba()
    for extension in (".tif", ".webp"):
        target = export_image(tmp_path / f"out{extension}", array)
        with Image.open(target) as image:
            assert image.size == (6, 4)


def test_export_unsupported_extension(tmp_path):
    with pytest.raises(ExportError, match="Định dạng"):
        export_image(tmp_path / "out.xyz", sample_rgba())


def test_export_invalid_array(tmp_path):
    with pytest.raises(ExportError, match="không hợp lệ"):
        export_image(tmp_path / "out.png", np.zeros((4, 4, 3), dtype=np.uint8))


def test_export_does_not_leave_temp_file(tmp_path):
    export_image(tmp_path / "out.png", sample_rgba())
    assert not (tmp_path / "out.png.tmp").exists()
