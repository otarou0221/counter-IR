"""パレットの箱候補を単品と混在可能グループへ分離する。

Revision ID: 20260831_03
Revises: 20260831_02
Create Date: 2026-08-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_03"
down_revision = "20260831_02"
branch_labels = None
depends_on = None


def _json_type(bind: sa.Connection) -> sa.TypeEngine[object]:
    return postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    json_type = _json_type(bind)
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("pallet_slots")
    }
    with op.batch_alter_table("pallet_slots") as batch:
        if "single_box_labels" not in columns:
            batch.add_column(sa.Column(
                "single_box_labels",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ))
        if "mixed_box_groups" not in columns:
            batch.add_column(sa.Column(
                "mixed_box_groups",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ))
    if "target_box_labels" in columns:
        bind.execute(sa.text(
            "UPDATE pallet_slots SET single_box_labels = target_box_labels"
        ))
        with op.batch_alter_table("pallet_slots") as batch:
            batch.drop_column("target_box_labels")


def downgrade() -> None:
    bind = op.get_bind()
    json_type = _json_type(bind)
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("pallet_slots")
    }
    if "target_box_labels" not in columns:
        with op.batch_alter_table("pallet_slots") as batch:
            batch.add_column(sa.Column(
                "target_box_labels",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ))

    slots = sa.table(
        "pallet_slots",
        sa.column("pallet_slot_id", sa.BigInteger()),
        sa.column("single_box_labels", json_type),
        sa.column("mixed_box_groups", json_type),
        sa.column("target_box_labels", json_type),
    )
    for row in bind.execute(sa.select(
        slots.c.pallet_slot_id,
        slots.c.single_box_labels,
        slots.c.mixed_box_groups,
    )).mappings():
        labels: list[str] = []
        seen: set[str] = set()
        raw_labels = list(row["single_box_labels"] or [])
        raw_labels.extend(
            label
            for group in (row["mixed_box_groups"] or [])
            for label in group
        )
        for label in raw_labels:
            key = str(label).casefold()
            if key not in seen:
                seen.add(key)
                labels.append(str(label))
        bind.execute(
            sa.update(slots)
            .where(slots.c.pallet_slot_id == row["pallet_slot_id"])
            .values(target_box_labels=labels)
        )
    with op.batch_alter_table("pallet_slots") as batch:
        if "single_box_labels" in columns:
            batch.drop_column("single_box_labels")
        if "mixed_box_groups" in columns:
            batch.drop_column("mixed_box_groups")
