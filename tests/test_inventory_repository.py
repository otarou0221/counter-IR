from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    Base,
    CameraInstallationRecord,
    CameraRecord,
    CaptureRecord,
    InventoryHistoryRecord,
    LocationRecord,
    MeasurementSettingsRecord,
    PalletSlotRecord,
    RealtimeMeasurementRecord,
    PalletCalibrationRecord,
)
from cardboard_counter_v2.api.dashboard_schemas import PalletMapPlacementInput
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.api.inventory.repositories.dashboard_repository import (
    DashboardRepository,
)
from cardboard_counter_v2.api.inventory.repositories.factory_map_repository import (
    FactoryMapRepository,
)
from cardboard_counter_v2.common.schemas import (
    BoxCombinationCandidate,
    BoxCombinationResult,
    CalibrationResult,
    CameraMeasurementRun,
    CaptureManifest,
    MeasurementResponse,
    PalletPlaneCalibrationResult,
    PalletMeasurement,
    SystemSettings,
)
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec


def inventory_settings() -> SystemSettings:
    settings = SystemSettings()
    first, second = settings.pallets
    return settings.model_copy(update={
        # DBの履歴テストでは大きな合成画面を使う。実機既定は512x512。
        "cameras": [settings.cameras[0].model_copy(update={
            "width": 1280, "height": 720,
            "depth_width": 1280, "depth_height": 720,
        })],
        "pallets": [
            first.model_copy(update={
                "low_stock_threshold_liters": 160.0,
                "email_rearm_margin_liters": 154.0,
            }),
            second,
        ]
    })


def measurement(measurement_id: str, count: int) -> MeasurementResponse:
    counts = {"cardboard_box": count} if count else {}
    candidate = BoxCombinationCandidate(
        counts=counts,
        fitted_volume_liters=count * 78.2895,
        residual_volume_liters=0.0,
    )
    return MeasurementResponse(
        measurement_id=measurement_id,
        camera_runs=[CameraMeasurementRun(
            camera_id="camera_1",
            measurement_id=measurement_id,
            calibration_id="calibration_test",
            baseline_capture_id="empty_test",
            current_capture_id=f"current_{measurement_id}",
        )],
        pallets=[PalletMeasurement(
            pallet_id=1,
            pallet_number=1,
            camera_id="camera_1",
            volume_liters=count * 78.2895,
            estimated_boxes=float(count),
            occupied_cells=100,
            observed_cells=200,
            plane_rmse_mm=2.0,
            protrusion_components=0,
            protrusion_cells=0,
            protrusion_volume_liters=0.0,
            box_combination=BoxCombinationResult(
                best=candidate,
                alternatives=[candidate],
                ambiguous=False,
            ),
        )],
    )


def repository(tmp_path: Path) -> tuple[Database, InventoryRepository]:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'inventory.sqlite'}")
    return database, InventoryRepository(database)


def saved_capture(
    tmp_path: Path,
    monkeypatch,
    *,
    capture_id: str = "empty_capture",
    fx: float = 749.8,
    retention: str = "persistent",
) -> CaptureManifest:
    root = tmp_path / "data"
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(root))
    output = root / "captures" / capture_id
    output.mkdir(parents=True)
    manifest = CaptureManifest(
        capture_id=capture_id,
        camera_id="camera_1",
        purpose="floor",
        retention=retention,  # type: ignore[arg-type]
        depth_path=f"captures/{capture_id}/depth.npz",
        xyz_path=f"captures/{capture_id}/xyz.npz",
        rgb_path=f"captures/{capture_id}/rgb.jpg",
        projection=ProjectionIntrinsicsSpec(
            width=1280, height=720, fx=fx, fy=750.0, cx=646.5, cy=337.5,
        ),
        distortion={
            "k1": 0.1, "k2": -0.2, "k3": 0.0, "k4": 0.0,
            "k5": 0.0, "k6": 0.0, "p1": 0.01, "p2": -0.01,
        },
        frame_count=30,
        color_shape=(720, 1280),
        depth_shape=(720, 1280),
        depth_aligned_to_color=False,
        captured_at="2026-08-10T01:00:00+00:00",
    )
    return manifest


