"""Thanh tab quản lý nhiều tài liệu đang mở."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QTabBar, QTabWidget, QToolButton, QWidget

from ui import icons
from ui.canvas_view import CanvasView


class DocumentTabs(QTabWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setMovable(True)
        self.setTabsClosable(False)
        self.tabBar().setExpanding(False)
        self.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        self.tabBar().setUsesScrollButtons(True)
        self._title_connections: dict[int, tuple[object, object]] = {}

    def add_view(self, view: CanvasView) -> int:
        index = self.addTab(view, view.document.title)
        self._update_tooltip(view, index)
        close_button = QToolButton(self)
        close_button.setObjectName("tabCloseButton")
        close_button.setIcon(icons.icon("close"))
        close_button.setIconSize(QSize(10, 10))
        close_button.setAutoRaise(True)
        close_button.setToolTip("Đóng tài liệu (Ctrl+W)")
        close_button.clicked.connect(
            lambda checked=False, target=view: self.tabCloseRequested.emit(self.indexOf(target))
        )
        self.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close_button)
        signal = view.document.title_changed
        slot = lambda target=view: self.update_tab_title(target)
        signal.connect(slot)
        self._title_connections[id(view)] = (signal, slot)
        return index

    def remove_view(self, view: CanvasView) -> None:
        """Gỡ tab và ngắt signal để tài liệu không giữ widget đã đóng."""
        connection = self._title_connections.pop(id(view), None)
        if connection is not None:
            signal, slot = connection
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        index = self.indexOf(view)
        if index >= 0:
            self.removeTab(index)
        view.dispose()

    def update_tab_title(self, view: CanvasView) -> None:
        index = self.indexOf(view)
        if index < 0:
            return
        self.setTabText(index, view.document.title)
        self._update_tooltip(view, index)

    def _update_tooltip(self, view: CanvasView, index: int) -> None:
        document = view.document
        tooltip = document.file_path or document.base_title
        self.setTabToolTip(index, tooltip)

    def views(self) -> list[CanvasView]:
        result: list[CanvasView] = []
        for index in range(self.count()):
            widget = self.widget(index)
            if isinstance(widget, CanvasView):
                result.append(widget)
        return result

    def refresh_theme(self) -> None:
        for index in range(self.count()):
            button = self.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
            if isinstance(button, QToolButton):
                button.setIcon(icons.icon("close"))
