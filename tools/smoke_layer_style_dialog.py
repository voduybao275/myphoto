"""Smoke test: dựng LayerStyleDialog ngoài màn hình và áp style thật."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from compat.qt import QT_BINDING  # noqa: F401  (kích hoạt ánh xạ Qt trước)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from core.document import Document
from core.layer import Layer
from core.presets import PresetStore
from ui.layer_style_dialog import LayerStyleDialog


def main() -> None:
    app = QApplication.instance() or QApplication([])
    doc = Document(220, 160)
    pixels = np.zeros((80, 120, 4), dtype=np.uint8)
    pixels[..., 0] = 220
    pixels[..., 3] = 255
    layer = Layer(120, 80, "Hộp đỏ")
    layer.pixels = pixels
    layer.offset_x = 50
    layer.offset_y = 40
    doc.add_layer(layer=layer, select=True)

    store = PresetStore(Path(os.environ.get("TEMP", ".")) / "smoke_presets.sqlite3")
    dialog = LayerStyleDialog(None, doc, layer, preset_store=store)

    shadow_item = dialog._effect_items["drop_shadow"]
    shadow_item.setCheckState(Qt.CheckState.Checked)
    assert layer.style is None, "document layer must stay untouched while previewing"
    assert dialog._style.effect("drop_shadow").enabled

    dialog.fill_opacity_spin.setValue(60)
    dialog.accept()
    assert dialog.style is not None
    assert dialog.style.effect("drop_shadow").enabled
    assert abs(dialog.style.fill_opacity - 0.6) < 1e-6

    changed = doc.set_layer_style(layer, dialog.style, blend_mode=dialog.blend_mode, opacity=dialog.opacity)
    assert changed
    assert layer.style is not None
    assert layer.style.effect("drop_shadow").enabled

    doc.undo()
    assert layer.style is None
    doc.redo()
    assert layer.style is not None

    composite = doc.get_composite()
    assert composite.array[..., 3].max() > 0
    assert composite.array[0, 0, 3] == 0
    print(
        "OK: dialog -> style -> undo/redo, alpha max",
        int(composite.array[..., 3].max()),
    )
    app.quit()


if __name__ == "__main__":
    main()
