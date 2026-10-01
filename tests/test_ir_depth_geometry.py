"""広角Depthの視線補正とIR/Depth画素対応を検証する。"""

import cv2
import numpy as np
import pytest

from cardboard_counter_v2.common.depth_projection import build_depth_projector
from cardboard_counter_v2.common.ir_depth import validate_ir_depth_geometry
from cardboard_counter_v2.common.rgbd import CameraDistortion, RgbdIntrinsics, StreamIntrinsics


def test_wide_depth_rays_match_brown_conrady_reference() -> None:
    distortion = CameraDistortion(
        k1=0.12, k2=-0.06, k3=0.01,
        k4=0.02, k5=0.0, k6=0.0,
        p1=0.002, p2=-0.003,
    )
    profile = StreamIntrinsics(
        width=16, height=16, fx=9.5, fy=9.5, cx=7.5, cy=7.5,
        distortion=distortion,
    )
    intrinsics = RgbdIntrinsics(
        color=None, depth=profile, align_depth_to_color=False,
        point_cloud_sensor="depth", ir=profile,
    )
    validate_ir_depth_geometry(intrinsics, (16, 16), (16, 16))
    projector = build_depth_projector(intrinsics, (16, 16))
    samples = np.array([[[1.0, 1.0]], [[7.0, 7.0]], [[14.0, 14.0]]], dtype=np.float64)
    matrix = np.array([[9.5, 0, 7.5], [0, 9.5, 7.5], [0, 0, 1]], dtype=np.float64)
    coeffs = np.array([0.12, -0.06, 0.002, -0.003, 0.01, 0.02, 0, 0])
    expected = cv2.undistortPoints(samples, matrix, coeffs)[:, 0]
    actual = np.array([
        [projector.ray_x[int(y), int(x)], projector.ray_y[int(y), int(x)]]
        for x, y in samples[:, 0]
    ])
    assert np.allclose(actual, expected, atol=1e-4)


def test_ir_depth_rejects_shifted_intrinsics() -> None:
    ir = StreamIntrinsics(width=4, height=4, fx=10, fy=10, cx=1, cy=1)
    depth = StreamIntrinsics(width=4, height=4, fx=10, fy=10, cx=3, cy=1)
    with pytest.raises(ValueError, match="内部パラメータが一致"):
        validate_ir_depth_geometry(
            RgbdIntrinsics(None, depth, False, "depth", ir), (4, 4), (4, 4)
        )
