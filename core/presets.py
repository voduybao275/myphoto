"""Thư viện preset cục bộ bằng SQLite (điều chỉnh màu, action, layer style).

Không dùng mạng. Mỗi preset là một bản ghi gồm ``kind`` (``adjustment``,
``action`` hoặc ``layer_style``), ``name`` duy nhất trong từng loại và
``payload`` JSON.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.settings import app_config_dir

logger = logging.getLogger(__name__)

PRESET_KINDS = ("adjustment", "action", "layer_style")
MAX_PRESET_NAME = 48
_SCHEMA = """
CREATE TABLE IF NOT EXISTS presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(kind, name)
)
"""


class PresetError(Exception):
    """Lỗi thư viện preset với thông điệp thân thiện."""


@dataclass(frozen=True)
class Preset:
    preset_id: int
    kind: str
    name: str
    payload: dict
    updated_at: str


def _normalize_name(name: object) -> str:
    text = str(name).strip()
    if not text:
        raise PresetError("Tên preset không được để trống.")
    if len(text) > MAX_PRESET_NAME:
        raise PresetError(
            f"Tên preset quá dài (tối đa {MAX_PRESET_NAME} ký tự)."
        )
    return text


def _normalize_kind(kind: object) -> str:
    text = str(kind).strip().lower()
    if text not in PRESET_KINDS:
        raise PresetError(f"Loại preset không hợp lệ: {kind}")
    return text


class PresetStore:
    """Đọc/ghi preset trong một file SQLite, tạo schema khi cần."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else (app_config_dir() / "presets.sqlite3")

    # ------------------------------------------------------------- kết nối
    def _connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(_SCHEMA)
            return connection
        except (OSError, sqlite3.Error) as exc:
            raise PresetError(
                f"Không mở được thư viện preset.\nChi tiết: {exc}"
            ) from exc

    @staticmethod
    def _encode(payload: object) -> str:
        if not isinstance(payload, dict):
            raise PresetError("Dữ liệu preset phải là một đối tượng.")
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise PresetError("Dữ liệu preset không lưu được.") from exc

    @staticmethod
    def _row_to_preset(row) -> Preset | None:
        preset_id, kind, name, payload_text, updated_at = row
        try:
            payload = json.loads(payload_text)
        except (TypeError, ValueError):
            logger.warning("Bỏ qua preset '%s' vì dữ liệu JSON hỏng.", name)
            return None
        if not isinstance(payload, dict):
            return None
        return Preset(
            preset_id=int(preset_id),
            kind=str(kind),
            name=str(name),
            payload=payload,
            updated_at=str(updated_at),
        )

    # ---------------------------------------------------------------- đọc
    def list(self, kind: str | None = None) -> list[Preset]:
        """Danh sách preset, sắp xếp theo tên không phân biệt hoa thường."""
        query = "SELECT id, kind, name, payload, updated_at FROM presets"
        params: tuple[object, ...] = ()
        if kind is not None:
            query += " WHERE kind = ?"
            params = (_normalize_kind(kind),)
        query += " ORDER BY name COLLATE NOCASE, id"
        try:
            with self._connect() as connection:
                rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise PresetError(
                f"Không đọc được thư viện preset.\nChi tiết: {exc}"
            ) from exc
        presets = [self._row_to_preset(row) for row in rows]
        return [preset for preset in presets if preset is not None]

    def get(self, kind: str, name: str) -> Preset | None:
        normalized_kind = _normalize_kind(kind)
        normalized_name = _normalize_name(name)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT id, kind, name, payload, updated_at "
                    "FROM presets WHERE kind = ? AND name = ? COLLATE NOCASE",
                    (normalized_kind, normalized_name),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PresetError(
                f"Không đọc được preset.\nChi tiết: {exc}"
            ) from exc
        return self._row_to_preset(row) if row is not None else None

    def count(self, kind: str | None = None) -> int:
        return len(self.list(kind))

    # --------------------------------------------------------------- ghi
    def save(
        self,
        kind: str,
        name: str,
        payload: object,
        *,
        overwrite: bool = False,
    ) -> Preset:
        normalized_kind = _normalize_kind(kind)
        normalized_name = _normalize_name(name)
        encoded = self._encode(payload)
        if not overwrite and self.get(normalized_kind, normalized_name):
            raise PresetError(
                f"Preset '{normalized_name}' đã tồn tại. "
                "Hãy chọn tên khác hoặc xác nhận ghi đè."
            )
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO presets(kind, name, payload, updated_at) "
                    "VALUES(?, ?, ?, ?) "
                    "ON CONFLICT(kind, name) DO UPDATE SET "
                    "payload = excluded.payload, updated_at = excluded.updated_at",
                    (normalized_kind, normalized_name, encoded, stamp),
                )
        except sqlite3.Error as exc:
            raise PresetError(
                f"Không lưu được preset.\nChi tiết: {exc}"
            ) from exc
        saved = self.get(normalized_kind, normalized_name)
        if saved is None:
            raise PresetError("Không đọc lại được preset vừa lưu.")
        return saved

    def delete(self, kind: str, name: str) -> bool:
        normalized_kind = _normalize_kind(kind)
        normalized_name = _normalize_name(name)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM presets WHERE kind = ? AND name = ? COLLATE NOCASE",
                    (normalized_kind, normalized_name),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise PresetError(
                f"Không xoá được preset.\nChi tiết: {exc}"
            ) from exc

    def rename(self, kind: str, old_name: str, new_name: str) -> Preset:
        normalized_kind = _normalize_kind(kind)
        old = _normalize_name(old_name)
        new = _normalize_name(new_name)
        if self.get(normalized_kind, old) is None:
            raise PresetError(f"Không tìm thấy preset '{old}'.")
        if old != new and self.get(normalized_kind, new) is not None:
            raise PresetError(f"Preset '{new}' đã tồn tại.")
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE presets SET name = ?, updated_at = ? "
                    "WHERE kind = ? AND name = ? COLLATE NOCASE",
                    (
                        new,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        normalized_kind,
                        old,
                    ),
                )
        except sqlite3.Error as exc:
            raise PresetError(
                f"Không đổi tên preset.\nChi tiết: {exc}"
            ) from exc
        renamed = self.get(normalized_kind, new)
        if renamed is None:
            raise PresetError("Không đọc lại được preset vừa đổi tên.")
        return renamed

    # ---------------------------------------------------- helper có kiểu
    def save_adjustment(
        self, name: str, properties, *, overwrite: bool = False
    ) -> Preset:
        from core.adjustment_layer import AdjustmentProperties

        if not isinstance(properties, AdjustmentProperties):
            raise PresetError("Preset điều chỉnh cần AdjustmentProperties.")
        return self.save(
            "adjustment", name, properties.to_dict(), overwrite=overwrite
        )

    def load_adjustment(self, name: str):
        from core.adjustment_layer import AdjustmentProperties

        preset = self.get("adjustment", name)
        if preset is None:
            return None
        try:
            return AdjustmentProperties.from_dict(preset.payload)
        except ValueError as exc:
            raise PresetError(
                f"Preset '{preset.name}' có dữ liệu không hợp lệ.\n{exc}"
            ) from exc

    def save_action(
        self, name: str, action, *, overwrite: bool = False
    ) -> Preset:
        from core.batch import BatchAction

        if not isinstance(action, BatchAction):
            raise PresetError("Preset action cần BatchAction.")
        return self.save(
            "action", name, action.to_dict(), overwrite=overwrite
        )

    def load_action(self, name: str):
        from core.batch import BatchAction

        preset = self.get("action", name)
        if preset is None:
            return None
        try:
            return BatchAction.from_dict(preset.payload)
        except ValueError as exc:
            raise PresetError(
                f"Preset '{preset.name}' có dữ liệu không hợp lệ.\n{exc}"
            ) from exc
