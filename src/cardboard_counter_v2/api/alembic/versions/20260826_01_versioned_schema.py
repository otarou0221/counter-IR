"""既存DBをバージョン管理された現行スキーマへ移行する。

Revision ID: 20260826_01
Revises:
Create Date: 2026-08-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from cardboard_counter_v2.api.inventory.models import Base


revision = "20260826_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # 空DBはORM定義から現行スキーマを作る。既存DBは共有テーブルだけを
    # 非破壊で補完してから、存在しない新テーブルを作成する。
    if "cameras" not in tables:
        Base.metadata.create_all(bind=bind)
        return

    json_type = (
        postgresql.JSONB()
        if bind.dialect.name == "postgresql"
        else sa.JSON()
    )
    _add_columns("cameras", [
        sa.Column("intrinsics", json_type, nullable=True),
        sa.Column("distortion", json_type, nullable=True),
    ])

    if "camera_installations" in tables:
        _add_columns("camera_installations", [
            sa.Column("camera_service_url", sa.Text(), nullable=True),
            sa.Column(
                "driver", sa.String(length=64), nullable=False,
                server_default="orbbec_network",
            ),
            sa.Column("color_width", sa.Integer(), nullable=False, server_default="1280"),
            sa.Column("color_height", sa.Integer(), nullable=False, server_default="720"),
            sa.Column("depth_width", sa.Integer(), nullable=False, server_default="640"),
            sa.Column("depth_height", sa.Integer(), nullable=False, server_default="576"),
            sa.Column("fps", sa.Integer(), nullable=False, server_default="15"),
            sa.Column(
                "align_depth_to_color", sa.Boolean(), nullable=False,
                server_default=sa.true(),
            ),
        ])
        bind.execute(
            sa.text(
                "UPDATE camera_installations "
                "SET camera_service_url = "
                "'http://' || replace(camera_id, '_', '-') || :port_suffix "
                "WHERE camera_service_url IS NULL OR trim(camera_service_url) = ''"
            ),
            {"port_suffix": ":8001"},
        )
        op.alter_column(
            "camera_installations", "camera_service_url",
            existing_type=sa.Text(), nullable=False,
        )

    if "captures" in tables:
        _add_columns("captures", [
            sa.Column("storage_version", sa.Integer(), nullable=False, server_default="2"),
        ])

    if "pallet_slots" in tables:
        _add_columns("pallet_slots", [
            sa.Column(
                "plane_roi", json_type, nullable=False,
                server_default=sa.text("'[0.05, 0.15, 0.48, 0.95]'"),
            ),
            sa.Column(
                "target_box_labels", json_type, nullable=False,
                server_default=sa.text("'[\"cardboard_box\"]'"),
            ),
            sa.Column(
                "reference_box_label", sa.String(length=100), nullable=False,
                server_default="cardboard_box",
            ),
        ])

    if "measurement_settings" in tables:
        _add_columns("measurement_settings", [
            sa.Column("floor_frame_count", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("warmup_frames", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("grid_mm", sa.Float(), nullable=False, server_default="10.0"),
            sa.Column("pallet_height_mm", sa.Float(), nullable=False, server_default="150.0"),
            sa.Column(
                "pallet_roi_margin_mm", sa.Float(), nullable=False,
                server_default="100.0",
            ),
            sa.Column("occupied_height_mm", sa.Float(), nullable=False, server_default="30.0"),
        ])
        columns = _column_names("measurement_settings")
        if "model_class_source" in columns:
            op.drop_column("measurement_settings", "model_class_source")

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # 既存データを失う可能性があるため自動downgradeは提供しない。
    raise RuntimeError("このDB移行は自動downgradeできません。バックアップから復元してください")


def _column_names(table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _add_columns(table_name: str, columns: list[sa.Column[object]]) -> None:
    existing = _column_names(table_name)
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)
            existing.add(str(column.name))
