from __future__ import annotations

import asyncio
from types import SimpleNamespace

from cardboard_counter_v2.api.field_routes import create_field_router
from cardboard_counter_v2.api.state import CameraRuntimeState, RuntimeState
from cardboard_counter_v2.common.schemas import SystemSettings


def test_camera_calibration_route_targets_only_requested_camera() -> None:
    settings = SystemSettings()
    requested: list[str] = []

    class Workflow:
        async def ensure_camera_calibration(self, received, camera_id):
            assert received == settings
            requested.append(camera_id)
            return RuntimeState(cameras={camera_id: CameraRuntimeState(
                baseline_capture_id="empty_test",
                calibration_id="calibration_test",
            )})

    context = SimpleNamespace(
        monitor=SimpleNamespace(running=lambda: False),
        operation_lock=asyncio.Lock(),
        store=SimpleNamespace(load=lambda: settings),
        workflow=Workflow(),
    )
    router = create_field_router(context)  # type: ignore[arg-type]
    endpoint = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/cameras/{camera_id}/calibration"
    )

    response = asyncio.run(endpoint("camera_1"))

    assert requested == ["camera_1"]
    assert response.camera_id == "camera_1"
    assert response.calibration_id == "calibration_test"
