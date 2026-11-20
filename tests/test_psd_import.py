"""Kiểm thử đọc file PSD: header, RLE/raw/ZIP, mask, nhóm, ảnh hợp nhất và UI."""

from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest

from config.settings import OPEN_FILTER, SettingsStore
from core.layer import LayerKind
from formats.psd_import import PsdImportError, load_psd_document
from ui.main_window import MainWindow


# --------------------------------------------------------------- PSD tổng hợp
def _u16(value: int) -> bytes:
    return struct.pack(">H", value)


def _i16(value: int) -> bytes:
    return struct.pack(">h", value)


def _u32(value: int) -> bytes:
    return struct.pack(">I", value)


def _packbits(data: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        chunk = data[index : index + 128]
        out.append(len(chunk) - 1)
        out += chunk
        index += len(chunk)
    return bytes(out)


def _channel_block(array: np.ndarray, compression: str) -> bytes:
    plane = np.ascontiguousarray(array, dtype=np.uint8)
    if compression == "raw":
        return _u16(0) + plane.tobytes()
    if compression == "zip":
        return _u16(2) + zlib.compress(plane.tobytes())
    rows = [_packbits(plane[row].tobytes()) for row in range(plane.shape[0])]
    table = b"".join(_u16(len(row)) for row in rows)
    return _u16(1) + table + b"".join(rows)


def _tag(key: bytes, data: bytes, padding: int = 1) -> bytes:
    pad = (padding - len(data) % padding) % padding
    return b"8BIM" + key + _u32(len(data)) + data + b"\x00" * pad


def _record(
    name: str,
    rect: tuple[int, int, int, int],
    channels: dict[int, np.ndarray],
    *,
    blend: bytes = b"norm",
    opacity: int = 255,
    clipping: int = 0,
    visible: bool = True,
    locked: bool = False,
    section: int = 0,
    mask: tuple[tuple[int, int, int, int], np.ndarray, int, int] | None = None,
    tags: tuple[tuple[bytes, bytes], ...] = (),
    color_index: int | None = None,
    unicode_name: str | None = None,
    compression: str = "rle",
) -> tuple[bytes, bytes]:
    if mask is not None and -2 not in channels:
        channels = {**channels, -2: mask[1]}
    channel_info = b""
    channel_data = b""
    for channel_id, array in channels.items():
        block = _channel_block(array, compression)
        channel_info += _i16(channel_id) + _u32(len(block))
        channel_data += block

    extra = b""
    if mask is not None:
        mask_rect, _mask_array, mask_flags, mask_default = mask
        extra += _u32(18) + struct.pack(">iiii", *mask_rect) + bytes(
            [mask_default, mask_flags]
        )
    else:
        extra += _u32(0)
    extra += _u32(0)  # blending ranges

    raw_name = name.encode("utf-8")
    extra += bytes([len(raw_name)]) + raw_name
    extra += b"\x00" * ((4 - ((1 + len(raw_name)) % 4)) % 4)

    if section:
        extra += _tag(b"lsct", _u32(section) + b"8BIM" + b"norm")
    if unicode_name is not None:
        encoded = unicode_name.encode("utf-16-be")
        extra += _tag(b"luni", _u32(len(encoded) // 2) + encoded)
    if color_index is not None:
        extra += _tag(b"lclr", _u16(color_index))
    for key, data in tags:
        extra += _tag(key, data)

    flags = 0 if visible else 2
    if locked:
        flags |= 1
    header = (
        struct.pack(">iiii", *rect)
        + _u16(len(channels))
        + channel_info
        + b"8BIM"
        + blend
        + bytes([opacity, clipping, flags, 0])
        + _u32(len(extra))
        + extra
    )
    return header, channel_data


def _image_data(
    composite: np.ndarray, compression: str = "raw", rle_layout: str = "spec"
) -> bytes:
    if compression == "rle":
        channels = []
        for channel in range(composite.shape[2]):
            rows = [
                _packbits(composite[row, :, channel].tobytes())
                for row in range(composite.shape[0])
            ]
            channels.append(rows)
        if rle_layout == "per_channel":
            parts = []
            for rows in channels:
                parts.append(b"".join(_u16(len(row)) for row in rows))
                parts.append(b"".join(rows))
            return _u16(1) + b"".join(parts)
        # Đặc tả PSD: bảng độ dài của mọi dòng thuộc mọi kênh nằm liền nhau.
        tables = b"".join(
            b"".join(_u16(len(row)) for row in rows) for rows in channels
        )
        data = b"".join(b"".join(rows) for rows in channels)
        return _u16(1) + tables + data
    return _u16(0) + b"".join(
        np.ascontiguousarray(composite[..., channel]).tobytes()
        for channel in range(composite.shape[2])
    )


def _dpi_resource(dpi: float) -> bytes:
    fixed = int(round(dpi * 65536))
    data = struct.pack(">iHH", fixed, 1, 1) + struct.pack(">iHH", fixed, 1, 1)
    return b"8BIM" + _u16(1005) + b"\x00\x00" + _u32(len(data)) + data


def _write_psd(
    path,
    width: int,
    height: int,
    entries: list[tuple[bytes, bytes]],
    composite: np.ndarray | None = None,
    *,
    version: int = 1,
    depth: int = 8,
    color_mode: int = 3,
    channels: int = 4,
    resources: bytes = b"",
    composite_compression: str = "raw",
    rle_layout: str = "spec",
    write_layers: bool = True,
    global_mask: bool = True,
    global_tags: bytes = b"",
) -> None:
    header = (
        b"8BPS"
        + _u16(version)
        + b"\x00" * 6
        + _u16(channels)
        + _u32(height)
        + _u32(width)
        + _u16(depth)
        + _u16(color_mode)
    )
    color_data = _u32(0)
    image_resources = _u32(len(resources)) + resources
    if write_layers and entries:
        records = b"".join(entry[0] for entry in entries)
        channel_data = b"".join(entry[1] for entry in entries)
        layer_info = _i16(len(entries)) + records + channel_data
        section = _u32(len(layer_info)) + layer_info
        if global_mask:
            section += _u32(0)
        section += global_tags
        layer_section = _u32(len(section)) + section
    else:
        layer_section = _u32(0)
    if composite is None:
        composite = np.zeros((height, width, 4), dtype=np.uint8)
    image = _image_data(composite, composite_compression, rle_layout)
    path.write_bytes(
        header + color_data + image_resources + layer_section + image
    )


def _solid(width: int, height: int, color) -> np.ndarray:
    array = np.zeros((height, width, 4), dtype=np.uint8)
    array[...] = color
    return array


def _basic_psd(path, compression: str = "rle"):
    width, height = 20, 12
    background = _solid(width, height, (200, 50, 60, 255))
    hidden = _solid(4, 4, (10, 220, 30, 128))
    entries = [
        _record(
            "Background",
            (0, 0, height, width),
            {0: background[..., 0], 1: background[..., 1], 2: background[..., 2], -1: background[..., 3]},
            compression=compression,
        ),
        _record(
            "Ẩn",
            (3, 2, 7, 6),
            {
                0: hidden[..., 0],
                1: hidden[..., 1],
                2: hidden[..., 2],
                -1: hidden[..., 3],
            },
            blend=b"mul ",
            opacity=128,
            visible=False,
            color_index=2,
            compression=compression,
        ),
    ]
    composite = _solid(width, height, (12, 34, 56, 255))
    _write_psd(
        path,
        width,
        height,
        entries,
        composite,
        resources=_dpi_resource(300),
        composite_compression="rle",
    )
    return width, height


# ---------------------------------------------------- vogk (live shape) fixture
def _dstr(text: str) -> bytes:
    return _u32(len(text)) + text.encode("utf-16-be")


def _did(text: str) -> bytes:
    raw = text.encode("latin-1")
    return _u32(len(raw)) + raw


def _did_zero(text: str) -> bytes:
    """Khoá 4 ký tự kiểu Photoshop: độ dài 0 rồi 4 byte thô."""
    raw = text.encode("latin-1")
    if len(raw) == 4:
        return _u32(0) + raw
    return _u32(len(raw)) + raw


def _descriptor(name: str, class_id: str, items: list[bytes]) -> bytes:
    return _dstr(name) + _did(class_id) + _u32(len(items)) + b"".join(items)


def _descriptor_zero(name: str, class_id: str, items: list[bytes]) -> bytes:
    return _dstr(name) + _did_zero(class_id) + _u32(len(items)) + b"".join(items)


def _desc_item(key: str, os_type: bytes, value: bytes) -> bytes:
    return _did(key) + os_type + value


def _desc_item_zero(key: str, os_type: bytes, value: bytes) -> bytes:
    return _did_zero(key) + os_type + value


def _d_double(value: float) -> bytes:
    return struct.pack(">d", value)


def _shape_geometry(
    bounds: tuple[float, float, float, float],
    class_id: str,
    radius: float | None = None,
) -> bytes:
    top, left, bottom, right = bounds
    items = [
        _desc_item("Top ", b"doub", _d_double(top)),
        _desc_item("Left", b"doub", _d_double(left)),
        _desc_item("Btom", b"doub", _d_double(bottom)),
        _desc_item("Rght", b"doub", _d_double(right)),
    ]
    if radius is not None:
        items.append(_desc_item("Rds ", b"doub", _d_double(radius)))
    return _descriptor("", class_id, items)


def _vogk(
    key: str,
    class_id: str,
    bounds: tuple[float, float, float, float],
    *,
    radius: float | None = None,
    fill_enabled: bool = True,
    stroke: tuple[float, tuple[int, int, int]] | None = None,
) -> bytes:
    style_items = [
        _desc_item("fillEnabled", b"bool", bytes([1 if fill_enabled else 0]))
    ]
    if stroke is not None:
        width, color = stroke
        rg = _descriptor(
            "",
            "RGBC",
            [
                _desc_item("Rd  ", b"doub", _d_double(color[0])),
                _desc_item("Grn ", b"doub", _d_double(color[1])),
                _desc_item("Bl  ", b"doub", _d_double(color[2])),
            ],
        )
        style_items += [
            _desc_item("strokeEnabled", b"bool", b"\x01"),
            _desc_item("strokeStyleLineWidth", b"UntF", b"#Pnt" + _d_double(width)),
            _desc_item("strokeStyleContent", b"Objc", _descriptor("", "SoCo", [_desc_item("Clr ", b"Objc", rg)])),
        ]
    root = _descriptor(
        "",
        "vectorOriginationData",
        [
            _desc_item(key, b"Objc", _shape_geometry(bounds, class_id, radius)),
            _desc_item("shapeStyle", b"Objc", _descriptor("", "shapeStyle", style_items)),
        ],
    )
    return _u32(1) + root


def _shape_psd(
    path,
    bounds: tuple[int, int, int, int],
    vogk: bytes | None,
    *,
    raster: np.ndarray,
    mask: tuple[tuple[int, int, int, int], np.ndarray, int, int] | None = None,
    opacity: int = 255,
    tags: tuple[tuple[bytes, bytes], ...] = (),
):
    top, left, bottom, right = bounds
    width, height = right - left, bottom - top
    assert raster.shape[:2] == (height, width)
    channels = {
        0: raster[..., 0],
        1: raster[..., 1],
        2: raster[..., 2],
        -1: raster[..., 3],
    }
    all_tags: list[tuple[bytes, bytes]] = []
    if vogk is not None:
        all_tags.append((b"vogk", vogk))
    all_tags.extend(tags)
    entry = _record(
        "Shape",
        bounds,
        channels,
        tags=tuple(all_tags),
        mask=mask,
        opacity=opacity,
    )
    canvas_width, canvas_height = max(right, 24), max(bottom, 20)
    _write_psd(
        path,
        canvas_width,
        canvas_height,
        [entry],
        _solid(canvas_width, canvas_height, (1, 2, 3, 255)),
    )
    return canvas_width, canvas_height


def _origin_vogk(bounds: tuple[float, float, float, float]) -> bytes:
    """vogk thật của Photoshop: chỉ có keyDescriptorList với origin/bbox."""
    top, left, bottom, right = bounds
    bbox = _descriptor_zero(
        "",
        "unitRect",
        [
            _desc_item_zero("unitValueQuadVersion", b"long", _u32(1)),
            _desc_item_zero("Top ", b"UntF", b"#Pxl" + _d_double(top)),
            _desc_item_zero("Left", b"UntF", b"#Pxl" + _d_double(left)),
            _desc_item_zero("Btom", b"UntF", b"#Pxl" + _d_double(bottom)),
            _desc_item_zero("Rght", b"UntF", b"#Pxl" + _d_double(right)),
        ],
    )
    origin = _descriptor_zero(
        "",
        "null",
        [
            _desc_item_zero("keyOriginType", b"long", _u32(1)),
            _desc_item_zero("keyOriginResolution", b"doub", _d_double(240.0)),
            _desc_item_zero("keyOriginShapeBBox", b"Objc", bbox),
            _desc_item_zero("keyOriginIndex", b"long", _u32(0)),
        ],
    )
    root = _descriptor_zero(
        "",
        "null",
        [
            _desc_item_zero(
                "keyDescriptorList",
                b"VlLs",
                _u32(1) + b"Objc" + origin,
            )
        ],
    )
    return _u32(1) + _u32(16) + root


def _parametric_vogk_zero(
    key: str, class_id: str, bounds: tuple[float, float, float, float]
) -> bytes:
    """vogk dạng tham số nhưng khoá 4 ký tự dùng marker độ dài 0."""
    top, left, bottom, right = bounds
    geometry = _descriptor_zero(
        "",
        class_id,
        [
            _desc_item_zero("Top ", b"UntF", b"#Pxl" + _d_double(top)),
            _desc_item_zero("Left", b"UntF", b"#Pxl" + _d_double(left)),
            _desc_item_zero("Btom", b"UntF", b"#Pxl" + _d_double(bottom)),
            _desc_item_zero("Rght", b"UntF", b"#Pxl" + _d_double(right)),
        ],
    )
    root = _descriptor_zero(
        "", "null", [_desc_item_zero(key, b"Objc", geometry)]
    )
    return _u32(1) + _u32(16) + root


def _mask_raster(
    width: int,
    height: int,
    mask: np.ndarray,
    color: tuple[int, int, int],
) -> np.ndarray:
    raster = np.zeros((height, width, 4), dtype=np.uint8)
    raster[mask, 0] = color[0]
    raster[mask, 1] = color[1]
    raster[mask, 2] = color[2]
    raster[mask, 3] = 255
    return raster


def _rounded_mask(height: int, width: int, radius: float) -> np.ndarray:
    xs = np.arange(width, dtype=np.float64) + 0.5
    ys = np.arange(height, dtype=np.float64) + 0.5
    dx = np.maximum(np.maximum(radius - xs, xs - (width - radius)), 0.0)[None, :]
    dy = np.maximum(np.maximum(radius - ys, ys - (height - radius)), 0.0)[:, None]
    return dx * dx + dy * dy <= radius * radius


# ------------------------------------------------ TySh (layer văn bản) fixture
def _enum(type_id: str, value: str) -> bytes:
    return _did_zero(type_id) + _did_zero(value)


def _text_style_data(
    *,
    font_name: str | None = "ArialMT",
    font_index: int | None = None,
    size: float = 24.0,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bold: bool = False,
    italic: bool = False,
    tracking: int = 0,
    leading: float = 0.0,
    auto_leading: bool = True,
    underline: bool = False,
    strikethrough: bool = False,
    horizontal_scale: int = 100,
    vertical_scale: int = 100,
) -> bytes:
    items: list[bytes] = []
    if font_name is not None:
        items.append(_desc_item("FontPostScriptName", b"TEXT", _dstr(font_name)))
    if font_index is not None:
        items.append(_desc_item("Font", b"long", struct.pack(">i", font_index)))
    items += [
        _desc_item("FontSize", b"doub", _d_double(size)),
        _desc_item("FauxBold", b"bool", bytes([1 if bold else 0])),
        _desc_item("FauxItalic", b"bool", bytes([1 if italic else 0])),
        _desc_item("Tracking", b"long", struct.pack(">i", tracking)),
        _desc_item("Leading", b"doub", _d_double(leading)),
        _desc_item("AutoLeading", b"bool", bytes([1 if auto_leading else 0])),
        _desc_item("Underline", b"bool", bytes([1 if underline else 0])),
        _desc_item("Strikethrough", b"bool", bytes([1 if strikethrough else 0])),
        _desc_item("HorizontalScale", b"long", struct.pack(">i", horizontal_scale)),
        _desc_item("VerticalScale", b"long", struct.pack(">i", vertical_scale)),
        _desc_item(
            "FillColor",
            b"Objc",
            _descriptor(
                "",
                "RGBC",
                [
                    _desc_item("Rd  ", b"doub", _d_double(color[0])),
                    _desc_item("Grn ", b"doub", _d_double(color[1])),
                    _desc_item("Bl  ", b"doub", _d_double(color[2])),
                ],
            ),
        ),
    ]
    return _descriptor_zero("", "StyleSheetData", items)


def _text_style_run(lengths: list[int], styles: list[bytes]) -> bytes:
    run_items = []
    for style in styles:
        run_items.append(
            _descriptor_zero(
                "",
                "Pnt ",
                [
                    _desc_item(
                        "StyleSheet",
                        b"Objc",
                        _descriptor_zero(
                            "",
                            "StyleSheet",
                            [_desc_item("StyleSheetData", b"Objc", style)],
                        ),
                    )
                ],
            )
        )
    lengths_data = b"".join(b"long" + struct.pack(">i", value) for value in lengths)
    runs_data = b"".join(b"Objc" + item for item in run_items)
    return _descriptor_zero(
        "",
        "StyleRun",
        [
            _desc_item(
                "RunLengthArray",
                b"VlLs",
                _u32(len(lengths)) + lengths_data,
            ),
            _desc_item("RunArray", b"VlLs", _u32(len(run_items)) + runs_data),
        ],
    )


def _text_paragraph_run(justification: str) -> bytes:
    data = _descriptor_zero(
        "",
        "ParagraphSheetData",
        [
            _desc_item(
                "Justification", b"enum", _enum("Justification", justification)
            )
        ],
    )
    run = _descriptor_zero(
        "",
        "Pnt ",
        [
            _desc_item(
                "ParagraphSheet",
                b"Objc",
                _descriptor_zero(
                    "",
                    "ParagraphSheet",
                    [_desc_item("ParagraphSheetData", b"Objc", data)],
                ),
            )
        ],
    )
    return _descriptor_zero(
        "",
        "ParagraphRun",
        [_desc_item("RunArray", b"VlLs", _u32(1) + b"Objc" + run)],
    )


def _tysh(
    text: str,
    style_run: bytes | None,
    *,
    paragraph: bytes | None = None,
    orientation: str = "Hrzn",
    engine: bytes | None = None,
    warp_style: str = "warpNone",
    warp_value: float = 0.0,
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0),
    transform: tuple[float, float, float, float, float, float] = (1, 0, 0, 1, 10, 20),
) -> bytes:
    top, left, bottom, right = bounds
    items = [
        _desc_item_zero("Txt ", b"TEXT", _dstr(text)),
        _desc_item_zero("Ornt", b"enum", _enum("Ornt", orientation)),
        _desc_item(
            "bounds",
            b"Objc",
            _descriptor_zero(
                "",
                "bounds",
                [
                    _desc_item_zero("Left", b"doub", _d_double(left)),
                    _desc_item_zero("Top ", b"doub", _d_double(top)),
                    _desc_item_zero("Rght", b"doub", _d_double(right)),
                    _desc_item_zero("Btom", b"doub", _d_double(bottom)),
                ],
            ),
        ),
    ]
    if style_run is not None:
        items.append(_desc_item_zero("StyleRun", b"Objc", style_run))
    if paragraph is not None:
        items.append(_desc_item_zero("ParagraphRun", b"Objc", paragraph))
    if engine is not None:
        items.append(_desc_item("EngineData", b"tdta", _u32(len(engine)) + engine))
    root = _descriptor_zero("", "TxLr", items)
    warp = _descriptor_zero(
        "",
        "warp",
        [
            _desc_item("warpStyle", b"enum", _enum("warpStyle", warp_style)),
            _desc_item("warpValue", b"doub", _d_double(warp_value)),
        ],
    )
    return (
        _u16(1)
        + struct.pack(">6d", *transform)
        + _u16(50)
        + _u32(16)
        + root
        + _u16(1)
        + _u32(16)
        + warp
        + struct.pack(
            ">iiii",
            int(round(top)),
            int(round(left)),
            int(round(bottom)),
            int(round(right)),
        )
    )


def _text_psd(
    path,
    tysh: bytes,
    *,
    name: str = "Chữ",
    rect: tuple[int, int, int, int] = (6, 5, 26, 45),
    raster: np.ndarray | None = None,
    mask: tuple[tuple[int, int, int, int], np.ndarray, int, int] | None = None,
    dpi: float = 72.0,
    in_group: bool = False,
):
    top, left, bottom, right = rect
    width, height = right - left, bottom - top
    if raster is None:
        raster = _solid(width, height, (10, 20, 30, 255))
    assert raster.shape[:2] == (height, width)
    channels = {
        0: raster[..., 0],
        1: raster[..., 1],
        2: raster[..., 2],
        -1: raster[..., 3],
    }
    entries: list[tuple[bytes, bytes]] = []
    if in_group:
        entries.append(_record("Nhóm", (0, 0, 0, 0), {}, section=3))
    entries.append(
        _record(
            name,
            rect,
            channels,
            tags=((b"TySh", tysh),),
            mask=mask,
        )
    )
    if in_group:
        entries.append(_record("Nhóm", (0, 0, 0, 0), {}, section=1))
    canvas_width = max(right + 8, 64)
    canvas_height = max(bottom + 8, 48)
    resources = _dpi_resource(dpi) if abs(dpi - 72.0) > 0.01 else b""
    _write_psd(
        path,
        canvas_width,
        canvas_height,
        entries,
        _solid(canvas_width, canvas_height, (1, 2, 3, 255)),
        resources=resources,
    )
    return canvas_width, canvas_height


def _engine_string(text: str, *, utf16: bool = False) -> bytes:
    if utf16:
        return b"(" + b"\xfe\xff" + text.encode("utf-16-be") + b")"
    return b"(" + text.encode("ascii") + b")"


def _engine_text_blob(
    font_names: list[str],
    *,
    font_indices: list[int] | None = None,
    size: float = 24.0,
    color: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    tracking: int = 0,
    lengths: tuple[int, ...] = (5,),
    justification: int = 0,
    utf16_fonts: bool = False,
) -> bytes:
    if font_indices is None:
        font_indices = [0] * len(lengths)
    font_set = b" ".join(
        b"<< /Name " + _engine_string(name, utf16=utf16_fonts) + b" >>"
        for name in font_names
    )
    runs = []
    for index in font_indices:
        runs.append(
            (
                b"<< /StyleSheet << /StyleSheetData << /Font %d /FontSize %.1f "
                b"/FauxBold false /FauxItalic false /AutoLeading true "
                b"/Tracking %d /HorizontalScale 1.0 /VerticalScale 1.0 "
                b"/FillColor << /Type 1 /Values [ %s ] >> >> >> >>"
            )
            % (
                index,
                size,
                tracking,
                b" ".join(b"%.5f" % value for value in color),
            )
        )
    lengths_bytes = b" ".join(str(value).encode() for value in lengths)
    paragraph = (
        b"<< /ParagraphSheet << /Properties << /Justification %d >> >> >>"
        % justification
    )
    return (
        b"<< /EngineDict << "
        b"/StyleRun << /RunArray [ "
        + b" ".join(runs)
        + b" ] /RunLengthArray [ "
        + lengths_bytes
        + b" ] /IsJoinable 2 >> "
        b"/ParagraphRun << /RunArray [ "
        + paragraph
        + b" ] /RunLengthArray [ "
        + lengths_bytes
        + b" ] /IsJoinable 1 >> >> "
        b"/ResourceDict << /FontSet [ "
        + font_set
        + b" ] >> "
        b">>"
    )


# ------------------------------------------------------------------- kiểm thử
def test_psd_reads_raw_layers_properties_and_dpi(tmp_path):
    path = tmp_path / "basic.psd"
    width, height = _basic_psd(path, compression="raw")

    document, report = load_psd_document(path)

    assert (document.width, document.height) == (width, height)
    assert document.dpi == pytest.approx(300.0, abs=0.1)
    assert document.file_path is None
    assert [layer.name for layer in document.layers] == ["Background", "Ẩn"]
    assert report.layers == 2
    assert report.skipped == []
    assert report.composite_added is False

    background = document.layers[0]
    assert background.offset_x == 0 and background.offset_y == 0
    assert tuple(background.pixels[0, 0]) == (200, 50, 60, 255)

    hidden = document.layers[1]
    assert (hidden.offset_x, hidden.offset_y) == (2, 3)
    assert (hidden.width, hidden.height) == (4, 4)
    assert hidden.visible is False
    assert hidden.opacity == pytest.approx(128 / 255)
    assert hidden.blend_mode == "multiply"
    assert hidden.color_label == "orange"
    assert tuple(hidden.pixels[1, 1]) == (10, 220, 30, 128)


def test_psd_rle_and_zip_match_raw(tmp_path):
    raw_path = tmp_path / "raw.psd"
    rle_path = tmp_path / "rle.psd"
    zip_path = tmp_path / "zip.psd"
    _basic_psd(raw_path, compression="raw")
    _basic_psd(rle_path, compression="rle")
    _basic_psd(zip_path, compression="zip")

    raw_doc, _ = load_psd_document(raw_path)
    rle_doc, _ = load_psd_document(rle_path)
    zip_doc, _ = load_psd_document(zip_path)

    for index in range(2):
        assert np.array_equal(raw_doc.layers[index].pixels, rle_doc.layers[index].pixels)
        assert np.array_equal(raw_doc.layers[index].pixels, zip_doc.layers[index].pixels)


def test_psd_imports_group_mask_clipping_and_skips_text(tmp_path):
    path = tmp_path / "group.psd"
    width, height = 24, 18
    background = _solid(width, height, (20, 30, 40, 255))
    child = _solid(6, 5, (50, 100, 150, 255))
    child_mask = np.zeros((5, 6), dtype=np.uint8)
    child_mask[:, :3] = 255
    top = _solid(8, 8, (240, 240, 240, 180))

    entries = [
        _record(
            "Background",
            (0, 0, height, width),
            {0: background[..., 0], 1: background[..., 1], 2: background[..., 2], -1: background[..., 3]},
        ),
        _record("Nhóm", (0, 0, 0, 0), {}, section=3),
        _record(
            "Con",
            (4, 3, 9, 9),
            {0: child[..., 0], 1: child[..., 1], 2: child[..., 2], -1: child[..., 3]},
            mask=((4, 3, 9, 9), child_mask, 0, 255),
        ),
        _record(
            "Chữ",
            (0, 0, 0, 0),
            {},
            tags=((b"TySh", b"\x00" * 16),),
        ),
        _record("Nhóm", (0, 0, 0, 0), {}, section=1),
        _record(
            "Trên",
            (10, 12, 18, 20),
            {0: top[..., 0], 1: top[..., 1], 2: top[..., 2], -1: top[..., 3]},
            blend=b"scrn",
            clipping=1,
        ),
    ]
    composite = _solid(width, height, (90, 80, 70, 255))
    _write_psd(path, width, height, entries, composite)

    document, report = load_psd_document(path)

    assert report.layers == 3
    assert report.groups == 1
    assert any("Chữ" in item and "văn bản" in item for item in report.skipped)
    assert report.composite_added is True
    assert document.layers[0].name == "Ảnh hợp nhất PSD"
    assert document.layers[0].visible is False

    names = [layer.name for layer in document.layers]
    assert names == ["Ảnh hợp nhất PSD", "Background", "Con", "Nhóm", "Trên"]

    group = next(layer for layer in document.layers if layer.name == "Nhóm")
    child_layer = next(layer for layer in document.layers if layer.name == "Con")
    assert child_layer.group_id == group.id
    assert group.group_id is None
    assert document.layers.index_of(group) > document.layers.index_of(child_layer)
    assert child_layer.mask is not None
    assert child_layer.mask_enabled is True
    assert np.array_equal(child_layer.mask, child_mask)

    top_layer = document.layers[-1]
    assert top_layer.clipping is True
    assert top_layer.blend_mode == "screen"


def test_psd_mask_relative_inverted_and_disabled(tmp_path):
    path = tmp_path / "mask.psd"
    width, height = 12, 10
    source = _solid(4, 4, (100, 110, 120, 255))
    mask_values = np.array(
        [[0, 0, 255, 255], [0, 255, 255, 0], [255, 0, 0, 255], [0, 0, 0, 0]],
        dtype=np.uint8,
    )
    entries = [
        _record(
            "Masked",
            (2, 3, 6, 7),
            {0: source[..., 0], 1: source[..., 1], 2: source[..., 2], -1: source[..., 3]},
            mask=((0, 0, 4, 4), mask_values, 0b111, 255),
        )
    ]
    _write_psd(path, width, height, entries, _solid(width, height, (5, 5, 5, 255)))

    document, _ = load_psd_document(path)
    layer = document.layers[0]
    assert layer.mask_enabled is False
    assert np.array_equal(layer.mask, 255 - mask_values)


def test_psd_group_mask_on_folder_record(tmp_path):
    path = tmp_path / "group_mask.psd"
    width, height = 10, 8
    background = _solid(width, height, (70, 80, 90, 255))
    child = _solid(4, 3, (200, 100, 50, 255))
    group_mask = np.zeros((height, width), dtype=np.uint8)
    group_mask[2:6, 3:8] = 255
    entries = [
        _record(
            "Background",
            (0, 0, height, width),
            {0: background[..., 0], 1: background[..., 1], 2: background[..., 2], -1: background[..., 3]},
        ),
        _record("Nhóm", (0, 0, 0, 0), {}, section=3),
        _record(
            "Con",
            (1, 1, 4, 5),
            {0: child[..., 0], 1: child[..., 1], 2: child[..., 2], -1: child[..., 3]},
        ),
        _record(
            "Nhóm",
            (0, 0, 0, 0),
            {},
            section=1,
            mask=((0, 0, height, width), group_mask, 0, 255),
        ),
    ]
    _write_psd(path, width, height, entries, _solid(width, height, (1, 2, 3, 255)))

    document, report = load_psd_document(path)

    assert report.groups == 1
    group = next(layer for layer in document.layers if layer.name == "Nhóm")
    child_layer = next(layer for layer in document.layers if layer.name == "Con")
    assert child_layer.group_id == group.id
    assert group.mask is not None
    assert group.mask_enabled is True
    assert np.array_equal(group.mask, group_mask)


def test_psd_rectangle_becomes_editable_shape_layer(tmp_path):
    path = tmp_path / "rectangle.psd"
    bounds = (5, 4, 25, 34)
    raster = _solid(30, 20, (100, 150, 200, 255))
    _shape_psd(
        path,
        bounds,
        _vogk("rect", "rect", (5.0, 4.0, 25.0, 34.0)),
        raster=raster,
        opacity=180,
    )

    document, report = load_psd_document(path)

    assert report.shapes == 1
    assert report.layers == 1
    assert report.skipped == []
    layer = document.layers[0]
    assert layer.kind == LayerKind.SHAPE
    assert (layer.offset_x, layer.offset_y) == (4, 5)
    assert (layer.width, layer.height) == (30, 20)
    assert layer.shape.kind == "rectangle"
    assert layer.shape.fill_color == (100, 150, 200, 255)
    assert layer.shape.stroke_width == 0
    assert layer.opacity == pytest.approx(180 / 255)
    assert layer.shape.corner_radii == (0.0, 0.0, 0.0, 0.0)


def test_psd_rounded_rectangle_and_ellipse_become_shape_layers(tmp_path):
    rounded_path = tmp_path / "rounded.psd"
    raster = _solid(30, 20, (220, 120, 40, 255))
    _shape_psd(
        rounded_path,
        (2, 3, 22, 33),
        _vogk("roundRect", "rnd ", (2.0, 3.0, 22.0, 33.0), radius=6.0),
        raster=raster,
    )
    ellipse_path = tmp_path / "ellipse.psd"
    _shape_psd(
        ellipse_path,
        (2, 3, 22, 33),
        _vogk("ellipse", "elip", (2.0, 3.0, 22.0, 33.0)),
        raster=raster,
    )

    rounded_doc, rounded_report = load_psd_document(rounded_path)
    ellipse_doc, ellipse_report = load_psd_document(ellipse_path)

    assert rounded_report.shapes == 1
    rounded = rounded_doc.layers[0]
    assert rounded.kind == LayerKind.SHAPE
    assert rounded.shape.kind == "rounded_rectangle"
    assert rounded.shape.corner_radii == (6.0, 6.0, 6.0, 6.0)

    assert ellipse_report.shapes == 1
    ellipse = ellipse_doc.layers[0]
    assert ellipse.kind == LayerKind.SHAPE
    assert ellipse.shape.kind == "ellipse"


def test_psd_shape_keeps_stroke_and_disabled_fill(tmp_path):
    stroke_path = tmp_path / "stroke.psd"
    raster = _solid(20, 16, (60, 90, 120, 255))
    raster[:3, :] = raster[-3:, :] = (220, 30, 40, 255)
    raster[:, :3] = raster[:, -3:] = (220, 30, 40, 255)
    _shape_psd(
        stroke_path,
        (1, 1, 17, 21),
        _vogk(
            "rect",
            "rect",
            (1.0, 1.0, 17.0, 21.0),
            stroke=(3.0, (220, 30, 40)),
        ),
        raster=raster,
    )
    outline_path = tmp_path / "outline.psd"
    _shape_psd(
        outline_path,
        (1, 1, 17, 21),
        _vogk(
            "rect",
            "rect",
            (1.0, 1.0, 17.0, 21.0),
            fill_enabled=False,
            stroke=(2.0, (10, 20, 30)),
        ),
        raster=np.zeros((16, 20, 4), dtype=np.uint8),
    )

    stroke_doc, stroke_report = load_psd_document(stroke_path)
    outline_doc, outline_report = load_psd_document(outline_path)

    assert stroke_report.shapes == 1
    stroke_layer = stroke_doc.layers[0]
    assert stroke_layer.kind == LayerKind.SHAPE
    assert stroke_layer.shape.stroke_width == 3
    assert stroke_layer.shape.stroke_color == (220, 30, 40, 255)
    assert stroke_layer.shape.fill_color == (60, 90, 120, 255)

    assert outline_report.shapes == 1
    outline_layer = outline_doc.layers[0]
    assert outline_layer.kind == LayerKind.SHAPE
    assert outline_layer.shape.fill_color is None
    assert outline_layer.shape.stroke_width == 2
    assert outline_layer.shape.stroke_color == (10, 20, 30, 255)


def test_psd_gradient_shape_falls_back_to_pixel_layer(tmp_path):
    path = tmp_path / "gradient.psd"
    raster = np.zeros((16, 20, 4), dtype=np.uint8)
    raster[:, :10] = (200, 100, 50, 255)
    raster[:, 10:] = (10, 200, 100, 255)
    _shape_psd(
        path,
        (1, 1, 17, 21),
        _vogk("rect", "rect", (1.0, 1.0, 17.0, 21.0)),
        raster=raster,
    )

    document, report = load_psd_document(path)

    assert report.shapes == 0
    assert report.layers == 1
    assert document.layers[0].kind == LayerKind.PIXEL
    assert tuple(document.layers[0].pixels[0, 0]) == (200, 100, 50, 255)


def test_psd_shape_keeps_layer_mask(tmp_path):
    path = tmp_path / "shape_mask.psd"
    raster = _solid(20, 16, (90, 140, 60, 255))
    mask_values = np.zeros((16, 20), dtype=np.uint8)
    mask_values[:, :10] = 255
    _shape_psd(
        path,
        (1, 1, 17, 21),
        _vogk("rect", "rect", (1.0, 1.0, 17.0, 21.0)),
        raster=raster,
        mask=((1, 1, 17, 21), mask_values, 0, 255),
    )

    document, report = load_psd_document(path)

    assert report.shapes == 1
    layer = document.layers[0]
    assert layer.kind == LayerKind.SHAPE
    assert layer.mask is not None
    assert layer.mask_enabled is True
    assert np.array_equal(layer.mask, mask_values)
    assert not any("vector mask" in item for item in report.warnings)


def test_psd_shape_inside_group_keeps_group_and_layer_order(tmp_path):
    path = tmp_path / "group_shape.psd"
    width, height = 20, 16
    raster = _solid(10, 8, (50, 120, 200, 255))
    entries = [
        _record("Nhóm", (0, 0, 0, 0), {}, section=3),
        _record(
            "Shape",
            (1, 1, 9, 11),
            {0: raster[..., 0], 1: raster[..., 1], 2: raster[..., 2], -1: raster[..., 3]},
            tags=((b"vogk", _vogk("rect", "rect", (1.0, 1.0, 9.0, 11.0))),),
        ),
        _record("Nhóm", (0, 0, 0, 0), {}, section=1),
    ]
    _write_psd(path, width, height, entries, _solid(width, height, (0, 0, 0, 255)))

    document, report = load_psd_document(path)

    assert report.shapes == 1
    assert report.groups == 1
    assert [layer.name for layer in document.layers] == ["Shape", "Nhóm"]
    shape_layer, group = document.layers[0], document.layers[1]
    assert shape_layer.kind == LayerKind.SHAPE
    assert shape_layer.group_id == group.id


def test_psd_real_vogk_with_vmsk_infers_rectangle(tmp_path):
    path = tmp_path / "real_rect.psd"
    mask = np.zeros((20, 30), dtype=bool)
    mask[1:19, 1:29] = True
    raster = _mask_raster(30, 20, mask, (0, 0, 0))
    _shape_psd(
        path,
        (5, 4, 25, 34),
        _origin_vogk((6.0, 5.0, 24.0, 33.0)),
        raster=raster,
        tags=((b"vmsk", b"\x00\x00\x00\x03"),),
    )

    document, report = load_psd_document(path)

    assert report.shapes == 1
    assert report.layers == 1
    layer = document.layers[0]
    assert layer.kind == LayerKind.SHAPE
    assert layer.shape.kind == "rectangle"
    assert layer.shape.fill_color == (0, 0, 0, 255)
    assert (layer.offset_x, layer.offset_y) == (5, 6)
    assert (layer.width, layer.height) == (28, 18)


def test_psd_zero_length_descriptor_ids_still_read_parametric_shape(tmp_path):
    path = tmp_path / "zero_ids.psd"
    raster = _solid(30, 20, (120, 60, 200, 255))
    _shape_psd(
        path,
        (5, 4, 25, 34),
        _parametric_vogk_zero("rect", "rect", (5.0, 4.0, 25.0, 34.0)),
        raster=raster,
    )

    document, report = load_psd_document(path)

    assert report.shapes == 1
    layer = document.layers[0]
    assert layer.kind == LayerKind.SHAPE
    assert layer.shape.kind == "rectangle"
    assert layer.shape.fill_color == (120, 60, 200, 255)
    assert (layer.width, layer.height) == (30, 20)


def test_psd_raster_mask_infers_ellipse_and_rounded_rectangle(tmp_path):
    ellipse_path = tmp_path / "ellipse_mask.psd"
    yy, xx = np.mgrid[0:20, 0:30]
    ellipse = ((xx - 15) / 13.0) ** 2 + ((yy - 10) / 8.0) ** 2 <= 1.0
    _shape_psd(
        ellipse_path,
        (1, 1, 21, 31),
        None,
        raster=_mask_raster(30, 20, ellipse, (30, 160, 90)),
        tags=((b"vmsk", b"\x00\x00\x00\x03"),),
    )

    rounded_path = tmp_path / "rounded_mask.psd"
    _shape_psd(
        rounded_path,
        (1, 1, 21, 31),
        None,
        raster=_mask_raster(
            30, 20, _rounded_mask(20, 30, 6.0), (200, 80, 40)
        ),
        tags=((b"vmsk", b"\x00\x00\x00\x03"),),
    )

    ellipse_doc, ellipse_report = load_psd_document(ellipse_path)
    rounded_doc, rounded_report = load_psd_document(rounded_path)

    assert ellipse_report.shapes == 1
    ellipse_layer = ellipse_doc.layers[0]
    assert ellipse_layer.kind == LayerKind.SHAPE
    assert ellipse_layer.shape.kind == "ellipse"

    assert rounded_report.shapes == 1
    rounded_layer = rounded_doc.layers[0]
    assert rounded_layer.kind == LayerKind.SHAPE
    assert rounded_layer.shape.kind == "rounded_rectangle"
    assert rounded_layer.shape.corner_radius == pytest.approx(6.0, abs=1.5)


def test_psd_rectangle_mask_without_vmsk_stays_pixel_layer(tmp_path):
    path = tmp_path / "pixel_rect.psd"
    mask = np.zeros((20, 30), dtype=bool)
    mask[1:19, 1:29] = True
    _shape_psd(
        path,
        (5, 4, 25, 34),
        None,
        raster=_mask_raster(30, 20, mask, (10, 20, 30)),
    )

    document, report = load_psd_document(path)

    assert report.shapes == 0
    assert document.layers[0].kind == LayerKind.PIXEL


def test_psd_text_layer_imports_as_editable_text(tmp_path):
    path = tmp_path / "text.psd"
    style = _text_style_data(
        font_name="Arial-BoldMT", size=18, color=(1.0, 0.0, 0.0)
    )
    _text_psd(
        path,
        _tysh("Hello", _text_style_run([5], [style])),
        rect=(6, 5, 26, 45),
    )

    document, report = load_psd_document(path)

    assert report.layers == 1
    assert report.texts == 1
    assert report.shapes == 0
    assert report.skipped == []
    assert "1 layer văn bản" in report.summary()
    layer = document.layers[0]
    assert layer.kind == LayerKind.TEXT
    assert layer.text is not None
    properties = layer.text
    assert properties.text == "Hello"
    assert properties.font_family == "Arial"
    assert properties.font_size == 18
    assert properties.bold is True
    assert properties.italic is False
    assert properties.color == (255, 0, 0, 255)
    assert [run.text for run in properties.runs] == ["Hello"]
    assert (layer.offset_x, layer.offset_y) == (5, 6)
    # Pixel gốc của Photoshop vẫn là hình hiển thị ban đầu.
    assert tuple(layer.pixels[0, 0]) == (10, 20, 30, 255)


def test_psd_text_runs_fontset_and_dpi_preserved(tmp_path):
    path = tmp_path / "runs.psd"
    engine = (
        b"<<\n/FontSet [\n"
        b"<<\n/Name (Roboto-Regular)\n>>\n"
        b"<<\n/Name (OpenSans-Bold)\n>>\n"
        b"]\n>>"
    )
    first = _text_style_data(
        font_name=None, font_index=0, size=12, color=(0.0, 0.0, 1.0)
    )
    second = _text_style_data(
        font_name=None, font_index=1, size=12, color=(0.0, 1.0, 0.0)
    )
    _text_psd(
        path,
        _tysh(
            "Hello World",
            _text_style_run([5, 6], [first, second]),
            engine=engine,
        ),
        rect=(3, 2, 43, 62),
        dpi=144,
    )

    document, report = load_psd_document(path)

    assert report.texts == 1
    layer = document.layers[0]
    assert layer.kind == LayerKind.TEXT and layer.text is not None
    properties = layer.text
    assert [run.text for run in properties.runs] == ["Hello", " World"]
    assert [run.font_family for run in properties.runs] == ["Roboto", "Open Sans"]
    # 12 pt ở 144 DPI tương đương 24 px.
    assert [run.font_size for run in properties.runs] == [24, 24]
    assert properties.runs[1].color == (0, 255, 0, 255)


def test_psd_text_alignment_tracking_warp_and_warnings(tmp_path):
    path = tmp_path / "layout.psd"
    style = _text_style_data(size=20, tracking=120, underline=True)
    _text_psd(
        path,
        _tysh(
            "Hello",
            _text_style_run([5], [style]),
            paragraph=_text_paragraph_run("Center"),
            warp_style="warpArch",
            warp_value=40.0,
        ),
    )

    document, report = load_psd_document(path)

    layer = document.layers[0]
    assert layer.kind == LayerKind.TEXT and layer.text is not None
    properties = layer.text
    assert properties.alignment == "center"
    assert properties.letter_spacing == 2  # 120/1000 × 20 px
    assert properties.line_spacing == 1.0  # AutoLeading
    assert properties.warp_style == "arch"
    assert properties.warp_bend == 40
    assert any("gạch chân" in message for message in report.warnings)


def test_psd_vertical_text_falls_back_to_pixel(tmp_path):
    path = tmp_path / "vertical.psd"
    _text_psd(
        path,
        _tysh(
            "Doc",
            _text_style_run([3], [_text_style_data()]),
            orientation="Vrtc",
        ),
    )

    document, report = load_psd_document(path)

    assert report.texts == 0
    assert document.layers[0].kind == LayerKind.PIXEL
    assert any("văn bản dọc" in message for message in report.warnings)


def test_psd_invalid_tysh_with_pixels_stays_pixel(tmp_path):
    path = tmp_path / "bad_tysh.psd"
    top, left, bottom, right = 4, 3, 24, 23
    raster = _solid(right - left, bottom - top, (100, 110, 120, 255))
    _write_psd(
        path,
        64,
        48,
        [
            _record(
                "Chữ hỏng",
                (top, left, bottom, right),
                {
                    0: raster[..., 0],
                    1: raster[..., 1],
                    2: raster[..., 2],
                    -1: raster[..., 3],
                },
                tags=((b"TySh", b"\x00" * 16),),
            )
        ],
        _solid(64, 48, (1, 2, 3, 255)),
    )

    document, report = load_psd_document(path)

    assert report.texts == 0
    assert document.layers[0].kind == LayerKind.PIXEL
    assert any("giữ dạng pixel" in message for message in report.warnings)


def test_psd_text_layer_keeps_group_and_mask(tmp_path):
    path = tmp_path / "text_group.psd"
    top, left, bottom, right = 6, 5, 21, 25
    mask = np.zeros((bottom - top, right - left), dtype=np.uint8)
    mask[:, : (right - left) // 2] = 255
    _text_psd(
        path,
        _tysh("Hello", _text_style_run([5], [_text_style_data()])),
        rect=(top, left, bottom, right),
        mask=((top, left, bottom, right), mask, 0, 255),
        in_group=True,
    )

    document, report = load_psd_document(path)

    assert report.groups == 1
    assert report.texts == 1
    text_layer = next(layer for layer in document.layers if layer.name == "Chữ")
    group = next(layer for layer in document.layers if layer.name == "Nhóm")
    assert text_layer.kind == LayerKind.TEXT
    assert text_layer.group_id == group.id
    assert text_layer.mask is not None
    assert text_layer.mask.shape == mask.shape
    assert np.array_equal(text_layer.mask[:, : mask.shape[1] // 2], np.full((mask.shape[0], mask.shape[1] // 2), 255, dtype=np.uint8))


def test_psd_text_style_from_engine_data_only(tmp_path):
    path = tmp_path / "engine_text.psd"
    engine = _engine_text_blob(
        ["Inter-Regular"],
        size=30.0,
        color=(1.0, 0.0, 0.50196, 1.0),
        tracking=50,
        lengths=(5,),
        justification=2,
        utf16_fonts=True,
    )
    _text_psd(path, _tysh("Hello", None, engine=engine))

    document, report = load_psd_document(path)

    assert report.texts == 1
    layer = document.layers[0]
    assert layer.kind == LayerKind.TEXT
    properties = layer.text
    assert properties.text == "Hello"
    assert properties.font_family == "Inter"
    assert properties.font_size == 30
    assert properties.color == (0, 128, 255, 255)
    assert properties.alignment == "center"
    assert properties.letter_spacing == 2
    assert properties.runs[0].bold is False


def test_psd_text_engine_data_runs_split_fonts(tmp_path):
    path = tmp_path / "engine_runs.psd"
    engine = _engine_text_blob(
        ["Roboto-Regular", "OpenSans-Bold"],
        font_indices=[0, 1],
        lengths=(2, 3),
        size=20.0,
        color=(1.0, 0.2, 0.2, 0.2),
    )
    _text_psd(path, _tysh("Hello", None, engine=engine))

    document, report = load_psd_document(path)

    assert report.texts == 1
    properties = document.layers[0].text
    assert properties.color == (51, 51, 51, 255)
    assert [run.text for run in properties.runs] == ["He", "llo"]
    assert [run.font_family for run in properties.runs] == ["Roboto", "Open Sans"]
    assert [run.font_size for run in properties.runs] == [20, 20]
    assert properties.runs[0].bold is False
    assert properties.runs[1].bold is True


def test_psd_global_mask_and_tagged_blocks_padded_to_four(tmp_path):
    path = tmp_path / "global_blocks.psd"
    width, height = 6, 5
    background = _solid(width, height, (40, 60, 80, 255))
    global_tags = _tag(b"lnkD", b"abcdef", padding=4) + _tag(
        b"abcd", b"xyz12", padding=4
    )
    entries = [
        _record(
            "Nền",
            (0, 0, height, width),
            {0: background[..., 0], 1: background[..., 1], 2: background[..., 2], -1: background[..., 3]},
        )
    ]
    _write_psd(
        path,
        width,
        height,
        entries,
        _solid(width, height, (9, 9, 9, 255)),
        global_mask=True,
        global_tags=global_tags,
    )

    document, report = load_psd_document(path)

    assert [layer.name for layer in document.layers] == ["Nền"]
    assert report.layers == 1


def test_psd_rle_composite_reads_both_table_layouts(tmp_path):
    width, height = 6, 4
    composite = _solid(width, height, (30, 120, 210, 255))
    composite[1:3, 2:5] = (200, 40, 60, 255)
    spec_path = tmp_path / "spec_rle.psd"
    legacy_path = tmp_path / "legacy_rle.psd"
    _write_psd(
        spec_path,
        width,
        height,
        [],
        composite,
        composite_compression="rle",
        write_layers=False,
    )
    _write_psd(
        legacy_path,
        width,
        height,
        [],
        composite,
        composite_compression="rle",
        rle_layout="per_channel",
        write_layers=False,
    )

    spec_doc, _ = load_psd_document(spec_path)
    legacy_doc, _ = load_psd_document(legacy_path)

    assert np.array_equal(spec_doc.layers[0].pixels, composite)
    assert np.array_equal(legacy_doc.layers[0].pixels, composite)


def test_psd_composite_only_opens_as_background(tmp_path):
    path = tmp_path / "flat.psd"
    width, height = 9, 7
    composite = _solid(width, height, (30, 120, 210, 255))
    _write_psd(path, width, height, [], composite, write_layers=False)

    document, report = load_psd_document(path)

    assert report.layers == 1
    assert len(document.layers) == 1
    assert document.layers[0].name == "Ảnh PSD"
    assert tuple(document.layers[0].pixels[0, 0]) == (30, 120, 210, 255)


@pytest.mark.parametrize(
    "version, depth, color_mode, match",
    [
        (2, 8, 3, "PSB"),
        (1, 16, 3, "16-bit"),
        (1, 8, 4, "CMYK"),
    ],
)
def test_psd_rejects_unsupported_variants(tmp_path, version, depth, color_mode, match):
    path = tmp_path / "unsupported.psd"
    _write_psd(
        path,
        4,
        4,
        [],
        np.zeros((4, 4, 4), dtype=np.uint8),
        version=version,
        depth=depth,
        color_mode=color_mode,
        write_layers=False,
    )
    with pytest.raises(PsdImportError, match=match):
        load_psd_document(path)


def test_psd_rejects_bad_signature_and_truncated_file(tmp_path):
    bad = tmp_path / "bad.psd"
    bad.write_bytes(b"NOPE" + b"\x00" * 40)
    with pytest.raises(PsdImportError, match="8BPS"):
        load_psd_document(bad)

    good = tmp_path / "good.psd"
    _basic_psd(good)
    truncated = tmp_path / "truncated.psd"
    truncated.write_bytes(good.read_bytes()[:60])
    with pytest.raises(PsdImportError):
        load_psd_document(truncated)


def test_psd_rejects_empty_missing_or_oversized(tmp_path):
    empty = tmp_path / "empty.psd"
    empty.write_bytes(b"")
    with pytest.raises(PsdImportError, match="rỗng"):
        load_psd_document(empty)
    with pytest.raises(PsdImportError, match="Không tìm thấy"):
        load_psd_document(tmp_path / "missing.psd")

    huge = tmp_path / "huge.psd"
    header = (
        b"8BPS"
        + _u16(1)
        + b"\x00" * 6
        + _u16(4)
        + _u32(20000)
        + _u32(20001)
        + _u16(8)
        + _u16(3)
        + _u32(0)
        + _u32(0)
        + _u32(0)
    )
    huge.write_bytes(header)
    with pytest.raises(PsdImportError, match="megapixel"):
        load_psd_document(huge)


def test_psd_without_layers_or_composite_reports_error(tmp_path):
    path = tmp_path / "blank.psd"
    _write_psd(
        path,
        6,
        6,
        [],
        np.zeros((6, 6, 4), dtype=np.uint8),
        write_layers=False,
    )
    with pytest.raises(PsdImportError, match="không có ảnh hợp nhất"):
        load_psd_document(path)


def test_open_filter_includes_psd(tmp_path):
    assert "*.psd" in OPEN_FILTER
    assert "Photoshop" in OPEN_FILTER


def test_psd_opens_through_main_window(qapp, tmp_path):
    psd_path = tmp_path / "open.psd"
    _basic_psd(psd_path)
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.show()
    qapp.processEvents()

    window.open_paths([str(psd_path)])
    qapp.processEvents()

    assert window.tabs.count() == 1
    document = window.current_document
    assert document is not None
    assert document.file_path is None
    assert [layer.name for layer in document.layers] == ["Background", "Ẩn"]
    assert str(psd_path) in [path for path in store.data.recent_files]
    window.close()


def test_psd_open_error_shows_message(qapp, tmp_path, monkeypatch):
    bad = tmp_path / "bad.psd"
    bad.write_bytes(b"NOPE")
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    messages = []
    monkeypatch.setattr(
        "ui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: messages.append(args),
    )
    window.open_paths([str(bad)])
    assert window.tabs.count() == 0
    assert messages
    window.close()
