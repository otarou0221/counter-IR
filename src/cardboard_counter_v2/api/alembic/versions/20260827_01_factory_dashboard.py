"""工場マップとカメラ配置を追加する。

Revision ID: 20260827_01
Revises: 20260826_01
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260827_01"
down_revision = "20260826_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "factory_maps" not in tables:
        op.create_table(
            "factory_maps",
            sa.Column("factory_map_id", sa.BigInteger(), primary_key=True),
            sa.Column("display_name", sa.String(length=100), nullable=False),
            sa.Column("factory_name", sa.String(length=100), nullable=True),
            sa.Column("floor_name", sa.String(length=100), nullable=True),
            sa.Column(
                "image_media_type",
                sa.String(length=50),
                nullable=False,
                server_default="image/png",
            ),
            sa.Column("image_width", sa.Integer(), nullable=False),
            sa.Column("image_height", sa.Integer(), nullable=False),
            sa.Column("image_data", sa.LargeBinary(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "image_width > 0", name="ck_factory_map_image_width"
            ),
            sa.CheckConstraint(
                "image_height > 0", name="ck_factory_map_image_height"
            ),
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "camera_map_placements" not in tables:
        op.create_table(
            "camera_map_placements",
            sa.Column(
                "camera_map_placement_id", sa.BigInteger(), primary_key=True
            ),
            sa.Column(
                "factory_map_id",
                sa.BigInteger(),
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
            sa.UniqueConstraint(
                "camera_id", name="uq_camera_map_placement_camera"
            ),
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


def downgrade() -> None:
    op.drop_table("camera_map_placements")
    op.drop_table("factory_maps")
