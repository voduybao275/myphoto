"""Xây dựng Menu Bar của cửa sổ chính."""

from __future__ import annotations

from PySide6.QtWidgets import QMenuBar


def build_menu_bar(window) -> QMenuBar:
    menu_bar = QMenuBar(window)
    menu_bar.setNativeMenuBar(False)

    # ------------------------------------------------------------------- File
    file_menu = menu_bar.addMenu("&File")
    file_menu.addAction(window.action_new)
    file_menu.addAction(window.action_open)
    window.menu_open_recent = file_menu.addMenu("Open Recent")
    file_menu.addSeparator()
    file_menu.addAction(window.action_save)
    file_menu.addAction(window.action_save_as)
    file_menu.addAction(window.action_export)
    file_menu.addSeparator()
    file_menu.addAction(window.action_close)
    file_menu.addAction(window.action_exit)

    # ------------------------------------------------------------------- Edit
    edit_menu = menu_bar.addMenu("&Edit")
    edit_menu.addAction(window.action_undo)
    edit_menu.addAction(window.action_redo)
    edit_menu.addSeparator()
    edit_menu.addAction(window.action_cut)
    edit_menu.addAction(window.action_copy)
    edit_menu.addAction(window.action_copy_merged)
    edit_menu.addAction(window.action_paste)
    edit_menu.addSeparator()
    edit_menu.addAction(window.action_clear)
    edit_menu.addAction(window.action_fill_foreground)
    edit_menu.addAction(window.action_fill_background)
    edit_menu.addSeparator()
    transform_menu = edit_menu.addMenu("Transform")
    transform_menu.addAction(window.action_layer_rotate_cw)
    transform_menu.addAction(window.action_layer_rotate_ccw)
    transform_menu.addAction(window.action_layer_rotate_180)
    transform_menu.addAction(window.action_layer_rotate_arbitrary)
    transform_menu.addSeparator()
    transform_menu.addAction(window.action_layer_flip_h)
    transform_menu.addAction(window.action_layer_flip_v)

    # ------------------------------------------------------------------ Image
    image_menu = menu_bar.addMenu("&Image")
    image_menu.addAction(window.action_crop)
    image_menu.addAction(window.action_crop_selection)
    image_menu.addSeparator()
    image_menu.addAction(window.action_image_size)
    image_menu.addAction(window.action_canvas_size)
    image_menu.addSeparator()
    rotation_menu = image_menu.addMenu("Image Rotation")
    rotation_menu.addAction(window.action_rotate_cw)
    rotation_menu.addAction(window.action_rotate_ccw)
    rotation_menu.addAction(window.action_rotate_180)
    rotation_menu.addAction(window.action_rotate_arbitrary)
    image_menu.addAction(window.action_flip_canvas_h)
    image_menu.addAction(window.action_flip_canvas_v)

    # ------------------------------------------------------------------ Layer
    layer_menu = menu_bar.addMenu("&Layer")
    layer_menu.addAction(window.action_new_layer)
    layer_menu.addAction(window.action_new_group)
    fill_menu = layer_menu.addMenu("New Fill Layer")
    fill_menu.addAction(window.action_new_fill_solid)
    fill_menu.addAction(window.action_new_fill_gradient)
    layer_menu.addAction(window.action_place_smart_object)
    layer_menu.addAction(window.action_group_layers)
    layer_menu.addAction(window.action_ungroup_layers)
    layer_menu.addSeparator()
    layer_menu.addAction(window.action_duplicate_layer)
    layer_menu.addAction(window.action_rename_layer)
    layer_menu.addAction(window.action_lock_layer)
    layer_menu.addAction(window.action_delete_layer)
    layer_menu.addSeparator()
    layer_menu.addAction(window.action_merge_down)
    layer_menu.addAction(window.action_flatten)
    layer_menu.addSeparator()
    shape_menu = layer_menu.addMenu("Shape")
    shape_menu.addAction(window.action_new_shape)
    shape_menu.addAction(window.action_edit_shape)
    shape_menu.addSeparator()
    shape_menu.addAction(window.action_rasterize_shape)
    adjustment_menu = layer_menu.addMenu("New Adjustment Layer")
    adjustment_menu.addAction(window.action_new_adjustment_brightness_contrast)
    adjustment_menu.addAction(window.action_new_adjustment_hue_saturation)
    adjustment_menu.addSeparator()
    adjustment_menu.addAction(window.action_new_adjustment_invert)
    adjustment_menu.addAction(window.action_new_adjustment_desaturate)
    adjustment_menu.addSeparator()
    adjustment_menu.addAction(window.action_new_adjustment_levels)
    adjustment_menu.addAction(window.action_new_adjustment_curves)
    adjustment_menu.addAction(window.action_new_adjustment_color_balance)
    layer_menu.addAction(window.action_edit_adjustment)
    layer_menu.addAction(window.action_edit_fill)
    layer_menu.addAction(window.action_edit_smart_object)
    layer_menu.addAction(window.action_replace_smart_contents)
    layer_menu.addAction(window.action_reset_smart_object)
    layer_menu.addSeparator()
    rasterize_menu = layer_menu.addMenu("Rasterize")
    rasterize_menu.addAction(window.action_rasterize_shape)
    rasterize_menu.addAction(window.action_rasterize_text)
    rasterize_menu.addAction(window.action_rasterize_fill)
    rasterize_menu.addAction(window.action_rasterize_smart)
    layer_menu.addSeparator()
    mask_menu = layer_menu.addMenu("Layer Mask")
    mask_menu.addAction(window.action_add_mask)
    mask_menu.addAction(window.action_remove_mask)
    mask_menu.addAction(window.action_apply_mask)
    mask_menu.addSeparator()
    mask_menu.addAction(window.action_toggle_mask)
    mask_menu.addSeparator()
    mask_menu.addAction(window.action_paint_mask)

    # ------------------------------------------------------------------- Type
    type_menu = menu_bar.addMenu("&Type")
    type_menu.addAction(window.action_new_text)
    type_menu.addAction(window.action_edit_text)
    type_menu.addSeparator()
    type_menu.addAction(window.action_rasterize_text)

    # ----------------------------------------------------------------- Select
    select_menu = menu_bar.addMenu("&Select")
    select_menu.addAction(window.action_select_all)
    select_menu.addAction(window.action_deselect)
    select_menu.addAction(window.action_invert_selection)
    select_menu.addSeparator()
    select_menu.addAction(window.action_feather_selection)

    # ----------------------------------------------------------------- Filter
    filter_menu = menu_bar.addMenu("Fi&lter")
    adjustments_menu = filter_menu.addMenu("Adjustments")
    adjustments_menu.addAction(window.action_filter_brightness_contrast)
    adjustments_menu.addAction(window.action_filter_hue_saturation)
    adjustments_menu.addSeparator()
    adjustments_menu.addAction(window.action_filter_auto_contrast)
    adjustments_menu.addAction(window.action_filter_invert)
    adjustments_menu.addAction(window.action_filter_desaturate)
    filter_menu.addSeparator()
    blur_menu = filter_menu.addMenu("Blur")
    blur_menu.addAction(window.action_filter_gaussian_blur)
    sharpen_menu = filter_menu.addMenu("Sharpen")
    sharpen_menu.addAction(window.action_filter_unsharp_mask)

    # ------------------------------------------------------------- Automation
    automation_menu = menu_bar.addMenu("&Automation")
    automation_menu.addAction(window.action_batch_processing)

    # ------------------------------------------------------------------- View
    view_menu = menu_bar.addMenu("&View")
    view_menu.addAction(window.action_zoom_in)
    view_menu.addAction(window.action_zoom_out)
    view_menu.addAction(window.action_fit)
    view_menu.addAction(window.action_actual)
    view_menu.addSeparator()
    view_menu.addAction(window.action_quick_mask)
    view_menu.addSeparator()
    theme_menu = view_menu.addMenu("Theme")
    theme_menu.addAction(window.action_theme_dark)
    theme_menu.addAction(window.action_theme_light)

    # ----------------------------------------------------------------- Window
    window_menu = menu_bar.addMenu("&Window")
    window.actions_panels = [
        window.toolbox.toggleViewAction(),
        window.options_bar.toggleViewAction(),
        window.dock_layers.toggleViewAction(),
        window.dock_properties.toggleViewAction(),
    ]
    for action in window.actions_panels:
        window_menu.addAction(action)
    window_menu.addSeparator()
    window_menu.addAction(window.action_previous_document)
    window_menu.addAction(window.action_next_document)

    # ------------------------------------------------------------------- Help
    help_menu = menu_bar.addMenu("&Help")
    help_menu.addAction(window.action_shortcuts)
    help_menu.addAction(window.action_about)

    return menu_bar