def record_calibration(
    tmp_path: Path,
    monkeypatch,
    history: InventoryRepository,
    settings: SystemSettings,
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path / "data"))
    history.register_capture(
        saved_capture(tmp_path, monkeypatch, capture_id="empty_test")
    )
    calibrated_pallets: list[PalletPlaneCalibrationResult] = []
    for pallet in settings.pallets:
        if not pallet.enabled:
            continue
        calibrated_pallets.append(PalletPlaneCalibrationResult(
            pallet_id=pallet.pallet_id,
            pallet_number=pallet.pallet_number,
            plane_roi=pallet.plane_roi,
            floor_plane_normal=(0.0, 0.0, -1.0),
            floor_plane_offset=1000.0 + float(pallet.pallet_id),
            pallet_height_mm=120.0,
            plane_rmse_mm=2.0,
            plane_inlier_count=100,
            cell_size_mm=10.0,
        ))
    result = CalibrationResult(
        calibration_id="calibration_test",
        camera_id="camera_1",
        baseline_capture_id="empty_test",
        created_at="2026-08-08T01:00:00+00:00",
        projection=ProjectionIntrinsicsSpec(
            width=1280, height=720, fx=749.8, fy=750.0, cx=646.5, cy=337.5,
        ),
        pallets=calibrated_pallets,
    )
    history.record_calibration(result, settings)


def test_initializes_camera_and_location_masters(tmp_path: Path) -> None:
    database, history = repository(tmp_path)
    history.initialize(inventory_settings())

    with database.session() as session:
        cameras = session.scalars(select(CameraRecord)).all()
        locations_master = session.scalars(select(LocationRecord)).all()
        installations = session.scalars(select(CameraInstallationRecord)).all()
        installation_nulls = session.execute(select(
            CameraInstallationRecord.intrinsics.is_(None),
            CameraInstallationRecord.distortion.is_(None),
        )).one()

    assert [(item.camera_id, item.display_name, item.active) for item in cameras] == [
        ("camera_1", "カメラ1", True)
    ]
    assert cameras[0].camera_code == "CAM-001"
    assert [item.location_id for item in locations_master] == [1]
    assert installations[0].ip_address == "192.168.253.7"
    assert installations[0].intrinsics is None
    assert installations[0].distortion is None
    assert installation_nulls == (True, True)
    assert [column.name for column in CameraInstallationRecord.__table__.columns] == [
        "camera_installation_id",
        "camera_id",
        "location_id",
        "ip_address",
            "port",
            "camera_service_url",
            "driver",
            "color_width",
            "color_height",
            "depth_width",
            "depth_height",
            "fps",
            "align_depth_to_color",
            "intrinsics",
            "distortion",
            "installed_at",
        "removed_at",
        "mounting_note",
        "created_at",
        "updated_at",
    ]
    assert installations[0].camera_service_url == "http://camera-1:8001"
    with database.session() as session:
        slots = session.scalars(select(PalletSlotRecord).order_by(PalletSlotRecord.pallet_number)).all()
        measurement_settings = session.get(MeasurementSettingsRecord, 1)
    assert [slot.pallet_number for slot in slots] == [1, 2]
    assert all(
        slot.camera_installation_id == installations[0].camera_installation_id
        for slot in slots
    )
    assert slots[0].low_stock_threshold_liters == 160.0
    assert measurement_settings is not None
    assert measurement_settings.measurement_interval_seconds == 600
    assert measurement_settings.measurement_frame_count == 1
    assert measurement_settings.measurement_concurrency == 3
    assert "inventory_locations" not in Base.metadata.tables


