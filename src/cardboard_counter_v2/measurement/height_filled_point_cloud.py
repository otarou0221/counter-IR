"""採用済み高さグリッドを表示専用の充填点群へ変換する。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.height_palette import height_colors


DEFAULT_VERTICAL_STEP_MM = 20.0
DEFAULT_MAXIMUM_POINTS = 1_000_000


@dataclass(frozen=True)
class HeightFilledPointCloud:
    """パレット面からセル上面までを埋めた、高さ色付き表示用点群。"""

    uvh: np.ndarray
    colors_rgb: np.ndarray
    vertical_step_mm: float
    maximum_height_mm: float


@dataclass(frozen=True)
class HeightFilledGeometry:
    """色付けに依存しない、セル中心を縦方向へ充填した座標と元セル番号。"""

    uvh: np.ndarray
    source_rows: np.ndarray
    source_columns: np.ndarray
    vertical_step_mm: float
    maximum_height_mm: float


def build_height_filled_point_cloud(
    height_grid: np.ndarray,
    box_region: np.ndarray,
    geometry: PalletProjectionGeometry,
    *,
    vertical_step_mm: float = DEFAULT_VERTICAL_STEP_MM,
    maximum_points: int = DEFAULT_MAXIMUM_POINTS,
) -> HeightFilledPointCloud:
    """採用セルだけをパレット面から上面まで埋め、高さに応じたRGBを付ける。"""
    filled = build_height_filled_geometry(
        height_grid,
        box_region,
        geometry,
        vertical_step_mm=vertical_step_mm,
        maximum_points=maximum_points,
    )
    colors = height_colors(
        filled.uvh[:, 2],
        maximum_height_mm=filled.maximum_height_mm,
    )
    return HeightFilledPointCloud(
        uvh=filled.uvh,
        colors_rgb=colors,
        vertical_step_mm=filled.vertical_step_mm,
        maximum_height_mm=filled.maximum_height_mm,
    )


def build_height_filled_geometry(
    height_grid: np.ndarray,
    region_mask: np.ndarray,
    geometry: PalletProjectionGeometry,
    *,
    vertical_step_mm: float = DEFAULT_VERTICAL_STEP_MM,
    maximum_points: int = DEFAULT_MAXIMUM_POINTS,
) -> HeightFilledGeometry:
    """採用セル中心をパレット面から上面まで埋め、各点の元セル番号も返す。"""
    heights = np.asarray(height_grid, dtype=np.float32)
    region = np.asarray(region_mask, dtype=bool)
    if heights.shape != region.shape or heights.shape != geometry.pallet_mask.shape:
        raise ValueError("高さグリッド、箱領域、パレット形状が一致しません")
    step = max(float(vertical_step_mm), 1.0)
    point_limit = max(int(maximum_points), 1)
    active = region & geometry.pallet_mask & np.isfinite(heights) & (heights > 0)
    rows, columns = np.nonzero(active)
    if len(rows) == 0:
        return HeightFilledGeometry(
            uvh=np.empty((0, 3), dtype=np.float32),
            source_rows=np.empty(0, dtype=np.int32),
            source_columns=np.empty(0, dtype=np.int32),
            vertical_step_mm=step,
            maximum_height_mm=0.0,
        )

    cell_heights = heights[rows, columns].astype(np.float64)
    estimated_count = int(np.sum(np.floor(cell_heights / step).astype(np.int64) + 2))
    if estimated_count > point_limit:
        step *= int(np.ceil(estimated_count / point_limit))

    points: list[np.ndarray] = []
    point_rows: list[np.ndarray] = []
    point_columns: list[np.ndarray] = []
    for row, column, top in zip(rows, columns, cell_heights, strict=True):
        levels = np.arange(0.0, top, step, dtype=np.float32)
        # 上面は刻みと一致しない場合も必ず含める。
        levels = np.append(levels, np.float32(top))
        u = geometry.minimum_u + (float(column) + 0.5) * geometry.cell_size_mm
        v = geometry.minimum_v + (float(row) + 0.5) * geometry.cell_size_mm
        points.append(
            np.column_stack(
                (
                    np.full(len(levels), u, dtype=np.float32),
                    np.full(len(levels), v, dtype=np.float32),
                    levels,
                )
            )
        )
        point_rows.append(np.full(len(levels), row, dtype=np.int32))
        point_columns.append(np.full(len(levels), column, dtype=np.int32))
    uvh = np.concatenate(points, axis=0)
    maximum_height = float(np.max(cell_heights))
    return HeightFilledGeometry(
        uvh=uvh,
        source_rows=np.concatenate(point_rows),
        source_columns=np.concatenate(point_columns),
        vertical_step_mm=step,
        maximum_height_mm=maximum_height,
    )
