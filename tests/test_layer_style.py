"""Kiểm thử Layer Style: mô hình, dựng hiệu ứng, compositor, dự án và hộp thoại."""

from __future__ import annotations

import numpy as np
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from config.settings import SettingsStore
from core.adjustment_layer import AdjustmentProperties
from core.document import Document
from core.layer import Layer, LayerKind
from core.layer_style import (
    BlendChannelRange,
    BlendIf,
    ColorOverlaySettings,
    DropShadowSettings,
    InnerGlowSettings,
    LayerStyle,
    PatternOverlaySettings,
    StrokeSettings,
    default_effect,
    effect_from_dict,
    effect_margin,
)
from core import layer_style as layer_style_module
from core.presets import PresetError, PresetStore
from formats.native_project import FORMAT_VERSION, load_project, save_project
from ui import main_window as main_window_module
from ui.dialogs import NewDocumentDialog  # noqa: F401  (đảm bảo module import sạch)
from ui.layer_style_dialog import STYLE_PRESET_KIND, LayerStyleDialog


# --------------------------------------------------------------------- tiện ích
def make_rect_document(
    canvas=(128, 96),
    rect=(32, 24, 64, 48),
    color=(255, 0, 0, 255),
) -> tuple[Document, Layer]:
    width, height = canvas
    x, y, layer_width, layer_height = rect
    document = Document(width, height, name="Style")
    pixels = np.zeros((layer_height, layer_width, 4), dtype=np.uint8)
    pixels[...] = color
    layer = Layer(layer_width, layer_height, "Rect")
    layer.pixels = pixels
    layer.offset_x = x
    layer.offset_y = y
    document.add_layer(layer=layer, select=True, record=False)
    document.mark_clean()
    return document, document.active_layer


def apply_style(document: Document, layer: Layer, style: LayerStyle) -> None:
    assert document.set_layer_style(layer, style, record=False)


def composite(document: Document) -> np.ndarray:
    return document.get_composite().array


def outside_content(canvas, rect) -> np.ndarray:
    width, height = canvas
    x, y, w, h = rect
    mask = np.ones((height, width), dtype=bool)
    mask[y : y + h, x : x + w] = False
    return mask


# ------------------------------------------------------------------- mô hình
def test_settings_clamp_and_validate():
    shadow = DropShadowSettings(opacity=4.0, size=9999, angle=-90)
    assert shadow.opacity == 1.0
    assert shadow.size == layer_style_module.MAX_EFFECT_SIZE
    assert shadow.angle == 270.0

    glow = InnerGlowSettings(source="CENTER")
    assert glow.source == "center"

    with pytest.raises(ValueError):
        DropShadowSettings(blend_mode="not-a-mode")
    with pytest.raises(ValueError):
        StrokeSettings(position="middle")
    with pytest.raises(ValueError):
        PatternOverlaySettings(pattern="zigzag")
    with pytest.raises(ValueError):
        BlendChannelRange(black_low="x")


def test_blend_channel_range_orders_handles():
    channel = BlendChannelRange(black_low=200, black_high=50, white_low=10, white_high=-5)
    assert (channel.black_low, channel.black_high, channel.white_low, channel.white_high) == (
        200,
        200,
        200,
        200,
    )
    assert not channel.is_identity
    assert BlendChannelRange().is_identity


def test_blend_channel_weight_and_blend_if_weights():
    hard = BlendChannelRange(white_low=128, white_high=128)
    values = np.array([0.2, 0.6, 0.9], dtype=np.float32)
    weight = hard.weight(values)
    assert weight[0] == 1.0
    assert weight[1] == 0.0
    assert weight[2] == 0.0

    soft = BlendChannelRange(white_low=100, white_high=200)
    mid = soft.weight(np.array([0.2, 0.6, 0.95], dtype=np.float32))
    assert mid[0] == 1.0
    assert 0.0 < mid[1] < 1.0
    assert mid[2] == 0.0

    this_layer = [BlendChannelRange() for _ in range(4)]
    this_layer[0] = BlendChannelRange(white_low=64, white_high=64)
    blend_if = BlendIf(this_layer=tuple(this_layer))
    source = np.full((2, 2, 3), 0.9, dtype=np.float32)
    assert np.allclose(blend_if.weights(source), 0.0)
    source_dark = np.full((2, 2, 3), 0.1, dtype=np.float32)
    assert np.allclose(blend_if.weights(source_dark), 1.0)


