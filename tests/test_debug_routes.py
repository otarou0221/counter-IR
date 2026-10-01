import asyncio
from pathlib import Path

from cardboard_counter_v2.api.debug_routes import create_debug_router
from cardboard_counter_v2.common.schemas import (
    CalibrationResult,
    CameraMeasurementRun,
    CaptureManifest,
    DebugCurrentCaptureRequest,
    DebugReplayRequest,
    MeasurementResponse,
    PalletPlaneCalibrationResult,
    SystemSettings,
)
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec


def test_debug_replay_uses_selected_captures_without_changing_field_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    settings = SystemSettings()
    requests = []
    projection = ProjectionIntrinsicsSpec(
        width=1280, height=720, fx=750, fy=750, cx=640, cy=360,
    )
    captures = {
        capture_id: CaptureManifest(
            capture_id=capture_id,
            camera_id=camera_id,
            purpose=purpose,
            retention=retention,
            depth_path=f"captures/{capture_id}/depth.npz",
            xyz_path=f"captures/{capture_id}/xyz.npz",
            rgb_path=f"captures/{capture_id}/rgb.jpg",
            projection=projection,
            frame_count=30,
            color_shape=(720, 1280),
            depth_shape=(720, 1280),
            depth_aligned_to_color=True,
            captured_at=captured_at,
        )
        for capture_id, camera_id, purpose, retention, captured_at in (
            ("empty_saved", "camera_1", "floor", "persistent", "2026-07-31T00:00:00+00:00"),
            ("current_saved", "camera_1", "current", "transient", "2026-07-31T00:01:00+00:00"),
            ("current_debug", "camera_1", "current", "persistent", "2026-07-31T00:02:00+00:00"),
            ("other_floor", "camera_2", "floor", "persistent", "2026-07-31T00:03:00+00:00"),
            ("other_current", "camera_2", "current", "transient", "2026-07-31T00:04:00+00:00"),
        )
    }

    class History:
        def load_capture(self, capture_id):
            return captures[capture_id]

        def list_captures(
            self, *, camera_id=None, purpose=None, retention=None,
            limit=None, offset=0,
        ):
            matches = [
                capture for capture in captures.values()
                if (camera_id is None or capture.camera_id == camera_id)
                and (purpose is None or capture.purpose == purpose)
                and (retention is None or capture.retention == retention)
            ]
            matches.sort(
                key=lambda capture: (capture.captured_at or "", capture.capture_id),
                reverse=True,
            )
            page = matches[offset:]
            return page if limit is None else page[:limit]

    class Store:
        def load(self) -> SystemSettings:
            return settings

    async def calibrate(request):
        assert request.baseline_capture_id == "empty_saved"
        return CalibrationResult(
            calibration_id="debug_calibration",
            camera_id="camera_1",
            baseline_capture_id=request.baseline_capture_id,
            created_at="2026-07-31T00:00:00+00:00",
            projection=ProjectionIntrinsicsSpec(
                width=1280, height=720, fx=750, fy=750, cx=640, cy=360,
            ),
            pallets=[PalletPlaneCalibrationResult(
                pallet_id=request.pallets[0].pallet_id,
                pallet_number=request.pallets[0].pallet_number,
                plane_roi=request.pallets[0].plane_roi,
                floor_plane_normal=(0.0, 0.0, -1.0),
                floor_plane_offset=1000.0,
                pallet_height_mm=request.pallet_height_mm,
                plane_rmse_mm=1.0,
                plane_inlier_count=100,
                cell_size_mm=request.grid_mm,
            )],
        )

    async def measure(request):
        requests.append(request)
        return MeasurementResponse(
            measurement_id="debug_measurement",
            camera_runs=[CameraMeasurementRun(
                camera_id="camera_1",
                measurement_id="debug_measurement",
                calibration_id=request.calibration_id,
                baseline_capture_id="empty_saved",
                current_capture_id=request.current_capture_id,
            )],
            pallets=[],
        )

    async def prepare_runtime(calibration, pallets, box_catalog):
        assert calibration.calibration_id == "debug_calibration"
        assert pallets
        assert box_catalog
        return "debug_runtime"

    async def capture_current(_settings, camera_id):
        assert camera_id == "camera_1"
        return MeasurementResponse(
            measurement_id="current_debug_measurement",
            camera_runs=[CameraMeasurementRun(
                camera_id=camera_id,
                measurement_id="current_debug_measurement",
                calibration_id="field_calibration",
                baseline_capture_id="empty_saved",
                current_capture_id="current_new",
            )],
            pallets=[],
        )

    router = create_debug_router(
        store=Store(),
        operation_lock=asyncio.Lock(),
        monitoring=lambda: False,
        request_calibration=calibrate,
        request_measurement=measure,
        prepare_measurement_runtime=prepare_runtime,
        request_current_debug=capture_current,
        history=History(),  # type: ignore[arg-type]
    )
    catalog_endpoint = next(
        route.endpoint for route in router.routes if route.path.endswith("/catalog")
    )
    first_page = catalog_endpoint(
        camera_id="camera_1", current_offset=0, current_limit=1,
    )
    assert [item.capture_id for item in first_page.floor_captures] == ["empty_saved"]
    assert [item.capture_id for item in first_page.current_captures] == ["current_debug"]
    assert first_page.current_captures[0].retention == "persistent"
    assert first_page.current_has_more is True
    assert first_page.current_capture_limit == 2100

    second_page = catalog_endpoint(
        camera_id="camera_1", current_offset=1, current_limit=1,
    )
    assert [item.capture_id for item in second_page.current_captures] == ["current_saved"]
    assert second_page.current_captures[0].retention == "transient"
    assert second_page.current_has_more is False

    replay = next(route.endpoint for route in router.routes if route.path.endswith("/replay"))
    response = asyncio.run(replay(DebugReplayRequest(
        baseline_capture_id="empty_saved",
        current_capture_id="current_saved",
    )))

    assert response.measurement_id == "debug_measurement"
    assert requests[0].generate_artifacts is True
    assert requests[0].generate_debug_stages is True
    assert requests[0].current_capture_id == "current_saved"
    assert requests[0].runtime_id == "debug_runtime"
    assert requests[0].calibration is None
    assert not (tmp_path / "state" / "last_debug_result.json").exists()
    assert not (tmp_path / "state" / "last_result.json").exists()

    capture_current_endpoint = next(
        route.endpoint for route in router.routes if route.path.endswith("/capture-current")
    )
    current_response = asyncio.run(capture_current_endpoint(
        DebugCurrentCaptureRequest(camera_id="camera_1")
    ))
    assert current_response.measurement_id == "current_debug_measurement"
