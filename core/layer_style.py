"""Layer Style: hoà trộn nâng cao và 10 hiệu ứng layer.

Mô hình dữ liệu bất biến (frozen dataclass) để dễ so sánh thay đổi và làm
Undo/Redo. Việc dựng hiệu ứng chạy thuần NumPy trên silhouette alpha của
layer, không phụ thuộc Qt, nên kiểm thử được ở chế độ offscreen.

Toàn bộ hiệu ứng được tính trên một vùng đệm đã nới rộng quanh dải cần vẽ
(``margin``) để blur không bị nối mép giữa các ô tile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar

import numpy as np

from core.filters import _box_blur_1d, _gaussian_box_radii
from core.layer import BLEND_MODE_IDS

EFFECT_KINDS: tuple[str, ...] = (
    "drop_shadow",
    "inner_shadow",
    "outer_glow",
    "inner_glow",
    "bevel_emboss",
    "satin",
    "color_overlay",
    "gradient_overlay",
    "pattern_overlay",
    "stroke",
)

EFFECT_LABELS: dict[str, str] = {
    "drop_shadow": "Drop Shadow",
    "inner_shadow": "Inner Shadow",
    "outer_glow": "Outer Glow",
    "inner_glow": "Inner Glow",
    "bevel_emboss": "Bevel & Emboss",
    "satin": "Satin",
    "color_overlay": "Color Overlay",
    "gradient_overlay": "Gradient Overlay",
    "pattern_overlay": "Pattern Overlay",
    "stroke": "Stroke",
}

PATTERN_KINDS: tuple[str, ...] = ("checker", "stripes", "dots", "grid")
PATTERN_LABELS: dict[str, str] = {
    "checker": "Ca-rô",
    "stripes": "Sọc chéo",
    "dots": "Chấm tròn",
    "grid": "Lưới",
}

KNOCKOUT_MODES: tuple[tuple[str, str], ...] = (
    ("none", "None"),
    ("shallow", "Shallow"),
    ("deep", "Deep"),
)
KNOCKOUT_IDS = [mode for mode, _ in KNOCKOUT_MODES]

BEVEL_STYLES: tuple[tuple[str, str], ...] = (
    ("inner", "Inner Bevel"),
    ("outer", "Outer Bevel"),
    ("emboss", "Emboss"),
    ("pillow", "Pillow Emboss"),
    ("stroke", "Stroke Emboss"),
)
BEVEL_STYLE_IDS = [style for style, _ in BEVEL_STYLES]
BEVEL_DIRECTIONS: tuple[tuple[str, str], ...] = (("up", "Up"), ("down", "Down"))
GLOW_SOURCES: tuple[tuple[str, str], ...] = (("edge", "Edge"), ("center", "Center"))
STROKE_POSITIONS: tuple[tuple[str, str], ...] = (
    ("outside", "Outside"),
    ("inside", "Inside"),
    ("center", "Center"),
)
STROKE_POSITION_IDS = [position for position, _ in STROKE_POSITIONS]

MAX_EFFECT_SIZE = 250.0
MAX_EFFECT_DISTANCE = 3000.0
MAX_EFFECT_MARGIN = 600


def _clamp(value: object, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Giá trị hiệu ứng phải là số.") from exc
    if math.isnan(number):
        raise ValueError("Giá trị hiệu ứng không hợp lệ.")
    return max(low, min(high, number))


def _color(value: object) -> tuple[int, int, int, int]:
    try:
        channels = tuple(int(channel) for channel in value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("Màu hiệu ứng phải có 4 thành phần RGBA.") from exc
    if len(channels) != 4:
        raise ValueError("Màu hiệu ứng phải có 4 thành phần RGBA.")
    return tuple(max(0, min(255, channel)) for channel in channels)  # type: ignore[return-value]


def _blend_mode(value: object) -> str:
    mode = str(value).lower()
    if mode not in BLEND_MODE_IDS:
        raise ValueError(f"Blend mode không hợp lệ: {value}")
    return mode


def _angle(value: object) -> float:
    return _clamp(value, -180.0, 360.0) % 360.0


class LayerEffect:
    """Lớp cơ sở cho mọi hiệu ứng layer."""

    kind: ClassVar[str] = ""
    enabled: bool = False

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - ghi đè
        raise NotImplementedError

    @property
    def summary(self) -> str:  # pragma: no cover - ghi đè
        return EFFECT_LABELS.get(self.kind, self.kind)


@dataclass(frozen=True)
class DropShadowSettings(LayerEffect):
    kind: ClassVar[str] = "drop_shadow"
    enabled: bool = False
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    blend_mode: str = "multiply"
    opacity: float = 0.75
    angle: float = 120.0
    distance: float = 5.0
    spread: float = 0.0
    size: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "angle", _angle(self.angle))
        object.__setattr__(self, "distance", _clamp(self.distance, 0.0, MAX_EFFECT_DISTANCE))
        object.__setattr__(self, "spread", _clamp(self.spread, 0.0, MAX_EFFECT_SIZE))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "angle": self.angle,
            "distance": self.distance,
            "spread": self.spread,
            "size": self.size,
        }

    @property
    def summary(self) -> str:
        return f"{EFFECT_LABELS[self.kind]} · {self.distance:g} px · {self.size:g} px"


@dataclass(frozen=True)
class InnerShadowSettings(LayerEffect):
    kind: ClassVar[str] = "inner_shadow"
    enabled: bool = False
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    blend_mode: str = "multiply"
    opacity: float = 0.6
    angle: float = 120.0
    distance: float = 5.0
    choke: float = 0.0
    size: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "angle", _angle(self.angle))
        object.__setattr__(self, "distance", _clamp(self.distance, 0.0, MAX_EFFECT_DISTANCE))
        object.__setattr__(self, "choke", _clamp(self.choke, 0.0, MAX_EFFECT_SIZE))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "angle": self.angle,
            "distance": self.distance,
            "choke": self.choke,
            "size": self.size,
        }


@dataclass(frozen=True)
class OuterGlowSettings(LayerEffect):
    kind: ClassVar[str] = "outer_glow"
    enabled: bool = False
    color: tuple[int, int, int, int] = (255, 255, 190, 255)
    blend_mode: str = "screen"
    opacity: float = 0.75
    spread: float = 0.0
    size: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "spread", _clamp(self.spread, 0.0, MAX_EFFECT_SIZE))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "spread": self.spread,
            "size": self.size,
        }


@dataclass(frozen=True)
class InnerGlowSettings(LayerEffect):
    kind: ClassVar[str] = "inner_glow"
    enabled: bool = False
    color: tuple[int, int, int, int] = (255, 255, 190, 255)
    blend_mode: str = "screen"
    opacity: float = 0.75
    choke: float = 0.0
    size: float = 5.0
    source: str = "edge"

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "choke", _clamp(self.choke, 0.0, MAX_EFFECT_SIZE))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))
        source = str(self.source).lower()
        if source not in ("edge", "center"):
            raise ValueError(f"Nguồn Inner Glow không hợp lệ: {self.source}")
        object.__setattr__(self, "source", source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "choke": self.choke,
            "size": self.size,
            "source": self.source,
        }


@dataclass(frozen=True)
class BevelSettings(LayerEffect):
    kind: ClassVar[str] = "bevel_emboss"
    enabled: bool = False
    style: str = "inner"
    depth: float = 100.0
    direction: str = "up"
    size: float = 5.0
    soften: float = 0.0
    angle: float = 120.0
    altitude: float = 30.0
    highlight_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    highlight_mode: str = "screen"
    highlight_opacity: float = 0.75
    shadow_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    shadow_mode: str = "multiply"
    shadow_opacity: float = 0.75

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        style = str(self.style).lower()
        if style not in BEVEL_STYLE_IDS:
            raise ValueError(f"Kiểu bevel không hợp lệ: {self.style}")
        object.__setattr__(self, "style", style)
        direction = str(self.direction).lower()
        if direction not in ("up", "down"):
            raise ValueError(f"Hướng bevel không hợp lệ: {self.direction}")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "depth", _clamp(self.depth, 0.0, 1000.0))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))
        object.__setattr__(self, "soften", _clamp(self.soften, 0.0, 100.0))
        object.__setattr__(self, "angle", _angle(self.angle))
        object.__setattr__(self, "altitude", _clamp(self.altitude, 0.0, 90.0))
        object.__setattr__(self, "highlight_color", _color(self.highlight_color))
        object.__setattr__(self, "highlight_mode", _blend_mode(self.highlight_mode))
        object.__setattr__(self, "highlight_opacity", _clamp(self.highlight_opacity, 0.0, 1.0))
        object.__setattr__(self, "shadow_color", _color(self.shadow_color))
        object.__setattr__(self, "shadow_mode", _blend_mode(self.shadow_mode))
        object.__setattr__(self, "shadow_opacity", _clamp(self.shadow_opacity, 0.0, 1.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "style": self.style,
            "depth": self.depth,
            "direction": self.direction,
            "size": self.size,
            "soften": self.soften,
            "angle": self.angle,
            "altitude": self.altitude,
            "highlight_color": list(self.highlight_color),
            "highlight_mode": self.highlight_mode,
            "highlight_opacity": self.highlight_opacity,
            "shadow_color": list(self.shadow_color),
            "shadow_mode": self.shadow_mode,
            "shadow_opacity": self.shadow_opacity,
        }


@dataclass(frozen=True)
class SatinSettings(LayerEffect):
    kind: ClassVar[str] = "satin"
    enabled: bool = False
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    blend_mode: str = "multiply"
    opacity: float = 0.5
    angle: float = 19.0
    distance: float = 11.0
    size: float = 14.0
    invert: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "angle", _angle(self.angle))
        object.__setattr__(self, "distance", _clamp(self.distance, 0.0, MAX_EFFECT_DISTANCE))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))
        object.__setattr__(self, "invert", bool(self.invert))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "angle": self.angle,
            "distance": self.distance,
            "size": self.size,
            "invert": self.invert,
        }


@dataclass(frozen=True)
class ColorOverlaySettings(LayerEffect):
    kind: ClassVar[str] = "color_overlay"
    enabled: bool = False
    color: tuple[int, int, int, int] = (255, 0, 0, 255)
    blend_mode: str = "normal"
    opacity: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
        }


@dataclass(frozen=True)
class GradientOverlaySettings(LayerEffect):
    kind: ClassVar[str] = "gradient_overlay"
    enabled: bool = False
    start_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    end_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    blend_mode: str = "normal"
    opacity: float = 1.0
    angle: float = 90.0
    scale: float = 100.0
    reverse: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "start_color", _color(self.start_color))
        object.__setattr__(self, "end_color", _color(self.end_color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "angle", _angle(self.angle))
        object.__setattr__(self, "scale", _clamp(self.scale, 10.0, 400.0))
        object.__setattr__(self, "reverse", bool(self.reverse))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "start_color": list(self.start_color),
            "end_color": list(self.end_color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "angle": self.angle,
            "scale": self.scale,
            "reverse": self.reverse,
        }


@dataclass(frozen=True)
class PatternOverlaySettings(LayerEffect):
    kind: ClassVar[str] = "pattern_overlay"
    enabled: bool = False
    pattern: str = "checker"
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    background: tuple[int, int, int, int] = (255, 255, 255, 255)
    blend_mode: str = "normal"
    opacity: float = 1.0
    scale: float = 100.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        pattern = str(self.pattern).lower()
        if pattern not in PATTERN_KINDS:
            raise ValueError(f"Hoa văn không hợp lệ: {self.pattern}")
        object.__setattr__(self, "pattern", pattern)
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "background", _color(self.background))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))
        object.__setattr__(self, "scale", _clamp(self.scale, 25.0, 400.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "pattern": self.pattern,
            "color": list(self.color),
            "background": list(self.background),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "scale": self.scale,
        }


@dataclass(frozen=True)
class StrokeSettings(LayerEffect):
    kind: ClassVar[str] = "stroke"
    enabled: bool = False
    size: float = 3.0
    position: str = "outside"
    color: tuple[int, int, int, int] = (255, 0, 0, 255)
    blend_mode: str = "normal"
    opacity: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "size", _clamp(self.size, 0.0, MAX_EFFECT_SIZE))
        position = str(self.position).lower()
        if position not in STROKE_POSITION_IDS:
            raise ValueError(f"Vị trí stroke không hợp lệ: {self.position}")
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "blend_mode", _blend_mode(self.blend_mode))
        object.__setattr__(self, "opacity", _clamp(self.opacity, 0.0, 1.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enabled": self.enabled,
            "size": self.size,
            "position": self.position,
            "color": list(self.color),
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
        }


EFFECT_CLASSES: dict[str, type[LayerEffect]] = {
    effect.kind: effect
    for effect in (
        DropShadowSettings,
        InnerShadowSettings,
        OuterGlowSettings,
        InnerGlowSettings,
        BevelSettings,
        SatinSettings,
        ColorOverlaySettings,
        GradientOverlaySettings,
        PatternOverlaySettings,
        StrokeSettings,
    )
}


def default_effect(kind: str) -> LayerEffect:
    cls = EFFECT_CLASSES.get(kind)
    if cls is None:
        raise ValueError(f"Hiệu ứng không hợp lệ: {kind}")
    return cls()


def effect_from_dict(data: object) -> LayerEffect:
    if not isinstance(data, dict):
        raise ValueError("Dữ liệu hiệu ứng layer không hợp lệ.")
    kind = str(data.get("kind", ""))
    cls = EFFECT_CLASSES.get(kind)
    if cls is None:
        raise ValueError(f"Hiệu ứng không hợp lệ: {kind}")
    values = {key: value for key, value in data.items() if key != "kind"}
    try:
        return cls(**values)
    except TypeError as exc:
        raise ValueError(f"Dữ liệu hiệu ứng '{kind}' không hợp lệ.") from exc


# ------------------------------------------------------------------ Blend If
def _smoothstep(low: np.ndarray | float, high: np.ndarray | float, x: np.ndarray):
    if isinstance(low, np.ndarray) or isinstance(high, np.ndarray):
        span = np.maximum(np.asarray(high, np.float32) - np.asarray(low, np.float32), 1e-6)
        t = np.clip((x - low) / span, 0.0, 1.0)
    else:
        if high <= low:
            return (x >= low).astype(np.float32)
        t = np.clip((x - low) / (high - low), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


@dataclass(frozen=True)
class BlendChannelRange:
    """Dải hiển thị của một kênh: hai tay nắm đen và hai tay nắm trắng (0..255)."""

    black_low: int = 0
    black_high: int = 0
    white_low: int = 255
    white_high: int = 255

    def __post_init__(self) -> None:
        values = []
        for name in ("black_low", "black_high", "white_low", "white_high"):
            try:
                values.append(int(getattr(self, name)))
            except (TypeError, ValueError) as exc:
                raise ValueError("Dải Blend If phải là số nguyên.") from exc
        values = [max(0, min(255, value)) for value in values]
        low_black, high_black, low_white, high_white = values
        if high_black < low_black:
            high_black = low_black
        if low_white < high_black:
            low_white = high_black
        if high_white < low_white:
            high_white = low_white
        object.__setattr__(self, "black_low", low_black)
        object.__setattr__(self, "black_high", high_black)
        object.__setattr__(self, "white_low", low_white)
        object.__setattr__(self, "white_high", high_white)

    @property
    def is_identity(self) -> bool:
        return (
            self.black_low == 0
            and self.black_high == 0
            and self.white_low == 255
            and self.white_high == 255
        )

    def weight(self, values: np.ndarray) -> np.ndarray:
        low = self.black_low / 255.0
        low_high = self.black_high / 255.0
        high_low = self.white_low / 255.0
        high = self.white_high / 255.0
        result = np.ones_like(values, dtype=np.float32)
        if low_high > low:
            result *= _smoothstep(low, low_high, values)
        elif low > 0.0:
            result *= (values >= low).astype(np.float32)
        if high > high_low:
            result *= 1.0 - _smoothstep(high_low, high, values)
        elif high < 1.0:
            result *= (values <= high).astype(np.float32)
        return result

    def to_dict(self) -> dict[str, int]:
        return {
            "black_low": self.black_low,
            "black_high": self.black_high,
            "white_low": self.white_low,
            "white_high": self.white_high,
        }

    @classmethod
    def from_dict(cls, data: object) -> "BlendChannelRange":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("Dải Blend If không hợp lệ.")
        try:
            return cls(
                black_low=data.get("black_low", 0),
                black_high=data.get("black_high", 0),
                white_low=data.get("white_low", 255),
                white_high=data.get("white_high", 255),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Dải Blend If không hợp lệ.") from exc


_IDENTITY_RANGE = BlendChannelRange()
BLEND_IF_CHANNELS: tuple[tuple[str, str], ...] = (
    ("gray", "Gray"),
    ("red", "R"),
    ("green", "G"),
    ("blue", "B"),
)


def _channel_array(rgb: np.ndarray, channel: int) -> np.ndarray:
    if channel == 0:
        return (
            0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
        ).astype(np.float32)
    return rgb[..., channel - 1].astype(np.float32)


def _ranges(value: object) -> tuple[BlendChannelRange, ...]:
    if value is None:
        return (_IDENTITY_RANGE,) * 4
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("Blend If cần đúng 4 kênh (Gray, R, G, B).")
    return tuple(
        item if isinstance(item, BlendChannelRange) else BlendChannelRange.from_dict(item)
        for item in value
    )


@dataclass(frozen=True)
class BlendIf:
    """Điều kiện hiển thị theo kênh của layer này và layer nền bên dưới."""

    this_layer: tuple[BlendChannelRange, ...] = (_IDENTITY_RANGE,) * 4
    underlying: tuple[BlendChannelRange, ...] = (_IDENTITY_RANGE,) * 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "this_layer", _ranges(self.this_layer))
        object.__setattr__(self, "underlying", _ranges(self.underlying))

    @property
    def is_identity(self) -> bool:
        return all(item.is_identity for item in self.this_layer) and all(
            item.is_identity for item in self.underlying
        )

    def weights(
        self,
        source_rgb: np.ndarray,
        backdrop_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        """Hệ số alpha tổng hợp của mọi kênh có dải khác mặc định."""
        weight = np.ones(source_rgb.shape[:2], dtype=np.float32)
        for index in range(len(BLEND_IF_CHANNELS)):
            source_range = self.this_layer[index]
            if not source_range.is_identity:
                weight *= source_range.weight(_channel_array(source_rgb, index))
            under_range = self.underlying[index]
            if backdrop_rgb is not None and not under_range.is_identity:
                weight *= under_range.weight(_channel_array(backdrop_rgb, index))
        return weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "this_layer": [item.to_dict() for item in self.this_layer],
            "underlying": [item.to_dict() for item in self.underlying],
        }

    @classmethod
    def from_dict(cls, data: object) -> "BlendIf":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu Blend If không hợp lệ.")
        return cls(
            this_layer=_ranges(data.get("this_layer")),
            underlying=_ranges(data.get("underlying")),
        )


# --------------------------------------------------------------- Layer style
@dataclass(frozen=True)
class LayerStyle:
    """Thuộc tính Blending Options nâng cao và danh sách hiệu ứng của layer."""

    fill_opacity: float = 1.0
    knockout: str = "none"
    blend_interior_as_group: bool = False
    blend_clipped_as_group: bool = False
    transparency_shapes_layer: bool = True
    layer_mask_hides_effects: bool = True
    vector_mask_hides_effects: bool = True
    blend_if: BlendIf = field(default_factory=BlendIf)
    effects: tuple[LayerEffect, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill_opacity", _clamp(self.fill_opacity, 0.0, 1.0))
        knockout = str(self.knockout).lower()
        if knockout not in KNOCKOUT_IDS:
            raise ValueError(f"Knockout không hợp lệ: {self.knockout}")
        object.__setattr__(self, "knockout", knockout)
        for name in (
            "blend_interior_as_group",
            "blend_clipped_as_group",
            "transparency_shapes_layer",
            "layer_mask_hides_effects",
            "vector_mask_hides_effects",
        ):
            object.__setattr__(self, name, bool(getattr(self, name)))
        blend_if = self.blend_if
        if not isinstance(blend_if, BlendIf):
            blend_if = BlendIf.from_dict(blend_if)
        object.__setattr__(self, "blend_if", blend_if)
        effects: list[LayerEffect] = []
        seen: set[str] = set()
        for item in self.effects or ():
            effect = item if isinstance(item, LayerEffect) else effect_from_dict(item)
            if effect.kind in seen:
                continue
            seen.add(effect.kind)
            effects.append(effect)
        order = {kind: index for index, kind in enumerate(EFFECT_KINDS)}
        effects.sort(key=lambda entry: order.get(entry.kind, 999))
        object.__setattr__(self, "effects", tuple(effects))

    # ---------------------------------------------------------------- truy vấn
    def effect(self, kind: str) -> LayerEffect | None:
        for item in self.effects:
            if item.kind == kind:
                return item
        return None

    def with_effect(self, effect: LayerEffect) -> "LayerStyle":
        effects = [item for item in self.effects if item.kind != effect.kind]
        effects.append(effect)
        return replace(self, effects=tuple(effects))

    @property
    def enabled_effects(self) -> tuple[LayerEffect, ...]:
        return tuple(item for item in self.effects if item.enabled)

    @property
    def has_effects(self) -> bool:
        return bool(self.enabled_effects)

    @property
    def is_identity(self) -> bool:
        return (
            self.fill_opacity >= 0.999
            and self.knockout == "none"
            and not self.blend_interior_as_group
            and not self.blend_clipped_as_group
            and self.transparency_shapes_layer
            and self.layer_mask_hides_effects
            and self.vector_mask_hides_effects
            and self.blend_if.is_identity
            and not self.has_effects
        )

    def summary(self) -> str:
        names = [EFFECT_LABELS[item.kind] for item in self.enabled_effects]
        parts: list[str] = []
        if names:
            parts.append(", ".join(names))
        if self.fill_opacity < 0.999:
            parts.append(f"Fill {round(self.fill_opacity * 100)}%")
        if self.knockout != "none":
            parts.append(f"Knockout {self.knockout}")
        if not self.blend_if.is_identity:
            parts.append("Blend If")
        return " · ".join(parts) or "Layer Style"

    # ------------------------------------------------------------- chuyển đổi
    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_opacity": self.fill_opacity,
            "knockout": self.knockout,
            "blend_interior_as_group": self.blend_interior_as_group,
            "blend_clipped_as_group": self.blend_clipped_as_group,
            "transparency_shapes_layer": self.transparency_shapes_layer,
            "layer_mask_hides_effects": self.layer_mask_hides_effects,
            "vector_mask_hides_effects": self.vector_mask_hides_effects,
            "blend_if": self.blend_if.to_dict(),
            "effects": [item.to_dict() for item in self.effects],
        }

    @classmethod
    def from_dict(cls, data: object) -> "LayerStyle":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu layer style không hợp lệ.")
        effects = data.get("effects", [])
        if not isinstance(effects, list):
            raise ValueError("Danh sách hiệu ứng layer không hợp lệ.")
        try:
            return cls(
                fill_opacity=data.get("fill_opacity", 1.0),
                knockout=data.get("knockout", "none"),
                blend_interior_as_group=data.get("blend_interior_as_group", False),
                blend_clipped_as_group=data.get("blend_clipped_as_group", False),
                transparency_shapes_layer=data.get("transparency_shapes_layer", True),
                layer_mask_hides_effects=data.get("layer_mask_hides_effects", True),
                vector_mask_hides_effects=data.get("vector_mask_hides_effects", True),
                blend_if=BlendIf.from_dict(data.get("blend_if")),
                effects=tuple(effect_from_dict(item) for item in effects),
            )
        except ValueError:
            raise
        except (TypeError, AttributeError) as exc:
            raise ValueError("Dữ liệu layer style không hợp lệ.") from exc


# ------------------------------------------------------- dựng hiệu ứng (NumPy)
@dataclass(frozen=True)
class EffectPass:
    """Một lớp vẽ hiệu ứng: RGBA thẳng alpha trong toạ độ vùng đệm."""

    kind: str
    rgba: np.ndarray
    blend_mode: str
    below: bool


def effect_margin(style: LayerStyle | None) -> int:
    if style is None:
        return 0
    margin = 0.0
    for effect in style.enabled_effects:
        if isinstance(effect, DropShadowSettings):
            margin = max(margin, effect.distance + effect.spread + effect.size * 3.0)
        elif isinstance(effect, InnerShadowSettings):
            margin = max(margin, effect.distance + effect.choke + effect.size * 3.0)
        elif isinstance(effect, (OuterGlowSettings, InnerGlowSettings)):
            margin = max(margin, effect.spread + effect.size * 3.0)
            if isinstance(effect, InnerGlowSettings):
                margin = max(margin, effect.choke + effect.size * 3.0)
        elif isinstance(effect, BevelSettings):
            margin = max(margin, effect.size * 3.0 + effect.soften * 2.0)
        elif isinstance(effect, SatinSettings):
            margin = max(margin, effect.distance + effect.size * 3.0)
        elif isinstance(effect, StrokeSettings):
            margin = max(margin, effect.size + 2.0)
    if margin <= 0.0:
        return 0
    return int(min(MAX_EFFECT_MARGIN, math.ceil(margin) + 2))


def _zero_shift(array: np.ndarray, dx: int, dy: int) -> np.ndarray:
    height, width = array.shape[:2]
    output = np.zeros_like(array)
    if abs(dx) >= width or abs(dy) >= height:
        return output
    src_x0 = max(0, -dx)
    src_x1 = min(width, width - dx)
    dst_x0 = max(0, dx)
    dst_x1 = min(width, width + dx)
    src_y0 = max(0, -dy)
    src_y1 = min(height, height - dy)
    dst_y0 = max(0, dy)
    dst_y1 = min(height, height + dy)
    if src_x1 <= src_x0 or src_y1 <= src_y0:
        return output
    output[dst_y0:dst_y1, dst_x0:dst_x1] = array[src_y0:src_y1, src_x0:src_x1]
    return output


def _blur(array: np.ndarray, radius: float) -> np.ndarray:
    radius = float(radius)
    if radius <= 0.05:
        return array
    work = array.astype(np.float32, copy=True)
    for box_radius in _gaussian_box_radii(radius):
        work = _box_blur_1d(work, box_radius, 1)
        work = _box_blur_1d(work, box_radius, 0)
    return work.astype(np.float32)


def _dilate_step(mask: np.ndarray, step: int) -> np.ndarray:
    height, width = mask.shape
    output = mask.copy()
    if step < height:
        output[step:, :] = np.maximum(output[step:, :], mask[:-step, :])
        output[:-step, :] = np.maximum(output[:-step, :], mask[step:, :])
    if step < width:
        output[:, step:] = np.maximum(output[:, step:], mask[:, :-step])
        output[:, :-step] = np.maximum(output[:, :-step], mask[:, step:])
    return output


def _dilate(mask: np.ndarray, radius: float) -> np.ndarray:
    radius = int(round(float(radius)))
    if radius <= 0:
        return mask
    output = mask
    step = 1
    remaining = radius
    while remaining:
        if remaining & 1:
            output = _dilate_step(output, step)
        remaining >>= 1
        step <<= 1
    return output


def _erode(mask: np.ndarray, radius: float) -> np.ndarray:
    return 1.0 - _dilate(1.0 - mask, radius)


def _pack(color: tuple[int, int, int, int], alpha: np.ndarray) -> np.ndarray:
    output = np.empty(alpha.shape + (4,), dtype=np.float32)
    output[..., 0] = color[0] / 255.0
    output[..., 1] = color[1] / 255.0
    output[..., 2] = color[2] / 255.0
    output[..., 3] = np.clip(alpha * (color[3] / 255.0), 0.0, 1.0)
    return output


def _box_coverage(
    rect: tuple[int, int, int, int],
    bounds: tuple[int, int, int, int],
) -> np.ndarray:
    x0, y0, x1, y1 = rect
    bx0, by0, bx1, by1 = bounds
    coverage = np.zeros((y1 - y0, x1 - x0), dtype=np.float32)
    ix0 = max(x0, bx0)
    iy0 = max(y0, by0)
    ix1 = min(x1, bx1)
    iy1 = min(y1, by1)
    if ix1 > ix0 and iy1 > iy0:
        coverage[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] = 1.0
    return coverage


def _offset_bounds(
    layer_bounds: tuple[int, int, int, int],
    margin: int,
    canvas_width: int,
    canvas_height: int,
) -> tuple[int, int, int, int]:
    lx0, ly0, lx1, ly1 = layer_bounds
    x0 = max(0, lx0 - margin)
    y0 = max(0, ly0 - margin)
    x1 = min(canvas_width, lx1 + margin)
    y1 = min(canvas_height, ly1 + margin)
    return x0, y0, x1, y1


def _drop_shadow_pass(effect: DropShadowSettings, alpha, rect) -> EffectPass:
    radians = math.radians(effect.angle)
    dx = int(round(-math.cos(radians) * effect.distance))
    dy = int(round(math.sin(radians) * effect.distance))
    silhouette = _zero_shift(alpha, dx, dy)
    silhouette = _dilate(silhouette, effect.spread)
    silhouette = _blur(silhouette, effect.size)
    return EffectPass(effect.kind, _pack(effect.color, silhouette * effect.opacity), effect.blend_mode, True)


def _outer_glow_pass(effect: OuterGlowSettings, alpha, rect) -> EffectPass:
    glow = _dilate(alpha, effect.spread)
    glow = _blur(glow, effect.size)
    glow = np.clip(glow - alpha, 0.0, 1.0)
    return EffectPass(effect.kind, _pack(effect.color, glow * effect.opacity), effect.blend_mode, True)


def _inner_shadow_pass(effect: InnerShadowSettings, alpha, rect) -> EffectPass:
    radians = math.radians(effect.angle)
    dx = int(round(-math.cos(radians) * effect.distance))
    dy = int(round(math.sin(radians) * effect.distance))
    inverse = _zero_shift(1.0 - alpha, dx, dy)
    inverse = _dilate(inverse, effect.choke)
    shadow = _blur(inverse, effect.size) * alpha
    return EffectPass(effect.kind, _pack(effect.color, shadow * effect.opacity), effect.blend_mode, False)


def _inner_glow_pass(
    effect: InnerGlowSettings, alpha, rect, shape_mask: np.ndarray
) -> EffectPass:
    if effect.source == "center":
        glow = _blur(alpha, effect.size)
    else:
        glow = _dilate(alpha, effect.choke)
        glow = _blur(glow, effect.size)
    glow = np.clip(glow * shape_mask, 0.0, 1.0)
    return EffectPass(effect.kind, _pack(effect.color, glow * effect.opacity), effect.blend_mode, False)


def _bevel_passes(
    effect: BevelSettings, alpha, rect, shape_mask: np.ndarray
) -> list[EffectPass]:
    smooth = _blur(alpha, max(1.0, effect.size))
    gradient_y, gradient_x = np.gradient(smooth)
    radians = math.radians(effect.angle)
    altitude = math.radians(effect.altitude)
    light_x = math.cos(radians) * math.cos(altitude)
    light_y = math.sin(radians) * math.cos(altitude)
    light_z = math.sin(altitude)
    shade = -(gradient_x * light_x + gradient_y * light_y + light_z * 0.0)
    if effect.direction == "down":
        shade = -shade
    strength = 4.0 + effect.depth / 100.0 * 16.0
    highlight = np.clip(shade * strength, 0.0, 1.0)
    shadow = np.clip(-shade * strength, 0.0, 1.0)
    if effect.soften > 0.0:
        highlight = _blur(highlight, effect.soften)
        shadow = _blur(shadow, effect.soften)
    if effect.style == "outer":
        ring = np.clip(_dilate(alpha, effect.size) - alpha, 0.0, 1.0)
        highlight *= ring
        shadow *= ring
    elif effect.style == "stroke":
        ring = np.clip(alpha - _erode(alpha, effect.size), 0.0, 1.0)
        highlight *= ring
        shadow *= ring
    else:
        highlight *= shape_mask
        shadow *= shape_mask
    passes: list[EffectPass] = []
    passes.append(
        EffectPass(
            effect.kind + ":shadow",
            _pack(effect.shadow_color, shadow * effect.shadow_opacity),
            effect.shadow_mode,
            False,
        )
    )
    passes.append(
        EffectPass(
            effect.kind + ":highlight",
            _pack(effect.highlight_color, highlight * effect.highlight_opacity),
            effect.highlight_mode,
            False,
        )
    )
    return passes


def _satin_pass(effect: SatinSettings, alpha, rect, shape_mask: np.ndarray) -> EffectPass:
    radians = math.radians(effect.angle)
    dx = int(round(math.cos(radians) * effect.distance))
    dy = int(round(math.sin(radians) * effect.distance))
    smooth = _blur(alpha, max(1.0, effect.size))
    shifted = _zero_shift(smooth, dx, dy)
    difference = (smooth - shifted) if not effect.invert else (shifted - smooth)
    shade = np.clip(difference * 4.0, 0.0, 1.0) * shape_mask
    return EffectPass(effect.kind, _pack(effect.color, shade * effect.opacity), effect.blend_mode, False)


def _color_overlay_pass(effect: ColorOverlaySettings, alpha, rect, shape_mask) -> EffectPass:
    return EffectPass(effect.kind, _pack(effect.color, shape_mask * effect.opacity), effect.blend_mode, False)


def _gradient_overlay_pass(
    effect: GradientOverlaySettings,
    rect: tuple[int, int, int, int],
    bounds: tuple[int, int, int, int],
    shape_mask: np.ndarray,
) -> EffectPass:
    x0, y0, x1, y1 = rect
    xs = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
    ys = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
    bx0, by0, bx1, by1 = bounds
    center_x = (bx0 + bx1) * 0.5
    center_y = (by0 + by1) * 0.5
    radians = math.radians(effect.angle)
    direction_x = math.cos(radians)
    direction_y = math.sin(radians)
    # Chiếu toạ độ lên hướng gradient, chuẩn hoá theo kích thước hộp layer.
    extent = max(1.0, abs(direction_x) * (bx1 - bx0) + abs(direction_y) * (by1 - by0))
    extent /= max(0.01, effect.scale / 100.0)
    projection = ((xs - center_x) * direction_x + (ys - center_y) * direction_y) / extent + 0.5
    ramp = np.clip(projection, 0.0, 1.0)
    if effect.reverse:
        ramp = 1.0 - ramp
    alpha_array = np.empty(ramp.shape + (4,), dtype=np.float32)
    start = np.array(effect.start_color[:3], dtype=np.float32) / 255.0
    end = np.array(effect.end_color[:3], dtype=np.float32) / 255.0
    for channel in range(3):
        alpha_array[..., channel] = start[channel] + (end[channel] - start[channel]) * ramp
    start_alpha = effect.start_color[3] / 255.0
    end_alpha = effect.end_color[3] / 255.0
    alpha_channel = start_alpha + (end_alpha - start_alpha) * ramp
    alpha_array[..., 3] = np.clip(alpha_channel * shape_mask * effect.opacity, 0.0, 1.0)
    return EffectPass(effect.kind, alpha_array, effect.blend_mode, False)


def _pattern_overlay_pass(
    effect: PatternOverlaySettings,
    rect: tuple[int, int, int, int],
    shape_mask: np.ndarray,
) -> EffectPass:
    x0, y0, x1, y1 = rect
    xs = np.arange(x0, x1, dtype=np.int32)[None, :]
    ys = np.arange(y0, y1, dtype=np.int32)[:, None]
    cell = max(2, int(round(16.0 * effect.scale / 100.0)))
    if effect.pattern == "checker":
        mask = ((xs // cell + ys // cell) % 2).astype(bool) * np.ones((len(ys), 1), bool)
    elif effect.pattern == "stripes":
        mask = (((xs + ys) // cell) % 2).astype(bool) * np.ones((len(ys), 1), bool)
    elif effect.pattern == "dots":
        cx = (xs % cell) - cell / 2.0
        cy = (ys % cell) - cell / 2.0
        mask = (cx * cx + cy * cy) <= (cell * 0.3) ** 2
    else:  # grid
        mask = ((xs % cell) < max(1, cell // 8)) | ((ys % cell) < max(1, cell // 8))
    mask = np.broadcast_to(mask, (y1 - y0, x1 - x0))
    foreground = np.array(effect.color[:3], dtype=np.float32) / 255.0
    background = np.array(effect.background[:3], dtype=np.float32) / 255.0
    rgb = np.where(mask[..., None], foreground, background)
    alpha = shape_mask * effect.opacity
    out = np.empty(rgb.shape[:2] + (4,), dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = np.clip(alpha, 0.0, 1.0)
    return EffectPass(effect.kind, out, effect.blend_mode, False)


def _stroke_pass(effect: StrokeSettings, alpha) -> EffectPass:
    size = max(1.0, effect.size)
    if effect.position == "inside":
        band = alpha - _erode(alpha, size)
    elif effect.position == "center":
        half = size * 0.5
        band = _dilate(alpha, half) - _erode(alpha, half)
    else:
        band = _dilate(alpha, size) - alpha
    band = _blur(np.clip(band, 0.0, 1.0), max(0.6, size * 0.12))
    return EffectPass(effect.kind, _pack(effect.color, band * effect.opacity), effect.blend_mode, False)


def render_effect_passes(
    style: LayerStyle,
    alpha: np.ndarray,
    rect: tuple[int, int, int, int],
    layer_bounds: tuple[int, int, int, int],
) -> list[EffectPass]:
    """Dựng mọi hiệu ứng đang bật trên vùng đệm ``rect``.

    ``alpha`` là silhouette (0..1) cùng kích thước với ``rect``. Trả về danh
    sách pass theo thứ tự vẽ: pass ``below`` trước nội dung layer, còn lại sau.
    """
    passes: list[EffectPass] = []
    if alpha.size == 0 or not style.has_effects:
        return passes
    alpha = np.clip(alpha.astype(np.float32), 0.0, 1.0)
    box = _box_coverage(rect, layer_bounds)
    shape_mask = alpha if style.transparency_shapes_layer else box
    below: list[EffectPass] = []
    above: list[EffectPass] = []
    for effect in style.effects:
        if not effect.enabled:
            continue
        if isinstance(effect, DropShadowSettings):
            below.append(_drop_shadow_pass(effect, alpha, rect))
        elif isinstance(effect, OuterGlowSettings):
            below.append(_outer_glow_pass(effect, alpha, rect))
        elif isinstance(effect, InnerShadowSettings):
            above.append(_inner_shadow_pass(effect, alpha, rect))
        elif isinstance(effect, InnerGlowSettings):
            above.append(_inner_glow_pass(effect, alpha, rect, shape_mask))
        elif isinstance(effect, BevelSettings):
            above.extend(_bevel_passes(effect, alpha, rect, shape_mask))
        elif isinstance(effect, SatinSettings):
            # Satin vẽ bên dưới nội dung nhưng trên các hiệu ứng ngoài.
            above.append(_satin_pass(effect, alpha, rect, shape_mask))
        elif isinstance(effect, ColorOverlaySettings):
            above.append(_color_overlay_pass(effect, alpha, rect, shape_mask))
        elif isinstance(effect, GradientOverlaySettings):
            above.append(_gradient_overlay_pass(effect, rect, layer_bounds, shape_mask))
        elif isinstance(effect, PatternOverlaySettings):
            above.append(_pattern_overlay_pass(effect, rect, shape_mask))
        elif isinstance(effect, StrokeSettings):
            above.append(_stroke_pass(effect, alpha))
    passes.extend(below)
    passes.extend(above)
    return passes


def identity_style() -> LayerStyle:
    return LayerStyle()