def test_registers_capture_and_camera_parameters(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    history.initialize(inventory_settings())
    manifest = saved_capture(tmp_path, monkeypatch)

    assert history.register_capture(manifest)
    assert not history.register_capture(manifest)

    with database.session() as session:
        installation = session.scalar(select(CameraInstallationRecord))

    assert installation is not None
    assert installation.intrinsics == {
        "fx": 749.8,
        "fy": 750.0,
        "cx": 646.5,
        "cy": 337.5,
    }
    assert installation.distortion == {
        "k1": 0.1, "k2": -0.2, "k3": 0.0, "k4": 0.0,
        "k5": 0.0, "k6": 0.0, "p1": 0.01, "p2": -0.01,
    }
    assert "captures" in Base.metadata.tables
    with database.session() as session:
        capture = session.get(CaptureRecord, manifest.capture_id)
        assert capture is not None
        assert capture.camera_installation_id == installation.camera_installation_id
    assert [column.name for column in CaptureRecord.__table__.columns] == [
        "capture_id",
        "camera_installation_id",
        "purpose",
        "retention",
        "source_batch_id",
        "storage_version",
        "captured_at",
        "frame_count",
        "created_at",
    ]


def test_capture_catalog_filters_and_paginates_in_the_database(
    tmp_path: Path, monkeypatch
) -> None:
    _database, history = repository(tmp_path)
    history.initialize(inventory_settings())
    for index in range(5):
        manifest = saved_capture(
            tmp_path,
            monkeypatch,
            capture_id=f"current_{index}",
            retention="transient",
        ).model_copy(update={
            "purpose": "current",
            "captured_at": f"2026-08-10T01:0{index}:00+00:00",
        })
        assert history.register_capture(manifest)

    page = history.list_captures(
        camera_id="camera_1",
        purpose="current",
        limit=2,
        offset=1,
    )

    assert [capture.capture_id for capture in page] == ["current_3", "current_2"]


def test_resolution_change_creates_new_installation_and_preserves_capture_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    manifest = saved_capture(tmp_path, monkeypatch)
    assert history.register_capture(manifest)
    with database.session() as session:
        original_slot_ids = session.scalars(
            select(PalletSlotRecord.pallet_slot_id).order_by(
                PalletSlotRecord.pallet_number
            )
        ).all()

    updated_camera = settings.cameras[0].model_copy(update={
        "width": 640,
        "height": 360,
    })
    history.sync_settings(settings.model_copy(update={"cameras": [updated_camera]}))

    with database.session() as session:
        installations = session.scalars(
            select(CameraInstallationRecord).order_by(
                CameraInstallationRecord.camera_installation_id
            )
        ).all()
        capture = session.get(CaptureRecord, manifest.capture_id)
        slots = session.scalars(
            select(PalletSlotRecord).order_by(
                PalletSlotRecord.camera_installation_id,
                PalletSlotRecord.pallet_number,
            )
        ).all()

    assert len(installations) == 2
    assert installations[0].removed_at is not None
    assert installations[0].intrinsics is not None
    assert installations[1].removed_at is None
    assert installations[1].intrinsics is None
    assert capture is not None
    assert capture.camera_installation_id == installations[0].camera_installation_id
    assert len(slots) == 4
    assert [slot.pallet_slot_id for slot in slots[:2]] == original_slot_ids
    assert all(
        slot.camera_installation_id == installations[0].camera_installation_id
        and not slot.monitoring_enabled
        for slot in slots[:2]
    )
    assert all(
        slot.camera_installation_id == installations[1].camera_installation_id
        for slot in slots[2:]
    )
    assert [slot.monitoring_enabled for slot in slots[2:]] == [True, False]


def test_connection_change_updates_active_installation_without_losing_calibration_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    assert history.register_capture(saved_capture(tmp_path, monkeypatch))

    updated_camera = settings.cameras[0].model_copy(update={"ip": "192.168.253.9"})
    history.sync_settings(settings.model_copy(update={"cameras": [updated_camera]}))

    with database.session() as session:
        installations = session.scalars(select(CameraInstallationRecord)).all()

    assert len(installations) == 1
    assert str(installations[0].ip_address) == "192.168.253.9"
    assert installations[0].intrinsics is not None


def test_factory_dashboard_persists_png_positions_and_latest_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, inventory = repository(tmp_path)
    settings = inventory_settings()
    inventory.initialize(settings)
    dashboard = DashboardRepository(database)
    factory_maps = FactoryMapRepository(database)
    created = factory_maps.create_map(
        display_name="第5工場 3階",
        factory_name="長岡工場",
        building_name="第5工場",
        floor_name="3階",
        image_data=b"png-binary",
        image_width=1076,
        image_height=621,
    )
    assert factory_maps.map_image(created.factory_map_id) == (
        "image/png",
        b"png-binary",
    )
    assert created.factory_name == "長岡工場"
    assert created.building_name == "第5工場"
    assert created.floor_name == "3階"
    placements = factory_maps.save_placements(created.factory_map_id, [
        PalletMapPlacementInput(
            pallet_slot_id=1,
            position_x_ratio=0.25,
            position_y_ratio=0.75,
        )
    ])
    assert [(item.pallet_slot_id, item.position_x_ratio) for item in placements] == [
        (1, 0.25)
    ]

    stopped = dashboard.load_dashboard(
        monitor_running=False,
        measurement_interval_seconds=600,
    )
    assert stopped.cameras[0].state == "unavailable"
    assert stopped.cameras[0].state_message == "監視停止中"
    assert stopped.cameras[0].pallets[0].placement == placements[0]

    record_calibration(tmp_path, monkeypatch, inventory, settings)
    measured_at = datetime.now(UTC)
    inventory.record_success(
        measurement("dashboard", 1),
        settings,
        started_at=measured_at - timedelta(seconds=1),
        finished_at=measured_at,
    )
    running = dashboard.load_dashboard(
        monitor_running=True,
        measurement_interval_seconds=600,
        now=measured_at + timedelta(seconds=1),
    )
    assert running.cameras[0].state == "low_stock"
    assert running.cameras[0].pallets[0].inventory_count == 1
    assert running.cameras[0].pallets[0].volume_liters == pytest.approx(78.2895)

    inventory.record_failure(
        camera_id="camera_1",
        started_at=measured_at + timedelta(seconds=2),
        finished_at=measured_at + timedelta(seconds=3),
        error_message="camera timeout",
    )
    failed = dashboard.load_dashboard(
        monitor_running=True,
        measurement_interval_seconds=600,
        now=measured_at + timedelta(seconds=4),
    )
    assert failed.cameras[0].state == "unavailable"
    assert failed.cameras[0].state_message == "測定エラー: camera timeout"

    assert factory_maps.delete_map(created.factory_map_id) == created
    with pytest.raises(LookupError, match="見つかりません"):
        factory_maps.map_image(created.factory_map_id)


def test_factory_dashboard_materializes_only_latest_realtime_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, inventory = repository(tmp_path)
    settings = inventory_settings()
    first, second = settings.pallets
    settings = settings.model_copy(update={
        "pallets": [first, second.model_copy(update={"enabled": True})]
    })
    inventory.initialize(settings)
    record_calibration(tmp_path, monkeypatch, inventory, settings)
    started = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)
    for index in range(4):
        finished = started + timedelta(minutes=index)
        result = measurement(f"dashboard_latest_{index}", index)
        result = result.model_copy(update={
            "pallets": [
                result.pallets[0],
                result.pallets[0].model_copy(update={
                    "pallet_id": second.pallet_id,
                    "pallet_number": second.pallet_number,
                }),
            ]
        })
        assert inventory.record_success(
            result,
            settings,
            started_at=finished - timedelta(seconds=1),
            finished_at=finished,
        )
    for index in range(4):
        finished = started + timedelta(minutes=10 + index)
        inventory.record_failure(
            camera_id="camera_1",
            started_at=finished - timedelta(seconds=1),
            finished_at=finished,
            error_message=f"failure-{index}",
        )

    loaded: list[RealtimeMeasurementRecord] = []

    def record_load(target: RealtimeMeasurementRecord, _context: object) -> None:
        loaded.append(target)

    event.listen(RealtimeMeasurementRecord, "load", record_load)
    try:
        dashboard = DashboardRepository(database).load_dashboard(
            monitor_running=True,
            measurement_interval_seconds=600,
            now=started + timedelta(minutes=14),
        )
    finally:
        event.remove(RealtimeMeasurementRecord, "load", record_load)

    assert sorted(row.status for row in loaded) == [
        "failed",
        "success",
        "success",
    ]
    assert [pallet.inventory_count for pallet in dashboard.cameras[0].pallets] == [
        3,
        3,
    ]
    assert dashboard.cameras[0].state_message == "測定エラー: failure-3"


