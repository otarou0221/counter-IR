"""カメラ別のROI参照撮影、選択、保持件数を管理する。"""

from __future__ import annotations

from pathlib import Path

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.state import CameraRuntimeState, RuntimeState, RuntimeStateStore
from cardboard_counter_v2.common.schemas import (
    CaptureManifest,
    RoiReferenceCapture,
    RoiReferenceCatalog,
)
from cardboard_counter_v2.common.capture_policy import FLOOR_CAPTURES_PER_CAMERA
from cardboard_counter_v2.common.storage import capture_relative_dir, data_root


MAX_FLOOR_CAPTURES_PER_CAMERA = FLOOR_CAPTURES_PER_CAMERA


class RoiReferenceService:
    """測定処理から独立して、設定用撮影のライフサイクルだけを扱う。"""

    def __init__(
        self,
        state_store: RuntimeStateStore,
        history: InventoryHistoryService,
        root: Path | None = None,
    ) -> None:
        self.state_store = state_store
        self.history = history
        self.root = root or data_root()

    def catalog(self) -> RoiReferenceCatalog:
        state = self.state_store.load()
        references: list[RoiReferenceCapture] = []
        for camera_id, camera_state in state.cameras.items():
            capture_id = camera_state.baseline_capture_id
            if capture_id is None:
                continue
            try:
                manifest = self.load_manifest(capture_id)
            except ValueError:
                continue
            if manifest.camera_id == camera_id:
                references.append(reference_from_manifest(manifest))
        return RoiReferenceCatalog(
            captures=references,
            floor_captures=[
                summary_from_manifest(item)
                for item in self.history.list_captures(
                    purpose="floor", retention="persistent"
                )
            ],
            floor_capture_limit=MAX_FLOOR_CAPTURES_PER_CAMERA,
        )

    def select_floor(self, camera_id: str, capture_id: str) -> CaptureManifest:
        manifest = self.load_manifest(capture_id)
        if manifest.camera_id != camera_id:
            raise ValueError("選択した床撮影のカメラが一致しません")
        if manifest.purpose != "floor" or manifest.retention != "persistent":
            raise ValueError("永続保存された床撮影だけを選択できます")
        if manifest.depth_aligned_to_color or manifest.color_shape != manifest.depth_shape:
            raise ValueError("IRと同じ画素格子の未整列Depthが必要です")
        self.validate_capture_files(manifest)
        self.activate(manifest)
        return manifest

    def activate(self, manifest: CaptureManifest) -> None:
        current = self.state_store.load()
        states = dict(current.cameras)
        states[manifest.camera_id] = CameraRuntimeState(
            baseline_capture_id=manifest.capture_id,
            calibration_id=None,
        )
        self.state_store.save(RuntimeState(cameras=states))

    def excess_floor_capture_ids(self, camera_id: str) -> list[str]:
        captures = self.history.list_captures(
            camera_id=camera_id, purpose="floor", retention="persistent"
        )
        overflow = max(0, len(captures) - MAX_FLOOR_CAPTURES_PER_CAMERA)
        if overflow == 0:
            return []
        protected = self.state_store.load().camera(camera_id).baseline_capture_id
        oldest_first = reversed(captures)
        removable = [item.capture_id for item in oldest_first if item.capture_id != protected]
        return removable[:overflow]

    def load_manifest(self, capture_id: str) -> CaptureManifest:
        try:
            return self.history.load_capture(capture_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"保存撮影を読み込めません: {capture_id}") from exc

    def validate_capture_files(self, manifest: CaptureManifest) -> None:
        base = (self.root / capture_relative_dir(
            manifest.capture_id,
            camera_id=manifest.camera_id,
            purpose=manifest.purpose,
            storage_version=manifest.storage_version,
        )).resolve()
        for label, relative in (
            ("Depth", manifest.depth_path),
            ("IRプレビュー", manifest.rgb_path),
            ("IR生データ", manifest.ir_path),
            ("XYZ", manifest.xyz_path),
        ):
            if relative is None:
                raise ValueError(f"{label}の保存パスがありません")
            candidate = (self.root / relative).resolve()
            try:
                candidate.relative_to(base)
            except ValueError as exc:
                raise ValueError(f"{label}の保存パスが不正です") from exc
            if not candidate.is_file():
                raise ValueError(f"保存撮影の{label}が見つかりません: {manifest.capture_id}")


def reference_from_manifest(manifest: CaptureManifest) -> RoiReferenceCapture:
    return RoiReferenceCapture(
        camera_id=manifest.camera_id,
        capture_id=manifest.capture_id,
        captured_at=manifest.captured_at,
        rgb_path=manifest.rgb_path,
    )


def summary_from_manifest(manifest: CaptureManifest):
    from cardboard_counter_v2.common.schemas import SavedCaptureSummary

    return SavedCaptureSummary(
        capture_id=manifest.capture_id,
        camera_id=manifest.camera_id,
        purpose=manifest.purpose,
        retention=manifest.retention,
        captured_at=manifest.captured_at or "",
        frame_count=manifest.frame_count,
        color_shape=manifest.color_shape,
        depth_shape=manifest.depth_shape,
        rgb_path=manifest.rgb_path,
    )
