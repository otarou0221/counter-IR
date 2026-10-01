"""工場マップ配置をカメラ単位からパレット単位へ変更する。

Revision ID: 20260828_01
Revises: 20260827_01
Create Date: 2026-08-28
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260828_01"
down_revision = "20260827_01"
branch_labels = None
depends_on = None


def id_type() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def create_pallet_placements() -> None:
    op.create_table(
        "pallet_map_placements",
        sa.Column("pallet_map_placement_id", id_type(), primary_key=True),
        sa.Column(
            "factory_map_id",
            id_type(),
            sa.ForeignKey("factory_maps.factory_map_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pallet_slot_id",
            id_type(),
            sa.ForeignKey("pallet_slots.pallet_slot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position_x_ratio", sa.Float(), nullable=False),
        sa.Column("position_y_ratio", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "position_x_ratio >= 0 AND position_x_ratio <= 1",
            name="ck_pallet_map_placement_x_ratio",
        ),
        sa.CheckConstraint(
            "position_y_ratio >= 0 AND position_y_ratio <= 1",
            name="ck_pallet_map_placement_y_ratio",
        ),
        sa.UniqueConstraint(
            "pallet_slot_id", name="uq_pallet_map_placement_slot"
        ),
    )
    op.create_index(
        "ix_pallet_map_placements_factory_map_id",
        "pallet_map_placements",
        ["factory_map_id"],
    )
    op.create_index(
        "ix_pallet_map_placements_pallet_slot_id",
        "pallet_map_placements",
        ["pallet_slot_id"],
    )


def create_camera_placements() -> None:
    op.create_table(
        "camera_map_placements",
        sa.Column("camera_map_placement_id", id_type(), primary_key=True),
        sa.Column(
            "factory_map_id",
            id_type(),
            sa.ForeignKey("factory_maps.factory_map_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "camera_id",
            sa.String(length=64),
            sa.ForeignKey("cameras.camera_id"),
            nullable=False,
        ),
        sa.Column("position_x_ratio", sa.Float(), nullable=False),
        sa.Column("position_y_ratio", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "position_x_ratio >= 0 AND position_x_ratio <= 1",
            name="ck_camera_map_placement_x_ratio",
        ),
        sa.CheckConstraint(
            "position_y_ratio >= 0 AND position_y_ratio <= 1",
            name="ck_camera_map_placement_y_ratio",
        ),
        sa.UniqueConstraint("camera_id", name="uq_camera_map_placement_camera"),
    )
    op.create_index(
        "ix_camera_map_placements_factory_map_id",
        "camera_map_placements",
        ["factory_map_id"],
    )
    op.create_index(
        "ix_camera_map_placements_camera_id",
        "camera_map_placements",
        ["camera_id"],
    )


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "pallet_map_placements" not in tables:
        create_pallet_placements()

    if "camera_map_placements" in tables:
        slot_columns = {
            column["name"]
            for column in sa.inspect(bind).get_columns("pallet_slots")
        }
        slot_join = (
            "ps.camera_installation_id = ci.camera_installation_id"
            if "camera_installation_id" in slot_columns
            else "ps.location_id = ci.location_id"
        )
        rows = bind.execute(sa.text(f"""
            SELECT cmp.factory_map_id, cmp.camera_id,
                   cmp.position_x_ratio, cmp.position_y_ratio,
                   ps.pallet_slot_id
            FROM camera_map_placements AS cmp
            JOIN camera_installations AS ci
              ON ci.camera_id = cmp.camera_id AND ci.removed_at IS NULL
            JOIN pallet_slots AS ps ON {slot_join}
            ORDER BY cmp.camera_map_placement_id, ps.pallet_number
        """)).mappings()
        now = datetime.now(UTC)
        seen: set[int] = set()
        payload: list[dict[str, object]] = []
        for row in rows:
            pallet_slot_id = int(row["pallet_slot_id"])
            if pallet_slot_id in seen:
                continue
            seen.add(pallet_slot_id)
            payload.append({
                "factory_map_id": row["factory_map_id"],
                "pallet_slot_id": pallet_slot_id,
                "position_x_ratio": row["position_x_ratio"],
                "position_y_ratio": row["position_y_ratio"],
                "created_at": now,
                "updated_at": now,
            })
        if payload:
            placements = sa.table(
                "pallet_map_placements",
                sa.column("factory_map_id", id_type()),
                sa.column("pallet_slot_id", id_type()),
                sa.column("position_x_ratio", sa.Float()),
                sa.column("position_y_ratio", sa.Float()),
                sa.column("created_at", sa.DateTime(timezone=True)),
                sa.column("updated_at", sa.DateTime(timezone=True)),
            )
            bind.execute(placements.insert(), payload)
        op.drop_table("camera_map_placements")


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "camera_map_placements" not in tables:
        create_camera_placements()

    if "pallet_map_placements" in tables:
        rows = bind.execute(sa.text("""
            SELECT pmp.factory_map_id, ci.camera_id,
                   pmp.position_x_ratio, pmp.position_y_ratio
            FROM pallet_map_placements AS pmp
            JOIN pallet_slots AS ps ON ps.pallet_slot_id = pmp.pallet_slot_id
            JOIN camera_installations AS ci
              ON ci.location_id = ps.location_id AND ci.removed_at IS NULL
            ORDER BY pmp.pallet_map_placement_id
        """)).mappings()
        now = datetime.now(UTC)
        seen: set[str] = set()
        payload: list[dict[str, object]] = []
        for row in rows:
            camera_id = str(row["camera_id"])
            if camera_id in seen:
                continue
            seen.add(camera_id)
            payload.append({
                "factory_map_id": row["factory_map_id"],
                "camera_id": camera_id,
                "position_x_ratio": row["position_x_ratio"],
                "position_y_ratio": row["position_y_ratio"],
                "created_at": now,
                "updated_at": now,
            })
        if payload:
            placements = sa.table(
                "camera_map_placements",
                sa.column("factory_map_id", id_type()),
                sa.column("camera_id", sa.String(length=64)),
                sa.column("position_x_ratio", sa.Float()),
                sa.column("position_y_ratio", sa.Float()),
                sa.column("created_at", sa.DateTime(timezone=True)),
                sa.column("updated_at", sa.DateTime(timezone=True)),
            )
            bind.execute(placements.insert(), payload)
        op.drop_table("pallet_map_placements")
