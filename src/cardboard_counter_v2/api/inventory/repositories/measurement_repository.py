"""リアルタイム測定、失敗履歴、メール送信結果を管理する。"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.domain import evaluate_low_stock
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    PalletCalibrationRecord,
    PalletSlotRecord,
    RealtimeMeasurementRecord,
)
from cardboard_counter_v2.api.inventory.repositories.calibration_repository import (
    CalibrationRepository,
)
from cardboard_counter_v2.api.inventory.repositories.history_repository import (
    InventoryHistoryRepository,
)
from cardboard_counter_v2.common.schemas import MeasurementResponse, SystemSettings


REALTIME_RETENTION = timedelta(days=7)


class MeasurementRepository:
    def __init__(
        self,
        database: Database,
        calibrations: CalibrationRepository,
        history: InventoryHistoryRepository,
    ) -> None:
        self.database = database
        self.calibrations = calibrations
        self.history = history

    def record_success(
        self,
        result: MeasurementResponse,
        settings: SystemSettings,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> bool:
        with self.database.session() as session:
            existing = session.scalar(
                select(RealtimeMeasurementRecord.id).where(
                    RealtimeMeasurementRecord.finished_at == finished_at,
                    RealtimeMeasurementRecord.status == "success",
                )
            )
            if existing is not None:
                return False
            if not result.pallets:
                raise ValueError("保存するパレット測定結果がありません")
            self.history.prune_if_due(session, finished_at)
            for camera_run in result.camera_runs:
                self.calibrations.require(session, camera_run.calibration_id)
            camera_runs = {
                camera_run.camera_id: camera_run
                for camera_run in result.camera_runs
            }
            pallets = {pallet.pallet_id: pallet for pallet in settings.pallets}
            for measured in result.pallets:
                pallet = pallets.get(measured.pallet_id)
                if pallet is None or not pallet.enabled:
                    raise ValueError(
                        "測定結果のパレット設定が見つかりません: "
                        f"{measured.pallet_id}"
                    )
                counts = (
                    dict(measured.box_combination.best.counts)
                    if measured.box_combination is not None
                    else {}
                )
                inventory_count = (
                    sum(counts.values())
                    if measured.box_combination is not None
                    else max(int(round(measured.estimated_boxes)), 0)
                )
                camera_run = camera_runs.get(measured.camera_id)
                if camera_run is None:
                    raise ValueError(
                        "測定結果のカメラ履歴が見つかりません: "
                        f"{measured.camera_id}"
                    )
                calibration = self.calibrations.get_pallet(
                    session,
                    camera_run.calibration_id,
                    pallet.pallet_number,
                )
                threshold = calibration.pallet_slot.low_stock_threshold_liters
                decision = evaluate_low_stock(
                    max(float(measured.volume_liters), 0.0),
                    threshold,
                )
                values = {
                    "pallet_calibration_id": calibration.pallet_calibration_id,
                    "measurement_capture_id": camera_run.current_capture_id,
                    "finished_at": finished_at,
                    "inventory_count": inventory_count,
                    "volume_liters": max(float(measured.volume_liters), 0.0),
                    "box_counts": counts,
                    "is_low_stock": decision.is_low_stock,
                    "low_stock_threshold_liters": threshold,
                    "email_rearm_margin_liters": (
                        calibration.pallet_slot.email_rearm_margin_liters
                    ),
                    "email_sent_at": None,
                }
                session.add(RealtimeMeasurementRecord(
                    started_at=started_at,
                    status="success",
                    **values,
                ))
                self.history.add_if_changed(session, calibration, values)
            session.flush()
            self.prune_realtime(session, camera_runs, finished_at)
            return True

    def record_failure(
        self,
        *,
        camera_id: str | None = None,
        started_at: datetime,
        finished_at: datetime,
        error_message: str,
    ) -> None:
        with self.database.session() as session:
            query = (
                select(
                    PalletCalibrationRecord,
                    CameraInstallationRecord.camera_id,
                )
                .join(
                    PalletSlotRecord,
                    PalletCalibrationRecord.pallet_slot_id
                    == PalletSlotRecord.pallet_slot_id,
                )
                .join(
                    CameraInstallationRecord,
                    PalletSlotRecord.camera_installation_id
                    == CameraInstallationRecord.camera_installation_id,
                )
                .where(
                    PalletCalibrationRecord.status == "active",
                    PalletSlotRecord.monitoring_enabled.is_(True),
                    CameraInstallationRecord.removed_at.is_(None),
                )
            )
            if camera_id is not None:
                query = query.where(CameraInstallationRecord.camera_id == camera_id)
            calibration_rows = session.execute(query).all()
            if not calibration_rows:
                raise ValueError("測定失敗に対応する有効パレット校正がありません")
            for calibration, _failed_camera_id in calibration_rows:
                session.add(RealtimeMeasurementRecord(
                    pallet_calibration_id=calibration.pallet_calibration_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="failed",
                    error_message=error_message[:4_000],
                ))
            session.flush()
            self.prune_realtime(
                session,
                {_camera_id for _calibration, _camera_id in calibration_rows},
                finished_at,
            )

    def mark_email_sent(
        self,
        *,
        calibration_id: str,
        pallet_number: int,
        finished_at: datetime,
        sent_at: datetime,
    ) -> bool:
        with self.database.session() as session:
            record = session.scalar(
                select(RealtimeMeasurementRecord)
                .join(
                    PalletCalibrationRecord,
                    RealtimeMeasurementRecord.pallet_calibration_id
                    == PalletCalibrationRecord.pallet_calibration_id,
                )
                .join(
                    PalletSlotRecord,
                    PalletCalibrationRecord.pallet_slot_id
                    == PalletSlotRecord.pallet_slot_id,
                )
                .where(
                    PalletCalibrationRecord.calibration_id == calibration_id,
                    PalletSlotRecord.pallet_number == pallet_number,
                    RealtimeMeasurementRecord.finished_at == finished_at,
                    RealtimeMeasurementRecord.status == "success",
                )
            )
            if record is None:
                raise ValueError("メール送信元の測定履歴が見つかりません")
            record.email_sent_at = sent_at
            assert record.pallet_calibration_id is not None
            self.history.mark_email_sent(
                session,
                pallet_calibration_id=record.pallet_calibration_id,
                finished_at=finished_at,
                sent_at=sent_at,
            )
            return True

    @staticmethod
    def prune_realtime(
        session: Session,
        camera_ids: Collection[str],
        reference_time: datetime,
    ) -> None:
        if not camera_ids:
            return
        calibration_ids = select(
            PalletCalibrationRecord.pallet_calibration_id
        ).join(
            CameraInstallationRecord,
            PalletCalibrationRecord.camera_installation_id
            == CameraInstallationRecord.camera_installation_id,
        ).where(CameraInstallationRecord.camera_id.in_(camera_ids))
        session.execute(delete(RealtimeMeasurementRecord).where(
            RealtimeMeasurementRecord.pallet_calibration_id.in_(calibration_ids),
            RealtimeMeasurementRecord.finished_at
            < reference_time - REALTIME_RETENTION,
        ))
