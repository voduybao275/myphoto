"""Tiện ích định dạng hiển thị."""

from __future__ import annotations


def format_zoom(zoom: float) -> str:
    percent = zoom * 100.0
    text = f"{percent:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def format_memory(num_bytes: int) -> str:
    megabytes = num_bytes / (1024 * 1024)
    if megabytes >= 1024:
        return f"{megabytes / 1024:.2f} GB"
    return f"{megabytes:.1f} MB"
