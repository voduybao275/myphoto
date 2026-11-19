"""Kiểm thử lõi Magic Wand: flood fill và chuyển mask thành đường bao."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtGui import QPainterPath

from core.selection import Selection
from core.wand import (
    color_eligibility,
    flood_fill_eligible,
    flood_fill_mask,
    layer_sample,
    mask_to_path,
)


def two_color_sample(width=12, height=8):
    sample = np.zeros((height, width, 4), dtype=np.uint8)
    sample[:, : width // 2] = (220, 30, 30, 255)
    sample[:, width // 2 :] = (30, 30, 220, 255)
    return sample


def test_layer_sample_places_pixels_and_keeps_outside_transparent():
    pixels = np.full((4, 6, 4), 9, dtype=np.uint8)
    sample = layer_sample(pixels, 3, 5, 12, 10)
    assert sample.shape == (10, 12, 4)
    assert tuple(sample[5, 3]) == (9, 9, 9, 9)
    assert tuple(sample[8, 8]) == (9, 9, 9, 9)
    assert tuple(sample[4, 3]) == (0, 0, 0, 0)
    assert tuple(sample[5, 2]) == (0, 0, 0, 0)


def test_layer_sample_clips_layer_to_document():
    pixels = np.full((10, 10, 4), 200, dtype=np.uint8)
    sample = layer_sample(pixels, -4, -3, 5, 4)
    assert sample.shape == (4, 5, 4)
    assert (sample == 200).all()


def test_flood_fill_selects_only_connected_region():
    sample = two_color_sample()
    mask = flood_fill_mask(sample, 1, 1, 0)
    assert mask.shape == (8, 12)
    assert mask[:, :6].all()
    assert not mask[:, 6:].any()


def test_flood_fill_global_mode_selects_all_matching_pixels():
    sample = two_color_sample()
    sample[0:2, 8:12] = (220, 30, 30, 255)
    mask = flood_fill_mask(sample, 1, 1, 0, contiguous=False)
    assert mask[:, :6].all()
    assert mask[0:2, 8:12].all()
    assert not mask[2:, 6:].any()


def test_flood_fill_tolerance_includes_near_colors():
    sample = np.zeros((4, 6, 4), dtype=np.uint8)
    sample[:, :3] = (100, 100, 100, 255)
    sample[:, 3:] = (120, 100, 100, 255)
    strict = flood_fill_mask(sample, 0, 0, 5)
    assert strict[:, :3].all()
    assert not strict[:, 3:].any()

    loose = flood_fill_mask(sample, 0, 0, 25)
    assert loose.all()


def test_flood_fill_tolerance_compares_alpha_channel():
    sample = np.zeros((3, 4, 4), dtype=np.uint8)
    sample[:, :, :3] = 255
    sample[:, :2, 3] = 255
    mask = flood_fill_mask(sample, 0, 0, 0)
    assert mask[:, :2].all()
    assert not mask[:, 2:].any()


def test_flood_fill_outside_seed_raises():
    sample = two_color_sample()
    with pytest.raises(ValueError):
        flood_fill_mask(sample, -1, 0, 0)
    with pytest.raises(ValueError):
        flood_fill_mask(sample, 0, 99, 0)


def test_flood_fill_eligible_with_outside_or_blocked_seed_returns_empty():
    eligible = np.array([[True, False], [True, True]])
    assert not flood_fill_eligible(eligible, -1, 0).any()
    assert not flood_fill_eligible(eligible, 1, 0).any()


def test_color_eligibility_requires_uint8():
    with pytest.raises(ValueError):
        color_eligibility(np.zeros((2, 2, 4), dtype=np.float32), (0, 0, 0, 0), 0)


def test_mask_to_path_empty_and_invalid():
    assert mask_to_path(np.zeros((5, 5), dtype=bool)).isEmpty()
    with pytest.raises(ValueError):
        mask_to_path(np.zeros((5,), dtype=bool))


def test_mask_to_path_roundtrip_rect():
    mask = np.zeros((10, 12), dtype=bool)
    mask[2:8, 3:9] = True
    selection = Selection.from_path(
        12, 10, mask_to_path(mask), antialias=False
    )
    assert selection.bounds().width() == 6
    assert selection.bounds().height() == 6
    assert np.array_equal(selection.mask(), mask.astype(np.uint8) * 255)


def test_mask_to_path_preserves_holes():
    mask = np.zeros((12, 12), dtype=bool)
    mask[2:10, 2:10] = True
    mask[4:8, 4:8] = False
    selection = Selection.from_path(
        12, 12, mask_to_path(mask), antialias=False
    )
    assert np.array_equal(selection.mask(), mask.astype(np.uint8) * 255)
    assert selection.mask()[5, 5] == 0


def test_mask_to_path_handles_diagonal_contact():
    mask = np.zeros((6, 6), dtype=bool)
    mask[1, 1] = True
    mask[2, 2] = True
    selection = Selection.from_path(
        6, 6, mask_to_path(mask), antialias=False
    )
    result = selection.mask()
    assert result[1, 1] == 255
    assert result[2, 2] == 255
    assert int((result == 255).sum()) == 2


def test_selection_from_path_validates_type():
    with pytest.raises(TypeError):
        Selection.from_path(5, 5, "not-a-path")


def test_mask_to_path_accepts_integer_mask():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[1:3, 1:4] = 255
    path = mask_to_path(mask)
    assert isinstance(path, QPainterPath)
    selection = Selection.from_path(5, 4, path, antialias=False)
    assert int((selection.mask() == 255).sum()) == 6
