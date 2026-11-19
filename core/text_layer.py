"""Mô hình và bộ render cho layer văn bản.

Nội dung văn bản được chia thành các ``TextRun`` — mỗi đoạn có font, cỡ chữ, màu,
đậm/nghiêng riêng. ``TextProperties`` giữ danh sách run cùng căn lề, giãn dòng/chữ,
kerning thủ công theo cặp ký tự, kiểu uốn chữ và kiểu đặt chữ trên đường dẫn. Khi
tạo hoặc sửa văn bản, nội dung được render thành mảng RGBA bằng QPainter, sau đó
(nếu có uốn) biến đổi điểm ảnh bằng phép lấy mẫu song tuyến để layer hoạt động như
mọi layer pixel khác (composite, mask, di chuyển, lưu dự án).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter

ALIGNMENTS = {"left", "center", "right"}
ALIGNMENT_LABELS = {
    "left": "Trái",
    "center": "Giữa",
    "right": "Phải",
}
MAX_TEXT_LENGTH = 10_000
MAX_LINES = 500
MAX_FONT_SIZE = 1_000
MIN_LINE_SPACING = 0.5
MAX_LINE_SPACING = 5.0
MIN_LETTER_SPACING = -200
MAX_LETTER_SPACING = 500
MIN_WARP_BEND = -100
MAX_WARP_BEND = 100
MIN_KERNING = -200
MAX_KERNING = 200
MAX_KERNING_PAIRS = 200
MIN_PATH_BEND = -100
MAX_PATH_BEND = 100
PATH_STYLES = ("none", "arc", "circle", "wave", "s_curve")
PATH_LABELS = {
    "none": "Không",
    "arc": "Cung tròn",
    "circle": "Vòng tròn",
    "wave": "Lượn sóng",
    "s_curve": "Chữ S",
}
WARP_STYLES = (
    "none",
    "arc",
    "arch",
    "bulge",
    "squeeze",
    "wave",
    "flag",
    "fish",
    "rise",
    "twist",
)
WARP_LABELS = {
    "none": "Không uốn",
    "arc": "Cung tròn",
    "arch": "Vòm",
    "bulge": "Phồng",
    "squeeze": "Ép dọc",
    "wave": "Lượn sóng",
    "flag": "Cờ",
    "fish": "Đuôi cá",
    "rise": "Dốc",
    "twist": "Xoắn",
}
MAX_RENDER_PIXELS = 64_000_000  # ~64 MP, tránh render văn bản làm cạn RAM
MAX_WARP_PIXELS = 24_000_000  # ảnh trung gian khi uốn/đặt chữ, giữ RAM an toàn


def parse_kerning_pairs(value: str) -> tuple[tuple[str, int], ...]:
    """Đọc chuỗi ``AV=-4, To=2`` thành các cặp kerning thủ công."""
    text = str(value).strip()
    if not text:
        return ()
    pairs: list[tuple[str, int]] = []
    for entry in text.replace(";", ",").replace("\n", ",").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValueError(f'Cặp kerning "{entry}" phải có dạng AB=giá trị.')
        key, raw = entry.split("=", 1)
        key = key.strip()
        if len(key) != 2 or "\n" in key or "\r" in key:
            raise ValueError(f'Cặp kerning "{key}" phải gồm đúng 2 ký tự.')
        try:
            amount = int(raw.strip())
        except ValueError as exc:
            raise ValueError(f'Giá trị kerning của "{key}" không hợp lệ.') from exc
        if not (MIN_KERNING <= amount <= MAX_KERNING):
            raise ValueError(
                f'Kerning của "{key}" phải trong khoảng '
                f"{MIN_KERNING}..{MAX_KERNING} px."
            )
        pairs.append((key, amount))
    if len(pairs) > MAX_KERNING_PAIRS:
        raise ValueError(f"Chỉ hỗ trợ tối đa {MAX_KERNING_PAIRS} cặp kerning.")
    return tuple(pairs)


def format_kerning_pairs(pairs: tuple[tuple[str, int], ...]) -> str:
    """Chuyển các cặp kerning thành chuỗi để hiển thị trong hộp thoại."""
    return ", ".join(f"{key}={amount}" for key, amount in pairs)


@dataclass(frozen=True)
class TextRun:
    """Một đoạn văn bản liền mạch dùng chung một kiểu định dạng."""
    text: str
    font_family: str = ""
    font_size: int = 48
    color: tuple[int, int, int, int] = (255, 255, 255, 255)
    bold: bool = False
    italic: bool = False

    def __post_init__(self) -> None:
        text = str(self.text)
        family = str(self.font_family).strip()
        try:
            size = int(self.font_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("Cỡ chữ không hợp lệ.") from exc
        if not (1 <= size <= MAX_FONT_SIZE):
            raise ValueError(f"Cỡ chữ phải trong khoảng 1..{MAX_FONT_SIZE} px.")
        channels = tuple(int(value) for value in self.color)
        if len(channels) != 4 or any(not 0 <= value <= 255 for value in channels):
            raise ValueError("Màu văn bản phải là RGBA trong khoảng 0..255.")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "font_family", family)
        object.__setattr__(self, "font_size", size)
        object.__setattr__(self, "color", channels)
        object.__setattr__(self, "bold", bool(self.bold))
        object.__setattr__(self, "italic", bool(self.italic))

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "color": list(self.color),
            "bold": self.bold,
            "italic": self.italic,
        }

    @classmethod
    def from_dict(cls, data: object) -> "TextRun":
        if not isinstance(data, dict):
            raise ValueError("Đoạn văn bản không hợp lệ.")
        try:
            return cls(
                text=str(data.get("text", "")),
                font_family=str(data.get("font_family", "")),
                font_size=int(data.get("font_size", 48)),
                color=tuple(data.get("color", (255, 255, 255, 255))),  # type: ignore[arg-type]
                bold=bool(data.get("bold", False)),
                italic=bool(data.get("italic", False)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thuộc tính đoạn văn bản không hợp lệ: {exc}") from exc


def _run_style(run: TextRun) -> tuple[object, ...]:
    return (run.font_family, run.font_size, run.color, run.bold, run.italic)


def _merge_runs(runs: tuple[TextRun, ...]) -> tuple[TextRun, ...]:
    """Gộp các đoạn liền kề cùng kiểu để dữ liệu ổn định sau khi sửa."""
    merged: list[TextRun] = []
    for run in runs:
        if not run.text:
            continue
        if merged and _run_style(merged[-1]) == _run_style(run):
            previous = merged[-1]
            merged[-1] = TextRun(
                text=previous.text + run.text,
                font_family=previous.font_family,
                font_size=previous.font_size,
                color=previous.color,
                bold=previous.bold,
                italic=previous.italic,
            )
        else:
            merged.append(run)
    return tuple(merged)


@dataclass(frozen=True)
class TextProperties:
    """Thuộc tính của một layer văn bản (bất biến để chia sẻ an toàn với history)."""

    text: str = ""
    font_family: str = ""
    font_size: int = 48
    color: tuple[int, int, int, int] = (255, 255, 255, 255)
    bold: bool = False
    italic: bool = False
    alignment: str = "left"
    line_spacing: float = 1.0
    letter_spacing: int = 0
    runs: tuple[TextRun, ...] = ()
    warp_style: str = "none"
    warp_bend: int = 0
    kerning_pairs: tuple[tuple[str, int], ...] = ()
    path_style: str = "none"
    path_bend: int = 0

    def __post_init__(self) -> None:
        text = str(self.text)
        family = str(self.font_family).strip()
        try:
            size = int(self.font_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("Cỡ chữ không hợp lệ.") from exc
        if not (1 <= size <= MAX_FONT_SIZE):
            raise ValueError(f"Cỡ chữ phải trong khoảng 1..{MAX_FONT_SIZE} px.")
        channels = tuple(int(value) for value in self.color)
        if len(channels) != 4 or any(not 0 <= value <= 255 for value in channels):
            raise ValueError("Màu văn bản phải là RGBA trong khoảng 0..255.")
        alignment = str(self.alignment).lower()
        if alignment not in ALIGNMENTS:
            raise ValueError(f"Căn lề không hợp lệ: {self.alignment}")
        try:
            line_spacing = float(self.line_spacing)
        except (TypeError, ValueError) as exc:
            raise ValueError("Giãn dòng không hợp lệ.") from exc
        if not math.isfinite(line_spacing) or not (
            MIN_LINE_SPACING <= line_spacing <= MAX_LINE_SPACING
        ):
            raise ValueError(
                f"Giãn dòng phải trong khoảng {MIN_LINE_SPACING:g}.."
                f"{MAX_LINE_SPACING:g} lần."
            )
        try:
            letter_spacing = int(round(float(self.letter_spacing)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Giãn chữ không hợp lệ.") from exc
        if not (MIN_LETTER_SPACING <= letter_spacing <= MAX_LETTER_SPACING):
            raise ValueError(
                f"Giãn chữ phải trong khoảng {MIN_LETTER_SPACING}.."
                f"{MAX_LETTER_SPACING} px."
            )
        warp_style = str(self.warp_style).strip().lower()
        if warp_style not in WARP_STYLES:
            raise ValueError(f"Kiểu uốn chữ không hợp lệ: {self.warp_style}")
        try:
            warp_bend = int(round(float(self.warp_bend)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Độ uốn chữ không hợp lệ.") from exc
        if not (MIN_WARP_BEND <= warp_bend <= MAX_WARP_BEND):
            raise ValueError(
                f"Độ uốn chữ phải trong khoảng {MIN_WARP_BEND}..{MAX_WARP_BEND}%."
            )
        if warp_style == "none":
            warp_bend = 0
        raw_pairs = tuple(self.kerning_pairs or ())
        if len(raw_pairs) > MAX_KERNING_PAIRS:
            raise ValueError(f"Chỉ hỗ trợ tối đa {MAX_KERNING_PAIRS} cặp kerning.")
        normalized_pairs: dict[str, int] = {}
        for item in raw_pairs:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError("Mỗi cặp kerning phải gồm 2 ký tự và một giá trị.")
            key = str(item[0])
            if len(key) != 2 or "\n" in key or "\r" in key:
                raise ValueError(
                    f'Cặp kerning "{key}" phải gồm đúng 2 ký tự.'
                )
            try:
                amount = int(round(float(item[1])))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f'Giá trị kerning của "{key}" không hợp lệ.'
                ) from exc
            if not (MIN_KERNING <= amount <= MAX_KERNING):
                raise ValueError(
                    f'Kerning của "{key}" phải trong khoảng '
                    f"{MIN_KERNING}..{MAX_KERNING} px."
                )
            if amount:
                normalized_pairs[key] = amount
        kerning_pairs = tuple(normalized_pairs.items())
        path_style = str(self.path_style).strip().lower()
        if path_style not in PATH_STYLES:
            raise ValueError(f"Kiểu chữ trên đường dẫn không hợp lệ: {self.path_style}")
        try:
            path_bend = int(round(float(self.path_bend)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Độ cong đường dẫn không hợp lệ.") from exc
        if not (MIN_PATH_BEND <= path_bend <= MAX_PATH_BEND):
            raise ValueError(
                f"Độ cong đường dẫn phải trong khoảng "
                f"{MIN_PATH_BEND}..{MAX_PATH_BEND}%."
            )
        if path_style == "none":
            path_bend = 0
        runs = tuple(self.runs)
        if runs:
            if not all(isinstance(run, TextRun) for run in runs):
                raise TypeError("Mỗi đoạn văn bản phải là TextRun.")
            text = "".join(run.text for run in runs)
        else:
            runs = (
                TextRun(
                    text=text,
                    font_family=family,
                    font_size=size,
                    color=channels,
                    bold=bool(self.bold),
                    italic=bool(self.italic),
                ),
            )
        if not text.strip():
            raise ValueError("Nội dung văn bản không được để trống.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Văn bản quá dài (tối đa {MAX_TEXT_LENGTH} ký tự).")
        if len(text.split("\n")) > MAX_LINES:
            raise ValueError(f"Văn bản có quá nhiều dòng (tối đa {MAX_LINES}).")
        runs = _merge_runs(runs)
        first = runs[0]
        family = first.font_family
        size = first.font_size
        channels = first.color
        bold = first.bold
        italic = first.italic
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "font_family", family)
        object.__setattr__(self, "font_size", size)
        object.__setattr__(self, "color", channels)
        object.__setattr__(self, "bold", bold)
        object.__setattr__(self, "italic", italic)
        object.__setattr__(self, "alignment", alignment)
        object.__setattr__(self, "line_spacing", round(line_spacing, 2))
        object.__setattr__(self, "letter_spacing", letter_spacing)
        object.__setattr__(self, "runs", runs)
        object.__setattr__(self, "warp_style", warp_style)
        object.__setattr__(self, "warp_bend", warp_bend)
        object.__setattr__(self, "kerning_pairs", kerning_pairs)
        object.__setattr__(self, "path_style", path_style)
        object.__setattr__(self, "path_bend", path_bend)

    @property
    def default_name(self) -> str:
        for line in self.text.split("\n"):
            cleaned = line.strip()
            if cleaned:
                return cleaned[:40]
        return "Văn bản"

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "color": list(self.color),
            "bold": self.bold,
            "italic": self.italic,
            "alignment": self.alignment,
            "line_spacing": self.line_spacing,
            "letter_spacing": self.letter_spacing,
            "runs": [run.to_dict() for run in self.runs],
            "warp_style": self.warp_style,
            "warp_bend": self.warp_bend,
            "kerning_pairs": [
                [key, amount] for key, amount in self.kerning_pairs
            ],
            "path_style": self.path_style,
            "path_bend": self.path_bend,
        }

    @classmethod
    def from_dict(cls, data: object) -> "TextProperties":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu văn bản không hợp lệ.")
        try:
            runs_data = data.get("runs")
            runs: tuple[TextRun, ...] = ()
            if runs_data is not None:
                if not isinstance(runs_data, list):
                    raise ValueError("Danh sách đoạn văn bản không hợp lệ.")
                runs = tuple(TextRun.from_dict(item) for item in runs_data)
            pairs_data = data.get("kerning_pairs", ())
            if pairs_data is None:
                pairs_data = ()
            elif isinstance(pairs_data, dict):
                pairs_data = list(pairs_data.items())
            elif not isinstance(pairs_data, (list, tuple)):
                raise ValueError("Danh sách cặp kerning không hợp lệ.")
            return cls(
                text=str(data.get("text", "")),
                font_family=str(data.get("font_family", "")),
                font_size=int(data.get("font_size", 48)),
                color=tuple(data.get("color", (255, 255, 255, 255))),  # type: ignore[arg-type]
                bold=bool(data.get("bold", False)),
                italic=bool(data.get("italic", False)),
                alignment=str(data.get("alignment", "left")),
                line_spacing=float(data.get("line_spacing", 1.0)),
                letter_spacing=int(data.get("letter_spacing", 0)),
                runs=runs,
                warp_style=str(data.get("warp_style", "none")),
                warp_bend=int(data.get("warp_bend", 0)),
                kerning_pairs=tuple(pairs_data) if pairs_data else (),
                path_style=str(data.get("path_style", "none")),
                path_bend=int(data.get("path_bend", 0)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thuộc tính văn bản không hợp lệ: {exc}") from exc


def _absolute_spacing() -> object:
    spacing_type = getattr(QFont, "SpacingType", None)
    if spacing_type is not None:
        return spacing_type.AbsoluteSpacing
    return QFont.AbsoluteSpacing  # pragma: no cover - Qt 5.14 trở xuống


def _make_font(run: TextRun, letter_spacing: int = 0) -> QFont:
    font = QFont()
    if run.font_family:
        font.setFamily(run.font_family)
    font.setPixelSize(max(1, int(round(run.font_size))))
    font.setBold(run.bold)
    font.setItalic(run.italic)
    if letter_spacing:
        font.setLetterSpacing(_absolute_spacing(), float(letter_spacing))
    return font


@dataclass(frozen=True)
class _Segment:
    font: QFont
    text: str
    color: tuple[int, int, int, int]
    advance: float


@dataclass(frozen=True)
class _Glyph:
    font: QFont
    text: str
    color: tuple[int, int, int, int]
    advance: float
    x: float


@dataclass(frozen=True)
class _LineLayout:
    segments: list[_Segment]
    width: float
    height: float
    ascent: float
    glyphs: list[_Glyph]


@dataclass(frozen=True)
class _TextLayout:
    lines: list[_LineLayout]
    content_width: float
    padding: int
    width: int
    height: int
    line_spacing: float


def _split_lines(properties: TextProperties) -> list[list[tuple[TextRun, str]]]:
    lines: list[list[tuple[TextRun, str]]] = [[]]
    for run in properties.runs:
        parts = run.text.split("\n")
        for index, part in enumerate(parts):
            if index:
                lines.append([])
            if part:
                lines[-1].append((run, part))
    return lines


def _layout_line(
    segments_data: list[tuple[TextRun, str]],
    base_run: TextRun,
    letter_spacing: int,
    kerning_pairs: dict[str, int] | None = None,
    per_glyph: bool = False,
) -> _LineLayout:
    if per_glyph:
        glyphs: list[_Glyph] = []
        x = 0.0
        previous = ""
        height = 0.0
        ascent = 0.0
        kerning = kerning_pairs or {}
        for run, text in segments_data:
            font = _make_font(run)
            metrics = QFontMetricsF(font)
            height = max(height, float(metrics.lineSpacing()))
            ascent = max(ascent, float(metrics.ascent()))
            for char in text:
                if previous:
                    x += kerning.get(previous + char, 0)
                advance = float(metrics.horizontalAdvance(char))
                glyphs.append(_Glyph(font, char, run.color, advance, x))
                x += advance + letter_spacing
                previous = char
        if glyphs:
            width = max(0.0, x - letter_spacing)
        else:
            metrics = QFontMetricsF(_make_font(base_run, letter_spacing))
            width = 0.0
            height = float(metrics.lineSpacing())
            ascent = float(metrics.ascent())
        return _LineLayout(
            segments=[],
            width=width,
            height=height,
            ascent=ascent,
            glyphs=glyphs,
        )

    segments: list[_Segment] = []
    total_advance = 0.0
    height = 0.0
    ascent = 0.0
    for run, text in segments_data:
        font = _make_font(run, letter_spacing)
        metrics = QFontMetricsF(font)
        advance = float(metrics.horizontalAdvance(text))
        segments.append(_Segment(font, text, run.color, advance))
        total_advance += advance
        height = max(height, float(metrics.lineSpacing()))
        ascent = max(ascent, float(metrics.ascent()))
    if segments:
        # Qt cộng giãn chữ cả sau ký tự cuối; bỏ phần đó để căn lề theo mực in.
        width = max(0.0, total_advance - letter_spacing)
    else:
        metrics = QFontMetricsF(_make_font(base_run, letter_spacing))
        width = 0.0
        height = float(metrics.lineSpacing())
        ascent = float(metrics.ascent())
    return _LineLayout(
        segments=segments,
        width=width,
        height=height,
        ascent=ascent,
        glyphs=[],
    )


def _layout(properties: TextProperties) -> _TextLayout:
    letter_spacing = properties.letter_spacing
    base_run = TextRun(
        text="",
        font_family=properties.font_family,
        font_size=properties.font_size,
        color=properties.color,
        bold=properties.bold,
        italic=properties.italic,
    )
    kerning = dict(properties.kerning_pairs)
    per_glyph = bool(kerning) or (
        properties.path_style != "none" and bool(properties.path_bend)
    )
    lines = [
        _layout_line(parts, base_run, letter_spacing, kerning, per_glyph)
        for parts in _split_lines(properties)
    ]
    content_width = max((line.width for line in lines), default=0.0)
    max_font = max((run.font_size for run in properties.runs), default=properties.font_size)
    padding = max(2, int(round(max_font * 0.15)))
    width = max(1, int(math.ceil(content_width + padding * 2)))
    height = lines[0].height + sum(
        line.height * properties.line_spacing for line in lines[1:]
    )
    height = max(1, int(math.ceil(height + padding * 2)))
    if width > 30_000 or height > 30_000 or width * height > MAX_RENDER_PIXELS:
        raise ValueError(
            "Văn bản sau khi render vượt giới hạn kích thước an toàn.\n"
            "Hãy giảm cỡ chữ hoặc nội dung."
        )
    return _TextLayout(
        lines=lines,
        content_width=content_width,
        padding=padding,
        width=width,
        height=height,
        line_spacing=properties.line_spacing,
    )


def text_size(properties: TextProperties) -> tuple[int, int]:
    """Kích thước pixel của layer văn bản sau khi render (uốn hoặc đường dẫn)."""
    if properties.path_style != "none":
        if not properties.path_bend:
            layout = _layout(properties)
            return layout.width, layout.height
    elif properties.warp_style == "none" or not properties.warp_bend:
        layout = _layout(properties)
        return layout.width, layout.height
    rendered = render_text(properties)
    return int(rendered.shape[1]), int(rendered.shape[0])


def _qimage_to_rgba(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = converted.width()
    height = converted.height()
    line_bytes = converted.bytesPerLine()
    pointer = converted.constBits()
    if hasattr(pointer, "setsize"):  # PySide2 trả về sip.voidptr
        pointer.setsize(line_bytes * height)
    try:
        buffer = bytes(pointer)
    except TypeError:  # pragma: no cover - PySide6 trả memoryview
        buffer = memoryview(pointer).tobytes()
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape((height, line_bytes))
    array = rows[:, : width * 4].reshape((height, width, 4))
    return np.ascontiguousarray(array).copy()


def _sample_bilinear_row(
    pixels: np.ndarray, src_x: np.ndarray, src_y: np.ndarray
) -> np.ndarray:
    """Lấy mẫu một hàng điểm ảnh bằng nội suy song tuyến, ngoài biên là trong suốt."""
    height, width = pixels.shape[:2]
    valid = (
        (src_x >= 0.0)
        & (src_x <= width - 1)
        & (src_y >= 0.0)
        & (src_y <= height - 1)
    )
    x0 = np.floor(np.clip(src_x, 0.0, width - 1)).astype(np.int32)
    y0 = np.floor(np.clip(src_y, 0.0, height - 1)).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    fx = (src_x - x0)[:, None].astype(np.float32)
    fy = (src_y - y0)[:, None].astype(np.float32)
    weight_00 = (1.0 - fx) * (1.0 - fy)
    weight_10 = fx * (1.0 - fy)
    weight_01 = (1.0 - fx) * fy
    weight_11 = fx * fy

    pixel_00 = pixels[y0, x0].astype(np.float32)
    pixel_10 = pixels[y0, x1].astype(np.float32)
    pixel_01 = pixels[y1, x0].astype(np.float32)
    pixel_11 = pixels[y1, x1].astype(np.float32)
    # Nhân trước alpha để viền chữ không bị quầng tối khi nội suy.
    alpha_00 = pixel_00[:, 3:4] / 255.0
    alpha_10 = pixel_10[:, 3:4] / 255.0
    alpha_01 = pixel_01[:, 3:4] / 255.0
    alpha_11 = pixel_11[:, 3:4] / 255.0
    premultiplied = (
        pixel_00[:, :3] * alpha_00 * weight_00
        + pixel_10[:, :3] * alpha_10 * weight_10
        + pixel_01[:, :3] * alpha_01 * weight_01
        + pixel_11[:, :3] * alpha_11 * weight_11
    )
    alpha = (
        alpha_00 * weight_00
        + alpha_10 * weight_10
        + alpha_01 * weight_01
        + alpha_11 * weight_11
    )

    result = np.zeros((src_x.shape[0], 4), dtype=np.uint8)
    inside = valid & (alpha[:, 0] > 1e-6)
    if np.any(inside):
        result[inside, :3] = np.clip(
            premultiplied[inside] / alpha[inside], 0.0, 255.0
        )
        result[inside, 3] = np.clip(alpha[inside, 0] * 255.0 + 0.5, 0, 255)
    return result


def _crop_alpha(pixels: np.ndarray) -> np.ndarray:
    alpha = pixels[..., 3]
    rows = np.flatnonzero(alpha.max(axis=1) > 0)
    cols = np.flatnonzero(alpha.max(axis=0) > 0)
    if rows.size == 0 or cols.size == 0:
        return np.zeros((1, 1, 4), dtype=np.uint8)
    top = max(0, int(rows[0]) - 1)
    bottom = min(pixels.shape[0], int(rows[-1]) + 2)
    left = max(0, int(cols[0]) - 1)
    right = min(pixels.shape[1], int(cols[-1]) + 2)
    return np.ascontiguousarray(pixels[top:bottom, left:right])


def _warp_pixels(pixels: np.ndarray, style: str, bend: int) -> np.ndarray:
    """Uốn ảnh chữ theo kiểu đã chọn bằng cách lấy mẫu ngược từ ảnh gốc."""
    if style == "none" or not bend:
        return pixels
    height, width = pixels.shape[:2]
    strength = bend / 100.0
    if style in ("rise", "twist"):
        pad = int(math.ceil(abs(strength) * 0.5 * max(width, height))) + 2
        pad_x = pad_y = pad
    elif style in ("bulge", "squeeze"):
        pad_x = 2
        pad_y = int(math.ceil(abs(strength) * 0.6 * height)) + 2
    else:
        pad_x = pad_y = int(math.ceil(abs(strength) * 0.5 * height)) + 2
    out_width = width + pad_x * 2
    out_height = height + pad_y * 2
    if out_width * out_height > MAX_WARP_PIXELS:
        raise ValueError(
            "Văn bản sau khi uốn vượt giới hạn kích thước an toàn.\n"
            "Hãy giảm cỡ chữ, bớt nội dung hoặc giảm độ uốn."
        )

    output = np.zeros((out_height, out_width, 4), dtype=np.uint8)
    center_x = width / 2.0
    center_y = height / 2.0
    xs = (np.arange(out_width, dtype=np.float32) - np.float32(pad_x)).astype(
        np.float32
    )
    u = xs / max(1.0, float(width - 1)) * 2.0 - 1.0
    clipped_u = np.clip(u, -1.0, 1.0)
    sin_wave = np.sin(np.float32(2.0 * math.pi) * clipped_u)
    for row in range(out_height):
        y = float(row - pad_y)
        v = y / max(1.0, float(height - 1)) * 2.0 - 1.0
        clipped_v = min(1.0, max(-1.0, v))
        src_x = xs.copy()
        src_y = np.full(out_width, y, dtype=np.float32)
        if style in ("arc", "arch"):
            if style == "arc":
                profile = 1.0 - clipped_u * clipped_u
            else:
                profile = np.sqrt(np.maximum(0.0, 1.0 - clipped_u * clipped_u))
            src_y = src_y + np.float32(strength * 0.35 * height) * profile
        elif style in ("bulge", "squeeze"):
            # Co giãn chiều cao theo vị trí ngang: glyph giữ nguyên hình dạng,
            # chỉ cao dần (phồng) hoặc thấp dần (ép) ở giữa, hai mép không đổi.
            factor = np.maximum(
                np.float32(0.25),
                np.float32(1.0)
                + np.float32(strength * 0.6) * (np.float32(1.0) - clipped_u * clipped_u),
            )
            dy = src_y - np.float32(center_y)
            if style == "bulge":
                src_y = np.float32(center_y) + dy / factor
            else:
                src_y = np.float32(center_y) + dy * factor
        elif style == "wave":
            src_y = src_y + np.float32(strength * 0.25 * height) * sin_wave
        elif style == "flag":
            src_y = src_y + np.float32(strength * 0.35 * height) * clipped_u
        elif style == "fish":
            profile = 1.0 - clipped_u * clipped_u
            src_y = src_y + np.float32(strength * 0.25 * height) * profile
            src_x = (
                src_x
                - np.float32(strength * 0.35 * height * clipped_v) * profile
            )
        elif style == "rise":
            theta = math.radians(25.0) * strength
            cos_theta = math.cos(theta)
            sin_theta = math.sin(theta)
            dx = src_x - center_x
            dy = src_y - center_y
            src_x = np.float32(center_x) + dx * cos_theta - dy * sin_theta
            src_y = np.float32(center_y) + dx * sin_theta + dy * cos_theta
        elif style == "twist":
            theta = np.float32(0.8 * strength) * clipped_u
            cos_theta = np.cos(theta)
            sin_theta = np.sin(theta)
            dx = src_x - center_x
            dy = src_y - center_y
            src_x = np.float32(center_x) + dx * cos_theta - dy * sin_theta
            src_y = np.float32(center_y) + dx * sin_theta + dy * cos_theta
        output[row] = _sample_bilinear_row(pixels, src_x, src_y)
    return _crop_alpha(output)


def _path_positions(
    style: str,
    bend: int,
    width: float,
    line_height: float,
    centres: list[float],
) -> list[tuple[float, float, float]]:
    """Trả về (x, y, góc quay độ) của tâm từng ký tự trên đường dẫn."""
    strength = min(1.0, abs(bend) / 100.0)
    sign = 1.0 if bend > 0 else -1.0
    radius = 0.0
    amplitude = 0.0
    cycles = 0.0
    if style == "arc":
        theta = math.radians(80.0 * strength)
        if theta > 1e-4:
            radius = width / (2.0 * theta)
    elif style == "circle":
        sweep = math.radians(360.0 * max(0.08, strength))
        radius = width / sweep
    elif style == "wave":
        amplitude = strength * max(line_height, 1.0) * 0.9
        cycles = 2.0
    elif style == "s_curve":
        amplitude = strength * max(line_height, 1.0) * 1.2
        cycles = 1.0

    arc_lengths: list[float] | None = None
    if style in ("wave", "s_curve"):
        # Lấy mẫu đường sóng để đặt ký tự theo độ dài cung thật, tránh chồng chữ.
        samples = max(64, min(2048, int(width)))
        arc_lengths = [0.0]
        previous_y = 0.0
        step = width / samples
        for index in range(1, samples + 1):
            t = index / samples
            y = sign * amplitude * math.sin(2.0 * math.pi * cycles * t)
            arc_lengths.append(
                arc_lengths[-1] + math.hypot(step, y - previous_y)
            )
            previous_y = y
        total_length = max(arc_lengths[-1], 1e-6)
        length_scale = total_length / width

    def wave_point(centre: float) -> tuple[float, float, float]:
        assert arc_lengths is not None
        target = min(arc_lengths[-1], max(0.0, centre * length_scale))
        low, high = 0, len(arc_lengths) - 1
        while low < high:
            mid = (low + high) // 2
            if arc_lengths[mid] < target:
                low = mid + 1
            else:
                high = mid
        index = min(max(low, 1), len(arc_lengths) - 1)
        span = arc_lengths[index] - arc_lengths[index - 1]
        fraction = (
            (target - arc_lengths[index - 1]) / span if span > 1e-9 else 0.0
        )
        t = (index - 1 + fraction) / (len(arc_lengths) - 1)
        phase = 2.0 * math.pi * cycles * t
        x = t * width
        y = sign * amplitude * math.sin(phase)
        slope = (
            sign
            * amplitude
            * (2.0 * math.pi * cycles / width)
            * math.cos(phase)
        )
        return x, y, math.degrees(math.atan(slope))

    placements: list[tuple[float, float, float]] = []
    for centre in centres:
        if style == "arc" and radius:
            phi = (centre - width / 2.0) / radius
            x = width / 2.0 + radius * math.sin(phi)
            y = sign * radius * (1.0 - math.cos(phi))
            angle = math.degrees(phi) * sign
        elif style == "circle":
            phi = (centre - width / 2.0) / radius
            x = width / 2.0 + radius * math.sin(phi)
            y = sign * radius * (1.0 - math.cos(phi))
            angle = math.degrees(phi) * sign
        elif style in ("wave", "s_curve"):
            x, y, angle = wave_point(centre)
        else:
            x, y, angle = centre, 0.0, 0.0
        placements.append((x, y, angle))
    return placements


def _render_path_text(properties: TextProperties) -> np.ndarray:
    """Đặt từng ký tự dọc theo đường cong và render thành ảnh RGBA."""
    base_run = TextRun(
        text="",
        font_family=properties.font_family,
        font_size=properties.font_size,
        color=properties.color,
        bold=properties.bold,
        italic=properties.italic,
    )
    flattened: list[tuple[TextRun, str]] = []
    for run in properties.runs:
        text = run.text.replace("\r", " ").replace("\n", " ")
        if text:
            flattened.append((run, text))
    line = _layout_line(
        flattened,
        base_run,
        properties.letter_spacing,
        dict(properties.kerning_pairs),
        True,
    )
    if not line.glyphs:
        raise ValueError("Nội dung văn bản không được để trống.")
    width = max(1.0, line.width)
    centres = [glyph.x + glyph.advance / 2.0 for glyph in line.glyphs]
    placements = _path_positions(
        properties.path_style,
        properties.path_bend,
        width,
        line.height,
        centres,
    )

    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    bounds: list[QRectF] = []
    for glyph in line.glyphs:
        bounds.append(QFontMetricsF(glyph.font).boundingRect(glyph.text))
    for glyph, box, (px, py, angle) in zip(line.glyphs, bounds, placements):
        if not glyph.text.strip():
            continue
        theta = math.radians(angle)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        origin_x = -glyph.advance / 2.0
        for corner_x, corner_y in (
            (box.left() + origin_x, box.top()),
            (box.right() + origin_x, box.top()),
            (box.left() + origin_x, box.bottom()),
            (box.right() + origin_x, box.bottom()),
        ):
            x = px + corner_x * cos_t - corner_y * sin_t
            y = py + corner_x * sin_t + corner_y * cos_t
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if not math.isfinite(min_x):
        raise ValueError("Nội dung văn bản không được để trống.")
    pad = 2
    left = int(math.floor(min_x)) - pad
    top = int(math.floor(min_y)) - pad
    out_width = max(1, int(math.ceil(max_x)) - left + pad)
    out_height = max(1, int(math.ceil(max_y)) - top + pad)
    if (
        out_width > 30_000
        or out_height > 30_000
        or out_width * out_height > MAX_WARP_PIXELS
    ):
        raise ValueError(
            "Văn bản trên đường dẫn vượt giới hạn kích thước an toàn.\n"
            "Hãy giảm cỡ chữ, bớt nội dung hoặc giảm độ cong."
        )

    image = QImage(
        out_width, out_height, QImage.Format.Format_ARGB32_Premultiplied
    )
    if image.isNull():
        raise MemoryError("Không đủ bộ nhớ để render văn bản trên đường dẫn.")
    image.fill(0)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for glyph, (px, py, angle) in zip(line.glyphs, placements):
            if not glyph.text.strip():
                continue
            painter.save()
            painter.translate(px - left, py - top)
            if angle:
                painter.rotate(angle)
            painter.setFont(glyph.font)
            painter.setPen(QColor(*glyph.color))
            painter.drawText(QPointF(-glyph.advance / 2.0, 0.0), glyph.text)
            painter.restore()
    finally:
        painter.end()
    return _crop_alpha(_qimage_to_rgba(image))


def render_text(properties: TextProperties) -> np.ndarray:
    """Render văn bản thành mảng RGBA uint8 với nền trong suốt."""
    if properties.path_style != "none":
        if properties.path_bend:
            return _render_path_text(properties)
        return _render_plain_text(properties)
    pixels = _render_plain_text(properties)
    return _warp_pixels(pixels, properties.warp_style, properties.warp_bend)


def _render_plain_text(properties: TextProperties) -> np.ndarray:
    layout = _layout(properties)
    image = QImage(
        layout.width, layout.height, QImage.Format.Format_ARGB32_Premultiplied
    )
    image.fill(0)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        baseline = layout.padding + layout.lines[0].ascent
        for index, line in enumerate(layout.lines):
            if index:
                baseline += layout.lines[index - 1].height * layout.line_spacing
            if properties.alignment == "center":
                x = layout.padding + (layout.content_width - line.width) / 2.0
            elif properties.alignment == "right":
                x = layout.padding + layout.content_width - line.width
            else:
                x = float(layout.padding)
            if line.glyphs:
                for glyph in line.glyphs:
                    painter.setFont(glyph.font)
                    painter.setPen(QColor(*glyph.color))
                    painter.drawText(QPointF(x + glyph.x, baseline), glyph.text)
            else:
                for segment in line.segments:
                    painter.setFont(segment.font)
                    painter.setPen(QColor(*segment.color))
                    painter.drawText(QPointF(x, baseline), segment.text)
                    x += segment.advance
    finally:
        painter.end()
    return _qimage_to_rgba(image)
