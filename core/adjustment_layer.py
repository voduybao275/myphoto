"""Layer điều chỉnh không phá huỷ: thuộc tính và phép biến đổi màu."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from core.filters import _hsl_to_rgb, _rgb_to_hsl

ADJUSTMENT_KINDS = (
    "brightness_contrast",
    "hue_saturation",
    "invert",
    "desaturate",
    "levels",
    "curves",
    "color_balance",
)
ADJUSTMENT_LABELS = {
    "brightness_contrast": "Brightness/Contrast",
    "hue_saturation": "Hue/Saturation",
    "invert": "Invert",
    "desaturate": "Desaturate",
    "levels": "Levels",
    "curves": "Curves",
    "color_balance": "Color Balance",
}
MAX_BRIGHTNESS = 100
MAX_CONTRAST = 100
MAX_HUE_SHIFT = 180
MAX_SATURATION = 100
MAX_LIGHTNESS = 100
MAX_GAMMA = 9.99
MIN_GAMMA = 0.1
MAX_CURVE_POINTS = 16
MIN_CURVE_POINTS = 2
DEFAULT_CURVE_POINTS = ((0, 0), (255, 255))
CURVE_CHANNELS = ("rgb", "red", "green", "blue")
AUTO_LEVELS_CLIP_PERCENT = 0.5


def _clamp_int(value: object, minimum: int, maximum: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("Tham số điều chỉnh phải là số nguyên.") from exc
    return max(minimum, min(maximum, number))


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("Tham số điều chỉnh phải là số.") from exc
    if not math.isfinite(number):
        raise ValueError("Tham số điều chỉnh phải là số hữu hạn.")
    return max(minimum, min(maximum, number))


def _normalize_curve_points(
    value: object,
) -> tuple[tuple[int, int], ...]:
    if value is None:
        return DEFAULT_CURVE_POINTS
    try:
        pairs = list(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            "Điểm đường cong phải là danh sách cặp toạ độ."
        ) from exc
    if not MIN_CURVE_POINTS <= len(pairs) <= MAX_CURVE_POINTS:
        raise ValueError(
            f"Đường cong cần từ {MIN_CURVE_POINTS} đến {MAX_CURVE_POINTS} điểm."
        )
    points: list[tuple[int, int]] = []
    for pair in pairs:
        try:
            x, y = pair  # type: ignore[misc]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Mỗi điểm đường cong phải là cặp (x, y)."
            ) from exc
        points.append((_clamp_int(x, 0, 255), _clamp_int(y, 0, 255)))
    points.sort()
    for previous, current in zip(points, points[1:]):
        if previous[0] == current[0]:
            raise ValueError("Điểm đường cong phải có hoành độ khác nhau.")
    return tuple(points)


def _normalize_balance(value: object) -> tuple[int, int, int]:
    if value is None:
        return (0, 0, 0)
    try:
        channels = list(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError("Giá trị Color Balance phải gồm 3 số.") from exc
    if len(channels) != 3:
        raise ValueError("Giá trị Color Balance phải gồm 3 số.")
    return (
        _clamp_int(channels[0], -100, 100),
        _clamp_int(channels[1], -100, 100),
        _clamp_int(channels[2], -100, 100),
    )


def _format_triple(values: tuple[int, int, int]) -> str:
    return f"{values[0]:+d}/{values[1]:+d}/{values[2]:+d}"


@dataclass(frozen=True)
class AdjustmentProperties:
    """Tham số của một layer điều chỉnh (bất biến để chia sẻ với history)."""

    kind: str = "brightness_contrast"
    brightness: int = 0
    contrast: int = 0
    hue: int = 0
    saturation: int = 0
    lightness: int = 0
    levels_black: int = 0
    levels_white: int = 255
    levels_gamma: float = 1.0
    levels_out_black: int = 0
    levels_out_white: int = 255
    curve_points: tuple[tuple[int, int], ...] = DEFAULT_CURVE_POINTS
    curve_red: tuple[tuple[int, int], ...] = DEFAULT_CURVE_POINTS
    curve_green: tuple[tuple[int, int], ...] = DEFAULT_CURVE_POINTS
    curve_blue: tuple[tuple[int, int], ...] = DEFAULT_CURVE_POINTS
    color_shadows: tuple[int, int, int] = (0, 0, 0)
    color_midtones: tuple[int, int, int] = (0, 0, 0)
    color_highlights: tuple[int, int, int] = (0, 0, 0)
    preserve_luminosity: bool = True

    def __post_init__(self) -> None:
        kind = str(self.kind).lower()
        if kind not in ADJUSTMENT_KINDS:
            raise ValueError(f"Loại điều chỉnh không hợp lệ: {self.kind}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self,
            "brightness",
            _clamp_int(self.brightness, -MAX_BRIGHTNESS, MAX_BRIGHTNESS),
        )
        object.__setattr__(
            self, "contrast", _clamp_int(self.contrast, -MAX_CONTRAST, MAX_CONTRAST)
        )
        object.__setattr__(
            self, "hue", _clamp_int(self.hue, -MAX_HUE_SHIFT, MAX_HUE_SHIFT)
        )
        object.__setattr__(
            self,
            "saturation",
            _clamp_int(self.saturation, -MAX_SATURATION, MAX_SATURATION),
        )
        object.__setattr__(
            self,
            "lightness",
            _clamp_int(self.lightness, -MAX_LIGHTNESS, MAX_LIGHTNESS),
        )
        black = _clamp_int(self.levels_black, 0, 254)
        white = _clamp_int(self.levels_white, 1, 255)
        if black >= white:
            white = min(255, black + 1)
        object.__setattr__(self, "levels_black", black)
        object.__setattr__(self, "levels_white", white)
        object.__setattr__(
            self,
            "levels_gamma",
            _clamp_float(self.levels_gamma, MIN_GAMMA, MAX_GAMMA),
        )
        out_black = _clamp_int(self.levels_out_black, 0, 255)
        out_white = _clamp_int(self.levels_out_white, 0, 255)
        if out_black > out_white:
            out_black, out_white = out_white, out_black
        object.__setattr__(self, "levels_out_black", out_black)
        object.__setattr__(self, "levels_out_white", out_white)
        object.__setattr__(
            self, "curve_points", _normalize_curve_points(self.curve_points)
        )
        object.__setattr__(
            self, "curve_red", _normalize_curve_points(self.curve_red)
        )
        object.__setattr__(
            self, "curve_green", _normalize_curve_points(self.curve_green)
        )
        object.__setattr__(
            self, "curve_blue", _normalize_curve_points(self.curve_blue)
        )
        object.__setattr__(
            self, "color_shadows", _normalize_balance(self.color_shadows)
        )
        object.__setattr__(
            self, "color_midtones", _normalize_balance(self.color_midtones)
        )
        object.__setattr__(
            self, "color_highlights", _normalize_balance(self.color_highlights)
        )
        object.__setattr__(
            self, "preserve_luminosity", bool(self.preserve_luminosity)
        )

    @property
    def default_name(self) -> str:
        return ADJUSTMENT_LABELS.get(self.kind, "Adjustment")

    @property
    def is_identity(self) -> bool:
        if self.kind == "brightness_contrast":
            return self.brightness == 0 and self.contrast == 0
        if self.kind == "hue_saturation":
            return self.hue == 0 and self.saturation == 0 and self.lightness == 0
        if self.kind == "levels":
            return (
                self.levels_black == 0
                and self.levels_white == 255
                and abs(self.levels_gamma - 1.0) < 1e-9
                and self.levels_out_black == 0
                and self.levels_out_white == 255
            )
        if self.kind == "curves":
            return (
                self.curve_points == DEFAULT_CURVE_POINTS
                and self.curve_red == DEFAULT_CURVE_POINTS
                and self.curve_green == DEFAULT_CURVE_POINTS
                and self.curve_blue == DEFAULT_CURVE_POINTS
            )
        if self.kind == "color_balance":
            return not (
                any(self.color_shadows)
                or any(self.color_midtones)
                or any(self.color_highlights)
            )
        return False

    def summary(self) -> str:
        if self.kind == "brightness_contrast":
            if self.is_identity:
                return "Không thay đổi"
            return (
                f"Sáng {self.brightness:+d} · "
                f"Tương phản {self.contrast:+d}"
            )
        if self.kind == "hue_saturation":
            if self.is_identity:
                return "Không thay đổi"
            return (
                f"Màu {self.hue:+d}° · Bão hoà {self.saturation:+d} · "
                f"Sáng {self.lightness:+d}"
            )
        if self.kind == "levels":
            if self.is_identity:
                return "Không thay đổi"
            parts = [
                f"Đen {self.levels_black}",
                f"Gamma {self.levels_gamma:.2f}",
                f"Trắng {self.levels_white}",
            ]
            if (
                self.levels_out_black != 0
                or self.levels_out_white != 255
            ):
                parts.append(
                    f"Ra {self.levels_out_black}..{self.levels_out_white}"
                )
            return " · ".join(parts)
        if self.kind == "curves":
            if self.is_identity:
                return "Không thay đổi"
            parts = []
            if self.curve_points != DEFAULT_CURVE_POINTS:
                parts.append(f"{len(self.curve_points)} điểm")
            for label, points in (
                ("R", self.curve_red),
                ("G", self.curve_green),
                ("B", self.curve_blue),
            ):
                if points != DEFAULT_CURVE_POINTS:
                    parts.append(label)
            return "Đường cong " + " · ".join(parts)
        if self.kind == "color_balance":
            if self.is_identity:
                return "Không thay đổi"
            parts = []
            if any(self.color_shadows):
                parts.append(f"Tối {_format_triple(self.color_shadows)}")
            if any(self.color_midtones):
                parts.append(f"Trung {_format_triple(self.color_midtones)}")
            if any(self.color_highlights):
                parts.append(f"Sáng {_format_triple(self.color_highlights)}")
            if self.preserve_luminosity:
                parts.append("giữ độ sáng")
            return " · ".join(parts)
        if self.kind == "invert":
            return "Đảo màu"
        return "Chuyển xám"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "hue": self.hue,
            "saturation": self.saturation,
            "lightness": self.lightness,
            "levels_black": self.levels_black,
            "levels_white": self.levels_white,
            "levels_gamma": self.levels_gamma,
            "levels_out_black": self.levels_out_black,
            "levels_out_white": self.levels_out_white,
            "curve_points": [[x, y] for x, y in self.curve_points],
            "curve_red": [[x, y] for x, y in self.curve_red],
            "curve_green": [[x, y] for x, y in self.curve_green],
            "curve_blue": [[x, y] for x, y in self.curve_blue],
            "color_shadows": list(self.color_shadows),
            "color_midtones": list(self.color_midtones),
            "color_highlights": list(self.color_highlights),
            "preserve_luminosity": self.preserve_luminosity,
        }

    @classmethod
    def from_dict(cls, data: object) -> "AdjustmentProperties":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu điều chỉnh không hợp lệ.")
        try:
            return cls(
                kind=str(data.get("kind", "brightness_contrast")),
                brightness=int(data.get("brightness", 0)),
                contrast=int(data.get("contrast", 0)),
                hue=int(data.get("hue", 0)),
                saturation=int(data.get("saturation", 0)),
                lightness=int(data.get("lightness", 0)),
                levels_black=int(data.get("levels_black", 0)),
                levels_white=int(data.get("levels_white", 255)),
                levels_gamma=float(data.get("levels_gamma", 1.0)),
                levels_out_black=int(data.get("levels_out_black", 0)),
                levels_out_white=int(data.get("levels_out_white", 255)),
                curve_points=data.get("curve_points", DEFAULT_CURVE_POINTS),
                curve_red=data.get("curve_red", DEFAULT_CURVE_POINTS),
                curve_green=data.get("curve_green", DEFAULT_CURVE_POINTS),
                curve_blue=data.get("curve_blue", DEFAULT_CURVE_POINTS),
                color_shadows=data.get("color_shadows", (0, 0, 0)),
                color_midtones=data.get("color_midtones", (0, 0, 0)),
                color_highlights=data.get("color_highlights", (0, 0, 0)),
                preserve_luminosity=bool(
                    data.get("preserve_luminosity", True)
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thuộc tính điều chỉnh không hợp lệ: {exc}") from exc


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (
        0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    )


def apply_adjustment_rgb(
    rgb: np.ndarray, properties: AdjustmentProperties
) -> np.ndarray:
    """Áp điều chỉnh lên màu RGB float 0..1, không đổi alpha."""
    array = np.asarray(rgb, dtype=np.float32)
    if array.shape[-1] != 3:
        raise ValueError("Mảng màu phải có 3 kênh ở trục cuối.")
    if properties.is_identity:
        return np.clip(array, 0.0, 1.0)

    kind = properties.kind
    if kind == "invert":
        return np.clip(1.0 - array, 0.0, 1.0)
    if kind == "desaturate":
        gray = _luma(array)[..., None]
        return np.clip(np.repeat(gray, 3, axis=-1), 0.0, 1.0)
    if kind == "brightness_contrast":
        contrast_px = properties.contrast * 2.55
        factor = (259.0 * (contrast_px + 255.0)) / (
            255.0 * (259.0 - contrast_px)
        )
        levels = array * 255.0
        out = (levels - 128.0) * factor + 128.0 + properties.brightness * 2.55
        return np.clip(out / 255.0, 0.0, 1.0)
    if kind == "levels":
        black = properties.levels_black / 255.0
        white = properties.levels_white / 255.0
        normalized = np.clip(
            (array - black) / max(white - black, 1e-6), 0.0, 1.0
        )
        if abs(properties.levels_gamma - 1.0) > 1e-9:
            normalized = normalized ** (1.0 / properties.levels_gamma)
        out_min = properties.levels_out_black / 255.0
        out_max = properties.levels_out_white / 255.0
        return np.clip(
            out_min + normalized * (out_max - out_min), 0.0, 1.0
        )
    if kind == "curves":
        def sample(points, values):
            xs = np.array([point[0] for point in points], dtype=np.float32)
            ys = np.array([point[1] for point in points], dtype=np.float32)
            return np.interp(values * 255.0, xs, ys) / 255.0

        channel_points = (
            properties.curve_red,
            properties.curve_green,
            properties.curve_blue,
        )
        out = array.copy()
        for index, points in enumerate(channel_points):
            if points != DEFAULT_CURVE_POINTS:
                out[..., index] = sample(points, array[..., index])
        if properties.curve_points != DEFAULT_CURVE_POINTS:
            out = sample(properties.curve_points, out)
        return np.clip(out, 0.0, 1.0)
    if kind == "color_balance":
        shadow_shift = (
            np.array(properties.color_shadows, dtype=np.float32)
            / 100.0
            * 0.25
        )
        mid_shift = (
            np.array(properties.color_midtones, dtype=np.float32)
            / 100.0
            * 0.25
        )
        high_shift = (
            np.array(properties.color_highlights, dtype=np.float32)
            / 100.0
            * 0.25
        )
        luma = _luma(array)[..., None]
        shadow_weight = np.clip(1.0 - 2.0 * luma, 0.0, 1.0)
        high_weight = np.clip(2.0 * luma - 1.0, 0.0, 1.0)
        mid_weight = np.clip(1.0 - shadow_weight - high_weight, 0.0, 1.0)
        out = (
            array
            + shadow_shift * shadow_weight
            + mid_shift * mid_weight
            + high_shift * high_weight
        )
        if properties.preserve_luminosity:
            original_luma = luma
            new_luma = _luma(out)[..., None]
            scale = original_luma / np.maximum(new_luma, 1e-4)
            out = out * scale
        return np.clip(out, 0.0, 1.0)

    shape = array.shape
    flat = np.ascontiguousarray(array.reshape(-1, 3))
    hue, saturation, lightness = _rgb_to_hsl(flat)
    hue = (hue + properties.hue / 360.0) % 1.0
    saturation = np.clip(
        saturation * (1.0 + properties.saturation / 100.0), 0.0, 1.0
    )
    if properties.lightness < 0:
        lightness = lightness * (1.0 + properties.lightness / 100.0)
    elif properties.lightness > 0:
        lightness = lightness + (1.0 - lightness) * (
            properties.lightness / 100.0
        )
    converted = _hsl_to_rgb(hue, saturation, lightness)
    return np.clip(converted.reshape(shape), 0.0, 1.0)


def compute_auto_levels(
    rgba: np.ndarray, clip_percent: float = AUTO_LEVELS_CLIP_PERCENT
) -> tuple[int, int]:
    """Tính điểm đen/trắng tự động từ histogram độ sáng.

    Pixel trong suốt hoàn toàn bị bỏ qua. ``clip_percent`` phần trăm số pixel
    ở mỗi đầu bị cắt để bỏ qua nhiễu. Ảnh phẳng (không có dải động) trả về
    0..255 để không tạo thay đổi.
    """
    array = np.asarray(rgba)
    if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
        raise ValueError("Ảnh phải là mảng (cao, rộng, 4) uint8.")
    try:
        clip = float(clip_percent)
    except (TypeError, ValueError) as exc:
        raise ValueError("Tỉ lệ cắt auto levels không hợp lệ.") from exc
    if not math.isfinite(clip) or not 0.0 <= clip < 50.0:
        raise ValueError("Tỉ lệ cắt auto levels phải trong khoảng 0..50 %.")
    opaque = array[..., 3] > 0
    if not opaque.any():
        return 0, 255
    luma = _luma(array[..., :3].astype(np.float32))[opaque]
    if float(luma.max()) <= float(luma.min()):
        return 0, 255
    histogram = np.bincount(
        np.rint(np.clip(luma, 0.0, 255.0)).astype(np.intp), minlength=256
    )
    cut = int(int(histogram.sum()) * clip / 100.0)
    cumulative = np.cumsum(histogram)
    black = int(np.searchsorted(cumulative, cut, side="right"))
    reversed_cumulative = np.cumsum(histogram[::-1])
    white = 255 - int(np.searchsorted(reversed_cumulative, cut, side="right"))
    black = max(0, min(254, black))
    white = max(1, min(255, white))
    if black >= white:
        return 0, 255
    return black, white


def apply_adjustment_rgba(
    rgba: np.ndarray, properties: AdjustmentProperties
) -> np.ndarray:
    """Áp điều chỉnh lên ảnh RGBA uint8 (dùng cho xem trước)."""
    array = np.asarray(rgba)
    if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
        raise ValueError("Ảnh phải là mảng (cao, rộng, 4) uint8.")
    result = array.copy()
    rgb = array[..., :3].astype(np.float32) / 255.0
    adjusted = apply_adjustment_rgb(rgb, properties)
    result[..., :3] = np.clip(adjusted * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return result
