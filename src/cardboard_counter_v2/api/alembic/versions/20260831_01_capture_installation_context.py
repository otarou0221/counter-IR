"""撮影条件を設置履歴へ集約し、場所IDを数値化する。

Revision ID: 20260831_01
Revises: 20260828_02
Create Date: 2026-08-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_01"
down_revision = "20260828_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    location_type = next(
        column["type"]
        for column in inspector.get_columns("locations")
        if column["name"] == "location_id"
    )
    if not isinstance(location_type, sa.Integer):
        _convert_location_ids(bind)

    inspector = sa.inspect(bind)
    location_columns = {
        column["name"] for column in inspector.get_columns("locations")
    }
    for name in ("building_name", "floor_name"):
        if name not in location_columns:
            op.add_column(
                "locations",
                sa.Column(name, sa.String(length=100), nullable=True),
            )

    installation_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("camera_installations")
    }
    json_type = (
        postgresql.JSONB()
        if bind.dialect.name == "postgresql"
        else sa.JSON()
    )
    for name in ("intrinsics", "distortion"):
        if name not in installation_columns:
            op.add_column(
                "camera_installations",
                sa.Column(name, json_type, nullable=True),
            )

    capture_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("captures")
    }
    if "camera_installation_id" not in capture_columns:
        _move_capture_context(bind)

    camera_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("cameras")
    }
    for name in ("intrinsics", "distortion"):
        if name in camera_columns:
            op.drop_column("cameras", name)


def _convert_location_ids(bind: sa.Connection) -> None:
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            "文字列場所IDを持つ旧DBの移行はPostgreSQLで実行してください"
        )
    bind.execute(sa.text("CREATE SEQUENCE locations_location_id_seq"))
    bind.execute(sa.text("""
        ALTER TABLE locations
        ADD COLUMN location_id_v2 BIGINT
        DEFAULT nextval('locations_location_id_seq')
    """))
    bind.execute(sa.text("""
        ALTER TABLE camera_installations
        ADD COLUMN location_id_v2 BIGINT
    """))
    bind.execute(sa.text("""
        ALTER TABLE pallet_slots
        ADD COLUMN location_id_v2 BIGINT
    """))
    bind.execute(sa.text("""
        UPDATE camera_installations AS ci
        SET location_id_v2 = l.location_id_v2
        FROM locations AS l
        WHERE ci.location_id = l.location_id
    """))
    bind.execute(sa.text("""
        UPDATE pallet_slots AS ps
        SET location_id_v2 = l.location_id_v2
        FROM locations AS l
        WHERE ps.location_id = l.location_id
    """))
    missing = bind.execute(sa.text("""
        SELECT
          (SELECT count(*) FROM camera_installations WHERE location_id_v2 IS NULL)
          + (SELECT count(*) FROM pallet_slots WHERE location_id_v2 IS NULL)
    """)).scalar_one()
    if missing:
        raise RuntimeError("数値場所IDへ変換できない関連データがあります")

    bind.execute(sa.text("""
        ALTER TABLE camera_installations DROP COLUMN location_id CASCADE;
        ALTER TABLE pallet_slots DROP COLUMN location_id CASCADE;
        ALTER TABLE locations DROP COLUMN location_id CASCADE;
        ALTER TABLE locations RENAME COLUMN location_id_v2 TO location_id;
        ALTER TABLE camera_installations RENAME COLUMN location_id_v2 TO location_id;
        ALTER TABLE pallet_slots RENAME COLUMN location_id_v2 TO location_id;
        ALTER TABLE locations ALTER COLUMN location_id SET NOT NULL;
        ALTER TABLE camera_installations ALTER COLUMN location_id SET NOT NULL;
        ALTER TABLE pallet_slots ALTER COLUMN location_id SET NOT NULL;
        ALTER TABLE locations ADD CONSTRAINT locations_pkey PRIMARY KEY (location_id);
        ALTER TABLE camera_installations
          ADD CONSTRAINT camera_installations_location_id_fkey
          FOREIGN KEY (location_id) REFERENCES locations(location_id);
        ALTER TABLE pallet_slots
          ADD CONSTRAINT pallet_slots_location_id_fkey
          FOREIGN KEY (location_id) REFERENCES locations(location_id);
        ALTER TABLE pallet_slots
          ADD CONSTRAINT uq_pallet_slot_location_number
          UNIQUE (location_id, pallet_number);
        CREATE INDEX ix_camera_installations_location_id
          ON camera_installations (location_id);
        CREATE INDEX ix_pallet_slots_location_id ON pallet_slots (location_id);
        ALTER SEQUENCE locations_location_id_seq OWNED BY locations.location_id;
    """))


def _move_capture_context(bind: sa.Connection) -> None:
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            "旧撮影台帳の設置履歴移行はPostgreSQLで実行してください"
        )
    bind.execute(sa.text("""
        UPDATE camera_installations AS ci
        SET intrinsics = jsonb_build_object(
            'fx', (c.intrinsics ->> 'fx')::double precision,
            'fy', (c.intrinsics ->> 'fy')::double precision,
            'cx', (c.intrinsics ->> 'cx')::double precision,
            'cy', (c.intrinsics ->> 'cy')::double precision
        ),
        distortion = c.distortion
        FROM cameras AS c
        WHERE ci.camera_id = c.camera_id
          AND c.intrinsics IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE camera_installations AS ci
        SET intrinsics = (
            SELECT jsonb_build_object(
                'fx', (cap.projection ->> 'fx')::double precision,
                'fy', (cap.projection ->> 'fy')::double precision,
                'cx', (cap.projection ->> 'cx')::double precision,
                'cy', (cap.projection ->> 'cy')::double precision
            )
            FROM captures AS cap
            WHERE cap.camera_id = ci.camera_id
            ORDER BY cap.captured_at DESC, cap.capture_id DESC
            LIMIT 1
        ),
        distortion = (
            SELECT cap.distortion
            FROM captures AS cap
            WHERE cap.camera_id = ci.camera_id
            ORDER BY cap.captured_at DESC, cap.capture_id DESC
            LIMIT 1
        )
        WHERE ci.intrinsics IS NULL
    """))
    op.add_column(
        "captures",
        sa.Column("camera_installation_id", sa.BigInteger(), nullable=True),
    )
    bind.execute(sa.text("""
        UPDATE captures AS cap
        SET camera_installation_id = COALESCE(
            (
                SELECT ci.camera_installation_id
                FROM camera_installations AS ci
                WHERE ci.camera_id = cap.camera_id
                  AND ci.installed_at <= cap.captured_at
                  AND (ci.removed_at IS NULL OR cap.captured_at <= ci.removed_at)
                ORDER BY ci.installed_at DESC, ci.camera_installation_id DESC
                LIMIT 1
            ),
            (
                SELECT ci.camera_installation_id
                FROM camera_installations AS ci
                WHERE ci.camera_id = cap.camera_id
                ORDER BY (ci.removed_at IS NULL) DESC,
                         ci.camera_installation_id DESC
                LIMIT 1
            )
        )
    """))
    missing = bind.execute(sa.text(
        "SELECT count(*) FROM captures WHERE camera_installation_id IS NULL"
    )).scalar_one()
    if missing:
        raise RuntimeError(
            f"設置履歴へ紐づけられないCaptureが{missing}件あります"
        )
    op.alter_column("captures", "camera_installation_id", nullable=False)
    op.create_foreign_key(
        "captures_camera_installation_id_fkey",
        "captures",
        "camera_installations",
        ["camera_installation_id"],
        ["camera_installation_id"],
    )
    op.create_index(
        "ix_captures_camera_installation_id",
        "captures",
        ["camera_installation_id"],
    )
    for name in (
        "camera_id",
        "color_height",
        "color_width",
        "depth_height",
        "depth_width",
        "depth_aligned_to_color",
        "projection",
        "distortion",
    ):
        op.drop_column("captures", name)


def downgrade() -> None:
    raise RuntimeError(
        "撮影台帳と場所IDを再構成する移行のため、"
        "ダウングレードはDBバックアップから復元してください"
    )
