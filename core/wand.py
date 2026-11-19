"""Lõi chọn theo màu: flood fill và chuyển mask nhị phân thành QPainterPath.

Magic Wand và Quick Selection làm việc trên mask pixel. Toàn bộ hệ thống vùng
chọn của dự án dùng QPainterPath làm nguồn dữ liệu chính, vì vậy mask được
chuyển thành đường bao kín theo biên pixel rồi mới đưa vào ``Selection``.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath

MAX_TOLERANCE = 255

# Hướng rẽ phải của từng bước đi trên lưới pixel (trục y hướng xuống).
_RIGHT_TURN = {
    (1, 0): (0, 1),
    (0, 1): (-1, 0),
    (-1, 0): (0, -1),
    (0, -1): (1, 0),
}


def clamp_tolerance(value: float) -> int:
    value = int(round(float(value)))
    return max(0, min(MAX_TOLERANCE, value))


def layer_sample(
    pixels: np.ndarray,
    offset_x: int,
    offset_y: int,
    width: int,
    height: int,
) -> np.ndarray:
    """Đặt pixel RGBA của một layer vào khung tài liệu (ngoài layer là trong suốt)."""
    if pixels.ndim != 3 or pixels.shape[2] != 4:
        raise ValueError("Pixel của layer phải có dạng (cao, rộng, 4).")
    if width < 1 or height < 1:
        raise ValueError("Kích thước tài liệu phải >= 1 px.")
    sample = np.zeros((int(height), int(width), 4), dtype=np.uint8)
    layer_height, layer_width = pixels.shape[0], pixels.shape[1]
    x0 = max(0, int(offset_x))
    y0 = max(0, int(offset_y))
    x1 = min(int(width), int(offset_x) + layer_width)
    y1 = min(int(height), int(offset_y) + layer_height)
    if x1 > x0 and y1 > y0:
        sample[y0:y1, x0:x1] = pixels[
            y0 - offset_y : y1 - offset_y,
            x0 - offset_x : x1 - offset_x,
        ]
    return sample


def color_eligibility(
    sample: np.ndarray, color: tuple[int, int, int, int] | np.ndarray, tolerance: int
) -> np.ndarray:
    """Mask bool các pixel có mọi kênh RGBA lệch không quá ``tolerance``."""
    if sample.ndim != 3 or sample.shape[2] != 4:
        raise ValueError("Ảnh mẫu phải có dạng (cao, rộng, 4).")
    if sample.dtype != np.uint8:
        raise ValueError("Ảnh mẫu phải là uint8.")
    tolerance = clamp_tolerance(tolerance)
    seed = np.asarray(color)
    if seed.shape != (4,):
        raise ValueError("Màu mẫu phải có 4 kênh RGBA.")
    seed = seed.astype(np.int16)
    height, width = sample.shape[:2]
    eligible = np.ones((height, width), dtype=bool)
    buffer = np.empty((height, width), dtype=np.int16)
    for channel in range(4):
        np.subtract(sample[..., channel], seed[channel], out=buffer)
        np.abs(buffer, out=buffer)
        eligible &= buffer <= tolerance
    return eligible


def flood_fill_eligible(eligible: np.ndarray, x: int, y: int) -> np.ndarray:
    """Lan vùng liền kề từ (x, y) trên mask bool đã đủ điều kiện."""
    eligible = np.asarray(eligible)
    if eligible.ndim != 2:
        raise ValueError("Mask đủ điều kiện phải là mảng 2 chiều.")
    if eligible.dtype != bool:
        eligible = eligible.astype(bool)
    height, width = eligible.shape
    result = np.zeros((height, width), dtype=bool)
    seed_x, seed_y = int(x), int(y)
    if not (0 <= seed_x < width and 0 <= seed_y < height):
        return result
    if not eligible[seed_y, seed_x]:
        return result

    stack: list[tuple[int, int]] = [(seed_y, seed_x)]

    def push_segments(row_index: int, start: int, stop: int) -> None:
        if row_index < 0 or row_index >= height or stop <= start:
            return
        segment = eligible[row_index, start:stop] & ~result[row_index, start:stop]
        if not segment.any():
            return
        transitions = np.diff(
            np.concatenate(([0], segment.astype(np.int8), [0]))
        )
        for offset in np.flatnonzero(transitions == 1):
            stack.append((row_index, start + int(offset)))

    while stack:
        row_index, start_x = stack.pop()
        if result[row_index, start_x] or not eligible[row_index, start_x]:
            continue
        row = eligible[row_index]
        blocked_left = np.flatnonzero(~row[:start_x])
        left = int(blocked_left[-1]) + 1 if blocked_left.size else 0
        blocked_right = np.flatnonzero(~row[start_x:])
        right = start_x + int(blocked_right[0]) if blocked_right.size else width
        result[row_index, left:right] = True
        push_segments(row_index - 1, left, right)
        push_segments(row_index + 1, left, right)
    return result


def flood_fill_mask(
    sample: np.ndarray,
    x: int,
    y: int,
    tolerance: int = 0,
    *,
    contiguous: bool = True,
) -> np.ndarray:
    """Chọn các pixel giống màu tại (x, y) trong ảnh mẫu RGBA uint8."""
    height, width = sample.shape[:2]
    seed_x, seed_y = int(x), int(y)
    if not (0 <= seed_x < width and 0 <= seed_y < height):
        raise ValueError("Điểm nhấp nằm ngoài tài liệu.")
    eligible = color_eligibility(sample, sample[seed_y, seed_x], tolerance)
    if not contiguous:
        return eligible
    return flood_fill_eligible(eligible, seed_x, seed_y)


def _add_edge(
    edges: dict[tuple[int, int], list[tuple[int, int]]],
    start: tuple[int, int],
    end: tuple[int, int],
) -> None:
    edges.setdefault(start, []).append(end)


def _choose_next(
    previous: tuple[int, int],
    current: tuple[int, int],
    targets: list[tuple[int, int]],
) -> tuple[int, int]:
    if len(targets) == 1:
        return targets[0]
    direction = (current[0] - previous[0], current[1] - previous[1])
    preferred = _RIGHT_TURN.get(direction)
    for target in targets:
        if (target[0] - current[0], target[1] - current[1]) == preferred:
            return target
    return targets[0]


def mask_to_path(mask: np.ndarray) -> QPainterPath:
    """Chuyển mask bool thành đường bao kín theo biên pixel.

    Mỗi pixel được coi là ô vuông đơn vị; các cạnh nằm giữa pixel được chọn và
    không được chọn tạo thành đồ thị có hướng. Đi theo đồ thị (ưu tiên rẽ phải
    tại điểm chéo) tạo ra các vòng kín ngoài và lỗ bên trong.
    """
    selected = np.asarray(mask)
    if selected.ndim != 2:
        raise ValueError("Mask phải là mảng 2 chiều.")
    if selected.dtype != bool:
        selected = selected.astype(bool)
    path = QPainterPath()
    height, width = selected.shape
    if height == 0 or width == 0 or not selected.any():
        return path

    padded = np.pad(selected, 1, mode="constant", constant_values=False)
    core = padded[1:-1, 1:-1]
    top = core & ~padded[:-2, 1:-1]
    bottom = core & ~padded[2:, 1:-1]
    left = core & ~padded[1:-1, :-2]
    right = core & ~padded[1:-1, 2:]
    boundary = top | bottom | left | right

    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    rows, columns = np.nonzero(boundary)
    for y, x in zip(rows.tolist(), columns.tolist()):
        if top[y, x]:
            _add_edge(edges, (x, y), (x + 1, y))
        if right[y, x]:
            _add_edge(edges, (x + 1, y), (x + 1, y + 1))
        if bottom[y, x]:
            _add_edge(edges, (x + 1, y + 1), (x, y + 1))
        if left[y, x]:
            _add_edge(edges, (x, y + 1), (x, y))

    total_edges = sum(len(targets) for targets in edges.values())
    guard_limit = total_edges + 4
    while edges:
        start = next(iter(edges))
        current = start
        previous: tuple[int, int] | None = None
        points: list[tuple[int, int]] = [start]
        guard = 0
        while True:
            targets = edges.get(current)
            if not targets:
                break
            chosen = targets[0] if previous is None else _choose_next(
                previous, current, targets
            )
            targets.remove(chosen)
            if not targets:
                del edges[current]
            previous, current = current, chosen
            if current == start:
                break
            points.append(current)
            guard += 1
            if guard > guard_limit:  # pragma: no cover - bảo vệ đồ thị lỗi
                break
        if len(points) < 3:
            continue
        path.moveTo(float(points[0][0]), float(points[0][1]))
        for px, py in points[1:]:
            path.lineTo(float(px), float(py))
        path.closeSubpath()

    path.setFillRule(Qt.FillRule.WindingFill)
    return path
