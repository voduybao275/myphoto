"""Đọc file Photoshop PSD thành Document của My Photo Studio.

Chỉ dùng đặc tả định dạng công khai của Adobe (PSD version 1): 8-bit, RGB hoặc
Grayscale, nén Raw/RLE/ZIP, layer pixel, nhóm layer, layer mask, layer hình khối
vector dạng chữ nhật/bo góc/ellipse, layer văn bản (khối ``TySh``) và ảnh hợp nhất.
Không dùng mã nguồn, logo hay tài nguyên bản quyền của Adobe.

Layer văn bản được giữ thành layer chữ chỉnh sửa với nội dung, font, cỡ, màu,
giãn chữ/dòng, căn lề và kiểu uốn; pixel gốc của Photoshop được dùng làm hình
hiển thị ban đầu. Những phần chưa thể dựng lại (smart object, layer điều chỉnh,
hình khối vector tự do, chữ dọc/trên đường dẫn) được bỏ qua hoặc giữ dạng pixel
và liệt kê trong báo cáo nhập; ảnh hợp nhất cuối file (nếu có) được thêm vào dưới
cùng và để ẩn để người dùng đối chiếu.
"""

from __future__ import annotations

import mmap
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.document import Document
from core.layer import Layer, LayerKind
from core.shape_layer import ShapeProperties
from core.text_layer import TextProperties, TextRun, font_line_height

MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_LAYER_RECORDS = 500
MAX_CHANNELS = 56
# Tổng pixel của các kênh layer + mask; giữ mức RAM an toàn cho máy 8 GB.
MAX_TOTAL_PIXELS = 250_000_000

COMPRESSION_RAW = 0
COMPRESSION_RLE = 1
COMPRESSION_ZIP = 2
COMPRESSION_ZIP_PREDICTION = 3

COLOR_MODE_GRAYSCALE = 1
COLOR_MODE_RGB = 3

SECTION_DIVIDER = 3
SECTION_FOLDER = (1, 2)

BLEND_MODE_KEYS: dict[bytes, str] = {
    b"norm": "normal",
    b"mul ": "multiply",
    b"scrn": "screen",
    b"over": "overlay",
    b"sLit": "soft_light",
    b"hLit": "hard_light",
    b"dark": "darken",
    b"lite": "lighten",
    b"div ": "color_dodge",
    b"idiv": "color_burn",
    b"diff": "difference",
    b"hue ": "hue",
    b"sat ": "saturation",
    b"colr": "color",
    b"lum ": "luminosity",
}

COLOR_LABELS = ("none", "red", "orange", "yellow", "green", "blue", "violet", "gray")

TEXT_TAGS = {b"TySh", b"TyLd", b"Txt2"}
SMART_TAGS = {b"SoLd", b"SoLE", b"PlLd", b"lnkD", b"lnk2", b"lnk3"}
VECTOR_TAGS = {b"vmsk", b"vsms", b"vstk", b"vscg", b"vogk"}
ADJUSTMENT_TAGS = {
    b"brit",
    b"levl",
    b"curv",
    b"blnc",
    b"hue ",
    b"hue2",
    b"blwh",
    b"phfl",
    b"mixr",
    b"clrL",
    b"nvrt",
    b"post",
    b"thrs",
    b"grdm",
    b"vibA",
    b"expA",
    b"selc",
    b"CgEd",
}


class PsdImportError(Exception):
    """Lỗi đọc file PSD với thông điệp thân thiện cho người dùng."""


@dataclass
class PsdImportReport:
    layers: int = 0
    groups: int = 0
    shapes: int = 0
    texts: int = 0
    skipped: list[str] = field(default_factory=list)
    blend_fallbacks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    composite_added: bool = False

    def has_issues(self) -> bool:
        return bool(
            self.skipped
            or self.blend_fallbacks
            or self.warnings
            or self.composite_added
        )

    def summary(self) -> str:
        lines: list[str] = []
        if self.layers or self.groups:
            lines.append(f"Đã nhập {self.layers} layer và {self.groups} nhóm.")
        if self.shapes:
            lines.append(
                f"{self.shapes} layer hình khối được giữ dạng vector để chỉnh sửa tiếp."
            )
        if self.texts:
            lines.append(
                f"{self.texts} layer văn bản được giữ dạng chữ chỉnh sửa tiếp."
            )
        if self.skipped:
            names = ", ".join(self.skipped[:8])
            if len(self.skipped) > 8:
                names += f"… (+{len(self.skipped) - 8})"
            lines.append(f"Bỏ qua {len(self.skipped)} layer chưa hỗ trợ: {names}.")
        if self.composite_added:
            lines.append(
                "Ảnh hợp nhất của PSD được thêm ở dưới cùng và đang ẩn "
                "để đối chiếu các layer chưa hỗ trợ."
            )
        if self.blend_fallbacks:
            lines.append(
                "Blend mode chưa hỗ trợ, đã chuyển về Normal: "
                + ", ".join(self.blend_fallbacks[:6])
                + ("…" if len(self.blend_fallbacks) > 6 else "")
                + "."
            )
        for warning in self.warnings[:4]:
            lines.append(warning)
        return "\n".join(lines)


@dataclass
class _Record:
    index: int
    name: str
    rect: tuple[int, int, int, int] | None
    channels: list[tuple[int, int]]
    blend_key: bytes
    opacity: int
    clipping: bool
    visible: bool
    locked: bool
    mask_rect: tuple[int, int, int, int] | None
    mask_default: int
    mask_flags: int
    section: int
    color_label: str
    tags: set[bytes]
    vogk: bytes | None = None
    tysh: bytes | None = None


@dataclass
class _Node:
    name: str
    kind: str
    record: _Record | None = None
    children: list["_Node"] = field(default_factory=list)


class _Cursor:
    def __init__(self, data, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def read(self, count: int) -> bytes:
        if count < 0:
            raise PsdImportError("File PSD chứa độ dài không hợp lệ.")
        end = self.pos + count
        if end > len(self.data):
            raise PsdImportError("File PSD bị hỏng hoặc thiếu dữ liệu.")
        value = self.data[self.pos:end]
        self.pos = end
        return value if isinstance(value, bytes) else bytes(value)

    def skip(self, count: int) -> None:
        self.read(count)

    def peek(self, count: int) -> bytes:
        value = self.data[self.pos : self.pos + count]
        return value if isinstance(value, bytes) else bytes(value)

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.read(2))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.read(4))[0]

    def remaining(self) -> int:
        return len(self.data) - self.pos


def _unpackbits(source: bytes, expected: int) -> bytes:
    if expected <= 0:
        return b""
    out = bytearray()
    index = 0
    size = len(source)
    while index < size and len(out) < expected:
        control = source[index]
        index += 1
        if control < 128:
            count = control + 1
            take = min(count, size - index, expected - len(out))
            out += source[index : index + take]
            index += count
            if take < count:
                break
        elif control > 128:
            count = 257 - control
            if index >= size:
                break
            out += bytes((source[index],)) * min(count, expected - len(out))
            index += 1
    if len(out) < expected:
        out += bytes(expected - len(out))
    return bytes(out[:expected])


def _decode_rle(payload: bytes, width: int, height: int) -> np.ndarray:
    table = height * 2
    if len(payload) < table:
        raise PsdImportError("Dữ liệu nén RLE của PSD bị thiếu bảng độ dài dòng.")
    counts = np.frombuffer(payload[:table], dtype=">u2").astype(np.int64)
    out = np.empty((height, width), dtype=np.uint8)
    offset = table
    for row in range(height):
        length = int(counts[row])
        end = offset + length
        if end > len(payload):
            raise PsdImportError("Dữ liệu nén RLE của PSD bị hỏng.")
        out[row] = np.frombuffer(_unpackbits(payload[offset:end], width), dtype=np.uint8)
        offset = end
    return out


def _decode_channel(
    cursor: _Cursor, length: int, width: int, height: int
) -> np.ndarray | None:
    start = cursor.pos
    end = start + length
    if length < 2:
        cursor.pos = end
        return None
    compression = cursor.u16()
    payload = cursor.read(end - cursor.pos)
    expected = width * height
    if compression == COMPRESSION_RAW:
        if len(payload) < expected:
            payload += bytes(expected - len(payload))
        return np.frombuffer(payload[:expected], dtype=np.uint8).reshape(height, width)
    if compression == COMPRESSION_RLE:
        return _decode_rle(payload, width, height)
    if compression == COMPRESSION_ZIP:
        try:
            raw = zlib.decompress(payload)
        except zlib.error as exc:
            raise PsdImportError("Dữ liệu nén ZIP trong PSD bị hỏng.") from exc
        if len(raw) < expected:
            raw += bytes(expected - len(raw))
        return np.frombuffer(raw[:expected], dtype=np.uint8).reshape(height, width)
    if compression == COMPRESSION_ZIP_PREDICTION:
        raise PsdImportError(
            "File PSD dùng nén ZIP có dự đoán (thường là 16/32-bit) nên chưa hỗ trợ."
        )
    raise PsdImportError(f"Kiểu nén kênh PSD chưa hỗ trợ ({compression}).")


def _read_pascal_name(cursor: _Cursor) -> str:
    length = cursor.u8()
    raw = cursor.read(length)
    padding = (4 - ((length + 1) % 4)) % 4
    cursor.skip(padding)
    return raw.decode("utf-8", "replace").strip("\x00")