def test_compares_camera_parameters_directly_with_float_tolerance(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    history.initialize(inventory_settings())
    assert history.register_capture(saved_capture(tmp_path, monkeypatch))
    within_tolerance = saved_capture(
        tmp_path, monkeypatch, capture_id="within_tolerance", fx=749.8005
    )
    assert history.register_capture(within_tolerance)
    changed = saved_capture(
        tmp_path, monkeypatch, capture_id="changed_capture", fx=800.0
    )

    with pytest.raises(ValueError, match="一致しません"):
        history.register_capture(changed)


def test_first_new_capture_completes_unrecorded_legacy_distortion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, history = repository(tmp_path)
    history.initialize(inventory_settings())
    with database.session() as session:
        installation = session.query(CameraInstallationRecord).one()
        installation.intrinsics = {
            "fx": 749.8,
            "fy": 750.0,
            "cx": 646.5,
            "cy": 337.5,
        }
        installation.distortion = None

    manifest = saved_capture(tmp_path, monkeypatch)
    assert history.register_capture(manifest)
    with database.session() as session:
        installation = session.query(CameraInstallationRecord).one()
        assert installation.distortion == manifest.distortion


def test_records_readings_and_marks_low_stock_from_volume(tmp_path: Path, monkeypatch) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    monkeypatch.setattr(
        history,
        "_sync_settings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("測定ループ内でマスター同期を実行しています")
        ),
    )
    started = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)

    for index, count in enumerate((5, 2, 1, 4), start=1):
        finished = started + timedelta(minutes=index)
        assert history.record_success(
            measurement(f"measurement_{index}", count),
            settings,
            started_at=started,
            finished_at=finished,
        )

    with database.session() as session:
        measurements = session.scalars(
            select(RealtimeMeasurementRecord).order_by(RealtimeMeasurementRecord.id)
        ).all()
        inventory_history = session.scalars(
            select(InventoryHistoryRecord).order_by(InventoryHistoryRecord.id)
        ).all()
        calibration_count = session.scalar(
            select(func.count()).select_from(PalletCalibrationRecord)
        )
        calibration = session.scalar(
            select(PalletCalibrationRecord).join(PalletSlotRecord).where(
                PalletCalibrationRecord.calibration_id == "calibration_test",
                PalletSlotRecord.pallet_number == 1,
            )
        )
        assert calibration is not None
        calibration_pallet_number = calibration.pallet_slot.pallet_number
        calibration_threshold = calibration.pallet_slot.low_stock_threshold_liters

    assert [item.inventory_count for item in measurements] == [5, 2, 1, 4]
    assert [item.inventory_count for item in inventory_history] == [5, 2, 1, 4]
    assert all(
        item.pallet_calibration_id == calibration.pallet_calibration_id
        for item in measurements
    )
    assert [item.is_low_stock for item in measurements] == [False, True, True, False]
    assert measurements[1].box_counts == {"cardboard_box": 2}
    assert calibration_count == 1
    assert calibration.calibration_data == {
        "roi": [0.05, 0.15, 0.48, 0.95],
        "floor_plane_normal": [0.0, 0.0, -1.0],
        "floor_plane_offset": 1001.0,
        "pallet_height_mm": 120.0,
    }
    assert calibration_pallet_number == 1
    assert calibration.calibration_capture_id == "empty_test"
    assert calibration_threshold == 160.0
    assert all(item.low_stock_threshold_liters == 160.0 for item in measurements)
    assert all(item.email_rearm_margin_liters == 154.0 for item in measurements)
    assert "manifest_path" not in PalletCalibrationRecord.__table__.columns
    assert "manifest_checksum" not in PalletCalibrationRecord.__table__.columns


