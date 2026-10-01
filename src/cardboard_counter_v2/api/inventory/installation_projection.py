"""設置履歴へ保存するIR・Depth投影条件の正規化と検証。"""

from __future__ import annotations

import math

from cardboard_counter_v2.api.inventory.models import CameraInstallationRecord
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec
from cardboard_counter_v2.common.schemas import CaptureManifest


def capture_parameters(
    manifest: CaptureManifest,
) -> tuple[dict[str, object], dict[str, object] | None]:
    projection = require_projection(manifest)
    return {
        "fx": projection.fx,
        "fy": projection.fy,
        "cx": projection.cx,
        "cy": projection.cy,
    }, manifest.distortion


def parameters_match(
    stored_intrinsics: dict[str, object],
    stored_distortion: dict[str, object] | None,
    observed_intrinsics: dict[str, object],
    observed_distortion: dict[str, object] | None,
    *,
    allow_unrecorded_distortion: bool = False,
) -> bool:
    if any(
        not math.isclose(
            float(stored_intrinsics.get(name, float("nan"))),
            float(observed_intrinsics.get(name, float("nan"))),
            rel_tol=1e-9,
            abs_tol=1e-3,
        )
        for name in ("fx", "fy", "cx", "cy")
    ):
        return False
    if allow_unrecorded_distortion and observed_distortion is None:
        return True
    if stored_distortion is None or observed_distortion is None:
        return stored_distortion is None and observed_distortion is None
    if stored_distortion.keys() != observed_distortion.keys():
        return False
    return all(
        math.isclose(
            float(stored_distortion[name]),
            float(observed_distortion[name]),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
        for name in stored_distortion
    )


def validate_capture_mode(
    installation: CameraInstallationRecord,
    manifest: CaptureManifest,
) -> None:
    projection = require_projection(manifest)
    expected_color_shape = (
        installation.color_height,
        installation.color_width,
    )
    if manifest.color_shape != expected_color_shape:
        raise ValueError(
            "撮影時のIR解像度が設置履歴と一致しません: "
            f"{manifest.color_shape} != {expected_color_shape}"
        )
    if (
        projection.point_cloud_sensor != "depth"
        or projection.align_depth_to_color
        or installation.align_depth_to_color
        or manifest.depth_aligned_to_color
    ):
        raise ValueError("IR版ではDepth座標の未整列データが必要です")
    if manifest.depth_shape != expected_color_shape:
        raise ValueError("IRとDepthの画素数が一致しません")
    if (projection.height, projection.width) != expected_color_shape:
        raise ValueError("内部パラメータの解像度がIR解像度と一致しません")


def installation_projection(
    installation: CameraInstallationRecord,
) -> ProjectionIntrinsicsSpec:
    if installation.intrinsics is None:
        raise ValueError(
            "カメラ設置履歴に内部パラメータがありません: "
            f"{installation.camera_installation_id}"
        )
    return ProjectionIntrinsicsSpec(
        point_cloud_sensor="depth",
        align_depth_to_color=installation.align_depth_to_color,
        width=installation.color_width,
        height=installation.color_height,
        distortion=installation.distortion,
        **installation.intrinsics,
    )


def require_projection(manifest: CaptureManifest) -> ProjectionIntrinsicsSpec:
    if manifest.projection is None:
        raise ValueError(
            f"撮影台帳に投影パラメータがありません: {manifest.capture_id}"
        )
    return manifest.projection