def test_layer_style_deduplicates_and_orders_effects():
    style = LayerStyle(
        effects=(
            ColorOverlaySettings(enabled=True, color=(0, 0, 255, 255)),
            DropShadowSettings(enabled=True),
            DropShadowSettings(enabled=False),
        )
    )
    kinds = [effect.kind for effect in style.effects]
    assert kinds == ["drop_shadow", "color_overlay"]
    assert style.has_effects
    assert len(style.enabled_effects) == 2


def test_layer_style_identity_and_roundtrip():
    assert LayerStyle().is_identity
    assert not LayerStyle(fill_opacity=0.5).is_identity
    assert not LayerStyle(knockout="deep").is_identity
    assert not LayerStyle(transparency_shapes_layer=False).is_identity
    assert not LayerStyle(effects=(DropShadowSettings(enabled=True),)).is_identity

    style = LayerStyle(
        fill_opacity=0.8,
        knockout="shallow",
        blend_interior_as_group=True,
        blend_clipped_as_group=True,
        transparency_shapes_layer=False,
        layer_mask_hides_effects=False,
        effects=(
            DropShadowSettings(enabled=True, color=(10, 20, 30, 200)),
            StrokeSettings(enabled=True, size=4.0, position="inside"),
            default_effect("pattern_overlay"),
        ),
    )
    assert LayerStyle.from_dict(style.to_dict()) == style
    assert "Drop Shadow" in style.summary()


def test_effect_from_dict_rejects_bad_data():
    with pytest.raises(ValueError):
        effect_from_dict(None)
    with pytest.raises(ValueError):
        effect_from_dict({"kind": "unknown"})
    with pytest.raises(ValueError):
        effect_from_dict({"kind": "drop_shadow", "opacity": "abc"})
    with pytest.raises(ValueError):
        LayerStyle.from_dict({"effects": "not-a-list"})
    with pytest.raises(ValueError):
        LayerStyle.from_dict({"effects": [{"kind": "drop_shadow", "size": "abc"}]})


def test_effect_margin_grows_with_enabled_effects():
    assert effect_margin(None) == 0
    assert effect_margin(LayerStyle()) == 0
    margin = effect_margin(
        LayerStyle(
            effects=(
                DropShadowSettings(enabled=True, distance=12, size=8),
                StrokeSettings(enabled=True, size=4),
            )
        )
    )
    assert margin >= 12 + 8 * 3


# --------------------------------------------------------------- compositor
def test_color_overlay_replaces_layer_pixels():
    document, layer = make_rect_document()
    apply_style(
        document,
        layer,
        LayerStyle(
            effects=(
                ColorOverlaySettings(enabled=True, color=(0, 0, 255, 255), opacity=1.0),
            )
        ),
    )
    result = composite(document)
    red, green, blue, alpha = result[48, 64]
    assert alpha == 255
    assert blue >= 250 and red <= 5 and green <= 5


def test_fill_opacity_lowers_content_alpha_only():
    document, layer = make_rect_document()
    apply_style(document, layer, LayerStyle(fill_opacity=0.5))
    result = composite(document)
    assert 100 <= result[48, 64, 3] <= 160
    assert result[0, 0, 3] == 0


