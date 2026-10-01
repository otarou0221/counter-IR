"""リアルタイム測定から画面表示に必要な最新行だけを取得する。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.models import (
    PalletCalibrationRecord,
    RealtimeMeasurementRecord,
)


def latest_success_by_calibration(
    session: Session,
    calibration_ids: Sequence[int],
) -> dict[int, RealtimeMeasurementRecord]:
    if not calibration_ids:
        return {}
    ranked = (
        select(
            RealtimeMeasurementRecord.id.label("measurement_id"),
            RealtimeMeasurementRecord.pallet_calibration_id,
            func.row_number().over(
                partition_by=RealtimeMeasurementRecord.pallet_calibration_id,
                order_by=(
                    RealtimeMeasurementRecord.finished_at.desc(),
                    RealtimeMeasurementRecord.id.desc(),
                ),
            ).label("recency_rank"),
        )
        .where(
            RealtimeMeasurementRecord.status == "success",
            RealtimeMeasurementRecord.pallet_calibration_id.in_(calibration_ids),
        )
        .subquery()
    )
    rows = session.scalars(
        select(RealtimeMeasurementRecord)
        .join(ranked, RealtimeMeasurementRecord.id == ranked.c.measurement_id)
        .where(ranked.c.recency_rank == 1)
    ).all()
    return {
        row.pallet_calibration_id: row
        for row in rows
    }


def latest_failure_by_installation(
    session: Session,
    calibration_ids: Sequence[int],
) -> dict[int, RealtimeMeasurementRecord]:
    if not calibration_ids:
        return {}
    ranked = (
        select(
            RealtimeMeasurementRecord.id.label("measurement_id"),
            PalletCalibrationRecord.camera_installation_id,
            func.row_number().over(
                partition_by=PalletCalibrationRecord.camera_installation_id,
                order_by=(
                    RealtimeMeasurementRecord.finished_at.desc(),
                    RealtimeMeasurementRecord.id.desc(),
                ),
            ).label("recency_rank"),
        )
        .join(
            PalletCalibrationRecord,
            RealtimeMeasurementRecord.pallet_calibration_id
            == PalletCalibrationRecord.pallet_calibration_id,
        )
        .where(
            RealtimeMeasurementRecord.status == "failed",
            RealtimeMeasurementRecord.pallet_calibration_id.in_(calibration_ids),
        )
        .subquery()
    )
    rows = session.execute(
        select(
            RealtimeMeasurementRecord,
            ranked.c.camera_installation_id,
        )
        .join(ranked, RealtimeMeasurementRecord.id == ranked.c.measurement_id)
        .where(ranked.c.recency_rank == 1)
    ).all()
    return {
        installation_id: row
        for row, installation_id in rows
    }