def test_records_two_pallets_in_one_calibration(tmp_path: Path, monkeypatch) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    first, second = settings.pallets
    settings = settings.model_copy(update={
        "pallets": [first, second.model_copy(update={"enabled": True})]
    })
    history.initialize(settings)

    record_calibration(tmp_path, monkeypatch, history, settings)
    result = measurement("two_pallets", 3)
    result = result.model_copy(update={
        "pallets": [
            result.pallets[0],
            result.pallets[0].model_copy(update={
                "pallet_id": second.pallet_id,
                "pallet_number": second.pallet_number,
            }),
        ]
    })
    timestamp = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)
    assert history.record_success(
        result,
        settings,
        started_at=timestamp,
        finished_at=timestamp,
    )

    with database.session() as session:
        calibrations = session.scalars(
            select(PalletCalibrationRecord).join(PalletSlotRecord).order_by(
                PalletSlotRecord.pallet_number
            )
        ).all()
        installation = session.scalar(
            select(CameraInstallationRecord).where(
                CameraInstallationRecord.removed_at.is_(None)
            )
        )
        measurements = session.scalars(
            select(RealtimeMeasurementRecord).order_by(RealtimeMeasurementRecord.id)
        ).all()
        measurement_pallet_numbers = [
            item.pallet_calibration.pallet_slot.pallet_number
            for item in measurements
            if item.pallet_calibration is not None
        ]

    assert installation is not None
    assert installation.intrinsics is not None
    assert [item.calibration_id for item in calibrations] == [
        "calibration_test",
        "calibration_test",
    ]
    assert [item.pallet_slot.pallet_number for item in calibrations] == [1, 2]
    assert [
        item.calibration_data["floor_plane_offset"] for item in calibrations
    ] == [1001.0, 1002.0]
    assert [item.measurement_capture_id for item in measurements] == [
        "current_two_pallets",
        "current_two_pallets",
    ]
    assert measurement_pallet_numbers == [1, 2]
    definition = history.load_calibration_definition("calibration_test")
    assert definition.calibration_capture_id == "empty_test"
    assert [region.region_id for region in definition.regions] == [1, 2]
    assert [region.reference_plane_offset for region in definition.regions] == [
        1001.0, 1002.0,
    ]
    assert [region.surface_offset_mm for region in definition.regions] == [120.0, 120.0]
    assert definition.projection.fx == 749.8
    assert "pallet_number" not in RealtimeMeasurementRecord.__table__.columns
    assert "source" not in RealtimeMeasurementRecord.__table__.columns
    assert "measurement_id" not in RealtimeMeasurementRecord.__table__.columns
    assert "camera_measurement_id" not in RealtimeMeasurementRecord.__table__.columns
    assert "current_capture_id" not in RealtimeMeasurementRecord.__table__.columns
    assert "capture_id" not in PalletCalibrationRecord.__table__.columns
    assert [column.name for column in InventoryHistoryRecord.__table__.columns] == [
        "id",
        "pallet_calibration_id",
        "measurement_capture_id",
        "finished_at",
        "inventory_count",
        "volume_liters",
        "box_counts",
        "is_low_stock",
        "low_stock_threshold_liters",
        "email_rearm_margin_liters",
        "email_sent_at",
        "created_at",
    ]


