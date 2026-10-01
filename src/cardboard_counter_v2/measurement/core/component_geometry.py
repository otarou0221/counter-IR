"""2次元マスク成分の向きに依存しない形状計測。"""

from __future__ import annotations

import cv2
import numpy as np


def oriented_mask_spans(
    mask: np.ndarray,
    *,
    cell_size_mm: float,
) -> tuple[float, float]:
    """有効セルを囲む回転矩形の短辺・長辺をmmで返す。"""
    active = np.asarray(mask, dtype=bool)
    if active.ndim != 2:
        raise ValueError("成分マスクは2次元である必要があります。")
    rows, columns = np.nonzero(active)
    if rows.size == 0:
        return 0.0, 0.0

    cell = float(cell_size_mm)
    if not np.isfinite(cell) or cell <= 0:
        raise ValueError("セル寸法は正の有限値である必要があります。")
    if rows.size == 1:
        return cell, cell

    points = np.column_stack((columns, rows)).astype(np.float32)
    _center, (width_cells, height_cells), _angle = cv2.minAreaRect(points)
    # minAreaRectはセル中心間の距離を返すため、占有セル1個分を加える。
    spans = sorted(
        (
            (float(width_cells) + 1.0) * cell,
            (float(height_cells) + 1.0) * cell,
        )
    )
    return spans[0], spans[1]
