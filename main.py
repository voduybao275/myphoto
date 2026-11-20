"""Điểm khởi chạy My Photo Studio.

Chạy:  python main.py
Mở file:  python main.py "C:\\duong\\dan\\anh.png"
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import compat.qt  # noqa: F401  - phải import trước PySide6 để chọn đúng binding
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from compat.qt import QT_BINDING, exec_object
from config.settings import APP_NAME, APP_SLUG, APP_VERSION, SettingsStore, app_config_dir
from ui import icons, theme


def setup_logging() -> Path:
    """Ghi log xoay vòng vào thư mục cấu hình người dùng."""
    log_dir = app_config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "myphotostudio.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return log_file


def _install_excepthook() -> None:
    """Hiển thị lỗi nghiêm trọng thay vì để ứng dụng chết im lặng."""
    logger = logging.getLogger("crash")

    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Lỗi không xử lý được", exc_info=(exc_type, exc_value, exc_tb))
        try:
            QMessageBox.critical(
                None,
                f"{APP_NAME} gặp lỗi",
                "Ứng dụng vừa gặp lỗi không mong muốn.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Chi tiết đã được ghi vào log:\n{app_config_dir() / 'logs'}",
            )
        except Exception:  # noqa: BLE001 - không được để chính excepthook sập
            pass

    sys.excepthook = handle


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    log_file = setup_logging()
    logging.getLogger(__name__).info(
        "Khởi động %s %s (Python %s, %s)",
        APP_NAME,
        APP_VERSION,
        sys.version.split()[0],
        QT_BINDING,
    )
    _install_excepthook()

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_SLUG)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(True)

    store = SettingsStore()
    theme.apply_theme(app, store.data.theme)

    # Import muộn để QApplication và theme có hiệu lực trước khi dựng widget.
    from ui.main_window import MainWindow

    window = MainWindow(store)
    window.show()

    file_args = [arg for arg in argv[1:] if not arg.startswith("-")]
    paths = [arg for arg in file_args if Path(arg).exists()]
    if paths:
        window.open_paths(paths)
    else:
        logging.getLogger(__name__).info("Log file: %s", log_file)

    return exec_object(app)


if __name__ == "__main__":
    raise SystemExit(main())
