"""IR・DepthバッチをCardboard測定用入力へ変換する。"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import shutil
import uuid
from dataclasses import asdict

import cv2
import numpy as np

from cardboard_counter_v2.common.camera_contracts import FrameBatchManifest
from cardboard_counter_v2.common.capture_policy import CURRENT_CAPTURE_STORAGE_VERSION
from cardboard_counter_v2.common.depth_projection import pointcloud_intrinsics_for_depth_shape
from cardboard_counter_v2.common.ir_depth import validate_ir_depth_geometry
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec
from cardboard_counter_v2.common.rgbd import parse_rgbd_intrinsics
from cardboard_counter_v2.common.schemas import CaptureManifest, PrepareCaptureRequest
from cardboard_counter_v2.common.storage import (
    capture_dir,
    frame_batch_dir,
    read_json,
)


def prepare_capture(request: PrepareCaptureRequest) -> CaptureManifest:
    """汎用バッチの中央値Depth・任意XYZをCardboard用Captureへ引き継ぐ。"""
    source_dir = frame_batch_dir(request.batch_id)
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"フレームバッチが見つかりません: {request.batch_id}")
    source = FrameBatchManifest.model_validate(read_json(manifest_path))
    if source.batch_id != request.batch_id:
        raise ValueError("バッチIDとmanifestの内容が一致しません")
    if source.camera_id != request.camera_id:
        raise ValueError("フレームバッチと前処理要求のcamera_idが一致しません")
    if source.depth_aligned_to_color or source.ir_path is None:
        raise ValueError("Active IR画像と未整列Depthのバッチが必要です")

    if source.xyz_path is None or source.median_depth_path is None:
        raise ValueError("新方式のCaptureには中央値DepthとXYZが必要です")
    if source.xyz_source != "temporal_median_ignore_zero":
        raise ValueError(f"未対応のXYZ生成元です: {source.xyz_source}")

    intrinsics_payload = request.intrinsics or source.intrinsics
    if intrinsics_payload is None:
        raw_intrinsics = read_json(source_dir / "intrinsics.json")
        if not isinstance(raw_intrinsics, dict):
            raise ValueError("フレームバッチの内部パラメータが不正です")
        intrinsics_payload = raw_intrinsics
    intrinsics = parse_rgbd_intrinsics(intrinsics_payload)
    validate_ir_depth_geometry(intrinsics, source.color_shape, source.depth_shape)
    stream = pointcloud_intrinsics_for_depth_shape(intrinsics, source.depth_shape)
    projection = ProjectionIntrinsicsSpec(
        point_cloud_sensor=intrinsics.point_cloud_sensor,
        align_depth_to_color=intrinsics.align_depth_to_color,
        width=stream.width,
        height=stream.height,
        fx=stream.fx,
        fy=stream.fy,
        cx=stream.cx,
        cy=stream.cy,
        distortion=asdict(stream.distortion) if stream.distortion is not None else None,
    )
    distortion = asdict(stream.distortion) if stream.distortion is not None else None

    capture_id = (
        datetime.now(UTC).strftime("%Y%m%d_%H%M%S_")
        + request.camera_id
        + "_"
        + request.purpose
        + "_"
        + uuid.uuid4().hex[:8]
    )
    output_dir = capture_dir(
        capture_id,
        camera_id=source.camera_id,
        purpose=request.purpose,
        storage_version=CURRENT_CAPTURE_STORAGE_VERSION,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    depth_path = output_dir / "depth.npz"
    xyz_path = output_dir / "xyz.npz"
    rgb_path = output_dir / "rgb.jpg"
    ir_path = output_dir / "ir.npz"
    link_or_copy_required(source_dir / "median_depth.npz", depth_path)
    link_or_copy_required(source_dir / "xyz.npz", xyz_path)
    copy_required(source_dir / "rgb.jpg", rgb_path)
    link_or_copy_required(source_dir / "ir.npz", ir_path)

    manifest = CaptureManifest(
        capture_id=capture_id,
        camera_id=source.camera_id,
        purpose=request.purpose,
        retention=request.retention,
        source_batch_id=source.batch_id,
        storage_version=CURRENT_CAPTURE_STORAGE_VERSION,
        depth_path=relative_capture_path(depth_path),
        xyz_path=relative_capture_path(xyz_path),
        rgb_path=relative_capture_path(rgb_path),
        ir_path=relative_capture_path(ir_path),
        projection=projection,
        distortion=distortion,
        frame_count=source.frame_count,
        color_shape=source.color_shape,
        depth_shape=source.depth_shape,
        depth_aligned_to_color=source.depth_aligned_to_color,
        captured_at=source.captured_at,
    )
    return manifest


def load_depth_file(path: Path) -> np.ndarray:
    """前処理済みの1枚Depthを読む。"""
    if not path.is_file():
        raise ValueError(f"Depthファイルが見つかりません: {path}")
    with np.load(path) as payload:
        if "depth_mm" not in payload:
            raise ValueError(f"depth_mmがありません: {path}")
        depth = payload["depth_mm"]
    if depth.ndim != 2:
        raise ValueError(f"Depthの形状が不正です: {depth.shape}")
    return depth.astype(np.float32)


def load_xyz_file(path: Path) -> np.ndarray:
    """画素配置を維持したXYZファイルを読む。"""
    if not path.is_file():
        raise ValueError(f"XYZファイルが見つかりません: {path}")
    with np.load(path) as payload:
        if "xyz_mm" not in payload:
            raise ValueError(f"xyz_mmがありません: {path}")
        xyz = payload["xyz_mm"]
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise ValueError(f"XYZの形状が不正です: {xyz.shape}")
    return xyz.astype(np.float32, copy=False)


def load_rgb_file(path: Path, expected_shape: tuple[int, int]) -> np.ndarray:
    """IRプレビューJPEGを読み、点群着色用の3チャンネル配列を返す。"""
    if not path.is_file():
        raise ValueError(f"IRプレビューが見つかりません: {path}")
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"IRプレビューを読み込めませんでした: {path}")
    if bgr.shape[:2] != expected_shape:
        raise ValueError(
            f"IRプレビューと撮影manifestの形状が一致しません: {bgr.shape[:2]} != {expected_shape}"
        )
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def copy_required(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ValueError(f"必要なバッチファイルが見つかりません: {source}")
    shutil.copy2(source, destination)


def link_or_copy_required(source: Path, destination: Path) -> None:
    """同一共有ボリュームでは複製せず、別FSの場合だけコピーする。"""
    if not source.is_file():
        raise ValueError(f"必要なバッチファイルが見つかりません: {source}")
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def relative_capture_path(path: Path) -> str:
    parts = path.resolve().parts
    try:
        index = parts.index("captures")
    except ValueError:
        return str(path)
    return str(Path(*parts[index:]))
