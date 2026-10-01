"""ROIの正本をパレット校正履歴へ集約する。

Revision ID: 20260901_02
Revises: 20260901_01
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260901_02"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("pallet_slots")
    }
    if "plane_roi" not in columns:
        return
    with op.batch_alter_table("pallet_slots") as batch:
        batch.drop_column("plane_roi")


def downgrade() -> None:
    raise RuntimeError(
        "ROIの校正履歴集約は自動downgradeできません。"
        "バックアップから復元してください"
    )
