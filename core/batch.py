"""Xử lý hàng loạt ngoại tuyến: các bước xử lý, action và bộ chạy theo file.

Mỗi ảnh được đọc bằng Pillow, áp lần lượt các bước NumPy/Pillow rồi ghi ra thư
mục đích. Không bao giờ ghi đè file gốc: tên đầu ra có hậu tố ``_edited`` và
tự thêm số thứ tự khi trùng tên.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from core import filters
from core.adjustment_layer import (
    AdjustmentProperties,
    apply_adjustment_rgba,
    compute_auto_levels,
)
from formats.export_manager import ExportError, export_image
from formats.import_manager import ImageImportError, load_image_rgba

logger = logging.getLogger(__name__)

MAX_BATCH_FILES = 500
MAX_BATCH_PIXELS = 80_000_000  # ~80 MP để giữ RAM an toàn trên máy 8 GB
DEFAULT_SUFFIX = "_edited"
OUTPUT_FORMATS = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
OUTPUT_FORMAT_LABELS = {
    "png": "PNG (giữ alpha)",
    "jpeg": "JPEG (nền trắng)",
    "webp": "WebP",
}
BATCH_STEP_TYPES = (
    "auto_levels",
    "auto_contrast",
    "grayscale",
    "invert",
    "brightness_contrast",
    "hue_saturation",
    "levels",
    "gaussian_blur",
    "unsharp_mask",
    "resize_percent",
    "resize_max",
)
BATCH_STEP_LABELS = {
    "auto_levels": "Auto Levels",
    "auto_contrast": "Auto Contrast",
    "grayscale": "Chuyển xám",
    "invert": "Đảo màu",
    "brightness_contrast": "Sáng / Tương phản",
    "hue_saturation": "Màu / Bão hoà",
    "levels": "Levels",
    "gaussian_blur": "Làm mờ Gaussian",
    "unsharp_mask": "Làm nét",
    "resize_percent": "Thu phóng theo %",
    "resize_max": "Giới hạn cạnh dài",
}
_BAD_NAME_CHARS = '<>:"/\\|?*'


class BatchError(Exception):
    """Lỗi cấu hình hoặc xử lý hàng loạt với thông điệp thân thiện."""


def _clamp_int(value: object, minimum: int, maximum: int, label: str) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} phải là số nguyên.") from exc
    return max(minimum, min(maximum, number))


def _clamp_float(value: object, minimum: float, maximum: float, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} phải là số.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} phải là số hữu hạn.")
    return max(minimum, min(maximum, number))


@dataclass(frozen=True)
class BatchStep:
    """Một bước xử lý; tham số không dùng tới được giữ ở giá trị mặc định."""

    kind: str
    brightness: int = 0
    contrast: int = 0
    hue: int = 0
    saturation: int = 0
    lightness: int = 0
    levels_black: int = 0
    levels_white: int = 255
    levels_gamma: float = 1.0
    radius: float = 2.0
    amount: int = 100
    threshold: int = 0
    percent: int = 100
    max_size: int = 1920

    def __post_init__(self) -> None:
        kind = str(self.kind).strip().lower()
        if kind not in BATCH_STEP_TYPES:
            raise ValueError(f"Loại bước xử lý không hợp lệ: {self.kind}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self, "brightness", _clamp_int(self.brightness, -100, 100, "Độ sáng")
        )
        object.__setattr__(
            self, "contrast", _clamp_int(self.contrast, -100, 100, "Tương phản")
        )
        object.__setattr__(self, "hue", _clamp_int(self.hue, -180, 180, "Dịch màu"))
        object.__setattr__(
            self, "saturation", _clamp_int(self.saturation, -100, 100, "Bão hoà")
        )
        object.__setattr__(
            self, "lightness", _clamp_int(self.lightness, -100, 100, "Độ sáng HSL")
        )
        black = _clamp_int(self.levels_black, 0, 254, "Điểm đen")
        white = _clamp_int(self.levels_white, 1, 255, "Điểm trắng")
        if black >= white:
            white = min(255, black + 1)
        object.__setattr__(self, "levels_black", black)
        object.__setattr__(self, "levels_white", white)
        object.__setattr__(
            self,
            "levels_gamma",
            _clamp_float(self.levels_gamma, 0.1, 9.99, "Gamma"),
        )
        object.__setattr__(
            self, "radius", _clamp_float(self.radius, 0.0, filters.MAX_BLUR_RADIUS, "Bán kính")
        )
        object.__setattr__(
            self, "amount", _clamp_int(self.amount, 0, 300, "Mức làm nét")
        )
        object.__setattr__(
            self, "threshold", _clamp_int(self.threshold, 0, 255, "Ngưỡng")
        )
        object.__setattr__(
            self, "percent", _clamp_int(self.percent, 10, 400, "Tỉ lệ")
        )
        object.__setattr__(
            self, "max_size", _clamp_int(self.max_size, 16, 8000, "Cạnh dài")
        )

    @property
    def label(self) -> str:
        return BATCH_STEP_LABELS.get(self.kind, self.kind)

    def summary(self) -> str:
        if self.kind == "brightness_contrast":
            return f"Sáng {self.brightness:+d} · Tương phản {self.contrast:+d}"
        if self.kind == "hue_saturation":
            return (
                f"Màu {self.hue:+d}° · Bão hoà {self.saturation:+d} · "
                f"Sáng {self.lightness:+d}"
            )
        if self.kind == "levels":
            return (
                f"Đen {self.levels_black} · Gamma {self.levels_gamma:.2f} · "
                f"Trắng {self.levels_white}"
            )
        if self.kind == "gaussian_blur":
            return f"Bán kính {self.radius:.1f} px"
        if self.kind == "unsharp_mask":
            return (
                f"Mức {self.amount} · Bán kính {self.radius:.1f} px · "
                f"Ngưỡng {self.threshold}"
            )
        if self.kind == "resize_percent":
            return f"{self.percent}%"
        if self.kind == "resize_max":
            return f"Cạnh dài {self.max_size} px"
        if self.kind == "auto_levels":
            return "Tự cân bằng điểm đen/trắng"
        if self.kind == "auto_contrast":
            return "Tự kéo giãn tương phản"
        if self.kind == "grayscale":
            return "Bỏ màu theo luma"
        return "Đảo màu RGB"

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
            "radius": self.radius,
            "amount": self.amount,
            "threshold": self.threshold,
            "percent": self.percent,
            "max_size": self.max_size,
        }

    @classmethod
    def from_dict(cls, data: object) -> "BatchStep":
        if not isinstance(data, dict):
            raise ValueError("Bước xử lý không hợp lệ.")
        return cls(
            kind=str(data.get("kind", "")),
            brightness=data.get("brightness", 0),
            contrast=data.get("contrast", 0),
            hue=data.get("hue", 0),
            saturation=data.get("saturation", 0),
            lightness=data.get("lightness", 0),
            levels_black=data.get("levels_black", 0),
            levels_white=data.get("levels_white", 255),
            levels_gamma=data.get("levels_gamma", 1.0),
            radius=data.get("radius", 2.0),
            amount=data.get("amount", 100),
            threshold=data.get("threshold", 0),
            percent=data.get("percent", 100),
            max_size=data.get("max_size", 1920),
        )


@dataclass(frozen=True)
class BatchAction:
    """Chuỗi bước có tên, dùng lại được hoặc lưu vào thư viện preset."""

    name: str = "Action"
    steps: tuple[BatchStep, ...] = ()

    def __post_init__(self) -> None:
        name = str(self.name).strip() or "Action"
        if len(name) > 48:
            raise ValueError("Tên action quá dài (tối đa 48 ký tự).")
        object.__setattr__(self, "name", name)
        steps = tuple(self.steps)
        if not steps:
            raise ValueError("Action cần ít nhất một bước xử lý.")
        for step in steps:
            if not isinstance(step, BatchStep):
                raise ValueError("Action chỉ chứa các bước xử lý hợp lệ.")
        object.__setattr__(self, "steps", steps)

    def summary(self) -> str:
        return f"{len(self.steps)} bước: " + " → ".join(
            step.label for step in self.steps
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: object) -> "BatchAction":
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu action không hợp lệ.")
        raw_steps = data.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError("Danh sách bước của action không hợp lệ.")
        return cls(
            name=str(data.get("name", "Action")),
            steps=tuple(BatchStep.from_dict(item) for item in raw_steps),
        )


def _validate_rgba(rgba: np.ndarray) -> np.ndarray:
    array = np.asarray(rgba)
    if array.ndim != 3 or array.shape[2] != 4 or array.dtype != np.uint8:
        raise BatchError("Ảnh phải là mảng (cao, rộng, 4) uint8.")
    pixels = array.shape[0] * array.shape[1]
    if pixels > MAX_BATCH_PIXELS:
        raise BatchError(
            f"Ảnh có {pixels / 1_000_000:.1f} megapixel, vượt giới hạn "
            f"an toàn {MAX_BATCH_PIXELS // 1_000_000} MP cho xử lý hàng loạt."
        )
    return array


def _resize_rgba(rgba: np.ndarray, width: int, height: int) -> np.ndarray:
    if width <= 0 or height <= 0:
        raise BatchError("Kích thước ảnh sau khi thu phóng không hợp lệ.")
    image = Image.fromarray(np.ascontiguousarray(rgba), "RGBA")
    resized = image.resize((width, height), Image.Resampling.LANCZOS)
    return np.asarray(resized, dtype=np.uint8)


def apply_step(rgba: np.ndarray, step: BatchStep) -> np.ndarray:
    """Áp một bước lên mảng RGBA và trả về mảng mới."""
    if not isinstance(step, BatchStep):
        raise BatchError("Bước xử lý không hợp lệ.")
    array = _validate_rgba(rgba)

    if step.kind == "auto_levels":
        black, white = compute_auto_levels(array)
        if (black, white) == (0, 255):
            return array.copy()
        return apply_adjustment_rgba(
            array,
            AdjustmentProperties(
                kind="levels", levels_black=black, levels_white=white
            ),
        )
    if step.kind == "auto_contrast":
        return filters.auto_contrast(array)
    if step.kind == "grayscale":
        return filters.desaturate(array)
    if step.kind == "invert":
        return filters.invert(array)
    if step.kind == "brightness_contrast":
        return filters.brightness_contrast(array, step.brightness, step.contrast)
    if step.kind == "hue_saturation":
        return filters.hue_saturation(
            array, step.hue, step.saturation, step.lightness
        )
    if step.kind == "levels":
        return apply_adjustment_rgba(
            array,
            AdjustmentProperties(
                kind="levels",
                levels_black=step.levels_black,
                levels_white=step.levels_white,
                levels_gamma=step.levels_gamma,
            ),
        )
    if step.kind == "gaussian_blur":
        return filters.gaussian_blur(array, step.radius)
    if step.kind == "unsharp_mask":
        return filters.unsharp_mask(
            array, step.amount, step.radius, step.threshold
        )
    if step.kind == "resize_percent":
        height, width = array.shape[:2]
        new_width = max(1, round(width * step.percent / 100.0))
        new_height = max(1, round(height * step.percent / 100.0))
        return _resize_rgba(array, new_width, new_height)
    if step.kind == "resize_max":
        height, width = array.shape[:2]
        longest = max(width, height)
        if longest <= step.max_size:
            return array.copy()
        scale = step.max_size / float(longest)
        return _resize_rgba(
            array,
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )
    raise BatchError(f"Chưa hỗ trợ bước xử lý: {step.kind}")


def apply_steps(rgba: np.ndarray, steps) -> np.ndarray:
    """Áp cả chuỗi bước theo thứ tự."""
    result = _validate_rgba(rgba)
    for step in tuple(steps):
        result = apply_step(result, step)
    return result


@dataclass(frozen=True)
class BatchResult:
    source: Path
    output: Path | None
    status: str  # ok | failed | cancelled
    message: str = ""


def _normalize_suffix(suffix: object) -> str:
    text = str(suffix).strip()
    if not text:
        raise BatchError("Hậu tố tên file không được để trống.")
    if any(character in text for character in _BAD_NAME_CHARS):
        raise BatchError("Hậu tố tên file chứa ký tự không hợp lệ.")
    if text.startswith("."):
        text = text[1:]
    if not text:
        raise BatchError("Hậu tố tên file không được để trống.")
    return text


class BatchRunner:
    """Xử lý một danh sách file ảnh theo chuỗi bước đã cấu hình."""

    def __init__(
        self,
        steps,
        output_dir: str | Path,
        *,
        output_format: str = "png",
        quality: int = 92,
        suffix: str = DEFAULT_SUFFIX,
        overwrite: bool = False,
    ) -> None:
        self.steps = tuple(steps)
        if not self.steps:
            raise BatchError("Hãy thêm ít nhất một bước xử lý.")
        for step in self.steps:
            if not isinstance(step, BatchStep):
                raise BatchError("Danh sách bước xử lý không hợp lệ.")
        fmt = str(output_format).strip().lower()
        if fmt not in OUTPUT_FORMATS:
            raise BatchError("Định dạng đầu ra không hợp lệ.")
        self.output_format = fmt
        self.quality = _clamp_int(quality, 1, 100, "Chất lượng")
        self.suffix = _normalize_suffix(suffix)
        self.overwrite = bool(overwrite)
        self.output_dir = Path(output_dir) if str(output_dir).strip() else None
        if self.output_dir is None:
            raise BatchError("Hãy chọn thư mục đầu ra.")
        if self.output_dir.exists() and not self.output_dir.is_dir():
            raise BatchError("Đường dẫn đầu ra không phải thư mục.")

    @property
    def extension(self) -> str:
        return OUTPUT_FORMATS[self.output_format]

    def output_path_for(self, source: str | Path) -> Path:
        source_path = Path(source)
        extension = self.extension
        stem = source_path.stem
        if not stem.lower().endswith(self.suffix.lower()):
            stem = f"{stem}{self.suffix}"
        attempt = 1
        while attempt <= 10_000:
            marker = "" if attempt == 1 else f" ({attempt})"
            candidate = self.output_dir / f"{stem}{marker}{extension}"
            if candidate.exists() and not self.overwrite:
                attempt += 1
                continue
            try:
                same = candidate.resolve() == source_path.resolve()
            except OSError:
                same = False
            if same:
                attempt += 1
                continue
            return candidate
        raise BatchError("Không tìm được tên file đầu ra không trùng.")

    def _process(self, source: Path) -> BatchResult:
        rgba = load_image_rgba(source)
        result = apply_steps(rgba, self.steps)
        target = self.output_path_for(source)
        export_image(target, result, quality=self.quality)
        return BatchResult(source=source, output=target, status="ok")

    def run(self, sources, progress=None, cancel=None) -> list[BatchResult]:
        """Chạy tuần tự; ``progress(done, total, source)`` sau mỗi file.

        ``cancel()`` được kiểm tra giữa các file (một file đang xử lý vẫn
        hoàn tất để không để lại file dở dang).
        """
        paths = [Path(item) for item in sources]
        if not paths:
            raise BatchError("Danh sách file đầu vào đang trống.")
        if len(paths) > MAX_BATCH_FILES:
            raise BatchError(
                f"Mỗi lần chỉ xử lý tối đa {MAX_BATCH_FILES} file."
            )
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BatchError(
                f"Không tạo được thư mục đầu ra.\nChi tiết: {exc}"
            ) from exc

        results: list[BatchResult] = []
        total = len(paths)
        for index, source in enumerate(paths):
            if cancel is not None and cancel():
                for remaining in paths[index:]:
                    results.append(
                        BatchResult(
                            source=remaining,
                            output=None,
                            status="cancelled",
                            message="Đã huỷ trước khi xử lý.",
                        )
                    )
                break
            try:
                results.append(self._process(source))
            except MemoryError:
                results.append(
                    BatchResult(
                        source=source,
                        output=None,
                        status="failed",
                        message="Hết bộ nhớ khi xử lý ảnh này.",
                    )
                )
            except (
                ImageImportError,
                ExportError,
                BatchError,
                ValueError,
                OSError,
            ) as exc:
                results.append(
                    BatchResult(
                        source=source,
                        output=None,
                        status="failed",
                        message=str(exc),
                    )
                )
            if progress is not None:
                progress(index + 1, total, source)
        return results
