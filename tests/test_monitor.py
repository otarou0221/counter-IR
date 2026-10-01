from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from cardboard_counter_v2.api.monitoring import MonitorController
from cardboard_counter_v2.api.state import RuntimeState
from cardboard_counter_v2.api.state import CameraRuntimeState
from cardboard_counter_v2.api.workflows import CameraMeasurementOutcome
from cardboard_counter_v2.common.schemas import (
    CameraMeasurementRun,
    MeasurementResponse,
    SystemSettings,
)


def test_monitor_loop_records_result_and_stops() -> None:
    stop_event = asyncio.Event()
    cycle_requests = []
    settings = SystemSettings().model_copy(update={"monitor_interval_seconds": 1})

    class Store:
        def load(self) -> SystemSettings:
            return settings

    class Workflow:
        async def measure_camera_jobs(self, settings, runtime, *, generate_artifacts, persistent):
            cycle_requests.append((settings, runtime, generate_artifacts, persistent))
            stop_event.set()
            result = MeasurementResponse(
                measurement_id="measurement_test",
                camera_runs=[CameraMeasurementRun(
                    camera_id="camera_1",
                    measurement_id="measurement_test",
                    calibration_id="calibration_test",
                    baseline_capture_id="empty_test",
                    current_capture_id="current_test",
                )],
                pallets=[],
            )
            now = datetime.now(UTC)
            return [CameraMeasurementOutcome(
                camera_id="camera_1",
                started_at=now,
                finished_at=now,
                result=result,
            )]

    monitor = MonitorController(
        store=Store(),  # type: ignore[arg-type]
        workflow=Workflow(),  # type: ignore[arg-type]
        operation_lock=asyncio.Lock(),
    )
    runtime = RuntimeState(cameras={"camera_1": CameraRuntimeState(
        baseline_capture_id="empty_test", calibration_id="calibration_test",
    )})
    asyncio.run(monitor.run_loop(stop_event, settings, runtime))

    assert monitor.status.completed_measurements == 1
    assert monitor.status.last_result is not None
    assert monitor.status.last_result.measurement_id == "measurement_test"
    assert monitor.status.running is False
    assert monitor.status.last_error is None
    assert monitor.status.last_outcome == "success"
    assert monitor.status.last_issues == []
    assert cycle_requests[0][1].camera("camera_1").calibration_id == "calibration_test"
    assert cycle_requests[0][2] is False
    assert cycle_requests[0][3] is False


def test_monitor_saves_success_and_failure_per_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_inline(operation, *args, **kwargs):
        return operation(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", run_inline)
    stop_event = asyncio.Event()
    settings = SystemSettings().model_copy(update={"monitor_interval_seconds": 1})
    saved_successes: list[str] = []
    saved_failures: list[str | None] = []

    class Store:
        def load(self) -> SystemSettings:
            return settings

    class Workflow:
        async def measure_camera_jobs(self, *_args, **_kwargs):
            stop_event.set()
            now = datetime.now(UTC)
            result = MeasurementResponse(
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
            return [
                CameraMeasurementOutcome(
                    camera_id="camera_1", started_at=now,
                    finished_at=now, result=result,
                ),
                CameraMeasurementOutcome(
                    camera_id="camera_2", started_at=now,
                    finished_at=now, error=RuntimeError("offline"),
                ),
            ]

    class History:
        def record_success(self, result, _settings, **_timestamps):
            saved_successes.append(result.camera_runs[0].camera_id)

        def record_failure(self, *, camera_id=None, **_details):
            saved_failures.append(camera_id)

    monitor = MonitorController(
        store=Store(),  # type: ignore[arg-type]
        workflow=Workflow(),  # type: ignore[arg-type]
        operation_lock=asyncio.Lock(),
        history=History(),  # type: ignore[arg-type]
    )
    asyncio.run(monitor.run_loop(stop_event, settings, RuntimeState()))

    assert saved_successes == ["camera_1"]
    assert saved_failures == ["camera_2"]
    assert monitor.status.completed_measurements == 1
    assert monitor.status.consecutive_errors == 0
    assert monitor.status.last_error == "camera_2: offline"
    assert monitor.status.last_outcome == "partial_failure"
    assert len(monitor.status.last_issues) == 1
    issue = monitor.status.last_issues[0]
    assert issue.category == "camera_connection"
    assert issue.camera_id == "camera_2"
    assert issue.action_target == "field_camera"
