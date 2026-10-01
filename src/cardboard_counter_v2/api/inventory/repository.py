"""用途別DBリポジトリを束ねる後方互換ファサード。"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repositories import (
    CalibrationRepository,
    CaptureRepository,
    InventoryHistoryRepository,
    MeasurementRepository,
    SettingsRepository,
)
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition
from cardboard_counter_v2.common.schemas import (
    CalibrationResult,
    CaptureManifest,
    MeasurementResponse,
    SystemSettings,
)


class InventoryRepository:
    """既存サービス向け入口。SQL実装は5つの専用Repositoryへ委譲する。"""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.settings = SettingsRepository(database)
        self.captures = CaptureRepository(database)
        self.calibrations = CalibrationRepository(
            database,
            self.settings,
            self.captures,
        )
        self.inventory_history = InventoryHistoryRepository(database)
        self.measurements = MeasurementRepository(
            database,
            self.calibrations,
            self.inventory_history,
        )

    def initialize(self, settings: SystemSettings) -> None:
        self.settings.initialize(settings)

    def sync_settings(self, settings: SystemSettings) -> None:
        self.settings.sync(settings)

    def sync_settings_in_session(
        self,
        session: Session,
        settings: SystemSettings,
    ) -> None:
        self.settings.sync_in_session(session, settings)

    # 旧テスト・保守コードの互換名。測定保存からは呼び出さない。
    _sync_settings = staticmethod(SettingsRepository.sync_in_session)

    def load_settings(self) -> SystemSettings | None:
        return self.settings.load()

    def register_capture(self, manifest: CaptureManifest) -> bool:
        return self.captures.register(manifest)

    def load_capture(self, capture_id: str) -> CaptureManifest:
        return self.captures.load(capture_id)

    def list_captures(
        self,
        *,
        camera_id: str | None = None,
        purpose: str | None = None,
        retention: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CaptureManifest]:
        return self.captures.list(
            camera_id=camera_id,
            purpose=purpose,
            retention=retention,
            limit=limit,
            offset=offset,
        )

    def delete_capture_record(self, capture_id: str) -> bool:
        return self.captures.delete(capture_id)

    def excess_current_capture_ids(self, camera_id: str) -> list[str]:
        return self.captures.excess_current_ids(camera_id)

    def record_calibration(
        self,
        result: CalibrationResult,
        settings: SystemSettings,
    ) -> bool:
        return self.calibrations.record(result, settings)

    def load_calibration_definition(
        self,
        calibration_id: str,
    ) -> PlanarCalibrationDefinition:
        return self.calibrations.load_definition(calibration_id)

    def load_active_calibrations(self) -> dict[str, tuple[str, str]]:
        return self.calibrations.load_active()

    def record_success(
        self,
        result: MeasurementResponse,
        settings: SystemSettings,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> bool:
        return self.measurements.record_success(
            result,
            settings,
            started_at=started_at,
            finished_at=finished_at,
        )

    def record_failure(
        self,
        *,
        camera_id: str | None = None,
        started_at: datetime,
        finished_at: datetime,
        error_message: str,
    ) -> None:
        self.measurements.record_failure(
            camera_id=camera_id,
            started_at=started_at,
            finished_at=finished_at,
            error_message=error_message,
        )

    def mark_email_sent(
        self,
        *,
        calibration_id: str,
        pallet_number: int,
        finished_at: datetime,
        sent_at: datetime,
    ) -> bool:
        return self.measurements.mark_email_sent(
            calibration_id=calibration_id,
            pallet_number=pallet_number,
            finished_at=finished_at,
            sent_at=sent_at,
        )

    def prune_inventory_history(
        self,
        reference_time: datetime | None = None,
    ) -> None:
        self.inventory_history.prune(reference_time)
