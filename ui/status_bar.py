"""Status bar: gợi ý thao tác, toạ độ con trỏ, kích thước, bộ nhớ và zoom."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QStatusBar, QWidget

from ui.formatting import format_memory, format_zoom

ZOOM_PRESETS = [12.5, 25.0, 33.33, 50.0, 66.67, 100.0, 200.0, 400.0, 800.0, 1600.0]


class AppStatusBar(QStatusBar):
    zoom_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)

        self.hint_label = QLabel("Sẵn sàng")
        self.addWidget(self.hint_label, 1)

        self.pos_label = QLabel("X —   Y —")
        self.pos_label.setMinimumWidth(130)
        self.addPermanentWidget(self.pos_label)

        self.size_label = QLabel("—")
        self.addPermanentWidget(self.size_label)

        self.memory_label = QLabel("")
        self.addPermanentWidget(self.memory_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setObjectName("ZoomCombo")
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.zoom_combo.setFixedWidth(80)
        for preset in ZOOM_PRESETS:
            self.zoom_combo.addItem(format_zoom(preset / 100.0))
        self.zoom_combo.activated.connect(self._on_zoom_combo_activated)
        self.zoom_combo.lineEdit().editingFinished.connect(self._on_zoom_editing_finished)
        self.addPermanentWidget(self.zoom_combo)

        self._view = None
        self._connections: list[tuple[object, object]] = []
        self._updating_zoom = False

    def bind_view(self, view) -> None:
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()
        self._view = view
        if view is None:
            self.pos_label.setText("X —   Y —")
            self.size_label.setText("—")
            self.memory_label.setText("")
            self._set_zoom_text(1.0)
            return
        document = view.document
        self._connect(view.cursor_moved, self._on_cursor_moved)
        self._connect(view.zoom_changed, self._set_zoom_text)
        self._connect(document.structure_changed, self._update_document_info)
        self._connect(document.content_changed, self._update_document_info)
        self._update_document_info()
        self._set_zoom_text(view.zoom)

    def _connect(self, signal, slot) -> None:
        signal.connect(slot)
        self._connections.append((signal, slot))

    def set_hint(self, text: str) -> None:
        self.hint_label.setText(text)

    def _on_cursor_moved(self, position: QPointF, inside: bool) -> None:
        if inside:
            self.pos_label.setText(
                f"X {math.floor(position.x())}   Y {math.floor(position.y())}"
            )
        else:
            self.pos_label.setText("X —   Y —")

    def _update_document_info(self) -> None:
        if self._view is None:
            return
        document = self._view.document
        self.size_label.setText(f"{document.width} × {document.height} px")
        self.memory_label.setText(format_memory(document.memory_estimate()))

    def _set_zoom_text(self, zoom: float) -> None:
        self._updating_zoom = True
        try:
            self.zoom_combo.setEditText(format_zoom(zoom))
        finally:
            self._updating_zoom = False

    def _on_zoom_combo_activated(self, _index: int) -> None:
        self._emit_zoom_from_text()

    def _on_zoom_editing_finished(self) -> None:
        self._emit_zoom_from_text()

    def _emit_zoom_from_text(self) -> None:
        if self._updating_zoom:
            return
        text = self.zoom_combo.currentText().strip().replace("%", "").replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            if self._view is not None:
                self._set_zoom_text(self._view.zoom)
            return
        if value <= 0 or value > 3200:
            if self._view is not None:
                self._set_zoom_text(self._view.zoom)
            return
        self.zoom_requested.emit(value / 100.0)
