"""設定値のDB制約をUI・APIの入力規則へそろえる。

Revision ID: 20260828_02
Revises: 20260828_01
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260828_02"
down_revision = "20260828_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE pallet_slots
        SET low_stock_threshold_liters = 1
        WHERE low_stock_threshold_liters <= 0
    """))
    bind.execute(sa.text("""
        UPDATE pallet_slots
        SET email_rearm_margin_liters = 1
        WHERE email_rearm_margin_liters <= 0
    """))
    bind.execute(sa.text("""
        UPDATE measurement_settings
        SET measurement_interval_seconds = CASE
            WHEN measurement_interval_seconds < 60 THEN 60
            WHEN measurement_interval_seconds > 3600 THEN 3600
            ELSE ((measurement_interval_seconds + 30) / 60) * 60
        END
    """))

    with op.batch_alter_table("pallet_slots") as batch:
        batch.drop_constraint("ck_pallet_slot_low_stock_threshold", type_="check")
        batch.drop_constraint("ck_pallet_slot_email_rearm_margin", type_="check")
        batch.create_check_constraint(
            "ck_pallet_slot_low_stock_threshold",
            "low_stock_threshold_liters > 0",
        )
        batch.create_check_constraint(
            "ck_pallet_slot_email_rearm_margin",
            "email_rearm_margin_liters > 0",
        )

    with op.batch_alter_table("measurement_settings") as batch:
        batch.drop_constraint("ck_measurement_interval", type_="check")
        batch.create_check_constraint(
            "ck_measurement_interval",
            "measurement_interval_seconds >= 60 AND "
            "measurement_interval_seconds <= 3600 AND "
            "measurement_interval_seconds % 60 = 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("pallet_slots") as batch:
        batch.drop_constraint("ck_pallet_slot_low_stock_threshold", type_="check")
        batch.drop_constraint("ck_pallet_slot_email_rearm_margin", type_="check")
        batch.create_check_constraint(
            "ck_pallet_slot_low_stock_threshold",
            "low_stock_threshold_liters >= 0",
        )
        batch.create_check_constraint(
            "ck_pallet_slot_email_rearm_margin",
            "email_rearm_margin_liters >= 0",
        )

    with op.batch_alter_table("measurement_settings") as batch:
        batch.drop_constraint("ck_measurement_interval", type_="check")
        batch.create_check_constraint(
            "ck_measurement_interval",
            "measurement_interval_seconds > 0",
        )