def _read_unicode_name(data: bytes) -> str:
    if len(data) < 4:
        return ""
    count = struct.unpack(">I", data[:4])[0]
    raw = data[4 : 4 + min(count, (len(data) - 4) // 2) * 2]
    text = raw.decode("utf-16-be", "replace")
    return text.replace("\x00", "").strip()


# ------------------------------------------------------- shape vector (vogk)
class _DescriptorError(Exception):
    pass


class _Descriptor:
    """Descriptor PSD đã giải mã: classID + các cặp khoá/giá trị."""

    __slots__ = ("class_id", "items")

    def __init__(self, class_id: bytes, items: dict[bytes, object]) -> None:
        self.class_id = class_id
        self.items = items


def _read_descriptor_str(cursor: _Cursor) -> str:
    count = cursor.u32()
    if count > 1_000_000:
        raise _DescriptorError("Descriptor PSD có chuỗi quá dài.")
    return cursor.read(count * 2).decode("utf-16-be", "replace")


def _read_descriptor_id(cursor: _Cursor) -> bytes:
    length = cursor.u32()
    if length == 0:
        # Một số bản PSD ghi khoá/class 4 ký tự bằng độ dài 0 rồi 4 byte thô
        # thay vì độ dài 4 như đặc tả.
        return cursor.read(4)
    if length > 1024:
        raise _DescriptorError("Descriptor PSD có khoá quá dài.")
    return cursor.read(length)


def _read_descriptor_value(cursor: _Cursor, os_type: bytes) -> object:
    if os_type in (b"Objc", b"GlbO"):
        return _read_descriptor(cursor)
    if os_type in (b"VlLs", b"ObAr"):
        count = cursor.u32()
        if count > 100_000:
            raise _DescriptorError("Descriptor PSD có mảng quá lớn.")
        return [
            _read_descriptor_value(cursor, cursor.read(4)) for _ in range(count)
        ]
    if os_type == b"doub":
        return struct.unpack(">d", cursor.read(8))[0]
    if os_type == b"UntF":
        cursor.read(4)
        return struct.unpack(">d", cursor.read(8))[0]
    if os_type == b"UnFl":
        count = cursor.u32()
        if count > 100_000:
            raise _DescriptorError("Descriptor PSD có mảng số quá lớn.")
        return [struct.unpack(">d", cursor.read(8))[0] for _ in range(count)]
    if os_type == b"bool":
        return cursor.u8() != 0
    if os_type == b"long":
        return cursor.i32()
    if os_type == b"comp":
        return struct.unpack(">q", cursor.read(8))[0]
    if os_type == b"enum":
        return (_read_descriptor_id(cursor), _read_descriptor_id(cursor))
    if os_type == b"TEXT":
        return _read_descriptor_str(cursor)
    if os_type in (b"type", b"GlbC"):
        return _read_descriptor_id(cursor)
    if os_type in (b"tdta", b"alis"):
        length = cursor.u32()
        if length > len(cursor.data) - cursor.pos:
            raise _DescriptorError("Descriptor PSD bị hỏng.")
        return cursor.read(length)
    raise _DescriptorError(f"Descriptor PSD dùng kiểu dữ liệu chưa hỗ trợ: {os_type!r}")


def _read_descriptor(cursor: _Cursor) -> _Descriptor:
    _read_descriptor_str(cursor)
    class_id = _read_descriptor_id(cursor)
    count = cursor.u32()
    if count > 100_000:
        raise _DescriptorError("Descriptor PSD có quá nhiều mục.")
    items: dict[bytes, object] = {}
    for _ in range(count):
        key = _read_descriptor_id(cursor)
        os_type = cursor.read(4)
        items[key] = _read_descriptor_value(cursor, os_type)
    return _Descriptor(class_id, items)


def _descriptor_number(descriptor: _Descriptor, stem: bytes) -> float | None:
    for key, value in descriptor.items.items():
        if key.rstrip(b" ").lower() == stem and isinstance(value, (int, float)):
            if not isinstance(value, bool):
                return float(value)
    return None


def _descriptor_bool(descriptor: _Descriptor, key: bytes) -> bool | None:
    value = descriptor.items.get(key)
    return value if isinstance(value, bool) else None


def _descriptor_color(descriptor: _Descriptor) -> tuple[int, int, int, int] | None:
    red = _descriptor_number(descriptor, b"rd")
    green = _descriptor_number(descriptor, b"grn")
    blue = _descriptor_number(descriptor, b"bl")
    if red is None or green is None or blue is None:
        return None
    values = [red, green, blue]
    if max(values) <= 1.0:
        values = [value * 255.0 for value in values]
    return (
        max(0, min(255, round(values[0]))),
        max(0, min(255, round(values[1]))),
        max(0, min(255, round(values[2]))),
        255,
    )


def _find_descriptor_color(value: object) -> tuple[int, int, int, int] | None:
    if isinstance(value, _Descriptor):
        if b"clr" in {key.rstrip(b" ").lower() for key in value.items}:
            for key, item in value.items.items():
                if key.rstrip(b" ").lower() == b"clr" and isinstance(item, _Descriptor):
                    color = _descriptor_color(item)
                    if color is not None:
                        return color
        color = _descriptor_color(value)
        if color is not None:
            return color
        for item in value.items.values():
            color = _find_descriptor_color(item)
            if color is not None:
                return color
    elif isinstance(value, list):
        for item in value:
            color = _find_descriptor_color(item)
            if color is not None:
                return color
    return None


# ------------------------------------------------------- layer văn bản (TySh)
_FONT_SUFFIXES = ("psmt", "mt", "ps", "ms")
_ENGINE_NUMBER = re.compile(rb"[-+]?(?:\d+\.\d*|\.\d+|\d+)")
_ENGINE_WS = b" \t\r\n"
_MAX_ENGINE_BYTES = 8_000_000
_ENGINE_MAX_DEPTH = 32
_ENGINE_MAX_TOKENS = 500_000

WARP_STYLE_KEYS: dict[bytes, str] = {
    b"warpnone": "none",
    b"warparc": "arc",
    b"warparch": "arch",
    b"warpbulge": "bulge",
    b"warpsqueeze": "squeeze",
    b"warpwave": "wave",
    b"warpflag": "flag",
    b"warpfish": "fish",
    b"warprise": "rise",
    b"warptwist": "twist",
}

_font_family_cache: dict[str, str] | None = None


def _descriptor_lookup(descriptor: _Descriptor, stem: bytes) -> object | None:
    target = stem.rstrip(b" ").lower()
    for key, value in descriptor.items.items():
        if key.rstrip(b" ").lower() == target:
            return value
    return None


def _descriptor_bool_stem(descriptor: _Descriptor, stem: bytes) -> bool | None:
    value = _descriptor_lookup(descriptor, stem)
    return value if isinstance(value, bool) else None


def _descriptor_text_stem(descriptor: _Descriptor, stem: bytes) -> str:
    value = _descriptor_lookup(descriptor, stem)
    return value.strip() if isinstance(value, str) else ""


def _descriptor_enum(descriptor: _Descriptor, stem: bytes) -> bytes | None:
    value = _descriptor_lookup(descriptor, stem)
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], bytes):
        return value[1]
    return None


