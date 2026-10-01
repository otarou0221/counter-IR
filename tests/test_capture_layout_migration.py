from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cardboard_counter_v2.api.capture_layout_migration import CaptureLayoutMigrator
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    CameraRecord,
    CaptureRecord,
    LocationRecord,
)
from cardboard_counter_v2.api.inventory.repositories.capture_repository import (
    CaptureRepository,
)


def configured_database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'layout.sqlite'}")
    database.initialize()
    with database.session() as session:
        camera = CameraRecord(
            camera_id="camera_2",
            camera_code="CAM-002",
            display_name="カメラ2",
        )
        location = LocationRecord(factory_name="長岡工場")
        session.add_all((camera, location))
        session.flush()
        installation = CameraInstallationRecord(
            camera_id=camera.camera_id,
            location_id=location.location_id,
            ip_address="192.168.253.8",
            port=8090,
            camera_service_url="http://camera-2:8001",
            driver="orbbec_network",
            intrinsics={
                "fx": 750.0,
                "fy": 750.0,
                "cx": 640.0,
                "cy": 360.0,
            },
        )
        session.add(installation)
        session.flush()
        session.add(CaptureRecord(
            capture_id="legacy_current",
            camera_installation_id=installation.camera_installation_id,
            purpose="current",
            retention="transient",
            storage_version=2,
            captured_at=datetime(2026, 9, 1, tzinfo=UTC),
            frame_count=1,
        ))
    return database


def write_capture(directory: Path) -> None:
    directory.mkdir(parents=True)
    for name in ("rgb.jpg", "depth.npz", "xyz.npz"):
        (directory / name).write_bytes(b"test")


def test_capture_layout_migration_moves_files_and_updates_db(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    root = tmp_path / "data"
    source = root / "captures/legacy_current"
    destination = root / "captures/camera_2/current/legacy_current"
    write_capture(source)
    migrator = CaptureLayoutMigrator(database, root)

    planned = migrator.validate()
    migrated = migrator.apply()

    assert planned.candidates == 1
    assert planned.successful
    assert migrated.migrated == 1
    assert migrated.successful
    assert not source.exists()
    assert (destination / "rgb.jpg").is_file()
    with database.session() as session:
        assert session.get(CaptureRecord, "legacy_current").storage_version == 3
    manifest = CaptureRepository(database).load("legacy_current")
    assert manifest.depth_path == (
        "captures/camera_2/current/legacy_current/depth.npz"
    )


def test_capture_layout_migration_recovers_move_before_db_update(
    tmp_path: Path,
) -> None:
    database = configured_database(tmp_path)
    root = tmp_path / "data"
    destination = root / "captures/camera_2/current/legacy_current"
    write_capture(destination)

    report = CaptureLayoutMigrator(database, root).apply()

    assert report.migrated == 1
    assert report.successful
    with database.session() as session:
        assert session.get(CaptureRecord, "legacy_current").storage_version == 3


def test_capture_layout_migration_rejects_conflicting_directories(
    tmp_path: Path,
) -> None:
    database = configured_database(tmp_path)
    root = tmp_path / "data"
    write_capture(root / "captures/legacy_current")
    write_capture(root / "captures/camera_2/current/legacy_current")

    report = CaptureLayoutMigrator(database, root).validate()

    assert not report.successful
    assert "両方が存在" in report.errors[0]
