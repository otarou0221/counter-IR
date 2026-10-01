"""パレット校正履歴の保存と実行定義への復元。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    PalletCalibrationRecord,
    PalletSlotRecord,
)
from cardboard_counter_v2.api.inventory.installation_projection import (
    installation_projection,
)
from cardboard_counter_v2.api.inventory.repositories.capture_repository import (
    CaptureRepository,
)
from cardboard_counter_v2.api.inventory.repositories.settings_repository import (
    SettingsRepository,
)
from cardboard_counter_v2.common.planar_calibration import (
    PlanarCalibrationDefinition,
    PlanarRegionCalibration,
)
from cardboard_counter_v2.common.schemas import CalibrationResult, SystemSettings


class CalibrationRepository:
    def __init__(
        self,
        database: Database,
        settings: SettingsRepository,
        captures: CaptureRepository,
    ) -> None:
        self.database = database
        self.settings = settings
        self.captures = captures

    def record(
        self,
        result: CalibrationResult,
        settings: SystemSettings,
    ) -> bool:
        with self.database.session() as session:
            self.settings.sync_in_session(session, settings)
            return self.record_in_session(session, result, settings)

    def load_definition(self, calibration_id: str) -> PlanarCalibrationDefinition:
        with self.database.session() as session:
            return self.load_definition_in_session(session, calibration_id)

    def load_active(self) -> dict[str, tuple[str, str]]:
        with self.database.session() as session:
            rows = session.execute(
                select(
                    CameraInstallationRecord.camera_id,
                    PalletCalibrationRecord.calibration_capture_id,
                    PalletCalibrationRecord.calibration_id,
                )
                .join(
                    PalletCalibrationRecord,
                    PalletCalibrationRecord.camera_installation_id
                    == CameraInstallationRecord.camera_installation_id,
                )
                .where(
                    CameraInstallationRecord.removed_at.is_(None),
                    PalletCalibrationRecord.status == "active",
                )
                .distinct()
                .order_by(CameraInstallationRecord.camera_id)
            ).all()
            result: dict[str, tuple[str, str]] = {}
            for camera_id, capture_id, calibration_id in rows:
                value = (capture_id, calibration_id)
                previous = result.get(camera_id)
                if previous is not None and previous != value:
                    raise ValueError(f"有効な校正が複数あります: {camera_id}")
                result[camera_id] = value
            return result

    def record_in_session(
        self,
        session: Session,
        result: CalibrationResult,
        settings: SystemSettings,
    ) -> bool:
        self.captures.ensure_camera_parameters(session, result.baseline_capture_id)
        if session.scalar(
            select(PalletCalibrationRecord.pallet_calibration_id)
            .where(PalletCalibrationRecord.calibration_id == result.calibration_id)
            .limit(1)
        ) is not None:
            return False
        installation = self.active_installation(session, result.camera_id)
        created_at = datetime.fromisoformat(result.created_at)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        for active in session.scalars(
            select(PalletCalibrationRecord).where(
                PalletCalibrationRecord.camera_installation_id
                == installation.camera_installation_id,
                PalletCalibrationRecord.status == "active",
            )
        ).all():
            active.status = "superseded"
            active.invalidated_at = created_at

        pallet_settings = {pallet.pallet_id: pallet for pallet in settings.pallets}
        for pallet in result.pallets:
            configured = pallet_settings.get(pallet.pallet_id)
            if configured is None:
                raise ValueError(
                    f"校正対象の設置場所設定がありません: {pallet.pallet_id}"
                )
            if configured.pallet_number != pallet.pallet_number:
                raise ValueError(
                    "校正結果と設定のパレット番号が一致しません: "
                    f"{pallet.pallet_id}"
                )
            pallet_slot = session.scalar(
                select(PalletSlotRecord).where(
                    PalletSlotRecord.camera_installation_id
                    == installation.camera_installation_id,
                    PalletSlotRecord.pallet_number == pallet.pallet_number,
                )
            )
            if pallet_slot is None:
                raise ValueError(
                    "校正対象のパレット監視枠がありません: "
                    "camera_installation_id="
                    f"{installation.camera_installation_id} "
                    f"pallet={pallet.pallet_number}"
                )
            session.add(PalletCalibrationRecord(
                calibration_id=result.calibration_id,
                camera_installation_id=installation.camera_installation_id,
                pallet_slot_id=pallet_slot.pallet_slot_id,
                calibration_capture_id=result.baseline_capture_id,
                grid_mm=pallet.cell_size_mm,
                calibration_data={
                    "roi": list(pallet.plane_roi),
                    "floor_plane_normal": list(pallet.floor_plane_normal),
                    "floor_plane_offset": pallet.floor_plane_offset,
                    "pallet_height_mm": pallet.pallet_height_mm,
                },
                status="active",
                created_at=created_at,
            ))
        return True

    @staticmethod
    def load_definition_in_session(
        session: Session,
        calibration_id: str,
    ) -> PlanarCalibrationDefinition:
        records = session.scalars(
            select(PalletCalibrationRecord)
            .join(
                PalletSlotRecord,
                PalletCalibrationRecord.pallet_slot_id
                == PalletSlotRecord.pallet_slot_id,
            )
            .where(PalletCalibrationRecord.calibration_id == calibration_id)
            .order_by(PalletSlotRecord.pallet_number)
        ).all()
        if not records:
            raise ValueError(f"DBにパレット校正がありません: {calibration_id}")
        installation_ids = {record.camera_installation_id for record in records}
        capture_ids = {record.calibration_capture_id for record in records}
        if len(installation_ids) != 1 or len(capture_ids) != 1:
            raise ValueError(
                f"校正行のカメラまたはCaptureが一致しません: {calibration_id}"
            )
        installation = records[0].camera_installation
        camera = installation.camera
        if installation.intrinsics is None:
            raise ValueError(
                "カメラ設置履歴に内部パラメータがありません: "
                f"{installation.camera_installation_id}"
            )

        regions: list[PlanarRegionCalibration] = []
        for record in records:
            data = record.calibration_data
            try:
                regions.append(PlanarRegionCalibration(
                    region_id=record.pallet_slot.pallet_number,
                    roi=data["roi"],
                    reference_plane_normal=data["floor_plane_normal"],
                    reference_plane_offset=data["floor_plane_offset"],
                    surface_offset_mm=data["pallet_height_mm"],
                    cell_size_mm=record.grid_mm,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"パレット校正データが不正です: {record.pallet_calibration_id}"
                ) from exc
        return PlanarCalibrationDefinition(
            calibration_id=calibration_id,
            camera_id=camera.camera_id,
            calibration_capture_id=records[0].calibration_capture_id,
            projection=installation_projection(installation),
            regions=regions,
        )

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
    def require(session: Session, calibration_id: str) -> None:
        if session.scalar(
            select(PalletCalibrationRecord.pallet_calibration_id)
            .where(PalletCalibrationRecord.calibration_id == calibration_id)
            .limit(1)
        ) is None:
            raise ValueError(f"DBにパレット校正がありません: {calibration_id}")

    @staticmethod
    def get_pallet(
        session: Session,
        calibration_id: str,
        pallet_number: int,
    ) -> PalletCalibrationRecord:
        record = session.scalar(
            select(PalletCalibrationRecord)
            .join(
                PalletSlotRecord,
                PalletCalibrationRecord.pallet_slot_id
                == PalletSlotRecord.pallet_slot_id,
            )
            .where(
                PalletCalibrationRecord.calibration_id == calibration_id,
                PalletSlotRecord.pallet_number == pallet_number,
            )
        )
        if record is None:
            raise ValueError(
                "パレット校正履歴が見つかりません: "
                f"{calibration_id} pallet={pallet_number}"
            )
        return record
