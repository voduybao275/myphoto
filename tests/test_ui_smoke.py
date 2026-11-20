"""Smoke test giao diện: dựng MainWindow, thêm layer, undo, đổi theme, đóng tab."""

from __future__ import annotations

import numpy as np
import pytest

from PySide6.QtCore import Qt, QEvent, QPointF
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu

from config.settings import THEME_DARK, THEME_LIGHT, SettingsStore
from core.adjustment_layer import AdjustmentProperties
from core.document import Document, rotated_dimensions
from core.layer import LayerKind
from core.shape_layer import ShapeProperties
from core.text_layer import TextProperties, TextRun
from ui import theme
from ui.dialogs import (
    AdjustmentLayerDialog,
    BrightnessContrastDialog,
    CanvasSizeDialog,
    FeatherDialog,
    GaussianBlurDialog,
    HueSaturationDialog,
    ImageSizeDialog,
    RotateDialog,
    ShapeDialog,
    TextDialog,
    UnsharpMaskDialog,
)
from ui.layers_panel import (
    ROLE_CLIPPING,
    ROLE_COLOR_LABEL,
    ROLE_KIND,
    ROLE_SUBTITLE,
    LayersPanel,
)
from ui.main_window import MainWindow


def test_main_window_smoke(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    assert window.tabs.count() == 0

    document = Document(64, 48, name="Smoke")
    document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    assert window.tabs.count() == 1
    assert window.current_document is document
    assert window.layers_panel.document is document
    assert window.properties_panel.document is document

    window._on_new_layer()
    qapp.processEvents()
    assert len(document.layers) == 2
    assert document.modified
    assert document.history.can_undo

    window._on_undo()
    qapp.processEvents()
    assert len(document.layers) == 1
    assert not document.history.can_undo

    view = window.current_view
    assert view is not None
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_H, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)
    assert view.tool_id == "hand"
    assert window.toolbox._actions["hand"].isChecked()

    view.set_zoom(2.0)
    assert view.zoom == 2.0
    view.fit_to_window()
    assert 0.02 <= view.zoom <= 4.0

    window._set_theme(THEME_LIGHT)
    qapp.processEvents()
    assert theme.current_theme().name == THEME_LIGHT
    assert window.action_theme_light.isChecked()

    window._set_theme(THEME_DARK)
    qapp.processEvents()
    assert theme.current_theme().name == THEME_DARK
    assert window.action_theme_dark.isChecked()

    pixmap = window.grab()
    assert not pixmap.isNull()

    screenshot = tmp_path / "smoke.png"
    assert pixmap.save(str(screenshot), "PNG")
    assert screenshot.exists() and screenshot.stat().st_size > 0

    window._remove_view(view)
    qapp.processEvents()
    assert window.tabs.count() == 0
    assert window.current_document is None

    window.close()


