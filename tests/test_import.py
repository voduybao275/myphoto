"""Kiểm thử nhập ảnh qua Pillow."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from formats.import_manager import ImageImportError, load_image_document


def test_load_png(tmp_path):
    array = np.zeros((7, 11, 4), dtype=np.uint8)
    array[..., 0] = 255
    array[..., 3] = 255
    path = tmp_path / "anh-thu.png"
    Image.fromarray(array, "RGBA").save(path)

    document = load_image_document(path)
    assert (document.width, document.height) == (11, 7)
    assert document.name == "anh-thu"
    assert len(document.layers) == 1
    assert document.layers[0].name == "Background"
    assert not document.modified
    assert np.array_equal(document.get_composite().array, array)


def test_load_jpeg_converts_to_rgba(tmp_path):
    path = tmp_path / "anh.jpg"
    Image.new("RGB", (5, 4), (120, 130, 140)).save(path, quality=95)
    document = load_image_document(path)
    assert document.layers[0].pixels.shape == (4, 5, 4)
    assert np.all(document.layers[0].pixels[..., 3] == 255)


def test_missing_file(tmp_path):
    with pytest.raises(ImageImportError, match="Không tìm thấy"):
        load_image_document(tmp_path / "khong-co.png")


def test_empty_file(tmp_path):
    path = tmp_path / "rong.png"
    path.write_bytes(b"")
    with pytest.raises(ImageImportError, match="rỗng"):
        load_image_document(path)


def test_invalid_image_file(tmp_path):
    path = tmp_path / "hong.png"
    path.write_bytes(b"not an image")
    with pytest.raises(ImageImportError):
        load_image_document(path)
