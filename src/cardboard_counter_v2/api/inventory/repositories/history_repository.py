"""在庫変化の累積履歴と6か月保持を管理する。"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    InventoryHistoryRecord,
    PalletCalibrationRecord,
    PalletSlotRecord,
)


INVENTORY_HISTORY_MONTHS = 6


class InventoryHistoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._retention_lock = Lock()
        self._last_prune_date = None

    def add_if_changed(
        self,
        session: Session,
        pallet_calibration: PalletCalibrationRecord,
        values: dict[str, Any],
    ) -> bool:
        previous = self.latest(session, pallet_calibration)
        if (
            previous is not None
            and previous.inventory_count == values["inventory_count"]
        ):
            return False
        session.add(InventoryHistoryRecord(**values))
        return True

    def prune_if_due(self, session: Session, reference_time: datetime) -> None:
        with self._retention_lock:
            current_date = reference_time.date()
            if self._last_prune_date == current_date:
                return
            self._last_prune_date = current_date
        self.prune_in_session(session, reference_time)

    def prune(self, reference_time: datetime | None = None) -> None:
        effective_time = reference_time or datetime.now(UTC)
        with self.database.session() as session:
            self.prune_in_session(session, effective_time)
        with self._retention_lock:
            self._last_prune_date = effective_time.date()

    @classmethod
    def latest(
        cls,
        session: Session,
        pallet_calibration: PalletCalibrationRecord,
    ) -> InventoryHistoryRecord | None:
        location_id = cls.logical_location(pallet_calibration)
        return session.scalar(
            select(InventoryHistoryRecord)
            .join(
                PalletCalibrationRecord,
                InventoryHistoryRecord.pallet_calibration_id
                == PalletCalibrationRecord.pallet_calibration_id,
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
                CameraInstallationRecord.location_id == location_id,
                PalletSlotRecord.pallet_number
                == pallet_calibration.pallet_slot.pallet_number,
            )
            .order_by(
                InventoryHistoryRecord.finished_at.desc(),
                InventoryHistoryRecord.id.desc(),
            )
            .limit(1)
        )

    @staticmethod
    def logical_location(pallet_calibration: PalletCalibrationRecord) -> int:
        location_id = pallet_calibration.camera_installation.location_id
        if location_id is None:
            raise ValueError(
                "パレット校正に対応する設置場所がありません: "
                f"{pallet_calibration.pallet_calibration_id}"
            )
        return location_id

    @staticmethod
    def mark_email_sent(
        session: Session,
        *,
        pallet_calibration_id: int,
        finished_at: datetime,
        sent_at: datetime,
    ) -> None:
        history = session.scalar(
            select(InventoryHistoryRecord).where(
                InventoryHistoryRecord.pallet_calibration_id
                == pallet_calibration_id,
                InventoryHistoryRecord.finished_at == finished_at,
            )
        )
        if history is not None:
            history.email_sent_at = sent_at

    @staticmethod
    def prune_in_session(session: Session, reference_time: datetime) -> None:
        month_index = reference_time.year * 12 + reference_time.month - 1
        cutoff_month_index = month_index - INVENTORY_HISTORY_MONTHS
        cutoff_year, cutoff_month_zero_based = divmod(cutoff_month_index, 12)
        cutoff_month = cutoff_month_zero_based + 1
        cutoff_day = min(
            reference_time.day,
            calendar.monthrange(cutoff_year, cutoff_month)[1],
        )
        cutoff = reference_time.replace(
            year=cutoff_year,
            month=cutoff_month,
            day=cutoff_day,
        )
        session.execute(
            delete(InventoryHistoryRecord).where(
                InventoryHistoryRecord.finished_at < cutoff
            )
        )
