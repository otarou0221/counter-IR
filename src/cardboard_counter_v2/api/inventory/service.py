"""DB障害を測定処理から分離し、接続状態をAPIへ公開する。"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from threading import Lock
from collections.abc import Callable

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.common.schemas import (
    CalibrationResult,
    CaptureManifest,
    DatabaseStatus,
    MeasurementResponse,
    SystemSettings,
)
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition


LOGGER = logging.getLogger(__name__)


class InventoryHistoryService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = InventoryRepository(database)
        self._lock = Lock()
        self._connected = False
        self._last_saved_at: str | None = None
        self._last_error: str | None = None

    def status(self) -> DatabaseStatus:
        with self._lock:
            return DatabaseStatus(
                enabled=self.database.enabled,
                connected=self._connected if self.database.enabled else False,
                last_saved_at=self._last_saved_at,
                last_error=self._last_error,
            )

    def initialize(self, settings: SystemSettings) -> bool:
        if not self.database.enabled:
            return False
        return self._execute("DB初期化", self.repository.initialize, settings)

    def sync_settings(self, settings: SystemSettings) -> bool:
        if not self.database.enabled:
            return False
        return self._execute("在庫マスター同期", self.repository.sync_settings, settings)

    def register_capture(self, manifest: CaptureManifest) -> bool:
        if not self.database.enabled:
            return False
        return self._execute(
            "撮影台帳保存",
            self.repository.register_capture,
            manifest,
        )

    def load_capture(self, capture_id: str) -> CaptureManifest:
        if not self.database.enabled:
            raise RuntimeError("DBが設定されていません")
        return self.repository.load_capture(capture_id)

    def list_captures(
        self,
        *,
        camera_id: str | None = None,
        purpose: str | None = None,
        retention: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CaptureManifest]:
        if not self.database.enabled:
            raise RuntimeError("DBが設定されていません")
        return self.repository.list_captures(
            camera_id=camera_id,
            purpose=purpose,
            retention=retention,
            limit=limit,
            offset=offset,
        )

    def delete_capture_record(self, capture_id: str) -> bool:
        if not self.database.enabled:
            return False
        return self._execute(
            "撮影台帳削除", self.repository.delete_capture_record, capture_id
        )

    def excess_current_capture_ids(self, camera_id: str) -> list[str]:
        if not self.database.enabled:
            return []
        return self.repository.excess_current_capture_ids(camera_id)

    def record_success(
        self,
        result: MeasurementResponse,
        settings: SystemSettings,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> bool:
        if not self.database.enabled:
            return False
        return self._execute(
            "測定履歴保存",
            self.repository.record_success,
            result,
            settings,
            started_at=started_at,
            finished_at=finished_at,
        )

    def record_calibration(
        self, result: CalibrationResult, settings: SystemSettings
    ) -> bool:
        if not self.database.enabled:
            return False
        return self._execute(
            "校正履歴保存",
            self.repository.record_calibration,
            result,
            settings,
        )

    def load_calibration_definition(
        self, calibration_id: str
    ) -> PlanarCalibrationDefinition:
        if not self.database.enabled:
            raise RuntimeError("DBが設定されていません")
        try:
            definition = self.repository.load_calibration_definition(calibration_id)
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = f"校正定義読込みに失敗しました: {exc}"
            raise
        with self._lock:
            self._connected = True
            self._last_error = None
        return definition

    def load_active_calibrations(self) -> dict[str, tuple[str, str]]:
        if not self.database.enabled:
            raise RuntimeError("DBが設定されていません")
        try:
            calibrations = self.repository.load_active_calibrations()
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = f"有効校正読込みに失敗しました: {exc}"
            raise
        with self._lock:
            self._connected = True
            self._last_error = None
        return calibrations

    def record_failure(
        self,
        *,
        camera_id: str | None = None,
        started_at: datetime,
        finished_at: datetime,
        error_message: str,
    ) -> bool:
        if not self.database.enabled:
            return False
        return self._execute(
            "測定失敗履歴保存",
            self.repository.record_failure,
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
        if not self.database.enabled:
            return False
        return self._execute(
            "メール送信時刻保存",
            self.repository.mark_email_sent,
            calibration_id=calibration_id,
            pallet_number=pallet_number,
            finished_at=finished_at,
            sent_at=sent_at,
        )

    def prune_inventory_history(self) -> bool:
        if not self.database.enabled:
            return False
        return self._execute(
            "累積在庫履歴整理",
            self.repository.prune_inventory_history,
        )

    def dispose(self) -> None:
        self.database.dispose()

    def _execute(
        self,
        label: str,
        operation: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> bool:
        try:
            result = operation(*args, **kwargs)
        except Exception as exc:
            LOGGER.exception("%sに失敗しました", label)
            with self._lock:
                self._connected = False
                self._last_error = f"{label}に失敗しました: {exc}"
            return False
        with self._lock:
            self._connected = True
            self._last_error = None
            if label in {"測定履歴保存", "測定失敗履歴保存"}:
                self._last_saved_at = datetime.now(UTC).isoformat()
        return bool(result is not False)
