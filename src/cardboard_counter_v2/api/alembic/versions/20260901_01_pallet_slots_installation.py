"""パレット監視枠をカメラ設置履歴へ直接紐づける。

Revision ID: 20260901_01
Revises: 20260831_03
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "20260901_01"
down_revision = "20260831_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("pallet_slots")
    }
    if "camera_installation_id" in columns and "location_id" not in columns:
        return
    if "location_id" not in columns:
        raise RuntimeError("pallet_slotsに移行元のlocation_idがありません")
    if "camera_installation_id" not in columns:
        op.add_column(
            "pallet_slots",
            sa.Column("camera_installation_id", sa.BigInteger(), nullable=True),
        )

    _drop_location_unique(bind)
    _assign_installations(bind)
    _replace_location_reference(bind)


def downgrade() -> None:
    raise RuntimeError(
        "パレット監視枠の設置履歴移行は自動downgradeできません。"
        "バックアップから復元してください"
    )


def _drop_location_unique(bind: sa.Connection) -> None:
    constraints = sa.inspect(bind).get_unique_constraints("pallet_slots")
    with op.batch_alter_table("pallet_slots") as batch:
        for constraint in constraints:
            if set(constraint["column_names"]) != {"location_id", "pallet_number"}:
                continue
            name = constraint.get("name")
            if name:
                batch.drop_constraint(name, type_="unique")


def _assign_installations(bind: sa.Connection) -> None:
    metadata = sa.MetaData()
    slots = sa.Table("pallet_slots", metadata, autoload_with=bind)
    installations = sa.Table("camera_installations", metadata, autoload_with=bind)
    table_names = set(sa.inspect(bind).get_table_names())
    calibrations = (
        sa.Table("pallet_calibrations", metadata, autoload_with=bind)
        if "pallet_calibrations" in table_names
        else None
    )

    installation_rows = bind.execute(sa.select(
        installations.c.camera_installation_id,
        installations.c.location_id,
        installations.c.removed_at,
    )).mappings().all()
    active_by_location: dict[int, list[int]] = defaultdict(list)
    all_by_location: dict[int, list[int]] = defaultdict(list)
    for row in installation_rows:
        installation_id = int(row["camera_installation_id"])
        location_id = int(row["location_id"])
        all_by_location[location_id].append(installation_id)
        if row["removed_at"] is None:
            active_by_location[location_id].append(installation_id)

    calibration_ids_by_slot: dict[int, set[int]] = defaultdict(set)
    if calibrations is not None:
        for row in bind.execute(sa.select(
            calibrations.c.pallet_slot_id,
            calibrations.c.camera_installation_id,
        )).mappings():
            calibration_ids_by_slot[int(row["pallet_slot_id"])].add(
                int(row["camera_installation_id"])
            )

    slot_rows = bind.execute(
        sa.select(slots).order_by(slots.c.pallet_slot_id)
    ).mappings().all()
    for row in slot_rows:
        slot_id = int(row["pallet_slot_id"])
        location_id = int(row["location_id"])
        active_ids = sorted(active_by_location.get(location_id, []))
        target_ids = set(active_ids)
        target_ids.update(calibration_ids_by_slot.get(slot_id, set()))
        if not target_ids:
            known_ids = sorted(all_by_location.get(location_id, []))
            if known_ids:
                target_ids.add(known_ids[-1])
        if not target_ids:
            raise RuntimeError(
                "パレット監視枠に対応するカメラ設置履歴がありません: "
                f"pallet_slot_id={slot_id}, location_id={location_id}"
            )

        primary_id = active_ids[-1] if active_ids else max(target_ids)
        bind.execute(
            sa.update(slots)
            .where(slots.c.pallet_slot_id == slot_id)
            .values(camera_installation_id=primary_id)
        )
        for installation_id in sorted(target_ids - {primary_id}):
            clone_values: dict[str, Any] = {
                column.name: row[column.name]
                for column in slots.columns
                if column.name
                not in {"pallet_slot_id", "location_id", "camera_installation_id"}
            }
            clone_values.update({
                "location_id": location_id,
                "camera_installation_id": installation_id,
            })
            result = bind.execute(sa.insert(slots).values(**clone_values))
            cloned_slot_id = int(result.inserted_primary_key[0])
            if calibrations is not None:
                bind.execute(
                    sa.update(calibrations)
                    .where(
                        calibrations.c.pallet_slot_id == slot_id,
                        calibrations.c.camera_installation_id == installation_id,
                    )
                    .values(pallet_slot_id=cloned_slot_id)
                )


def _replace_location_reference(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes("pallet_slots")
    for index in indexes:
        if index["column_names"] == ["location_id"] and index.get("name"):
            op.drop_index(index["name"], table_name="pallet_slots")

    foreign_keys = inspector.get_foreign_keys("pallet_slots")
    with op.batch_alter_table("pallet_slots") as batch:
        for foreign_key in foreign_keys:
            if foreign_key["constrained_columns"] != ["location_id"]:
                continue
            name = foreign_key.get("name")
            if name:
                batch.drop_constraint(name, type_="foreignkey")
        batch.alter_column(
            "camera_installation_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
        batch.create_foreign_key(
            "pallet_slots_camera_installation_id_fkey",
            "camera_installations",
            ["camera_installation_id"],
            ["camera_installation_id"],
        )
        batch.create_unique_constraint(
            "uq_pallet_slot_installation_number",
            ["camera_installation_id", "pallet_number"],
        )
        batch.create_index(
            "ix_pallet_slots_camera_installation_id",
            ["camera_installation_id"],
        )
        batch.drop_column("location_id")
