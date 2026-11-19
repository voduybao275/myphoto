"""Trình soạn văn bản ngay trên canvas, không cần hộp thoại.

Giữ nguyên các thiết lập nền của layer (căn lề, giãn dòng/chữ, kerning, uốn chữ,
chữ trên đường dẫn) và cho phép sửa nội dung/định dạng theo từng đoạn bằng chính
QTextEdit. Cỡ chữ, màu và font được chuyển qua lại với ``TextRun`` nhờ helper dùng
chung.
"""

from __future__ import annotations

import math
from dataclasses import replace

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QTextEdit, QWidget

from core.text_layer import TextProperties, TextRun
from ui.text_format import format_from_run, run_from_format
from ui.theme import current_theme

MIN_EDITOR_WIDTH = 120
MIN_EDITOR_HEIGHT = 20
PADDING_RATIO = 0.15


class InlineTextEditor(QTextEdit):
    """Ô soạn chữ trong suốt đặt đè lên canvas."""

    commit_requested = Signal()
    cancel_requested = Signal()
    content_size_changed = Signal()

    def __init__(
        self,
        base: TextProperties | None,
        default_run: TextRun,
        zoom: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if base is not None and not isinstance(base, TextProperties):
            raise TypeError("Thông tin văn bản nền phải là TextProperties.")
        if not isinstance(default_run, TextRun):
            raise TypeError("Định dạng mặc định phải là TextRun.")

        self._zoom = max(0.02, float(zoom))
        self._alignment = base.alignment if base is not None else "left"
        self._line_spacing = base.line_spacing if base is not None else 1.0
        self._letter_spacing = base.letter_spacing if base is not None else 0
        self._warp_style = base.warp_style if base is not None else "none"
        self._warp_bend = base.warp_bend if base is not None else 0
        self._kerning_pairs = base.kerning_pairs if base is not None else ()
        self._path_style = base.path_style if base is not None else "none"
        self._path_bend = base.path_bend if base is not None else 0
        self._fallback = base.runs[0] if base is not None and base.runs else default_run
        self._min_width = MIN_EDITOR_WIDTH if base is None else 1
        self._layout_guard = False
        self._ended = False

        self.setObjectName("InlineTextEditor")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.viewport().setAutoFillBackground(False)
        self.setCursorWidth(2)

        accent = current_theme().accent
        self.setStyleSheet(
            "QTextEdit#InlineTextEditor {"
            " background: transparent;"
            f" selection-background-color: {accent};"
            "}"
        )

        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.setInterval(0)
        self._focus_timer.timeout.connect(self._commit_after_focus_out)

        runs = base.runs if base is not None else (default_run,)
        self._load_runs(runs)
        self.textChanged.connect(self._on_text_changed)

    # ------------------------------------------------------------------ API
    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def min_width(self) -> int:
        return self._min_width

    def set_zoom(self, zoom: float) -> None:
        zoom = max(0.02, float(zoom))
        if abs(zoom - self._zoom) < 1e-9:
            return
        position = self.textCursor().position()
        runs = self._extract_runs()
        self._zoom = zoom
        self.document().setDocumentMargin(self._scaled_padding())
        if runs:
            self._load_runs(runs, cursor_position=position)
        else:
            self.update_size()

    def text_properties(self) -> TextProperties | None:
        """Thuộc tính hoàn chỉnh, hoặc None khi nội dung rỗng/toàn khoảng trắng."""
        runs = self._extract_runs()
        if not any(run.text.strip() for run in runs):
            return None
        return TextProperties(
            runs=runs,
            alignment=self._alignment,
            line_spacing=self._line_spacing,
            letter_spacing=self._letter_spacing,
            warp_style=self._warp_style,
            warp_bend=self._warp_bend,
            kerning_pairs=self._kerning_pairs,
            path_style=self._path_style,
            path_bend=self._path_bend,
        )

    def update_size(self) -> QSize:
        layout = self.document().documentLayout()
        size = layout.documentSize() if layout is not None else None
        width = int(math.ceil(size.width())) if size is not None else 0
        height = int(math.ceil(size.height())) if size is not None else 0
        width = max(self._min_width, width + 4)
        height = max(MIN_EDITOR_HEIGHT, height + 4)
        self.setFixedSize(width, height)
        return QSize(width, height)

    # ------------------------------------------------------------- dữ liệu
    def _scaled_padding(self) -> float:
        base_size = max(1, int(self._fallback.font_size))
        padding = max(2, int(round(base_size * PADDING_RATIO)))
        return float(padding) * self._zoom

    def _load_runs(
        self,
        runs: tuple[TextRun, ...],
        cursor_position: int | None = None,
    ) -> None:
        self._layout_guard = True
        try:
            self.document().clear()
            self.document().setDocumentMargin(self._scaled_padding())
            cursor = QTextCursor(self.document())
            cursor.beginEditBlock()
            for run in runs:
                if run.text:
                    cursor.insertText(run.text, format_from_run(run, self._zoom))
            cursor.endEditBlock()
            if runs:
                self._fallback = runs[-1]
            self._apply_block_format()
            end = self.document().characterCount() - 1
            position = 0 if cursor_position is None else max(0, min(cursor_position, end))
            cursor.setPosition(position)
            self.setTextCursor(cursor)
            if cursor_position is None or position >= end:
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
            if not any(run.text for run in runs):
                self.setCurrentCharFormat(format_from_run(self._fallback, self._zoom))
        finally:
            self._layout_guard = False
        self.update_size()

    def _apply_block_format(self) -> None:
        if self._layout_guard:
            return
        self._layout_guard = True
        try:
            alignments = {
                "left": Qt.AlignmentFlag.AlignLeft,
                "center": Qt.AlignmentFlag.AlignHCenter,
                "right": Qt.AlignmentFlag.AlignRight,
            }
            alignment = alignments.get(self._alignment, Qt.AlignmentFlag.AlignLeft)
            cursor = QTextCursor(self.document())
            block = self.document().begin()
            while block.isValid():
                fmt = block.blockFormat()
                fmt.setAlignment(alignment)
                fmt.setLineHeight(
                    100.0 * self._line_spacing,
                    QTextBlockFormat.LineHeightTypes.ProportionalHeight,
                )
                cursor.setPosition(block.position())
                cursor.setBlockFormat(fmt)
                block = block.next()
        finally:
            self._layout_guard = False

    def _extract_runs(self) -> tuple[TextRun, ...]:
        document = self.document()
        runs: list[TextRun] = []
        for block_index in range(document.blockCount()):
            if block_index:
                if runs:
                    runs[-1] = replace(runs[-1], text=runs[-1].text + "\n")
                else:
                    runs.append(replace(self._fallback, text="\n"))
            block = document.findBlockByNumber(block_index)
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                content = fragment.text()
                if content:
                    runs.append(
                        run_from_format(fragment.charFormat(), content, self._fallback)
                    )
                iterator += 1
        return tuple(runs)

    # ------------------------------------------------------------- sự kiện
    def _on_text_changed(self) -> None:
        if self._layout_guard:
            return
        self._apply_block_format()
        self.update_size()
        self.content_size_changed.emit()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802 (Qt override)
        super().focusOutEvent(event)
        if not self._ended:
            self._focus_timer.start()

    def _commit_after_focus_out(self) -> None:
        if self._ended or self.hasFocus():
            return
        self.commit_requested.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
            event.accept()
            return
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.commit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def close_editor(self) -> None:
        """Đánh dấu đã đóng để bỏ qua focus-out khi widget bị gỡ."""
        self._ended = True
        self._focus_timer.stop()
