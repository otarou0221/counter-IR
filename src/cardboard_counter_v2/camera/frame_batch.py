"""同期Active IR・Depthと、必要な場合だけXYZを共有領域へ保存する。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import uuid

import cv2
import numpy as np

from cardboard_counter_v2.camera.ir_preview import ir_preview
from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    FrameBatchManifest,
    FrameBatchRequest,
)
from cardboard_counter_v2.camera.storage import (
    frame_batch_dir,
    relative_camera_path,
)
from cardboard_counter_v2.camera.point_cloud import build_median_point_cloud
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics
from cardboard_counter_v2.common.ir_depth import validate_ir_depth_geometry
from cardboard_counter_v2.common.storage import atomic_write_json


def save_frame_batch(
    request: FrameBatchRequest,
    camera: CameraDeviceSettings,
    depth_frames: np.ndarray | list[np.ndarray],
    latest_ir: np.ndarray,
    intrinsics: RgbdIntrinsics,
    frame_timestamps: list[str],
) -> FrameBatchManifest:
    """IR/Depthを保存し、要求時だけ中央値DepthとXYZも生成する。"""
    if len(depth_frames) != request.frame_count:
        raise RuntimeError(
            f"取得フレーム不足: expected={request.frame_count}, actual={len(depth_frames)}"
        )
    if len(frame_timestamps) != request.frame_count:
        raise RuntimeError(
            "Depthフレームと時刻の個数が一致しません: "
            f"frames={len(depth_frames)}, timestamps={len(frame_timestamps)}"
        )

    captured_at = frame_timestamps[-1]
    batch_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    output_dir = frame_batch_dir(batch_id)
    depth_frames_path = output_dir / "depth_frames.npz"
    ir_path = output_dir / "ir.npz"
    rgb_path = output_dir / "rgb.jpg"  # 既存の表示契約。内容はIRプレビュー。
    intrinsics_path = output_dir / "intrinsics.json"
    metadata_path = output_dir / "metadata.json"
    median_depth_path = output_dir / "median_depth.npz"
    xyz_path = output_dir / "xyz.npz"

    # CameraStreamHubからは既に連続配列で届くため、通常はコピーしない。
    depth_stack = np.asarray(depth_frames)
    if depth_stack.ndim != 3:
        raise RuntimeError(f"Depthフレーム群の形状が不正です: {depth_stack.shape}")
    color_shape = (int(latest_ir.shape[0]), int(latest_ir.shape[1]))
    depth_shape = (int(depth_stack.shape[1]), int(depth_stack.shape[2]))
    if latest_ir.dtype != np.uint16:
        raise ValueError("Active IRはuint16で保存してください")
    validate_ir_depth_geometry(intrinsics, color_shape, depth_shape)
    depth_aligned_to_color = False
    output_dir.mkdir(parents=True, exist_ok=False)
    if request.include_raw_frames:
        np.savez_compressed(depth_frames_path, depth_mm=depth_stack)
    if request.include_xyz:
        point_cloud = build_median_point_cloud(depth_stack, intrinsics)
        np.savez_compressed(median_depth_path, depth_mm=point_cloud.depth_mm)
        np.savez_compressed(xyz_path, xyz_mm=point_cloud.xyz_mm)
    np.savez_compressed(ir_path, ir=latest_ir)
    if not cv2.imwrite(str(rgb_path), ir_preview(latest_ir)):
        raise RuntimeError(f"IRプレビューを保存できませんでした: {rgb_path}")
    atomic_write_json(intrinsics_path, asdict(intrinsics))
    atomic_write_json(
        metadata_path,
        {
            "batch_id": batch_id,
            "captured_at": captured_at,
            "frame_timestamps": frame_timestamps,
            "frame_count": len(depth_frames),
            "warmup_frames": request.warmup_frames,
            "color_shape": color_shape,
            "reference_shape": color_shape,
            "depth_shape": depth_shape,
            "depth_aligned_to_color": depth_aligned_to_color,
            "reference_image_sensor": "active_ir",
            "ir_path": relative_camera_path(ir_path),
            "preview_path": relative_camera_path(rgb_path),
            "camera": camera.model_dump(),
            "include_xyz": request.include_xyz,
            "include_raw_frames": request.include_raw_frames,
            "xyz_source": "temporal_median_ignore_zero" if request.include_xyz else None,
        },
    )
    manifest = FrameBatchManifest(
        batch_id=batch_id,
        camera_id=camera.camera_id,
        captured_at=captured_at,
        frame_timestamps=frame_timestamps,
        depth_frames_path=(
            relative_camera_path(depth_frames_path)
            if request.include_raw_frames
            else None
        ),
        ir_path=relative_camera_path(ir_path),
        preview_path=relative_camera_path(rgb_path),
        rgb_path=relative_camera_path(rgb_path),
        intrinsics_path=relative_camera_path(intrinsics_path),
        intrinsics=asdict(intrinsics),
        metadata_path=relative_camera_path(metadata_path),
        median_depth_path=(
            relative_camera_path(median_depth_path) if request.include_xyz else None
        ),
        xyz_path=relative_camera_path(xyz_path) if request.include_xyz else None,
        xyz_source="temporal_median_ignore_zero" if request.include_xyz else None,
        frame_count=len(depth_frames),
        color_shape=color_shape,
        reference_shape=color_shape,
        depth_shape=depth_shape,
        depth_aligned_to_color=depth_aligned_to_color,
    )
    atomic_write_json(output_dir / "manifest.json", manifest.model_dump())
    return manifest