def test_drop_shadow_draws_outside_content():
    document, layer = make_rect_document()
    apply_style(
        document,
        layer,
        LayerStyle(
            effects=(
                DropShadowSettings(
                    enabled=True,
                    opacity=1.0,
                    distance=10,
                    spread=4,
                    size=6,
                    angle=90,
                ),
            )
        ),
    )
    result = composite(document)
    mask = outside_content((128, 96), (32, 24, 64, 48))
    outside = result[..., 3][mask]
    assert outside.max() > 0
    assert outside.max() < 255


def test_stroke_outside_paints_border():
    document, layer = make_rect_document()
    apply_style(
        document,
        layer,
        LayerStyle(
            effects=(
                StrokeSettings(
                    enabled=True,
                    size=4,
                    position="outside",
                    color=(0, 0, 255, 255),
                    opacity=1.0,
                ),
            )
        ),
    )
    result = composite(document)
    border = result[48, 30]
    assert border[3] > 0
    assert int(border[2]) > int(border[0])
    assert result[48, 64, 0] > 200  # lòng layer vẫn đỏ


def test_blend_if_this_layer_hides_bright_pixels():
    document, layer = make_rect_document()
    ranges = [BlendChannelRange() for _ in range(4)]
    ranges[0] = BlendChannelRange(white_low=60, white_high=60)
    apply_style(document, layer, LayerStyle(blend_if=BlendIf(this_layer=tuple(ranges))))
    result = composite(document)
    assert result[48, 64, 3] == 0


def test_knockout_with_zero_fill_punches_through_backdrop():
    document = Document(64, 48, name="Knockout")
    background = Layer(64, 48, "Nền")
    background.fill((255, 255, 255, 255))
    document.add_layer(layer=background, select=True, record=False)
    top = Layer(16, 16, "Đục")
    top.pixels = np.zeros((16, 16, 4), dtype=np.uint8)
    top.pixels[..., 0] = 255
    top.pixels[..., 3] = 255
    top.offset_x = 24
    top.offset_y = 16
    document.add_layer(layer=top, select=True, record=False)
    document.mark_clean()

    apply_style(document, top, LayerStyle(fill_opacity=0.0, knockout="shallow"))
    result = composite(document)
    assert result[24, 32, 3] == 0  # vùng đục trở nên trong suốt
    assert result[2, 2, 3] == 255  # nền ngoài vùng đục còn nguyên


def test_layer_mask_hides_effects_flag_changes_shadow():
    document, layer = make_rect_document()
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[:, 32:] = 255
    layer.mask = mask
    layer.mask_enabled = True

    style = LayerStyle(
        layer_mask_hides_effects=True,
        effects=(
            DropShadowSettings(
                enabled=True, opacity=1.0, distance=0, spread=2, size=6
            ),
        ),
    )
    apply_style(document, layer, style)
    hidden = composite(document)
    left_inside = (48, 40)
    assert hidden[left_inside[0], left_inside[1], 3] == 0

    document.set_layer_style(
        layer,
        LayerStyle(
            layer_mask_hides_effects=False,
            effects=style.effects,
        ),
        record=False,
    )
    shown = composite(document)
    assert shown[left_inside[0], left_inside[1], 3] > 0


def test_transparency_shapes_layer_controls_overlay_region():
    document, layer = make_rect_document()
    # Nửa phải của layer trong suốt nhưng vẫn nằm trong hộp layer.
    layer.pixels[:, 32:, 3] = 0
    overlay = ColorOverlaySettings(enabled=True, color=(0, 255, 0, 255), opacity=1.0)

    apply_style(
        document,
        layer,
        LayerStyle(transparency_shapes_layer=True, effects=(overlay,)),
    )
    shaped = composite(document)
    assert shaped[48, 90, 3] == 0  # vùng trong suốt không bị tô

    document.set_layer_style(
        layer,
        LayerStyle(transparency_shapes_layer=False, effects=(overlay,)),
        record=False,
    )
    boxed = composite(document)
    assert boxed[48, 90, 3] > 0  # tô kín hộp layer
    assert boxed[48, 90, 1] > 200


