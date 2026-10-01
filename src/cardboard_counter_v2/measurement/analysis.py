"""新方式の純粋な数値解析。HTTP・保存・HTML生成は扱わない。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import (
    HeightGridDebugPoints,
    SurfaceNormalMap,
    height_grid_from_frame,
)
from cardboard_counter_v2.measurement.core.masking import extract_box_region_mask, recover_nearby_box_pixels
from cardboard_counter_v2.measurement.core.protrusion_filter import HeightProtrusionFilterResult, suppress_small_height_protrusions
from cardboard_counter_v2.measurement.planning import PalletMeasurementPlan
from cardboard_counter_v2.measurement.point_cloud_view import (
    ProjectedPointCloud,
    ScenePointCloudSource,
    project_scene_point_cloud_for_view,
)


@dataclass(frozen=True)
class PalletAnalysis:
    plan: PalletMeasurementPlan
    height_grid: np.ndarray
    original_height_grid: np.ndarray
    box_region: np.ndarray
    observed_mask: np.ndarray
    protrusion: HeightProtrusionFilterResult
    volume_mm3: float
    point_cloud: ProjectedPointCloud | None
    debug_points: HeightGridDebugPoints | None


def analyze_pallet(
    xyz: np.ndarray,
    surface_normals: SurfaceNormalMap,
    plan: PalletMeasurementPlan,
    *,
    occupied_height_mm: float,
    point_cloud_source: ScenePointCloudSource | None,
    collect_debug: bool,
    preserve_original: bool,
    raw_debug_points: np.ndarray | None = None,
) -> PalletAnalysis:
    """現在点群を1回だけ新方式で解析し、必要な場合だけ中間値を返す。"""
    projection = height_grid_from_frame(
        xyz,
        geometry=plan.geometry,
        surface_normals=surface_normals,
        collect_debug=collect_debug,
        raw_debug_points=raw_debug_points,
    )
    point_cloud = (
        project_scene_point_cloud_for_view(
            point_cloud_source,
            plan.geometry,
        )
        if point_cloud_source is not None
        else None
    )
    valid = plan.geometry.pallet_mask & projection.observed_mask
    occupied = valid & (projection.height_grid >= occupied_height_mm)
    box_region = recover_nearby_box_pixels(
        extract_box_region_mask(occupied),
        projection.height_grid,
        valid,
        occupied_height_mm=occupied_height_mm,
    )
    # フィルタは入力を破壊しないため、成果物が無い通常監視ではコピー不要。
    original_height = (
        projection.height_grid.copy()
        if preserve_original
        else projection.height_grid
    )
    protrusion = suppress_small_height_protrusions(
        projection.height_grid,
        box_region,
        cell_size_mm=plan.geometry.cell_size_mm,
        box_width_mm=plan.reference_box.width_mm,
        box_depth_mm=plan.reference_box.depth_mm,
    )
    volume_mm3 = float(
        np.sum(protrusion.height_grid[box_region]) * plan.geometry.cell_size_mm**2
    )
    return PalletAnalysis(
        plan=plan,
        height_grid=protrusion.height_grid,
        original_height_grid=original_height,
        box_region=box_region,
        observed_mask=projection.observed_mask,
        protrusion=protrusion,
        volume_mm3=volume_mm3,
        point_cloud=point_cloud,
        debug_points=projection.debug_points,
    )
