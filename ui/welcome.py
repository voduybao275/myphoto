"""Trang chào khi chưa có tài liệu nào được mở."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.settings import APP_VERSION
from ui import icons


class WelcomePage(QWidget):
    new_requested = Signal()
    open_requested = Signal()
    recent_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomePage")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 20)

        content = QWidget(self)
        content.setMaximumWidth(560)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(icons.pixmap("app", 88))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._logo = logo
        layout.addWidget(logo)

        title = QLabel("My Photo Studio")
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        subtitle = QLabel("Trình chỉnh sửa ảnh và thiết kế đồ họa trên desktop")
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        new_button = QPushButton("Tạo tài liệu mới")
        new_button.setObjectName("WelcomePrimary")
        new_button.setToolTip("Ctrl+N")
        new_button.clicked.connect(self.new_requested)
        buttons.addWidget(new_button)

        open_button = QPushButton("Mở ảnh…")
        open_button.setObjectName("WelcomeSecondary")
        open_button.setToolTip("Ctrl+O")
        open_button.clicked.connect(self.open_requested)
        buttons.addWidget(open_button)
        layout.addLayout(buttons)
        layout.addSpacing(20)

        self.recent_title = QLabel("MỞ GẦN ĐÂY")
        self.recent_title.setObjectName("WelcomeSection")
        layout.addWidget(self.recent_title)

        self._recent_container = QWidget(self)
        self._recent_layout = QVBoxLayout(self._recent_container)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(2)
        layout.addWidget(self._recent_container)
        layout.addStretch(1)

        line = QFrame()
        line.setObjectName("WelcomeLine")
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        layout.addWidget(line)

        footer = QLabel(f"Phiên bản {APP_VERSION} · Windows 10/11 · Dữ liệu xử lý cục bộ")
        footer.setObjectName("WelcomeVersion")
        footer.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(footer)

        outer.addStretch(1)
        outer.addWidget(content)
        outer.addStretch(1)

        self.set_recent_files([])

    def set_recent_files(self, files: list[str]) -> None:
        while self._recent_layout.count():
            item = self._recent_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        valid = [path for path in files if path][:6]
        self.recent_title.setVisible(bool(valid))
        for file_path in valid:
            path = Path(file_path)
            button = QPushButton(f"{path.name}\n{path.parent}")
            button.setObjectName("WelcomeRecent")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(file_path)
            button.setFixedHeight(46)
            button.clicked.connect(
                lambda checked=False, target=file_path: self.recent_requested.emit(target)
            )
            self._recent_layout.addWidget(button)

    def refresh_theme(self) -> None:
        self._logo.setPixmap(icons.pixmap("app", 88))
