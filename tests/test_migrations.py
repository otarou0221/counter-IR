from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from alembic import command
import numpy as np
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
)

from cardboard_counter_v2.api.box_catalog_repository import BoxCatalogRepository
from cardboard_counter_v2.api.capture_migration import LegacyCaptureMigrator
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    CaptureRecord,
)
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.api.migration_cli import alembic_config, run_db
from cardboard_counter_v2.api.settings import SettingsStore


def test_alembic_creates_versioned_schema(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "alembic.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.delenv("POSTGRES_HOST", raising=False)

    assert run_db("upgrade") == 0

    database = Database(f"sqlite+pysqlite:///{database_path}")
    tables = inspect(database.engine).get_table_names()  # type: ignore[arg-type]
    assert "captures" in tables
    assert "factory_maps" in tables
    assert "pallet_map_placements" in tables
    assert "camera_map_placements" not in tables
    inspector = inspect(database.engine)  # type: ignore[arg-type]
    capture_columns = {
        column["name"] for column in inspector.get_columns("captures")
    }
    assert capture_columns == {
        "capture_id", "camera_installation_id", "purpose", "retention",
        "source_batch_id", "storage_version", "captured_at", "frame_count",
        "created_at",
    }
    assert "intrinsics" not in {
        column["name"] for column in inspector.get_columns("cameras")
    }
    assert {"intrinsics", "distortion"} <= {
        column["name"]
        for column in inspector.get_columns("camera_installations")
    }
    assert {"building_name", "floor_name", "area_name"} <= {
        column["name"] for column in inspector.get_columns("locations")
    }
    assert "building_name" in {
        column["name"] for column in inspector.get_columns("factory_maps")
    }
    pallet_slot_columns = {
        column["name"] for column in inspector.get_columns("pallet_slots")
    }
    assert {
        "camera_installation_id",
        "single_box_labels",
        "mixed_box_groups",
    } <= pallet_slot_columns
    assert "location_id" not in pallet_slot_columns
    assert "plane_roi" not in pallet_slot_columns
    assert "target_box_labels" not in pallet_slot_columns
    with database.engine.connect() as connection:  # type: ignore[union-attr]
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "20260901_03"
    database.dispose()


def test_pallet_slot_migration_preserves_each_installation_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy-pallet-slots.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    engine = create_engine(database_url)
    metadata = MetaData()
    installations = Table(
        "camera_installations",
        metadata,
        Column("camera_installation_id", Integer, primary_key=True),
        Column("location_id", Integer, nullable=False),
        Column("removed_at", DateTime(timezone=True)),
    )
    slots = Table(
        "pallet_slots",
        metadata,
        Column("pallet_slot_id", Integer, primary_key=True),
        Column("location_id", Integer, nullable=False),
        Column("pallet_number", Integer, nullable=False),
        Column("display_name", String(100), nullable=False),
        Column("monitoring_enabled", Boolean, nullable=False),
        Column("plane_roi", String(100), nullable=False),
        UniqueConstraint(
            "location_id",
            "pallet_number",
            name="uq_pallet_slot_location_number",
        ),
    )
    calibrations = Table(
        "pallet_calibrations",
        metadata,
        Column("pallet_calibration_id", Integer, primary_key=True),
        Column("camera_installation_id", Integer, nullable=False),
        Column("pallet_slot_id", Integer, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(installations.insert(), [
            {
                "camera_installation_id": 10,
                "location_id": 1,
                "removed_at": datetime(2026, 8, 31, tzinfo=UTC),
            },
            {
                "camera_installation_id": 20,
                "location_id": 1,
                "removed_at": None,
            },
        ])
        connection.execute(slots.insert(), {
            "pallet_slot_id": 1,
            "location_id": 1,
            "pallet_number": 1,
            "display_name": "パレット1",
            "monitoring_enabled": True,
            "plane_roi": "[0.1, 0.1, 0.4, 0.4]",
        })
        connection.execute(calibrations.insert(), [
            {
                "pallet_calibration_id": 100,
                "camera_installation_id": 10,
                "pallet_slot_id": 1,
            },
            {
                "pallet_calibration_id": 200,
                "camera_installation_id": 20,
                "pallet_slot_id": 1,
            },
        ])
    engine.dispose()

    config = alembic_config()
    command.stamp(config, "20260831_03")
    command.upgrade(config, "head")

    migrated = create_engine(database_url)
    migrated_metadata = MetaData()
    migrated_slots = Table(
        "pallet_slots", migrated_metadata, autoload_with=migrated
    )
    migrated_calibrations = Table(
        "pallet_calibrations", migrated_metadata, autoload_with=migrated
    )
    with migrated.connect() as connection:
        slot_rows = connection.execute(
            select(migrated_slots).order_by(migrated_slots.c.pallet_slot_id)
        ).mappings().all()
        calibration_rows = connection.execute(
            select(migrated_calibrations).order_by(
                migrated_calibrations.c.pallet_calibration_id
            )
        ).mappings().all()

    assert "location_id" not in migrated_slots.c
    assert "plane_roi" not in migrated_slots.c
    assert {row["camera_installation_id"] for row in slot_rows} == {10, 20}
    installation_by_slot = {
        row["pallet_slot_id"]: row["camera_installation_id"]
        for row in slot_rows
    }
    assert [
        installation_by_slot[row["pallet_slot_id"]]
        for row in calibration_rows
    ] == [10, 20]
    migrated.dispose()


def test_realtime_measurement_migration_assigns_failures_to_each_pallet(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy-realtime.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    engine = create_engine(database_url)
    metadata = MetaData()
    calibrations = Table(
        "pallet_calibrations",
        metadata,
        Column("pallet_calibration_id", Integer, primary_key=True),
        Column("camera_installation_id", Integer, nullable=False),
        Column("pallet_slot_id", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("invalidated_at", DateTime(timezone=True)),
    )
    measurements = Table(
        "realtime_measurements",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("camera_installation_id", Integer, nullable=False, index=True),
        Column("pallet_calibration_id", Integer),
        Column("measurement_capture_id", String(100)),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("finished_at", DateTime(timezone=True), nullable=False),
        Column("status", String(16), nullable=False),
        Column("error_message", String),
        Column("inventory_count", Integer),
        Column("volume_liters", Float),
        Column("box_counts", JSON),
        Column("is_low_stock", Boolean),
        Column("low_stock_threshold_liters", Float),
        Column("email_rearm_margin_liters", Float),
        Column("email_sent_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False),
        CheckConstraint(
            "status = 'success' OR pallet_calibration_id IS NULL",
            name="ck_realtime_measurement_result_shape",
        ),
    )
    metadata.create_all(engine)
    calibrated_at = datetime(2026, 8, 31, tzinfo=UTC)
    failed_at = datetime(2026, 9, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(calibrations.insert(), [
            {
                "pallet_calibration_id": 101,
                "camera_installation_id": 10,
                "pallet_slot_id": 1,
                "created_at": calibrated_at,
            },
            {
                "pallet_calibration_id": 102,
                "camera_installation_id": 10,
                "pallet_slot_id": 2,
                "created_at": calibrated_at,
            },
        ])
        connection.execute(measurements.insert(), {
            "id": 1001,
            "camera_installation_id": 10,
            "pallet_calibration_id": None,
            "started_at": failed_at,
            "finished_at": failed_at,
            "status": "failed",
            "error_message": "camera timeout",
            "created_at": failed_at,
        })
    engine.dispose()

    config = alembic_config()
    command.stamp(config, "20260901_02")
    command.upgrade(config, "head")

    migrated = create_engine(database_url)
    inspector = inspect(migrated)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("realtime_measurements")
    }
    reflected = Table(
        "realtime_measurements", MetaData(), autoload_with=migrated
    )
    with migrated.connect() as connection:
        rows = connection.execute(
            select(reflected).order_by(reflected.c.pallet_calibration_id)
        ).mappings().all()

    assert "camera_installation_id" not in columns
    assert columns["pallet_calibration_id"]["nullable"] is False
    assert [row["pallet_calibration_id"] for row in rows] == [101, 102]
    assert {row["error_message"] for row in rows} == {"camera timeout"}
    migrated.dispose()


def test_legacy_rgb_capture_is_rejected_by_ir_migration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "data"
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(root))
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'capture.sqlite'}")
    database.initialize()
    SettingsStore(
        InventoryRepository(database),
        BoxCatalogRepository(database),
        root / "config" / "settings.json",
    ).load()
    with database.session() as session:
        installation = session.query(CameraInstallationRecord).one()
        installation.color_width = 4
        installation.color_height = 3
        installation.depth_width = 4
        installation.depth_height = 3
        installation.intrinsics = {
            "fx": 4.0,
            "fy": 4.0,
            "cx": 1.5,
            "cy": 1.0,
        }
        installation.distortion = {
            "k1": 0.08, "k2": -0.1, "k3": 0.04, "k4": 0.0,
            "k5": 0.0, "k6": 0.0, "p1": 0.0, "p2": 0.0,
        }

    capture_id = "legacy_floor_test"
    directory = root / "captures" / capture_id
    directory.mkdir(parents=True)
    depth = np.full((3, 4), 1200.0, dtype=np.float32)
    np.savez_compressed(directory / "depth.npz", depth_mm=depth)
    (directory / "rgb.jpg").write_bytes(b"legacy-rgb")
    (directory / "intrinsics.json").write_text(json.dumps({
        "color": {
            "width": 4, "height": 3,
            "fx": 4.0, "fy": 4.0, "cx": 1.5, "cy": 1.0,
            "distortion": None,
        },
        "depth": None,
        "align_depth_to_color": True,
        "point_cloud_sensor": "color",
    }), encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "capture_id": capture_id,
        "camera_id": "camera_1",
        "purpose": "empty",
        "depth_path": f"captures/{capture_id}/depth.npz",
        "rgb_path": f"captures/{capture_id}/rgb.jpg",
        "intrinsics_path": f"captures/{capture_id}/intrinsics.json",
        "frame_count": 30,
        "color_shape": [3, 4],
        "depth_shape": [3, 4],
        "depth_aligned_to_color": True,
        "captured_at": "2026-08-05T01:00:00+00:00",
    }), encoding="utf-8")

    migrator = LegacyCaptureMigrator(database, root)
    planned = migrator.validate()
    assert planned.candidates == 1
    assert not planned.successful
    assert "IR版ではDepth座標" in planned.errors[0]
    assert not (directory / "xyz.npz").exists()
    assert (directory / "manifest.json").exists()
    database.dispose()