def test_syncs_ui_threshold_to_pallet_slot_without_mutating_calibration(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    first, second = settings.pallets
    updated = settings.model_copy(update={
        "pallets": [
            first.model_copy(update={"low_stock_threshold_liters": 6.5}),
            second,
        ]
    })

    history.sync_settings(updated)

    with database.session() as session:
        calibration = session.scalar(
            select(PalletCalibrationRecord).join(PalletSlotRecord).where(
                PalletCalibrationRecord.calibration_id == "calibration_test",
                PalletSlotRecord.pallet_number == 1,
            )
        )
        assert calibration is not None
        threshold = calibration.pallet_slot.low_stock_threshold_liters

    assert threshold == 6.5
    assert "low_stock_threshold_liters" not in PalletCalibrationRecord.__table__.columns


def test_loads_roi_from_active_calibration_only(tmp_path: Path, monkeypatch) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    first, second = settings.pallets
    calibrated_roi = (0.1, 0.2, 0.4, 0.8)
    settings = settings.model_copy(update={
        "pallets": [
            first.model_copy(update={"plane_roi": calibrated_roi}),
            second,
        ]
    })
    history.initialize(settings)

    assert history.load_settings().pallets[0].plane_roi != calibrated_roi  # type: ignore[union-attr]
    record_calibration(tmp_path, monkeypatch, history, settings)

    loaded = history.load_settings()
    assert loaded is not None
    assert loaded.pallets[0].plane_roi == calibrated_roi
    assert "plane_roi" not in PalletSlotRecord.__table__.columns


def test_finished_at_makes_history_write_idempotent(tmp_path: Path, monkeypatch) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    timestamp = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)
    result = measurement("same_measurement", 3)

    assert history.record_success(
        result,
        settings,
        started_at=timestamp,
        finished_at=timestamp,
    )
    assert not history.record_success(
        result,
        settings,
        started_at=timestamp,
        finished_at=timestamp,
    )

    with database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(RealtimeMeasurementRecord)
        ) == 1


