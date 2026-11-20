"""Định dạng dự án gốc .mps.

Cấu trúc file ZIP:
    manifest.json          — thông tin tài liệu và danh sách layer
    layers/<layer_id>.png  — dữ liệu RGBA của từng layer

Bản ghi manifest có version riêng để nâng cấp định dạng về sau mà vẫn phát
hiện được file của phiên bản mới hơn.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from config.settings import APP_VERSION, PROJECT_EXTENSION
from core.adjustment_layer import AdjustmentProperties
from core.document import Document
from core.fill_layer import FillProperties
from core.layer import BLEND_MODE_IDS, LAYER_COLOR_IDS, Layer, LayerKind
from core.layer_style import LayerStyle
from core.shape_layer import ShapeProperties
from core.smart_object import SmartObjectProperties, validate_source
from core.text_layer import TextProperties

FORMAT_ID = "myphoto-project"
FORMAT_VERSION = 10

_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_LAYER_BYTES = 512 * 1024 * 1024


class ProjectFormatError(Exception):
    pass


def ensure_project_extension(path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != PROJECT_EXTENSION:
        target = target.with_suffix(PROJECT_EXTENSION)
    return target


def save_project(document: Document, path: str | Path) -> Path:
    target = ensure_project_extension(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")

    manifest: dict[str, Any] = {
        "format": FORMAT_ID,
        "version": FORMAT_VERSION,
        "application": "My Photo Studio",
        "application_version": APP_VERSION,
        "document": {
            "width": document.width,
            "height": document.height,
            "dpi": document.dpi,
            "name": document.name,
            "active_layer": document.active_layer.id if document.active_layer else None,
        },
        "layers": [],
    }

    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for layer in document.layers:
                entry_name = f"layers/{layer.id}.png"
                mask_name = f"masks/{layer.id}.png" if layer.mask is not None else None
                source_name = (
                    f"sources/{layer.id}.png"
                    if layer.kind == LayerKind.SMART and layer.smart_source is not None
                    else None
                )
                entry: dict[str, Any] = {
                    "id": layer.id,
                    "name": layer.name,
                    "kind": layer.kind,
                    "visible": layer.visible,
                    "locked": bool(layer.locked),
                    "clipping": bool(layer.clipping),
                    "color_label": layer.color_label,
                    "opacity": layer.opacity,
                    "blend_mode": layer.blend_mode,
                    "offset_x": layer.offset_x,
                    "offset_y": layer.offset_y,
                    "width": layer.width,
                    "height": layer.height,
                    "group_id": layer.group_id,
                    "file": entry_name,
                    "mask_file": mask_name,
                    "mask_enabled": bool(layer.mask_enabled),
                    "source_file": source_name,
                }
                if layer.kind == LayerKind.TEXT and layer.text is not None:
                    entry["text"] = layer.text.to_dict()
                elif layer.kind == LayerKind.SHAPE and layer.shape is not None:
                    entry["shape"] = layer.shape.to_dict()
                elif layer.kind == LayerKind.ADJUSTMENT and layer.adjustment is not None:
                    entry["adjustment"] = layer.adjustment.to_dict()
                elif layer.kind == LayerKind.FILL and layer.fill_props is not None:
                    entry["fill"] = layer.fill_props.to_dict()
                elif layer.kind == LayerKind.SMART and layer.smart_props is not None:
                    entry["smart"] = layer.smart_props.to_dict()
                if layer.style is not None:
                    entry["style"] = layer.style.to_dict()
                manifest["layers"].append(entry)
                buffer = io.BytesIO()
                image = Image.fromarray(np.ascontiguousarray(layer.pixels), "RGBA")
                image.save(buffer, format="PNG", compress_level=6)
                archive.writestr(entry_name, buffer.getvalue())
                if source_name is not None:
                    source_buffer = io.BytesIO()
                    source_image = Image.fromarray(
                        np.ascontiguousarray(layer.smart_source), "RGBA"
                    )
                    source_image.save(source_buffer, format="PNG", compress_level=6)
                    archive.writestr(source_name, source_buffer.getvalue())
                if mask_name is not None:
                    mask_buffer = io.BytesIO()
                    mask_image = Image.fromarray(
                        np.ascontiguousarray(layer.mask), "L"
                    )
                    mask_image.save(mask_buffer, format="PNG", compress_level=6)
                    archive.writestr(mask_name, mask_buffer.getvalue())
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        os.replace(temporary, target)
    except OSError as exc:
        raise ProjectFormatError(f"Không thể lưu dự án.\nChi tiết: {exc}") from exc
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass

    document.mark_saved(str(target))
    return target


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        info = archive.getinfo("manifest.json")
    except KeyError as exc:
        raise ProjectFormatError("File dự án thiếu manifest.json.") from exc
    if info.file_size > _MAX_MANIFEST_BYTES:
        raise ProjectFormatError("Manifest của dự án quá lớn hoặc không hợp lệ.")
    try:
        data = json.loads(archive.read(info).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProjectFormatError("Manifest của dự án bị hỏng.") from exc
    if not isinstance(data, dict):
        raise ProjectFormatError("Manifest của dự án không hợp lệ.")
    return data


def _validate_groups(document: Document) -> None:
    """Kiểm tra quan hệ nhóm: cha phải tồn tại, đúng loại và không tạo vòng lặp."""
    for layer in document.layers:
        if layer.group_id is None:
            continue
        parent = document.layers.get(layer.group_id)
        if parent is None or parent.kind != LayerKind.GROUP:
            raise ProjectFormatError(
                f"Layer '{layer.name}' thuộc một nhóm không hợp lệ."
            )
        visited = {layer.group_id}
        current = parent
        while current.group_id is not None:
            if current.group_id in visited:
                raise ProjectFormatError(
                    "Quan hệ nhóm trong dự án bị vòng lặp."
                )
            visited.add(current.group_id)
            next_parent = document.layers.get(current.group_id)
            if next_parent is None or next_parent.kind != LayerKind.GROUP:
                raise ProjectFormatError(
                    f"Nhóm '{current.name}' có nhóm cha không hợp lệ."
                )
            current = next_parent


def _sanitize_clipping(document: Document) -> None:
    """Bỏ cờ clipping ở layer không còn layer nền phía dưới trong cùng nhóm."""
    group_ids = [
        layer.id for layer in document.layers if layer.kind == LayerKind.GROUP
    ]
    for parent_id in [None, *group_ids]:
        has_base = False
        for layer in document.layers.children_of(parent_id):
            if layer.clipping and not has_base:
                layer.clipping = False
            if not layer.clipping:
                has_base = True


def _load_smart_source(
    archive: zipfile.ZipFile,
    entry: dict[str, Any],
    properties: SmartObjectProperties | None,
) -> np.ndarray:
    if properties is None:
        raise ProjectFormatError("Smart object thiếu thuộc tính biến đổi.")
    source_file = entry.get("source_file")
    if (
        not isinstance(source_file, str)
        or not source_file.startswith("sources/")
        or ".." in source_file
    ):
        raise ProjectFormatError("Đường dẫn ảnh nguồn smart object không hợp lệ.")
    try:
        info = archive.getinfo(source_file)
    except KeyError as exc:
        raise ProjectFormatError("Dự án thiếu ảnh nguồn của smart object.") from exc
    if info.file_size > _MAX_LAYER_BYTES:
        raise ProjectFormatError("Ảnh nguồn smart object vượt giới hạn an toàn.")
    try:
        with Image.open(io.BytesIO(archive.read(info))) as image:
            image.load()
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            source = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProjectFormatError("Ảnh nguồn smart object bị hỏng.") from exc
    try:
        source = validate_source(source)
    except ValueError as exc:
        raise ProjectFormatError(str(exc)) from exc
    height, width = source.shape[:2]
    if (width, height) != (
        properties.source_width,
        properties.source_height,
    ):
        raise ProjectFormatError(
            "Kích thước ảnh nguồn smart object không khớp thuộc tính."
        )
    return source


def load_project(path: str | Path) -> Document:
    source = Path(path)
    if not source.exists():
        raise ProjectFormatError(f"Không tìm thấy file dự án:\n{source}")

    try:
        with zipfile.ZipFile(source) as archive:
            manifest = _read_manifest(archive)
            if manifest.get("format") != FORMAT_ID:
                raise ProjectFormatError("File không phải dự án My Photo Studio.")
            try:
                version = int(manifest.get("version", 0))
            except (TypeError, ValueError) as exc:
                raise ProjectFormatError("Phiên bản định dạng dự án không hợp lệ.") from exc
            if version > FORMAT_VERSION:
                raise ProjectFormatError(
                    "Dự án được tạo bởi phiên bản My Photo Studio mới hơn. "
                    "Hãy cập nhật ứng dụng để mở file này."
                )

            document_info = manifest.get("document")
            layer_entries = manifest.get("layers")
            if not isinstance(document_info, dict) or not isinstance(layer_entries, list):
                raise ProjectFormatError("Cấu trúc dự án không hợp lệ.")

            try:
                width = int(document_info["width"])
                height = int(document_info["height"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProjectFormatError("Kích thước tài liệu không hợp lệ.") from exc
            dpi = float(document_info.get("dpi", 72.0) or 72.0)
            document = Document(
                width,
                height,
                dpi=dpi,
                name=str(document_info.get("name") or source.stem),
            )

            for entry in layer_entries:
                if not isinstance(entry, dict):
                    raise ProjectFormatError("Thông tin layer không hợp lệ.")
                layer_kind = str(entry.get("kind", "pixel"))
                if layer_kind not in (
                    LayerKind.PIXEL,
                    LayerKind.TEXT,
                    LayerKind.SHAPE,
                    LayerKind.ADJUSTMENT,
                    LayerKind.GROUP,
                    LayerKind.FILL,
                    LayerKind.SMART,
                ):
                    raise ProjectFormatError(
                        f"Layer '{entry.get('name', '?')}' thuộc loại chưa được hỗ trợ "
                        f"trong phiên bản này."
                    )
                text_properties: TextProperties | None = None
                if layer_kind == LayerKind.TEXT:
                    try:
                        text_properties = TextProperties.from_dict(entry.get("text"))
                    except ValueError as exc:
                        raise ProjectFormatError(
                            f"Dữ liệu văn bản của layer '{entry.get('name', '?')}' "
                            f"không hợp lệ."
                        ) from exc
                shape_properties: ShapeProperties | None = None
                if layer_kind == LayerKind.SHAPE:
                    try:
                        shape_properties = ShapeProperties.from_dict(entry.get("shape"))
                    except ValueError as exc:
                        raise ProjectFormatError(
                            f"Dữ liệu hình khối của layer '{entry.get('name', '?')}' "
                            f"không hợp lệ."
                        ) from exc
                adjustment_properties: AdjustmentProperties | None = None
                if layer_kind == LayerKind.ADJUSTMENT:
                    try:
                        adjustment_properties = AdjustmentProperties.from_dict(
                            entry.get("adjustment")
                        )
                    except ValueError as exc:
                        raise ProjectFormatError(
                            f"Dữ liệu điều chỉnh của layer '{entry.get('name', '?')}' "
                            f"không hợp lệ."
                        ) from exc
                fill_properties: FillProperties | None = None
                if layer_kind == LayerKind.FILL:
                    try:
                        fill_properties = FillProperties.from_dict(entry.get("fill"))
                    except ValueError as exc:
                        raise ProjectFormatError(
                            f"Dữ liệu màu tô của layer '{entry.get('name', '?')}' "
                            f"không hợp lệ."
                        ) from exc
                smart_properties: SmartObjectProperties | None = None
                if layer_kind == LayerKind.SMART:
                    try:
                        smart_properties = SmartObjectProperties.from_dict(
                            entry.get("smart")
                        )
                    except ValueError as exc:
                        raise ProjectFormatError(
                            f"Dữ liệu smart object của layer '{entry.get('name', '?')}' "
                            f"không hợp lệ."
                        ) from exc
                entry_file = str(entry.get("file", ""))
                if not entry_file.startswith("layers/") or ".." in entry_file:
                    raise ProjectFormatError("Đường dẫn dữ liệu layer không hợp lệ.")
                try:
                    info = archive.getinfo(entry_file)
                except KeyError as exc:
                    raise ProjectFormatError("Dự án thiếu dữ liệu của một layer.") from exc
                if info.file_size > _MAX_LAYER_BYTES:
                    raise ProjectFormatError("Dữ liệu layer vượt giới hạn an toàn.")

                try:
                    with Image.open(io.BytesIO(archive.read(info))) as image:
                        image.load()
                        if image.mode != "RGBA":
                            image = image.convert("RGBA")
                        pixels = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
                except (UnidentifiedImageError, OSError, ValueError) as exc:
                    raise ProjectFormatError("Dữ liệu pixel của layer bị hỏng.") from exc

                layer_height, layer_width = pixels.shape[:2]
                layer = Layer(
                    layer_width,
                    layer_height,
                    str(entry.get("name") or "Layer"),
                    layer_id=str(entry.get("id") or "") or None,
                )
                if shape_properties is not None and (
                    shape_properties.width != layer_width
                    or shape_properties.height != layer_height
                ):
                    raise ProjectFormatError(
                        f"Kích thước hình khối của layer '{layer.name}' "
                        f"không khớp với dữ liệu pixel."
                    )
                layer.pixels = pixels
                layer.kind = layer_kind
                layer.text = text_properties
                layer.shape = shape_properties
                layer.adjustment = adjustment_properties
                layer.fill_props = fill_properties
                layer.smart_props = smart_properties
                if "style" in entry:
                    try:
                        layer.style = LayerStyle.from_dict(entry.get("style"))
                    except ValueError as exc:
                        raise ProjectFormatError(
                            f"Dữ liệu layer style của layer '{layer.name}' "
                            f"không hợp lệ."
                        ) from exc
                if layer_kind == LayerKind.SMART:
                    smart_source = _load_smart_source(
                        archive, entry, smart_properties
                    )
                    layer.smart_source = smart_source
                layer.offset_x = int(entry.get("offset_x", 0))
                layer.offset_y = int(entry.get("offset_y", 0))
                group_id = entry.get("group_id")
                if group_id is not None and not isinstance(group_id, str):
                    raise ProjectFormatError(
                        f"Thông tin nhóm của layer '{layer.name}' không hợp lệ."
                    )
                layer.group_id = group_id or None
                layer.visible = bool(entry.get("visible", True))
                layer.locked = bool(entry.get("locked", False))
                layer.clipping = bool(entry.get("clipping", False))
                color_label = str(entry.get("color_label", "none"))
                layer.color_label = (
                    color_label if color_label in LAYER_COLOR_IDS else "none"
                )
                try:
                    layer.opacity = max(0.0, min(1.0, float(entry.get("opacity", 1.0))))
                except (TypeError, ValueError):
                    layer.opacity = 1.0
                blend_mode = str(entry.get("blend_mode", "normal"))
                layer.blend_mode = blend_mode if blend_mode in BLEND_MODE_IDS else "normal"

                mask_file = entry.get("mask_file")
                if mask_file:
                    if (
                        not isinstance(mask_file, str)
                        or not mask_file.startswith("masks/")
                        or ".." in mask_file
                    ):
                        raise ProjectFormatError("Đường dẫn layer mask không hợp lệ.")
                    try:
                        mask_info = archive.getinfo(mask_file)
                    except KeyError as exc:
                        raise ProjectFormatError(
                            "Dự án thiếu dữ liệu layer mask."
                        ) from exc
                    if mask_info.file_size > _MAX_LAYER_BYTES:
                        raise ProjectFormatError("Dữ liệu layer mask vượt giới hạn an toàn.")
                    try:
                        with Image.open(io.BytesIO(archive.read(mask_info))) as mask_image:
                            mask_image.load()
                            if mask_image.mode != "L":
                                mask_image = mask_image.convert("L")
                            mask = np.array(mask_image, dtype=np.uint8, copy=True)
                    except (UnidentifiedImageError, OSError, ValueError) as exc:
                        raise ProjectFormatError(
                            "Dữ liệu layer mask bị hỏng."
                        ) from exc
                    if layer_kind in LayerKind.CANVAS_MASK_KINDS:
                        expected_size = (document.height, document.width)
                    else:
                        expected_size = (layer.height, layer.width)
                    if mask.shape != expected_size:
                        raise ProjectFormatError(
                            "Kích thước layer mask không khớp với layer."
                        )
                    layer.mask = np.ascontiguousarray(mask)
                    layer.mask_enabled = bool(entry.get("mask_enabled", True))

                document.add_layer(
                    layer=layer,
                    index=len(document.layers),
                    select=False,
                    record=False,
                )

            _validate_groups(document)
            _sanitize_clipping(document)

            active_layer_id = document_info.get("active_layer")
            active = document.layers.get(str(active_layer_id)) if active_layer_id else None
            document.set_active_layer(active)
    except zipfile.BadZipFile as exc:
        raise ProjectFormatError("File dự án bị hỏng hoặc không phải định dạng ZIP.") from exc

    document.mark_saved(str(source))
    return document