def test_effects_stay_inside_tiles_when_compositing_region():
    from core.canvas import composite_region

    document, layer = make_rect_document()
    apply_style(
        document,
        layer,
        LayerStyle(
            effects=(
                DropShadowSettings(enabled=True, distance=6, size=5, opacity=1.0),
            )
        ),
    )
    full = composite(document)
    tile = composite_region(document.layers.layers, 128, 96, 0, 40, 128, 96)
    assert np.array_equal(tile, full[40:96])


# ----------------------------------------------------------- Document + .mps
def test_document_style_undo_redo_keeps_single_step():
    document, layer = make_rect_document()
    style = LayerStyle(effects=(DropShadowSettings(enabled=True),))
    assert document.set_layer_style(layer, style, blend_mode="screen", opacity=0.5)
    assert layer.style == style
    assert layer.blend_mode == "screen"
    assert abs(layer.opacity - 0.5) < 1e-6
    assert document.history.can_undo

    document.undo()
    assert layer.style is None
    assert layer.blend_mode == "normal"
    assert abs(layer.opacity - 1.0) < 1e-6

    document.redo()
    assert layer.style == style
    assert layer.blend_mode == "screen"


def test_adjustment_layer_rejects_blend_mode_change():
    document = Document(32, 24, name="Adj")
    adjustment = document.add_adjustment_layer(AdjustmentProperties(), record=False)
    with pytest.raises(ValueError):
        document.set_layer_style(adjustment, None, blend_mode="screen")
    assert document.set_layer_style(adjustment, None, opacity=0.4)
    assert abs(adjustment.opacity - 0.4) < 1e-6


def test_layer_copy_keeps_style():
    _, layer = make_rect_document()
    layer.style = LayerStyle(effects=(DropShadowSettings(enabled=True),))
    clone = layer.copy()
    assert clone.style == layer.style


def test_project_format_roundtrip_preserves_style(tmp_path):
    assert FORMAT_VERSION >= 10
    document, layer = make_rect_document()
    style = LayerStyle(
        fill_opacity=0.75,
        knockout="shallow",
        blend_if=BlendIf(this_layer=(BlendChannelRange(white_low=20, white_high=40),) * 4),
        effects=(
            DropShadowSettings(enabled=True, distance=7, color=(5, 6, 7, 128)),
            StrokeSettings(enabled=True, size=3, position="inside"),
        ),
    )
    apply_style(document, layer, style)
    path = save_project(document, tmp_path / "style.mps")

    loaded = load_project(path)
    loaded_layer = loaded.layers.layers[0]
    assert loaded_layer.style == style
    assert loaded_layer.style.effect("drop_shadow").distance == 7


def test_project_with_bad_style_is_rejected(tmp_path):
    import json
    import zipfile

    source, _layer = make_rect_document()
    path = save_project(source, tmp_path / "bad.mps")
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries["manifest.json"].decode("utf-8"))
    manifest["layers"][0]["style"] = {"effects": "không hợp lệ"}
    entries["manifest.json"] = json.dumps(manifest).encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)

    with pytest.raises(Exception) as excinfo:
        load_project(path)
    assert "layer style" in str(excinfo.value)


# --------------------------------------------------------------------- UI
@pytest.fixture
def styled_dialog(qapp, tmp_path):
    document, layer = make_rect_document()
    store = PresetStore(tmp_path / "presets.sqlite3")
    dialog = LayerStyleDialog(None, document, layer, preset_store=store)
    yield dialog, document, layer, store
    dialog.deleteLater()