def test_records_failure_with_measurement_values_as_null(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    settings = settings.model_copy(update={
        "pallets": [
            settings.pallets[0],
            settings.pallets[1].model_copy(update={"enabled": True}),
        ]
    })
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    started = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)
    finished = started + timedelta(seconds=5)

    history.record_failure(
        started_at=started,
        finished_at=finished,
        error_message="camera timeout",
    )

    with database.session() as session:
        records = session.scalars(
            select(RealtimeMeasurementRecord).order_by(
                RealtimeMeasurementRecord.pallet_calibration_id
            )
        ).all()
        pallet_numbers = session.scalars(
            select(PalletSlotRecord.pallet_number)
            .join(
                PalletCalibrationRecord,
                PalletCalibrationRecord.pallet_slot_id
                == PalletSlotRecord.pallet_slot_id,
            )
            .join(
                RealtimeMeasurementRecord,
                RealtimeMeasurementRecord.pallet_calibration_id
                == PalletCalibrationRecord.pallet_calibration_id,
            )
            .where(RealtimeMeasurementRecord.status == "failed")
            .order_by(PalletSlotRecord.pallet_number)
        ).all()

    assert len(records) == 2
    assert pallet_numbers == [1, 2]
    assert all(record.status == "failed" for record in records)
    assert all(record.error_message == "camera timeout" for record in records)
    assert all(record.pallet_calibration_id is not None for record in records)
    assert "camera_installation_id" not in RealtimeMeasurementRecord.__table__.columns
    assert all(record.measurement_capture_id is None for record in records)
    assert all(record.inventory_count is None for record in records)
    assert all(record.volume_liters is None for record in records)
    assert all(record.box_counts is None for record in records)


def test_inventory_history_only_records_inventory_changes(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    started = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)

    for index, count in enumerate((5, 5, 4, 4), start=1):
        finished = started + timedelta(minutes=index * 10)
        assert history.record_success(
            measurement(f"change_{index}", count),
            settings,
            started_at=started,
            finished_at=finished,
        )

    with database.session() as session:
        realtime_counts = session.scalars(
            select(RealtimeMeasurementRecord.inventory_count)
            .where(RealtimeMeasurementRecord.status == "success")
            .order_by(RealtimeMeasurementRecord.finished_at)
        ).all()
        history_counts = session.scalars(
            select(InventoryHistoryRecord.inventory_count)
            .order_by(InventoryHistoryRecord.finished_at)
        ).all()

    assert realtime_counts == [5, 5, 4, 4]
    assert history_counts == [5, 4]


