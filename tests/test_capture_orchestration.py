from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from cardboard_counter_v2.api.internal_services import InternalServices
from cardboard_counter_v2.api.state import CameraRuntimeState, RuntimeState
from cardboard_counter_v2.api.workflows import MeasurementWorkflow
from cardboard_counter_v2.common.schemas import (
    CameraSettings,
    CameraMeasurementRun,
    CaptureManifest,
    MeasurementResponse,
    SystemSettings,
)
from cardboard_counter_v2.common.planar_calibration import (
    PlanarCalibrationDefinition,
    PlanarRegionCalibration,
    ProjectionIntrinsicsSpec,
)


def test_cardboard_capture_requires_requested_xyz() -> None:
    deleted: list[str] = []

    class Services:
        async def create_frame_batch(self, _camera_id, _request):
            return SimpleNamespace(
                batch_id="batch_without_xyz",
                median_depth_path=None,
                xyz_path=None,
            )

        async def prepare_capture(self, _request):
            raise AssertionError("XYZがないバッチをCaptureへ変換してはいけません")

        async def delete_frame_batch(self, camera_id, batch_id):
            deleted.append((camera_id, batch_id))

    workflow = MeasurementWorkflow(Services(), object())  # type: ignore[arg-type]
    with pytest.raises(HTTPException, match="中央値Depth・XYZ"):
        asyncio.run(workflow.capture(SystemSettings(), "camera_1", purpose="current"))

    assert deleted == [("camera_1", "batch_without_xyz")]


def test_camera_service_receives_only_generic_device_settings() -> None:
    requests: list[dict[str, object]] = []

    class Client:
        async def put_json(self, _url: str, payload: dict[str, object]):
            requests.append(payload)
            return {"cameras": []}

    services = InternalServices(
        Client(),  # type: ignore[arg-type]
        camera_url="http://camera:8001",
        measurement_url="http://measurement:8002",
    )
    camera = CameraSettings(
        camera_code="CAM-099",
        factory_name="第1工場",
        area_name="出荷エリア",
        mounting_note="柱へ固定",
    )

    asyncio.run(services.configure_cameras([camera]))

    device = requests[0]["cameras"][0]  # type: ignore[index]
    assert device["camera_id"] == "camera_1"  # type: ignore[index]
    assert "factory_name" not in device
    assert "area_name" not in device
    assert "mounting_note" not in device
    assert "camera_code" not in device


def test_camera_services_are_routed_by_camera_configuration() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    class Client:
        async def put_json(self, url: str, payload: dict[str, object]):
            requests.append((url, payload))
            return {
                "cameras": [
                    {"camera": camera}
                    for camera in payload["cameras"]  # type: ignore[union-attr]
                ]
            }

    services = InternalServices(
        Client(),  # type: ignore[arg-type]
        camera_url="http://camera-1:8001",
        measurement_url="http://measurement:8002",
    )
    first = CameraSettings(camera_id="camera_1")
    second = CameraSettings(
        camera_id="camera_2",
        display_name="カメラ2",
        camera_code="CAM-002",
        ip="192.168.253.8",
        location_id="location_camera_2",
        camera_service_url="http://camera-2:8001",
    )

    statuses = asyncio.run(services.configure_cameras([first, second]))

    assert {url for url, _payload in requests} == {
        "http://camera-1:8001/v1/cameras",
        "http://camera-2:8001/v1/cameras",
    }
    assert all(len(payload["cameras"]) == 1 for _url, payload in requests)  # type: ignore[arg-type]
    assert services.camera_url("camera_1") == "http://camera-1:8001"
    assert services.camera_url("camera_2") == "http://camera-2:8001"
    assert [status.camera.camera_id for status in statuses if status.camera] == [
        "camera_1", "camera_2",
    ]


