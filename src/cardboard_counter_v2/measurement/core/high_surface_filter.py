"""箱の上面より小さく細い、高所の背景片を見分ける。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import cv2
import numpy as np

from cardboard_counter_v2.measurement.core.component_geometry import oriented_mask_spans


HIGH_SURFACE_START_MM = 1_500.0
BOX_TOP_AREA_RATIO = 0.20
BOX_SHORT_SIDE_RATIO = 0.50


@dataclass(frozen=True)
class HighSurfaceFilter:
    """測定設定が変わるまで再利用する高所背景片の判定基準。"""

    start_height_mm: float
    maximum_area_mm2: float
    maximum_short_span_mm: float

    @classmethod
    def for_box_footprints(
        cls,
        footprints_mm: Iterable[tuple[float, float]],
    ) -> HighSurfaceFilter:
        dimensions = tuple(footprints_mm)
        if not dimensions or any(
            not np.isfinite((width, depth)).all() or width <= 0 or depth <= 0
            for width, depth in dimensions
        ):
            raise ValueError("箱の上面寸法は正の値で1種類以上必要です")
        minimum_area = min(width * depth for width, depth in dimensions)
        minimum_short_side = min(min(width, depth) for width, depth in dimensions)
        return cls(
            start_height_mm=HIGH_SURFACE_START_MM,
            maximum_area_mm2=minimum_area * BOX_TOP_AREA_RATIO,
            maximum_short_span_mm=minimum_short_side * BOX_SHORT_SIDE_RATIO,
        )


def small_high_surface_mask(
    heights: np.ndarray,
    observed: np.ndarray,
    *,
    cell_size_mm: float,
    rule: HighSurfaceFilter,
) -> np.ndarray:
    """高所にあり、面積と短辺の両方が箱より小さい連結領域を返す。"""
    if heights.shape != observed.shape or heights.ndim != 2:
        raise ValueError("高さグリッドと有効セルの形状が一致しません")
    high = observed & (heights > rule.start_height_mm)
    discarded = np.zeros_like(high)
    if not np.any(high):
        return discarded

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        high.astype(np.uint8), connectivity=8,
    )
    for label in range(1, count):
        area_mm2 = float(stats[label, cv2.CC_STAT_AREA]) * cell_size_mm**2
        if area_mm2 >= rule.maximum_area_mm2:
            continue
        component = labels == label
        short_span_mm, _long_span_mm = oriented_mask_spans(
            component, cell_size_mm=cell_size_mm,
        )
        if short_span_mm < rule.maximum_short_span_mm:
            discarded |= component
    return discarded
