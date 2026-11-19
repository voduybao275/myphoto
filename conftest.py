"""Cấu hình chung cho pytest: đảm bảo import được package và Qt chạy offscreen."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
if os.name == "nt":
    # Qt5 offscreen không tự tìm thấy font trên Windows; trỏ tới thư mục font hệ thống.
    font_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if os.path.isdir(font_dir):
        os.environ.setdefault("QT_QPA_FONTDIR", font_dir)

import pytest  # noqa: E402

import compat.qt  # noqa: E402,F401  - chọn PySide2/PySide6 trước khi import Qt
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="session", autouse=True)
def _apply_test_theme(qapp):
    from config.settings import THEME_DARK
    from ui import theme

    theme.apply_theme(qapp, THEME_DARK)
    yield