def test_monitor_setup_prepares_fixed_measurement_plan_before_loop() -> None:
    settings = SystemSettings()
    active_pallets = [
        pallet for pallet in settings.pallets
        if pallet.enabled and pallet.camera_id == "camera_1"
    ]
    definition = PlanarCalibrationDefinition(
        calibration_id="calibration_1",
        camera_id="camera_1",
        calibration_capture_id="empty_1",
        projection=ProjectionIntrinsicsSpec(
            width=10, height=10, fx=10, fy=10, cx=5, cy=5,
        ),
        regions=[
            PlanarRegionCalibration(
                region_id=pallet.pallet_number,
                roi=pallet.plane_roi,
                reference_plane_normal=(0, 0, -1),
                reference_plane_offset=1000,
                surface_offset_mm=120,
                cell_size_mm=settings.grid_mm,
            )
            for pallet in active_pallets
        ],
    )
    prepared: list[tuple[object, object, object]] = []

    class Services:
        async def prepare_measurement_runtime(
            self, calibration, pallets, box_catalog
        ):
            prepared.append((calibration, pallets, box_catalog))

    class StateStore:
        def load(self):
            return RuntimeState(cameras={
                "camera_1": CameraRuntimeState(
                    baseline_capture_id="empty_1",
                    calibration_id="calibration_1",
                )
            })

    workflow = MeasurementWorkflow(Services(), StateStore())  # type: ignore[arg-type]
    workflow._calibration_definitions[definition.calibration_id] = definition  # noqa: SLF001

    asyncio.run(workflow.ensure_calibrations(settings))

    assert prepared == [(definition, active_pallets, settings.box_catalog)]


def test_monitor_setup_keeps_ready_camera_when_another_has_no_floor_capture() -> None:
    defaults = SystemSettings()
    second = CameraSettings(
        camera_id="camera_2", display_name="カメラ2", camera_code="CAM-002",
        ip="192.168.253.8", location_id="location_camera_2",
        camera_service_url="http://camera-2:8001",
    )
    settings = defaults.model_copy(update={
        "cameras": [defaults.cameras[0], second],
        "pallets": [
            defaults.pallets[0], defaults.pallets[1],
            defaults.pallets[0].model_copy(update={
                "pallet_id": 3, "camera_id": "camera_2", "enabled": True,
            }),
            defaults.pallets[1].model_copy(update={
                "pallet_id": 4, "camera_id": "camera_2", "enabled": False,
            }),
        ],
    })
    pallet = defaults.pallets[0]
    definition = PlanarCalibrationDefinition(
        calibration_id="calibration_1",
        camera_id="camera_1",
        calibration_capture_id="empty_1",
        projection=ProjectionIntrinsicsSpec(
            width=10, height=10, fx=10, fy=10, cx=5, cy=5,
        ),
        regions=[PlanarRegionCalibration(
            region_id=1, roi=pallet.plane_roi,
            reference_plane_normal=(0, 0, -1),
            reference_plane_offset=1000, surface_offset_mm=120,
            cell_size_mm=10,
        )],
    )
    prepared: list[str] = []

    class Services:
        async def prepare_measurement_runtime(
            self, calibration, _pallets, _box_catalog,
        ):
            prepared.append(calibration.camera_id)

    class StateStore:
        def load(self):
            return RuntimeState(cameras={
                "camera_1": CameraRuntimeState(
                    baseline_capture_id="empty_1",
                    calibration_id="calibration_1",
                ),
                "camera_2": CameraRuntimeState(),
            })

    workflow = MeasurementWorkflow(Services(), StateStore())  # type: ignore[arg-type]
    workflow._calibration_definitions["calibration_1"] = definition  # noqa: SLF001

    runtime = asyncio.run(workflow.ensure_calibrations(settings))

    assert runtime.camera("camera_1").calibration_id == "calibration_1"
    assert prepared == ["camera_1"]
    assert workflow._camera_startup_errors == {  # noqa: SLF001
        "camera_2": "先に設定画面で床画像を撮影してください"
    }


