"""段階別診断を、実写色のパレット座標点群へ変換する。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import HeightGridDebugPoints
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.height_filled_point_cloud import (
    build_height_filled_geometry,
)
from cardboard_counter_v2.measurement.point_cloud_view import (
    ProjectedPointCloud,
    RgbPointCloud,
    ScenePointCloudSource,
    measurement_volume_point_mask,
    project_scene_point_cloud_for_view,
    rgb_colors_for_pixel_indices,
)


@dataclass(frozen=True)
class DebugPointCloudStage:
    """1処理段階分の、実写色を保持した表示専用点群。"""

    key: str
    title: str
    cloud: RgbPointCloud
    solid_cloud: RgbPointCloud | None = None
    solid_key: str | None = None
    solid_vertical_step_mm: float | None = None


@dataclass(frozen=True)
class DebugPointCloudBundle:
    """全段階で共有する背景と、処理後点群。"""

    context: RgbPointCloud
    stages: tuple[DebugPointCloudStage, ...]


def build_debug_point_cloud_bundle(
    *,
    debug_points: HeightGridDebugPoints,
    context_points: ProjectedPointCloud,
    rgb_image: np.ndarray,
    original_height_grid: np.ndarray,
    height_grid: np.ndarray,
    box_region: np.ndarray,
    geometry: PalletProjectionGeometry,
) -> DebugPointCloudBundle:
    """解析済み中間値を再計算せず、6段階のPotree入力へ変換する。"""
    context = _rgb_cloud(context_points.uvh, context_points.pixel_indices, rgb_image)
    # 生点群は周辺背景と同じデータなので共有し、LAS/Potree変換を重複させない。
    raw = context
    candidate = _project_camera_debug_points(
        debug_points.candidate_xyz,
        debug_points.candidate_pixel_indices,
        geometry,
        rgb_image,
    )
    projected = _rgb_cloud(
        debug_points.projected_uvh,
        debug_points.projected_pixel_indices,
        rgb_image,
    )
    original_grid = _grid_cloud(
        original_height_grid,
        box_region,
        debug_points.grid_pixel_indices,
        geometry,
        rgb_image,
    )
    corrected_grid = _grid_cloud(
        height_grid,
        box_region,
        debug_points.grid_pixel_indices,
        geometry,
        rgb_image,
    )
    original_filled, original_step = _filled_grid_cloud(
        original_height_grid,
        box_region,
        debug_points.grid_pixel_indices,
        geometry,
        rgb_image,
    )
    corrected_filled, corrected_step = _filled_grid_cloud(
        height_grid,
        box_region,
        debug_points.grid_pixel_indices,
        geometry,
        rgb_image,
    )
    final_mask = measurement_volume_point_mask(
        context_points,
        height_grid=height_grid,
        box_region=box_region,
        geometry=geometry,
    )
    final = _rgb_cloud(
        context_points.uvh[final_mask],
        context_points.pixel_indices[final_mask],
        rgb_image,
    )
    return DebugPointCloudBundle(
        context=context,
        stages=(
            DebugPointCloudStage("raw", "1 生点群", raw),
            DebugPointCloudStage("candidate", "2 現在フレーム候補", candidate),
            DebugPointCloudStage("projected", "3 側面除外・平面投影・外周制限", projected),
            DebugPointCloudStage(
                "grid",
                f"4 {geometry.cell_size_mm:g}mm高さグリッド",
                original_grid,
                solid_cloud=original_filled,
                solid_key="grid_filled",
                solid_vertical_step_mm=original_step,
            ),
            DebugPointCloudStage(
                "corrected",
                "5 局所突起除外",
                corrected_grid,
                solid_cloud=corrected_filled,
                solid_key="corrected_filled",
                solid_vertical_step_mm=corrected_step,
            ),
            DebugPointCloudStage(
                "volume",
                "6 最終体積採用点",
                final,
                solid_cloud=corrected_filled,
                solid_key="corrected_filled",
                solid_vertical_step_mm=corrected_step,
            ),
        ),
    )


def _project_camera_debug_points(
    xyz: np.ndarray,
    pixel_indices: np.ndarray,
    geometry: PalletProjectionGeometry,
    rgb_image: np.ndarray,
) -> RgbPointCloud:
    source = ScenePointCloudSource(
        xyz=np.asarray(xyz, dtype=np.float32),
        pixel_indices=np.asarray(pixel_indices, dtype=np.int64),
    )
    projected = project_scene_point_cloud_for_view(source, geometry)
    return _rgb_cloud(projected.uvh, projected.pixel_indices, rgb_image)


def _grid_cloud(
    heights: np.ndarray,
    region: np.ndarray,
    pixel_indices: np.ndarray,
    geometry: PalletProjectionGeometry,
    rgb_image: np.ndarray,
) -> RgbPointCloud:
    valid = np.asarray(region, dtype=bool) & (np.asarray(pixel_indices) >= 0)
    rows, columns = np.nonzero(valid)
    uvh = np.column_stack(
        (
            geometry.minimum_u + (columns + 0.5) * geometry.cell_size_mm,
            geometry.minimum_v + (rows + 0.5) * geometry.cell_size_mm,
            np.asarray(heights, dtype=np.float32)[rows, columns],
        )
    ).astype(np.float32)
    return _rgb_cloud(uvh, np.asarray(pixel_indices)[rows, columns], rgb_image)


def _filled_grid_cloud(
    heights: np.ndarray,
    region: np.ndarray,
    pixel_indices: np.ndarray,
    geometry: PalletProjectionGeometry,
    rgb_image: np.ndarray,
) -> tuple[RgbPointCloud, float]:
    representative_pixels = np.asarray(pixel_indices, dtype=np.int64)
    valid = np.asarray(region, dtype=bool) & (representative_pixels >= 0)
    filled = build_height_filled_geometry(heights, valid, geometry)
    source_pixels = representative_pixels[
        filled.source_rows,
        filled.source_columns,
    ]
    return (
        _rgb_cloud(filled.uvh, source_pixels, rgb_image),
        filled.vertical_step_mm,
    )


def _rgb_cloud(
    uvh: np.ndarray,
    pixel_indices: np.ndarray,
    rgb_image: np.ndarray,
) -> RgbPointCloud:
    points = np.asarray(uvh, dtype=np.float32).reshape(-1, 3)
    indices = np.asarray(pixel_indices, dtype=np.int64).reshape(-1)
    return RgbPointCloud(
        uvh=points,
        colors_rgb=rgb_colors_for_pixel_indices(rgb_image, indices),
    )
