from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cardboard_counter_v2.camera.frame_batch import save_frame_batch
from cardboard_counter_v2.camera import point_cloud as point_cloud_module
from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    FrameBatchRequest,
)
from cardboard_counter_v2.common import depth_projection
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics, StreamIntrinsics
from cardboard_counter_v2.common.schemas import PrepareCaptureRequest
from cardboard_counter_v2.measurement.preprocessing import prepare_capture


def test_point_cloud_reuses_static_pixel_projector(monkeypatch) -> None:
    intrinsics = RgbdIntrinsics(
        color=None,
        ir=StreamIntrinsics(width=3, height=2, fx=100, fy=100, cx=1, cy=1),
        depth=StreamIntrinsics(width=3, height=2, fx=100, fy=100, cx=1, cy=1),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    frames = np.full((3, 2, 3), 1000, dtype=np.uint16)
    calls = 0
    original = depth_projection.build_depth_projector

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    depth_projection.cached_depth_projector.cache_clear()
    monkeypatch.setattr(depth_projection, "build_depth_projector", counted)
    point_cloud_module.build_median_point_cloud(frames, intrinsics)
    point_cloud_module.build_median_point_cloud(frames, intrinsics)

    assert calls == 1


def test_camera_optionally_builds_xyz_and_measurement_reuses_it(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CAMERA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    request = FrameBatchRequest(
        frame_count=3,
        warmup_frames=1,
        include_xyz=True,
    )
    frames = [
        np.full((4, 5), 1000, dtype=np.uint16),
        np.zeros((4, 5), dtype=np.uint16),
        np.full((4, 5), 1200, dtype=np.uint16),
    ]
    intrinsics = RgbdIntrinsics(
        color=None,
        ir=StreamIntrinsics(
            width=5,
            height=4,
            fx=100.0,
            fy=100.0,
            cx=2.0,
            cy=2.0,
        ),
        depth=StreamIntrinsics(width=5, height=4, fx=100.0, fy=100.0, cx=2.0, cy=2.0),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    timestamps = [
        "2026-07-31T00:00:01+00:00",
        "2026-07-31T00:00:02+00:00",
        "2026-07-31T00:00:03+00:00",
    ]

    batch = save_frame_batch(
        request,
        CameraDeviceSettings(),
        frames,
        np.zeros((4, 5), dtype=np.uint16),
        intrinsics,
        timestamps,
    )

    batch_dir = tmp_path / "camera" / "frame_batches" / batch.batch_id
    with np.load(batch_dir / "depth_frames.npz") as payload:
        assert payload["depth_mm"].shape == (3, 4, 5)
    with np.load(batch_dir / "median_depth.npz") as payload:
        assert np.all(payload["depth_mm"] == 1100)
    with np.load(batch_dir / "xyz.npz") as payload:
        assert payload["xyz_mm"].shape == (4, 5, 3)
        assert np.all(payload["xyz_mm"][:, :, 2] == 1100)
    assert batch.xyz_source == "temporal_median_ignore_zero"
    assert batch.preview_path == batch.rgb_path
    assert batch.reference_shape == batch.color_shape
    assert batch.intrinsics is not None
    assert batch.intrinsics["color"] is None
    assert batch.intrinsics["ir"]["width"] == 5

    capture = prepare_capture(
        PrepareCaptureRequest(batch_id=batch.batch_id, purpose="current")
    )

    assert capture.source_batch_id == batch.batch_id
    assert capture.color_shape == (4, 5)
    assert capture.depth_shape == (4, 5)
    assert capture.depth_aligned_to_color is False
    assert capture.ir_path is not None
    assert capture.xyz_path is not None
    capture_dir = (
        tmp_path / "captures" / capture.camera_id / capture.purpose / capture.capture_id
    )
    assert capture.storage_version == 3
    # 同じ共有ボリュームでは大きな派生成果物を複製しない。
    assert (batch_dir / "median_depth.npz").stat().st_ino == (
        capture_dir / "depth.npz"
    ).stat().st_ino
    assert (batch_dir / "xyz.npz").stat().st_ino == (
        capture_dir / "xyz.npz"
    ).stat().st_ino
    with np.load(capture_dir / "depth.npz") as payload:
        assert np.all(payload["depth_mm"] == 1100)
    with np.load(capture_dir / "xyz.npz") as payload:
        assert np.all(payload["xyz_mm"][:, :, 2] == 1100)


def test_raw_camera_batch_does_not_build_xyz_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMERA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    request = FrameBatchRequest(frame_count=1, warmup_frames=0)
    intrinsics = RgbdIntrinsics(
        color=None,
        ir=StreamIntrinsics(width=2, height=2, fx=100, fy=100, cx=1, cy=1),
        depth=StreamIntrinsics(width=2, height=2, fx=100, fy=100, cx=1, cy=1),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    batch = save_frame_batch(
        request,
        CameraDeviceSettings(),
        [np.full((2, 2), 1000, dtype=np.uint16)],
        np.zeros((2, 2), dtype=np.uint16),
        intrinsics,
        ["2026-07-31T00:00:01+00:00"],
    )
    batch_dir = tmp_path / "camera" / "frame_batches" / batch.batch_id
    assert batch.xyz_path is None
    assert batch.median_depth_path is None
    assert not (batch_dir / "xyz.npz").exists()
    with pytest.raises(ValueError, match="中央値DepthとXYZ"):
        prepare_capture(PrepareCaptureRequest(batch_id=batch.batch_id, purpose="current"))


def test_ir_method_rejects_mismatched_ir_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMERA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    request = FrameBatchRequest(frame_count=1, warmup_frames=0)
    intrinsics = RgbdIntrinsics(
        color=None,
        ir=StreamIntrinsics(width=5, height=4, fx=100, fy=100, cx=5, cy=2),
        depth=StreamIntrinsics(width=5, height=4, fx=100, fy=100, cx=2, cy=2),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    with pytest.raises(ValueError, match="内部パラメータが一致"):
        save_frame_batch(
            request,
            CameraDeviceSettings(),
            [np.full((4, 5), 1000, dtype=np.uint16)],
            np.zeros((4, 5), dtype=np.uint16),
            intrinsics,
            ["2026-07-31T00:00:01+00:00"],
        )