def test_api_keeps_purpose_out_of_generic_camera_request() -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    deletions: list[str] = []

    class Client:
        async def post_json(self, url: str, payload: dict[str, object]):
            requests.append((url, payload))
            if url.endswith("/frame-batches"):
                return {
                    "batch_id": "batch_test",
                    "camera_id": "camera_1",
                    "captured_at": "2026-07-31T00:00:03+00:00",
                    "frame_timestamps": ["2026-07-31T00:00:03+00:00"] * 3,
                    "depth_frames_path": "camera/frame_batches/batch_test/depth_frames.npz",
                    "rgb_path": "camera/frame_batches/batch_test/rgb.jpg",
                    "intrinsics_path": "camera/frame_batches/batch_test/intrinsics.json",
                    "metadata_path": "camera/frame_batches/batch_test/metadata.json",
                    "median_depth_path": "camera/frame_batches/batch_test/median_depth.npz",
                    "xyz_path": "camera/frame_batches/batch_test/xyz.npz",
                    "xyz_source": "temporal_median_ignore_zero",
                    "frame_count": 3,
                    "color_shape": [720, 1280],
                    "depth_shape": [720, 1280],
                    "depth_aligned_to_color": True,
                }
            return {
                "capture_id": "capture_test",
                "camera_id": payload["camera_id"],
                "purpose": payload["purpose"],
                "retention": payload["retention"],
                "source_batch_id": payload["batch_id"],
                "depth_path": "captures/capture_test/depth.npz",
                "xyz_path": "captures/capture_test/xyz.npz",
                "rgb_path": "captures/capture_test/rgb.jpg",
                "intrinsics_path": "captures/capture_test/intrinsics.json",
                "frame_count": 3,
                "color_shape": [720, 1280],
                "depth_shape": [720, 1280],
                "depth_aligned_to_color": True,
            }

        async def delete_json(self, url: str):
            deletions.append(url)
            return {"removed": True}

    services = InternalServices(
        Client(),  # type: ignore[arg-type]
        camera_url="http://camera:8001",
        measurement_url="http://measurement:8002",
    )
    workflow = MeasurementWorkflow(services, object())  # type: ignore[arg-type]
    result = asyncio.run(
        workflow.capture(
            SystemSettings(frame_count=3, warmup_frames=0),
            "camera_1",
            purpose="floor",
        )
    )

    assert result.capture_id == "capture_test"
    assert "purpose" not in requests[0][1]
    assert "camera" not in requests[0][1]
    assert requests[0][1]["include_xyz"] is True
    assert requests[0][1]["include_raw_frames"] is False
    assert requests[1][1] == {
        "camera_id": "camera_1",
        "batch_id": "batch_test",
        "purpose": "floor",
        "retention": "persistent",
    }
    assert deletions == ["http://camera:8001/v1/frame-batches/batch_test"]


