"""工場マップへ建物・工場棟名を追加する。

Revision ID: 20260831_02
Revises: 20260831_01
Create Date: 2026-08-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260831_02"
down_revision = "20260831_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("factory_maps")
    }
    if "building_name" not in columns:
        op.add_column(
            "factory_maps",
            sa.Column("building_name", sa.String(length=100), nullable=True),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("factory_maps")
    }
    if "building_name" in columns:
        op.drop_column("factory_maps", "building_name")
