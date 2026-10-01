"""旧Captureファイルを現行のDB台帳＋NPZ形式へ明示的に移行する。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import shutil
from typing import Any

import numpy as np

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repositories.capture_repository import (
    CaptureRepository,
)
from cardboard_counter_v2.common.depth_projection import (
    build_depth_projector,
    pointcloud_intrinsics_for_depth_shape,
    validate_xyz_depth,
)
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec
from cardboard_counter_v2.common.rgbd import parse_rgbd_intrinsics
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics, StreamIntrinsics
from cardboard_counter_v2.common.schemas import CaptureManifest
from cardboard_counter_v2.common.storage import data_root, read_json, safe_id


CAPTURE_STORAGE_VERSION = 2


@dataclass(frozen=True)
class LegacyCapturePlan:
    capture_id: str
    manifest_path: Path
    depth_path: Path
    intrinsics_path: Path | None
    needs_depth_conversion: bool
    needs_xyz_generation: bool


@dataclass
class CaptureMigrationReport:
    candidates: int = 0
    migrated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.errors


class LegacyCaptureMigrator:
    """v1のJSONサイドカーを、再実行可能な手順でv2へ変換する。"""

    def __init__(self, database: Database, root: Path | None = None) -> None:
        self.database = database
        self.root = (root or data_root()).resolve()
        self.capture_root = self.root / "captures"
        self.repository = CaptureRepository(database)

    def plans(self) -> list[LegacyCapturePlan]:
        if not self.capture_root.is_dir():
            return []
        return [
            self._build_plan(path)
            for path in sorted(self.capture_root.glob("*/manifest.json"))
        ]

    def validate(self) -> CaptureMigrationReport:
        report = CaptureMigrationReport()
        paths = (
            sorted(self.capture_root.glob("*/manifest.json"))
            if self.capture_root.is_dir()
            else []
        )
        report.candidates = len(paths)
        for path in paths:
            try:
                plan = self._build_plan(path)
                manifest = self._prepare_manifest(plan, write_files=False)
                self.repository.validate_camera_parameters(
                    manifest,
                    allow_unrecorded_distortion=True,
                )
            except Exception as exc:
                report.errors.append(f"{path.parent.name}: {exc}")
        return report

    def apply(self) -> CaptureMigrationReport:
        self.database.initialize()
        report = CaptureMigrationReport()
        paths = (
            sorted(self.capture_root.glob("*/manifest.json"))
            if self.capture_root.is_dir()
            else []
        )
        report.candidates = len(paths)
        for path in paths:
            try:
                plan = self._build_plan(path)
                manifest = self._prepare_manifest(plan, write_files=True)
                self.repository.register(
                    manifest,
                    allow_unrecorded_distortion=True,
                )
                self._archive_legacy_files(plan)
                report.migrated += 1
            except Exception as exc:
                report.errors.append(f"{path.parent.name}: {exc}")
        return report

    def _build_plan(self, manifest_path: Path) -> LegacyCapturePlan:
        payload = self._payload(manifest_path)
        capture_id = safe_id(str(payload.get("capture_id") or manifest_path.parent.name))
        if capture_id != manifest_path.parent.name:
            raise ValueError("ディレクトリ名とcapture_idが一致しません")
        depth_path = self._resolve_file(
            manifest_path.parent,
            payload.get("depth_path"),
            ("depth.npz", "depth.npy"),
        )
        intrinsics_path = self._optional_file(
            manifest_path.parent,
            payload.get("intrinsics_path"),
            ("intrinsics.json",),
        )
        if intrinsics_path is None and not isinstance(payload.get("projection"), dict):
            raise ValueError("内部パラメータまたはprojectionがありません")
        xyz_path = self._optional_file(
            manifest_path.parent,
            payload.get("xyz_path"),
            ("xyz.npz", "xyz.npy"),
        )
        return LegacyCapturePlan(
            capture_id=capture_id,
            manifest_path=manifest_path,
            depth_path=depth_path,
            intrinsics_path=intrinsics_path,
            needs_depth_conversion=depth_path != manifest_path.parent / "depth.npz",
            needs_xyz_generation=xyz_path is None,
        )

    def _prepare_manifest(
        self,
        plan: LegacyCapturePlan,
        *,
        write_files: bool,
    ) -> CaptureManifest:
        payload = self._payload(plan.manifest_path)
        depth = self._load_depth(plan.depth_path)
        expected_depth_shape = self._shape(payload, "depth_shape")
        if depth.shape != expected_depth_shape:
            raise ValueError(
                f"Depth形状がmanifestと一致しません: {depth.shape} != {expected_depth_shape}"
            )
        intrinsics, projection, distortion = self._projection_context(plan, payload)
        if not intrinsics.depth_is_color_aligned:
            raise ValueError("RGBへ整列されていない旧Depthは移行できません")
        stream = pointcloud_intrinsics_for_depth_shape(intrinsics, depth.shape)

        legacy_xyz = self._optional_file(
            plan.manifest_path.parent,
            payload.get("xyz_path"),
            ("xyz.npz", "xyz.npy"),
        )
        if legacy_xyz is None:
            xyz = build_depth_projector(intrinsics, depth.shape).project(depth)
        else:
            xyz = self._load_xyz(legacy_xyz)
        validate_xyz_depth(xyz, depth)

        rgb_path = self._resolve_file(
            plan.manifest_path.parent,
            payload.get("rgb_path"),
            ("rgb.jpg",),
        )
        if write_files:
            self._write_npz_atomic(
                plan.manifest_path.parent / "depth.npz", "depth_mm", depth
            )
            self._write_npz_atomic(
                plan.manifest_path.parent / "xyz.npz", "xyz_mm", xyz
            )

        purpose = "floor" if payload.get("purpose") == "empty" else payload.get("purpose")
        if purpose not in {"floor", "current"}:
            raise ValueError(f"未対応の撮影用途です: {purpose!r}")
        retention = payload.get("retention", "persistent")
        if retention not in {"persistent", "transient"}:
            raise ValueError(f"未対応の保存区分です: {retention!r}")
        relative = Path("captures") / plan.capture_id
        return CaptureManifest(
            capture_id=plan.capture_id,
            camera_id=str(payload.get("camera_id") or "camera_1"),
            purpose=str(purpose),
            retention=retention,
            source_batch_id=payload.get("source_batch_id"),
            storage_version=CAPTURE_STORAGE_VERSION,
            depth_path=str(relative / "depth.npz"),
            xyz_path=str(relative / "xyz.npz"),
            rgb_path=str(relative / rgb_path.name),
            projection=projection,
            distortion=distortion,
            frame_count=int(payload.get("frame_count") or 1),
            color_shape=self._shape(payload, "color_shape"),
            depth_shape=expected_depth_shape,
            depth_aligned_to_color=True,
            captured_at=payload.get("captured_at"),
        )

    def _archive_legacy_files(self, plan: LegacyCapturePlan) -> None:
        backup = self.root / "backups" / "capture_v1" / plan.capture_id
        backup.mkdir(parents=True, exist_ok=True)
        paths = [plan.manifest_path]
        if plan.intrinsics_path is not None:
            paths.append(plan.intrinsics_path)
        if plan.depth_path.name != "depth.npz":
            paths.append(plan.depth_path)
        payload = self._payload(plan.manifest_path)
        legacy_xyz = self._optional_file(
            plan.manifest_path.parent,
            payload.get("xyz_path"),
            ("xyz.npy",),
        )
        if legacy_xyz is not None and legacy_xyz.name != "xyz.npz":
            paths.append(legacy_xyz)
        for source in paths:
            if not source.is_file():
                continue
            destination = backup / source.name
            if not destination.exists():
                shutil.copy2(source, destination)
            source.unlink()

    @staticmethod
    def _projection_context(
        plan: LegacyCapturePlan,
        payload: dict[str, Any],
    ) -> tuple[RgbdIntrinsics, ProjectionIntrinsicsSpec, dict[str, object] | None]:
        if plan.intrinsics_path is not None:
            raw = read_json(plan.intrinsics_path)
            if not isinstance(raw, dict):
                raise ValueError("内部パラメータJSONが不正です")
            intrinsics = parse_rgbd_intrinsics(raw)
            stream = pointcloud_intrinsics_for_depth_shape(
                intrinsics,
                LegacyCaptureMigrator._shape(payload, "depth_shape"),
            )
            projection = ProjectionIntrinsicsSpec(
                point_cloud_sensor=intrinsics.point_cloud_sensor,
                align_depth_to_color=intrinsics.align_depth_to_color,
                width=stream.width,
                height=stream.height,
                fx=stream.fx,
                fy=stream.fy,
                cx=stream.cx,
                cy=stream.cy,
            )
            distortion = (
                asdict(stream.distortion)
                if stream.distortion is not None
                else None
            )
            return intrinsics, projection, distortion

        projection = ProjectionIntrinsicsSpec.model_validate(payload["projection"])
        stream = StreamIntrinsics(
            width=projection.width,
            height=projection.height,
            fx=projection.fx,
            fy=projection.fy,
            cx=projection.cx,
            cy=projection.cy,
        )
        intrinsics = RgbdIntrinsics(
            color=stream if projection.point_cloud_sensor == "color" else None,
            depth=stream if projection.point_cloud_sensor == "depth" else None,
            align_depth_to_color=projection.align_depth_to_color,
            point_cloud_sensor=projection.point_cloud_sensor,
        )
        distortion = payload.get("distortion")
        if distortion is not None and not isinstance(distortion, dict):
            raise ValueError("distortionが不正です")
        return intrinsics, projection, distortion

    @staticmethod
    def _payload(path: Path) -> dict[str, Any]:
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"manifest JSONが不正です: {path}")
        return payload

    def _resolve_file(
        self,
        directory: Path,
        configured: object,
        fallback_names: tuple[str, ...],
    ) -> Path:
        path = self._optional_file(directory, configured, fallback_names)
        if path is None:
            names = ", ".join(fallback_names)
            raise ValueError(f"必要なファイルがありません: {names}")
        return path

    def _optional_file(
        self,
        directory: Path,
        configured: object,
        fallback_names: tuple[str, ...],
    ) -> Path | None:
        candidates: list[Path] = []
        if isinstance(configured, str) and configured.strip():
            value = Path(configured)
            candidates.extend([
                value if value.is_absolute() else self.root / value,
                directory / value.name,
            ])
        candidates.extend(directory / name for name in fallback_names)
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(self.root)
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                return resolved
        return None

    @staticmethod
    def _shape(payload: dict[str, Any], name: str) -> tuple[int, int]:
        value = payload.get(name)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"{name}が不正です")
        shape = (int(value[0]), int(value[1]))
        if shape[0] < 1 or shape[1] < 1:
            raise ValueError(f"{name}が不正です: {shape}")
        return shape

    @staticmethod
    def _load_depth(path: Path) -> np.ndarray:
        loaded = np.load(path, allow_pickle=False)
        try:
            if isinstance(loaded, np.ndarray):
                depth = loaded
            else:
                if "depth_mm" not in loaded:
                    raise ValueError(f"depth_mmがありません: {path}")
                depth = loaded["depth_mm"]
        finally:
            if hasattr(loaded, "close"):
                loaded.close()
        if depth.ndim != 2:
            raise ValueError(f"Depth形状が不正です: {depth.shape}")
        return depth.astype(np.float32)

    @staticmethod
    def _load_xyz(path: Path) -> np.ndarray:
        loaded = np.load(path, allow_pickle=False)
        try:
            if isinstance(loaded, np.ndarray):
                xyz = loaded
            else:
                if "xyz_mm" not in loaded:
                    raise ValueError(f"xyz_mmがありません: {path}")
                xyz = loaded["xyz_mm"]
        finally:
            if hasattr(loaded, "close"):
                loaded.close()
        return xyz.astype(np.float32)

    @staticmethod
    def _write_npz_atomic(path: Path, key: str, value: np.ndarray) -> None:
        temporary = path.with_name(f".{path.name}.migrating")
        with temporary.open("wb") as output:
            np.savez_compressed(output, **{key: value})
        os.replace(temporary, path)
