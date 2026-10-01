"""リアルタイム測定をパレット校正だけで対象特定する。

Revision ID: 20260901_03
Revises: 20260901_02
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "20260901_03"
down_revision = "20260901_02"
branch_labels = None
depends_on = None


RESULT_SHAPE_CONSTRAINT = "ck_realtime_measurement_result_shape"
RESULT_SHAPE_SQL = (
    "(status = 'success'"
    " AND measurement_capture_id IS NOT NULL"
    " AND inventory_count IS NOT NULL"
    " AND volume_liters IS NOT NULL"
    " AND box_counts IS NOT NULL"
    " AND is_low_stock IS NOT NULL"
    " AND low_stock_threshold_liters IS NOT NULL"
    " AND email_rearm_margin_liters IS NOT NULL"
    " AND error_message IS NULL)"
    " OR (status = 'failed'"
    " AND measurement_capture_id IS NULL"
    " AND inventory_count IS NULL"
    " AND volume_liters IS NULL"
    " AND box_counts IS NULL"
    " AND is_low_stock IS NULL"
    " AND low_stock_threshold_liters IS NULL"
    " AND email_rearm_margin_liters IS NULL"
    " AND email_sent_at IS NULL"
    " AND error_message IS NOT NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "realtime_measurements" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("realtime_measurements")
    }
    if "camera_installation_id" not in columns:
        _require_complete_calibration_links(bind)
        return

    _drop_old_result_shape_constraint(bind)
    _assign_failed_measurements(bind)
    _require_complete_calibration_links(bind)
    _replace_installation_reference(bind)


def downgrade() -> None:
    raise RuntimeError(
        "測定失敗のパレット校正への分割は自動downgradeできません。"
        "バックアップから復元してください"
    )


def _drop_old_result_shape_constraint(bind: sa.Connection) -> None:
    constraints = sa.inspect(bind).get_check_constraints("realtime_measurements")
    if not any(item.get("name") == RESULT_SHAPE_CONSTRAINT for item in constraints):
        return
    with op.batch_alter_table("realtime_measurements") as batch:
        batch.drop_constraint(RESULT_SHAPE_CONSTRAINT, type_="check")


def _assign_failed_measurements(bind: sa.Connection) -> None:
    metadata = sa.MetaData()
    measurements = sa.Table(
        "realtime_measurements", metadata, autoload_with=bind
    )
    calibrations = sa.Table(
        "pallet_calibrations", metadata, autoload_with=bind
    )
    failed_rows = bind.execute(
        sa.select(measurements)
        .where(
            measurements.c.status == "failed",
            measurements.c.pallet_calibration_id.is_(None),
        )
        .order_by(measurements.c.id)
    ).mappings().all()

    for failed in failed_rows:
        candidates = bind.execute(
            sa.select(
                calibrations.c.pallet_calibration_id,
                calibrations.c.pallet_slot_id,
            )
            .where(
                calibrations.c.camera_installation_id
                == failed["camera_installation_id"],
                calibrations.c.created_at <= failed["finished_at"],
                sa.or_(
                    calibrations.c.invalidated_at.is_(None),
                    calibrations.c.invalidated_at >= failed["started_at"],
                ),
            )
            .order_by(
                calibrations.c.pallet_slot_id,
                calibrations.c.created_at.desc(),
                calibrations.c.pallet_calibration_id.desc(),
            )
        ).mappings().all()
        latest_by_slot: dict[int, int] = {}
        for candidate in candidates:
            latest_by_slot.setdefault(
                int(candidate["pallet_slot_id"]),
                int(candidate["pallet_calibration_id"]),
            )
        calibration_ids = list(latest_by_slot.values())
        if not calibration_ids:
            raise RuntimeError(
                "測定失敗に対応するパレット校正を特定できません: "
                f"realtime_measurement_id={failed['id']}"
            )

        bind.execute(
            sa.update(measurements)
            .where(measurements.c.id == failed["id"])
            .values(pallet_calibration_id=calibration_ids[0])
        )
        clone_values: dict[str, Any] = {
            column.name: (
                sa.null()
                if failed[column.name] is None
                else failed[column.name]
            )
            for column in measurements.columns
            if column.name not in {"id", "pallet_calibration_id"}
        }
        for calibration_id in calibration_ids[1:]:
            bind.execute(sa.insert(measurements).values(
                pallet_calibration_id=calibration_id,
                **clone_values,
            ))


def _require_complete_calibration_links(bind: sa.Connection) -> None:
    measurements = sa.Table(
        "realtime_measurements", sa.MetaData(), autoload_with=bind
    )
    missing = bind.scalar(
        sa.select(sa.func.count())
        .select_from(measurements)
        .where(measurements.c.pallet_calibration_id.is_(None))
    )
    if missing:
        raise RuntimeError(
            "pallet_calibration_idを特定できない測定履歴があります: "
            f"{missing}件"
        )


def _replace_installation_reference(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    with op.batch_alter_table("realtime_measurements") as batch:
        for index in inspector.get_indexes("realtime_measurements"):
            if (
                index.get("column_names") == ["camera_installation_id"]
                and index.get("name")
            ):
                batch.drop_index(index["name"])
        for foreign_key in inspector.get_foreign_keys("realtime_measurements"):
            if foreign_key["constrained_columns"] != ["camera_installation_id"]:
                continue
            if foreign_key.get("name"):
                batch.drop_constraint(foreign_key["name"], type_="foreignkey")
        batch.alter_column(
            "pallet_calibration_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
        batch.drop_column("camera_installation_id")
        batch.create_check_constraint(
            RESULT_SHAPE_CONSTRAINT,
            RESULT_SHAPE_SQL,
        )
