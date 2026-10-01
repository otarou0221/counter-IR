"""撮影台帳とカメラ固有パラメータを管理する。"""

from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    CaptureRecord,
)
from cardboard_counter_v2.api.inventory.installation_projection import (
    capture_parameters,
    installation_projection,
    parameters_match,
    validate_capture_mode,
)
from cardboard_counter_v2.common.schemas import CaptureManifest
from cardboard_counter_v2.common.capture_policy import CURRENT_CAPTURES_PER_CAMERA
from cardboard_counter_v2.common.storage import capture_relative_dir


class CaptureRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def register(
        self,
        manifest: CaptureManifest,
        *,
        allow_unrecorded_distortion: bool = False,
    ) -> bool:
        if manifest.projection is None:
            raise ValueError(
                f"撮影台帳に投影パラメータがありません: {manifest.capture_id}"
            )
        with self.database.session() as session:
            installation = self.active_installation(session, manifest.camera_id)
            self.register_installation_parameters(
                session,
                installation,
                manifest,
                allow_unrecorded_distortion=allow_unrecorded_distortion,
            )
            if session.get(CaptureRecord, manifest.capture_id) is not None:
                return False
            self.add_record(session, manifest, installation)
            return True

    def load(self, capture_id: str) -> CaptureManifest:
        with self.database.session() as session:
            record = session.get(CaptureRecord, capture_id)
            if record is None:
                raise ValueError(f"撮影台帳が見つかりません: {capture_id}")
            return self.to_manifest(record)

    def list(
        self,
        *,
        camera_id: str | None = None,
        purpose: str | None = None,
        retention: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CaptureManifest]:
        with self.database.session() as session:
            query = select(CaptureRecord)
            if camera_id is not None:
                query = query.join(CameraInstallationRecord).where(
                    CameraInstallationRecord.camera_id == camera_id
                )
            if purpose is not None:
                query = query.where(CaptureRecord.purpose == purpose)
            if retention is not None:
                query = query.where(CaptureRecord.retention == retention)
            query = query.order_by(
                CaptureRecord.captured_at.desc(),
                CaptureRecord.capture_id.desc(),
            ).offset(offset)
            if limit is not None:
                query = query.limit(limit)
            records = session.scalars(query).all()
            return [self.to_manifest(record) for record in records]

    def delete(self, capture_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(CaptureRecord, capture_id)
            if record is None:
                return False
            session.delete(record)
            return True

    def excess_current_ids(self, camera_id: str) -> list[str]:
        if CURRENT_CAPTURES_PER_CAMERA == 0:
            return []
        with self.database.session() as session:
            return list(session.scalars(
                select(CaptureRecord.capture_id)
                .join(CameraInstallationRecord)
                .where(
                    CameraInstallationRecord.camera_id == camera_id,
                    CaptureRecord.purpose == "current",
                )
                .order_by(
                    CaptureRecord.captured_at.desc(),
                    CaptureRecord.capture_id.desc(),
                )
                .offset(CURRENT_CAPTURES_PER_CAMERA)
            ).all())

    @classmethod
    def add_record(
        cls,
        session: Session,
        manifest: CaptureManifest,
        installation: CameraInstallationRecord,
    ) -> None:
        session.add(CaptureRecord(
            capture_id=manifest.capture_id,
            camera_installation_id=installation.camera_installation_id,
            purpose=manifest.purpose,
            retention=manifest.retention,
            source_batch_id=manifest.source_batch_id,
            storage_version=manifest.storage_version,
            captured_at=cls.parse_capture_time(manifest.captured_at),
            frame_count=manifest.frame_count,
        ))

    def ensure_camera_parameters(self, session: Session, capture_id: str) -> None:
        record = session.get(CaptureRecord, capture_id)
        if record is None:
            raise ValueError(f"撮影台帳が見つかりません: {capture_id}")
        self.register_installation_parameters(
            session,
            record.camera_installation,
            self.to_manifest(record),
        )

    def register_installation_parameters(
        self,
        session: Session,
        installation: CameraInstallationRecord,
        manifest: CaptureManifest,
        *,
        allow_unrecorded_distortion: bool = False,
    ) -> bool:
        del session
        validate_capture_mode(installation, manifest)
        intrinsics, distortion = capture_parameters(manifest)
        if installation.intrinsics is None:
            installation.intrinsics = intrinsics
            installation.distortion = distortion
            return True
        if installation.distortion is None and distortion is not None:
            if parameters_match(
                installation.intrinsics,
                None,
                intrinsics,
                None,
            ):
                # 旧CaptureのNULLは歪みなしではなく未記録。最初の新規撮影で補完する。
                installation.distortion = distortion
                return True
        if not parameters_match(
            installation.intrinsics,
            installation.distortion,
            intrinsics,
            distortion,
            allow_unrecorded_distortion=allow_unrecorded_distortion,
        ):
            raise ValueError(
                "カメラマスターと撮影時の内部・歪みパラメータが"
                f"一致しません: {manifest.camera_id}"
            )
        return False

    def validate_camera_parameters(
        self,
        manifest: CaptureManifest,
        *,
        allow_unrecorded_distortion: bool = False,
    ) -> None:
        with self.database.session() as session:
            installation = self.active_installation(session, manifest.camera_id)
            validate_capture_mode(installation, manifest)
            if installation.intrinsics is None:
                return
            intrinsics, distortion = capture_parameters(manifest)
            if not parameters_match(
                installation.intrinsics,
                installation.distortion,
                intrinsics,
                distortion,
                allow_unrecorded_distortion=allow_unrecorded_distortion,
            ):
                raise ValueError(
                    "カメラマスターと撮影時の内部・歪みパラメータが"
                    f"一致しません: {manifest.camera_id}"
                )

    @staticmethod
    def parse_capture_time(value: str | None) -> datetime:
        captured_at = datetime.fromisoformat(value) if value else datetime.now(UTC)
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
        return captured_at

    @staticmethod
    def active_installation(
        session: Session,
        camera_id: str,
    ) -> CameraInstallationRecord:
        installation = session.scalar(
            select(CameraInstallationRecord)
            .where(
                CameraInstallationRecord.camera_id == camera_id,
                CameraInstallationRecord.removed_at.is_(None),
            )
            .order_by(CameraInstallationRecord.camera_installation_id.desc())
            .limit(1)
        )
        if installation is None:
            raise ValueError(f"有効なカメラ設置履歴がありません: {camera_id}")
        return installation

    @staticmethod
    def to_manifest(record: CaptureRecord) -> CaptureManifest:
        installation = record.camera_installation
        relative = capture_relative_dir(
            record.capture_id,
            camera_id=installation.camera_id,
            purpose=record.purpose,
            storage_version=record.storage_version,
        )
        return CaptureManifest(
            capture_id=record.capture_id,
            camera_id=installation.camera_id,
            purpose=record.purpose,
            retention=record.retention,  # type: ignore[arg-type]
            source_batch_id=record.source_batch_id,
            storage_version=record.storage_version,
            depth_path=str(relative / "depth.npz"),
            xyz_path=str(relative / "xyz.npz"),
            rgb_path=str(relative / "rgb.jpg"),
            ir_path=str(relative / "ir.npz"),
            projection=installation_projection(installation),
            distortion=installation.distortion,
            frame_count=record.frame_count,
            color_shape=(installation.color_height, installation.color_width),
            depth_shape=(installation.color_height, installation.color_width),
            depth_aligned_to_color=installation.align_depth_to_color,
            captured_at=record.captured_at.isoformat(),
        )
