"""Quản lý ngăn xếp Undo/Redo độc lập với giao diện."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.command_manager import Command

if TYPE_CHECKING:  # pragma: no cover
    from core.document import Document


class HistoryManager:
    def __init__(self, max_states: int = 60) -> None:
        if max_states < 1:
            raise ValueError("max_states phải >= 1.")
        self.max_states = max_states
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_label(self) -> str:
        return self._undo_stack[-1].label if self._undo_stack else ""

    @property
    def redo_label(self) -> str:
        return self._redo_stack[-1].label if self._redo_stack else ""

    def push(self, command: Command) -> None:
        self._undo_stack.append(command)
        if len(self._undo_stack) > self.max_states:
            del self._undo_stack[0]
        self._redo_stack.clear()

    def undo(self, document: "Document") -> Command | None:
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.undo(document)
        self._redo_stack.append(command)
        return command

    def redo(self, document: "Document") -> Command | None:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.redo(document)
        self._undo_stack.append(command)
        return command

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def __len__(self) -> int:
        return len(self._undo_stack)