def test_selection_mask_crop_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(96, 64, name="Phase 2")
    layer = document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    for tool_id in ("rect_select", "ellipse_select", "crop"):
        assert tool_id in window.toolbox._actions

    view = window.current_view
    view.set_tool("rect_select")
    qapp.processEvents()
    assert window.toolbox._actions["rect_select"].isChecked()

    start = view.image_to_widget(QPointF(10.0, 10.0)).toPoint()
    end = view.image_to_widget(QPointF(60.0, 44.0)).toPoint()
    QTest.mousePress(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    QTest.mouseRelease(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end
    )
    qapp.processEvents()

    assert document.has_selection()
    bounds = document.selection.bounds()
    assert bounds.width() >= 40
    assert view._ants_timer.isActive()

    window._on_add_layer_mask()
    qapp.processEvents()
    assert layer.mask is not None
    assert window.action_toggle_mask.isEnabled()
    window.action_toggle_mask.trigger()
    qapp.processEvents()
    assert not layer.mask_enabled
    document.undo()

    window._on_crop_tool()
    qapp.processEvents()
    assert view.tool_id == "crop"
    assert view.crop_rect is not None
    old_width = document.width
    assert view.apply_crop()
    assert document.width < old_width
    assert document.selection is None
    document.undo()
    assert document.width == old_width

    view.set_tool("ellipse_select")
    image_dialog = ImageSizeDialog(document, window)
    image_dialog.width_spin.setValue(48)
    assert image_dialog.image_height == 32
    assert image_dialog.method == "bicubic"
    image_dialog.close()

    canvas_dialog = CanvasSizeDialog(document, window)
    canvas_dialog.anchor_picker.set_anchor("top_left")
    assert canvas_dialog.anchor == "top_left"
    canvas_dialog.close()

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_rotate_arbitrary_ui(qapp, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(48, 32, name="Free rotate")
    document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    assert window.action_rotate_arbitrary.isEnabled()
    assert window.action_layer_rotate_arbitrary.isEnabled()

    new_width, new_height = rotated_dimensions(48, 32, 30.0)
    dialog = RotateDialog(48, 32, subject="canvas", parent=window)
    dialog.angle_spin.setValue(30.0)
    assert dialog.angle == 30.0
    assert dialog.method == "bicubic"
    assert f"{new_width} × {new_height}" in dialog.info_label.text()
    dialog.close()

    def fake_exec(dialog):
        dialog.angle_spin.setValue(30.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("ui.main_window.exec_object", fake_exec)

    window.action_rotate_arbitrary.trigger()
    qapp.processEvents()
    assert (document.width, document.height) == (new_width, new_height)
    assert document.history.can_undo

    layer = document.active_layer
    layer_dims = (layer.width, layer.height)
    window.action_layer_rotate_arbitrary.trigger()
    qapp.processEvents()
    assert (document.width, document.height) == (new_width, new_height)
    assert (layer.width, layer.height) == rotated_dimensions(
        layer_dims[0], layer_dims[1], 30.0
    )

    window._on_undo()
    window._on_undo()
    qapp.processEvents()
    assert (document.width, document.height) == (48, 32)
    assert (layer.width, layer.height) == (48, 32)

    view = window.current_view
    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_rotate_flip_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(48, 32, name="Phase 3")
    layer = document.add_layer(name="Background", color=(200, 120, 60, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    assert view is not None
    assert window.action_rotate_cw.isEnabled()
    assert window.action_flip_canvas_h.isEnabled()
    assert window.action_layer_rotate_cw.isEnabled()

    window.action_rotate_cw.trigger()
    qapp.processEvents()
    assert (document.width, document.height) == (32, 48)
    assert document.history.can_undo

    window.action_flip_canvas_v.trigger()
    qapp.processEvents()
    assert (document.width, document.height) == (32, 48)

    window.action_layer_rotate_cw.trigger()
    qapp.processEvents()
    assert (layer.width, layer.height) == (48, 32)
    assert (document.width, document.height) == (32, 48)

    for _ in range(3):
        window._on_undo()
    qapp.processEvents()
    assert (document.width, document.height) == (48, 32)
    assert (layer.width, layer.height) == (48, 32)

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_filter_menu_ui(qapp, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(32, 24, name="Filters UI")
    layer = document.add_layer(
        name="Colors", color=(10, 20, 30, 255), record=False
    )
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    filter_menu = next(
        menu
        for menu in window._menu_bar.findChildren(QMenu)
        if menu.title().replace("&", "") == "Filter"
    )
    assert [menu_action.text() for menu_action in filter_menu.actions()][:3] == [
        "Adjustments",
        "",
        "Blur",
    ]

    filter_actions = (
        window.action_filter_brightness_contrast,
        window.action_filter_hue_saturation,
        window.action_filter_auto_contrast,
        window.action_filter_invert,
        window.action_filter_desaturate,
        window.action_filter_gaussian_blur,
        window.action_filter_unsharp_mask,
    )
    assert all(action.isEnabled() for action in filter_actions)

    window.action_filter_invert.trigger()
    qapp.processEvents()
    assert tuple(layer.pixels[0, 0]) == (245, 235, 225, 255)
    assert document.history.can_undo
    window._on_undo()
    qapp.processEvents()
    assert tuple(layer.pixels[0, 0]) == (10, 20, 30, 255)

    window.action_filter_auto_contrast.trigger()
    qapp.processEvents()
    assert not document.history.can_undo
    assert "không tạo ra thay đổi" in window.statusBar().currentMessage()

    brightness_dialog = BrightnessContrastDialog(layer, window)
    brightness_dialog.brightness_field.setValue(40)
    brightness_dialog._update_preview()
    pixmap = brightness_dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert "Xem trước" in brightness_dialog.info_label.text()
    assert tuple(brightness_dialog.filtered_pixels()[0, 0]) == (112, 122, 132, 255)
    brightness_dialog.close()

    hue_dialog = HueSaturationDialog(layer, window)
    assert hue_dialog.hue == 0 and hue_dialog.saturation == 0
    assert hue_dialog.filtered_pixels().shape == layer.pixels.shape
    hue_dialog.close()

    blur_dialog = GaussianBlurDialog(layer, window)
    assert blur_dialog.radius == 2.0
    assert blur_dialog.filtered_pixels().shape == layer.pixels.shape
    blur_dialog.close()

    unsharp_dialog = UnsharpMaskDialog(layer, window)
    assert unsharp_dialog.amount == 100 and unsharp_dialog.threshold == 0
    unsharp_dialog.close()

    def accept_brightness(dialog):
        dialog.brightness_field.setValue(-40)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("ui.main_window.exec_object", accept_brightness)
    window.action_filter_brightness_contrast.trigger()
    qapp.processEvents()
    assert tuple(layer.pixels[0, 0]) == (0, 0, 0, 255)
    window._on_undo()
    qapp.processEvents()
    assert tuple(layer.pixels[0, 0]) == (10, 20, 30, 255)

    layer.locked = True
    window._update_action_states()
    assert all(not action.isEnabled() for action in filter_actions)
    layer.locked = False
    window._update_action_states()
    assert all(action.isEnabled() for action in filter_actions)

    window._remove_view(window.current_view)
    document.mark_clean()
    window.close()


def test_text_dialog_preview(qapp):
    dialog = TextDialog()
    assert dialog.preview_label.text()
    dialog.text_edit.setPlainText("Xin chào")
    dialog.size_spin.setValue(24)
    dialog.bold_check.setChecked(True)
    dialog.line_spacing_spin.setValue(1.5)
    dialog.letter_spacing_spin.setValue(4)
    dialog._update_preview()
    assert dialog.properties.text == "Xin chào"
    assert dialog.properties.font_size == 24
    assert dialog.properties.bold
    assert dialog.properties.line_spacing == 1.5
    assert dialog.properties.letter_spacing == 4
    pixmap = dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert "Layer dự kiến" in dialog.info_label.text()
    assert "giãn dòng 1.5×" in dialog.info_label.text()

    editing = TextDialog(properties=dialog.properties, editing=True)
    assert editing.text_edit.toPlainText() == "Xin chào"
    assert editing.bold_check.isChecked()
    assert editing.alignment_combo.currentData() == "left"
    assert editing.line_spacing_spin.value() == 1.5
    assert editing.letter_spacing_spin.value() == 4
    editing.close()
    dialog.close()


def test_text_dialog_formats_selection(qapp):
    dialog = TextDialog()
    dialog.text_edit.setPlainText("Xin chào thế giới")
    dialog.size_spin.setValue(40)

    start = dialog.text_edit.toPlainText().index("thế")
    cursor = dialog.text_edit.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len("thế giới"), QTextCursor.MoveMode.KeepAnchor)
    dialog.text_edit.setTextCursor(cursor)
    dialog.size_spin.setValue(22)
    dialog.bold_check.setChecked(True)

    properties = dialog.properties
    assert properties.text == "Xin chào thế giới"
    assert len(properties.runs) == 2
    assert properties.runs[0].text == "Xin chào "
    assert properties.runs[0].font_size == 40
    assert properties.runs[0].bold is False
    assert properties.runs[1].text == "thế giới"
    assert properties.runs[1].font_size == 22
    assert properties.runs[1].bold is True

    dialog._update_preview()
    assert "2 kiểu chữ" in dialog.info_label.text()
    dialog.close()


def test_text_dialog_edits_rich_runs(qapp):
    properties = TextProperties(
        runs=(
            TextRun("Hello ", font_family="Arial", font_size=40, bold=True),
            TextRun("world", font_family="Arial", font_size=22, color=(60, 120, 255, 255)),
        ),
        alignment="center",
        line_spacing=1.4,
        letter_spacing=3,
    )
    dialog = TextDialog(properties=properties, editing=True)
    assert dialog.text_edit.toPlainText() == "Hello world"
    assert dialog.properties == properties

    # Con trỏ ở cuối: điều khiển phản ánh run cuối.
    assert dialog.size_spin.value() == 22
    assert dialog.bold_check.isChecked() is False

    # Đưa con trỏ về đầu: điều khiển phản ánh run đầu.
    cursor = dialog.text_edit.textCursor()
    cursor.setPosition(0)
    dialog.text_edit.setTextCursor(cursor)
    assert dialog.size_spin.value() == 40
    assert dialog.bold_check.isChecked() is True

    # Chọn "world" và đổi cỡ: chỉ run thứ hai thay đổi.
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    dialog.text_edit.setTextCursor(cursor)
    dialog.size_spin.setValue(30)
    edited = dialog.properties
    assert [run.font_size for run in edited.runs] == [40, 30]
    assert edited.runs[0].bold is True
    assert edited.alignment == "center"
    assert edited.line_spacing == 1.4
    assert edited.letter_spacing == 3
    dialog.close()


def test_text_dialog_roundtrips_legacy_and_multiline(qapp):
    for properties in (
        TextProperties("Xin chào", font_size=20),
        TextProperties("Dòng 1\nDòng 2\n", font_size=24, color=(10, 20, 30, 255)),
        TextProperties("Uốn chữ", font_size=28, warp_style="arch", warp_bend=-45),
    ):
        dialog = TextDialog(properties=properties, editing=True)
        assert dialog.text_edit.toPlainText() == properties.text
        assert dialog.properties == properties
        dialog.close()


def test_text_dialog_warp_controls(qapp):
    dialog = TextDialog()
    dialog.text_edit.setPlainText("Uốn chữ")
    assert dialog.warp_combo.currentData() == "none"
    assert not dialog.warp_bend_spin.isEnabled()
    assert dialog.properties.warp_style == "none"
    assert dialog.properties.warp_bend == 0

    dialog.warp_combo.setCurrentIndex(dialog.warp_combo.findData("wave"))
    assert dialog.warp_bend_spin.isEnabled()
    assert dialog.warp_bend_spin.value() == 50
    dialog.warp_bend_spin.setValue(-35)
    dialog._update_preview()
    properties = dialog.properties
    assert properties.warp_style == "wave"
    assert properties.warp_bend == -35
    assert "uốn lượn sóng -35%" in dialog.info_label.text()
    pixmap = dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()

    editing = TextDialog(properties=properties, editing=True)
    assert editing.warp_combo.currentData() == "wave"
    assert editing.warp_bend_spin.value() == -35
    assert editing.warp_bend_spin.isEnabled()
    assert editing.properties == properties

    editing.warp_combo.setCurrentIndex(editing.warp_combo.findData("none"))
    assert not editing.warp_bend_spin.isEnabled()
    assert editing.properties.warp_style == "none"
    assert editing.properties.warp_bend == 0

    editing.close()
    dialog.close()


def test_text_dialog_kerning_and_path_controls(qapp):
    dialog = TextDialog()
    dialog.text_edit.setPlainText("AVATAR")
    dialog.kerning_edit.setText("AV=-6, VA=-4")
    dialog._update_preview()
    assert dialog.properties.kerning_pairs == (("AV", -6), ("VA", -4))
    assert "kerning 2 cặp" in dialog.info_label.text()

    dialog.path_combo.setCurrentIndex(dialog.path_combo.findData("arc"))
    assert dialog.path_bend_spin.isEnabled()
    assert dialog.path_bend_spin.value() == 60
    assert not dialog.warp_combo.isEnabled()
    dialog.path_bend_spin.setValue(-45)
    dialog._update_preview()
    properties = dialog.properties
    assert properties.path_style == "arc"
    assert properties.path_bend == -45
    assert "đường dẫn cung tròn -45%" in dialog.info_label.text()
    pixmap = dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()

    editing = TextDialog(properties=properties, editing=True)
    assert editing.kerning_edit.text() == "AV=-6, VA=-4"
    assert editing.path_combo.currentData() == "arc"
    assert editing.path_bend_spin.value() == -45
    assert editing.path_bend_spin.isEnabled()
    assert not editing.warp_combo.isEnabled()
    assert editing.properties == properties

    editing.kerning_edit.setText("AV")
    editing._update_preview()
    assert "AB=giá trị" in editing.preview_label.text()

    editing.kerning_edit.setText("AV=-6")
    editing.path_combo.setCurrentIndex(editing.path_combo.findData("none"))
    assert not editing.path_bend_spin.isEnabled()
    assert editing.warp_combo.isEnabled()
    assert editing.properties.path_style == "none"
    assert editing.properties.path_bend == 0
    editing.close()
    dialog.close()


def test_properties_panel_shows_text_path_and_kerning(qapp):
    from ui.properties_panel import PropertiesPanel

    document = Document(220, 140, name="Path info")
    layer = document.add_text_layer(
        TextProperties(
            "Vòng chữ",
            font_size=32,
            path_style="circle",
            path_bend=55,
            kerning_pairs=(("Vò", -3),),
        ),
        record=False,
    )
    panel = PropertiesPanel()
    panel.bind_document(document)
    document.set_active_layer(layer)
    panel.refresh()
    info = panel._values["layer_info"].text()
    assert "Đường dẫn: Vòng tròn +55%" in info
    assert "Kerning: Vò-3" in info
    panel.deleteLater()


def test_text_properties_panel_shows_transform(qapp):
    from ui.properties_panel import PropertiesPanel

    document = Document(240, 180, name="Text transform")
    layer = document.add_text_layer(
        TextProperties("Properties", font_size=24), 30, 40, record=False
    )
    panel = PropertiesPanel()
    panel.bind_document(document)
    panel.show()
    qapp.processEvents()

    assert not panel.text_properties.isHidden()
    assert panel.text_width.value() == float(layer.width)
    assert panel.text_height.value() == float(layer.height)
    assert panel.text_x.value() == 30
    assert panel.text_y.value() == 40
    assert panel.text_angle.value() == 0.0
    assert panel.text_angle.isReadOnly()
    assert not panel.text_link_button.isEnabled()
    assert not panel.text_flip_h.isEnabled()
    assert not panel.text_flip_v.isEnabled()
    assert panel.transform_section.reset_button is not None
    assert not panel.transform_section.reset_button.isEnabled()

    panel.text_x.setValue(55)
    panel.text_x.editingFinished.emit()
    qapp.processEvents()
    assert layer.offset_x == 55
    assert document.undo()
    qapp.processEvents()
    assert layer.offset_x == 30

    document.add_layer(name="Pixel", color=(0, 0, 0, 255), record=False)
    panel.refresh()
    assert panel.text_properties.isHidden()
    panel.close()
    panel.deleteLater()


def test_text_properties_panel_edits_character(qapp):
    from ui.properties_panel import PropertiesPanel

    document = Document(200, 160, name="Text character")
    layer = document.add_text_layer(
        TextProperties("Aa", font_size=20, color=(10, 20, 30, 255)), record=False
    )
    panel = PropertiesPanel()
    panel.bind_document(document)
    panel.show()
    qapp.processEvents()

    assert panel.text_size.value() == 20
    assert panel.text_style.currentData() == "regular"
    assert panel.text_leading.currentText() == "(Auto)"
    assert not panel.text_kerning.isEnabled()

    panel.text_size.setValue(28)
    panel.text_size.editingFinished.emit()
    qapp.processEvents()
    assert layer.text.font_size == 28

    style_index = panel.text_style.findData("bold_italic")
    assert style_index >= 0
    panel.text_style.setCurrentIndex(style_index)
    qapp.processEvents()
    assert layer.text.bold and layer.text.italic

    leading_index = panel.text_leading.findData(1.4)
    assert leading_index >= 0
    panel.text_leading.setCurrentIndex(leading_index)
    qapp.processEvents()
    assert layer.text.line_spacing == 1.4

    panel.text_tracking.setValue(5)
    panel.text_tracking.editingFinished.emit()
    qapp.processEvents()
    assert layer.text.letter_spacing == 5

    assert panel.set_text_color(QColor(200, 60, 40, 128))
    qapp.processEvents()
    assert layer.text.color == (200, 60, 40, 128)
    assert document.undo()
    qapp.processEvents()
    assert layer.text.color == (10, 20, 30, 255)
    panel.close()
    panel.deleteLater()


def test_shape_properties_panel_shows_live_shape(qapp):
    from ui.properties_panel import PropertiesPanel

    document = Document(240, 180, name="Shape transform")
    layer = document.add_shape_layer(
        ShapeProperties(
            width=80,
            height=50,
            fill_color=(10, 20, 30, 255),
        ),
        30,
        40,
        record=False,
    )
    panel = PropertiesPanel()
    panel.bind_document(document)
    panel.show()
    qapp.processEvents()

    assert not panel.shape_properties.isHidden()
    assert panel.text_properties.isHidden()
    assert panel.shape_kind_label.text() == "Hình chữ nhật"
    assert panel.shape_width.value() == 80
    assert panel.shape_height.value() == 50
    assert panel.shape_x.value() == 30
    assert panel.shape_y.value() == 40
    assert panel.shape_link_button.isEnabled()
    assert not panel.shape_link_button.isChecked()
    assert panel.shape_fill_check.isChecked()
    assert not panel.shape_stroke_button.isEnabled()
    assert not panel.shape_stroke_style.isEnabled()
    assert not panel.shape_corner_section.isHidden()
    assert all(not button.isEnabled() for button in panel.shape_path_buttons)

    panel.shape_width.setValue(100)
    panel.shape_width.editingFinished.emit()
    qapp.processEvents()
    assert (layer.shape.width, layer.shape.height) == (100, 50)

    panel.shape_link_button.setChecked(True)
    panel.shape_height.setValue(60)
    panel.shape_height.editingFinished.emit()
    qapp.processEvents()
    assert (layer.shape.width, layer.shape.height) == (120, 60)

    panel.shape_x.setValue(44)
    panel.shape_x.editingFinished.emit()
    qapp.processEvents()
    assert layer.offset_x == 44
    assert document.undo()
    qapp.processEvents()
    assert layer.offset_x == 30

    document.add_layer(name="Pixel", color=(0, 0, 0, 255), record=False)
    panel.refresh()
    assert panel.shape_properties.isHidden()
    panel.close()
    panel.deleteLater()


def test_shape_properties_panel_edits_fill_and_corners(qapp):
    from ui.properties_panel import PropertiesPanel

    document = Document(240, 180, name="Shape appearance")
    layer = document.add_shape_layer(
        ShapeProperties(
            width=120,
            height=80,
            fill_color=(10, 20, 30, 255),
        ),
        record=False,
    )
    panel = PropertiesPanel()
    panel.bind_document(document)
    panel.show()
    qapp.processEvents()

    panel.shape_fill_check.setChecked(False)
    qapp.processEvents()
    assert layer.shape.fill_color is None
    assert layer.shape.stroke_width == 1
    assert panel.shape_stroke_button.isEnabled()

    assert panel.set_shape_fill_color(QColor(200, 60, 40, 128))
    qapp.processEvents()
    assert layer.shape.fill_color == (200, 60, 40, 128)
    assert panel.shape_fill_check.isChecked()

    assert panel.set_shape_stroke_color(QColor(255, 255, 255, 200))
    qapp.processEvents()
    assert layer.shape.stroke_color == (255, 255, 255, 200)

    panel.shape_stroke_width.setValue(4)
    panel.shape_stroke_width.editingFinished.emit()
    qapp.processEvents()
    assert layer.shape.stroke_width == 4

    panel.shape_radius_link.setChecked(False)
    panel.shape_radius_spins[0].setValue(12)
    panel.shape_radius_spins[0].editingFinished.emit()
    qapp.processEvents()
    panel.shape_radius_spins[2].setValue(4)
    panel.shape_radius_spins[2].editingFinished.emit()
    qapp.processEvents()
    assert layer.shape.kind == "rounded_rectangle"
    assert layer.shape.corner_radii == (12.0, 0.0, 4.0, 0.0)
    assert document.undo()
    qapp.processEvents()
    assert layer.shape.corner_radii == (12.0, 0.0, 0.0, 0.0)

    panel.shape_radius_link.setChecked(True)
    panel.shape_radius_spins[1].setValue(6)
    panel.shape_radius_spins[1].editingFinished.emit()
    qapp.processEvents()
    assert layer.shape.corner_radii == (6.0, 6.0, 6.0, 6.0)

    ellipse = document.add_shape_layer(
        ShapeProperties(
            kind="ellipse",
            width=50,
            height=30,
            fill_color=(10, 20, 30, 255),
        ),
        record=False,
    )
    panel.refresh()
    assert panel.shape_kind_label.text() == "Hình ellipse"
    assert panel.shape_corner_section.isHidden()
    assert ellipse.shape.kind == "ellipse"
    panel.close()
    panel.deleteLater()


def test_text_layer_ui(qapp, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(160, 100, name="Text UI")
    document.add_layer(name="Background", color=(40, 40, 40, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    assert view is not None
    assert "text" in window.toolbox._actions
    view.set_tool("text")
    qapp.processEvents()
    assert view.tool_id == "text"
    assert window.toolbox._actions["text"].isChecked()
    assert window.action_new_text.isEnabled()
    assert not window.action_edit_text.isEnabled()
    assert not window.action_rasterize_text.isEnabled()

    def accept_as(text: str):
        def fake_exec(dialog):
            dialog.text_edit.setPlainText(text)
            dialog.size_spin.setValue(20)
            return QDialog.DialogCode.Accepted

        return fake_exec

    start = view.image_to_widget(QPointF(20.0, 14.0)).toPoint()
    QTest.mousePress(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    QTest.mouseRelease(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    qapp.processEvents()

    editor = view.inline_editor
    assert editor is not None
    assert editor.toPlainText() == ""
    editor.setPlainText("Nhấp chuột")
    qapp.processEvents()
    view.commit_inline_text()
    qapp.processEvents()
    assert view.inline_editor is None

    text_layer = document.active_layer
    assert text_layer is not None
    assert text_layer.kind == "text"
    assert text_layer.text is not None and text_layer.text.text == "Nhấp chuột"
    assert (text_layer.offset_x, text_layer.offset_y) == (20, 14)
    assert window.action_edit_text.isEnabled()
    assert window.action_rasterize_text.isEnabled()
    assert "Văn bản" in window.properties_panel._values["layer_info"].text()
    assert "Văn bản" in window.layers_panel.layer_list.item(0).data(ROLE_SUBTITLE)

    monkeypatch.setattr("ui.main_window.exec_object", accept_as("Đã sửa"))
    window.action_edit_text.trigger()
    qapp.processEvents()
    assert text_layer.text.text == "Đã sửa"
    window._on_undo()
    qapp.processEvents()
    assert text_layer.text.text == "Nhấp chuột"
    window._on_redo()
    qapp.processEvents()
    assert text_layer.text.text == "Đã sửa"

    window.action_rasterize_text.trigger()
    qapp.processEvents()
    assert text_layer.kind == "pixel"
    assert text_layer.text is None
    assert not window.action_edit_text.isEnabled()
    assert not window.action_rasterize_text.isEnabled()
    window._on_undo()
    qapp.processEvents()
    assert text_layer.kind == "text"
    assert text_layer.text.text == "Đã sửa"

    monkeypatch.setattr("ui.main_window.exec_object", accept_as("Từ panel"))
    window.layers_panel._text_button.click()
    qapp.processEvents()
    latest = document.active_layer
    assert latest is not text_layer
    assert latest.kind == "text"
    assert latest.text.text == "Từ panel"

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_inline_text_editor_on_canvas(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(220, 140, name="Inline Text")
    document.add_layer(name="Background", color=(38, 42, 50, 255), record=False)
    layer = document.add_text_layer(
        TextProperties(
            runs=(TextRun("Tiêu đề", font_size=24, color=(230, 180, 90, 255)),),
            alignment="center",
            line_spacing=1.2,
            letter_spacing=2,
            warp_style="wave",
            warp_bend=45,
        ),
        x=30,
        y=20,
    )
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    view.fit_to_window()
    view.set_tool("text")
    window.toolbox.set_current_tool("text")
    qapp.processEvents()

    def click_image(x: float, y: float) -> None:
        point = view.image_to_widget(QPointF(x, y)).toPoint()
        QTest.mousePress(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
        )
        QTest.mouseRelease(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
        )
        qapp.processEvents()

    # Nhấp vào layer chữ sẵn có: sửa tại chỗ, giữ căn lề/giãn/uốn và định dạng.
    click_image(layer.offset_x + 3, layer.offset_y + 3)
    editor = view.inline_editor
    assert editor is not None
    assert editor.toPlainText() == "Tiêu đề"
    assert view._inline_backdrop is not None
    editor.setPlainText("Đã sửa trên canvas")
    qapp.processEvents()
    assert editor.toPlainText() == "Đã sửa trên canvas"
    QTest.keyClick(
        editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )
    qapp.processEvents()

    assert view.inline_editor is None
    assert view._inline_backdrop is None
    text_layers = [item for item in document.layers if item.kind == "text"]
    assert len(text_layers) == 1
    assert layer.text is not None
    assert layer.text.text == "Đã sửa trên canvas"
    assert layer.text.warp_style == "wave" and layer.text.warp_bend == 45
    assert layer.text.alignment == "center"
    assert abs(layer.text.line_spacing - 1.2) < 1e-6
    assert layer.text.letter_spacing == 2
    assert layer.text.runs[0].font_size == 24
    assert layer.text.runs[0].color == (230, 180, 90, 255)

    window._on_undo()
    qapp.processEvents()
    assert layer.text.text == "Tiêu đề"
    window._on_redo()
    qapp.processEvents()
    assert layer.text.text == "Đã sửa trên canvas"

    # Esc huỷ nội dung mới, không tạo layer.
    count_before = len(document.layers)
    click_image(170, 112)
    editor = view.inline_editor
    assert editor is not None
    editor.setPlainText("sẽ huỷ")
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert view.inline_editor is None
    assert len(document.layers) == count_before

    # Nhấp ra ngoài: hoàn tất và tạo layer, không mở ô soạn mới.
    click_image(170, 112)
    editor = view.inline_editor
    assert editor is not None
    editor.setPlainText("Tạo trên canvas")
    qapp.processEvents()
    click_image(205, 130)
    assert view.inline_editor is None
    assert len([item for item in document.layers if item.kind == "text"]) == 2
    assert document.active_layer.text.text == "Tạo trên canvas"

    # Ô soạn bám theo zoom và vị trí ảnh.
    view.begin_inline_text(
        QPointF(20.0, 120.0), TextRun("", font_size=16, color=(255, 255, 255, 255))
    )
    editor = view.inline_editor
    assert editor is not None
    view.set_zoom(2.0)
    qapp.processEvents()
    assert abs(editor.zoom - 2.0) < 1e-9
    origin = view.image_to_widget(QPointF(20.0, 120.0))
    assert (editor.x(), editor.y()) == (round(origin.x()), round(origin.y()))
    view.cancel_inline_text()
    qapp.processEvents()

    # Layer chữ có mask: chặn sửa tại chỗ để tránh sai dữ liệu.
    layer.set_mask(
        np.full((layer.height, layer.width), 255, dtype=np.uint8)
    )
    assert (
        view.begin_inline_text(
            QPointF(layer.offset_x + 2, layer.offset_y + 2),
            TextRun("", font_size=20, color=(255, 255, 255, 255)),
        )
        is False
    )
    assert view.inline_editor is None
    document.mark_clean()
    window.close()


def test_shape_dialog_preview(qapp):
    dialog = ShapeDialog()
    assert "Layer dự kiến" in dialog.info_label.text()
    assert dialog.properties == ShapeProperties()
    assert not dialog.radius_spin.isEnabled()

    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData("ellipse"))
    dialog.width_spin.setValue(120)
    dialog.height_spin.setValue(80)
    dialog.stroke_spin.setValue(4)
    dialog._update_preview()
    properties = dialog.properties
    assert properties.kind == "ellipse"
    assert (properties.width, properties.height) == (120, 80)
    assert properties.stroke_width == 4
    pixmap = dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()

    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData("rounded_rectangle"))
    assert dialog.radius_spin.isEnabled()
    dialog.fill_check.setChecked(False)
    assert dialog.properties.fill_color is None

    editing = ShapeDialog(properties=dialog.properties, editing=True)
    assert editing.kind_combo.currentData() == "rounded_rectangle"
    assert not editing.fill_check.isChecked()
    editing.close()

    per_corner = ShapeProperties(
        kind="rounded_rectangle",
        width=80,
        height=60,
        corner_radii=(10.0, 0.0, 4.0, 0.0),
    )
    editing = ShapeDialog(properties=per_corner, editing=True)
    assert editing.properties == per_corner
    editing.radius_spin.setValue(3.0)
    assert editing.properties.corner_radii == (3.0, 3.0, 3.0, 3.0)
    editing.close()
    dialog.close()


def test_shape_tool_ui(qapp, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(160, 120, name="Shape UI")
    document.add_layer(name="Background", color=(240, 240, 240, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    assert "shape" in window.toolbox._actions
    view.set_tool("shape")
    qapp.processEvents()
    assert window.toolbox._actions["shape"].isChecked()
    assert window.options_bar._shape_kind is not None
    assert window.options_bar._shape_kind.currentData() == "rectangle"
    assert window.options_bar._shape_radius_spin is not None
    assert not window.options_bar._shape_radius_spin.isEnabled()

    def drag(x0: float, y0: float, x1: float, y1: float) -> None:
        start = view.image_to_widget(QPointF(x0, y0)).toPoint()
        end = view.image_to_widget(QPointF(x1, y1)).toPoint()
        QTest.mousePress(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
        )
        QTest.mouseRelease(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end
        )
        qapp.processEvents()

    drag(20, 20, 120, 90)
    rectangle = document.active_layer
    assert rectangle is not None
    assert rectangle.kind == "shape"
    assert rectangle.shape.kind == "rectangle"
    assert abs(rectangle.offset_x - 20) <= 2
    assert abs(rectangle.offset_y - 20) <= 2
    assert abs(rectangle.width - 100) <= 2
    assert abs(rectangle.height - 70) <= 2
    assert window.action_edit_shape.isEnabled()
    assert window.action_rasterize_shape.isEnabled()
    assert "Hình chữ nhật" in window.properties_panel._values["layer_info"].text()
    assert "Hình chữ nhật" in window.layers_panel.layer_list.item(0).data(ROLE_SUBTITLE)

    window.options_bar._shape_kind.setCurrentIndex(
        window.options_bar._shape_kind.findData("ellipse")
    )
    qapp.processEvents()
    assert view.shape_options()["kind"] == "ellipse"
    assert window.options_bar._shape_radius_spin.isEnabled() is False

    drag(40, 40, 100, 100)
    ellipse = document.active_layer
    assert ellipse is not rectangle
    assert ellipse.kind == "shape"
    assert ellipse.shape.kind == "ellipse"

    def accept_edit(dialog):
        dialog.kind_combo.setCurrentIndex(
            dialog.kind_combo.findData("rounded_rectangle")
        )
        dialog.width_spin.setValue(60)
        dialog.height_spin.setValue(40)
        dialog.radius_spin.setValue(8.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("ui.main_window.exec_object", accept_edit)
    window.action_edit_shape.trigger()
    qapp.processEvents()
    assert ellipse.shape.kind == "rounded_rectangle"
    assert (ellipse.width, ellipse.height) == (60, 40)
    assert ellipse.shape.corner_radius == 8.0

    window._on_undo()
    qapp.processEvents()
    assert ellipse.shape.kind == "ellipse"

    window.action_rasterize_shape.trigger()
    qapp.processEvents()
    assert ellipse.kind == "pixel"
    assert ellipse.shape is None
    window._on_undo()
    qapp.processEvents()
    assert ellipse.kind == "shape"

    layer_count = len(document.layers)
    start = view.image_to_widget(QPointF(10.0, 10.0)).toPoint()
    QTest.mousePress(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    escape = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(escape)
    QTest.mouseRelease(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    qapp.processEvents()
    assert len(document.layers) == layer_count
    assert view.shape_preview is None

    monkeypatch.setattr(
        "ui.main_window.exec_object", lambda dialog: QDialog.DialogCode.Accepted
    )
    window.layers_panel._shape_button.click()
    qapp.processEvents()
    assert document.active_layer is not ellipse
    assert document.active_layer.kind == "shape"

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_brush_eraser_and_mask_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(160, 120, name="Brush UI")
    layer = document.add_layer(
        name="Background", color=(255, 255, 255, 255), record=False
    )
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    assert "brush" in window.toolbox._actions
    assert "eraser" in window.toolbox._actions
    window.color_manager.set_foreground(QColor(20, 120, 220, 255))
    view.set_tool("brush")
    window.toolbox.set_current_tool("brush")
    qapp.processEvents()
    assert window.toolbox._actions["brush"].isChecked()
    assert window.options_bar._brush_size is not None
    assert window.options_bar._brush_hardness is not None
    assert window.options_bar._brush_opacity is not None
    assert window.options_bar._brush_target is not None
    assert not window.options_bar._brush_target.isEnabled()

    window.options_bar._brush_size.setValue(18)
    window.options_bar._brush_hardness.setValue(100)
    qapp.processEvents()
    assert view.brush_options()["size"] == 18
    assert abs(view.brush_options()["hardness"] - 1.0) < 1e-6
    assert view.brush_options()["color"] == (20, 120, 220, 255)

    def drag(x0: float, y0: float, x1: float, y1: float) -> None:
        start = view.image_to_widget(QPointF(x0, y0)).toPoint()
        end = view.image_to_widget(QPointF(x1, y1)).toPoint()
        QTest.mousePress(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
        )
        QTest.mouseRelease(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end
        )
        qapp.processEvents()

    drag(20, 20, 140, 100)
    assert tuple(layer.pixels[60, 80]) == (20, 120, 220, 255)
    assert document.history.can_undo

    key_b = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(key_b)
    assert view.tool_id == "brush"

    key_shift_e = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.ShiftModifier
    )
    view.keyPressEvent(key_shift_e)
    qapp.processEvents()
    assert view.tool_id == "eraser"
    assert window.toolbox._actions["eraser"].isChecked()
    assert window.options_bar._brush_size is not None
    assert window.options_bar._brush_target is None

    drag(80, 60, 80, 60)
    assert layer.pixels[60, 80, 3] == 0
    window._on_undo()
    qapp.processEvents()
    assert layer.pixels[60, 80, 3] == 255

    document.add_layer_mask(record=False)
    layer.mask[...] = 0
    window._update_action_states()
    qapp.processEvents()
    assert window.action_paint_mask.isEnabled()
    window.action_paint_mask.trigger()
    qapp.processEvents()
    assert view.tool_id == "brush"
    assert window.action_paint_mask.isChecked()
    assert view.brush_options()["paint_mask"] is True
    assert window.options_bar._brush_target.isEnabled()
    assert window.options_bar._brush_target.currentData() == "mask"

    window.color_manager.set_foreground(QColor(255, 255, 255, 255))
    qapp.processEvents()
    drag(80, 60, 80, 60)
    assert layer.mask[60, 80] == 255
    window._on_undo()
    qapp.processEvents()
    assert layer.mask[60, 80] == 0

    before = layer.pixels.copy()
    start = view.image_to_widget(QPointF(40, 40)).toPoint()
    QTest.mousePress(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    escape = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(escape)
    QTest.mouseRelease(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    qapp.processEvents()
    assert (layer.pixels == before).all()

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_gradient_tool_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(160, 100, name="Gradient UI")
    layer = document.add_layer(
        name="Background", color=(255, 255, 255, 255), record=False
    )
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    assert "gradient" in window.toolbox._actions
    view.set_tool("gradient")
    window.toolbox.set_current_tool("gradient")
    qapp.processEvents()
    assert window.toolbox._actions["gradient"].isChecked()
    assert window.options_bar._gradient_type is not None
    assert window.options_bar._gradient_preset is not None
    assert window.options_bar._gradient_target is not None
    assert not window.options_bar._gradient_target.isEnabled()

    def drag(x0: float, y0: float, x1: float, y1: float) -> None:
        start = view.image_to_widget(QPointF(x0, y0)).toPoint()
        end = view.image_to_widget(QPointF(x1, y1)).toPoint()
        QTest.mousePress(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
        )
        QTest.mouseRelease(
            view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end
        )
        qapp.processEvents()

    window.color_manager.set_foreground(QColor(240, 120, 40, 255))
    qapp.processEvents()
    window.options_bar._gradient_preset.setCurrentIndex(
        window.options_bar._gradient_preset.findData("fg_transparent")
    )
    qapp.processEvents()
    assert view.gradient_options()["preset"] == "fg_transparent"
    assert view.gradient_options()["colors"][1] == (240, 120, 40, 0)

    drag(10, 50, 150, 50)
    assert tuple(layer.pixels[50, 20, :3]) == (240, 120, 40)
    assert layer.pixels[50, 20, 3] > 200
    assert layer.pixels[50, 140, 3] < 60
    assert document.history.can_undo

    window._on_undo()
    qapp.processEvents()
    assert tuple(layer.pixels[50, 20]) == (255, 255, 255, 255)

    window.options_bar._gradient_type.setCurrentIndex(1)
    qapp.processEvents()
    assert view.gradient_options()["gradient_type"] == "radial"
    window.options_bar._gradient_type.setCurrentIndex(0)
    window.options_bar._gradient_preset.setCurrentIndex(
        window.options_bar._gradient_preset.findData("black_white")
    )
    qapp.processEvents()

    document.add_layer_mask(record=False)
    layer.mask[...] = 0
    window._update_action_states()
    qapp.processEvents()
    assert window.action_paint_mask.isEnabled()
    window.action_paint_mask.trigger()
    qapp.processEvents()
    assert view.tool_id == "gradient"
    assert view.gradient_options()["paint_mask"] is True
    assert view.brush_options()["paint_mask"] is True
    assert window.options_bar._gradient_target.isEnabled()
    assert window.options_bar._gradient_target.currentData() == "mask"

    drag(10, 50, 150, 50)
    assert layer.mask[50, 20] < 30
    assert layer.mask[50, 140] > 225
    window._on_undo()
    qapp.processEvents()
    assert layer.mask[50, 20] == 0
    assert layer.mask[50, 140] == 0

    key_g = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_G, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(key_g)
    assert view.tool_id == "gradient"

    before = layer.pixels.copy()
    start = view.image_to_widget(QPointF(40, 40)).toPoint()
    QTest.mousePress(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    escape = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(escape)
    QTest.mouseRelease(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    qapp.processEvents()
    assert (layer.pixels == before).all()

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_selection_feather_antialias_ui(qapp, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(160, 100, name="Feather UI")
    document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    view.set_tool("rect_select")
    window.toolbox.set_current_tool("rect_select")
    qapp.processEvents()
    assert window.options_bar._selection_feather is not None
    assert window.options_bar._selection_antialias is not None

    window.options_bar._selection_feather.setValue(8)
    window.options_bar._selection_antialias.setChecked(False)
    qapp.processEvents()
    assert view.selection_options()["feather"] == 8
    assert view.selection_options()["antialias"] is False

    start = view.image_to_widget(QPointF(20.0, 20.0)).toPoint()
    end = view.image_to_widget(QPointF(120.0, 80.0)).toPoint()
    QTest.mousePress(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start
    )
    QTest.mouseRelease(
        view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end
    )
    qapp.processEvents()

    assert document.has_selection()
    assert document.selection.feather == 8
    assert not document.selection.antialias
    assert 0 < int(document.selection_mask()[50, 19]) < 255
    assert window.action_feather_selection.isEnabled()
    assert "Feather 8 px" in window.options_bar._selection_info.text()

    dialog = FeatherDialog(8, parent=window)
    dialog.radius_spin.setValue(20)
    assert dialog.radius == 20
    assert "20 px" in dialog.info_label.text()
    dialog.close()

    def fake_exec(dialog):
        dialog.radius_spin.setValue(20)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("ui.main_window.exec_object", fake_exec)
    window.action_feather_selection.trigger()
    qapp.processEvents()
    assert document.selection.feather == 20
    assert "Feather 20 px" in window.options_bar._selection_info.text()
    assert "20 px" in window.statusBar().currentMessage()

    window._on_undo()
    qapp.processEvents()
    assert document.selection.feather == 8

    view.set_tool("ellipse_select")
    qapp.processEvents()
    assert window.options_bar._selection_feather.value() == 0
    assert window.options_bar._selection_antialias.isChecked()

    window.options_bar._selection_feather.setValue(4)
    qapp.processEvents()
    assert view.selection_options()["feather"] == 4
    assert view.selection_options()["antialias"] is True

    view.set_tool("rect_select")
    qapp.processEvents()
    assert window.options_bar._selection_feather.value() == 8
    assert not window.options_bar._selection_antialias.isChecked()

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_advanced_selection_tools_and_quick_mask(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(120, 80, name="Advanced Selection")
    layer = document.add_layer(
        name="Background", color=(255, 255, 255, 255), record=False
    )
    pixels = layer.pixels.copy()
    pixels[:, :60] = (210, 40, 40, 255)
    pixels[:, 60:] = (40, 40, 210, 255)
    layer.set_pixels(pixels)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    view.fit_to_window()
    qapp.processEvents()

    for tool_id in ("lasso", "magic_wand", "quick_select"):
        assert tool_id in window.toolbox._actions

    def press_at(x, y, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mousePress(
            view,
            Qt.MouseButton.LeftButton,
            modifier,
            view.image_to_widget(QPointF(x, y)).toPoint(),
        )

    def move_to(x, y):
        position = view.image_to_widget(QPointF(x, y))
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            position,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseMoveEvent(event)

    def release_at(x, y, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mouseRelease(
            view,
            Qt.MouseButton.LeftButton,
            modifier,
            view.image_to_widget(QPointF(x, y)).toPoint(),
        )

    # Phím tắt công cụ mới.
    view.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_L, Qt.KeyboardModifier.NoModifier)
    )
    assert view.tool_id == "lasso"
    view.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_W, Qt.KeyboardModifier.NoModifier)
    )
    assert view.tool_id == "magic_wand"
    view.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_W, Qt.KeyboardModifier.ShiftModifier)
    )
    assert view.tool_id == "quick_select"

    # Lasso: kéo đường tự do, kết quả là một vùng chọn kín.
    view.set_tool("lasso")
    press_at(10, 10)
    for point in ((50, 12), (46, 60), (12, 54)):
        move_to(*point)
    release_at(12, 54)
    qapp.processEvents()
    assert document.has_selection()
    bounds = document.selection.bounds()
    assert bounds.width() >= 35
    assert bounds.height() >= 44
    assert document.history.can_undo

    # Esc huỷ nét lasso đang vẽ và giữ nguyên vùng chọn cũ.
    old_bounds = document.selection.bounds()
    press_at(70, 20)
    move_to(100, 30)
    view.keyPressEvent(
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
    )
    release_at(100, 30)
    qapp.processEvents()
    assert document.selection.bounds() == old_bounds

    # Magic Wand: chọn nửa đỏ, Shift+click cộng, Alt+click trừ.
    document.deselect()
    view.set_tool("magic_wand")
    qapp.processEvents()
    assert window.options_bar._wand_tolerance is not None
    window.options_bar._wand_tolerance.setValue(0)
    window.options_bar._wand_contiguous.setChecked(True)
    press_at(20, 40)
    release_at(20, 40)
    qapp.processEvents()
    assert document.has_selection()
    assert document.selection.bounds().width() == 60
    assert document.selection.bounds().height() == 80

    press_at(90, 40, Qt.KeyboardModifier.ShiftModifier)
    release_at(90, 40, Qt.KeyboardModifier.ShiftModifier)
    qapp.processEvents()
    assert document.selection.bounds().width() == 120

    press_at(20, 40, Qt.KeyboardModifier.AltModifier)
    release_at(20, 40, Qt.KeyboardModifier.AltModifier)
    qapp.processEvents()
    assert document.selection.bounds().x() == 60
    assert document.selection.bounds().width() == 60

    window.options_bar._wand_tolerance.setValue(10)
    window.options_bar._wand_contiguous.setChecked(False)
    window.options_bar._selection_feather.setValue(3)
    qapp.processEvents()
    wand_options = view.magic_wand_options()
    assert wand_options["tolerance"] == 10
    assert wand_options["contiguous"] is False
    assert wand_options["feather"] == 3

    # Quick Selection: lớp phủ tạm xuất hiện khi kéo và biến mất khi thả.
    document.deselect()
    view.set_tool("quick_select")
    qapp.processEvents()
    window.options_bar._quick_size.setValue(24)
    window.options_bar._quick_tolerance.setValue(0)
    qapp.processEvents()
    assert view.quick_select_options()["size"] == 24

    press_at(90, 30)
    move_to(90, 55)
    qapp.processEvents()
    assert view._selection_preview_image is not None
    assert "Quick Selection" in window.statusBar().currentMessage()
    release_at(90, 55)
    qapp.processEvents()
    assert view._selection_preview_image is None
    assert document.has_selection()
    assert document.selection.bounds().x() >= 60
    assert document.history.can_undo

    window._on_undo()
    qapp.processEvents()
    assert not document.has_selection()

    # Quick Mask: phím Q bật/tắt, menu View đồng bộ, tự tắt khi bỏ vùng chọn.
    document.select_all()
    qapp.processEvents()
    if view.tool_id != "quick_select":
        view.set_tool("quick_select")
    view.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier)
    )
    qapp.processEvents()
    assert view.quick_mask
    assert window.action_quick_mask.isChecked()
    assert view._quick_mask_image is not None
    assert not view._ants_timer.isActive()

    window.action_quick_mask.trigger()
    qapp.processEvents()
    assert not view.quick_mask
    assert not window.action_quick_mask.isChecked()

    view.set_quick_mask(True)
    qapp.processEvents()
    assert window.action_quick_mask.isChecked()

    document.deselect()
    qapp.processEvents()
    assert not view.quick_mask
    assert not window.action_quick_mask.isChecked()

    window.action_quick_mask.trigger()
    qapp.processEvents()
    assert not window.action_quick_mask.isChecked()

    window._remove_view(view)
    document.mark_clean()
    window.close()


def test_adjustment_layer_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(64, 48, name="Adjustment UI")
    document.add_layer(name="Background", color=(40, 80, 160, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    layer = document.add_adjustment_layer(AdjustmentProperties(kind="invert"))
    qapp.processEvents()

    panel = window.layers_panel
    assert panel.layer_list.count() == 2
    item = panel.layer_list.item(0)
    assert item.data(ROLE_KIND) == LayerKind.ADJUSTMENT
    assert "Điều chỉnh" in item.data(ROLE_SUBTITLE)
    assert "Đảo màu" in item.toolTip()
    assert not panel.blend_combo.isEnabled()
    assert panel.blend_combo.toolTip().startswith("Layer điều chỉnh")

    assert window.action_new_adjustment_invert.isEnabled()
    assert window.action_edit_adjustment.isEnabled()
    assert not window.action_filter_invert.isEnabled()
    assert window.action_add_mask.isEnabled()
    assert not window.action_layer_rotate_cw.isEnabled()
    assert "Layer điều chỉnh" in window.properties_panel._values["layer_info"].text()

    window.action_add_mask.trigger()
    qapp.processEvents()
    assert layer.mask is not None
    assert layer.mask.shape == (document.height, document.width)
    assert not window.action_add_mask.isEnabled()
    assert not window.action_apply_mask.isEnabled()
    assert window.action_remove_mask.isEnabled()
    assert panel.layer_list.item(0).data(ROLE_SUBTITLE).endswith("Mask")
    assert "Mask: bật" in window.properties_panel._values["layer_info"].text()

    dialog = AdjustmentLayerDialog(
        layer.adjustment,
        window,
        preview=window._adjustment_preview_source(layer),
        mask=layer.mask,
        editing=True,
    )
    assert dialog.properties == layer.adjustment
    pixmap = dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    dialog.close()

    controls = AdjustmentLayerDialog(
        AdjustmentProperties(kind="brightness_contrast"), window
    )
    controls.brightness_field.setValue(25)
    controls.contrast_field.setValue(-10)
    assert controls.properties.brightness == 25
    assert controls.properties.contrast == -10
    controls.close()

    standalone = LayersPanel()
    standalone.bind_document(document)
    edit_requests: list[str] = []
    rename_requests: list[str] = []
    standalone.adjustment_edit_requested.connect(edit_requests.append)
    standalone.layer_list.rename_requested.connect(rename_requests.append)
    standalone.layer_list._on_item_double_clicked(standalone.layer_list.item(0))
    assert edit_requests == [layer.id]
    assert rename_requests == []
    standalone.deleteLater()

    window._remove_view(window.current_view)
    document.mark_clean()
    window.close()


def test_advanced_adjustment_dialogs_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(64, 48, name="Advanced Adjustment UI")
    document.add_layer(name="Background", color=(40, 80, 160, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    levels = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="levels", levels_black=12, levels_gamma=1.5, levels_out_white=250
        )
    )
    curves = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="curves", curve_points=((0, 0), (128, 96), (255, 255))
        )
    )
    balance = document.add_adjustment_layer(
        AdjustmentProperties(
            kind="color_balance",
            color_midtones=(30, -10, 0),
            preserve_luminosity=False,
        )
    )
    qapp.processEvents()

    for action in (
        window.action_new_adjustment_levels,
        window.action_new_adjustment_curves,
        window.action_new_adjustment_color_balance,
    ):
        assert action.isEnabled()

    panel = window.layers_panel
    tooltips = [
        panel.layer_list.item(row).toolTip()
        for row in range(panel.layer_list.count())
    ]
    assert any("Levels" in text for text in tooltips)
    assert any("Curves" in text for text in tooltips)
    assert "Color Balance" in window.properties_panel._values["layer_info"].text()
    assert "Trung +30/-10/+0" in window.properties_panel._values["layer_info"].text()

    levels_dialog = AdjustmentLayerDialog(
        levels.adjustment,
        window,
        preview=window._adjustment_preview_source(levels),
        editing=True,
    )
    assert levels_dialog.properties == levels.adjustment
    levels_dialog.levels_black_field.setValue(20)
    levels_dialog.levels_gamma_field.setValue(1.8)
    assert levels_dialog.properties.levels_black == 20
    assert levels_dialog.properties.levels_gamma == pytest.approx(1.8)
    pixmap = levels_dialog.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert "Gamma 1.80" in levels_dialog.info_label.text()
    levels_dialog.close()

    curves_dialog = AdjustmentLayerDialog(curves.adjustment, window)
    assert curves_dialog.curve_editor.points() == curves.adjustment.curve_points
    curves_dialog.curve_editor.set_points(((0, 0), (100, 40), (255, 255)))
    assert curves_dialog.properties.curve_points == ((0, 0), (100, 40), (255, 255))
    assert curves_dialog.preview_label.pixmap() is not None
    curves_dialog.curve_editor.reset()
    assert curves_dialog.properties.curve_points == ((0, 0), (255, 255))
    curves_dialog.close()

    balance_dialog = AdjustmentLayerDialog(balance.adjustment, window)
    balance_dialog.balance_fields["highlights"][2].setValue(25)
    balance_dialog.preserve_luma_check.setChecked(True)
    properties = balance_dialog.properties
    assert properties.color_highlights == (0, 0, 25)
    assert properties.preserve_luminosity is True
    assert balance_dialog.preview_label.pixmap() is not None
    balance_dialog.close()

    window._remove_view(window.current_view)
    document.mark_clean()
    window.close()


def test_edit_clipboard_lock_and_fill_actions(qapp, tmp_path):
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QApplication

    from core.selection import Selection

    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    document = Document(40, 30, name="Clipboard")
    layer = document.add_layer(name="Background", color=(10, 20, 30, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    assert window.action_copy.isEnabled()
    assert window.action_paste.isEnabled()
    assert window.action_clear.isEnabled()
    assert not window.action_quick_mask.isEnabled()

    document.set_selection(
        Selection.from_rect(40, 30, QRectF(5, 5, 10, 8)), "Chọn vùng"
    )
    qapp.processEvents()
    assert window.action_quick_mask.isEnabled()

    window._on_copy()
    clipboard_image = QApplication.clipboard().image()
    assert (clipboard_image.width(), clipboard_image.height()) == (10, 8)

    window._on_paste()
    qapp.processEvents()
    assert len(document.layers) == 2
    pasted = document.active_layer
    assert (pasted.width, pasted.height) == (10, 8)
    assert (pasted.offset_x, pasted.offset_y) == (5, 5)
    assert tuple(pasted.pixels[0, 0]) == (10, 20, 30, 255)

    document.set_active_layer(layer.id)
    window._on_cut()
    qapp.processEvents()
    assert layer.pixels[6, 6, 3] == 0
    assert layer.pixels[0, 0, 3] == 255

    window._on_fill_foreground()
    qapp.processEvents()
    assert layer.pixels[6, 6, 3] == 255

    window.action_lock_layer.trigger()
    qapp.processEvents()
    assert layer.locked
    assert window.action_lock_layer.isChecked()
    assert not window.action_clear.isEnabled()
    assert not window.action_cut.isEnabled()
    assert window.layers_panel._lock_button.isChecked()
    window.action_lock_layer.trigger()
    qapp.processEvents()
    assert not layer.locked
    assert window.action_clear.isEnabled()

    window.tabs.removeTab(0)
    window.close()


def test_eyedropper_tool_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(80, 60, name="Eyedropper UI")
    layer = document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    layer.pixels[:, 40:] = (10, 200, 30, 255)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    view = window.current_view
    assert "eyedropper" in window.toolbox._actions
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_I, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)
    assert view.tool_id == "eyedropper"
    assert window.toolbox._actions["eyedropper"].isChecked()

    def click(x: float, y: float, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        pos = view.image_to_widget(QPointF(x, y)).toPoint()
        QTest.mousePress(view, Qt.MouseButton.LeftButton, modifiers, pos)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, modifiers, pos)
        qapp.processEvents()

    click(60.5, 30.5)
    assert window.color_manager.foreground_rgba() == (10, 200, 30, 255)
    click(10.5, 30.5, Qt.KeyboardModifier.AltModifier)
    assert window.color_manager.background_rgba() == (255, 255, 255, 255)
    assert window.color_manager.foreground_rgba() == (10, 200, 30, 255)

    window.tabs.removeTab(0)
    window.close()


def test_color_and_brush_size_shortcuts(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(64, 48, name="Shortcuts")
    document.add_layer(name="Background", color=(255, 255, 255, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()
    view = window.current_view

    def press(key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
        qapp.processEvents()

    window.color_manager.set_foreground(QColor(10, 20, 30, 255))
    window.color_manager.set_background(QColor(200, 210, 220, 255))
    press(Qt.Key.Key_X)
    assert window.color_manager.foreground_rgba() == (200, 210, 220, 255)
    assert window.color_manager.background_rgba() == (10, 20, 30, 255)
    press(Qt.Key.Key_D)
    assert window.color_manager.foreground_rgba() == (255, 255, 255, 255)
    assert window.color_manager.background_rgba() == (0, 0, 0, 255)

    press(Qt.Key.Key_B)
    assert view.tool_id == "brush"
    view.set_brush_options(size=40)
    window.options_bar.refresh_paint_colors()
    press(Qt.Key.Key_BracketRight)
    assert view.brush_options()["size"] == 50
    assert window.options_bar._brush_size.value() == 50
    press(Qt.Key.Key_BracketLeft)
    press(Qt.Key.Key_BracketLeft)
    assert view.brush_options()["size"] == 30
    view.set_brush_options(size=5)
    press(Qt.Key.Key_BracketLeft)
    assert view.brush_options()["size"] == 4
    view.set_brush_options(size=1)
    press(Qt.Key.Key_BracketLeft)
    assert view.brush_options()["size"] == 1

    press(Qt.Key.Key_V)
    press(Qt.Key.Key_BracketRight)
    assert view.brush_options()["size"] == 1

    assert window.action_delete_layer.shortcut().toString() == "Ctrl+Shift+Del"

    window.tabs.removeTab(0)
    window.close()


def test_layer_context_menu_actions(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(40, 30, name="Context")
    layer = document.add_layer(name="Pixel", color=(20, 40, 60, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    menu = window.build_layer_context_menu(layer)
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]
    for label in (
        "Blending Options…",
        "Edit Adjustment…",
        "Copy CSS",
        "Copy SVG",
        "Duplicate Layer",
        "Delete Layer",
        "Group Layers",
        "Quick Export as PNG",
        "Export As…",
        "Convert to Smart Object",
        "Rasterize Layer",
        "Merge Visible",
        "Flatten Image",
        "Red",
        "No Color",
    ):
        assert label in labels
    assert not any(action.text() == "Merge Visible" and action.isEnabled() for action in menu.actions())
    assert any(action.text() == "Red" and action.isEnabled() for action in menu.actions())

    window.action_copy_css.trigger()
    qapp.processEvents()
    clipboard = QApplication.clipboard().text()
    assert clipboard.startswith(".layer-")
    assert "width: 40px;" in clipboard

    red = next(action for action in menu.actions() if action.text() == "Red")
    red.trigger()
    qapp.processEvents()
    assert layer.color_label == "red"
    item = window.layers_panel.layer_list.item(0)
    assert item.data(ROLE_COLOR_LABEL) == "red"

    document.file_path = str(tmp_path / "context.mps")
    window.action_quick_export_png.trigger()
    assert (tmp_path / "Pixel-export.png").exists()

    window.action_convert_smart.trigger()
    qapp.processEvents()
    assert layer.kind == LayerKind.SMART
    window.action_rasterize_layer.trigger()
    qapp.processEvents()
    assert layer.kind == LayerKind.PIXEL

    window.tabs.removeTab(0)
    window.close()


def test_clipping_mask_ui(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.resize(1280, 820)
    window.show()
    qapp.processEvents()

    document = Document(40, 30, name="Clipping UI")
    base = document.add_layer(name="Base", color=(255, 0, 0, 255), record=False)
    upper = document.add_layer(name="Upper", color=(0, 0, 255, 255), record=False)
    document.mark_clean()
    window._add_document_tab(document)
    qapp.processEvents()

    assert window.action_clipping_mask.isEnabled()
    assert window.action_clipping_mask.text() == "Create Clipping Mask"
    window.action_clipping_mask.trigger()
    qapp.processEvents()
    assert upper.clipping
    item = window.layers_panel.layer_list.item(0)
    assert bool(item.data(ROLE_CLIPPING))
    assert "Clipping" in item.data(ROLE_SUBTITLE)
    assert window.action_clipping_mask.text() == "Release Clipping Mask"

    document.set_active_layer(base)
    qapp.processEvents()
    assert not window.action_clipping_mask.isEnabled()

    document.set_active_layer(upper)
    qapp.processEvents()
    window.action_clipping_mask.trigger()
    qapp.processEvents()
    assert not upper.clipping
    assert window.action_clipping_mask.text() == "Create Clipping Mask"

    window.tabs.removeTab(0)
    window.close()