def test_measurement_cycle_captures_different_cameras_in_parallel() -> None:
    defaults = SystemSettings()
    settings = defaults.model_copy(update={
        "cameras": [
            defaults.cameras[0],
            CameraSettings(camera_id="camera_2", display_name="カメラ2", ip="192.168.253.8"),
        ],
        "pallets": [
            defaults.pallets[0],
            defaults.pallets[1],
            defaults.pallets[0].model_copy(update={
                "pallet_id": 3, "pallet_number": 1, "camera_id": "camera_2", "enabled": True,
            }),
            defaults.pallets[1].model_copy(update={
                "pallet_id": 4, "pallet_number": 2, "camera_id": "camera_2", "enabled": False,
            }),
        ],
    })
    started: set[str] = set()
    both_started = asyncio.Event()
    deleted: list[str] = []
    measurement_requests = []
    frame_requests = []

    class Services:
        async def create_frame_batch(self, camera_id, request):
            frame_requests.append((camera_id, request))
            started.add(camera_id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return SimpleNamespace(
                batch_id=f"batch_{camera_id}",
                median_depth_path="median_depth.npz",
                xyz_path="xyz.npz",
            )

        async def prepare_capture(self, request):
            return CaptureManifest(
                capture_id=f"capture_{request.camera_id}", camera_id=request.camera_id,
                purpose=request.purpose, retention=request.retention,
                depth_path="depth.npz", rgb_path="rgb.jpg",
                xyz_path="xyz.npz",
                frame_count=3, color_shape=(10, 10), depth_shape=(10, 10),
                depth_aligned_to_color=True,
            )

        async def delete_frame_batch(self, _camera_id, _batch_id):
            return None

        async def delete_capture(self, capture_id):
            deleted.append(capture_id)

        async def prepare_measurement_runtime(
            self, _calibration, _pallets, _box_catalog
        ):
            return None

        async def measure(self, request):
            measurement_requests.append(request)
            return MeasurementResponse(
                measurement_id=f"measurement_{request.camera_id}",
                camera_runs=[CameraMeasurementRun(
                    camera_id=request.camera_id,
                    measurement_id=f"measurement_{request.camera_id}",
                    calibration_id=request.calibration_id,
                    baseline_capture_id=f"empty_{request.camera_id}",
                    current_capture_id=request.current_capture_id,
                )],
                pallets=[],
            )

    runtime = RuntimeState(cameras={
        camera.camera_id: CameraRuntimeState(
            baseline_capture_id=f"empty_{camera.camera_id}",
            calibration_id=f"calibration_{camera.camera_id}",
        )
        for camera in settings.cameras
    })

    workflow = MeasurementWorkflow(Services(), object())  # type: ignore[arg-type]
    for camera_id in ("camera_1", "camera_2"):
        pallet = next(
            item for item in settings.pallets
            if item.camera_id == camera_id and item.enabled
        )
        calibration_id = f"calibration_{camera_id}"
        workflow._calibration_definitions[calibration_id] = (  # noqa: SLF001
            PlanarCalibrationDefinition(
                calibration_id=calibration_id,
                camera_id=camera_id,
                calibration_capture_id=f"empty_{camera_id}",
                projection=ProjectionIntrinsicsSpec(
                    width=10, height=10, fx=10, fy=10, cx=5, cy=5,
                ),
                regions=[PlanarRegionCalibration(
                    region_id=pallet.pallet_number,
                    roi=pallet.plane_roi,
                    reference_plane_normal=(0, 0, -1),
                    reference_plane_offset=1000,
                    surface_offset_mm=120,
                    cell_size_mm=10,
                )],
            )
        )
    result = asyncio.run(workflow.measure_cycle(
        settings, runtime, generate_artifacts=False, persistent=False,
    ))

    assert started == {"camera_1", "camera_2"}
    assert {run.camera_id for run in result.camera_runs} == started
    assert deleted == []
    assert all(not request.generate_artifacts for request in measurement_requests)
    assert all(not request.generate_debug_stages for request in measurement_requests)
    assert all(request.runtime_id for request in measurement_requests)
    assert all(request.calibration is None for request in measurement_requests)
    assert all(not request.pallets for request in measurement_requests)
    assert {request.frame_count for _camera_id, request in frame_requests} == {1}

    class StateStore:
        def load(self):
            return runtime

    debug_workflow = MeasurementWorkflow(Services(), StateStore())  # type: ignore[arg-type]
    debug_workflow._calibration_definitions.update(  # noqa: SLF001
        workflow._calibration_definitions  # noqa: SLF001
    )
    debug_result = asyncio.run(debug_workflow.capture_current_debug(settings, "camera_1"))
    assert debug_result.camera_runs[0].camera_id == "camera_1"
    assert measurement_requests[-1].generate_artifacts is True
    assert measurement_requests[-1].generate_debug_stages is True
    assert frame_requests[-1][1].frame_count == 1


def test_camera_configuration_isolated_when_one_service_is_down() -> None:
    class Client:
        async def put_json(self, url: str, payload: dict[str, object]):
            if "camera-2" in url:
                raise HTTPException(status_code=502, detail="camera-2 unavailable")
            return {"cameras": [{"camera": item} for item in payload["cameras"]]}

    defaults = SystemSettings()
    second = CameraSettings(
        camera_id="camera_2",
        display_name="カメラ2",
        camera_code="CAM-002",
        ip="192.168.253.8",
        location_id="location_camera_2",
        camera_service_url="http://camera-2:8001",
    )
    services = InternalServices(
        Client(),  # type: ignore[arg-type]
        camera_url="http://camera-1:8001",
        measurement_url="http://measurement:8002",
    )

    statuses = asyncio.run(
        services.configure_cameras([defaults.cameras[0], second])
    )

    assert statuses[0].error is None
    assert statuses[1].error == "camera-2 unavailable"


def test_camera_status_fanout_is_cached() -> None:
    calls = 0

    class Client:
        async def put_json(self, _url: str, payload: dict[str, object]):
            return {"cameras": [{"camera": item} for item in payload["cameras"]]}

        async def get_json(self, _url: str):
            nonlocal calls
            calls += 1
            return {"cameras": [{"camera": SystemSettings().cameras[0].model_dump()}]}

    services = InternalServices(
        Client(),  # type: ignore[arg-type]
        camera_url="http://camera-1:8001",
        measurement_url="http://measurement:8002",
        camera_status_ttl_seconds=30,
    )
    camera = SystemSettings().cameras[0]
    asyncio.run(services.configure_cameras([camera]))

    async def read_twice():
        await services.camera_statuses()
        await services.camera_statuses()

    asyncio.run(read_twice())
    assert calls == 1


def test_camera_measurement_jobs_honor_concurrency_and_isolate_failure() -> None:
    defaults = SystemSettings()
    settings = defaults.model_copy(update={
        "measurement_concurrency": 1,
        "cameras": [
            defaults.cameras[0],
            CameraSettings(
                camera_id="camera_2", display_name="カメラ2",
                camera_code="CAM-002", ip="192.168.253.8",
                location_id="location_camera_2",
                camera_service_url="http://camera-2:8001",
            ),
        ],
        "pallets": [
            defaults.pallets[0], defaults.pallets[1],
            defaults.pallets[0].model_copy(update={
                "pallet_id": 3, "camera_id": "camera_2", "enabled": True,
            }),
            defaults.pallets[1].model_copy(update={
                "pallet_id": 4, "camera_id": "camera_2", "enabled": False,
            }),
        ],
    })
    active = 0
    maximum = 0

    workflow = MeasurementWorkflow(object(), object())  # type: ignore[arg-type]

    async def measure_camera(
        _settings, _runtime, camera_id, *, generate_artifacts, persistent,
    ):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        if camera_id == "camera_2":
            raise RuntimeError("camera disconnected")
        return MeasurementResponse(
            measurement_id="measurement_camera_1",
            camera_runs=[CameraMeasurementRun(
                camera_id="camera_1",
                measurement_id="measurement_camera_1",
                calibration_id="calibration_camera_1",
                baseline_capture_id="empty_camera_1",
                current_capture_id="current_camera_1",
            )],
            pallets=[],
        )

    workflow.measure_camera = measure_camera  # type: ignore[method-assign]
    outcomes = asyncio.run(workflow.measure_camera_jobs(
        settings, RuntimeState(), generate_artifacts=False, persistent=False,
    ))

    assert maximum == 1
    assert outcomes[0].result is not None
    assert str(outcomes[1].error) == "camera disconnected"


def test_roi_reference_capture_is_one_shot_and_keeps_business_terms_out_of_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_inline(operation, *args, **kwargs):
        return operation(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", run_inline)
    settings = SystemSettings(frame_count=9, warmup_frames=2)
    frame_requests = []
    recorded_captures: list[str] = []

    class Services:
        async def create_frame_batch(self, camera_id, request):
            frame_requests.append((camera_id, request))
            return SimpleNamespace(
                batch_id=f"batch_{len(frame_requests)}",
                median_depth_path="median_depth.npz",
                xyz_path="xyz.npz",
            )

        async def prepare_capture(self, request):
            return CaptureManifest(
                capture_id=f"capture_{len(frame_requests)}",
                camera_id=request.camera_id,
                purpose=request.purpose,
                retention=request.retention,
                depth_path="depth.npz",
                xyz_path="xyz.npz",
                rgb_path="rgb.jpg",
                frame_count=frame_requests[-1][1].frame_count,
                color_shape=(10, 10),
                depth_shape=(10, 10),
                depth_aligned_to_color=True,
                captured_at="2026-08-04T00:00:00+00:00",
            )

        async def delete_frame_batch(self, _camera_id, _batch_id):
            return None

    class StateStore:
        def __init__(self):
            self.state = RuntimeState()

        def load(self):
            return self.state

        def save(self, state):
            self.state = state
            return state

    class History:
        def register_capture(self, manifest):
            recorded_captures.append(manifest.capture_id)
            return True

        def excess_current_capture_ids(self, _camera_id):
            return []

    state_store = StateStore()
    workflow = MeasurementWorkflow(Services(), state_store, History())  # type: ignore[arg-type]

    floor = asyncio.run(workflow.capture_floor_reference(settings, "camera_1"))

    assert floor.purpose == "floor"
    assert [request.frame_count for _camera_id, request in frame_requests] == [9]
    assert all(request.include_xyz for _camera_id, request in frame_requests)
    assert all(not hasattr(request, "purpose") for _camera_id, request in frame_requests)
    assert recorded_captures == [floor.capture_id]
    # 参照撮影の選択・保持はRoiReferenceServiceへ分離され、測定ワークフローは状態を変えない。
    assert state_store.state.camera("camera_1").baseline_capture_id is None


def test_capture_deletion_sends_storage_location() -> None:
    deletions: list[str] = []

    class Client:
        async def delete_json(self, url: str):
            deletions.append(url)
            return {"removed": True}

    services = InternalServices(
        Client(),  # type: ignore[arg-type]
        camera_url="http://camera:8001",
        measurement_url="http://measurement:8002",
    )
    capture = CaptureManifest(
        capture_id="capture_test",
        camera_id="camera_2",
        purpose="current",
        retention="transient",
        storage_version=3,
        depth_path="captures/camera_2/current/capture_test/depth.npz",
        xyz_path="captures/camera_2/current/capture_test/xyz.npz",
        rgb_path="captures/camera_2/current/capture_test/rgb.jpg",
        frame_count=1,
        color_shape=(720, 1280),
        depth_shape=(720, 1280),
        depth_aligned_to_color=True,
    )

    asyncio.run(services.delete_capture(capture))

    assert deletions == [
        "http://measurement:8002/v1/captures/capture_test?"
        "camera_id=camera_2&purpose=current&storage_version=3"
    ]