def _find_descriptor(
    value: object, stem: bytes, depth: int = 0
) -> _Descriptor | None:
    if depth > 8:
        return None
    if isinstance(value, _Descriptor):
        item = _descriptor_lookup(value, stem)
        if isinstance(item, _Descriptor):
            return item
        for child in value.items.values():
            found = _find_descriptor(child, stem, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_descriptor(child, stem, depth + 1)
            if found is not None:
                return found
    return None


def _find_enum(value: object, stem: bytes, depth: int = 0) -> bytes | None:
    if depth > 8:
        return None
    if isinstance(value, _Descriptor):
        found = _descriptor_enum(value, stem)
        if found is not None:
            return found
        for child in value.items.values():
            found = _find_enum(child, stem, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_enum(child, stem, depth + 1)
            if found is not None:
                return found
    return None


def _descriptor_text_color(value: object) -> tuple[int, int, int, int] | None:
    """Đọc màu FillColor của chữ từ descriptor RGB/Xám/CMYK/HSB."""
    if not isinstance(value, _Descriptor):
        return None
    red = _descriptor_number(value, b"rd")
    green = _descriptor_number(value, b"grn")
    blue = _descriptor_number(value, b"bl")
    alpha = _descriptor_number(value, b"a")
    if red is not None and green is not None and blue is not None:
        channels = [red, green, blue]
        if max(channels) <= 1.0:
            channels = [channel * 255.0 for channel in channels]
        rgb = tuple(max(0, min(255, round(channel))) for channel in channels)
    else:
        gray = _descriptor_number(value, b"gry")
        cyan = _descriptor_number(value, b"cyn")
        magenta = _descriptor_number(value, b"mgnt")
        yellow = _descriptor_number(value, b"ylw")
        black = _descriptor_number(value, b"blck")
        if gray is not None:
            level = gray * 255.0 if gray <= 1.0 else gray
            gray_level = max(0, min(255, round(level)))
            rgb = (gray_level, gray_level, gray_level)
        elif None not in (cyan, magenta, yellow, black):
            values = [cyan, magenta, yellow, black]
            if max(values) > 1.0:
                values = [channel / 100.0 for channel in values]
            c, m, y, k = (max(0.0, min(1.0, channel)) for channel in values)
            rgb = (
                round(255 * (1.0 - c) * (1.0 - k)),
                round(255 * (1.0 - m) * (1.0 - k)),
                round(255 * (1.0 - y) * (1.0 - k)),
            )
        else:
            hue = _descriptor_number(value, b"h")
            saturation = _descriptor_number(value, b"strt")
            brightness = _descriptor_number(value, b"brgh")
            if None in (hue, saturation, brightness):
                return None
            rgb = _hsv_to_rgb(hue, saturation, brightness)
    opacity = 255
    if alpha is not None:
        opacity = round(alpha * 255.0) if alpha <= 1.0 else round(alpha)
        opacity = max(0, min(255, int(opacity)))
    return (rgb[0], rgb[1], rgb[2], opacity)


def _hsv_to_rgb(
    hue: float, saturation: float, brightness: float
) -> tuple[int, int, int]:
    saturation = saturation / 100.0 if saturation > 1.0 else saturation
    brightness = brightness / 100.0 if brightness > 1.0 else brightness
    saturation = max(0.0, min(1.0, saturation))
    brightness = max(0.0, min(1.0, brightness))
    hue = hue % 360.0
    chroma = brightness * saturation
    sector = hue / 60.0
    second = chroma * (1.0 - abs(sector % 2.0 - 1.0))
    offset = brightness - chroma
    table = (
        (chroma, second, 0.0),
        (second, chroma, 0.0),
        (0.0, chroma, second),
        (0.0, second, chroma),
        (second, 0.0, chroma),
        (chroma, 0.0, second),
    )
    red, green, blue = table[int(sector) % 6]
    return (
        round((red + offset) * 255),
        round((green + offset) * 255),
        round((blue + offset) * 255),
    )


def _decode_engine_string(raw: bytes) -> str:
    raw = bytes(raw)
    if raw.startswith(b"\xfe\xff"):
        text = raw[2:].decode("utf-16-be", "replace")
    elif raw.startswith(b"\xff\xfe"):
        text = raw[2:].decode("utf-16-le", "replace")
    elif raw[:1] == b"\x00" and b"\x00" in raw[1:]:
        text = raw.decode("utf-16-be", "replace")
    else:
        for marker in (b"\xcb\x9b", b"\xcb\x87", b"\xcb\x88", b"\xc2\xb4"):
            if raw.startswith(marker):
                raw = raw[len(marker) :]
                break
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", "replace")
    text = text.strip("\x00")
    while text and (
        ord(text[0]) < 0x20 or (ord(text[0]) >= 0x80 and not text[0].isalnum())
    ):
        text = text[1:]
    return text.strip()


class _EngineDataParser:
    """Bộ đọc tối giản markup EngineData mà Photoshop dùng cho dữ liệu chữ."""

    def __init__(self, blob: bytes) -> None:
        self.blob = blob[:_MAX_ENGINE_BYTES]
        self.pos = 0
        self.tokens = 0

    def parse(self) -> dict | None:
        try:
            value = self._value(0)
        except (ValueError, RecursionError):
            return None
        return value if isinstance(value, dict) else None

    def _skip(self) -> None:
        blob = self.blob
        while self.pos < len(blob) and blob[self.pos] in _ENGINE_WS:
            self.pos += 1

    def _peek(self, marker: bytes) -> bool:
        return self.blob.startswith(marker, self.pos)

    def _value(self, depth: int):
        if depth > _ENGINE_MAX_DEPTH:
            raise ValueError("EngineData lồng quá sâu.")
        self.tokens += 1
        if self.tokens > _ENGINE_MAX_TOKENS:
            raise ValueError("EngineData quá lớn.")
        self._skip()
        blob = self.blob
        if self.pos >= len(blob):
            raise ValueError("EngineData bị cụt.")
        if self._peek(b"<<"):
            return self._dictionary(depth)
        if blob[self.pos] == 0x5B:  # '['
            return self._array(depth)
        if blob[self.pos] == 0x28:  # '('
            return self._string()
        if blob[self.pos] == 0x2F:  # '/'
            return self._name()
        if self._peek(b"true"):
            self.pos += 4
            return True
        if self._peek(b"false"):
            self.pos += 5
            return False
        match = _ENGINE_NUMBER.match(blob, self.pos)
        if match is not None:
            self.pos = match.end()
            token = match.group(0)
            return float(token) if b"." in token else int(token)
        return self._raw_token()

    def _raw_token(self) -> str:
        start = self.pos
        blob = self.blob
        delimiters = b" \t\r\n<>[]()"
        while self.pos < len(blob) and blob[self.pos] not in delimiters:
            self.pos += 1
        if self.pos == start:
            self.pos += 1
        return blob[start : self.pos].decode("latin-1", "replace")

    def _name(self) -> str:
        self.pos += 1
        start = self.pos
        blob = self.blob
        delimiters = b" \t\r\n<>[]()/"
        while self.pos < len(blob) and blob[self.pos] not in delimiters:
            self.pos += 1
        return blob[start : self.pos].decode("latin-1", "replace")

    def _string(self) -> str:
        self.pos += 1
        blob = self.blob
        out = bytearray()
        while self.pos < len(blob):
            char = blob[self.pos]
            self.pos += 1
            if char == 0x5C and self.pos < len(blob):  # dấu gạch chéo thoát
                out.append(blob[self.pos])
                self.pos += 1
                continue
            if char == 0x29:  # ')'
                break
            out.append(char)
        return _decode_engine_string(bytes(out))

    def _array(self, depth: int) -> list:
        self.pos += 1
        values: list = []
        while True:
            self._skip()
            if self.pos >= len(self.blob):
                raise ValueError("EngineData bị cụt.")
            if self.blob[self.pos] == 0x5D:  # ']'
                self.pos += 1
                return values
            values.append(self._value(depth + 1))

    def _dictionary(self, depth: int) -> dict:
        self.pos += 2
        values: dict[str, object] = {}
        while True:
            self._skip()
            if self.pos >= len(self.blob):
                raise ValueError("EngineData bị cụt.")
            if self._peek(b">>"):
                self.pos += 2
                return values
            if self.blob[self.pos] == 0x2F:  # '/'
                key = self._name()
                self._skip()
                if self._peek(b">>"):
                    values[key] = ""
                    continue
                values[key] = self._value(depth + 1)
            else:
                self._value(depth + 1)


def _engine_find(value: object, key: str, depth: int = 0) -> object | None:
    if depth > 12:
        return None
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _engine_find(child, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _engine_find(child, key, depth + 1)
            if found is not None:
                return found
    return None


def _engine_data_fonts(blob: bytes) -> list[str]:
    """Lấy danh sách font từ FontSet trong EngineData (nếu có)."""
    root = _EngineDataParser(blob).parse()
    if root is None:
        return []
    font_set = _engine_find(root, "FontSet")
    names: list[str] = []
    if isinstance(font_set, list):
        for item in font_set:
            if isinstance(item, dict):
                name = item.get("Name")
                if isinstance(name, str) and name.strip():
                    names.append(name)
            elif isinstance(item, str) and item.strip():
                names.append(item)
    return names


def _engine_data_text(blob: bytes) -> str:
    root = _EngineDataParser(blob).parse()
    if root is None:
        return ""
    editor = _engine_find(root, "Editor")
    if isinstance(editor, dict):
        text = editor.get("Text")
        if isinstance(text, str):
            return text
    text = _engine_find(root, "Text")
    return text if isinstance(text, str) else ""


def _engine_number(mapping: dict, key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _engine_color(value: object) -> tuple[int, int, int, int] | None:
    """Màu trong EngineData: Values theo thứ tự kênh alpha, đỏ, lục, lam."""
    if not isinstance(value, dict):
        return None
    kind = value.get("Type")
    values = value.get("Values")
    if not isinstance(values, list) or len(values) < 2:
        return None
    floats: list[float] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        floats.append(max(0.0, min(1.0, float(item))))
    if kind == 1 and len(floats) >= 4:
        alpha, red, green, blue = floats[:4]
        return (
            int(round(red * 255)),
            int(round(green * 255)),
            int(round(blue * 255)),
            int(round(alpha * 255)),
        )
    if kind == 1 and len(floats) == 3:
        red, green, blue = floats
        return (
            int(round(red * 255)),
            int(round(green * 255)),
            int(round(blue * 255)),
            255,
        )
    if kind == 0 and len(floats) >= 2:
        alpha, gray = floats[:2]
        level = int(round(gray * 255))
        return (level, level, level, int(round(alpha * 255)))
    return None


def _engine_style_data(
    style: dict, fonts: list[str], dpi: float
) -> _TextRunData:
    family = ""
    raw_font = ""
    font_index = _engine_number(style, "Font")
    if font_index is not None:
        index = int(round(font_index))
        if 0 <= index < len(fonts):
            raw_font = fonts[index]
            family = _clean_font_family(raw_font)
    size = _engine_number(style, "FontSize")
    # FontSize trong EngineData là pixel tài liệu; file 300 DPI ghi 200.0 cho
    # chữ cao ~190 px, nên không nhân thêm DPI như descriptor tính theo point.
    size_px = size if size is not None and size > 0 else 48.0
    hint = f"{raw_font} {family}".lower()
    bold = style.get("FauxBold") is True or "bold" in hint or "black" in hint
    italic = style.get("FauxItalic") is True or "italic" in hint or "oblique" in hint
    color = _engine_color(style.get("FillColor")) or (0, 0, 0, 255)
    tracking = _engine_number(style, "Tracking")
    auto_leading = style.get("AutoLeading") is True
    leading = _engine_number(style, "Leading")
    # EngineData ghi leading theo pixel hoặc theo bội cỡ chữ tuỳ bản Photoshop.
    if leading is not None and leading > 0:
        if leading < 4.0:
            leading = leading * size_px
        leading = leading * 72.0 / max(1.0, dpi)
    horizontal = _engine_number(style, "HorizontalScale")
    vertical = _engine_number(style, "VerticalScale")
    return _TextRunData(
        length=0,
        family=family,
        size=size_px,
        color=color,
        bold=bool(bold),
        italic=bool(italic),
        tracking=tracking or 0.0,
        leading=leading,
        auto_leading=auto_leading,
        underline=style.get("Underline") is True,
        strikeout=style.get("Strikethrough") is True,
        horizontal_scale=100.0 if horizontal is None else horizontal * 100.0,
        vertical_scale=100.0 if vertical is None else vertical * 100.0,
    )


def _engine_style_runs(
    blob: bytes, fonts: list[str], dpi: float
) -> list[_TextRunData]:
    """Đọc StyleRun từ EngineData (một số bản Photoshop không ghi StyleRun descriptor)."""
    root = _EngineDataParser(blob).parse()
    if root is None:
        return []
    style_run = _engine_find(root, "StyleRun")
    if not isinstance(style_run, dict):
        return []
    raw_runs = style_run.get("RunArray")
    default = style_run.get("DefaultRunData")
    entries: list[dict] = []
    if isinstance(raw_runs, list):
        entries = [item for item in raw_runs if isinstance(item, dict)]
    if not entries and isinstance(default, dict):
        entries = [default]
    styles: list[_TextRunData] = []
    for entry in entries:
        sheet = entry.get("StyleSheet")
        data = sheet.get("StyleSheetData") if isinstance(sheet, dict) else None
        if not isinstance(data, dict):
            data = entry.get("StyleSheetData")
        styles.append(
            _engine_style_data(data if isinstance(data, dict) else {}, fonts, dpi)
        )
    if not styles:
        return []
    raw_lengths = style_run.get("RunLengthArray")
    lengths: list[int] = []
    if isinstance(raw_lengths, list):
        lengths = [
            int(value)
            for value in raw_lengths
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0
        ]
    if len(lengths) == len(styles):
        for style, length in zip(styles, lengths):
            style.length = length
    else:
        styles[0].length = -1
    return styles


_ENGINE_JUSTIFICATION = {0: "left", 1: "right", 2: "center"}


def _engine_alignment(blob: bytes) -> tuple[str, bool] | None:
    root = _EngineDataParser(blob).parse()
    if root is None:
        return None
    paragraph_run = _engine_find(root, "ParagraphRun")
    if not isinstance(paragraph_run, dict):
        return None
    runs = paragraph_run.get("RunArray")
    entry = None
    if isinstance(runs, list) and runs and isinstance(runs[0], dict):
        entry = runs[0]
    elif isinstance(paragraph_run.get("DefaultRunData"), dict):
        entry = paragraph_run["DefaultRunData"]
    if entry is None:
        return None
    sheet = entry.get("ParagraphSheet")
    data = sheet.get("Properties") if isinstance(sheet, dict) else None
    if not isinstance(data, dict):
        return None
    justification = _engine_number(data, "Justification")
    if justification is None:
        return None
    code = int(round(justification))
    justified = code >= 3
    return _ENGINE_JUSTIFICATION.get(code, "left"), justified


def _installed_font_families() -> dict[str, str]:
    global _font_family_cache
    if _font_family_cache is None:
        try:
            from PySide6.QtGui import QFontDatabase

            _font_family_cache = {
                name.lower(): name for name in QFontDatabase.families()
            }
        except Exception:  # noqa: BLE001 - thiếu Qt vẫn đọc được tên font
            _font_family_cache = {}
    return _font_family_cache


def _spaced_font_name(value: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)


def _clean_font_family(postscript_name: str) -> str:
    """Đổi tên PostScript (ArialMT, TimesNewRomanPSMT…) về tên font hiển thị."""
    name = str(postscript_name).strip()
    if not name:
        return ""
    base = name.split("-", 1)[0].strip()
    candidates = [name, _spaced_font_name(name), base, _spaced_font_name(base)]
    stripped = base
    lowered = stripped.lower()
    for suffix in _FONT_SUFFIXES:
        if lowered.endswith(suffix) and len(stripped) > len(suffix) + 1:
            stripped = stripped[: -len(suffix)]
            candidates.extend([stripped, _spaced_font_name(stripped)])
            break
    families = _installed_font_families()
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in families:
            return families[key]
    return _spaced_font_name(stripped).strip() or base


@dataclass
class _TextRunData:
    length: int
    family: str
    size: float
    color: tuple[int, int, int, int]
    bold: bool
    italic: bool
    tracking: float
    leading: float | None
    auto_leading: bool
    underline: bool
    strikeout: bool
    horizontal_scale: float
    vertical_scale: float


@dataclass
class _TextImportResult:
    properties: TextProperties | None = None
    warnings: list[str] = field(default_factory=list)


def _parse_tysh(
    data: bytes,
) -> tuple[_Descriptor, tuple[float, ...], _Descriptor | None] | None:
    """Đọc khối TySh: version, transform 6 số, descriptor chữ, descriptor uốn."""
    if len(data) < 52:
        return None
    try:
        version = struct.unpack(">H", data[:2])[0]
        if not 1 <= version <= 8:
            return None
        transform = struct.unpack(">6d", data[2:50])
    except struct.error:
        return None
    # Photoshop đặt descriptor ngay sau trường phiên bản 16 (4 byte). Một số bản
    # ghi thiếu/thêm 4 byte trước descriptor nên thử vài vị trí và ưu tiên
    # descriptor có nội dung chữ.
    candidates: list[tuple[_Descriptor, _Cursor]] = []
    for offset in (56, 52, 60):
        if offset >= len(data):
            continue
        probe = _Cursor(data, offset)
        try:
            descriptor = _read_descriptor(probe)
        except (_DescriptorError, PsdImportError, struct.error, ValueError):
            continue
        candidates.append((descriptor, probe))
    if not candidates:
        return None
    descriptor, cursor = candidates[0]
    for candidate, probe in candidates:
        if b"Txt " in candidate.items or b"EngineData" in candidate.items:
            descriptor, cursor = candidate, probe
            break
    warp: _Descriptor | None = None
    try:
        if cursor.remaining() >= 6:
            cursor.u16()
            if cursor.u32() <= 1024:
                warp = _read_descriptor(cursor)
    except (_DescriptorError, PsdImportError, struct.error, ValueError):
        warp = None
    return descriptor, tuple(float(value) for value in transform), warp


def _style_descriptor(run: _Descriptor) -> _Descriptor:
    sheet = _descriptor_lookup(run, b"StyleSheet")
    if isinstance(sheet, _Descriptor):
        data = _descriptor_lookup(sheet, b"StyleSheetData")
        if isinstance(data, _Descriptor):
            return data
        return sheet
    data = _descriptor_lookup(run, b"StyleSheetData")
    return data if isinstance(data, _Descriptor) else run


def _style_from_run(
    run: _Descriptor, fonts: list[str], dpi: float
) -> _TextRunData:
    style = _style_descriptor(run)
    postscript = (
        _descriptor_text_stem(style, b"FontPostScriptName")
        or _descriptor_text_stem(style, b"FontName")
        or _descriptor_text_stem(style, b"FontFamilyName")
        or _descriptor_text_stem(style, b"FontFamily")
    )
    style_name = _descriptor_text_stem(style, b"FontStyleName")
    font_index = _descriptor_number(style, b"font")
    if not postscript and font_index is not None:
        index = int(round(font_index))
        if 0 <= index < len(fonts):
            postscript = fonts[index]
    hint = f"{postscript} {style_name}".lower()
    # FauxBold/FauxItalic chỉ đánh dấu kiểu giả lập; font thật như Arial-BoldMT
    # vẫn có đậm/ nghiêng nằm trong tên nên kết hợp cả hai nguồn.
    bold = _descriptor_bool_stem(style, b"fauxbold") is True
    bold = bold or "bold" in hint or "black" in hint or "heavy" in hint
    italic = _descriptor_bool_stem(style, b"fauxitalic") is True
    italic = italic or "italic" in hint or "oblique" in hint
    size_points = _descriptor_number(style, b"fontsize") or 0.0
    size_px = size_points * dpi / 72.0 if size_points > 0 else 48.0
    fill = _descriptor_lookup(style, b"fillcolor")
    color = _descriptor_text_color(fill) or (0, 0, 0, 255)
    horizontal = _descriptor_number(style, b"horizontalscale")
    vertical = _descriptor_number(style, b"verticalscale")
    return _TextRunData(
        length=0,
        family=_clean_font_family(postscript),
        size=size_px,
        color=color,
        bold=bool(bold),
        italic=bool(italic),
        tracking=_descriptor_number(style, b"tracking") or 0.0,
        leading=_descriptor_number(style, b"leading"),
        auto_leading=_descriptor_bool_stem(style, b"autoleading") is True,
        underline=_descriptor_bool_stem(style, b"underline") is True,
        strikeout=_descriptor_bool_stem(style, b"strikethrough") is True,
        horizontal_scale=100.0 if horizontal is None else horizontal,
        vertical_scale=100.0 if vertical is None else vertical,
    )


def _default_text_style() -> _TextRunData:
    return _TextRunData(
        length=0,
        family="",
        size=48.0,
        color=(0, 0, 0, 255),
        bold=False,
        italic=False,
        tracking=0.0,
        leading=None,
        auto_leading=True,
        underline=False,
        strikeout=False,
        horizontal_scale=100.0,
        vertical_scale=100.0,
    )


def _read_style_runs(
    root: _Descriptor, fonts: list[str], dpi: float
) -> list[_TextRunData]:
    style_run = _descriptor_lookup(root, b"StyleRun")
    if not isinstance(style_run, _Descriptor):
        style_run = _find_descriptor(root, b"stylerun")
    styles: list[_TextRunData] = []
    lengths: list[int] = []
    if isinstance(style_run, _Descriptor):
        raw_lengths = _descriptor_lookup(style_run, b"RunLengthArray")
        if isinstance(raw_lengths, list):
            lengths = [
                int(value)
                for value in raw_lengths
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            ]
        raw_runs = _descriptor_lookup(style_run, b"RunArray")
        if isinstance(raw_runs, list):
            styles = [
                _style_from_run(item, fonts, dpi)
                for item in raw_runs
                if isinstance(item, _Descriptor)
            ]
    if not styles:
        return []
    if len(lengths) == len(styles):
        for style, length in zip(styles, lengths):
            style.length = length
    else:
        styles[0].length = -1
    return styles


def _split_text_runs(
    text: str, styles: list[_TextRunData]
) -> list[tuple[str, _TextRunData]] | None:
    """Chia chuỗi theo RunLengthArray (đơn vị UTF-16 như PSD)."""
    if not styles or styles[0].length < 0:
        return None
    units = [len(char.encode("utf-16-be")) // 2 for char in text]
    boundaries: list[int] = []
    total = 0
    for style in styles:
        total += style.length
        boundaries.append(total)
    if total != sum(units):
        return None
    chunks: list[tuple[str, _TextRunData]] = []
    current: list[str] = []
    position = 0
    run_index = 0
    for char, unit in zip(text, units):
        if run_index >= len(boundaries):
            break
        if position + unit > boundaries[run_index]:
            return None
        current.append(char)
        position += unit
        if position == boundaries[run_index]:
            chunks.append(("".join(current), styles[run_index]))
            current = []
            run_index += 1
            while run_index < len(boundaries) and boundaries[run_index] == position:
                chunks.append(("", styles[run_index]))
                run_index += 1
    if current:
        if run_index >= len(boundaries):
            return None
        chunks.append(("".join(current), styles[run_index]))
    return chunks


def _line_spacing(style: _TextRunData, dpi: float) -> float:
    if style.auto_leading or style.leading is None or style.leading <= 0:
        return 1.0
    leading_px = style.leading * dpi / 72.0
    height = font_line_height(style.family, int(round(style.size)))
    return round(min(5.0, max(0.5, leading_px / max(1.0, height))), 2)


def _text_alignment(root: _Descriptor) -> tuple[str, bool]:
    token = (_find_enum(root, b"justification") or b"").lower()
    justified = b"justif" in token
    if b"center" in token or b"midd" in token:
        return "center", justified
    if b"right" in token:
        return "right", justified
    return "left", justified


def _text_warp(warp: _Descriptor | None) -> tuple[str, int, str | None]:
    if warp is None:
        return "none", 0, None
    token = (_descriptor_enum(warp, b"warpstyle") or b"").lower()
    bend = _descriptor_number(warp, b"warpvalue")
    if bend is None:
        bend = _descriptor_number(warp, b"warpbend")
    mapped = WARP_STYLE_KEYS.get(token)
    note = None
    if mapped is None and token not in (b"", b"warpnone"):
        label = token.decode("latin-1", "replace")
        note = f"kiểu uốn chữ '{label}' chưa hỗ trợ, đã bỏ uốn."
        mapped = "none"
    if mapped is None:
        mapped = "none"
    bend_value = int(round(max(-100.0, min(100.0, bend or 0.0))))
    if mapped == "none":
        bend_value = 0
    return mapped, bend_value, note


def _normalize_text(text: str) -> str:
    return (
        text.replace("\x00", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x03", "\n")
    )


def _build_text_properties(
    text: str,
    styles: list[_TextRunData],
    alignment: str,
    warp_style: str,
    warp_bend: int,
    dpi: float,
) -> TextProperties | None:
    chunks = _split_text_runs(text, styles)
    if chunks is None:
        chunks = [(text, styles[0])]
    runs: list[TextRun] = []
    for chunk, style in chunks:
        if not chunk:
            continue
        size = int(round(min(1000.0, max(1.0, style.size))))
        runs.append(
            TextRun(
                text=chunk,
                font_family=style.family,
                font_size=size,
                color=style.color,
                bold=style.bold,
                italic=style.italic,
            )
        )
    if not runs:
        return None
    first = styles[0]
    letter_spacing = int(round(first.tracking / 1000.0 * first.size))
    letter_spacing = max(-200, min(500, letter_spacing))
    try:
        return TextProperties(
            text=text,
            runs=tuple(runs),
            alignment=alignment,
            line_spacing=_line_spacing(first, dpi),
            letter_spacing=letter_spacing,
            warp_style=warp_style,
            warp_bend=warp_bend,
        )
    except (TypeError, ValueError):
        return None


def _read_text_layer(record: _Record, dpi: float) -> _TextImportResult:
    result = _TextImportResult()
    if record.tysh is None:
        result.warnings.append(
            f"Layer '{record.name}' là văn bản kiểu mới chưa hỗ trợ; giữ dạng pixel."
        )
        return result
    parsed = _parse_tysh(record.tysh)
    if parsed is None:
        result.warnings.append(
            f"Layer '{record.name}': không đọc được dữ liệu chữ; giữ dạng pixel."
        )
        return result
    root, transform, warp_descriptor = parsed
    engine = _descriptor_lookup(root, b"EngineData")
    fonts = _engine_data_fonts(engine) if isinstance(engine, bytes) else []
    raw_text = _descriptor_lookup(root, b"Txt")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raw_text = _engine_data_text(engine) if isinstance(engine, bytes) else ""
    text = _normalize_text(raw_text) if isinstance(raw_text, str) else ""
    if not text.strip():
        result.warnings.append(
            f"Layer '{record.name}': nội dung chữ rỗng; giữ dạng pixel."
        )
        return result
    orientation = _descriptor_enum(root, b"Ornt")
    if orientation is not None and orientation.lower().startswith(b"vrt"):
        result.warnings.append(
            f"Layer '{record.name}' là văn bản dọc; My Photo Studio chỉ hỗ trợ "
            "chữ ngang nên giữ dạng pixel."
        )
        return result

    styles = _read_style_runs(root, fonts, dpi)
    if not styles and isinstance(engine, bytes):
        styles = _engine_style_runs(engine, fonts, dpi)
    if not styles:
        styles = [_default_text_style()]
    alignment, justified = _text_alignment(root)
    if alignment == "left" and not justified and isinstance(engine, bytes):
        engine_alignment = _engine_alignment(engine)
        if engine_alignment is not None:
            alignment, justified = engine_alignment
    warp_style, warp_bend, warp_note = _text_warp(warp_descriptor)
    if justified:
        result.warnings.append(
            f"Layer '{record.name}': căn đều (justify) được chuyển thành căn trái."
        )
    if warp_note:
        result.warnings.append(f"Layer '{record.name}': {warp_note}")
    if any(style.underline or style.strikeout for style in styles):
        result.warnings.append(
            f"Layer '{record.name}': bỏ qua gạch chân/gạch ngang của chữ."
        )
    if any(
        abs(style.horizontal_scale - 100.0) > 0.5
        or abs(style.vertical_scale - 100.0) > 0.5
        for style in styles
    ):
        result.warnings.append(
            f"Layer '{record.name}' dùng co giãn chữ khác 100%; "
            "khi sửa chữ sẽ về tỉ lệ 100%."
        )
    xx, xy, yx, yy = transform[:4]
    if abs(xy) > 1e-4 or abs(yx) > 1e-4 or abs(xx - yy) > 1e-4 or abs(xx) < 1e-4:
        result.warnings.append(
            f"Layer '{record.name}' bị xoay/nghiêng; hình ban đầu giữ nguyên pixel, "
            "khi sửa chữ sẽ về hướng ngang."
        )
    properties = _build_text_properties(
        text, styles, alignment, warp_style, warp_bend, dpi
    )
    if properties is None:
        result.warnings.append(
            f"Layer '{record.name}': thuộc tính chữ không hợp lệ; giữ dạng pixel."
        )
        return result
    result.properties = properties
    return result


def _has_shape_bounds(descriptor: _Descriptor) -> bool:
    return (
        _descriptor_number(descriptor, b"top") is not None
        and _descriptor_number(descriptor, b"left") is not None
        and _descriptor_number(descriptor, b"btom") is not None
        and _descriptor_number(descriptor, b"rght") is not None
    )


@dataclass
class _VectorShape:
    kind: str
    left: float
    top: float
    right: float
    bottom: float
    radius: float
    stroke_width: int
    stroke_color: tuple[int, int, int, int]
    fill_enabled: bool | None = None


SHAPE_KEYS = (b"roundRect", b"ellipse", b"rect")


def _read_vogk_descriptor(vogk: bytes) -> _Descriptor | None:
    cursor = _Cursor(vogk)
    try:
        if cursor.u32() not in (1, 2):
            return None
    except PsdImportError:
        return None
    # Photoshop đặt descriptor ngay sau trường phiên bản; một số bản ghi thêm
    # một trường 4 byte (thường là 16) trước descriptor. Offset sai có thể vẫn
    # giải mã được một descriptor con, nên ưu tiên descriptor chứa hình học.
    candidates: list[_Descriptor] = []
    for offset in (4, 8):
        if offset >= len(vogk):
            continue
        probe = _Cursor(vogk, offset)
        try:
            candidates.append(_read_descriptor(probe))
        except (_DescriptorError, PsdImportError, struct.error, ValueError):
            continue
    for descriptor in candidates:
        if any(key in descriptor.items for key in SHAPE_KEYS):
            return descriptor
    return candidates[0] if candidates else None


def _parse_vector_shape(vogk: bytes) -> _VectorShape | None:
    """Đọc tagged block ``vogk`` của live shape; trả None nếu không hỗ trợ."""
    descriptor = _read_vogk_descriptor(vogk)
    if descriptor is None:
        return None

    geometry_key: bytes | None = None
    geometry: _Descriptor | None = None
    for key in SHAPE_KEYS:
        candidate = descriptor.items.get(key)
        if isinstance(candidate, _Descriptor) and _has_shape_bounds(candidate):
            geometry_key, geometry = key, candidate
            break
    if geometry is None:
        return None

    top = _descriptor_number(geometry, b"top")
    left = _descriptor_number(geometry, b"left")
    bottom = _descriptor_number(geometry, b"btom")
    right = _descriptor_number(geometry, b"rght")
    if None in (top, left, bottom, right):
        return None
    if right - left < 1.0 or bottom - top < 1.0:
        return None

    class_id = geometry.class_id.lower()
    if geometry_key == b"ellipse" or class_id.startswith(b"elip"):
        kind = "ellipse"
    elif geometry_key == b"roundRect" or class_id.startswith(b"rnd"):
        kind = "rounded_rectangle"
    else:
        kind = "rectangle"

    radius = 0.0
    for stem in (b"rad", b"rds", b"radius"):
        value = _descriptor_number(geometry, stem)
        if value is not None:
            radius = max(0.0, value)
            break
    if kind == "rounded_rectangle" and radius <= 0.0:
        kind = "rectangle"

    stroke_width = 0
    stroke_color = (0, 0, 0, 255)
    fill_enabled: bool | None = None
    style = descriptor.items.get(b"shapeStyle")
    if isinstance(style, _Descriptor):
        fill_enabled = _descriptor_bool(style, b"fillEnabled")
        enabled = _descriptor_bool(style, b"strokeEnabled")
        width = _descriptor_number(style, b"strokestylelinewidth")
        if enabled is not False and width is not None and width >= 1.0:
            color = _find_descriptor_color(
                style.items.get(b"strokeStyleContent", style)
            )
            if color is None:
                return None
            stroke_width = int(round(width))
            stroke_color = color

    return _VectorShape(
        kind=kind,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        radius=radius,
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        fill_enabled=fill_enabled,
    )


def _solid_shape_fill(
    channels: dict[int, np.ndarray], color_mode: int, inset: int = 0
) -> tuple[int, int, int, int] | None:
    """Lấy màu tô nếu pixel của layer là một màu đặc (không phải gradient)."""
    red = channels.get(0)
    if red is None:
        return None
    if color_mode == COLOR_MODE_RGB:
        green = channels.get(1, red)
        blue = channels.get(2, red)
    else:
        green = blue = red
    alpha = channels.get(-1)
    if 2 * inset < red.shape[0] and 2 * inset < red.shape[1]:
        trim = (slice(inset, red.shape[0] - inset), slice(inset, red.shape[1] - inset))
        red = red[trim]
        green = green[trim]
        blue = blue[trim]
        if alpha is not None:
            alpha = alpha[trim]
    mask = alpha >= 200 if alpha is not None else np.ones(red.shape, dtype=bool)
    total = int(mask.sum())
    if total == 0:
        return None
    ys, xs = np.nonzero(mask)
    stride = max(1, total // 100_000)
    ys = ys[::stride]
    xs = xs[::stride]
    pixels = np.stack((red[ys, xs], green[ys, xs], blue[ys, xs]), axis=1)
    colors, counts = np.unique(pixels, axis=0, return_counts=True)
    best = int(counts.argmax())
    if counts[best] / pixels.shape[0] < 0.96:
        return None
    value = colors[best]
    return (int(value[0]), int(value[1]), int(value[2]), 255)


MASK_CLASSIFY_LIMIT = 512
MISSING_CORNER_FACTOR = 4.0 - 3.141592653589793
SOLID_VECTOR_TAGS = {b"vmsk", b"vsms"}


def _mask_iou(observed: np.ndarray, model: np.ndarray) -> float:
    union = int(np.count_nonzero(observed | model))
    if union == 0:
        return 0.0
    return int(np.count_nonzero(observed & model)) / union


def _rounded_rect_mask(height: int, width: int, radius: float) -> np.ndarray:
    radius = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    xs = np.arange(width, dtype=np.float64) + 0.5
    ys = np.arange(height, dtype=np.float64) + 0.5
    dx = np.maximum(np.maximum(radius - xs, xs - (width - radius)), 0.0)[None, :]
    dy = np.maximum(np.maximum(radius - ys, ys - (height - radius)), 0.0)[:, None]
    return dx * dx + dy * dy <= radius * radius


def _ellipse_mask(height: int, width: int) -> np.ndarray:
    xs = (np.arange(width, dtype=np.float64) + 0.5) / (width / 2.0) - 1.0
    ys = (np.arange(height, dtype=np.float64) + 0.5) / (height / 2.0) - 1.0
    return xs[None, :] ** 2 + ys[:, None] ** 2 <= 1.0


def _classify_small_mask(mask: np.ndarray) -> tuple[str | None, float]:
    height, width = mask.shape
    if height < 3 or width < 3:
        return None, 0.0
    area = int(mask.sum())
    if area == 0 or area < 0.45 * height * width:
        return None, 0.0

    best_kind: str | None = None
    best_radius = 0.0
    best_score = 0.0

    rect = _rounded_rect_mask(height, width, 0.0)
    score = _mask_iou(mask, rect)
    if score >= 0.96:
        best_kind, best_radius, best_score = "rectangle", 0.0, score

    ellipse = _ellipse_mask(height, width)
    score = _mask_iou(mask, ellipse)
    if score > best_score + 0.01:
        best_kind, best_radius, best_score = "ellipse", 0.0, score

    missing = max(0.0, height * width - area)
    radius = (missing / MISSING_CORNER_FACTOR) ** 0.5
    if radius >= 3.0:
        radius = min(radius, min(width, height) / 2.0)
        rounded = _rounded_rect_mask(height, width, radius)
        score = _mask_iou(mask, rounded)
        if score > best_score + 0.005:
            best_kind, best_radius, best_score = "rounded_rectangle", radius, score

    if best_kind is None or best_score < 0.9:
        return None, 0.0
    return best_kind, best_radius


def _classify_shape_mask(mask: np.ndarray) -> tuple[str | None, float]:
    stride = max(1, max(mask.shape) // MASK_CLASSIFY_LIMIT)
    sample = mask[::stride, ::stride] if stride > 1 else mask
    kind, radius = _classify_small_mask(sample)
    if kind is None:
        return None, 0.0
    return kind, radius * stride


def _shape_from_raster(
    record: _Record, channels: dict[int, np.ndarray], color_mode: int
) -> tuple[ShapeProperties, int, int] | None:
    """Suy ra hình khối từ alpha mask của layer có vector mask (``vmsk``)."""
    if record.rect is None or not (record.tags & SOLID_VECTOR_TAGS):
        return None
    if record.tags & (TEXT_TAGS | SMART_TAGS | ADJUSTMENT_TAGS):
        return None
    alpha = channels.get(-1)
    if alpha is None:
        return None
    filled = alpha >= 128
    ys, xs = np.nonzero(filled)
    if len(ys) < 9:
        return None
    top, bottom = int(ys.min()), int(ys.max()) + 1
    left, right = int(xs.min()), int(xs.max()) + 1
    height, width = bottom - top, right - left
    if width < 3 or height < 3:
        return None
    kind, radius = _classify_shape_mask(filled[top:bottom, left:right])
    if kind is None:
        return None
    fill = _solid_shape_fill(channels, color_mode)
    if fill is None:
        return None
    try:
        properties = ShapeProperties(
            kind=kind,
            width=width,
            height=height,
            fill_color=fill,
            stroke_color=(0, 0, 0, 255),
            stroke_width=0,
            corner_radius=radius,
        )
    except ValueError:
        return None
    layer_top, layer_left = record.rect[0], record.rect[1]
    return properties, layer_left + left, layer_top + top


def _shape_from_vector(
    record: _Record,
    channels: dict[int, np.ndarray],
    color_mode: int,
    vector: _VectorShape,
) -> tuple[ShapeProperties, int, int] | None:
    fill = _solid_shape_fill(
        channels, color_mode, inset=vector.stroke_width + 2
    )
    if vector.fill_enabled is False:
        fill = None
    elif fill is None and vector.fill_enabled is True:
        return None
    if fill is None and vector.stroke_width == 0:
        return None
    left = int(round(vector.left))
    top = int(round(vector.top))
    width = int(round(vector.right - vector.left))
    height = int(round(vector.bottom - vector.top))
    if width < 1 or height < 1:
        return None
    stroke_width = min(
        vector.stroke_width,
        500,
        max(1, min(width, height) // 2),
    )
    if fill is None and stroke_width == 0:
        return None
    try:
        properties = ShapeProperties(
            kind=vector.kind,
            width=width,
            height=height,
            fill_color=fill,
            stroke_color=vector.stroke_color,
            stroke_width=stroke_width,
            corner_radius=vector.radius,
        )
    except ValueError:
        return None
    return properties, left, top


def _shape_from_record(
    record: _Record, channels: dict[int, np.ndarray], color_mode: int
) -> tuple[ShapeProperties, int, int] | None:
    """Chuyển layer live shape hoặc layer vector mask thành hình khối chỉnh sửa."""
    if record.rect is None:
        return None
    if record.vogk is not None:
        vector = _parse_vector_shape(record.vogk)
        if vector is not None:
            return _shape_from_vector(record, channels, color_mode, vector)
    return _shape_from_raster(record, channels, color_mode)


def _read_layer_record(cursor: _Cursor, index: int) -> _Record:
    top = cursor.i32()
    left = cursor.i32()
    bottom = cursor.i32()
    right = cursor.i32()
    width = right - left
    height = bottom - top
    if width < 0 or height < 0 or width > Document.MAX_DIMENSION or height > Document.MAX_DIMENSION:
        raise PsdImportError("Layer trong PSD có kích thước không hợp lệ.")
    rect = (top, left, bottom, right) if width > 0 and height > 0 else None

    channel_count = cursor.u16()
    if channel_count > MAX_CHANNELS:
        raise PsdImportError("Layer trong PSD có số kênh không hợp lệ.")
    channels = [(cursor.i16(), cursor.u32()) for _ in range(channel_count)]

    if cursor.read(4) != b"8BIM":
        raise PsdImportError("Layer trong PSD thiếu chữ ký blend mode '8BIM'.")
    blend_key = cursor.read(4)
    opacity = cursor.u8()
    clipping = cursor.u8() == 1
    flags = cursor.u8()
    cursor.skip(1)
    visible = (flags & 0x02) == 0
    locked = bool(flags & 0x01)

    extra_length = cursor.u32()
    extra_end = cursor.pos + extra_length
    if extra_end > len(cursor.data):
        raise PsdImportError("Phần mở rộng của layer PSD bị hỏng.")

    mask_rect: tuple[int, int, int, int] | None = None
    mask_default = 255
    mask_flags = 0
    if cursor.pos + 4 <= extra_end:
        mask_length = cursor.u32()
        mask_end = cursor.pos + mask_length
        if mask_end > extra_end:
            raise PsdImportError("Dữ liệu layer mask trong PSD bị hỏng.")
        if mask_length >= 18:
            m_top = cursor.i32()
            m_left = cursor.i32()
            m_bottom = cursor.i32()
            m_right = cursor.i32()
            mask_default = cursor.u8()
            mask_flags = cursor.u8()
            if mask_flags & 0x01 and rect is not None:
                m_top += top
                m_bottom += top
                m_left += left
                m_right += left
            if m_right > m_left and m_bottom > m_top:
                mask_rect = (m_top, m_left, m_bottom, m_right)
        cursor.pos = mask_end

    if cursor.pos + 4 <= extra_end:
        ranges_length = cursor.u32()
        cursor.skip(min(ranges_length, max(0, extra_end - cursor.pos)))

    name = ""
    if cursor.pos < extra_end:
        name = _read_pascal_name(cursor)

    tags: set[bytes] = set()
    unicode_name = ""
    section = 0
    color_label = "none"
    vogk_data: bytes | None = None
    tysh_data: bytes | None = None
    while cursor.pos + 12 <= extra_end:
        signature = cursor.read(4)
        if signature not in (b"8BIM", b"8B64"):
            break
        key = cursor.read(4)
        size = cursor.u32()
        if size > extra_end - cursor.pos:
            break
        data = cursor.read(size)
        tags.add(key)
        if key == b"luni":
            unicode_name = _read_unicode_name(data)
        elif key == b"lsct" and len(data) >= 4:
            section = struct.unpack(">I", data[:4])[0]
        elif key == b"lclr" and len(data) >= 2:
            index_value = int.from_bytes(data[: min(4, len(data))], "big")
            if 0 <= index_value < len(COLOR_LABELS):
                color_label = COLOR_LABELS[index_value]
        elif key == b"lspf" and any(data):
            locked = True
        elif key == b"vogk":
            vogk_data = data
        elif key == b"TySh":
            tysh_data = data
    cursor.pos = extra_end

    return _Record(
        index=index,
        name=unicode_name or name or f"Layer {index + 1}",
        rect=rect,
        channels=channels,
        blend_key=blend_key,
        opacity=opacity,
        clipping=clipping,
        visible=visible,
        locked=locked,
        mask_rect=mask_rect,
        mask_default=mask_default,
        mask_flags=mask_flags,
        section=section,
        color_label=color_label,
        tags=tags,
        vogk=vogk_data,
        tysh=tysh_data,
    )


def _channel_size(record: _Record, channel_id: int) -> tuple[int, int]:
    if channel_id == -2 and record.mask_rect is not None:
        top, left, bottom, right = record.mask_rect
    elif record.rect is not None:
        top, left, bottom, right = record.rect
    else:
        return 0, 0
    return right - left, bottom - top


def _read_layers(
    cursor: _Cursor, section_end: int
) -> tuple[list[_Record], list[dict[int, np.ndarray]], list[str]]:
    records: list[_Record] = []
    decoded: list[dict[int, np.ndarray]] = []
    warnings: list[str] = []
    if cursor.pos + 4 > section_end:
        return records, decoded, warnings

    layer_info_length = cursor.u32()
    info_end = cursor.pos + layer_info_length
    if info_end > section_end:
        raise PsdImportError("Phần thông tin layer của PSD bị hỏng.")
    if layer_info_length > 0:
        count = abs(cursor.i16())
        if count > MAX_LAYER_RECORDS:
            raise PsdImportError(
                f"PSD có {count} layer, vượt giới hạn an toàn {MAX_LAYER_RECORDS}."
            )
        records = [_read_layer_record(cursor, index) for index in range(count)]

        total_pixels = 0
        for record in records:
            channel_map: dict[int, np.ndarray] = {}
            for channel_id, length in record.channels:
                if length < 3:
                    cursor.skip(length)
                    continue
                width, height = _channel_size(record, channel_id)
                if width <= 0 or height <= 0:
                    cursor.skip(length)
                    continue
                total_pixels += width * height
                if total_pixels > MAX_TOTAL_PIXELS:
                    raise PsdImportError(
                        "PSD có tổng dung lượng pixel quá lớn để mở an toàn trên "
                        "máy 8 GB. Hãy thu nhỏ hoặc hợp nhất bớt layer trong Photoshop."
                    )
                pixels = _decode_channel(cursor, length, width, height)
                if pixels is not None:
                    channel_map[channel_id] = pixels
            decoded.append(channel_map)
        cursor.pos = info_end

    if (
        cursor.pos + 4 <= section_end
        and cursor.peek(4) not in (b"8BIM", b"8B64")
    ):
        global_mask_length = cursor.u32()
        cursor.skip(min(global_mask_length, max(0, section_end - cursor.pos)))

    while cursor.pos + 12 <= section_end:
        signature = cursor.read(4)
        if signature not in (b"8BIM", b"8B64"):
            break
        cursor.read(4)
        size = cursor.u32()
        if size > section_end - cursor.pos:
            break
        cursor.skip(size)
        pad = (4 - size % 4) % 4
        if pad and cursor.pos + pad <= section_end:
            cursor.skip(pad)
    cursor.pos = section_end
    return records, decoded, warnings


def _build_tree(records: list[_Record]) -> _Node:
    root = _Node(name="", kind="root")
    stack = [root]
    for record in records:
        if record.section == SECTION_DIVIDER:
            node = _Node(name=record.name, kind="group")
            stack[-1].children.append(node)
            stack.append(node)
        elif record.section in SECTION_FOLDER:
            if len(stack) > 1:
                node = stack.pop()
                node.record = record
                node.name = record.name
            else:
                stack[-1].children.append(
                    _Node(name=record.name, kind="group", record=record)
                )
        else:
            stack[-1].children.append(
                _Node(name=record.name, kind="layer", record=record)
            )
    return root


def _skip_reason(record: _Record) -> str:
    tags = record.tags
    if tags & TEXT_TAGS:
        return "layer văn bản"
    if tags & SMART_TAGS:
        return "smart object"
    if tags & VECTOR_TAGS:
        return "hình khối vector"
    if tags & ADJUSTMENT_TAGS:
        return "layer điều chỉnh"
    return "không có dữ liệu pixel"


def _apply_common(layer: Layer, record: _Record, report: PsdImportReport) -> None:
    layer.visible = record.visible
    layer.opacity = record.opacity / 255.0
    layer.locked = record.locked
    layer.color_label = record.color_label
    mode = BLEND_MODE_KEYS.get(record.blend_key)
    if mode is None:
        mode = "normal"
        report.blend_fallbacks.append(
            f"'{record.name}' ({record.blend_key.decode('latin-1', 'replace')})"
        )
    layer.blend_mode = mode


def _layer_rgba(
    record: _Record, channels: dict[int, np.ndarray], color_mode: int
) -> np.ndarray | None:
    if record.rect is None:
        return None
    top, left, bottom, right = record.rect
    width = right - left
    height = bottom - top
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    if color_mode == COLOR_MODE_RGB:
        for target, channel_id in enumerate((0, 1, 2)):
            plane = channels.get(channel_id)
            if plane is not None and plane.shape == (height, width):
                rgba[..., target] = plane
    else:
        plane = channels.get(0)
        if plane is not None and plane.shape == (height, width):
            rgba[..., 0] = plane
            rgba[..., 1] = plane
            rgba[..., 2] = plane
    alpha = channels.get(-1)
    if alpha is not None and alpha.shape == (height, width):
        rgba[..., 3] = alpha
    else:
        rgba[..., 3] = 255
    return rgba


def _place_mask(
    mask_rect: tuple[int, int, int, int],
    plane: np.ndarray,
    layer_rect: tuple[int, int, int, int],
    default: int,
    flags: int,
) -> np.ndarray:
    top, left, bottom, right = layer_rect
    height = bottom - top
    width = right - left
    canvas = np.full((height, width), 0 if default == 0 else 255, dtype=np.uint8)
    m_top, m_left, m_bottom, m_right = mask_rect
    src_y0 = max(0, top - m_top)
    src_x0 = max(0, left - m_left)
    dst_y0 = max(0, m_top - top)
    dst_x0 = max(0, m_left - left)
    copy_height = min(m_bottom - m_top - src_y0, height - dst_y0)
    copy_width = min(m_right - m_left - src_x0, width - dst_x0)
    if copy_height > 0 and copy_width > 0:
        canvas[dst_y0 : dst_y0 + copy_height, dst_x0 : dst_x0 + copy_width] = plane[
            src_y0 : src_y0 + copy_height, src_x0 : src_x0 + copy_width
        ]
    if flags & 0x04:
        canvas = 255 - canvas
    return canvas


def _group_mask(
    record: _Record | None,
    channels: dict[int, np.ndarray],
    canvas_width: int,
    canvas_height: int,
) -> np.ndarray | None:
    if record is None or record.mask_rect is None:
        return None
    plane = channels.get(-2)
    if plane is None:
        return None
    m_top, m_left, m_bottom, m_right = record.mask_rect
    mask_width = m_right - m_left
    mask_height = m_bottom - m_top
    if plane.shape != (mask_height, mask_width):
        return None
    canvas = np.full(
        (canvas_height, canvas_width),
        0 if record.mask_default == 0 else 255,
        dtype=np.uint8,
    )
    src_y0 = max(0, -m_top)
    src_x0 = max(0, -m_left)
    dst_y0 = max(0, m_top)
    dst_x0 = max(0, m_left)
    copy_height = min(mask_height - src_y0, canvas_height - dst_y0)
    copy_width = min(mask_width - src_x0, canvas_width - dst_x0)
    canvas[dst_y0 : dst_y0 + copy_height, dst_x0 : dst_x0 + copy_width] = plane[
        src_y0 : src_y0 + copy_height, src_x0 : src_x0 + copy_width
    ]
    if record.mask_flags & 0x04:
        canvas = 255 - canvas
    return canvas


def _materialize(
    node: _Node,
    parent_group_id: str | None,
    document: Document,
    decoded: list[dict[int, np.ndarray]],
    color_mode: int,
    report: PsdImportReport,
    dpi: float,
) -> None:
    for child in node.children:
        if child.kind == "group":
            record = child.record
            group = Layer(1, 1, name=child.name or "Group")
            group.kind = LayerKind.GROUP
            if record is not None:
                _apply_common(group, record, report)
                mask = _group_mask(
                    record, decoded[record.index], document.width, document.height
                )
                if mask is not None:
                    group.set_mask(mask)
                    group.mask_enabled = not bool(record.mask_flags & 0x02)
            _materialize(
                child, group.id, document, decoded, color_mode, report, dpi
            )
            group.group_id = parent_group_id
            document.add_layer(
                group, index=len(document.layers), select=False, record=False
            )
            report.groups += 1
            continue

        record = child.record
        if record is None:
            report.skipped.append(f"{child.name} (thiếu dữ liệu layer)")
            continue
        channels = decoded[record.index]
        if not any(channel_id in channels for channel_id in (0, 1, 2, -1)):
            report.skipped.append(f"{record.name} ({_skip_reason(record)})")
            continue
        top, left, bottom, right = record.rect if record.rect is not None else (0, 0, 0, 0)
        if record.tags & TEXT_TAGS:
            rgba = _layer_rgba(record, channels, color_mode)
            text_result = _read_text_layer(record, dpi)
            if rgba is not None and text_result.properties is not None:
                text_layer = Layer(right - left, bottom - top, name=record.name)
                text_layer.set_pixels(rgba)
                text_layer.kind = LayerKind.TEXT
                text_layer.text = text_result.properties
                text_layer.offset_x = left
                text_layer.offset_y = top
                text_layer.clipping = record.clipping
                _apply_common(text_layer, record, report)
                mask_plane = channels.get(-2)
                if record.mask_rect is not None and mask_plane is not None:
                    mask = _place_mask(
                        record.mask_rect,
                        mask_plane,
                        record.rect,
                        record.mask_default,
                        record.mask_flags,
                    )
                    text_layer.set_mask(mask)
                    text_layer.mask_enabled = not bool(record.mask_flags & 0x02)
                if b"lfx2" in record.tags or b"lrFX" in record.tags:
                    report.warnings.append(
                        f"Bỏ qua hiệu ứng layer (layer style) của '{record.name}'."
                    )
                if b"vmsk" in record.tags:
                    report.warnings.append(
                        f"Bỏ qua vector mask của layer '{record.name}'."
                    )
                text_layer.group_id = parent_group_id
                document.add_layer(
                    text_layer, index=len(document.layers), select=False, record=False
                )
                report.layers += 1
                report.texts += 1
                report.warnings.extend(text_result.warnings)
                continue
            if rgba is not None:
                report.warnings.extend(text_result.warnings)
        vector_shape = _shape_from_record(record, channels, color_mode)
        if vector_shape is not None:
            properties, shape_left, shape_top = vector_shape
            shape_layer = document.add_shape_layer(
                properties,
                x=shape_left,
                y=shape_top,
                name=record.name,
                index=len(document.layers),
                select=False,
                record=False,
            )
            shape_layer.clipping = record.clipping
            _apply_common(shape_layer, record, report)
            mask_plane = channels.get(-2)
            if record.mask_rect is not None and mask_plane is not None:
                shape_rect = (
                    shape_top,
                    shape_left,
                    shape_top + shape_layer.height,
                    shape_left + shape_layer.width,
                )
                mask = _place_mask(
                    record.mask_rect,
                    mask_plane,
                    shape_rect,
                    record.mask_default,
                    record.mask_flags,
                )
                shape_layer.set_mask(mask)
                shape_layer.mask_enabled = not bool(record.mask_flags & 0x02)
            if b"lfx2" in record.tags or b"lrFX" in record.tags:
                report.warnings.append(
                    f"Bỏ qua hiệu ứng layer (layer style) của '{record.name}'."
                )
            shape_layer.group_id = parent_group_id
            report.layers += 1
            report.shapes += 1
            continue
        rgba = _layer_rgba(record, channels, color_mode)
        if rgba is None:
            report.skipped.append(f"{record.name} ({_skip_reason(record)})")
            continue
        top, left, bottom, right = record.rect
        layer = Layer(right - left, bottom - top, name=record.name)
        layer.set_pixels(rgba)
        layer.offset_x = left
        layer.offset_y = top
        layer.clipping = record.clipping
        _apply_common(layer, record, report)
        mask_plane = channels.get(-2)
        if record.mask_rect is not None and mask_plane is not None:
            mask = _place_mask(
                record.mask_rect,
                mask_plane,
                record.rect,
                record.mask_default,
                record.mask_flags,
            )
            layer.set_mask(mask)
            layer.mask_enabled = not bool(record.mask_flags & 0x02)
        if b"lfx2" in record.tags or b"lrFX" in record.tags:
            report.warnings.append(
                f"Bỏ qua hiệu ứng layer (layer style) của '{record.name}'."
            )
        if b"vmsk" in record.tags:
            report.warnings.append(
                f"Bỏ qua vector mask của layer '{record.name}'."
            )
        layer.group_id = parent_group_id
        document.add_layer(
            layer, index=len(document.layers), select=False, record=False
        )
        report.layers += 1


def _read_composite_planes(
    cursor: _Cursor, width: int, height: int, channels: int, compression: int
) -> list[np.ndarray] | None:
    if compression == COMPRESSION_RAW:
        expected = width * height
        planes: list[np.ndarray] = []
        for _ in range(channels):
            if cursor.remaining() < expected:
                return None
            planes.append(
                np.frombuffer(cursor.read(expected), dtype=np.uint8).reshape(
                    height, width
                )
            )
        return planes
    if compression != COMPRESSION_RLE:
        return None

    start = cursor.pos
    # Đặc tả PSD: bảng độ dài RLE của toàn bộ dòng thuộc mọi kênh nằm liền nhau,
    # sau đó mới đến dữ liệu nén.
    if cursor.remaining() >= height * channels * 2:
        counts = np.frombuffer(
            cursor.read(height * channels * 2), dtype=">u2"
        ).astype(np.int64)
        if int(counts.sum()) <= cursor.remaining():
            planes = []
            complete = True
            for channel in range(channels):
                out = np.empty((height, width), dtype=np.uint8)
                for row in range(height):
                    length = int(counts[channel * height + row])
                    if length > cursor.remaining():
                        complete = False
                        break
                    out[row] = np.frombuffer(
                        _unpackbits(cursor.read(length), width), dtype=np.uint8
                    )
                if not complete:
                    break
                planes.append(out)
            if complete:
                return planes
    cursor.pos = start

    # Tương thích file cũ ghi bảng độ dài riêng cho từng kênh.
    planes = []
    for _ in range(channels):
        if cursor.remaining() < height * 2:
            return None
        counts = np.frombuffer(cursor.read(height * 2), dtype=">u2").astype(np.int64)
        if int(counts.sum()) > cursor.remaining():
            return None
        out = np.empty((height, width), dtype=np.uint8)
        for row in range(height):
            out[row] = np.frombuffer(
                _unpackbits(cursor.read(int(counts[row])), width), dtype=np.uint8
            )
        planes.append(out)
    return planes


def _read_composite(
    cursor: _Cursor, width: int, height: int, channels: int, color_mode: int
) -> np.ndarray | None:
    if cursor.remaining() < 2:
        return None
    compression = cursor.u16()
    planes = _read_composite_planes(cursor, width, height, channels, compression)
    if planes is None:
        return None

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    if color_mode == COLOR_MODE_RGB:
        for target in range(3):
            if target < len(planes):
                rgba[..., target] = planes[target]
        if channels >= 4:
            rgba[..., 3] = planes[3]
        else:
            rgba[..., 3] = 255
    else:
        rgba[..., 0] = planes[0]
        rgba[..., 1] = planes[0]
        rgba[..., 2] = planes[0]
        rgba[..., 3] = planes[1] if channels >= 2 else 255
    return rgba


def _read_dpi(cursor: _Cursor, length: int) -> float:
    end = cursor.pos + length
    if end > len(cursor.data):
        raise PsdImportError("Phần image resources của PSD bị hỏng.")
    dpi = 72.0
    while cursor.pos + 12 <= end:
        signature = cursor.read(4)
        if signature not in (b"8BIM", b"8B64"):
            break
        resource_id = cursor.u16()
        name_length = cursor.u8()
        cursor.skip(name_length)
        if (1 + name_length) % 2:
            cursor.skip(1)
        size = cursor.u32()
        if size > end - cursor.pos:
            break
        data = cursor.read(size)
        if size % 2 and cursor.pos < end:
            cursor.skip(1)
        if resource_id == 1005 and len(data) >= 16:
            h_res = struct.unpack(">i", data[0:4])[0] / 65536.0
            h_unit = struct.unpack(">H", data[4:6])[0]
            if h_unit == 1 and h_res > 0:
                dpi = h_res
            elif h_unit == 2 and h_res > 0:
                dpi = h_res * 2.54
    cursor.pos = end
    return dpi


def _load(
    cursor: _Cursor, source_name: str
) -> tuple[Document, PsdImportReport]:
    report = PsdImportReport()
    if cursor.read(4) != b"8BPS":
        raise PsdImportError("Không phải file PSD (thiếu chữ ký '8BPS').")
    version = cursor.u16()
    if version == 2:
        raise PsdImportError(
            "Đây là file PSB (Photoshop Large Document) chưa được hỗ trợ."
        )
    if version != 1:
        raise PsdImportError(f"Phiên bản PSD không hợp lệ ({version}).")
    cursor.skip(6)
    channels = cursor.u16()
    height = cursor.u32()
    width = cursor.u32()
    depth = cursor.u16()
    color_mode = cursor.u16()
    if not (1 <= channels <= MAX_CHANNELS):
        raise PsdImportError("File PSD có số kênh màu không hợp lệ.")
    if not (1 <= width <= Document.MAX_DIMENSION and 1 <= height <= Document.MAX_DIMENSION):
        raise PsdImportError("Kích thước ảnh trong PSD không hợp lệ.")
    if width * height > Document.MAX_PIXELS:
        raise PsdImportError("PSD vượt giới hạn an toàn 400 megapixel.")
    if depth != 8:
        raise PsdImportError(
            f"PSD {depth}-bit chưa được hỗ trợ; hiện chỉ đọc file 8-bit."
        )
    if color_mode not in (COLOR_MODE_GRAYSCALE, COLOR_MODE_RGB):
        names = {0: "Bitmap", 2: "Indexed", 4: "CMYK", 7: "Multichannel", 8: "Duotone", 9: "Lab"}
        raise PsdImportError(
            f"Chế độ màu {names.get(color_mode, color_mode)} chưa được hỗ trợ; "
            "hiện chỉ đọc PSD RGB hoặc Grayscale."
        )

    color_data_length = cursor.u32()
    cursor.skip(color_data_length)
    resources_length = cursor.u32()
    dpi = _read_dpi(cursor, resources_length)

    records: list[_Record] = []
    decoded: list[dict[int, np.ndarray]] = []
    if cursor.remaining() >= 4:
        layers_length = cursor.u32()
        section_end = cursor.pos + layers_length
        if section_end > len(cursor.data):
            raise PsdImportError("Phần layer của PSD bị hỏng.")
        records, decoded, _ = _read_layers(cursor, section_end)
        cursor.pos = section_end

    document = Document(width, height, dpi=dpi, name=source_name)
    root = _build_tree(records)
    _materialize(root, None, document, decoded, color_mode, report, dpi)

    composite = None
    try:
        composite = _read_composite(cursor, width, height, channels, color_mode)
    except PsdImportError as exc:
        report.warnings.append(f"Không đọc được ảnh hợp nhất của PSD: {exc}")

    composite_has_alpha = composite is not None and bool(np.any(composite[..., 3]))
    if report.layers == 0:
        if composite is None or not composite_has_alpha:
            raise PsdImportError(
                "PSD không có layer pixel nào đọc được và cũng không có ảnh hợp nhất."
            )
        layer = Layer(width, height, name="Ảnh PSD")
        layer.set_pixels(composite)
        document.add_layer(layer, index=0, select=True, record=False)
        report.layers = 1
        return document, report

    if report.skipped and composite_has_alpha:
        layer = Layer(width, height, name="Ảnh hợp nhất PSD")
        layer.set_pixels(composite)
        layer.visible = False
        document.add_layer(layer, index=0, select=False, record=False)
        report.composite_added = True

    if len(document.layers):
        document.set_active_layer(document.layers[-1])
    return document, report


def load_psd_document(path: str | Path) -> tuple[Document, PsdImportReport]:
    """Mở file .psd thành Document; trả kèm báo cáo những phần được/không được nhập."""
    file_path = Path(path)
    if not file_path.exists():
        raise PsdImportError(f"Không tìm thấy file:\n{file_path}")
    size = file_path.stat().st_size
    if size == 0:
        raise PsdImportError("File PSD rỗng, không thể mở.")
    if size > MAX_FILE_BYTES:
        raise PsdImportError("File PSD quá lớn (vượt 2 GB).")
    try:
        with open(file_path, "rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
                cursor = _Cursor(data)
                document, report = _load(cursor, file_path.stem)
    except OSError as exc:
        raise PsdImportError(f"Không thể đọc file PSD.\nChi tiết: {exc}") from exc
    document.mark_clean()
    return document, report
