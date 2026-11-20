"""Tạo ảnh xem trước giao diện Phase 1–6 vào thư mục artifacts/.

Chạy từ thư mục gốc dự án:
    .venv310qt5\\Scripts\\python.exe tools\\preview_screenshots.py
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from config.settings import SettingsStore
from core import filters
from core.adjustment_layer import AdjustmentProperties
from core.batch import BatchAction, BatchStep
from core.document import Document
from core.fill_layer import FillProperties
from core.gradient import GradientSettings
from core.layer import Layer, LayerKind
from core.layer_style import (
    BevelSettings,
    ColorOverlaySettings,
    DropShadowSettings,
    GradientOverlaySettings,
    LayerStyle,
    OuterGlowSettings,
    StrokeSettings,
)
from core.paint import BrushSettings
from core.presets import PresetStore
from core.selection import Selection
from core.shape_layer import ShapeProperties
from core.smart_object import SmartObjectProperties
from core.text_layer import TextProperties, TextRun, render_text, text_size
from core.wand import flood_fill_mask, mask_to_path
from formats.export_manager import export_image
from ui import theme
from ui.dialogs import (
    AdjustmentLayerDialog,
    BatchDialog,
    CanvasSizeDialog,
    FillDialog,
    GaussianBlurDialog,
    ImageSizeDialog,
    ShapeDialog,
    SmartObjectDialog,
    TextDialog,
)
from ui.layer_style_dialog import LayerStyleDialog
from ui.main_window import MainWindow

OUTPUT_DIR = ROOT / "artifacts"


def gradient_layer(width: int, height: int) -> Layer:
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    top = np.array([26, 36, 66], dtype=np.float32)
    bottom = np.array([212, 132, 74], dtype=np.float32)
    rgb = top[None, :] * (1.0 - y) + bottom[None, :] * y
    rgb = np.repeat(rgb[:, None, :], width, axis=1)
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    rgba[..., 3] = 255
    layer = Layer(width, height, name="Sky Gradient")
    layer.set_pixels(rgba)
    return layer


def glow_layer(size: int = 520) -> Layer:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for radius in range(size // 2, 0, -8):
        alpha = int(70 * (1.0 - radius / (size / 2)) ** 1.6)
        draw.ellipse(
            (size / 2 - radius, size / 2 - radius, size / 2 + radius, size / 2 + radius),
            fill=(255, 205, 120, alpha),
        )
    image = image.filter(ImageFilter.GaussianBlur(24))
    layer = Layer(size, size, name="Warm Glow")
    layer.set_pixels(np.asarray(image, dtype=np.uint8))
    layer.offset_x = 660
    layer.offset_y = 40
    layer.opacity = 0.85
    return layer


def card_layer(
    width: int = 520,
    height: int = 230,
    subtitle: str = "Giai đoạn 2: Selection, Mask, Crop",
    lines: str = "Vùng chọn chữ nhật/ellipse, layer mask,\ncrop, Image Size và Canvas Size",
) -> Layer:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, width - 2, height - 2), radius=22, fill=(20, 24, 32, 225))
    draw.rounded_rectangle(
        (2, 2, width - 2, height - 2), radius=22, outline=(224, 160, 82, 255), width=2
    )
    try:
        font = ImageFont.truetype("arial.ttf", 26)
        small = ImageFont.truetype("arial.ttf", 17)
    except OSError:
        font = ImageFont.load_default()
        small = font
    draw.text((26, 24), "My Photo Studio", font=font, fill=(240, 242, 245, 255))
    draw.text(
        (26, 66),
        subtitle,
        font=small,
        fill=(224, 160, 82, 255),
    )
    draw.text(
        (26, 100),
        lines,
        font=small,
        fill=(176, 184, 194, 255),
        spacing=6,
    )
    layer = Layer(width, height, name="Info Card")
    layer.set_pixels(np.asarray(image, dtype=np.uint8))
    layer.offset_x = 70
    layer.offset_y = 470
    return layer


def arrow_layer(size: int = 180) -> Layer:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = (255, 196, 84, 240)
    draw.rounded_rectangle((24, 72, 116, 108), radius=10, fill=color)
    draw.polygon([(104, 34), (104, 146), (170, 90)], fill=color)
    layer = Layer(size, size, name="Arrow")
    layer.set_pixels(np.asarray(image, dtype=np.uint8))
    layer.offset_x = 930
    layer.offset_y = 80
    return layer


def build_demo_document() -> Document:
    document = Document(1200, 800, dpi=72.0, name="Phase 2 Demo")
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)

    glow = glow_layer()
    size = glow.width
    y, x = np.ogrid[:size, :size]
    distance = np.sqrt((x - size / 2) ** 2 + (y - size / 2) ** 2) / (size / 2)
    glow_mask = np.clip((1.1 - distance) * 255.0, 0.0, 255.0).astype(np.uint8)
    glow.set_mask(glow_mask)
    document.add_layer(layer=glow, index=1, select=False, record=False)

    card = card_layer()
    ramp = np.linspace(0.0, 1.0, card.width, dtype=np.float32)[None, :]
    card_mask = np.repeat(ramp, card.height, axis=0)
    card.set_mask((card_mask * 255.0).astype(np.uint8))
    document.add_layer(layer=card, index=2, select=True, record=False)
    document.mark_clean()
    return document


def build_phase3_document(name: str = "Phase 3 Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    document.add_layer(layer=glow_layer(), index=1, select=False, record=False)
    document.add_layer(layer=arrow_layer(), index=2, select=False, record=False)
    card = card_layer(
        subtitle="Giai đoạn 3: Xoay & Lật",
        lines="Xoay canvas/layer 90°, 180°\nvà góc bất kỳ với Undo/Redo",
    )
    card.offset_x = 340
    card.offset_y = 285
    document.add_layer(layer=card, index=3, select=True, record=False)
    document.mark_clean()
    return document


def backdrop_layer(width: int = 1000, height: int = 430) -> Layer:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (2, 2, width - 2, height - 2), radius=26, fill=(14, 18, 26, 232)
    )
    draw.rounded_rectangle(
        (2, 2, width - 2, height - 2), radius=26, outline=(224, 160, 82, 255), width=2
    )
    layer = Layer(width, height, name="Text Backdrop")
    layer.set_pixels(np.asarray(image, dtype=np.uint8))
    return layer


def build_phase4_document(name: str = "Phase 4 Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    document.add_layer(layer=glow_layer(), index=1, select=False, record=False)

    backdrop = backdrop_layer()
    backdrop.offset_x = 100
    backdrop.offset_y = 160
    document.add_layer(layer=backdrop, index=2, select=False, record=False)
    document.set_active_layer(backdrop)

    title = document.add_text_layer(
        TextProperties(
            text="My Photo Studio",
            font_size=76,
            bold=True,
            color=(250, 250, 252, 255),
        ),
        144,
        205,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 4 — Layer văn bản",
            font_size=36,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        148,
        320,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text=(
                "Chọn font, cỡ chữ, màu, đậm/nghiêng và căn lề.\n"
                "Văn bản vẫn chỉnh sửa được cho tới khi Rasterize."
            ),
            font_size=25,
            color=(200, 208, 220, 255),
        ),
        148,
        390,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Lưu trong .mps v3 · Undo/Redo · Layer mask",
            font_size=22,
            italic=True,
            color=(150, 160, 178, 255),
        ),
        148,
        490,
        record=False,
    )
    document.set_active_layer(title)
    document.mark_clean()
    return document


def photo_array(
    width: int = 460,
    height: int = 340,
    label: str = "",
    accent: tuple[int, int, int, int] = (255, 196, 84, 255),
    apply_filter=None,
) -> np.ndarray:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    top = np.array([24, 36, 78], dtype=np.float32)
    bottom = np.array([242, 148, 76], dtype=np.float32)
    for y in range(height):
        t = y / max(1, height - 1)
        color = top * (1.0 - t) + bottom * t
        draw.line((0, y, width, y), fill=tuple(int(v) for v in color) + (255,))
    draw.ellipse((300, 48, 388, 136), fill=(255, 228, 150, 255))
    draw.polygon(
        [(0, 250), (150, 150), (300, 260), (width, 175), (width, height), (0, height)],
        fill=(96, 46, 74, 255),
    )
    draw.polygon(
        [(0, 292), (190, 224), (340, 300), (width, 244), (width, height), (0, height)],
        fill=(40, 26, 46, 255),
    )
    if apply_filter is not None:
        image = Image.fromarray(
            apply_filter(np.asarray(image, dtype=np.uint8)), "RGBA"
        )
        draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(235, 238, 245, 255), width=2)
    draw.rectangle((0, height - 44, width, height), fill=(16, 20, 28, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text((16, height - 33), label, font=font, fill=accent)
    return np.asarray(image, dtype=np.uint8)


def build_phase5_document(name: str = "Phase 5 Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)

    original = Layer(460, 340, name="Ảnh gốc")
    original.set_pixels(photo_array(label="TRƯỚC KHI LỌC"))
    original.offset_x = 90
    original.offset_y = 140
    document.add_layer(layer=original, index=1, select=False, record=False)

    filtered = Layer(460, 340, name="Hue/Saturation")
    filtered.set_pixels(
        photo_array(
            label="SAU KHI LỌC",
            accent=(150, 255, 170, 255),
            apply_filter=lambda pixels: filters.hue_saturation(
                pixels, hue=65.0, saturation=30.0, lightness=8.0
            ),
        )
    )
    filtered.offset_x = 650
    filtered.offset_y = 140
    document.add_layer(layer=filtered, index=2, select=True, record=False)

    callout = backdrop_layer(1000, 96)
    callout.name = "Filter Caption"
    callout.offset_x = 100
    callout.offset_y = 560
    document.add_layer(layer=callout, index=3, select=False, record=False)
    document.set_active_layer(callout)

    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 5 — Bộ lọc và hiệu ứng",
            font_size=34,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        140,
        585,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Hue/Saturation áp dụng cho layer đang chọn · Vùng chọn giới hạn phạm vi · Ctrl+Z hoàn tác",
            font_size=19,
            color=(206, 212, 222, 255),
        ),
        142,
        628,
        record=False,
    )
    document.set_active_layer(filtered)
    document.mark_clean()
    return document


def build_phase6_document(name: str = "Phase 6 Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    document.add_layer(layer=glow_layer(), index=1, select=False, record=False)

    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Layer hình khối",
            font_size=50,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        90,
        58,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Hình chữ nhật · Chữ nhật bo góc · Ellipse — tô màu, viền và góc bo",
            font_size=21,
            color=(206, 212, 222, 255),
        ),
        92,
        126,
        record=False,
    )

    document.add_shape_layer(
        ShapeProperties(
            kind="rounded_rectangle",
            width=460,
            height=320,
            fill_color=(16, 20, 28, 232),
            stroke_color=(224, 160, 82, 255),
            stroke_width=3,
            corner_radius=26.0,
        ),
        90,
        240,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Kéo để vẽ hình\nShift tạo hình vuông/tròn\nEsc huỷ khi đang vẽ",
            font_size=28,
            bold=True,
            color=(240, 242, 245, 255),
        ),
        132,
        292,
        record=False,
    )

    ellipse = document.add_shape_layer(
        ShapeProperties(
            kind="ellipse",
            width=300,
            height=300,
            fill_color=(76, 132, 220, 235),
            stroke_color=(255, 255, 255, 255),
            stroke_width=4,
        ),
        620,
        250,
        record=False,
    )
    document.add_shape_layer(
        ShapeProperties(
            kind="rounded_rectangle",
            width=380,
            height=120,
            fill_color=(255, 196, 84, 255),
            stroke_width=0,
            corner_radius=60.0,
        ),
        590,
        590,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Vector vẫn sửa được · Lưu trong .mps v4",
            font_size=24,
            bold=True,
            color=(24, 30, 42, 255),
        ),
        640,
        632,
        record=False,
    )

    document.set_active_layer(ellipse)
    document.mark_clean()
    return document


def paint_stroke(
    document: Document,
    layer: Layer,
    points: list[tuple[float, float]],
    *,
    size: int,
    color: tuple[int, int, int, int],
    target: str = "pixels",
    hardness: float = 0.8,
    opacity: float = 1.0,
    erase: bool = False,
) -> None:
    """Vẽ một nét cọ hoàn chỉnh qua API công khai của Document."""
    settings = BrushSettings(
        size=size,
        hardness=hardness,
        opacity=opacity,
        color=color,
        erase=erase,
    )
    session = document.begin_brush_stroke(settings, target=target, layer=layer)
    for x, y in points:
        session.stroke_to(x, y)
    session.finish()


def wave_points(
    start_x: float, end_x: float, center_y: float, amplitude: float, count: int = 44
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(count + 1):
        t = index / count
        x = start_x + (end_x - start_x) * t
        y = center_y + amplitude * np.sin(t * np.pi * 2.6)
        points.append((x, y))
    return points


def build_phase6_brush_document(name: str = "Phase 6 Brush Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    document.add_layer(layer=glow_layer(), index=1, select=False, record=False)

    card = backdrop_layer(1000, 470)
    card.name = "Paint Card"
    card.offset_x = 100
    card.offset_y = 180
    document.add_layer(layer=card, index=2, select=False, record=False)
    card.set_mask(np.full((470, 1000), 255, dtype=np.uint8))
    document.set_active_layer(card)

    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Cọ, Tẩy và vẽ Mask",
            font_size=46,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        140,
        214,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Brush (B) · Eraser (Shift+E) · Kích thước, độ cứng, độ đục\nVẽ trực tiếp lên Layer Mask để ẩn/hiện mềm mại",
            font_size=21,
            color=(206, 212, 222, 255),
        ),
        142,
        278,
        record=False,
    )

    strokes = Layer(1200, 800, name="Brush Strokes")
    document.add_layer(
        layer=strokes, index=len(document.layers), select=False, record=False
    )
    paint_stroke(
        document,
        strokes,
        wave_points(170, 620, 470, 46),
        size=54,
        color=(255, 196, 84, 255),
        hardness=0.85,
    )
    paint_stroke(
        document,
        strokes,
        wave_points(560, 1030, 560, 34),
        size=34,
        color=(96, 168, 255, 255),
        hardness=0.7,
        opacity=0.9,
    )
    paint_stroke(
        document,
        strokes,
        wave_points(700, 1010, 470, 30),
        size=26,
        color=(255, 255, 255, 255),
        hardness=1.0,
        opacity=0.55,
    )

    paint_stroke(
        document,
        card,
        wave_points(760, 1050, 575, 26, count=60),
        size=90,
        color=(0, 0, 0, 255),
        target="mask",
        hardness=0.45,
    )

    document.set_active_layer(card)
    document.mark_clean()
    return document


def paint_gradient(
    document: Document,
    layer: Layer,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    start_color: tuple[int, int, int, int],
    end_color: tuple[int, int, int, int],
    gradient_type: str = "linear",
    target: str = "pixels",
) -> None:
    """Tô một gradient hoàn chỉnh qua API công khai của Document."""
    settings = GradientSettings(
        gradient_type=gradient_type,
        start_color=start_color,
        end_color=end_color,
    )
    session = document.begin_gradient(settings, start, target=target, layer=layer)
    session.update(end[0], end[1])
    session.finish()


def build_phase6_gradient_document(name: str = "Phase 6 Gradient Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)

    background = Layer(1200, 800, name="Gradient Sky")
    document.add_layer(layer=background, index=0, select=False, record=False)
    paint_gradient(
        document,
        background,
        (600.0, 0.0),
        (600.0, 800.0),
        start_color=(26, 36, 66, 255),
        end_color=(212, 132, 74, 255),
    )

    sun = Layer(1200, 800, name="Sun Glow")
    document.add_layer(layer=sun, index=1, select=False, record=False)
    paint_gradient(
        document,
        sun,
        (880.0, 220.0),
        (880.0, 520.0),
        start_color=(255, 214, 130, 255),
        end_color=(255, 214, 130, 0),
        gradient_type="radial",
    )
    sun.set_mask(np.full((800, 1200), 255, dtype=np.uint8))
    paint_gradient(
        document,
        sun,
        (600.0, 720.0),
        (600.0, 220.0),
        start_color=(0, 0, 0, 255),
        end_color=(255, 255, 255, 255),
        target="mask",
    )

    card = backdrop_layer(760, 330)
    card.name = "Gradient Card"
    card.offset_x = 90
    card.offset_y = 240
    document.add_layer(layer=card, index=2, select=False, record=False)
    document.set_active_layer(card)

    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Gradient",
            font_size=44,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        120,
        272,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text=(
                "Tuyến tính và hình tròn · Tô lên Layer hoặc Layer Mask\n"
                "Vùng chọn giới hạn phạm vi · Ctrl+Z hoàn tác"
            ),
            font_size=22,
            color=(214, 220, 230, 255),
        ),
        122,
        336,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Mask của lớp nắng được tô gradient đen → trắng",
            font_size=19,
            italic=True,
            color=(170, 178, 192, 255),
        ),
        122,
        452,
        record=False,
    )

    document.set_active_layer(sun)
    document.mark_clean()
    return document


def build_phase6_feather_document(name: str = "Phase 6 Feather Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)

    background = gradient_layer(1200, 800)
    background.name = "Feather Sky"
    document.add_layer(layer=background, index=0, select=False, record=False)

    spotlight = Layer(1200, 800, name="Feathered Spotlight")
    document.add_layer(layer=spotlight, index=1, select=False, record=False)
    paint_gradient(
        document,
        spotlight,
        (820.0, 360.0),
        (820.0, 700.0),
        start_color=(255, 240, 205, 255),
        end_color=(255, 198, 126, 255),
        gradient_type="radial",
    )

    selection = Selection.from_ellipse(
        1200, 800, QRectF(560.0, 170.0, 520.0, 440.0), feather=40, antialias=True
    )
    document.set_selection(selection)
    document.set_active_layer(spotlight)
    document.add_layer_mask()

    card = backdrop_layer(760, 330)
    card.name = "Feather Card"
    card.offset_x = 90
    card.offset_y = 240
    document.add_layer(layer=card, index=2, select=False, record=False)
    document.set_active_layer(card)

    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Feather",
            font_size=44,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        120,
        272,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text=(
                "Ellipse với Feather 40 px · Anti-alias bật\n"
                "Biên mềm áp dụng cho mask, cọ, gradient và bộ lọc"
            ),
            font_size=22,
            color=(214, 220, 230, 255),
        ),
        122,
        336,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Menu Select ▸ Feather Selection… (Shift+F6)",
            font_size=19,
            italic=True,
            color=(170, 178, 192, 255),
        ),
        122,
        452,
        record=False,
    )

    document.set_active_layer(spotlight)
    document.mark_clean()
    return document


def build_phase6_select_tools_document(name: str = "Phase 6 Select Tools Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)

    sky = Layer(1200, 800, name="Night Sky")
    sky.fill((34, 46, 78, 255))
    document.add_layer(layer=sky, index=0, select=False, record=False)

    glow = glow_layer(520)
    glow.name = "Moon Glow"
    glow.offset_x = 620
    glow.offset_y = 60
    document.add_layer(layer=glow, index=1, select=False, record=False)

    mountains = Layer(1200, 800, name="Mountains")
    image = Image.new("RGBA", (1200, 800), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [
            (0, 800),
            (0, 648),
            (170, 536),
            (356, 660),
            (548, 494),
            (726, 642),
            (902, 516),
            (1084, 654),
            (1200, 588),
            (1200, 800),
        ],
        fill=(20, 28, 46, 255),
    )
    draw.polygon(
        [
            (0, 800),
            (0, 724),
            (218, 650),
            (436, 734),
            (652, 662),
            (872, 742),
            (1094, 682),
            (1200, 722),
            (1200, 800),
        ],
        fill=(11, 16, 29, 255),
    )
    mountains.set_pixels(np.asarray(image, dtype=np.uint8))
    document.add_layer(layer=mountains, index=2, select=False, record=False)

    # Magic Wand thật: chọn vùng trời phẳng từ ảnh composite, đổi mask thành path.
    composite = document.get_composite().array
    region = flood_fill_mask(composite, 20, 20, 0, contiguous=True)
    document.set_selection(
        Selection.from_path(
            1200,
            800,
            mask_to_path(region),
            feather=8,
            antialias=True,
        )
    )

    card = card_layer(
        500,
        300,
        subtitle="Giai đoạn 6 — Lasso · Wand · Quick Selection",
        lines=(
            "Magic Wand: dung sai 0 · liền mạch · feather 8\n"
            "Quick Mask (Q): vùng đỏ = phần CHƯA chọn\n"
            "Lasso L · Wand W · Quick Selection Shift+W\n"
            "Dùng chung QPainterPath, mask và Undo"
        ),
    )
    card.offset_x = 50
    card.offset_y = 190
    document.add_layer(layer=card, index=3, select=False, record=False)
    document.set_active_layer(glow)
    document.mark_clean()
    return document


def build_phase6_rich_text_document(name: str = "Phase 6 Rich Text Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    document.add_layer(layer=glow_layer(), index=1, select=False, record=False)

    left_card = backdrop_layer(500, 330)
    left_card.name = "Default Card"
    left_card.offset_x = 60
    left_card.offset_y = 180
    document.add_layer(layer=left_card, index=2, select=False, record=False)

    right_card = backdrop_layer(500, 330)
    right_card.name = "Spacing Card"
    right_card.offset_x = 640
    right_card.offset_y = 180
    document.add_layer(layer=right_card, index=3, select=False, record=False)
    document.set_active_layer(right_card)

    body = (
        "Văn bản nhiều dòng\n"
        "để thấy rõ khoảng cách.\n"
        "Giãn chữ áp dụng cho\n"
        "mọi ký tự trong dòng."
    )
    document.add_text_layer(
        TextProperties(
            text="Mặc định",
            font_size=34,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        88,
        208,
        record=False,
    )
    document.add_text_layer(
        TextProperties(text=body, font_size=22, color=(206, 214, 226, 255)),
        88,
        268,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Giãn dòng 1,6× · chữ +5 px",
            font_size=26,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        668,
        214,
        record=False,
    )
    spaced = document.add_text_layer(
        TextProperties(
            text=body,
            font_size=22,
            color=(206, 214, 226, 255),
            line_spacing=1.6,
            letter_spacing=5,
        ),
        668,
        268,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Lưu trong .mps v4 · sửa lại bất cứ lúc nào bằng Type ▸ Edit Text…",
            font_size=20,
            italic=True,
            color=(158, 168, 186, 255),
        ),
        60,
        566,
        record=False,
    )
    document.set_active_layer(spaced)
    document.mark_clean()
    return document


def build_phase6_rich_runs_document(name: str = "Phase 6 Rich Runs Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    glow = glow_layer()
    glow.offset_x = 640
    glow.offset_y = -60
    document.add_layer(layer=glow, index=1, select=False, record=False)

    card = backdrop_layer(1060, 300)
    card.name = "Typography Card"
    card.offset_x = 70
    card.offset_y = 300
    document.add_layer(layer=card, index=2, select=False, record=False)
    document.set_active_layer(card)

    document.add_text_layer(
        TextProperties(
            runs=(
                TextRun("SÁNG ", font_size=66, bold=True, color=(255, 196, 84, 255)),
                TextRun("TẠO ", font_size=66, italic=True, color=(255, 122, 150, 255)),
                TextRun("Ý TƯỞNG", font_size=66, bold=True, color=(120, 196, 255, 255)),
            )
        ),
        70,
        82,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            runs=(
                TextRun("Rich text", font_size=38, bold=True, color=(236, 242, 250, 255)),
                TextRun(
                    " trong một layer duy nhất",
                    font_size=24,
                    italic=True,
                    color=(168, 182, 204, 255),
                ),
            )
        ),
        74,
        190,
        record=False,
    )
    body = document.add_text_layer(
        TextProperties(
            runs=(
                TextRun("Mỗi đoạn ", font_size=27, color=(206, 214, 226, 255)),
                TextRun(
                    "có font, cỡ, màu",
                    font_size=27,
                    bold=True,
                    color=(255, 196, 84, 255),
                ),
                TextRun(" riêng.\n", font_size=27, color=(206, 214, 226, 255)),
                TextRun("Vẫn giữ ", font_size=22, italic=True, color=(168, 182, 204, 255)),
                TextRun(
                    "giãn dòng 1,4×",
                    font_size=22,
                    bold=True,
                    color=(132, 230, 168, 255),
                ),
                TextRun(
                    " và giãn chữ +3 px.",
                    font_size=22,
                    italic=True,
                    color=(168, 182, 204, 255),
                ),
            ),
            line_spacing=1.4,
            letter_spacing=3,
            color=(206, 214, 226, 255),
        ),
        110,
        340,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            runs=(
                TextRun("Bôi đen ", font_size=24, color=(206, 214, 226, 255)),
                TextRun("một phần chữ", font_size=30, bold=True, color=(255, 122, 150, 255)),
                TextRun(" rồi đổi kiểu.", font_size=24, color=(206, 214, 226, 255)),
            )
        ),
        110,
        468,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Type ▸ Edit Text… giữ nguyên mọi kiểu chữ · .mps v4",
            font_size=20,
            italic=True,
            color=(158, 168, 186, 255),
        ),
        70,
        650,
        record=False,
    )
    document.set_active_layer(body)
    document.mark_clean()
    return document


def build_phase6_text_warp_document(name: str = "Phase 6 Text Warp Demo") -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(layer=gradient_layer(1200, 800), index=0, select=False, record=False)
    glow = glow_layer()
    glow.offset_x = 520
    glow.offset_y = -80
    document.add_layer(layer=glow, index=1, select=False, record=False)

    card = backdrop_layer(1080, 520)
    card.name = "Warp Card"
    card.offset_x = 60
    card.offset_y = 150
    document.add_layer(layer=card, index=2, select=False, record=False)
    document.set_active_layer(card)

    title = document.add_text_layer(
        TextProperties(
            text="MY PHOTO STUDIO",
            font_size=68,
            bold=True,
            color=(255, 196, 84, 255),
            warp_style="arc",
            warp_bend=75,
        ),
        110,
        195,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Lượn sóng theo nhịp",
            font_size=34,
            bold=True,
            color=(132, 230, 168, 255),
            warp_style="wave",
            warp_bend=75,
        ),
        120,
        335,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Vòm cong mềm mại",
            font_size=34,
            bold=True,
            color=(255, 122, 150, 255),
            warp_style="arch",
            warp_bend=-65,
        ),
        520,
        335,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Xoắn nhẹ cuốn hút",
            font_size=34,
            bold=True,
            color=(120, 196, 255, 255),
            warp_style="twist",
            warp_bend=60,
        ),
        120,
        450,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Phồng to tâm chữ",
            font_size=34,
            bold=True,
            color=(236, 242, 250, 255),
            warp_style="bulge",
            warp_bend=50,
        ),
        520,
        455,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Uốn chữ mà vẫn sửa được nội dung, font, màu và từng đoạn.",
            font_size=24,
            italic=True,
            color=(206, 214, 226, 255),
        ),
        110,
        555,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Type ▸ Edit Text… · chọn Uốn chữ và Độ uốn · .mps v4",
            font_size=20,
            italic=True,
            color=(158, 168, 186, 255),
        ),
        70,
        700,
        record=False,
    )
    document.set_active_layer(title)
    document.mark_clean()
    return document


def build_phase6_text_path_document(
    name: str = "Phase 6 Text On Path Demo",
) -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(
        layer=gradient_layer(1200, 800), index=0, select=False, record=False
    )
    glow = glow_layer()
    glow.offset_x = 600
    glow.offset_y = -40
    document.add_layer(layer=glow, index=1, select=False, record=False)

    card = backdrop_layer(1080, 620)
    card.name = "Path Card"
    card.offset_x = 60
    card.offset_y = 100
    document.add_layer(layer=card, index=2, select=False, record=False)
    document.set_active_layer(card)

    document.add_text_layer(
        TextProperties(
            text="GIAI ĐOẠN 6 · CHỮ TRÊN ĐƯỜNG DẪN",
            font_size=22,
            bold=True,
            color=(224, 160, 82, 255),
        ),
        100,
        132,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="TEXT ON PATH",
            font_size=70,
            bold=True,
            color=(250, 250, 252, 255),
            path_style="arc",
            path_bend=80,
        ),
        100,
        180,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Sóng mềm theo từng ký tự",
            font_size=34,
            bold=True,
            color=(132, 230, 168, 255),
            path_style="wave",
            path_bend=45,
            letter_spacing=4,
        ),
        100,
        356,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Chữ S uyển chuyển",
            font_size=34,
            bold=True,
            color=(120, 196, 255, 255),
            path_style="s_curve",
            path_bend=40,
            letter_spacing=2,
        ),
        100,
        470,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Kerning thủ công: AV −8 · VA −6 · WA −4 px",
            font_size=22,
            italic=True,
            color=(206, 214, 226, 255),
        ),
        100,
        560,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="AVATAR WAVE",
            font_size=46,
            bold=True,
            color=(255, 196, 84, 255),
            kerning_pairs=(("AV", -8), ("VA", -6), ("WA", -4)),
        ),
        100,
        596,
        record=False,
    )

    ring_text = "MY PHOTO STUDIO · CHỮ TRÊN ĐƯỜNG DẪN · "
    ring = TextProperties(
        text=ring_text,
        font_size=27,
        bold=True,
        color=(255, 122, 150, 255),
        path_style="circle",
        path_bend=100,
    )
    ring_width, ring_height = text_size(ring)
    document.add_text_layer(
        ring,
        640 + (430 - ring_width) // 2,
        300 + (250 - ring_height) // 2,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Đường dẫn thay thế uốn chữ · kerning theo cặp · vẫn sửa nội dung · .mps",
            font_size=20,
            italic=True,
            color=(158, 168, 186, 255),
        ),
        100,
        690,
        record=False,
    )
    document.mark_clean()
    return document


def build_phase6_canvas_text_document(
    name: str = "Phase 6 Canvas Text Demo",
) -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(
        layer=gradient_layer(1200, 800), index=0, select=False, record=False
    )
    glow = glow_layer()
    glow.offset_x = 520
    glow.offset_y = -80
    document.add_layer(layer=glow, index=1, select=False, record=False)

    card = backdrop_layer(1060, 470)
    card.name = "Canvas Text Card"
    card.offset_x = 70
    card.offset_y = 165
    document.add_layer(layer=card, index=2, select=False, record=False)
    document.set_active_layer(card)

    title = document.add_text_layer(
        TextProperties(
            text="MY PHOTO STUDIO",
            font_size=62,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        100,
        205,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Gõ chữ ngay trên canvas",
            font_size=34,
            bold=True,
            color=(236, 242, 250, 255),
        ),
        100,
        315,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text=(
                "Chọn công cụ Text (T), nhấp và gõ trực tiếp — không cần hộp thoại.\n"
                "Ctrl+Enter để xong, Esc để huỷ; nhấp vào layer chữ để sửa lại."
            ),
            font_size=24,
            color=(206, 214, 226, 255),
        ),
        100,
        390,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Type ▸ Edit Text… vẫn mở hộp thoại để đổi font, màu, căn lề, uốn chữ.",
            font_size=20,
            italic=True,
            color=(158, 168, 186, 255),
        ),
        70,
        700,
        record=False,
    )
    document.set_active_layer(title)
    document.mark_clean()
    return document


def build_phase6_adjustment_document(
    name: str = "Phase 6 Adjustment Layers Demo",
) -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(
        layer=gradient_layer(1200, 800), index=0, select=False, record=False
    )

    photo = Layer(660, 440, name="Ảnh gốc")
    photo.set_pixels(photo_array(660, 440, label="ẢNH GỐC"))
    photo.offset_x = 70
    photo.offset_y = 120
    document.add_layer(layer=photo, index=1, select=True, record=False)

    brightness = document.add_adjustment_layer(
        AdjustmentProperties(brightness=16, contrast=14),
        name="Brightness/Contrast",
        record=False,
    )
    hue = document.add_adjustment_layer(
        AdjustmentProperties(kind="hue_saturation", hue=35, saturation=22),
        name="Hue/Saturation",
        record=False,
    )
    document.set_layer_opacity(brightness, 0.75)

    card = backdrop_layer(1000, 120)
    card.name = "Adjustment Caption"
    card.offset_x = 100
    card.offset_y = 610
    document.add_layer(
        layer=card, index=len(document.layers), select=True, record=False
    )

    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Layer điều chỉnh",
            font_size=32,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        140,
        636,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Nhấp đôi layer để sửa · Opacity = độ mạnh",
            font_size=19,
            color=(206, 212, 222, 255),
        ),
        142,
        690,
        record=False,
    )
    document.set_active_layer(hue)
    document.mark_clean()
    return document


def build_phase6_advanced_adjustments_document(
    name: str = "Phase 6 Advanced Adjustments Demo",
) -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(
        layer=gradient_layer(1200, 800), index=0, select=False, record=False
    )

    photo = Layer(660, 440, name="Ảnh gốc")
    photo.set_pixels(photo_array(660, 440, label="ẢNH GỐC"))
    photo.offset_x = 70
    photo.offset_y = 120
    document.add_layer(layer=photo, index=1, select=True, record=False)

    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="levels",
            levels_black=15,
            levels_white=240,
            levels_gamma=1.2,
            levels_out_black=4,
            levels_out_white=252,
        ),
        name="Levels",
        record=False,
    )
    document.add_adjustment_layer(
        AdjustmentProperties(
            kind="curves",
            curve_points=((0, 0), (58, 40), (160, 196), (255, 255)),
            curve_red=((0, 0), (52, 70), (168, 176), (255, 255)),
        ),
        name="Curves",
        record=False,
    )
    balance = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="color_balance",
            color_shadows=(10, -4, 8),
            color_midtones=(26, -10, 12),
            color_highlights=(-6, 2, 10),
            preserve_luminosity=True,
        ),
        name="Color Balance",
        record=False,
    )
    document.set_layer_opacity(balance, 0.9)

    card = backdrop_layer(1000, 120)
    card.name = "Advanced Adjustment Caption"
    card.offset_x = 100
    card.offset_y = 610
    document.add_layer(
        layer=card, index=len(document.layers), select=True, record=False
    )
    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Levels · Curves · Color Balance",
            font_size=31,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        140,
        636,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Nhấp đôi layer để sửa · đường cong 4 điểm · giữ độ sáng khi cân màu",
            font_size=18,
            color=(206, 212, 222, 255),
        ),
        142,
        690,
        record=False,
    )
    document.set_active_layer(balance)
    document.mark_clean()
    return document


def build_phase6_groups_document(
    name: str = "Phase 6 Layer Groups Demo",
) -> Document:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(
        layer=gradient_layer(1200, 800), index=0, select=False, record=False
    )

    photo = Layer(500, 340, name="Ảnh gốc")
    photo.set_pixels(photo_array(500, 340, label="ẢNH GỐC"))
    photo.offset_x = 110
    photo.offset_y = 180
    document.add_layer(layer=photo, select=True, record=False)

    adjustment = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="color_balance",
            color_midtones=(28, 4, -18),
            color_highlights=(12, 2, -10),
            preserve_luminosity=True,
        ),
        name="Tông ấm",
        record=False,
    )

    badges = []
    for index, (top, fill) in enumerate(
        (
            (190, (64, 132, 224, 235)),
            (310, (240, 178, 74, 235)),
            (430, (58, 186, 158, 235)),
        )
    ):
        badge = document.add_shape_layer(
            ShapeProperties(
                kind="rounded_rectangle",
                width=270,
                height=92,
                fill_color=fill,
                stroke_color=(255, 255, 255, 220),
                stroke_width=2,
                corner_radius=20.0,
            ),
            x=780,
            y=top,
            record=False,
        )
        badge.name = f"Huy hiệu {index + 1}"
        badges.append(badge)

    card = backdrop_layer(980, 112)
    card.name = "Group Caption"
    card.offset_x = 110
    card.offset_y = 620
    document.add_layer(
        layer=card, index=len(document.layers), select=True, record=False
    )
    document.add_text_layer(
        TextProperties(
            text="Giai đoạn 6 — Layer Group lồng nhau",
            font_size=31,
            bold=True,
            color=(255, 196, 84, 255),
        ),
        145,
        640,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Opacity, blend và mask áp lên cả nhóm · điều chỉnh trong nhóm "
            "chỉ ảnh hưởng layer cùng nhóm",
            font_size=18,
            color=(206, 212, 222, 255),
        ),
        146,
        690,
        record=False,
    )

    tone_group = document.group_layers([photo, adjustment], name="Tông màu")
    badge_group = document.group_layers(badges, name="Huy hiệu")
    badge_group.opacity = 0.94
    outer = document.group_layers([tone_group, badge_group], name="Bố cục")
    document.set_active_layer(outer)
    document.mark_clean()
    return document


def build_phase6_layer_style_document(
    name: str = "Phase 6 Layer Style Demo",
) -> tuple[Document, Layer]:
    document = Document(1200, 800, dpi=72.0, name=name)
    document.add_layer(
        layer=gradient_layer(1200, 800), index=0, select=False, record=False
    )

    width, height = 620, 340
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    top = np.array([44, 54, 82], dtype=np.float32)
    bottom = np.array([24, 30, 48], dtype=np.float32)
    rgb = top[None, :] * (1.0 - y) + bottom[None, :] * y
    rgb = np.repeat(rgb[:, None, :], width, axis=1)
    mask_image = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask_image).rounded_rectangle(
        (3, 3, width - 3, height - 3), radius=30, fill=255
    )
    card_pixels = np.empty((height, width, 4), dtype=np.uint8)
    card_pixels[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    card_pixels[..., 3] = np.asarray(mask_image, dtype=np.uint8)
    card = Layer(width, height, name="Thẻ chính")
    card.set_pixels(card_pixels)
    card.offset_x = 110
    card.offset_y = 210
    document.add_layer(layer=card, select=True, record=False)
    card.style = LayerStyle(
        effects=(
            DropShadowSettings(
                enabled=True,
                color=(2, 4, 10, 255),
                opacity=0.65,
                angle=120.0,
                distance=16.0,
                spread=6.0,
                size=20.0,
            ),
            BevelSettings(
                enabled=True,
                style="inner",
                depth=120.0,
                direction="up",
                size=8.0,
                soften=3.0,
                highlight_color=(255, 236, 196, 255),
                highlight_opacity=0.45,
                shadow_color=(0, 0, 0, 255),
                shadow_opacity=0.4,
            ),
            StrokeSettings(
                enabled=True,
                size=2.0,
                position="center",
                color=(255, 206, 128, 255),
            ),
        )
    )

    badge = document.add_shape_layer(
        ShapeProperties(
            kind="rounded_rectangle",
            width=210,
            height=86,
            fill_color=(90, 110, 160, 255),
            stroke_color=(255, 255, 255, 0),
            stroke_width=0,
            corner_radius=22.0,
        ),
        x=470,
        y=460,
        record=False,
    )
    badge.name = "Huy hiệu Gradient"
    badge.style = LayerStyle(
        effects=(
            OuterGlowSettings(
                enabled=True,
                color=(255, 178, 92, 255),
                blend_mode="screen",
                opacity=0.8,
                spread=4.0,
                size=14.0,
            ),
            GradientOverlaySettings(
                enabled=True,
                start_color=(255, 176, 84, 255),
                end_color=(242, 92, 128, 255),
                blend_mode="normal",
                opacity=1.0,
                angle=25.0,
                scale=100.0,
            ),
            StrokeSettings(
                enabled=True,
                size=2.0,
                position="inside",
                color=(255, 236, 210, 255),
            ),
        )
    )

    document.add_text_layer(
        TextProperties(
            text="LAYER STYLE",
            font_size=62,
            bold=True,
            color=(255, 208, 128, 255),
        ),
        154,
        292,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Drop Shadow · Bevel & Emboss · Stroke · Gradient Overlay",
            font_size=22,
            color=(214, 222, 236, 255),
        ),
        158,
        388,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Blend If · Fill Opacity · Knockout · hiệu ứng thật trên mọi layer",
            font_size=19,
            italic=True,
            color=(158, 170, 192, 255),
        ),
        158,
        430,
        record=False,
    )
    document.set_active_layer(card)
    document.mark_clean()
    return document, card


def build_phase6_fill_smart_document(
    name: str = "Phase 6 Fill & Smart Object Demo",
) -> tuple[Document, Layer, Layer]:
    document = Document(1200, 800, dpi=72.0, name=name)
    background = document.add_fill_layer(
        FillProperties(
            fill_type="gradient",
            gradient_type="linear",
            color=(14, 22, 48, 255),
            color2=(70, 36, 82, 255),
            angle=32,
        ),
        name="Nền gradient",
        record=False,
    )

    source = photo_array(560, 360, label="ẢNH GỐC · 560 × 360")
    smart = document.add_smart_object_layer(
        source,
        SmartObjectProperties(
            source_name="phong-canh.png",
            source_width=source.shape[1],
            source_height=source.shape[0],
            angle=7,
            scale=88,
        ),
        name="Ảnh phong cảnh (smart)",
        record=False,
    )
    smart.offset_y = 130

    tint = document.add_fill_layer(
        FillProperties(
            fill_type="gradient",
            gradient_type="linear",
            color=(255, 186, 96, 120),
            color2=(42, 120, 210, 0),
            angle=90,
        ),
        name="Ánh hoàng hôn",
        record=False,
    )
    tint.opacity = 0.5
    tint.blend_mode = "screen"

    document.add_text_layer(
        TextProperties(
            text="Layer tô & Smart Object",
            font_size=40,
            bold=True,
            color=(255, 214, 140, 255),
        ),
        356,
        590,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Gradient không phá huỷ · ảnh gốc xoay 7° vẫn sắc nét",
            font_size=19,
            color=(216, 224, 238, 255),
        ),
        358,
        650,
        record=False,
    )
    document.set_active_layer(smart)
    document.mark_clean()
    return document, background, smart


def build_phase6_tiles_document(
    name: str = "Phase 6 Tile & Lazy Demo",
) -> Document:
    document = Document(3600, 2400, dpi=72.0, name=name)
    document.add_fill_layer(
        FillProperties(
            fill_type="gradient",
            gradient_type="linear",
            color=(16, 24, 46, 255),
            color2=(78, 40, 84, 255),
            angle=26,
        ),
        name="Nền gradient 3600 × 2400",
        record=False,
    )

    detail = Layer(1300, 820, name="Ảnh chi tiết 1300 × 820")
    detail.set_pixels(photo_array(1300, 820, label="XEM 100% · TILE 256 × 256"))
    detail.offset_x = 120
    detail.offset_y = 230
    document.add_layer(layer=detail, record=False)

    document.add_text_layer(
        TextProperties(
            text="Ảnh lớn 3600 × 2400",
            font_size=52,
            bold=True,
            color=(255, 214, 140, 255),
        ),
        120,
        96,
        record=False,
    )
    document.add_text_layer(
        TextProperties(
            text="Chỉ composite vùng nhìn thấy · cache ô LRU · dirty rect khi vẽ",
            font_size=20,
            color=(216, 224, 238, 255),
        ),
        122,
        162,
        record=False,
    )

    secondary = Layer(900, 620, name="Ảnh phụ 900 × 620")
    secondary.set_pixels(photo_array(900, 620, label="NGOÀI KHUNG NHÌN"))
    secondary.offset_x = 2100
    secondary.offset_y = 1500
    document.add_layer(layer=secondary, record=False)

    document.add_adjustment_layer(
        AdjustmentProperties(kind="brightness_contrast", brightness=6, contrast=14),
        name="Tương phản nhẹ",
        select=False,
        record=False,
    )
    document.set_active_layer(detail)
    document.mark_clean()
    return document


def build_phase6_psd_demo(path: Path) -> Path:
    """Ghi PSD RGB 8-bit nhỏ (RLE) mô phỏng file Photoshop để chụp ảnh mở PSD."""

    def u16(value: int) -> bytes:
        return struct.pack(">H", value)

    def i16(value: int) -> bytes:
        return struct.pack(">h", value)

    def u32(value: int) -> bytes:
        return struct.pack(">I", value)

    def packbits(data: bytes) -> bytes:
        out = bytearray()
        index = 0
        while index < len(data):
            chunk = data[index : index + 128]
            out.append(len(chunk) - 1)
            out += chunk
            index += len(chunk)
        return bytes(out)

    def channel_block(array: np.ndarray) -> bytes:
        plane = np.ascontiguousarray(array, dtype=np.uint8)
        rows = [packbits(plane[row].tobytes()) for row in range(plane.shape[0])]
        table = b"".join(u16(len(row)) for row in rows)
        return u16(1) + table + b"".join(rows)

    def tag(key: bytes, data: bytes) -> bytes:
        return b"8BIM" + key + u32(len(data)) + data

    def dstr(text: str) -> bytes:
        return u32(len(text)) + text.encode("utf-16-be")

    def did(text: str) -> bytes:
        raw = text.encode("latin-1")
        return u32(len(raw)) + raw

    def descriptor(name: str, class_id: str, items: list[bytes]) -> bytes:
        return dstr(name) + did(class_id) + u32(len(items)) + b"".join(items)

    def desc_item(key: str, os_type: bytes, value: bytes) -> bytes:
        return did(key) + os_type + value

    def d_double(value: float) -> bytes:
        return struct.pack(">d", value)

    def round_rect_vogk(
        top: int,
        left: int,
        bottom: int,
        right: int,
        radius: float,
        stroke: tuple[float, tuple[int, int, int]] | None = None,
    ) -> bytes:
        geometry = descriptor(
            "",
            "rnd ",
            [
                desc_item("Top ", b"doub", d_double(float(top))),
                desc_item("Left", b"doub", d_double(float(left))),
                desc_item("Btom", b"doub", d_double(float(bottom))),
                desc_item("Rght", b"doub", d_double(float(right))),
                desc_item("Rds ", b"doub", d_double(radius)),
            ],
        )
        style_items = [desc_item("fillEnabled", b"bool", b"\x01")]
        if stroke is not None:
            stroke_width, stroke_color = stroke
            rg = descriptor(
                "",
                "RGBC",
                [
                    desc_item("Rd  ", b"doub", d_double(stroke_color[0])),
                    desc_item("Grn ", b"doub", d_double(stroke_color[1])),
                    desc_item("Bl  ", b"doub", d_double(stroke_color[2])),
                ],
            )
            style_items += [
                desc_item("strokeEnabled", b"bool", b"\x01"),
                desc_item(
                    "strokeStyleLineWidth",
                    b"UntF",
                    b"#Pnt" + d_double(stroke_width),
                ),
                desc_item(
                    "strokeStyleContent",
                    b"Objc",
                    descriptor("", "SoCo", [desc_item("Clr ", b"Objc", rg)]),
                ),
            ]
        style = descriptor("", "shapeStyle", style_items)
        return u32(1) + descriptor(
            "",
            "vectorOriginationData",
            [
                desc_item("roundRect", b"Objc", geometry),
                desc_item("shapeStyle", b"Objc", style),
            ],
        )

    def text_style_data(
        font_name: str, size: float, color: tuple[float, float, float]
    ) -> bytes:
        return descriptor(
            "",
            "StyleSheetData",
            [
                desc_item("FontPostScriptName", b"TEXT", dstr(font_name)),
                desc_item("FontSize", b"doub", d_double(size)),
                desc_item("FauxBold", b"bool", b"\x00"),
                desc_item("FauxItalic", b"bool", b"\x00"),
                desc_item("Tracking", b"long", struct.pack(">i", 0)),
                desc_item("Leading", b"doub", d_double(0.0)),
                desc_item("AutoLeading", b"bool", b"\x01"),
                desc_item("Underline", b"bool", b"\x00"),
                desc_item("Strikethrough", b"bool", b"\x00"),
                desc_item("HorizontalScale", b"long", struct.pack(">i", 100)),
                desc_item("VerticalScale", b"long", struct.pack(">i", 100)),
                desc_item(
                    "FillColor",
                    b"Objc",
                    descriptor(
                        "",
                        "RGBC",
                        [
                            desc_item("Rd  ", b"doub", d_double(color[0])),
                            desc_item("Grn ", b"doub", d_double(color[1])),
                            desc_item("Bl  ", b"doub", d_double(color[2])),
                        ],
                    ),
                ),
            ],
        )

    def text_style_run(count: int, style: bytes) -> bytes:
        run = descriptor(
            "",
            "Pnt ",
            [
                desc_item(
                    "StyleSheet",
                    b"Objc",
                    descriptor(
                        "",
                        "StyleSheet",
                        [desc_item("StyleSheetData", b"Objc", style)],
                    ),
                )
            ],
        )
        return descriptor(
            "",
            "StyleRun",
            [
                desc_item(
                    "RunLengthArray",
                    b"VlLs",
                    u32(1) + b"long" + struct.pack(">i", count),
                ),
                desc_item("RunArray", b"VlLs", u32(1) + b"Objc" + run),
            ],
        )

    def text_tysh(
        text: str,
        style: bytes,
        bounds: tuple[int, int, int, int],
    ) -> bytes:
        top, left, bottom, right = bounds
        root = descriptor(
            "",
            "TxLr",
            [
                desc_item("Txt ", b"TEXT", dstr(text)),
                desc_item("Ornt", b"enum", did("Ornt") + did("Hrzn")),
                desc_item(
                    "bounds",
                    b"Objc",
                    descriptor(
                        "",
                        "bounds",
                        [
                            desc_item("Left", b"doub", d_double(float(left))),
                            desc_item("Top ", b"doub", d_double(float(top))),
                            desc_item("Rght", b"doub", d_double(float(right))),
                            desc_item("Btom", b"doub", d_double(float(bottom))),
                        ],
                    ),
                ),
                desc_item("StyleRun", b"Objc", text_style_run(len(text), style)),
            ],
        )
        warp = descriptor(
            "",
            "warp",
            [
                desc_item("warpStyle", b"enum", did("warpStyle") + did("warpNone")),
                desc_item("warpValue", b"doub", d_double(0.0)),
            ],
        )
        return (
            u16(1)
            + struct.pack(">6d", 1.0, 0.0, 0.0, 1.0, float(left), float(top))
            + u16(50)
            + u32(16)
            + root
            + u16(1)
            + u32(16)
            + warp
            + struct.pack(">iiii", top, left, bottom, right)
        )

    def record(
        name: str,
        rect: tuple[int, int, int, int],
        channels: dict[int, np.ndarray],
        *,
        opacity: int = 255,
        blend: bytes = b"norm",
        section: int = 0,
        mask: tuple[tuple[int, int, int, int], np.ndarray] | None = None,
        tags: tuple[tuple[bytes, bytes], ...] = (),
    ) -> tuple[bytes, bytes]:
        if mask is not None:
            channels = {**channels, -2: mask[1]}
        info = b""
        data = b""
        for channel_id, array in channels.items():
            block = channel_block(array)
            info += i16(channel_id) + u32(len(block))
            data += block
        extra = b""
        if mask is not None:
            extra += u32(18) + struct.pack(">iiii", *mask[0]) + b"\xff\x00"
        else:
            extra += u32(0)
        extra += u32(0)
        raw_name = name.encode("utf-8")
        extra += bytes([len(raw_name)]) + raw_name
        extra += b"\x00" * ((4 - ((1 + len(raw_name)) % 4)) % 4)
        if section:
            extra += tag(b"lsct", u32(section) + b"8BIM" + b"norm")
        for key, tag_data in tags:
            extra += tag(key, tag_data)
        header = (
            struct.pack(">iiii", *rect)
            + u16(len(channels))
            + info
            + b"8BIM"
            + blend
            + bytes([opacity, 0, 0, 0])
            + u32(len(extra))
            + extra
        )
        return header, data

    width, height = 640, 420
    background = np.zeros((height, width, 4), dtype=np.uint8)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    background[..., 0] = np.clip(24 + 96 * x + 18 * y, 0, 255).astype(np.uint8)
    background[..., 1] = np.clip(30 + 42 * x + 12 * y, 0, 255).astype(np.uint8)
    background[..., 2] = np.clip(58 + 92 * x + 30 * y, 0, 255).astype(np.uint8)
    background[..., 3] = 255

    glow_w, glow_h = 300, 220
    yy, xx = np.mgrid[0:glow_h, 0:glow_w].astype(np.float32)
    cx, cy = (glow_w - 1) / 2.0, (glow_h - 1) / 2.0
    dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    falloff = np.clip(1.0 - dist, 0.0, 1.0) ** 1.6
    glow = np.zeros((glow_h, glow_w, 4), dtype=np.uint8)
    glow[..., 0] = 255
    glow[..., 1] = np.clip(150 + 80 * falloff, 0, 255).astype(np.uint8)
    glow[..., 2] = 90
    glow[..., 3] = (falloff * 235).astype(np.uint8)

    square_w, square_h = 210, 170
    masked = np.zeros((square_h, square_w, 4), dtype=np.uint8)
    masked[..., 0] = 40
    masked[..., 1] = 196
    masked[..., 2] = 178
    masked[..., 3] = 255
    square_mask = np.zeros((square_h, square_w), dtype=np.uint8)
    square_mask[:, : square_w // 2] = 255
    square_mask[:, square_w // 2 :] = np.linspace(
        255, 0, square_w - square_w // 2, dtype=np.float32
    ).astype(np.uint8)

    accent = np.zeros((140, 140, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:140, 0:140].astype(np.float32)
    dist = np.sqrt(((xx - 69.5) / 69.5) ** 2 + ((yy - 69.5) / 69.5) ** 2)
    halo = np.clip(1.0 - dist, 0.0, 1.0) ** 2
    accent[..., 0] = 255
    accent[..., 1] = 226
    accent[..., 2] = np.clip(170 + 60 * halo, 0, 255).astype(np.uint8)
    accent[..., 3] = (halo * 255).astype(np.uint8)

    card_top, card_left, card_bottom, card_right = 60, 468, 240, 618
    card = np.zeros(
        (card_bottom - card_top, card_right - card_left, 4), dtype=np.uint8
    )
    card[...] = (242, 132, 64, 255)

    group_mask = np.zeros((height, width), dtype=np.uint8)
    group_mask[:, :] = 255
    group_mask[:, width // 2 :] = np.linspace(
        255, 90, width - width // 2, dtype=np.float32
    ).astype(np.uint8)

    title_props = TextProperties(
        text="My Photo Studio",
        font_family="Arial",
        font_size=40,
        color=(255, 255, 255, 255),
        bold=True,
        alignment="left",
    )
    title_rgba = render_text(title_props)
    title_h, title_w = title_rgba.shape[:2]
    title_top, title_left = 34, 38
    title_bottom, title_right = title_top + title_h, title_left + title_w
    title_bounds = (title_top, title_left, title_bottom, title_right)

    entries = [
        record(
            "Nền gradient",
            (0, 0, height, width),
            {
                0: background[..., 0],
                1: background[..., 1],
                2: background[..., 2],
                -1: background[..., 3],
            },
        ),
        record("Họa tiết", (0, 0, 0, 0), {}, section=3),
        record(
            "Vệt sáng",
            (70, 60, 290, 360),
            {
                0: glow[..., 0],
                1: glow[..., 1],
                2: glow[..., 2],
                -1: glow[..., 3],
            },
            blend=b"scrn",
        ),
        record(
            "Ô màu có mask",
            (330, 160, 500, 540),
            {
                0: masked[..., 0],
                1: masked[..., 1],
                2: masked[..., 2],
                -1: masked[..., 3],
            },
            mask=((160, 330, 330, 540), square_mask),
        ),
        record(
            "Họa tiết",
            (0, 0, 0, 0),
            {},
            section=1,
            mask=((0, 0, height, width), group_mask),
        ),
        record(
            "Điểm nhấn",
            (250, 420, 390, 560),
            {
                0: accent[..., 0],
                1: accent[..., 1],
                2: accent[..., 2],
                -1: accent[..., 3],
            },
            blend=b"sLit",
            opacity=210,
        ),
        record(
            "Thẻ màu (live shape)",
            (card_top, card_left, card_bottom, card_right),
            {
                0: card[..., 0],
                1: card[..., 1],
                2: card[..., 2],
                -1: card[..., 3],
            },
            tags=(
                (
                    b"vogk",
                    round_rect_vogk(
                        card_top,
                        card_left,
                        card_bottom,
                        card_right,
                        18.0,
                        stroke=(4.0, (255, 255, 255)),
                    ),
                ),
            ),
        ),
        record(
            "Tiêu đề (text)",
            title_bounds,
            {
                0: title_rgba[..., 0],
                1: title_rgba[..., 1],
                2: title_rgba[..., 2],
                -1: title_rgba[..., 3],
            },
            tags=(
                (
                    b"TySh",
                    text_tysh(
                        "My Photo Studio",
                        text_style_data("Arial-BoldMT", 9.6, (1.0, 1.0, 1.0)),
                        title_bounds,
                    ),
                ),
            ),
        ),
    ]

    records = b"".join(entry[0] for entry in entries)
    channel_data = b"".join(entry[1] for entry in entries)
    layer_info = i16(len(entries)) + records + channel_data
    section = u32(len(layer_info)) + layer_info + u32(0)
    header = (
        b"8BPS"
        + u16(1)
        + b"\x00" * 6
        + u16(4)
        + u32(height)
        + u32(width)
        + u16(8)
        + u16(3)
    )
    image = u16(0) + b"".join(
        np.ascontiguousarray(background[..., channel]).tobytes()
        for channel in range(4)
    )
    fixed_dpi = int(round(300 * 65536))
    resource_data = struct.pack(">iHH", fixed_dpi, 1, 1) + struct.pack(
        ">iHH", fixed_dpi, 1, 1
    )
    resource = (
        b"8BIM" + u16(1005) + b"\x00\x00" + u32(len(resource_data)) + resource_data
    )
    path.write_bytes(
        header
        + u32(0)
        + u32(len(resource))
        + resource
        + u32(len(section))
        + section
        + image
    )
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    theme.apply_theme(app, "dark")

    settings_path = OUTPUT_DIR / "settings_preview.json"
    if settings_path.exists():
        settings_path.unlink()
    store = SettingsStore(settings_path)

    document = build_demo_document()
    window = MainWindow(store)
    window.resize(1420, 900)
    window.show()
    window._add_document_tab(document)
    window.current_view.fit_to_window()
    app.processEvents()

    dark_path = OUTPUT_DIR / "phase1_dark.png"
    window.grab().save(str(dark_path))
    print("saved", dark_path)

    window._set_theme("light")
    app.processEvents()
    light_path = OUTPUT_DIR / "phase1_light.png"
    window.grab().save(str(light_path))
    print("saved", light_path)

    window._set_theme("dark")
    view = window.current_view

    view.set_tool("ellipse_select")
    document.set_selection(
        Selection.from_ellipse(
            document.width, document.height, QRectF(180, 140, 720, 460)
        ),
        "Chọn ellipse",
    )
    app.processEvents()
    selection_path = OUTPUT_DIR / "phase2_selection.png"
    window.grab().save(str(selection_path))
    print("saved", selection_path)

    view.set_tool("crop")
    view.set_crop_rect(QRectF(200, 130, 760, 470))
    app.processEvents()
    crop_path = OUTPUT_DIR / "phase2_crop.png"
    window.grab().save(str(crop_path))
    print("saved", crop_path)

    image_dialog = ImageSizeDialog(document, window)
    image_dialog.show()
    app.processEvents()
    image_path = OUTPUT_DIR / "phase2_image_size.png"
    image_dialog.grab().save(str(image_path))
    print("saved", image_path)
    image_dialog.close()

    canvas_dialog = CanvasSizeDialog(document, window)
    canvas_dialog.show()
    app.processEvents()
    canvas_path = OUTPUT_DIR / "phase2_canvas_size.png"
    canvas_dialog.grab().save(str(canvas_path))
    print("saved", canvas_path)
    canvas_dialog.close()

    phase3_document = build_phase3_document()
    window._add_document_tab(phase3_document)
    app.processEvents()
    phase3_view = window.current_view
    phase3_view.fit_to_window()
    window._on_rotate_canvas("cw")
    app.processEvents()
    window._on_transform_layer("rotate_ccw")
    phase3_view.fit_to_window()
    app.processEvents()
    transform_path = OUTPUT_DIR / "phase3_transform.png"
    window.grab().save(str(transform_path))
    print("saved", transform_path)
    window._remove_view(phase3_view)
    phase3_document.mark_clean()

    free_document = build_phase3_document("Phase 3 Free Rotation")
    window._add_document_tab(free_document)
    app.processEvents()
    free_view = window.current_view
    free_view.fit_to_window()
    if free_document.rotate_canvas_arbitrary(12.0):
        free_view.clear_crop_rect()
        free_view.fit_to_window()
        free_document.rotate_layer_arbitrary(-6.0)
        window._show_transient_message(
            "Đã xoay canvas 12° và layer -6° (Ctrl+Z để hoàn tác)."
        )
    app.processEvents()
    free_path = OUTPUT_DIR / "phase3_free_rotate.png"
    window.grab().save(str(free_path))
    print("saved", free_path)
    window._remove_view(free_view)
    free_document.mark_clean()

    text_document = build_phase4_document()
    window._add_document_tab(text_document)
    app.processEvents()
    text_view = window.current_view
    text_view.set_tool("text")
    text_view.fit_to_window()
    app.processEvents()
    text_path = OUTPUT_DIR / "phase4_text.png"
    window.grab().save(str(text_path))
    print("saved", text_path)

    dialog = TextDialog(
        window,
        TextProperties(
            text="Xin chào! Đây là văn bản có thể chỉnh sửa.",
            font_size=42,
            bold=True,
            color=(255, 196, 84, 255),
            alignment="center",
        ),
        editing=True,
    )
    dialog.show()
    app.processEvents()
    dialog_path = OUTPUT_DIR / "phase4_text_dialog.png"
    dialog.grab().save(str(dialog_path))
    print("saved", dialog_path)
    dialog.close()

    window._remove_view(text_view)
    text_document.mark_clean()

    filter_document = build_phase5_document()
    window._add_document_tab(filter_document)
    app.processEvents()
    filter_view = window.current_view
    filter_view.fit_to_window()
    window._show_transient_message(
        "Đã áp dụng Hue/Saturation cho layer 'Hue/Saturation' (Ctrl+Z để hoàn tác)."
    )
    app.processEvents()
    filter_path = OUTPUT_DIR / "phase5_filters.png"
    window.grab().save(str(filter_path))
    print("saved", filter_path)

    filtered_layer = next(
        layer for layer in filter_document.layers if layer.name == "Hue/Saturation"
    )
    blur_dialog = GaussianBlurDialog(filtered_layer, window)
    blur_dialog.radius_spin.setValue(6.0)
    blur_dialog._update_preview()
    blur_dialog.show()
    app.processEvents()
    blur_dialog_path = OUTPUT_DIR / "phase5_blur_dialog.png"
    blur_dialog.grab().save(str(blur_dialog_path))
    print("saved", blur_dialog_path)
    blur_dialog.close()

    window._remove_view(filter_view)
    filter_document.mark_clean()

    shape_document = build_phase6_document()
    window._add_document_tab(shape_document)
    app.processEvents()
    shape_view = window.current_view
    shape_view.set_tool("shape")
    shape_view.fit_to_window()
    window._show_transient_message(
        "Shape: kéo trên canvas để vẽ · Shift tạo hình vuông/tròn · Esc để huỷ."
    )
    app.processEvents()
    shape_path = OUTPUT_DIR / "phase6_shapes.png"
    window.grab().save(str(shape_path))
    print("saved", shape_path)

    shape_dialog = ShapeDialog(
        window,
        ShapeProperties(
            kind="rounded_rectangle",
            width=320,
            height=220,
            fill_color=(76, 132, 220, 235),
            stroke_color=(255, 196, 84, 255),
            stroke_width=4,
            corner_radius=28.0,
        ),
        editing=True,
    )
    shape_dialog.show()
    app.processEvents()
    shape_dialog_path = OUTPUT_DIR / "phase6_shape_dialog.png"
    shape_dialog.grab().save(str(shape_dialog_path))
    print("saved", shape_dialog_path)
    shape_dialog.close()

    window._remove_view(shape_view)
    shape_document.mark_clean()

    brush_document = build_phase6_brush_document()
    window._add_document_tab(brush_document)
    app.processEvents()
    brush_view = window.current_view
    brush_view.set_tool("brush")
    brush_view.set_brush_options(size=64, hardness=0.75, opacity=0.9, paint_mask=True)
    brush_view.set_brush_color((255, 196, 84, 255))
    window.options_bar.sync_paint_state()
    brush_view.fit_to_window()
    window._show_transient_message(
        "Brush: kéo để vẽ màu Foreground · Shift+E chuyển sang Eraser · "
        "Vẽ lên Layer Mask để ẩn/hiện mềm mại."
    )
    app.processEvents()
    brush_path = OUTPUT_DIR / "phase6_brush.png"
    window.grab().save(str(brush_path))
    print("saved", brush_path)

    window._remove_view(brush_view)
    brush_document.mark_clean()

    gradient_document = build_phase6_gradient_document()
    window._add_document_tab(gradient_document)
    app.processEvents()
    gradient_view = window.current_view
    gradient_view.set_tool("gradient")
    gradient_view.set_gradient_options(
        gradient_type="linear", preset="black_white", paint_mask=True
    )
    window.options_bar.sync_paint_state()
    window._update_action_states()
    gradient_view.fit_to_window()
    window._show_transient_message(
        "Gradient: kéo từ điểm đầu tới điểm cuối · Kiểu tuyến tính/hình tròn · "
        "Có thể tô lên Layer Mask · Esc để huỷ."
    )
    app.processEvents()
    gradient_path = OUTPUT_DIR / "phase6_gradient.png"
    window.grab().save(str(gradient_path))
    print("saved", gradient_path)

    window._remove_view(gradient_view)
    gradient_document.mark_clean()

    feather_document = build_phase6_feather_document()
    window._add_document_tab(feather_document)
    app.processEvents()
    feather_view = window.current_view
    feather_view.set_tool("rect_select")
    window.toolbox.set_current_tool("rect_select")
    app.processEvents()
    window.options_bar._selection_feather.setValue(40)
    window.options_bar._selection_antialias.setChecked(True)
    feather_view.set_selection_options(feather=40, antialias=True)
    window._update_action_states()
    feather_view.fit_to_window()
    window._show_transient_message(
        "Feather 40 px: biên vùng chọn mềm · Áp dụng cho mask, cọ, gradient "
        "và bộ lọc · Shift+F6 để đổi bán kính."
    )
    app.processEvents()
    feather_path = OUTPUT_DIR / "phase6_feather.png"
    window.grab().save(str(feather_path))
    print("saved", feather_path)

    window._remove_view(feather_view)
    feather_document.mark_clean()

    select_document = build_phase6_select_tools_document()
    window._add_document_tab(select_document)
    app.processEvents()
    select_view = window.current_view
    select_view.set_tool("magic_wand")
    window.toolbox.set_current_tool("magic_wand")
    app.processEvents()
    window.options_bar._wand_tolerance.setValue(0)
    window.options_bar._wand_contiguous.setChecked(True)
    window.options_bar._selection_feather.setValue(8)
    select_view.set_magic_wand_options(tolerance=0, contiguous=True)
    select_view.set_selection_options(feather=8)
    select_view.set_quick_mask(True)
    window._update_action_states()
    select_view.fit_to_window()
    window._show_transient_message(
        "Magic Wand chọn vùng màu liền kề · Quick Mask: đỏ = phần chưa chọn · "
        "Lasso (L) · Quick Selection (Shift+W)."
    )
    app.processEvents()
    select_path = OUTPUT_DIR / "phase6_select_tools.png"
    window.grab().save(str(select_path))
    print("saved", select_path)

    window._remove_view(select_view)
    select_document.mark_clean()

    rich_document = build_phase6_rich_text_document()
    window._add_document_tab(rich_document)
    app.processEvents()
    rich_view = window.current_view
    rich_view.set_tool("text")
    window.toolbox.set_current_tool("text")
    app.processEvents()
    rich_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Giãn dòng 1,6× và giãn chữ +5 px: chọn layer văn bản rồi mở "
        "Type ▸ Edit Text… để chỉnh."
    )
    app.processEvents()
    rich_path = OUTPUT_DIR / "phase6_rich_text.png"
    window.grab().save(str(rich_path))
    print("saved", rich_path)

    active_text = rich_document.active_layer
    rich_dialog = TextDialog(
        window,
        active_text.text if active_text is not None else None,
        editing=True,
    )
    rich_dialog.show()
    app.processEvents()
    rich_dialog_path = OUTPUT_DIR / "phase6_rich_text_dialog.png"
    rich_dialog.grab().save(str(rich_dialog_path))
    print("saved", rich_dialog_path)
    rich_dialog.close()

    window._remove_view(rich_view)
    rich_document.mark_clean()

    rich_runs_document = build_phase6_rich_runs_document()
    window._add_document_tab(rich_runs_document)
    app.processEvents()
    rich_runs_view = window.current_view
    rich_runs_view.set_tool("text")
    window.toolbox.set_current_tool("text")
    app.processEvents()
    rich_runs_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Rich text: mỗi đoạn có font, cỡ, màu và đậm/nghiêng riêng trong cùng "
        "một layer · Undo vẫn hoạt động."
    )
    app.processEvents()
    rich_runs_path = OUTPUT_DIR / "phase6_rich_runs.png"
    window.grab().save(str(rich_runs_path))
    print("saved", rich_runs_path)

    rich_text_layer = next(
        layer
        for layer in rich_runs_document.layers
        if layer.text is not None and layer.text.text.startswith("Mỗi đoạn")
    )
    rich_runs_dialog = TextDialog(window, rich_text_layer.text, editing=True)
    rich_runs_dialog.show()
    app.processEvents()
    selected_text = "giãn dòng 1,4×"
    start = rich_text_layer.text.text.index(selected_text)
    dialog_cursor = rich_runs_dialog.text_edit.textCursor()
    dialog_cursor.setPosition(start)
    dialog_cursor.setPosition(
        start + len(selected_text), QTextCursor.MoveMode.KeepAnchor
    )
    rich_runs_dialog.text_edit.setTextCursor(dialog_cursor)
    rich_runs_dialog._update_preview()
    app.processEvents()
    rich_runs_dialog_path = OUTPUT_DIR / "phase6_rich_runs_dialog.png"
    rich_runs_dialog.grab().save(str(rich_runs_dialog_path))
    print("saved", rich_runs_dialog_path)
    rich_runs_dialog.close()

    window._remove_view(rich_runs_view)
    rich_runs_document.mark_clean()

    warp_document = build_phase6_text_warp_document()
    window._add_document_tab(warp_document)
    app.processEvents()
    warp_view = window.current_view
    warp_view.set_tool("text")
    window.toolbox.set_current_tool("text")
    app.processEvents()
    warp_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Uốn chữ: cung, vòm, sóng, phồng, xoắn… · vẫn sửa được nội dung và "
        "định dạng theo từng đoạn · Undo hoạt động."
    )
    app.processEvents()
    warp_path = OUTPUT_DIR / "phase6_text_warp.png"
    window.grab().save(str(warp_path))
    print("saved", warp_path)

    warp_title = next(
        layer
        for layer in warp_document.layers
        if layer.text is not None and layer.text.text.startswith("MY PHOTO")
    )
    warp_dialog = TextDialog(window, warp_title.text, editing=True)
    warp_dialog.show()
    warp_dialog._update_preview()
    app.processEvents()
    warp_dialog_path = OUTPUT_DIR / "phase6_text_warp_dialog.png"
    warp_dialog.grab().save(str(warp_dialog_path))
    print("saved", warp_dialog_path)
    warp_dialog.close()

    window._remove_view(warp_view)
    warp_document.mark_clean()

    path_document = build_phase6_text_path_document()
    window._add_document_tab(path_document)
    app.processEvents()
    path_view = window.current_view
    path_view.set_tool("text")
    window.toolbox.set_current_tool("text")
    app.processEvents()
    path_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Chữ trên đường dẫn: cung, vòng tròn, sóng, chữ S · kerning thủ công "
        "theo cặp ký tự · vẫn sửa nội dung và định dạng."
    )
    app.processEvents()
    path_shot = OUTPUT_DIR / "phase6_text_path.png"
    window.grab().save(str(path_shot))
    print("saved", path_shot)

    ring_layer = next(
        layer
        for layer in path_document.layers
        if layer.text is not None and layer.text.text.startswith("MY PHOTO")
    )
    path_dialog = TextDialog(window, ring_layer.text, editing=True)
    path_dialog.show()
    path_dialog._update_preview()
    app.processEvents()
    path_dialog_shot = OUTPUT_DIR / "phase6_text_path_dialog.png"
    path_dialog.grab().save(str(path_dialog_shot))
    print("saved", path_dialog_shot)
    path_dialog.close()

    window._remove_view(path_view)
    path_document.mark_clean()

    canvas_text_document = build_phase6_canvas_text_document()
    window._add_document_tab(canvas_text_document)
    app.processEvents()
    canvas_text_view = window.current_view
    canvas_text_view.set_tool("text")
    window.toolbox.set_current_tool("text")
    app.processEvents()
    canvas_text_view.fit_to_window()
    window._update_action_states()
    canvas_text_view.begin_inline_text(
        QPointF(96.0, 552.0),
        TextRun("", "", 34, (255, 255, 255, 255)),
    )
    inline_editor = canvas_text_view.inline_editor
    inline_cursor = inline_editor.textCursor()
    inline_cursor.insertText(
        "Gõ chữ trực tiếp trên canvas", inline_editor.currentCharFormat()
    )
    app.processEvents()
    window._show_transient_message(
        "Gõ chữ trên canvas: nhấp bằng công cụ Text (T) · Ctrl+Enter để xong · "
        "Esc để huỷ · Undo hoạt động."
    )
    app.processEvents()
    canvas_text_path = OUTPUT_DIR / "phase6_canvas_text.png"
    window.grab().save(str(canvas_text_path))
    print("saved", canvas_text_path)

    canvas_text_view.commit_inline_text()
    app.processEvents()
    window._update_action_states()
    canvas_text_result_path = OUTPUT_DIR / "phase6_canvas_text_result.png"
    window.grab().save(str(canvas_text_result_path))
    print("saved", canvas_text_result_path)

    window._remove_view(canvas_text_view)
    canvas_text_document.mark_clean()

    adjustment_document = build_phase6_adjustment_document()
    window._add_document_tab(adjustment_document)
    app.processEvents()
    adjustment_view = window.current_view
    adjustment_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Layer điều chỉnh: Layer ▸ New Adjustment Layer · nhấp đôi layer để sửa · "
        "Opacity = độ mạnh hiệu ứng."
    )
    app.processEvents()
    adjustment_path = OUTPUT_DIR / "phase6_adjustment_layers.png"
    window.grab().save(str(adjustment_path))
    print("saved", adjustment_path)

    adjustment_layer = adjustment_document.active_layer
    adjustment_dialog = AdjustmentLayerDialog(
        adjustment_layer.adjustment,
        window,
        preview=window._adjustment_preview_source(adjustment_layer),
        editing=True,
    )
    adjustment_dialog.show()
    app.processEvents()
    adjustment_dialog_path = OUTPUT_DIR / "phase6_adjustment_dialog.png"
    adjustment_dialog.grab().save(str(adjustment_dialog_path))
    print("saved", adjustment_dialog_path)
    adjustment_dialog.close()

    window._remove_view(adjustment_view)
    adjustment_document.mark_clean()

    mask_document = build_phase6_adjustment_document(
        "Phase 6 Adjustment Mask Demo"
    )
    mask_layer = next(
        layer
        for layer in mask_document.layers
        if layer.adjustment is not None and layer.name == "Hue/Saturation"
    )
    mask_document.add_layer_mask(mask_layer, record=False)
    mask_session = mask_document.begin_gradient(
        GradientSettings(
            gradient_type="linear",
            start_color=(0, 0, 0, 255),
            end_color=(255, 255, 255, 255),
        ),
        (90.0, 340.0),
        target="mask",
        layer=mask_layer,
    )
    mask_session.update(730.0, 340.0)
    mask_session.finish()

    window._add_document_tab(mask_document)
    app.processEvents()
    mask_view = window.current_view
    mask_view.set_tool("brush")
    window.toolbox.set_current_tool("brush")
    window.action_paint_mask.trigger()
    app.processEvents()
    mask_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Mask của layer điều chỉnh: Layer ▸ Layer Mask ▸ Add Layer Mask · "
        "vẽ bằng Brush/Gradient · đen = giữ ảnh gốc, trắng = áp hiệu ứng."
    )
    app.processEvents()
    mask_path = OUTPUT_DIR / "phase6_adjustment_mask.png"
    window.grab().save(str(mask_path))
    print("saved", mask_path)

    mask_dialog = AdjustmentLayerDialog(
        mask_layer.adjustment,
        window,
        preview=window._adjustment_preview_source(mask_layer),
        editing=True,
        mask=mask_layer.mask,
    )
    mask_dialog.show()
    app.processEvents()
    mask_dialog_path = OUTPUT_DIR / "phase6_adjustment_mask_dialog.png"
    mask_dialog.grab().save(str(mask_dialog_path))
    print("saved", mask_dialog_path)
    mask_dialog.close()

    window._remove_view(mask_view)
    mask_document.mark_clean()

    advanced_document = build_phase6_advanced_adjustments_document()
    window._add_document_tab(advanced_document)
    app.processEvents()
    advanced_view = window.current_view
    advanced_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Điều chỉnh nâng cao: Levels, Curves và Color Balance · nhấp đôi layer "
        "để sửa · Opacity = độ mạnh hiệu ứng."
    )
    app.processEvents()
    advanced_path = OUTPUT_DIR / "phase6_advanced_adjustments.png"
    window.grab().save(str(advanced_path))
    print("saved", advanced_path)

    for layer_name, file_name in (
        ("Levels", "phase6_levels_dialog.png"),
        ("Curves", "phase6_curves_dialog.png"),
        ("Color Balance", "phase6_color_balance_dialog.png"),
    ):
        layer = next(
            item for item in advanced_document.layers if item.name == layer_name
        )
        dialog = AdjustmentLayerDialog(
            layer.adjustment,
            window,
            preview=window._adjustment_preview_source(layer),
            editing=True,
        )
        dialog.show()
        app.processEvents()
        dialog_path = OUTPUT_DIR / file_name
        dialog.grab().save(str(dialog_path))
        print("saved", dialog_path)
        dialog.close()

    levels_layer = next(
        item for item in advanced_document.layers if item.name == "Levels"
    )
    auto_dialog = AdjustmentLayerDialog(
        levels_layer.adjustment,
        window,
        preview=window._adjustment_preview_source(levels_layer),
        editing=True,
    )
    auto_dialog.auto_levels_button.click()
    auto_dialog.show()
    app.processEvents()
    auto_path = OUTPUT_DIR / "phase6_levels_auto.png"
    auto_dialog.grab().save(str(auto_path))
    print("saved", auto_path)
    auto_dialog.close()

    curves_layer = next(
        item for item in advanced_document.layers if item.name == "Curves"
    )
    red_dialog = AdjustmentLayerDialog(
        curves_layer.adjustment,
        window,
        preview=window._adjustment_preview_source(curves_layer),
        editing=True,
    )
    red_dialog.curve_channel_combo.setCurrentIndex(1)
    red_dialog.show()
    app.processEvents()
    red_path = OUTPUT_DIR / "phase6_curves_red_channel.png"
    red_dialog.grab().save(str(red_path))
    print("saved", red_path)
    red_dialog.close()

    window._remove_view(advanced_view)
    advanced_document.mark_clean()

    groups_document = build_phase6_groups_document()
    window._add_document_tab(groups_document)
    app.processEvents()
    groups_view = window.current_view
    groups_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Layer Group: nhóm lồng nhau · Ctrl+G nhóm layer · Ctrl+Shift+G bỏ nhóm · "
        "Opacity/blend/mask áp lên cả nhóm."
    )
    app.processEvents()
    groups_path = OUTPUT_DIR / "phase6_layer_groups.png"
    window.grab().save(str(groups_path))
    print("saved", groups_path)

    badges = [
        layer
        for layer in groups_document.layers
        if layer.name.startswith("Huy hiệu ")
    ]
    groups_document.set_selected_layers(badges, active=badges[0])
    window._update_action_states()
    window._show_transient_message(
        "Giữ Shift + nhấp để chọn dải layer · Ctrl + nhấp để bật/tắt từng layer · "
        "xoá, nhân bản, khoá, opacity, gộp và Group Layers áp dụng cho cả vùng chọn."
    )
    app.processEvents()
    multi_path = OUTPUT_DIR / "phase6_layer_multi_select.png"
    window.grab().save(str(multi_path))
    print("saved", multi_path)

    window._remove_view(groups_view)
    groups_document.mark_clean()

    style_document, style_card = build_phase6_layer_style_document()
    window._add_document_tab(style_document)
    app.processEvents()
    style_view = window.current_view
    style_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Layer Style: chuột phải layer → Blending Options… mở hộp thoại "
        "hiệu ứng, Blend If, Fill Opacity, Knockout và preset."
    )
    app.processEvents()
    style_path = OUTPUT_DIR / "phase6_layer_style.png"
    window.grab().save(str(style_path))
    print("saved", style_path)

    style_dialog = LayerStyleDialog(window, style_document, style_card)
    style_dialog.effect_list.setCurrentRow(1)  # trang Drop Shadow
    style_dialog.show()
    app.processEvents()
    style_dialog_path = OUTPUT_DIR / "phase6_layer_style_dialog.png"
    style_dialog.grab().save(str(style_dialog_path))
    print("saved", style_dialog_path)
    style_dialog.close()

    window._remove_view(style_view)
    style_document.mark_clean()

    fill_smart_document, fill_layer, smart_layer = (
        build_phase6_fill_smart_document()
    )
    window._add_document_tab(fill_smart_document)
    app.processEvents()
    fill_smart_view = window.current_view
    fill_smart_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Layer tô gradient không giữ pixel · smart object xoay/lật không mất "
        "chi tiết · nhấp đôi layer để sửa."
    )
    app.processEvents()
    fill_smart_path = OUTPUT_DIR / "phase6_fill_smart.png"
    window.grab().save(str(fill_smart_path))
    print("saved", fill_smart_path)

    fill_dialog = FillDialog(fill_layer.fill_props, window, editing=True)
    fill_dialog.show()
    app.processEvents()
    fill_dialog_path = OUTPUT_DIR / "phase6_fill_dialog.png"
    fill_dialog.grab().save(str(fill_dialog_path))
    print("saved", fill_dialog_path)
    fill_dialog.close()

    smart_dialog = SmartObjectDialog(
        smart_layer.smart_source, smart_layer.smart_props, window
    )
    smart_dialog.show()
    app.processEvents()
    smart_dialog_path = OUTPUT_DIR / "phase6_smart_object_dialog.png"
    smart_dialog.grab().save(str(smart_dialog_path))
    print("saved", smart_dialog_path)
    smart_dialog.close()

    window._remove_view(fill_smart_view)
    fill_smart_document.mark_clean()

    batch_dir = Path(tempfile.mkdtemp(prefix="mps_batch_preview_"))
    batch_inputs = []
    for name, color in (
        ("hoang_hon.png", (216, 138, 82, 255)),
        ("bien_xanh.png", (64, 138, 206, 255)),
        ("pho_dem.png", (58, 62, 86, 255)),
    ):
        path = batch_dir / name
        export_image(path, np.full((90, 130, 4), color, np.uint8))
        batch_inputs.append(str(path))
    batch_store = PresetStore(batch_dir / "presets.sqlite3")
    action = BatchAction(
        name="Ảnh web 1600px",
        steps=(
            BatchStep("auto_levels"),
            BatchStep("resize_max", max_size=1600),
            BatchStep("unsharp_mask", amount=90, radius=1.2, threshold=4),
        ),
    )
    batch_store.save_action(action.name, action)
    batch_dialog = BatchDialog(
        window,
        preset_store=batch_store,
        start_directory=str(batch_dir),
        inputs=batch_inputs,
    )
    batch_dialog.set_steps(action.steps)
    batch_dialog.output_dir_edit.setText(str(batch_dir / "edited"))
    batch_dialog.action_combo.setCurrentIndex(
        batch_dialog.action_combo.findData(action.name)
    )
    batch_dialog._on_run()
    batch_dialog.show()
    app.processEvents()
    batch_path = OUTPUT_DIR / "phase6_batch_dialog.png"
    batch_dialog.grab().save(str(batch_path))
    print("saved", batch_path)
    batch_dialog.close()

    batch_store.save_adjustment(
        "Ấm hoàng hôn",
        AdjustmentProperties(
            kind="levels",
            levels_black=18,
            levels_white=238,
            levels_gamma=1.15,
        ),
    )
    preset_dialog = AdjustmentLayerDialog(
        AdjustmentProperties(kind="levels"),
        window,
        preset_store=batch_store,
    )
    preset_index = preset_dialog.preset_combo.findData("Ấm hoàng hôn")
    if preset_index >= 0:
        preset_dialog.preset_combo.setCurrentIndex(preset_index)
    preset_dialog.preset_name_edit.setText("Ấm hoàng hôn")
    preset_dialog.show()
    app.processEvents()
    preset_path = OUTPUT_DIR / "phase6_preset_library.png"
    preset_dialog.grab().save(str(preset_path))
    print("saved", preset_path)
    preset_dialog.close()

    tiles_document = build_phase6_tiles_document()
    window._add_document_tab(tiles_document)
    app.processEvents()
    tiles_view = window.current_view
    tiles_view.set_zoom(1.0, QPointF(0.0, 0.0))
    app.processEvents()
    window._update_action_states()
    window._show_transient_message(
        "Hiển thị theo ô 256 × 256: chỉ composite vùng nhìn thấy · zoom dưới 50% "
        "dùng ảnh preview thu nhỏ · thao tác chỉ vẽ lại đúng vùng đã đổi."
    )
    app.processEvents()
    tiles_path = OUTPUT_DIR / "phase6_tiles.png"
    window.grab().save(str(tiles_path))
    print("saved", tiles_path)

    window._remove_view(tiles_view)
    tiles_document.mark_clean()

    document.mark_clean()

    psd_path = build_phase6_psd_demo(OUTPUT_DIR / "demo_open.psd")
    window.open_paths([psd_path])
    app.processEvents()
    psd_view = window.current_view
    psd_view.fit_to_window()
    window._update_action_states()
    window._show_transient_message(
        "Mở file PSD: giữ layer, nhóm, mask, blend mode, opacity, chuyển hình chữ "
        "nhật vector thành layer hình khối và layer chữ thành văn bản chỉnh sửa "
        "được · file gốc không bao giờ bị ghi đè."
    )
    app.processEvents()
    psd_shot = OUTPUT_DIR / "phase6_psd_open.png"
    window.grab().save(str(psd_shot))
    print("saved", psd_shot)

    psd_document = psd_view.document
    text_layer = next(
        (layer for layer in psd_document.layers if layer.kind == LayerKind.TEXT),
        None,
    )
    if text_layer is not None:
        psd_document.set_active_layer(text_layer)
        window._update_action_states()
        window._show_transient_message(
            f"Layer chữ PSD '{text_layer.name}' được giữ dưới dạng văn bản: "
            "sửa nội dung, font, cỡ, màu, căn lề và uốn chữ ngay trong app."
        )
        app.processEvents()
        text_shot = OUTPUT_DIR / "phase6_psd_text.png"
        window.grab().save(str(text_shot))
        print("saved", text_shot)

    window._remove_view(psd_view)

    window.close()
    app.processEvents()
    (OUTPUT_DIR / "presets.sqlite3").unlink(missing_ok=True)
    app.quit()


if __name__ == "__main__":
    main()