def test_realtime_history_keeps_measurements_for_seven_days(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    current = datetime(2026, 8, 9, 1, 0, tzinfo=UTC)
    measurements = [
        ("expired", current - timedelta(days=7, seconds=1)),
        ("boundary", current - timedelta(days=7)),
        ("current", current),
    ]

    for measurement_id, finished in measurements:
        assert history.record_success(
            measurement(measurement_id, 1),
            settings,
            started_at=finished - timedelta(seconds=1),
            finished_at=finished,
        )

    with database.session() as session:
        capture_ids = session.scalars(
            select(RealtimeMeasurementRecord.measurement_capture_id)
            .where(RealtimeMeasurementRecord.status == "success")
            .order_by(RealtimeMeasurementRecord.finished_at)
        ).all()

    assert capture_ids == ["current_boundary", "current_current"]


def test_realtime_week_retention_does_not_limit_capture_count(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    first, second = settings.pallets
    settings = settings.model_copy(update={
        "pallets": [first, second.model_copy(update={"enabled": True})]
    })
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    started = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)

    for index in range(1, 14):
        result = measurement(f"two_pallet_retention_{index}", index)
        result = result.model_copy(update={
            "pallets": [
                result.pallets[0],
                result.pallets[0].model_copy(update={
                    "pallet_id": second.pallet_id,
                    "pallet_number": second.pallet_number,
                }),
            ]
        })
        finished = started + timedelta(minutes=index * 10)
        assert history.record_success(
            result,
            settings,
            started_at=started,
            finished_at=finished,
        )

    with database.session() as session:
        row_count = session.scalar(
            select(func.count()).select_from(RealtimeMeasurementRecord).where(
                RealtimeMeasurementRecord.status == "success"
            )
        )
        capture_count = session.scalar(
            select(
                func.count(
                    func.distinct(
                        RealtimeMeasurementRecord.measurement_capture_id
                    )
                )
            ).where(RealtimeMeasurementRecord.status == "success")
        )

    assert row_count == 26
    assert capture_count == 13


def test_inventory_history_expires_after_six_calendar_months_and_reseeds(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    first = datetime(2026, 1, 30, 1, 0, tzinfo=UTC)
    current = datetime(2026, 7, 31, 1, 0, tzinfo=UTC)

    assert history.record_success(
        measurement("old_history", 5),
        settings,
        started_at=first,
        finished_at=first,
    )
    assert history.record_success(
        measurement("current_history", 5),
        settings,
        started_at=current,
        finished_at=current,
    )

    with database.session() as session:
        records = session.scalars(select(InventoryHistoryRecord)).all()

    assert len(records) == 1
    assert records[0].measurement_capture_id == "current_current_history"


def test_failed_realtime_history_keeps_measurements_for_seven_days(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    current = datetime(2026, 8, 9, 1, 0, tzinfo=UTC)
    failures = [
        ("expired", current - timedelta(days=7, seconds=1)),
        ("boundary", current - timedelta(days=7)),
        ("current", current),
    ]

    for error_message, finished in failures:
        history.record_failure(
            started_at=finished - timedelta(seconds=1),
            finished_at=finished,
            error_message=error_message,
        )

    with database.session() as session:
        errors = session.scalars(
            select(RealtimeMeasurementRecord.error_message)
            .where(RealtimeMeasurementRecord.status == "failed")
            .order_by(RealtimeMeasurementRecord.finished_at)
        ).all()

    assert errors == ["boundary", "current"]


def test_marks_successful_low_stock_email_on_realtime_and_history(
    tmp_path: Path, monkeypatch
) -> None:
    database, history = repository(tmp_path)
    settings = inventory_settings()
    history.initialize(settings)
    record_calibration(tmp_path, monkeypatch, history, settings)
    finished_at = datetime(2026, 8, 8, 1, 10, tzinfo=UTC)
    assert history.record_success(
        measurement("email", 1),
        settings,
        started_at=finished_at - timedelta(seconds=2),
        finished_at=finished_at,
    )
    sent_at = finished_at + timedelta(seconds=1)

    assert history.mark_email_sent(
        calibration_id="calibration_test",
        pallet_number=1,
        finished_at=finished_at,
        sent_at=sent_at,
    )

    with database.session() as session:
        realtime = session.scalar(select(RealtimeMeasurementRecord))
        cumulative = session.scalar(select(InventoryHistoryRecord))
    assert realtime is not None and realtime.email_sent_at == sent_at.replace(tzinfo=None)
    assert cumulative is not None and cumulative.email_sent_at == sent_at.replace(tzinfo=None)
