"""校正済みパレット座標で、現在Depthを1回だけ3D前処理して測定する。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import uuid

import numpy as np

from cardboard_counter_v2.common.schemas import (
    CameraMeasurementRun,
    MeasurementRequest,
    MeasurementResponse,
    PalletMeasurement,
)
from cardboard_counter_v2.common.rgbd import intrinsics_compatible
from cardboard_counter_v2.common.depth_projection import validate_xyz_depth
from cardboard_counter_v2.common.storage import capture_dir, measurement_dir
from cardboard_counter_v2.measurement.core.height_grid import (
    build_surface_normal_map,
    sample_points,
)
from cardboard_counter_v2.measurement.analysis import PalletAnalysis, analyze_pallet
from cardboard_counter_v2.measurement.artifacts import save_measurement_artifacts
from cardboard_counter_v2.measurement.debug_point_cloud import (
    build_debug_point_cloud_bundle,
)
from cardboard_counter_v2.measurement.box_estimation import estimate_box_combination
from cardboard_counter_v2.measurement.preprocessing import (
    load_depth_file,
    load_rgb_file,
    load_xyz_file,
)
from cardboard_counter_v2.measurement.point_cloud_view import (
    build_scene_point_cloud_source,
    colorize_measurement_point_cloud,
)
from cardboard_counter_v2.measurement.runtime import runtime_cache
from cardboard_counter_v2.measurement.planning import get_measurement_plan
from cardboard_counter_v2.measurement.prepared_runtime import prepared_runtime_registry


def measure(request: MeasurementRequest) -> MeasurementResponse:
    prepared = (
        prepared_runtime_registry.get(request.runtime_id)
        if request.runtime_id is not None
        else None
    )
    calibration = (
        prepared.runtime.calibration if prepared is not None else request.calibration
    )
    if calibration is None:
        raise ValueError("測定ランタイムまたは校正定義が必要です")
    if calibration.camera_id != request.camera_id:
        raise ValueError("校正と測定要求のcamera_idが一致しません")
    current_manifest = request.current_capture
    if current_manifest is None or current_manifest.capture_id != request.current_capture_id:
        raise ValueError("現在撮影台帳が測定要求に含まれていません")
    current_dir = capture_dir(
        current_manifest.capture_id,
        camera_id=current_manifest.camera_id,
        purpose=current_manifest.purpose,
        storage_version=current_manifest.storage_version,
    )
    if current_manifest.camera_id != request.camera_id:
        raise ValueError("現在撮影と測定要求のcamera_idが一致しません")
    if prepared is None and any(item.camera_id != request.camera_id for item in request.pallets):
        raise ValueError("測定対象パレットに別カメラの設定が含まれています")
    if current_manifest.depth_aligned_to_color or current_manifest.color_shape != current_manifest.depth_shape:
        raise ValueError("IRと同じ画素格子の未整列Depthが必要です")
    current = load_depth_file(current_dir / "depth.npz")
    if current.shape != current_manifest.depth_shape:
        raise ValueError("現在Depth形状が撮影manifestと一致しません")
    runtime = prepared.runtime if prepared is not None else runtime_cache.get(
        calibration,
        color_shape=current_manifest.color_shape,
        depth_shape=current_manifest.depth_shape,
    )
    if current_manifest.projection is None or current_manifest.projection.point_cloud_sensor != "depth" or current_manifest.projection.align_depth_to_color:
        raise ValueError("Depth座標の投影パラメータがありません")
    current_intrinsics = current_manifest.projection.to_rgbd_intrinsics()
    if not intrinsics_compatible(runtime.intrinsics, current_intrinsics):
        raise ValueError("校正時と現在のカメラ内部パラメータが一致しません")
    current_rgb = (
        load_rgb_file(current_dir / "rgb.jpg", current_manifest.color_shape)
        if request.generate_artifacts
        else None
    )

    if prepared is not None:
        plan = prepared.plan
        if plan.color_shape != current_manifest.color_shape or plan.depth_shape != current_manifest.depth_shape:
            raise ValueError("測定ランタイムと現在撮影の解像度が一致しません")
    else:
        plan = get_measurement_plan(
            runtime,
            request.pallets,
            request.box_catalog,
            color_shape=current_manifest.color_shape,
            depth_shape=current_manifest.depth_shape,
        )
    # カメラ側で中央値Depthから一度だけ作ったXYZをそのまま使う。
    xyz = load_xyz_file(current_dir / "xyz.npz")
    validate_xyz_depth(xyz, current)
    surface_normals = build_surface_normal_map(xyz, bounds=plan.normal_bounds)
    # 診断用の全景抽出は撮影ごとに1回だけ行い、2パレットで共有する。
    point_cloud_source = (
        build_scene_point_cloud_source(xyz, surface_normals.point_valid)
        if request.generate_artifacts
        else None
    )
    raw_debug_points = None
    if request.generate_debug_stages:
        raw_valid = np.isfinite(xyz).all(axis=2) & (xyz[:, :, 2] > 0)
        raw_debug_points = sample_points(xyz[raw_valid])

    measurement_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    output_root = measurement_dir(measurement_id)
    if request.generate_artifacts:
        output_root.mkdir(parents=True, exist_ok=False)
    pallet_results: list[PalletMeasurement] = []
    for pallet_plan in plan.pallets:
        analysis = analyze_pallet(
            xyz,
            surface_normals,
            pallet_plan,
            occupied_height_mm=request.occupied_height_mm,
            point_cloud_source=point_cloud_source,
            collect_debug=request.generate_debug_stages,
            preserve_original=request.generate_artifacts,
            raw_debug_points=raw_debug_points,
        )
        pallet_results.append(
            build_pallet_result(
                analysis,
                output_dir=output_root / f"pallet_{pallet_plan.settings.pallet_id}",
                generate_artifacts=request.generate_artifacts,
                current_rgb=current_rgb,
            )
        )
    response = MeasurementResponse(
        measurement_id=measurement_id,
        camera_runs=[CameraMeasurementRun(
            camera_id=request.camera_id,
            measurement_id=measurement_id,
            calibration_id=calibration.calibration_id,
            baseline_capture_id=calibration.calibration_capture_id,
            current_capture_id=request.current_capture_id,
        )],
        pallets=pallet_results,
    )
    return response


def build_pallet_result(
    analysis: PalletAnalysis,
    *,
    output_dir: Path,
    generate_artifacts: bool,
    current_rgb: np.ndarray | None,
) -> PalletMeasurement:
    settings = analysis.plan.settings
    geometry = analysis.plan.geometry
    volume_mm3 = analysis.volume_mm3
    box_combination = estimate_box_combination(
        analysis.plan.box_optimizer,
        volume_mm3,
    )
    estimated_boxes = sum(box_combination.best.counts.values())
    grid_path: str | None = None
    plot_path: str | None = None
    debug_stages_path: str | None = None
    if generate_artifacts:
        if current_rgb is None or analysis.point_cloud is None:
            raise ValueError("IRプレビューを使う点群の生成に必要な撮影データがありません")
        colored_point_cloud = colorize_measurement_point_cloud(
            analysis.point_cloud,
            current_rgb,
            height_grid=analysis.height_grid,
            box_region=analysis.box_region,
            geometry=geometry,
        )
        debug_point_clouds = (
            build_debug_point_cloud_bundle(
                debug_points=analysis.debug_points,
                context_points=analysis.point_cloud,
                rgb_image=current_rgb,
                original_height_grid=analysis.original_height_grid,
                height_grid=analysis.height_grid,
                box_region=analysis.box_region,
                geometry=geometry,
            )
            if analysis.debug_points is not None
            else None
        )
        saved_grid, saved_plot, saved_debug = save_measurement_artifacts(
            output_dir,
            height_grid=analysis.height_grid,
            original_height_grid=analysis.original_height_grid,
            box_region=analysis.box_region,
            observed_mask=analysis.observed_mask,
            protrusion_mask=analysis.protrusion.suppressed_mask,
            point_cloud=colored_point_cloud,
            geometry=geometry,
            summary={
                "pallet_id": settings.pallet_id,
                "pallet_number": settings.pallet_number,
                "volume_liters": volume_mm3 / 1_000_000.0,
                "estimated_boxes": estimated_boxes,
                "box_counts": box_combination.best.counts,
                "box_fit_residual_liters": box_combination.best.residual_volume_liters,
                "box_fit_ambiguous": box_combination.ambiguous,
                "plane_rmse_mm": geometry.plane.fit_rmse_mm,
                "protrusion_volume_liters": analysis.protrusion.suppressed_volume_mm3 / 1_000_000.0,
            },
            debug_points=analysis.debug_points,
            debug_point_clouds=debug_point_clouds,
        )
        relative_root = Path("measurements") / output_dir.parent.name / output_dir.name
        grid_path = str(relative_root / saved_grid.name)
        plot_path = str(relative_root / saved_plot.name)
        if saved_debug is not None:
            debug_stages_path = str(relative_root / saved_debug.name)
    return PalletMeasurement(
        pallet_id=settings.pallet_id,
        pallet_number=settings.pallet_number,
        camera_id=settings.camera_id,
        volume_liters=volume_mm3 / 1_000_000.0,
        estimated_boxes=float(estimated_boxes),
        occupied_cells=int(np.count_nonzero(analysis.box_region)),
        observed_cells=int(np.count_nonzero(analysis.observed_mask & geometry.pallet_mask)),
        plane_rmse_mm=geometry.plane.fit_rmse_mm,
        protrusion_components=analysis.protrusion.component_count,
        protrusion_cells=analysis.protrusion.suppressed_cells,
        protrusion_volume_liters=analysis.protrusion.suppressed_volume_mm3 / 1_000_000.0,
        box_combination=box_combination,
        height_grid_path=grid_path,
        plot_path=plot_path,
        debug_stages_path=debug_stages_path,
    )
