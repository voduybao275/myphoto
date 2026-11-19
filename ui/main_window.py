"""Cửa sổ chính của My Photo Studio."""

from __future__ import annotations

import logging
from pathlib import Path

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtCore import QByteArray, QPointF, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
    QDialog,
)

from config.settings import (
    APP_NAME,
    APP_VERSION,
    EXPORT_FILTER,
    IMAGE_OPEN_FILTER,
    OPEN_FILTER,
    PROJECT_FILTER,
    THEME_DARK,
    THEME_LIGHT,
    SettingsStore,
)
from compat.qt import exec_object
from core import filters
from core.adjustment_layer import AdjustmentProperties
from core.canvas import composite_layers, downsample_rgba
from core.color_manager import ColorManager
from core.document import Document
from core.fill_layer import FillProperties
from core.layer import LayerKind
from core.presets import PresetStore
from core.shape_layer import ShapeProperties
from core.smart_object import SmartObjectProperties
from core.text_layer import TextProperties, TextRun
from formats.export_manager import ExportError, export_image
from formats.import_manager import (
    ImageImportError,
    load_image_document,
    load_image_rgba,
)
from formats.native_project import ProjectFormatError, ensure_project_extension, load_project, save_project
from ui import icons, theme
from ui.canvas_view import CanvasView
from ui.dialogs import (
    AdjustmentLayerDialog,
    BatchDialog,
    BrightnessContrastDialog,
    CanvasSizeDialog,
    FeatherDialog,
    FillDialog,
    GaussianBlurDialog,
    HueSaturationDialog,
    ImageSizeDialog,
    NewDocumentDialog,
    RotateDialog,
    ShapeDialog,
    SmartObjectDialog,
    TextDialog,
    UnsharpMaskDialog,
)
from ui.document_tabs import DocumentTabs
from ui.layers_panel import LayersPanel
from ui.menu_bar import build_menu_bar
from ui.options_bar import OptionsBar
from ui.properties_panel import PropertiesPanel
from ui.status_bar import AppStatusBar
from ui.toolbar import ToolBox
from ui.welcome import WelcomePage

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore) -> None:
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings_store.data
        self.preset_store = PresetStore(
            Path(settings_store.path).with_name("presets.sqlite3")
        )
        self.color_manager = ColorManager(self)
        self._untitled_counter = 1
        self._document_connections: list[tuple[object, object]] = []
        self._current_view: CanvasView | None = None

        self._setup_ui()
        self._create_actions()
        self._create_menu()
        self._restore_window_state()
        self._refresh_recent_ui()
        self._on_tab_changed(self.tabs.currentIndex())
        self._update_window_title()
        self._update_action_states()

    # ------------------------------------------------------------------- setup
    def _setup_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1420, 900)
        self.setMinimumSize(1080, 680)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("CentralStack")
        self.welcome = WelcomePage(self)
        self.tabs = DocumentTabs(self)
        self._stack.addWidget(self.welcome)
        self._stack.addWidget(self.tabs)
        self.setCentralWidget(self._stack)

        self.welcome.new_requested.connect(self._on_new_document)
        self.welcome.open_requested.connect(self._on_open_documents)
        self.welcome.recent_requested.connect(lambda path: self.open_paths([path]))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabCloseRequested.connect(self._request_close_tab)

        self.toolbox = ToolBox(self.color_manager, self)
        self.toolbox.setWindowTitle("Tool Box")
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.toolbox)
        self.toolbox.tool_selected.connect(self._on_tool_selected)

        self.options_bar = OptionsBar(self)
        self.options_bar.setWindowTitle("Options")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.options_bar)

        self.layers_panel = LayersPanel(self)
        self.dock_layers = QDockWidget("Layers", self)
        self.dock_layers.setObjectName("LayersDock")
        self.dock_layers.setWidget(self.layers_panel)
        self.dock_layers.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.dock_layers.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_layers)

        self.properties_panel = PropertiesPanel(self)
        self.dock_properties = QDockWidget("Properties", self)
        self.dock_properties.setObjectName("PropertiesDock")
        self.dock_properties.setWidget(self.properties_panel)
        self.dock_properties.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.dock_properties.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_properties)
        self.splitDockWidget(self.dock_layers, self.dock_properties, Qt.Orientation.Vertical)
        self.dock_layers.setMinimumWidth(292)
        self.dock_properties.setMinimumWidth(292)
        self.resizeDocks(
            [self.dock_layers, self.dock_properties], [560, 250], Qt.Orientation.Vertical
        )

        self.app_status = AppStatusBar(self)
        self.setStatusBar(self.app_status)
        self.app_status.zoom_requested.connect(self._on_status_zoom_requested)
        self.layers_panel.message.connect(self._show_transient_message)
        self.layers_panel.text_requested.connect(self._on_new_text_layer)
        self.layers_panel.shape_requested.connect(self._on_new_shape_layer)
        self.layers_panel.adjustment_edit_requested.connect(self._on_edit_adjustment)
        self.layers_panel.fill_edit_requested.connect(self._on_edit_fill)
        self.layers_panel.smart_edit_requested.connect(self._on_edit_smart_object)
        self.options_bar.text_layer_requested.connect(self._on_new_text_layer)
        self.options_bar.shape_layer_requested.connect(self._on_new_shape_layer)
        self.options_bar.brush_state_changed.connect(self._update_action_states)
        self.options_bar.gradient_state_changed.connect(self._update_action_states)
        self.color_manager.colors_changed.connect(self._on_colors_changed)

    def _create_actions(self) -> None:
        self.action_new = self._action("New…", "Ctrl+N", self._on_new_document)
        self.action_open = self._action("Open…", "Ctrl+O", self._on_open_documents)
        self.action_save = self._action("Save", "Ctrl+S", self._on_save)
        self.action_save_as = self._action("Save As…", "Ctrl+Shift+S", self._on_save_as)
        self.action_export = self._action("Export As…", "Ctrl+Alt+S", self._on_export)
        self.action_batch_processing = self._action(
            "Batch Processing…", "Ctrl+Shift+B", self._on_batch_processing
        )
        self.action_close = self._action("Close", "Ctrl+W", self._on_close_document)
        self.action_exit = self._action("Exit", "Ctrl+Q", self.close)

        self.action_undo = self._action("Undo", "Ctrl+Z", self._on_undo)
        self.action_redo = self._action("Redo", "Ctrl+Shift+Z", self._on_redo)
        self.action_redo.setShortcuts(
            [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")]
        )

        self.action_new_layer = self._action(
            "New Layer", "Ctrl+Shift+N", self._on_new_layer
        )
        self.action_new_group = self._action("New Group", "", self._on_new_group)
        self.action_group_layers = self._action(
            "Group Layers", "Ctrl+G", self._on_group_layers
        )
        self.action_ungroup_layers = self._action(
            "Ungroup Layers", "Ctrl+Shift+G", self._on_ungroup_layers
        )
        self.action_duplicate_layer = self._action(
            "Duplicate Layer", "Ctrl+J", self._on_duplicate_layer
        )
        self.action_rename_layer = self._action("Rename Layer…", "F2", self._on_rename_layer)
        self.action_delete_layer = self._action("Delete Layer", "", self._on_delete_layer)
        self.action_merge_down = self._action("Merge Down", "Ctrl+E", self._on_merge_down)
        self.action_flatten = self._action("Flatten Image", "Ctrl+Shift+E", self._on_flatten)
        self.action_add_mask = self._action("Add Layer Mask", "", self._on_add_layer_mask)
        self.action_remove_mask = self._action(
            "Remove Layer Mask", "", self._on_remove_layer_mask
        )
        self.action_apply_mask = self._action(
            "Apply Layer Mask", "", self._on_apply_layer_mask
        )
        self.action_toggle_mask = self._action(
            "Disable Layer Mask", "", self._on_toggle_layer_mask
        )
        self.action_toggle_mask.setCheckable(True)
        self.action_paint_mask = self._action(
            "Paint on Layer Mask", "", self._on_toggle_paint_mask
        )
        self.action_paint_mask.setCheckable(True)
        self.action_paint_mask.setToolTip(
            "Brush/Gradient sẽ vẽ lên layer mask thay vì pixel của layer.\n"
            "Màu mask lấy theo độ sáng của màu: đen = ẩn, trắng = hiện."
        )
        self.action_new_text = self._action(
            "New Text Layer…", "Ctrl+Shift+T", lambda: self._on_new_text_layer()
        )
        self.action_edit_text = self._action("Edit Text…", "", self._on_edit_text)
        self.action_rasterize_text = self._action(
            "Rasterize Text", "", self._on_rasterize_text
        )
        self.action_new_shape = self._action(
            "New Shape Layer…", "", lambda: self._on_new_shape_layer()
        )
        self.action_edit_shape = self._action("Edit Shape…", "", self._on_edit_shape)
        self.action_rasterize_shape = self._action(
            "Rasterize Shape", "", self._on_rasterize_shape
        )
        self.action_new_fill_solid = self._action(
            "Solid Color…", "", lambda: self._on_new_fill_layer("solid")
        )
        self.action_new_fill_gradient = self._action(
            "Gradient…", "", lambda: self._on_new_fill_layer("gradient")
        )
        self.action_edit_fill = self._action("Edit Fill…", "", self._on_edit_fill)
        self.action_rasterize_fill = self._action(
            "Rasterize Fill", "", self._on_rasterize_fill
        )
        self.action_place_smart_object = self._action(
            "Place as Smart Object…", "", self._on_place_smart_object
        )
        self.action_edit_smart_object = self._action(
            "Edit Smart Object…", "", self._on_edit_smart_object
        )
        self.action_replace_smart_contents = self._action(
            "Replace Contents…", "", self._on_replace_smart_contents
        )
        self.action_reset_smart_object = self._action(
            "Reset Transform", "", self._on_reset_smart_object
        )
        self.action_rasterize_smart = self._action(
            "Rasterize Smart Object", "", self._on_rasterize_smart
        )
        self.action_new_adjustment_brightness_contrast = self._action(
            "Brightness/Contrast…",
            "",
            lambda: self._on_new_adjustment_layer("brightness_contrast"),
        )
        self.action_new_adjustment_hue_saturation = self._action(
            "Hue/Saturation…",
            "",
            lambda: self._on_new_adjustment_layer("hue_saturation"),
        )
        self.action_new_adjustment_invert = self._action(
            "Invert", "", lambda: self._on_new_adjustment_layer("invert")
        )
        self.action_new_adjustment_desaturate = self._action(
            "Desaturate", "", lambda: self._on_new_adjustment_layer("desaturate")
        )
        self.action_new_adjustment_levels = self._action(
            "Levels…", "", lambda: self._on_new_adjustment_layer("levels")
        )
        self.action_new_adjustment_curves = self._action(
            "Curves…", "", lambda: self._on_new_adjustment_layer("curves")
        )
        self.action_new_adjustment_color_balance = self._action(
            "Color Balance…",
            "",
            lambda: self._on_new_adjustment_layer("color_balance"),
        )
        self.action_edit_adjustment = self._action(
            "Edit Adjustment…", "", lambda: self._on_edit_adjustment()
        )

        self.action_filter_brightness_contrast = self._action(
            "Brightness/Contrast…", "", self._on_filter_brightness_contrast
        )
        self.action_filter_hue_saturation = self._action(
            "Hue/Saturation…", "Ctrl+U", self._on_filter_hue_saturation
        )
        self.action_filter_auto_contrast = self._action(
            "Auto Contrast",
            "",
            lambda: self._apply_simple_filter(filters.auto_contrast, "Auto Contrast"),
        )
        self.action_filter_invert = self._action(
            "Invert",
            "Ctrl+I",
            lambda: self._apply_simple_filter(filters.invert, "Invert"),
        )
        self.action_filter_desaturate = self._action(
            "Desaturate",
            "Ctrl+Shift+U",
            lambda: self._apply_simple_filter(filters.desaturate, "Desaturate"),
        )
        self.action_filter_gaussian_blur = self._action(
            "Gaussian Blur…", "", self._on_filter_gaussian_blur
        )
        self.action_filter_unsharp_mask = self._action(
            "Unsharp Mask…", "", self._on_filter_unsharp_mask
        )

        self.action_select_all = self._action("Select All", "Ctrl+A", self._on_select_all)
        self.action_deselect = self._action("Deselect", "Ctrl+D", self._on_deselect)
        self.action_invert_selection = self._action(
            "Inverse Selection", "Ctrl+Shift+I", self._on_invert_selection
        )
        self.action_feather_selection = self._action(
            "Feather Selection…", "Shift+F6", self._on_feather_selection
        )
        self.action_quick_mask = QAction("Quick Mask", self)
        self.action_quick_mask.setCheckable(True)
        self.action_quick_mask.setToolTip(
            "Phủ đỏ phần chưa nằm trong vùng chọn (phím Q khi canvas đang focus)."
        )
        self.action_quick_mask.toggled.connect(self._on_toggle_quick_mask)
        self.action_crop = self._action("Crop", "", self._on_crop_tool)
        self.action_crop_selection = self._action(
            "Crop to Selection", "", self._on_crop_to_selection
        )
        self.action_image_size = self._action(
            "Image Size…", "Ctrl+Alt+I", self._on_image_size
        )
        self.action_canvas_size = self._action(
            "Canvas Size…", "Ctrl+Alt+C", self._on_canvas_size
        )

        self.action_rotate_cw = self._action(
            "Rotate 90° Clockwise", "", lambda: self._on_rotate_canvas("cw")
        )
        self.action_rotate_ccw = self._action(
            "Rotate 90° Counter Clockwise", "", lambda: self._on_rotate_canvas("ccw")
        )
        self.action_rotate_180 = self._action(
            "Rotate 180°", "", lambda: self._on_rotate_canvas("180")
        )
        self.action_rotate_arbitrary = self._action(
            "Arbitrary Rotation…", "", self._on_rotate_canvas_arbitrary
        )
        self.action_flip_canvas_h = self._action(
            "Flip Canvas Horizontal", "", lambda: self._on_flip_canvas(True)
        )
        self.action_flip_canvas_v = self._action(
            "Flip Canvas Vertical", "", lambda: self._on_flip_canvas(False)
        )
        self.action_layer_rotate_cw = self._action(
            "Rotate 90° Clockwise", "", lambda: self._on_transform_layer("rotate_cw")
        )
        self.action_layer_rotate_ccw = self._action(
            "Rotate 90° Counter Clockwise",
            "",
            lambda: self._on_transform_layer("rotate_ccw"),
        )
        self.action_layer_rotate_180 = self._action(
            "Rotate 180°", "", lambda: self._on_transform_layer("rotate_180")
        )
        self.action_layer_rotate_arbitrary = self._action(
            "Rotate…", "", self._on_rotate_layer_arbitrary
        )
        self.action_layer_flip_h = self._action(
            "Flip Horizontal", "", lambda: self._on_transform_layer("flip_h")
        )
        self.action_layer_flip_v = self._action(
            "Flip Vertical", "", lambda: self._on_transform_layer("flip_v")
        )

        self.action_zoom_in = self._action("Zoom In", "Ctrl+=", self._on_zoom_in)
        self.action_zoom_out = self._action("Zoom Out", "Ctrl+-", self._on_zoom_out)
        self.action_fit = self._action("Fit on Screen", "Ctrl+0", self._on_fit)
        self.action_actual = self._action("Actual Pixels", "Ctrl+1", self._on_actual)

        self.action_previous_document = self._action(
            "Previous Document", "Ctrl+Shift+Tab", lambda: self._cycle_document(-1)
        )
        self.action_next_document = self._action(
            "Next Document", "Ctrl+Tab", lambda: self._cycle_document(1)
        )

        self.action_shortcuts = self._action("Keyboard Shortcuts", "", self._on_shortcuts)
        self.action_about = self._action("About My Photo Studio", "", self._on_about)

        self.action_theme_dark = QAction("Dark", self)
        self.action_theme_dark.setCheckable(True)
        self.action_theme_light = QAction("Light", self)
        self.action_theme_light.setCheckable(True)
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        theme_group.addAction(self.action_theme_dark)
        theme_group.addAction(self.action_theme_light)
        self.action_theme_dark.triggered.connect(lambda: self._set_theme(THEME_DARK))
        self.action_theme_light.triggered.connect(lambda: self._set_theme(THEME_LIGHT))
        if self.settings.theme == THEME_LIGHT:
            self.action_theme_light.setChecked(True)
        else:
            self.action_theme_dark.setChecked(True)

    def _action(self, text: str, shortcut: str, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _create_menu(self) -> None:
        self._menu_bar = build_menu_bar(self)
        self.setMenuBar(self._menu_bar)
        self.menu_open_recent = getattr(self, "menu_open_recent", None)

    # ------------------------------------------------------------ trạng thái UI
    @property
    def current_view(self) -> CanvasView | None:
        view = self.tabs.currentWidget()
        if isinstance(view, CanvasView) and self._stack.currentWidget() is self.tabs:
            return view
        return None

    @property
    def current_document(self) -> Document | None:
        view = self.current_view
        return view.document if view else None

    def _on_tab_changed(self, index: int) -> None:
        self._disconnect_document_signals()
        view = self.current_view
        if view is None:
            self._current_view = None
            self.options_bar.bind_view(None)
            self.app_status.bind_view(None)
            self.layers_panel.bind_document(None)
            self.properties_panel.bind_document(None)
            self._stack.setCurrentWidget(self.welcome)
            self._update_window_title()
            self._update_action_states()
            return

        self._stack.setCurrentWidget(self.tabs)
        self._current_view = view
        document = view.document
        self._connect_document_signals(document)
        self.options_bar.bind_view(view)
        self.app_status.bind_view(view)
        self.layers_panel.bind_document(document)
        self.properties_panel.bind_document(document)
        self.toolbox.set_current_tool(view.tool_id)
        self.app_status.set_hint(view.current_tool.hint)
        self._update_window_title()
        self._update_action_states()

    def _connect_document_signals(self, document: Document) -> None:
        pairs = [
            (document.history_changed, self._update_action_states),
            (document.structure_changed, self._update_action_states),
            (document.active_layer_changed, self._update_action_states),
            (document.selection_changed, self._update_action_states),
            (document.title_changed, self._on_document_title_changed),
        ]
        for signal, slot in pairs:
            signal.connect(slot)
            self._document_connections.append((signal, slot))

    def _disconnect_document_signals(self) -> None:
        for signal, slot in self._document_connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._document_connections.clear()

    def _on_document_title_changed(self) -> None:
        self._update_window_title()
        self._update_action_states()

    def _update_window_title(self) -> None:
        document = self.current_document
        if document is None:
            self.setWindowTitle(APP_NAME)
        else:
            self.setWindowTitle(f"{document.title} — {APP_NAME}")

    def _update_action_states(self) -> None:
        document = self.current_document
        has_document = document is not None
        active = document.active_layer if document else None
        for action in (
            self.action_save,
            self.action_save_as,
            self.action_export,
            self.action_close,
            self.action_new_layer,
            self.action_new_group,
            self.action_zoom_in,
            self.action_zoom_out,
            self.action_fit,
            self.action_actual,
            self.action_select_all,
            self.action_crop,
            self.action_new_text,
            self.action_image_size,
            self.action_canvas_size,
            self.action_rotate_cw,
            self.action_rotate_ccw,
            self.action_rotate_180,
            self.action_rotate_arbitrary,
            self.action_flip_canvas_h,
            self.action_flip_canvas_v,
            self.action_new_adjustment_brightness_contrast,
            self.action_new_adjustment_hue_saturation,
            self.action_new_adjustment_invert,
            self.action_new_adjustment_desaturate,
            self.action_new_adjustment_levels,
            self.action_new_adjustment_curves,
            self.action_new_adjustment_color_balance,
            self.action_new_fill_solid,
            self.action_new_fill_gradient,
            self.action_place_smart_object,
        ):
            action.setEnabled(has_document)
        has_selection = bool(document and document.has_selection())
        self.action_deselect.setEnabled(has_selection)
        self.action_invert_selection.setEnabled(has_selection)
        self.action_feather_selection.setEnabled(has_selection)
        self.action_crop_selection.setEnabled(has_selection)
        self.action_quick_mask.setEnabled(has_document)
        view = self.current_view
        quick_mask_enabled = bool(view is not None and view.quick_mask)
        if self.action_quick_mask.isChecked() != quick_mask_enabled:
            self.action_quick_mask.blockSignals(True)
            try:
                self.action_quick_mask.setChecked(quick_mask_enabled)
            finally:
                self.action_quick_mask.blockSignals(False)
        self.action_undo.setEnabled(bool(document and document.history.can_undo))
        self.action_redo.setEnabled(bool(document and document.history.can_redo))
        self.action_undo.setText("Undo")
        self.action_redo.setText("Redo")
        if document is not None:
            if document.history.can_undo:
                self.action_undo.setToolTip(document.history.undo_label)
            if document.history.can_redo:
                self.action_redo.setToolTip(document.history.redo_label)

        has_active = active is not None
        is_adjustment = bool(
            active is not None and active.kind == LayerKind.ADJUSTMENT
        )
        is_group = bool(active is not None and active.kind == LayerKind.GROUP)
        has_pixels = bool(active is not None and not active.uses_canvas_mask)
        for action in (
            self.action_duplicate_layer,
            self.action_rename_layer,
            self.action_delete_layer,
        ):
            action.setEnabled(has_active)
        self.action_group_layers.setEnabled(has_active)
        self.action_ungroup_layers.setEnabled(is_group)
        self.action_add_mask.setEnabled(
            has_active and (active is None or active.mask is None)
        )
        for action in (
            self.action_layer_rotate_cw,
            self.action_layer_rotate_ccw,
            self.action_layer_rotate_180,
            self.action_layer_rotate_arbitrary,
            self.action_layer_flip_h,
            self.action_layer_flip_v,
        ):
            action.setEnabled(has_active and has_pixels)
        self.action_edit_adjustment.setEnabled(is_adjustment)
        can_filter = has_active and has_pixels and not bool(
            active and active.locked
        )
        for action in (
            self.action_filter_brightness_contrast,
            self.action_filter_hue_saturation,
            self.action_filter_auto_contrast,
            self.action_filter_invert,
            self.action_filter_desaturate,
            self.action_filter_gaussian_blur,
            self.action_filter_unsharp_mask,
        ):
            action.setEnabled(can_filter)
        has_mask = bool(active is not None and active.mask is not None)
        self.action_remove_mask.setEnabled(has_mask)
        self.action_apply_mask.setEnabled(has_mask and has_pixels)
        self.action_toggle_mask.setEnabled(has_mask)
        mask_enabled = bool(has_mask and active.mask_enabled)
        self.action_toggle_mask.blockSignals(True)
        self.action_toggle_mask.setChecked(mask_enabled)
        self.action_toggle_mask.blockSignals(False)
        self.action_toggle_mask.setText(
            "Disable Layer Mask" if mask_enabled else "Enable Layer Mask"
        )
        paint_mask = False
        if self.current_view is not None:
            paint_mask = bool(
                self.current_view.brush_options().get("paint_mask")
                or self.current_view.gradient_options().get("paint_mask")
            )
            if paint_mask and not has_mask:
                self.current_view.set_paint_mask(False)
                paint_mask = False
        self.action_paint_mask.setEnabled(has_mask)
        self.action_paint_mask.blockSignals(True)
        self.action_paint_mask.setChecked(bool(has_mask and paint_mask))
        self.action_paint_mask.blockSignals(False)
        is_text_layer = bool(active is not None and active.kind == LayerKind.TEXT)
        self.action_edit_text.setEnabled(is_text_layer)
        self.action_rasterize_text.setEnabled(is_text_layer)
        is_shape_layer = bool(active is not None and active.kind == LayerKind.SHAPE)
        self.action_edit_shape.setEnabled(is_shape_layer)
        self.action_rasterize_shape.setEnabled(is_shape_layer)
        is_fill_layer = bool(active is not None and active.kind == LayerKind.FILL)
        self.action_edit_fill.setEnabled(is_fill_layer)
        self.action_rasterize_fill.setEnabled(is_fill_layer)
        is_smart_layer = bool(active is not None and active.kind == LayerKind.SMART)
        for action in (
            self.action_edit_smart_object,
            self.action_replace_smart_contents,
            self.action_reset_smart_object,
            self.action_rasterize_smart,
        ):
            action.setEnabled(is_smart_layer)
        smart_has_mask = bool(
            is_smart_layer and active is not None and active.mask is not None
        )
        self.action_edit_smart_object.setEnabled(
            is_smart_layer and not smart_has_mask
        )
        self.action_replace_smart_contents.setEnabled(
            is_smart_layer and not smart_has_mask
        )
        self.action_reset_smart_object.setEnabled(
            is_smart_layer and not smart_has_mask
        )
        can_merge = False
        if document is not None and active is not None:
            index = document.layers.index_of(active)
            if index > 0 and not is_group:
                lower = document.layers[index - 1]
                can_merge = (
                    lower.kind != LayerKind.GROUP
                    and lower.group_id == active.group_id
                )
        self.action_merge_down.setEnabled(can_merge)
        self.action_flatten.setEnabled(bool(document and len(document.layers) > 0))
        can_cycle = self.tabs.count() > 1
        self.action_next_document.setEnabled(can_cycle)
        self.action_previous_document.setEnabled(can_cycle)

    def _show_transient_message(self, message: str) -> None:
        self.statusBar().showMessage(message, 4000)

    # --------------------------------------------------------------- mở tài liệu
    def _on_open_documents(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Mở ảnh hoặc dự án",
            self.settings.resolved_last_directory(),
            OPEN_FILTER,
        )
        if files:
            self.open_paths(files)

    def open_paths(self, paths: list[str]) -> None:
        opened = False
        for raw_path in paths:
            path = Path(raw_path)
            if not path.exists():
                self.settings_store.remove_recent(str(path))
                QMessageBox.critical(
                    self, "Không tìm thấy file", f"File không tồn tại:\n{path}"
                )
                self._refresh_recent_ui()
                continue
            try:
                if path.suffix.lower() == ".mps":
                    document = load_project(path)
                else:
                    document = load_image_document(path)
            except (ProjectFormatError, ImageImportError) as exc:
                QMessageBox.critical(self, "Không thể mở file", str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - hiển thị lỗi thân thiện cho người dùng
                logger.exception("Lỗi không mong đợi khi mở %s", path)
                QMessageBox.critical(
                    self,
                    "Không thể mở file",
                    f"Đã xảy ra lỗi khi mở:\n{path}\n\nChi tiết: {exc}",
                )
                continue
            self.settings_store.add_recent(str(path))
            self._add_document_tab(document)
            opened = True
        if opened:
            self._refresh_recent_ui()
            self._update_action_states()

    def _add_document_tab(self, document: Document) -> None:
        view = CanvasView(document, self.tabs)
        view.set_brush_color(tuple(self.color_manager.foreground.getRgb()))
        view.set_gradient_colors(
            tuple(self.color_manager.foreground.getRgb()),
            tuple(self.color_manager.background.getRgb()),
        )
        self.tabs.add_view(view)
        view.status_message.connect(self._show_transient_message)
        view.tool_changed.connect(
            lambda tool_id, target=view: self._on_view_tool_changed(target, tool_id)
        )
        view.text_placement_requested.connect(
            lambda position, target=view: self._on_text_placement_requested(
                target, position
            )
        )
        view.inline_text_finished.connect(
            lambda layer_id, properties, position, target=view: (
                self._on_inline_text_finished(target, layer_id, properties, position)
            )
        )
        view.quick_mask_changed.connect(
            lambda enabled, target=view: self._on_view_quick_mask_changed(
                target, enabled
            )
        )
        self._stack.setCurrentWidget(self.tabs)
        self.tabs.setCurrentWidget(view)
        self._on_tab_changed(self.tabs.currentIndex())

    def _on_view_tool_changed(self, view: CanvasView, tool_id: str) -> None:
        if view is self.current_view:
            self.toolbox.set_current_tool(tool_id)
            self.app_status.set_hint(view.current_tool.hint)

    def _on_view_quick_mask_changed(self, view: CanvasView, enabled: bool) -> None:
        if view is not self.current_view:
            return
        action = self.action_quick_mask
        if action.isChecked() == enabled:
            return
        action.blockSignals(True)
        try:
            action.setChecked(enabled)
        finally:
            action.blockSignals(False)

    def _on_tool_selected(self, tool_id: str) -> None:
        view = self.current_view
        if view is not None and view.tool_id != tool_id:
            view.set_tool(tool_id)

    def _on_colors_changed(self) -> None:
        foreground = tuple(self.color_manager.foreground.getRgb())
        background = tuple(self.color_manager.background.getRgb())
        for view in self.tabs.views():
            view.set_brush_color(foreground)
            view.set_gradient_colors(foreground, background)
        self.options_bar.refresh_paint_colors()

    # ------------------------------------------------------------ tạo tài liệu
    def _on_new_document(self) -> None:
        dialog = NewDocumentDialog(self, f"Untitled-{self._untitled_counter}")
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            document = Document(
                dialog.document_width,
                dialog.document_height,
                dpi=dialog.resolution,
                name=f"Untitled-{self._untitled_counter}",
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Không thể tạo tài liệu", str(exc))
            return
        self._untitled_counter += 1
        background = dialog.background_rgba()
        document.add_layer(
            name="Background" if background is not None else "Layer 1",
            color=background,
            select=True,
            record=False,
        )
        document.mark_clean()
        self._add_document_tab(document)
        self._show_transient_message("Đã tạo tài liệu mới.")

    # -------------------------------------------------------------- lưu / xuất
    def _on_save(self) -> None:
        document = self.current_document
        if document is not None:
            self._save_document(document)

    def _on_save_as(self) -> None:
        document = self.current_document
        if document is not None:
            self._save_document_as(document)

    def _save_document(self, document: Document) -> bool:
        if document.file_path:
            try:
                path = save_project(document, document.file_path)
            except ProjectFormatError as exc:
                QMessageBox.critical(self, "Lỗi lưu dự án", str(exc))
                return False
            self._after_save(document, path)
            return True
        return self._save_document_as(document)

    def _save_document_as(self, document: Document) -> bool:
        start_dir = self.settings.resolved_last_directory()
        stem = Path(document.file_path).stem if document.file_path else Path(document.name).stem
        suggested = str(Path(start_dir) / f"{stem}.mps")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Lưu dự án My Photo Studio", suggested, PROJECT_FILTER
        )
        if not filename:
            return False
        target = ensure_project_extension(filename)
        try:
            path = save_project(document, target)
        except ProjectFormatError as exc:
            QMessageBox.critical(self, "Lỗi lưu dự án", str(exc))
            return False
        self._after_save(document, path)
        return True

    def _after_save(self, document: Document, path: Path) -> None:
        self.settings_store.add_recent(str(path))
        self._refresh_recent_ui()
        view = self._view_for_document(document)
        if view is not None:
            self.tabs.update_tab_title(view)
        self._update_window_title()
        self._update_action_states()
        self._show_transient_message(f"Đã lưu dự án: {path.name}")

    def _on_export(self) -> None:
        document = self.current_document
        if document is None:
            return
        start_dir = self.settings.resolved_last_directory()
        stem = Path(document.file_path).stem if document.file_path else Path(document.name).stem
        suggested = str(Path(start_dir) / f"{stem}.png")
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, "Export As", suggested, EXPORT_FILTER
        )
        if not filename:
            return
        target = Path(filename)
        if not target.suffix:
            extension = ".png"
            if "JPEG" in selected_filter:
                extension = ".jpg"
            elif "BMP" in selected_filter:
                extension = ".bmp"
            elif "TIFF" in selected_filter:
                extension = ".tif"
            elif "WebP" in selected_filter:
                extension = ".webp"
            target = target.with_suffix(extension)
        try:
            composite = document.get_composite()
            export_image(target, composite.array)
        except ExportError as exc:
            QMessageBox.critical(self, "Lỗi xuất ảnh", str(exc))
            return
        self.settings.last_directory = str(target.parent)
        self.settings_store.save()
        self._show_transient_message(f"Đã xuất ảnh: {target.name}")

    def _on_batch_processing(self) -> None:
        dialog = BatchDialog(
            self,
            preset_store=self.preset_store,
            start_directory=self.settings.resolved_last_directory(),
        )
        exec_object(dialog)
        if dialog.last_results:
            self._show_transient_message(
                f"Xử lý hàng loạt xong {len(dialog.last_results)} file "
                f"(xem thư mục đầu ra)."
            )
        output_dir = dialog.output_directory()
        if output_dir:
            self.settings.last_directory = output_dir
            self.settings_store.save()

    # ------------------------------------------------------------ đóng tài liệu
    def _on_close_document(self) -> None:
        index = self.tabs.currentIndex()
        if index >= 0:
            self._request_close_tab(index)

    def _request_close_tab(self, index: int) -> None:
        view = self.tabs.widget(index)
        if not isinstance(view, CanvasView):
            return
        if not self._confirm_close_document(view.document):
            return
        self._remove_view(view)

    def _confirm_close_document(self, document: Document) -> bool:
        if not document.modified:
            return True
        answer = QMessageBox.warning(
            self,
            "Tài liệu chưa lưu",
            f"'{document.base_title}' có thay đổi chưa lưu.\nBạn có muốn lưu lại?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Discard:
            return True
        return self._save_document(document)

    def _remove_view(self, view: CanvasView) -> None:
        if self.tabs.indexOf(view) >= 0:
            self.tabs.remove_view(view)
        view.deleteLater()
        if self.tabs.count() == 0:
            self._stack.setCurrentWidget(self.welcome)
            self._on_tab_changed(-1)

    def _view_for_document(self, document: Document) -> CanvasView | None:
        for view in self.tabs.views():
            if view.document is document:
                return view
        return None

    # ------------------------------------------------------------- undo / layer
    def _on_undo(self) -> None:
        document = self.current_document
        if document is not None:
            document.undo()
            self._update_action_states()

    def _on_redo(self) -> None:
        document = self.current_document
        if document is not None:
            document.redo()
            self._update_action_states()

    def _on_new_layer(self) -> None:
        document = self.current_document
        if document is None:
            return
        try:
            document.add_layer()
            self._show_transient_message("Đã thêm layer mới.")
        except ValueError as exc:
            QMessageBox.critical(self, "Không thể thêm layer", str(exc))

    def _on_new_group(self) -> None:
        document = self.current_document
        if document is None:
            return
        group = document.add_group()
        self._show_transient_message(f"Đã thêm nhóm '{group.name}'.")

    def _on_group_layers(self) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            return
        try:
            group = document.group_layers()
        except ValueError as exc:
            QMessageBox.warning(self, "Không thể nhóm layer", str(exc))
            return
        if group is not None:
            self._show_transient_message(
                f"Đã đưa layer vào nhóm '{group.name}' (Ctrl+Z để hoàn tác)."
            )

    def _on_ungroup_layers(self) -> None:
        document = self.current_document
        if document is None:
            return
        try:
            changed = document.ungroup_layer()
        except ValueError as exc:
            QMessageBox.warning(self, "Không thể bỏ nhóm", str(exc))
            return
        if changed:
            self._show_transient_message("Đã bỏ nhóm (Ctrl+Z để hoàn tác).")

    def _on_duplicate_layer(self) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            return
        document.duplicate_layer()
        self._show_transient_message("Đã nhân bản layer.")

    def _on_delete_layer(self) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            return
        document.remove_layer()
        self._show_transient_message("Đã xoá layer (Ctrl+Z để hoàn tác).")

    def _on_rename_layer(self) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            return
        layer = document.active_layer
        name, accepted = QInputDialog.getText(
            self, "Rename Layer", "Tên layer:", text=layer.name
        )
        if accepted and name.strip():
            document.rename_layer(layer, name)

    def _on_merge_down(self) -> None:
        document = self.current_document
        if document is None:
            return
        if not document.merge_down():
            self._show_transient_message(
                "Merge Down cần layer nằm trên ít nhất một layer khác."
            )

    def _on_flatten(self) -> None:
        document = self.current_document
        if document is None:
            return
        if not document.flatten_image():
            self._show_transient_message("Tài liệu chưa có layer nào để flatten.")

    # ------------------------------------------------------------ vùng chọn
    def _on_select_all(self) -> None:
        document = self.current_document
        if document is not None:
            document.select_all()

    def _on_deselect(self) -> None:
        document = self.current_document
        if document is not None:
            document.deselect()

    def _on_invert_selection(self) -> None:
        document = self.current_document
        if document is not None:
            document.invert_selection()

    def _on_feather_selection(self) -> None:
        document = self.current_document
        if document is None or not document.has_selection():
            self._show_transient_message("Hãy tạo vùng chọn trước khi dùng Feather.")
            return
        dialog = FeatherDialog(document.selection.feather, parent=self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        radius = dialog.radius
        try:
            changed = document.feather_selection(radius)
        except ValueError as error:
            QMessageBox.warning(self, "Feather không hợp lệ", str(error))
            return
        if changed:
            self._show_transient_message(
                f"Đã feather vùng chọn {radius:g} px (Ctrl+Z để hoàn tác)."
            )
        else:
            self._show_transient_message("Vùng chọn đã có bán kính feather này.")

    def _on_toggle_quick_mask(self, checked: bool) -> None:
        view = self.current_view
        if view is None:
            self.action_quick_mask.blockSignals(True)
            try:
                self.action_quick_mask.setChecked(False)
            finally:
                self.action_quick_mask.blockSignals(False)
            return
        if checked and not view.document.has_selection():
            self.action_quick_mask.blockSignals(True)
            try:
                self.action_quick_mask.setChecked(False)
            finally:
                self.action_quick_mask.blockSignals(False)
            self._show_transient_message(
                "Hãy tạo vùng chọn trước khi bật Quick Mask."
            )
            return
        enabled = view.set_quick_mask(checked)
        if enabled != checked:
            self.action_quick_mask.blockSignals(True)
            try:
                self.action_quick_mask.setChecked(enabled)
            finally:
                self.action_quick_mask.blockSignals(False)
        if enabled:
            self._show_transient_message(
                "Quick Mask: vùng đỏ là phần CHƯA chọn. Nhấn Q để tắt."
            )
        else:
            self._show_transient_message("Đã tắt Quick Mask.")

    # ------------------------------------------------------------ mask
    def _on_add_layer_mask(self) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            self._show_transient_message("Hãy chọn một layer trước khi thêm mask.")
            return
        had_selection = document.has_selection()
        try:
            changed = document.add_layer_mask()
        except ValueError as exc:
            QMessageBox.critical(self, "Không thể thêm layer mask", str(exc))
            return
        if changed:
            active = document.active_layer
            if active is not None and active.kind == LayerKind.GROUP:
                self._show_transient_message(
                    "Đã thêm mask cho nhóm (trắng = hiện, đen = ẩn toàn nhóm)."
                )
            elif active is not None and active.kind == LayerKind.ADJUSTMENT:
                self._show_transient_message(
                    "Đã thêm mask cho layer điều chỉnh (trắng = áp hiệu ứng, "
                    "đen = giữ nguyên ảnh)."
                )
            else:
                self._show_transient_message(
                    "Đã thêm layer mask từ vùng chọn."
                    if had_selection
                    else "Đã thêm layer mask (hiển thị toàn bộ layer)."
                )

    def _on_remove_layer_mask(self) -> None:
        document = self.current_document
        if document is None:
            return
        if document.remove_layer_mask():
            self._show_transient_message("Đã xoá layer mask (Ctrl+Z để hoàn tác).")

    def _on_apply_layer_mask(self) -> None:
        document = self.current_document
        if document is None:
            return
        layer = document.active_layer
        if layer is None or layer.mask is None:
            return
        enabled = layer.mask_enabled
        if document.apply_layer_mask():
            self._show_transient_message(
                "Đã áp mask vào pixel của layer."
                if enabled
                else "Mask đang tắt nên chỉ được gỡ bỏ, pixel không đổi."
            )

    def _on_toggle_layer_mask(self, checked: bool) -> None:
        document = self.current_document
        if document is None:
            return
        document.set_layer_mask_enabled(document.active_layer, checked)

    def _on_toggle_paint_mask(self, checked: bool) -> None:
        view = self.current_view
        if view is None:
            return
        layer = view.document.active_layer
        if checked and (layer is None or layer.mask is None):
            self._update_action_states()
            self._show_transient_message(
                "Layer đang chọn chưa có mask. Hãy thêm Layer Mask trước."
            )
            return
        view.set_paint_mask(checked)
        self.options_bar.sync_paint_state()
        if checked:
            if view.tool_id not in ("brush", "gradient"):
                view.set_tool("brush")
                self.toolbox.set_current_tool("brush")
            self._show_transient_message(
                "Brush/Gradient sẽ vẽ lên layer mask. Màu mask = độ sáng màu: "
                "đen = ẩn, trắng = hiện."
            )
        else:
            self._show_transient_message("Brush/Gradient sẽ vẽ lên pixel của layer.")

    # ------------------------------------------------------------ văn bản
    def _on_text_placement_requested(self, view: CanvasView, position: QPointF) -> None:
        if view is not self.current_view:
            self.tabs.setCurrentWidget(view)
        document = view.document
        color = tuple(self.color_manager.foreground.getRgb())
        default_size = max(12, min(96, min(document.width, document.height) // 8))
        view.begin_inline_text(position, TextRun("", "", default_size, color))

    def _on_inline_text_finished(
        self,
        view: CanvasView,
        layer_id: str,
        properties: object,
        position: QPointF,
    ) -> None:
        if view is not self.current_view:
            self.tabs.setCurrentWidget(view)
        document = view.document
        if not isinstance(properties, TextProperties):
            return
        layer = document.layers.get(layer_id) if layer_id else None
        if layer_id and layer is None:
            self._show_transient_message(
                "Layer văn bản đã không còn tồn tại — bỏ qua nội dung vừa gõ."
            )
            return
        if layer is not None:
            try:
                changed = document.update_text_layer(properties, layer)
            except (ValueError, MemoryError) as exc:
                QMessageBox.critical(self, "Không thể sửa văn bản", str(exc))
                return
            if changed:
                self._show_transient_message(
                    "Đã cập nhật văn bản trên canvas (Ctrl+Z để hoàn tác)."
                )
        else:
            try:
                layer = document.add_text_layer(
                    properties,
                    int(round(position.x())),
                    int(round(position.y())),
                )
            except (ValueError, MemoryError) as exc:
                QMessageBox.critical(self, "Không thể tạo layer văn bản", str(exc))
                return
            self._show_transient_message(
                f"Đã thêm layer văn bản '{layer.name}' (Ctrl+Z để hoàn tác)."
            )
        self._update_action_states()

    def _on_new_text_layer(self, position: QPointF | None = None) -> None:
        document = self.current_document
        if document is None:
            return
        x = y = None
        if isinstance(position, QPointF):
            x, y = int(round(position.x())), int(round(position.y()))
        color = self.color_manager.foreground.getRgb()
        default_size = max(12, min(96, min(document.width, document.height) // 8))
        dialog = TextDialog(
            self,
            editing=False,
            default_color=color,
            default_size=default_size,
        )
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            layer = document.add_text_layer(dialog.properties, x, y)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể tạo layer văn bản", str(exc))
            return
        self._show_transient_message(
            f"Đã thêm layer văn bản '{layer.name}' (menu Type để sửa nội dung)."
        )

    def _on_edit_text(self) -> None:
        document = self.current_document
        if document is None:
            return
        layer = document.active_layer
        if layer is None or layer.kind != LayerKind.TEXT or layer.text is None:
            self._show_transient_message("Hãy chọn một layer văn bản để sửa.")
            return
        dialog = TextDialog(self, layer.text, editing=True)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.update_text_layer(dialog.properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể sửa văn bản", str(exc))
            return
        if changed:
            self._show_transient_message("Đã cập nhật văn bản (Ctrl+Z để hoàn tác).")

    def _on_rasterize_text(self) -> None:
        document = self.current_document
        if document is None:
            return
        if document.rasterize_text_layer():
            self._show_transient_message(
                "Đã rasterize layer văn bản thành pixel (Ctrl+Z để hoàn tác)."
            )

    # ----------------------------------------------------------- hình khối
    def _default_shape_properties(self) -> ShapeProperties:
        document = self.current_document
        view = self.current_view
        options = view.shape_options() if view is not None else {}
        width = max(1, min(240, document.width if document is not None else 240))
        height = max(1, min(160, document.height if document is not None else 160))
        stroke_width = min(
            int(options.get("stroke_width", 0)), max(0, min(width, height) // 2)
        )
        fill = options.get("fill_color")
        if fill is None and stroke_width == 0:
            stroke_width = 2
        return ShapeProperties(
            kind=str(options.get("kind", "rectangle")),
            width=width,
            height=height,
            fill_color=fill,
            stroke_color=tuple(
                options.get("stroke_color", (255, 255, 255, 255))
            ),
            stroke_width=stroke_width,
            corner_radius=float(options.get("corner_radius", 0.0)),
        )

    def _on_new_shape_layer(self) -> None:
        document = self.current_document
        if document is None:
            return
        try:
            defaults = self._default_shape_properties()
        except ValueError as exc:
            QMessageBox.critical(self, "Không thể tạo hình khối", str(exc))
            return
        dialog = ShapeDialog(self, defaults, editing=False)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            layer = document.add_shape_layer(dialog.properties)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể tạo layer hình khối", str(exc))
            return
        self._show_transient_message(
            f"Đã thêm layer hình khối '{layer.name}' (menu Layer ▸ Shape để sửa)."
        )

    def _on_edit_shape(self) -> None:
        document = self.current_document
        if document is None:
            return
        layer = document.active_layer
        if layer is None or layer.kind != LayerKind.SHAPE or layer.shape is None:
            self._show_transient_message("Hãy chọn một layer hình khối để sửa.")
            return
        dialog = ShapeDialog(self, layer.shape, editing=True)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.update_shape_layer(dialog.properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể sửa hình khối", str(exc))
            return
        if changed:
            self._show_transient_message("Đã cập nhật hình khối (Ctrl+Z để hoàn tác).")

    def _on_rasterize_shape(self) -> None:
        document = self.current_document
        if document is None:
            return
        if document.rasterize_shape_layer():
            self._show_transient_message(
                "Đã rasterize layer hình khối thành pixel (Ctrl+Z để hoàn tác)."
            )

    # ------------------------------------------------- layer tô / smart object
    def _on_new_fill_layer(self, fill_type: str = "solid") -> None:
        document = self.current_document
        if document is None:
            return
        defaults = FillProperties(
            fill_type=fill_type,
            color=tuple(self.color_manager.foreground.getRgb()),
            color2=tuple(self.color_manager.background.getRgb()),
        )
        dialog = FillDialog(defaults, self, editing=False)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            layer = document.add_fill_layer(dialog.properties)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể tạo layer tô", str(exc))
            return
        self._show_transient_message(
            f"Đã thêm layer tô '{layer.name}' (nhấp đôi để sửa, Ctrl+Z để hoàn tác)."
        )

    def _on_edit_fill(self, layer_id: str | None = None) -> None:
        document = self.current_document
        if document is None:
            return
        layer = document.layers.get(layer_id) if layer_id else document.active_layer
        if layer is None or layer.kind != LayerKind.FILL or layer.fill_props is None:
            self._show_transient_message("Hãy chọn một layer tô để sửa.")
            return
        dialog = FillDialog(layer.fill_props, self, editing=True)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.update_fill_layer(dialog.properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể sửa layer tô", str(exc))
            return
        if changed:
            self._show_transient_message(
                "Đã cập nhật layer tô (Ctrl+Z để hoàn tác)."
            )

    def _on_rasterize_fill(self) -> None:
        document = self.current_document
        if document is None:
            return
        if document.rasterize_fill_layer():
            self._show_transient_message(
                "Đã rasterize layer tô thành pixel (Ctrl+Z để hoàn tác)."
            )

    def _choose_smart_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn ảnh cho smart object",
            self.settings.resolved_last_directory(),
            IMAGE_OPEN_FILTER,
        )
        if not path:
            return None
        try:
            source = load_image_rgba(path)
        except ImageImportError as exc:
            QMessageBox.critical(self, "Không thể đọc ảnh", str(exc))
            return None
        return Path(path), source

    def _on_place_smart_object(self) -> None:
        document = self.current_document
        if document is None:
            return
        chosen = self._choose_smart_source()
        if chosen is None:
            return
        path, source = chosen
        height, width = source.shape[:2]
        properties = SmartObjectProperties(
            source_name=path.name,
            source_width=width,
            source_height=height,
        )
        try:
            layer = document.add_smart_object_layer(
                source, properties, name=path.stem
            )
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể đặt smart object", str(exc))
            return
        self._show_transient_message(
            f"Đã đặt smart object '{layer.name}' — xoay/lật/đổi tỉ lệ vẫn giữ "
            "chất lượng ảnh gốc (nhấp đôi để biến đổi)."
        )

    def _smart_layer(self, layer_id: str | None = None) -> bool:
        document = self.current_document
        if document is None:
            return False
        layer = document.layers.get(layer_id) if layer_id else document.active_layer
        if layer is None or layer.kind != LayerKind.SMART or layer.smart_props is None:
            self._show_transient_message("Hãy chọn một smart object.")
            return False
        if layer.mask is not None:
            self._show_transient_message(
                "Smart object đang có mask — hãy áp hoặc xoá mask trước khi "
                "biến đổi/thay nội dung."
            )
            return False
        return True

    def _on_edit_smart_object(self, layer_id: str | None = None) -> None:
        document = self.current_document
        if document is None or not self._smart_layer(layer_id):
            return
        layer = document.layers.get(layer_id) if layer_id else document.active_layer
        if layer is None or layer.smart_source is None or layer.smart_props is None:
            return
        dialog = SmartObjectDialog(layer.smart_source, layer.smart_props, self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.update_smart_object(dialog.properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể biến đổi smart object", str(exc))
            return
        if changed:
            self._show_transient_message(
                "Đã cập nhật smart object từ ảnh gốc (Ctrl+Z để hoàn tác)."
            )

    def _on_replace_smart_contents(self, layer_id: str | None = None) -> None:
        document = self.current_document
        if document is None or not self._smart_layer(layer_id):
            return
        layer = document.layers.get(layer_id) if layer_id else document.active_layer
        if layer is None:
            return
        chosen = self._choose_smart_source()
        if chosen is None:
            return
        path, source = chosen
        try:
            changed = document.replace_smart_contents(
                source, layer, name=path.name
            )
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể thay nội dung", str(exc))
            return
        if changed:
            self._show_transient_message(
                f"Đã thay nội dung smart object bằng '{path.name}' "
                "(giữ nguyên góc/tỉ lệ)."
            )

    def _on_reset_smart_object(self, layer_id: str | None = None) -> None:
        document = self.current_document
        if document is None or not self._smart_layer(layer_id):
            return
        try:
            changed = document.reset_smart_object(
                document.layers.get(layer_id) if layer_id else None
            )
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể đặt lại", str(exc))
            return
        if changed:
            self._show_transient_message(
                "Đã đặt smart object về ảnh gốc (Ctrl+Z để hoàn tác)."
            )

    def _on_rasterize_smart(self) -> None:
        document = self.current_document
        if document is None:
            return
        if document.rasterize_smart_layer():
            self._show_transient_message(
                "Đã rasterize smart object thành pixel thường "
                "(Ctrl+Z để hoàn tác)."
            )

    # --------------------------------------------------- layer điều chỉnh
    def _adjustment_preview_source(self, layer=None):
        """Ảnh ghép của các layer nằm dưới layer điều chỉnh (để xem trước)."""
        document = self.current_document
        if document is None:
            return None
        layers = list(document.layers)
        if layer is not None:
            index = document.layers.index_of(layer)
            layers = layers[:index]
        if not layers:
            return None
        composite = composite_layers(layers, document.width, document.height)
        return downsample_rgba(composite, 420)

    def _on_new_adjustment_layer(self, kind: str) -> None:
        document = self.current_document
        if document is None:
            return
        try:
            properties = AdjustmentProperties(kind=kind)
        except ValueError as exc:
            QMessageBox.critical(self, "Loại điều chỉnh không hợp lệ", str(exc))
            return
        dialog = AdjustmentLayerDialog(
            properties,
            self,
            preview=self._adjustment_preview_source(),
            preset_store=self.preset_store,
        )
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            layer = document.add_adjustment_layer(dialog.properties)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể tạo layer điều chỉnh", str(exc))
            return
        self._show_transient_message(
            f"Đã thêm layer điều chỉnh '{layer.name}' "
            "(nhấp đôi layer để sửa, Ctrl+Z để hoàn tác)."
        )

    def _on_edit_adjustment(self, layer_id: str | None = None) -> None:
        document = self.current_document
        if document is None:
            return
        layer = document.layers.get(layer_id) if layer_id else document.active_layer
        if (
            layer is None
            or layer.kind != LayerKind.ADJUSTMENT
            or layer.adjustment is None
        ):
            self._show_transient_message("Hãy chọn một layer điều chỉnh để sửa.")
            return
        mask = layer.mask if layer.mask is not None and layer.mask_enabled else None
        dialog = AdjustmentLayerDialog(
            layer.adjustment,
            self,
            preview=self._adjustment_preview_source(layer),
            mask=mask,
            editing=True,
            preset_store=self.preset_store,
        )
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.update_adjustment_layer(dialog.properties, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể sửa layer điều chỉnh", str(exc))
            return
        if changed:
            self._show_transient_message(
                "Đã cập nhật layer điều chỉnh (Ctrl+Z để hoàn tác)."
            )

    # ------------------------------------------------------------ bộ lọc
    def _filter_target(self):
        document = self.current_document
        if document is None:
            return None, None
        layer = document.active_layer
        if layer is None:
            self._show_transient_message("Hãy chọn một layer trước khi áp dụng bộ lọc.")
            return None, None
        if layer.locked:
            self._show_transient_message(f"Layer '{layer.name}' đang bị khoá.")
            return None, None
        return document, layer

    def _apply_filter_result(self, document, layer, pixels, label: str) -> None:
        try:
            changed = document.apply_layer_filter(pixels, label, layer)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể áp dụng bộ lọc", str(exc))
            return
        if changed:
            self._show_transient_message(
                f"Đã áp dụng {label} cho layer '{layer.name}' (Ctrl+Z để hoàn tác)."
            )
        else:
            self._show_transient_message("Bộ lọc không tạo ra thay đổi.")

    def _apply_simple_filter(self, function, label: str) -> None:
        document, layer = self._filter_target()
        if layer is None:
            return
        try:
            pixels = function(layer.pixels)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể áp dụng bộ lọc", str(exc))
            return
        self._apply_filter_result(document, layer, pixels, label)

    def _run_filter_dialog(self, dialog_class) -> None:
        document, layer = self._filter_target()
        if layer is None:
            return
        dialog = dialog_class(layer, self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            pixels = dialog.filtered_pixels()
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể áp dụng bộ lọc", str(exc))
            return
        self._apply_filter_result(document, layer, pixels, dialog.label)

    def _on_filter_brightness_contrast(self) -> None:
        self._run_filter_dialog(BrightnessContrastDialog)

    def _on_filter_hue_saturation(self) -> None:
        self._run_filter_dialog(HueSaturationDialog)

    def _on_filter_gaussian_blur(self) -> None:
        self._run_filter_dialog(GaussianBlurDialog)

    def _on_filter_unsharp_mask(self) -> None:
        self._run_filter_dialog(UnsharpMaskDialog)

    # ------------------------------------------------------------ crop / size
    def _on_crop_tool(self) -> None:
        view = self.current_view
        if view is not None:
            view.set_tool("crop")

    def _on_crop_to_selection(self) -> None:
        document = self.current_document
        if document is None or not document.has_selection():
            self._show_transient_message("Chưa có vùng chọn để crop.")
            return
        try:
            changed = document.crop_to_selection()
        except ValueError as exc:
            QMessageBox.critical(self, "Không thể crop", str(exc))
            return
        if changed:
            view = self.current_view
            if view is not None:
                view.fit_to_window()
            self._show_transient_message("Đã crop theo vùng chọn (Ctrl+Z để hoàn tác).")

    def _on_image_size(self) -> None:
        document = self.current_document
        if document is None:
            return
        dialog = ImageSizeDialog(document, self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.resize_image(
                dialog.image_width, dialog.image_height, dialog.method
            )
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể đổi kích thước ảnh", str(exc))
            return
        if changed:
            view = self.current_view
            if view is not None:
                view.fit_to_window()
            self._show_transient_message(
                f"Đã đổi kích thước ảnh thành {document.width} × {document.height} px."
            )

    def _on_canvas_size(self) -> None:
        document = self.current_document
        if document is None:
            return
        dialog = CanvasSizeDialog(document, self)
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = document.canvas_size(
                dialog.canvas_width, dialog.canvas_height, dialog.anchor
            )
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể đổi Canvas Size", str(exc))
            return
        if changed:
            view = self.current_view
            if view is not None:
                view.fit_to_window()
            self._show_transient_message(
                f"Đã đổi canvas thành {document.width} × {document.height} px."
            )

    # ------------------------------------------------------- xoay / lật
    def _on_rotate_canvas(self, direction: str) -> None:
        document = self.current_document
        if document is None:
            return
        try:
            changed = document.rotate_canvas(direction)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể xoay canvas", str(exc))
            return
        if not changed:
            return
        view = self.current_view
        if view is not None:
            view.clear_crop_rect()
            view.fit_to_window()
        labels = {
            "cw": "90° theo chiều kim đồng hồ",
            "ccw": "90° ngược chiều kim đồng hồ",
            "180": "180°",
        }
        self._show_transient_message(
            f"Đã xoay canvas {labels[direction]} (Ctrl+Z để hoàn tác)."
        )

    def _on_flip_canvas(self, horizontal: bool) -> None:
        document = self.current_document
        if document is None:
            return
        try:
            changed = document.flip_canvas(horizontal)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể lật canvas", str(exc))
            return
        if not changed:
            return
        view = self.current_view
        if view is not None:
            view.clear_crop_rect()
        direction = "ngang" if horizontal else "dọc"
        self._show_transient_message(
            f"Đã lật canvas theo chiều {direction} (Ctrl+Z để hoàn tác)."
        )

    def _on_transform_layer(self, operation: str) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            self._show_transient_message("Hãy chọn một layer trước khi xoay/lật.")
            return
        try:
            changed = document.transform_layer(operation)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể biến đổi layer", str(exc))
            return
        if not changed:
            return
        messages = {
            "rotate_cw": "Đã xoay layer 90° theo chiều kim đồng hồ.",
            "rotate_ccw": "Đã xoay layer 90° ngược chiều kim đồng hồ.",
            "rotate_180": "Đã xoay layer 180°.",
            "flip_h": "Đã lật layer theo chiều ngang.",
            "flip_v": "Đã lật layer theo chiều dọc.",
        }
        self._show_transient_message(
            f"{messages[operation]} (Ctrl+Z để hoàn tác)."
        )

    def _on_rotate_canvas_arbitrary(self) -> None:
        document = self.current_document
        if document is None:
            return
        dialog = RotateDialog(
            document.width, document.height, subject="canvas", parent=self
        )
        dialog.setWindowTitle("Xoay canvas tự do")
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        angle = dialog.angle
        try:
            changed = document.rotate_canvas_arbitrary(angle, dialog.method)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể xoay canvas", str(exc))
            return
        if not changed:
            return
        view = self.current_view
        if view is not None:
            view.clear_crop_rect()
            view.fit_to_window()
        self._show_transient_message(
            f"Đã xoay canvas {angle:g}° · kích thước mới "
            f"{document.width} × {document.height} px (Ctrl+Z để hoàn tác)."
        )

    def _on_rotate_layer_arbitrary(self) -> None:
        document = self.current_document
        if document is None or document.active_layer is None:
            self._show_transient_message("Hãy chọn một layer trước khi xoay.")
            return
        layer = document.active_layer
        dialog = RotateDialog(
            layer.width, layer.height, subject="layer", parent=self
        )
        dialog.setWindowTitle(f"Xoay layer tự do — {layer.name}")
        if exec_object(dialog) != QDialog.DialogCode.Accepted:
            return
        angle = dialog.angle
        try:
            changed = document.rotate_layer_arbitrary(angle, layer, dialog.method)
        except (ValueError, MemoryError) as exc:
            QMessageBox.critical(self, "Không thể xoay layer", str(exc))
            return
        if not changed:
            return
        self._show_transient_message(
            f"Đã xoay layer {angle:g}° · kích thước layer mới "
            f"{layer.width} × {layer.height} px (Ctrl+Z để hoàn tác)."
        )

    # ------------------------------------------------------------------ zoom
    def _on_zoom_in(self) -> None:
        if self.current_view:
            self.current_view.zoom_in()

    def _on_zoom_out(self) -> None:
        if self.current_view:
            self.current_view.zoom_out()

    def _on_fit(self) -> None:
        if self.current_view:
            self.current_view.fit_to_window()

    def _on_actual(self) -> None:
        if self.current_view:
            self.current_view.zoom_actual()

    def _on_status_zoom_requested(self, zoom: float) -> None:
        if self.current_view:
            self.current_view.set_zoom(zoom)

    # ------------------------------------------------------------------ theme
    def _set_theme(self, name: str) -> None:
        self.settings_store.set_theme(name)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, name)
        icons.clear_cache()
        self.toolbox.refresh_theme()
        self.options_bar.refresh_theme()
        self.layers_panel.refresh_theme()
        self.tabs.refresh_theme()
        self.welcome.refresh_theme()
        for view in self.tabs.views():
            view.refresh_theme()
        self.action_theme_dark.setChecked(name == THEME_DARK)
        self.action_theme_light.setChecked(name == THEME_LIGHT)
        self._show_transient_message(
            "Đã chuyển sang theme Sáng." if name == THEME_LIGHT else "Đã chuyển sang theme Tối."
        )

    # -------------------------------------------------------------- điều hướng
    def _cycle_document(self, step: int) -> None:
        count = self.tabs.count()
        if count <= 1:
            return
        index = (self.tabs.currentIndex() + step) % count
        self.tabs.setCurrentIndex(index)

    # ---------------------------------------------------------------- help
    def _on_shortcuts(self) -> None:
        rows = [
            ("Tạo tài liệu", "Ctrl+N"),
            ("Mở file", "Ctrl+O"),
            ("Lưu dự án", "Ctrl+S"),
            ("Lưu thành dự án mới", "Ctrl+Shift+S"),
            ("Xuất ảnh", "Ctrl+Alt+S"),
            ("Đóng tài liệu", "Ctrl+W"),
            ("Undo / Redo", "Ctrl+Z / Ctrl+Shift+Z"),
            ("Chọn toàn bộ / Bỏ chọn", "Ctrl+A / Ctrl+D"),
            ("Đảo vùng chọn", "Ctrl+Shift+I"),
            ("Feather vùng chọn", "Shift+F6 (hoặc ô Feather trên Options Bar)"),
            ("Lasso / Magic Wand / Quick Selection", "L / W / Shift+W (khi canvas đang focus)"),
            ("Quick Mask", "Q (khi canvas đang focus, cần có vùng chọn)"),
            ("Tạo / Áp dụng crop", "C, rồi Enter (Esc để huỷ)"),
            ("Crop theo vùng chọn", "Menu Image ▸ Crop to Selection"),
            ("Image Size / Canvas Size", "Ctrl+Alt+I / Ctrl+Alt+C"),
            ("Xoay canvas 90° / 180°", "Menu Image ▸ Image Rotation"),
            ("Xoay canvas tự do", "Menu Image ▸ Image Rotation ▸ Arbitrary Rotation…"),
            ("Lật canvas", "Menu Image ▸ Flip Canvas Horizontal/Vertical"),
            ("Xoay/lật layer đang chọn", "Menu Edit ▸ Transform"),
            ("Xoay layer tự do", "Menu Edit ▸ Transform ▸ Rotate…"),
            ("Hue/Saturation", "Ctrl+U"),
            ("Đảo màu (Invert)", "Ctrl+I"),
            ("Bỏ màu (Desaturate)", "Ctrl+Shift+U"),
            ("Brightness/Contrast, Auto Contrast", "Menu Filter ▸ Adjustments"),
            (
                "Layer điều chỉnh (Brightness/Contrast, Hue/Saturation, Invert, "
                "Desaturate, Levels, Curves, Color Balance)",
                "Menu Layer ▸ New Adjustment Layer",
            ),
            ("Sửa layer điều chỉnh", "Nhấp đôi layer, hoặc Layer ▸ Edit Adjustment…"),
            ("Gaussian Blur / Unsharp Mask", "Menu Filter ▸ Blur / Sharpen"),
            ("Cọ vẽ / Tẩy", "B / Shift+E (khi canvas đang focus)"),
            ("Gradient", "G (khi canvas đang focus)"),
            ("Vẽ lên layer mask", "Menu Layer ▸ Layer Mask ▸ Paint on Layer Mask"),
            ("Layer mới", "Ctrl+Shift+N"),
            ("Tạo layer văn bản", "Ctrl+Shift+T"),
            ("Sửa / Rasterize văn bản", "Menu Type"),
            ("Nhân bản layer", "Ctrl+J"),
            ("Đổi tên layer", "F2"),
            ("Merge Down / Flatten", "Ctrl+E / Ctrl+Shift+E"),
            ("Zoom In / Out", "Ctrl+= / Ctrl+-"),
            ("Fit / 100%", "Ctrl+0 / Ctrl+1"),
            ("Chuyển tài liệu", "Ctrl+Tab / Ctrl+Shift+Tab"),
            ("Di chuyển khung nhìn", "Space + kéo, hoặc chuột giữa"),
            ("Zoom tại con trỏ", "Lăn chuột"),
            ("Pan ngang", "Shift + lăn chuột"),
            (
                "Công cụ Move / Rect / Ellipse / Lasso / Wand / Quick Select / Crop / "
                "Text / Shape / Brush / Gradient / Hand / Zoom",
                "V / M / E / L / W / Shift+W / C / T / U / B / G / H / Z",
            ),
        ]
        table = "<table cellspacing='6' cellpadding='2'>"
        for name, shortcut in rows:
            table += f"<tr><td>{name}</td><td><b>{shortcut}</b></td></tr>"
        table += "</table>"
        QMessageBox.information(self, "Phím tắt", table)

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"Về {APP_NAME}",
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>Ứng dụng chỉnh sửa ảnh và thiết kế đồ họa độc lập, xử lý hoàn toàn cục bộ.</p>"
            "<p><b>Giai đoạn 1:</b> Core Application — quản lý tài liệu, layer, lịch sử, "
            "canvas zoom/pan, lưu dự án .mps.</p>"
            "<p><b>Giai đoạn 2:</b> Vùng chọn chữ nhật/ellipse, layer mask, crop, "
            "Image Size và Canvas Size; mask được lưu từ định dạng .mps v2.</p>"
            "<p><b>Giai đoạn 3:</b> Xoay canvas/layer 90°, 180° và góc tự do, "
            "lật ngang/dọc, có Undo/Redo.</p>"
            "<p><b>Giai đoạn 4:</b> Layer văn bản với font, cỡ, màu, đậm/nghiêng và "
            "căn lề; sửa lại nội dung, rasterize khi cần; lưu trong dự án .mps v3.</p>"
            "<p><b>Giai đoạn 5:</b> Bộ lọc Brightness/Contrast, Hue/Saturation, "
            "Auto Contrast, Invert, Desaturate, Gaussian Blur và Unsharp Mask; "
            "xem trước, áp dụng theo vùng chọn và Undo/Redo.</p>"
            "<p><b>Giai đoạn 6:</b> Layer hình khối vector, công cụ Cọ/Tẩy và Gradient, "
            "vẽ trực tiếp lên layer mask; feather và anti-alias cho vùng chọn; Lasso, "
            "Magic Wand, Quick Selection và Quick Mask; giãn dòng, giãn chữ và định "
            "dạng font/cỡ/màu/đậm/nghiêng theo từng đoạn trong một layer văn bản; "
            "uốn chữ theo các kiểu cung, vòm, sóng, phồng, xoắn… với độ uốn tùy chỉnh; "
            "gõ chữ trực tiếp trên canvas; layer điều chỉnh không phá huỷ "
            "(Brightness/Contrast, Hue/Saturation, Invert, Desaturate); dự án .mps v4.</p>"
            "<p>Công nghệ: Python, PySide6, NumPy, Pillow, SQLite (dự kiến cho preset/actions).</p>"
            "<p>™ và logo Adobe Photoshop thuộc Adobe Inc. Sản phẩm này không liên quan và "
            "không sao chép tài sản độc quyền của Adobe.</p>",
        )

    # ------------------------------------------------------------------ recent
    def _refresh_recent_ui(self) -> None:
        self._rebuild_recent_menu()
        self.welcome.set_recent_files(self.settings.recent_files)

    def _rebuild_recent_menu(self) -> None:
        menu = getattr(self, "menu_open_recent", None)
        if menu is None:
            return
        menu.clear()
        if not self.settings.recent_files:
            placeholder = menu.addAction("Chưa có file nào")
            placeholder.setEnabled(False)
            return
        for raw_path in self.settings.recent_files:
            path = Path(raw_path)
            action = menu.addAction(path.name)
            action.setToolTip(raw_path)
            action.triggered.connect(
                lambda checked=False, target=raw_path: self.open_paths([target])
            )
        menu.addSeparator()
        clear_action = menu.addAction("Xoá danh sách")
        clear_action.triggered.connect(self._clear_recent)

    def _clear_recent(self) -> None:
        self.settings.recent_files = []
        self.settings_store.save()
        self._refresh_recent_ui()

    # --------------------------------------------------------------- window state
    def _restore_window_state(self) -> None:
        try:
            if self.settings.window_geometry:
                geometry = QByteArray.fromBase64(self.settings.window_geometry.encode("ascii"))
                if not geometry.isEmpty():
                    self.restoreGeometry(geometry)
            if self.settings.window_state:
                state = QByteArray.fromBase64(self.settings.window_state.encode("ascii"))
                if not state.isEmpty():
                    self.restoreState(state)
        except (ValueError, TypeError):
            logger.warning("Không khôi phục được trạng thái cửa sổ.", exc_info=True)

    def _store_window_state(self) -> None:
        try:
            self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.settings.window_state = bytes(self.saveState().toBase64()).decode("ascii")
        except (ValueError, TypeError):
            logger.warning("Không lưu được trạng thái cửa sổ.", exc_info=True)
        self.settings_store.save()

    def closeEvent(self, event) -> None:  # noqa: N802
        for view in list(self.tabs.views()):
            if not self._confirm_close_document(view.document):
                event.ignore()
                return
        self._store_window_state()
        event.accept()
