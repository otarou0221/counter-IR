from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from cardboard_counter_v2.api.config_routes import (
    create_config_router,
    only_live_alert_settings_changed,
)
from cardboard_counter_v2.common.schemas import CameraSettings
from cardboard_counter_v2.common.schemas import SystemSettings


def complete_settings() -> SystemSettings:
    settings = SystemSettings()
    return settings.model_copy(update={
        "cameras": [camera.model_copy(update={
            "factory_name": "第5工場",
            "building_name": "第5工場",
            "floor_name": "3階",
            "area_name": "資材エリア",
        }) for camera in settings.cameras]
    })


def test_camera_restart_failure_does_not_save_new_settings() -> None:
    previous = complete_settings()
    candidate = previous.model_copy(
        update={"cameras": [previous.cameras[0].model_copy(update={"ip": "192.168.253.8"})]}
    )

    class Store:
        def __init__(self) -> None:
            self.saved: list[SystemSettings] = []

        def load(self) -> SystemSettings:
            return previous

        def save(self, settings: SystemSettings) -> SystemSettings:
            self.saved.append(settings)
            return settings

    class Services:
        async def configure_cameras(self, _settings: list[CameraSettings]):
            raise HTTPException(status_code=409, detail="camera restart failed")

    fake_store = Store()
    context = SimpleNamespace(
        store=fake_store,
        monitor=SimpleNamespace(running=lambda: False),
        operation_lock=asyncio.Lock(),
        services=Services(),
        state_store=object(),
    )
    router = create_config_router(context)  # type: ignore[arg-type]
    put_config = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/config" and "PUT" in route.methods
    )

    try:
        asyncio.run(put_config(candidate))
    except HTTPException as exc:
        assert exc.detail == "camera restart failed"
    else:
        raise AssertionError("camera restart failure must be propagated")
    assert fake_store.saved == []


def test_only_alert_thresholds_can_change_while_monitoring() -> None:
    previous = complete_settings()
    changed_alert = previous.model_copy(update={
        "pallets": [
            pallet.model_copy(update={
                "low_stock_threshold_liters": pallet.low_stock_threshold_liters + 5,
                "email_rearm_margin_liters": pallet.email_rearm_margin_liters + 10,
            })
            for pallet in previous.pallets
        ]
    })
    changed_camera = previous.model_copy(update={
        "cameras": [previous.cameras[0].model_copy(update={"ip": "192.168.253.8"})]
    })

    assert only_live_alert_settings_changed(previous, changed_alert)
    assert not only_live_alert_settings_changed(previous, changed_camera)


def test_alert_thresholds_can_be_saved_during_an_active_measurement() -> None:
    previous = complete_settings()
    candidate = previous.model_copy(update={
        "pallets": [
            pallet.model_copy(update={
                "low_stock_threshold_liters": 8.0,
                "email_rearm_margin_liters": 120.0,
            })
            for pallet in previous.pallets
        ]
    })

    class Store:
        def __init__(self) -> None:
            self.saved: list[SystemSettings] = []

        def load(self) -> SystemSettings:
            return previous

        def save(self, settings: SystemSettings) -> SystemSettings:
            self.saved.append(settings)
            return settings

    async def scenario() -> None:
        operation_lock = asyncio.Lock()
        await operation_lock.acquire()
        store = Store()
        context = SimpleNamespace(
            store=store,
            monitor=SimpleNamespace(running=lambda: True),
            operation_lock=operation_lock,
            services=object(),
            state_store=object(),
        )
        router = create_config_router(context)  # type: ignore[arg-type]
        put_config = next(
            route.endpoint
            for route in router.routes
            if route.path == "/api/config" and "PUT" in route.methods
        )
        assert await put_config(candidate) == candidate
        assert store.saved == [candidate]
        operation_lock.release()

    asyncio.run(scenario())
