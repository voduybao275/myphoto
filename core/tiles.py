"""Tile cache: hợp nhất từng ô 256 px theo nhu cầu để xem ảnh lớn.

CanvasView chỉ vẽ các ô giao với vùng nhìn thấy. Ô đã dựng được giữ trong
cache LRU có giới hạn, nên bộ nhớ không tăng theo kích thước ảnh. Khi nội dung
đổi, Document ghi lại vùng bẩn; cache chỉ bỏ những ô giao với vùng đó.
"""

from __future__ import annotations

from collections import OrderedDict

import compat.qt  # noqa: F401  - chọn binding Qt trước mọi import PySide6
from PySide6.QtGui import QImage

from core.canvas import composite_region, numpy_rgba_to_qimage
from core.document import Document

TILE_SIZE = 256
MAX_CACHED_TILES = 96


class TileCache:
    """Cache QImage theo ô vuông, dựng lười bằng ``composite_region``."""

    def __init__(
        self,
        document: Document,
        *,
        tile_size: int = TILE_SIZE,
        max_tiles: int = MAX_CACHED_TILES,
    ) -> None:
        if tile_size < 16:
            raise ValueError("Kích thước tile phải >= 16 px.")
        if max_tiles < 1:
            raise ValueError("Số tile cache phải >= 1.")
        self.document = document
        self.tile_size = int(tile_size)
        self.max_tiles = int(max_tiles)
        self._tiles: OrderedDict[tuple[int, int], QImage] = OrderedDict()
        self._seen_revision = document.revision
        self.hits = 0
        self.misses = 0
        self.composites = 0

    # ------------------------------------------------------------------ trạng thái
    @property
    def count(self) -> int:
        return len(self._tiles)

    def cached_keys(self) -> list[tuple[int, int]]:
        return list(self._tiles)

    def clear(self) -> None:
        self._tiles.clear()

    def sync(self) -> None:
        """Áp các vùng bẩn kể từ lần đồng bộ trước."""
        changes = self.document.changes_since(self._seen_revision)
        if changes is None:
            self._tiles.clear()
        else:
            for rect in changes:
                self._drop_rect(rect)
        self._seen_revision = self.document.revision

    def _drop_rect(self, rect: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = rect
        if x1 <= x0 or y1 <= y0:
            return
        size = self.tile_size
        tx0 = x0 // size
        ty0 = y0 // size
        tx1 = (x1 - 1) // size
        ty1 = (y1 - 1) // size
        stale = [
            key
            for key in self._tiles
            if tx0 <= key[0] <= tx1 and ty0 <= key[1] <= ty1
        ]
        for key in stale:
            del self._tiles[key]

    # ------------------------------------------------------------------ dựng tile
    def tile(self, tx: int, ty: int) -> QImage:
        """Trả QImage của ô (tx, ty), dựng và cache nếu chưa có."""
        self.sync()
        key = (int(tx), int(ty))
        image = self._tiles.get(key)
        if image is not None:
            self.hits += 1
            self._tiles.move_to_end(key)
            return image

        self.misses += 1
        size = self.tile_size
        x0 = key[0] * size
        y0 = key[1] * size
        x1 = min(self.document.width, x0 + size)
        y1 = min(self.document.height, y0 + size)
        if key[0] < 0 or key[1] < 0 or x1 <= x0 or y1 <= y0:
            raise ValueError(f"Tile ngoài tài liệu: {key}.")

        array = composite_region(
            self.document.layers.layers,
            self.document.width,
            self.document.height,
            x0,
            y0,
            x1,
            y1,
        )
        image = numpy_rgba_to_qimage(array)
        self.composites += 1
        self._tiles[key] = image
        while len(self._tiles) > self.max_tiles:
            self._tiles.popitem(last=False)
        return image

    def tiles_for_rect(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> list[tuple[int, int]]:
        """Các ô giao với vùng tài liệu cho trước (đã kẹp theo tài liệu)."""
        size = self.tile_size
        left = max(0, int(x0 // size))
        top = max(0, int(y0 // size))
        right = min((self.document.width - 1) // size, int((x1 - 1) // size))
        bottom = min((self.document.height - 1) // size, int((y1 - 1) // size))
        if right < left or bottom < top:
            return []
        return [
            (tx, ty)
            for ty in range(top, bottom + 1)
            for tx in range(left, right + 1)
        ]
