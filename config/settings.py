"""Cấu hình ứng dụng: hằng số, đường dẫn và lưu/đọc settings."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "My Photo Studio"
APP_SLUG = "MyPhotoStudio"
APP_VERSION = "0.25.0"

PROJECT_EXTENSION = ".mps"
PROJECT_FILTER = "My Photo Studio Project (*.mps)"

IMAGE_OPEN_FILTER = (
    "Tất cả ảnh hỗ trợ (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif *.webp);;"
    "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;TIFF (*.tif *.tiff);;"
    "GIF (*.gif);;WebP (*.webp)"
)
OPEN_FILTER = (
    "Tất cả file hỗ trợ (*.mps *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif *.webp);;"
    "My Photo Studio Project (*.mps);;"
    + IMAGE_OPEN_FILTER
)
EXPORT_FILTER = (
    "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;TIFF (*.tif *.tiff);;WebP (*.webp)"
)

MAX_RECENT_FILES = 12

THEME_DARK = "dark"
THEME_LIGHT = "light"


def app_config_dir() -> Path:
    """Thư mục cấu hình của người dùng trên từng hệ điều hành."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / APP_SLUG


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass
class AppSettings:
    theme: str = THEME_DARK
    recent_files: list[str] = field(default_factory=list)
    last_directory: str = ""
    window_geometry: str = ""
    window_state: str = ""
    export_quality: int = 92

    def resolved_last_directory(self) -> str:
        if self.last_directory and Path(self.last_directory).is_dir():
            return self.last_directory
        return str(Path.home())


class SettingsStore:
    """Đọc/ghi settings dạng JSON với ghi nguyên tử (atomic write)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_config_dir() / "settings.json")
        self.data = AppSettings()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            defaults = AppSettings()
            for key, value in asdict(defaults).items():
                if key not in raw:
                    setattr(self.data, key, value)
                    continue
                current = getattr(self.data, key)
                if isinstance(current, list):
                    setattr(self.data, key, [str(v) for v in raw[key] if isinstance(v, str)])
                elif isinstance(current, str):
                    setattr(self.data, key, str(raw[key]))
                elif isinstance(current, int):
                    setattr(self.data, key, int(raw[key]))
                else:
                    setattr(self.data, key, raw[key])
            if self.data.theme not in (THEME_DARK, THEME_LIGHT):
                self.data.theme = THEME_DARK
            self.data.export_quality = max(1, min(100, self.data.export_quality))
        except (OSError, ValueError, TypeError):
            logger.warning("Không đọc được settings, dùng cấu hình mặc định.", exc_info=True)
            self.data = AppSettings()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps(asdict(self.data), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, self.path)
        except OSError:
            logger.warning("Không ghi được settings.", exc_info=True)

    def add_recent(self, file_path: str) -> None:
        try:
            normalized = str(Path(file_path).resolve())
        except OSError:
            normalized = str(file_path)
        recent = [p for p in self.data.recent_files if p != normalized]
        recent.insert(0, normalized)
        self.data.recent_files = recent[:MAX_RECENT_FILES]
        try:
            self.data.last_directory = str(Path(normalized).parent)
        except OSError:
            pass
        self.save()

    def remove_recent(self, file_path: str) -> None:
        recent = [p for p in self.data.recent_files if p != file_path]
        if recent != self.data.recent_files:
            self.data.recent_files = recent
            self.save()

    def set_theme(self, theme: str) -> None:
        if theme in (THEME_DARK, THEME_LIGHT) and theme != self.data.theme:
            self.data.theme = theme
            self.save()


def load_settings() -> SettingsStore:
    return SettingsStore()
