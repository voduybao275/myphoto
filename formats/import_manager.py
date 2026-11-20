"""Đọc file ảnh thành Document (Pillow).

Hỗ trợ PNG, JPEG, BMP, TIFF, GIF (khung đầu) và WebP. Mọi ảnh được chuẩn hoá
sang RGBA 8-bit; EXIF orientation được áp dụng khi mở.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from core.document import Document
from core.layer import Layer

# Cùng giới hạn với Document; Pillow cũng dùng ngưỡng này để chống ảnh quá lớn.
Image.MAX_IMAGE_PIXELS = Document.MAX_PIXELS

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".webp",
}


class ImageImportError(Exception):
    """Lỗi khi đọc file ảnh với thông điệp thân thiện."""


def _to_8bit_gray(image: Image.Image) -> Image.Image:
    """Co ảnh xám sâu bit (I;16*, I, F) về L 8-bit theo dải thực tế.

    Pillow convert("RGBA") trực tiếp từ các mode này chỉ cắt giá trị >255
    nên ảnh gần như trắng xoá.
    """
    data = np.asarray(image, dtype=np.float64)
    if image.mode == "F":
        finite = data[np.isfinite(data)]
        top = float(finite.max()) if finite.size else 1.0
        scale = 255.0 if top <= 1.0 else 255.0 / max(top, 1e-12)
        data = np.nan_to_num(data) * scale
    elif image.mode == "I":
        top = float(data.max()) if data.size else 0.0
        if top > 65535:
            data = data / (2**32 - 1) * 255.0
        elif top > 255:
            data = data / 65535.0 * 255.0
    else:  # I;16, I;16B, I;16L, I;16N
        data = data / 65535.0 * 255.0
    return Image.fromarray(np.clip(np.rint(data), 0, 255).astype(np.uint8), "L")


def _read_rgba(image: Image.Image) -> np.ndarray:
    if image.mode in ("I", "F") or image.mode.startswith("I;16"):
        image = _to_8bit_gray(image)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))


def load_image_rgba(path: str | Path) -> np.ndarray:
    """Đọc ảnh thành mảng RGBA uint8 (dùng làm nội dung smart object)."""
    file_path = Path(path)
    if not file_path.exists():
        raise ImageImportError(f"Không tìm thấy file:\n{file_path}")
    if file_path.stat().st_size == 0:
        raise ImageImportError("File rỗng, không thể mở.")
    try:
        with Image.open(file_path) as opened:
            opened.load()
            rgba = _read_rgba(ImageOps.exif_transpose(opened))
    except Image.DecompressionBombError as exc:
        raise ImageImportError("Ảnh vượt quá giới hạn kích thước an toàn.") from exc
    except UnidentifiedImageError as exc:
        raise ImageImportError("Định dạng ảnh không được hỗ trợ hoặc file bị hỏng.") from exc
    except OSError as exc:
        raise ImageImportError(f"Không thể đọc file ảnh.\nChi tiết: {exc}") from exc
    return rgba


def load_image_document(path: str | Path) -> Document:
    file_path = Path(path)
    if not file_path.exists():
        raise ImageImportError(f"Không tìm thấy file:\n{file_path}")
    if file_path.stat().st_size == 0:
        raise ImageImportError("File rỗng, không thể mở.")

    try:
        with Image.open(file_path) as opened:
            opened.load()
            dpi_info = opened.info.get("dpi", (72.0, 72.0))
            dpi = float(dpi_info[0]) if isinstance(dpi_info, (tuple, list)) and dpi_info else 72.0
            transposed = ImageOps.exif_transpose(opened)
            rgba = _read_rgba(transposed)
    except Image.DecompressionBombError as exc:
        raise ImageImportError("Ảnh vượt quá giới hạn kích thước an toàn.") from exc
    except UnidentifiedImageError as exc:
        raise ImageImportError("Định dạng ảnh không được hỗ trợ hoặc file bị hỏng.") from exc
    except OSError as exc:
        raise ImageImportError(f"Không thể đọc file ảnh.\nChi tiết: {exc}") from exc

    height, width = rgba.shape[:2]
    if width * height > Document.MAX_PIXELS:
        raise ImageImportError("Ảnh quá lớn (vượt 400 megapixel).")

    document = Document(width, height, dpi=dpi, name=file_path.stem)
    layer = Layer(width, height, name="Background")
    layer.set_pixels(rgba)
    document.add_layer(layer=layer, index=0, select=True, record=False)
    document.mark_clean()
    return document
