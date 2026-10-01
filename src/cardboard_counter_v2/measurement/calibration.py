"""床XYZから、DB保存用の床基準校正結果だけを作る。"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import numpy as np

from cardboard_counter_v2.common.schemas import (
    CalibrationRequest,
    CalibrationResult,
    PalletPlaneCalibrationResult,
)
from cardboard_counter_v2.common.storage import capture_dir
from cardboard_counter_v2.common.depth_projection import validate_xyz_depth
from cardboard_counter_v2.measurement.core.models import normalized_roi
from cardboard_counter_v2.measurement.core.plane_estimation import (
    fit_pallet_plane,
    inset_roi,
)
from cardboard_counter_v2.measurement.preprocessing import (
    load_depth_file,
    load_xyz_file,
)


def calibrate(request: CalibrationRequest) -> CalibrationResult:
    """床平面を推定し、パレット上面の平行移動に必要な値だけを返す。"""
    capture = request.baseline_capture
    if capture is None or capture.capture_id != request.baseline_capture_id:
        raise ValueError("床撮影台帳が校正要求に含まれていません")
    baseline_dir = capture_dir(
        capture.capture_id,
        camera_id=capture.camera_id,
        purpose=capture.purpose,
        storage_version=capture.storage_version,
    )
    if capture.camera_id != request.camera_id:
        raise ValueError("床撮影と校正要求のcamera_idが一致しません")
    if capture.purpose != "floor":
        raise ValueError("床基準校正にはpurpose=floorの撮影が必要です")
    if any(item.camera_id != request.camera_id for item in request.pallets):
        raise ValueError("校正対象パレットに別カメラの設定が含まれています")
    if capture.depth_aligned_to_color or capture.color_shape != capture.depth_shape:
        raise ValueError("IRと同じ画素格子の未整列Depthが必要です")

    baseline = load_depth_file(baseline_dir / "depth.npz")
    if baseline.shape != capture.depth_shape:
        raise ValueError("Depth形状が撮影manifestと一致しません")
    if capture.projection is None:
        raise ValueError("撮影台帳に投影パラメータがありません")
    if capture.projection.align_depth_to_color or capture.projection.point_cloud_sensor != "depth":
        raise ValueError("Depth座標の内部パラメータが必要です")
    projection = capture.projection

    baseline_xyz = load_xyz_file(baseline_dir / "xyz.npz")
    validate_xyz_depth(baseline_xyz, baseline)
    positive = baseline[baseline > 0]
    if positive.size == 0:
        raise ValueError("床Depthに有効点がありません")
    expected_depth_mm = float(np.median(positive))

    calibrated: list[PalletPlaneCalibrationResult] = []
    for settings in request.pallets:
        if not settings.enabled:
            continue
        plane_roi = normalized_roi(settings.plane_roi, capture.color_shape)
        plane = fit_pallet_plane(
            baseline,
            baseline_xyz,
            color_shape=capture.color_shape,
            roi=inset_roi(plane_roi),
            expected_depth_mm=expected_depth_mm,
        )
        calibrated.append(
            PalletPlaneCalibrationResult(
                pallet_id=settings.pallet_id,
                pallet_number=settings.pallet_number,
                plane_roi=settings.plane_roi,
                floor_plane_normal=tuple(float(value) for value in plane.normal),
                floor_plane_offset=plane.offset,
                pallet_height_mm=request.pallet_height_mm,
                plane_rmse_mm=plane.fit_rmse_mm,
                plane_inlier_count=plane.inlier_count,
                cell_size_mm=request.grid_mm,
            )
        )

    if not calibrated:
        raise ValueError("有効なパレットがありません")
    return CalibrationResult(
        calibration_id=(
            datetime.now(UTC).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        ),
        camera_id=request.camera_id,
        baseline_capture_id=request.baseline_capture_id,
        created_at=datetime.now(UTC).isoformat(),
        projection=projection,
        pallets=calibrated,
    )
