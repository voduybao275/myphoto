"""Xuất ảnh composite ra các định dạng phổ thông."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

SUPPORTED_EXPORT_EXTENSIONS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".bmp": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".webp": "WEBP",
}


class ExportError(Exception):
    pass


def _flatten_on_white(image: Image.Image) -> Image.Image:
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.getchannel("A"))
    return background


def export_image(path: str | Path, rgba: np.ndarray, quality: int = 92) -> Path:
    """Ghi mảng RGBA ra file theo phần mở rộng. Ghi qua file tạm rồi thay thế."""
    target = Path(path)
    extension = target.suffix.lower()
    image_format = SUPPORTED_EXPORT_EXTENSIONS.get(extension)
    if image_format is None:
        raise ExportError(
            "Định dạng xuất không hỗ trợ. Hãy chọn PNG, JPEG, BMP, TIFF hoặc WebP."
        )
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ExportError("Dữ liệu ảnh xuất không hợp lệ.")

    image = Image.fromarray(np.ascontiguousarray(rgba), "RGBA")
    save_options: dict[str, object] = {}
    if image_format == "JPEG":
        image = _flatten_on_white(image)
        save_options = {"quality": int(quality), "optimize": True, "progressive": True}
    elif image_format == "BMP":
        # BMP không phổ quát hỗ trợ alpha: làm phẳng trên nền trắng cho an toàn.
        image = _flatten_on_white(image)
    elif image_format == "PNG":
        save_options = {"compress_level": 6}
    elif image_format == "TIFF":
        save_options = {"compression": "tiff_lzw"}
    elif image_format == "WEBP":
        save_options = {"quality": int(quality), "method": 4}

    temporary = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(temporary, format=image_format, **save_options)
        os.replace(temporary, target)
    except OSError as exc:
        raise ExportError(f"Không thể ghi file xuất.\nChi tiết: {exc}") from exc
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
    return target