def test_dialog_lists_all_effects_and_previews(styled_dialog, qapp):
    dialog, document, layer, _store = styled_dialog
    assert len(dialog._effect_items) == 10
    assert dialog.preview_label.pixmap() is not None
    assert not dialog.preview_label.pixmap().isNull()

    item = dialog._effect_items["drop_shadow"]
    item.setCheckState(Qt.CheckState.Checked)
    qapp.processEvents()
    assert dialog._style.effect("drop_shadow").enabled
    assert layer.style is None  # tài liệu chỉ đổi sau khi OK


def test_dialog_accept_returns_style_and_undo_step(styled_dialog, qapp):
    dialog, document, layer, _store = styled_dialog
    dialog._effect_items["outer_glow"].setCheckState(Qt.CheckState.Checked)
    dialog.fill_opacity_spin.setValue(40)
    dialog.opacity_spin.setValue(80)
    dialog.accept()

    assert dialog.style is not None
    assert dialog.style.effect("outer_glow").enabled
    assert abs(dialog.style.fill_opacity - 0.4) < 1e-6
    assert abs(dialog.opacity - 0.8) < 1e-6

    assert document.set_layer_style(
        layer, dialog.style, blend_mode=dialog.blend_mode, opacity=dialog.opacity
    )
    assert layer.style == dialog.style
    document.undo()
    assert layer.style is None


def test_dialog_blend_if_slider_updates_style(styled_dialog, qapp):
    dialog, _document, _layer, _store = styled_dialog
    dialog._on_blend_slider("this_layer", (0, 0, 120, 200))
    style = dialog._build_style()
    assert style is not None
    assert not style.blend_if.is_identity
    assert style.blend_if.this_layer[0].white_low == 120


def test_dialog_preset_save_and_apply(styled_dialog, qapp):
    dialog, _document, _layer, store = styled_dialog
    preset_style = LayerStyle(effects=(DropShadowSettings(enabled=True, distance=9),))
    store.save(STYLE_PRESET_KIND, "Bóng đổ", preset_style.to_dict())
    dialog._refresh_preset_list()
    assert dialog.preset_list.count() == 2

    dialog._apply_selected_preset(dialog.preset_list.item(1))
    assert dialog._style == preset_style
    assert dialog._effect_items["drop_shadow"].checkState() == Qt.CheckState.Checked

    with pytest.raises(PresetError):
        store.save(STYLE_PRESET_KIND, "Bóng đổ", preset_style.to_dict())


def test_dialog_adjustment_layer_disables_effects(qapp, tmp_path):
    document = Document(48, 32, name="Adj")
    adjustment = document.add_adjustment_layer(AdjustmentProperties(), record=False)
    dialog = LayerStyleDialog(None, document, adjustment, preset_store=None)
    try:
        item = dialog._effect_items["drop_shadow"]
        assert not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        dialog.opacity_spin.setValue(70)
        dialog.accept()
        assert dialog.style is None
        assert abs(dialog.opacity - 0.7) < 1e-6
        assert dialog.blend_mode == adjustment.blend_mode
    finally:
        dialog.deleteLater()


def test_main_window_blending_options_uses_layer_style_dialog(qapp, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    window = main_window_module.MainWindow(store)
    try:
        document, layer = make_rect_document()
        window._add_document_tab(document)
        qapp.processEvents()
        assert window.current_document is document

        class FakeDialog:
            def __init__(self, parent, doc, target, *, preset_store=None):
                self.style = LayerStyle(
                    effects=(DropShadowSettings(enabled=True),)
                )
                self.blend_mode = "screen"
                self.opacity = 0.6

        monkeypatch.setattr(main_window_module, "LayerStyleDialog", FakeDialog)
        monkeypatch.setattr(
            main_window_module, "exec_object", lambda dialog: QDialog.DialogCode.Accepted
        )
        window._on_blending_options()
        qapp.processEvents()
        assert layer.style is not None
        assert layer.style.effect("drop_shadow").enabled
        assert layer.blend_mode == "screen"
        assert abs(layer.opacity - 0.6) < 1e-6
    finally:
        document.mark_clean()
        window.close()
        window.deleteLater()
