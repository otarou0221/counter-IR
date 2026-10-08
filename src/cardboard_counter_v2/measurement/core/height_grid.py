"""現在XYZを校正済みパレット面へ投影し、堅牢な高さグリッドを作る。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.measurement.core.high_surface_filter import (
    HighSurfaceFilter,
    small_high_surface_mask,
)
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry


DEFAULT_MIN_POINTS_PER_CELL = 2


@dataclass(frozen=True)
class SurfaceNormalMap:
    """現在XYZから測定単位で1度だけ作る局所法線。"""

    unit_vectors: np.ndarray
    point_valid: np.ndarray
    valid: np.ndarray


@dataclass(frozen=True)
class HeightGridDebugPoints:
    """段階別3D診断にだけ使う、間引き済み点群。"""

    raw_xyz: np.ndarray
    candidate_xyz: np.ndarray
    candidate_pixel_indices: np.ndarray
    projected_uvh: np.ndarray
    projected_pixel_indices: np.ndarray
    grid_pixel_indices: np.ndarray


@dataclass(frozen=True)
class HeightGridProjection:
    height_grid: np.ndarray
    observed_mask: np.ndarray
    debug_points: HeightGridDebugPoints | None = None


def build_surface_normal_map(
    xyz: np.ndarray,
    *,
    bounds: tuple[int, int, int, int] | None = None,
) -> SurfaceNormalMap:
    """現在フレーム全体のXYZ差分と外積を測定単位で1度だけ計算する。"""
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise ValueError("XYZマップは高さ×幅×3である必要があります。")
    vectors = np.zeros_like(xyz, dtype=np.float32)
    point_valid = np.zeros(xyz.shape[:2], dtype=bool)
    valid = np.zeros(xyz.shape[:2], dtype=bool)
    if bounds is None:
        y1, y2, x1, x2 = 0, xyz.shape[0], 0, xyz.shape[1]
    else:
        y1, y2, x1, x2 = bounds
        if not (0 <= y1 < y2 <= xyz.shape[0] and 0 <= x1 < x2 <= xyz.shape[1]):
            raise ValueError("表面法線の計算範囲がXYZ画像外です")
    cropped = xyz[y1:y2, x1:x2]
    cropped_point_valid = np.isfinite(cropped).all(axis=2) & (cropped[:, :, 2] > 0)
    point_valid[y1:y2, x1:x2] = cropped_point_valid
    if cropped.shape[0] < 3 or cropped.shape[1] < 3:
        return SurfaceNormalMap(unit_vectors=vectors, point_valid=point_valid, valid=valid)
    delta_x = cropped[1:-1, 2:] - cropped[1:-1, :-2]
    delta_y = cropped[2:, 1:-1] - cropped[:-2, 1:-1]
    target = (slice(y1 + 1, y2 - 1), slice(x1 + 1, x2 - 1))
    vectors[target] = np.cross(delta_x, delta_y).astype(np.float32)
    valid[target] = (
        cropped_point_valid[1:-1, 1:-1]
        & cropped_point_valid[1:-1, :-2]
        & cropped_point_valid[1:-1, 2:]
        & cropped_point_valid[:-2, 1:-1]
        & cropped_point_valid[2:, 1:-1]
    )
    local_vectors = vectors[target]
    lengths = np.linalg.norm(local_vectors, axis=2)
    vectors[target] = np.divide(
        local_vectors,
        lengths[:, :, None],
        out=np.zeros_like(local_vectors),
        where=lengths[:, :, None] > 1e-6,
    )
    valid[target] &= lengths > 1e-6
    return SurfaceNormalMap(unit_vectors=vectors, point_valid=point_valid, valid=valid)


def height_grid_from_frame(
    xyz: np.ndarray,
    *,
    geometry: PalletProjectionGeometry,
    surface_normals: SurfaceNormalMap,
    high_surface_filter: HighSurfaceFilter | None = None,
    collect_debug: bool = False,
    raw_debug_points: np.ndarray | None = None,
) -> HeightGridProjection:
    """現在フレームを平面投影し、パレット物理外周内だけを集計する。"""
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise ValueError("XYZマップは高さ×幅×3である必要があります。")
    if surface_normals.valid.shape != xyz.shape[:2]:
        raise ValueError("XYZマップと局所法線のサイズが一致しません。")
    plane = geometry.plane
    candidate_xyz_map = xyz
    point_valid = surface_normals.point_valid
    normal_vectors = surface_normals.unit_vectors
    normal_valid = surface_normals.valid
    candidate_pixel_indices = np.flatnonzero(
        (point_valid & normal_valid).reshape(-1)
    )
    if candidate_pixel_indices.size:
        candidate_normals = normal_vectors.reshape(-1, 3)[candidate_pixel_indices]
        alignment = np.abs(candidate_normals @ plane.normal)
        candidate_pixel_indices = candidate_pixel_indices[alignment >= 0.5]
    points = candidate_xyz_map.reshape(-1, 3)[candidate_pixel_indices]
    heights = plane.heights_mm(points)
    valid_height = heights >= -20.0
    points = points[valid_height]
    accepted_pixel_indices = candidate_pixel_indices[valid_height]
    heights = np.maximum(heights[valid_height], 0.0)
    projected = points - heights[:, None] * plane.normal[None, :]
    u = (projected - geometry.origin_xyz) @ geometry.basis_u
    v = (projected - geometry.origin_xyz) @ geometry.basis_v
    ix = np.floor(
        (u - geometry.minimum_u) / geometry.cell_size_mm
    ).astype(np.int32)
    iy = np.floor(
        (v - geometry.minimum_v) / geometry.cell_size_mm
    ).astype(np.int32)
    inside = (
        (ix >= 0)
        & (ix < geometry.width)
        & (iy >= 0)
        & (iy < geometry.height)
    )
    accepted_pixel_indices = accepted_pixel_indices[inside]
    ix, iy, heights = ix[inside], iy[inside], heights[inside]
    inside_polygon = geometry.pallet_mask[iy, ix]
    # 表示用のUVは診断時だけ保持し、通常監視で余分な配列を作らない。
    if collect_debug:
        accepted_u = u[inside][inside_polygon]
        accepted_v = v[inside][inside_polygon]
    accepted_pixel_indices = accepted_pixel_indices[inside_polygon]
    ix, iy, heights = ix[inside_polygon], iy[inside_polygon], heights[inside_polygon]
    height_grid, observed_mask, grid_pixel_indices = _robust_height_grid(
        ix,
        iy,
        heights,
        accepted_pixel_indices,
        shape=(geometry.height, geometry.width),
    )
    if high_surface_filter is not None:
        discarded = small_high_surface_mask(
            height_grid,
            observed_mask & geometry.pallet_mask,
            cell_size_mm=geometry.cell_size_mm,
            rule=high_surface_filter,
        )
        if np.any(discarded):
            # 高い元点だけを外す。セル内の低い有効点は再集計して残す。
            keep = ~(discarded[iy, ix] & (heights > high_surface_filter.start_height_mm))
            ix, iy, heights = ix[keep], iy[keep], heights[keep]
            accepted_pixel_indices = accepted_pixel_indices[keep]
            if collect_debug:
                accepted_u, accepted_v = accepted_u[keep], accepted_v[keep]
            height_grid, observed_mask, grid_pixel_indices = _robust_height_grid(
                ix,
                iy,
                heights,
                accepted_pixel_indices,
                shape=(geometry.height, geometry.width),
            )
    debug_points = None
    if collect_debug:
        if raw_debug_points is None:
            raw_valid = np.isfinite(xyz).all(axis=2) & (xyz[:, :, 2] > 0)
            raw_debug_points = sample_points(xyz[raw_valid])
        candidate_points, sampled_candidate_indices = sample_indexed_points(
            candidate_xyz_map.reshape(-1, 3)[candidate_pixel_indices],
            candidate_pixel_indices,
        )
        accepted_uvh = np.column_stack((accepted_u, accepted_v, heights))
        projected_points, sampled_projected_indices = sample_indexed_points(
            accepted_uvh,
            accepted_pixel_indices,
        )
        debug_points = HeightGridDebugPoints(
            raw_xyz=raw_debug_points,
            candidate_xyz=candidate_points,
            candidate_pixel_indices=sampled_candidate_indices,
            projected_uvh=projected_points,
            projected_pixel_indices=sampled_projected_indices,
            grid_pixel_indices=grid_pixel_indices,
        )
    return HeightGridProjection(height_grid, observed_mask, debug_points)


def sample_points(points: np.ndarray, *, maximum: int = 12_000) -> np.ndarray:
    """HTMLを過大にしないよう、決定的に間引く。"""
    values = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    if len(values) <= maximum:
        return values.copy()
    step = int(np.ceil(len(values) / maximum))
    return values[::step].copy()


def sample_indexed_points(
    points: np.ndarray,
    pixel_indices: np.ndarray,
    *,
    maximum: int = 12_000,
) -> tuple[np.ndarray, np.ndarray]:
    """点位置と元RGB画素番号の対応を保ったまま決定的に間引く。"""
    values = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    indices = np.asarray(pixel_indices, dtype=np.int64).reshape(-1)
    if len(values) != len(indices):
        raise ValueError("点群とRGB画素番号の個数が一致しません。")
    if len(values) <= maximum:
        return values.copy(), indices.copy()
    step = int(np.ceil(len(values) / maximum))
    return values[::step].copy(), indices[::step].copy()


def _robust_height_grid(
    ix: np.ndarray,
    iy: np.ndarray,
    heights: np.ndarray,
    pixel_indices: np.ndarray,
    *,
    shape: tuple[int, int],
    quantile: float = 0.75,
    min_points: int = DEFAULT_MIN_POINTS_PER_CELL,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """1点だけのセルを捨て、採用セルでは上側75%分位点を使う。"""
    _grid_height, grid_width = shape
    grid = np.zeros(shape, dtype=np.float32)
    observed = np.zeros(shape, dtype=bool)
    representative_pixels = np.full(shape, -1, dtype=np.int64)
    if heights.size == 0:
        return grid, observed, representative_pixels
    if len(pixel_indices) != len(heights):
        raise ValueError("高さとRGB画素番号の個数が一致しません。")
    cell_ids = iy.astype(np.int64) * grid_width + ix.astype(np.int64)
    order = np.lexsort((heights, cell_ids))
    sorted_cells = cell_ids[order]
    sorted_heights = heights[order]
    unique_cells, starts, counts = np.unique(
        sorted_cells,
        return_index=True,
        return_counts=True,
    )
    supported = counts >= max(int(min_points), 1)
    if not np.any(supported):
        return grid, observed, representative_pixels
    unique_cells = unique_cells[supported]
    starts = starts[supported]
    counts = counts[supported]
    ranks = starts + np.floor(
        np.clip(float(quantile), 0.0, 1.0) * (counts - 1)
    ).astype(np.int64)
    grid.reshape(-1)[unique_cells] = sorted_heights[ranks].astype(np.float32)
    observed.reshape(-1)[unique_cells] = True
    representative_pixels.reshape(-1)[unique_cells] = pixel_indices[order][ranks]
    return grid, observed, representative_pixels
