"""Hệ thống theme Dark/Light dùng chung cho toàn ứng dụng."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from config.settings import THEME_DARK, THEME_LIGHT, project_root

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Theme:
    name: str
    window_bg: str
    menu_bg: str
    panel_bg: str
    panel_alt: str
    input_bg: str
    hover_bg: str
    selected_bg: str
    border: str
    text: str
    text_dim: str
    text_disabled: str
    accent: str
    accent_text: str
    canvas_bg: str
    checker_a: str
    checker_b: str
    icon: str
    tab_bg: str

    def color(self, attribute: str) -> QColor:
        return QColor(getattr(self, attribute))


DARK = Theme(
    name=THEME_DARK,
    window_bg="#1b1d21",
    menu_bg="#16181c",
    panel_bg="#23262b",
    panel_alt="#1f2227",
    input_bg="#141619",
    hover_bg="#2d323a",
    selected_bg="#37424f",
    border="#34383f",
    text="#e7e9ec",
    text_dim="#9aa1a9",
    text_disabled="#5f6570",
    accent="#e0a052",
    accent_text="#1c1508",
    canvas_bg="#141619",
    checker_a="#2c2f35",
    checker_b="#24272c",
    icon="#d6dade",
    tab_bg="#1b1e22",
)

LIGHT = Theme(
    name=THEME_LIGHT,
    window_bg="#eef0f3",
    menu_bg="#f7f8fa",
    panel_bg="#ffffff",
    panel_alt="#f4f6f8",
    input_bg="#ffffff",
    hover_bg="#e6e9ee",
    selected_bg="#dce6f4",
    border="#d2d6dd",
    text="#23262b",
    text_dim="#666d78",
    text_disabled="#a8adb5",
    accent="#b4751b",
    accent_text="#ffffff",
    canvas_bg="#c9ccd2",
    checker_a="#ffffff",
    checker_b="#e7e9ed",
    icon="#3b414a",
    tab_bg="#e8eaee",
)

_THEMES = {THEME_DARK: DARK, THEME_LIGHT: LIGHT}
_current_theme: Theme = DARK


def current_theme() -> Theme:
    return _current_theme


def theme_by_name(name: str) -> Theme:
    return _THEMES.get(name, DARK)


def _build_palette(theme: Theme) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: theme.window_bg,
        QPalette.ColorRole.WindowText: theme.text,
        QPalette.ColorRole.Base: theme.input_bg,
        QPalette.ColorRole.AlternateBase: theme.panel_alt,
        QPalette.ColorRole.ToolTipBase: theme.panel_bg,
        QPalette.ColorRole.ToolTipText: theme.text,
        QPalette.ColorRole.Text: theme.text,
        QPalette.ColorRole.Button: theme.panel_bg,
        QPalette.ColorRole.ButtonText: theme.text,
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Link: theme.accent,
        QPalette.ColorRole.Highlight: theme.accent,
        QPalette.ColorRole.HighlightedText: theme.accent_text,
        QPalette.ColorRole.PlaceholderText: theme.text_dim,
        QPalette.ColorRole.Mid: theme.border,
        QPalette.ColorRole.Dark: theme.window_bg,
        QPalette.ColorRole.Light: theme.panel_alt,
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(theme.text_disabled))
    return palette


def apply_theme(app: QApplication, name: str) -> Theme:
    global _current_theme
    theme = theme_by_name(name)
    stylesheet_path = project_root() / "assets" / "themes" / f"{theme.name}.qss"
    try:
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Không đọc được QSS theme %s", stylesheet_path, exc_info=True)
        stylesheet = ""
    app.setPalette(_build_palette(theme))
    app.setStyleSheet(stylesheet)
    _current_theme = theme
    return theme


def resource_path(*parts: str) -> Path:
    return project_root() / "assets" / Path(*parts)
