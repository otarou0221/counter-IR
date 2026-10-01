"""設定更新とシステム状態のHTTPルーター。"""

from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from cardboard_counter_v2.api.context import ApiContext
from cardboard_counter_v2.api.config_validation import validate_camera_settings_update
from cardboard_counter_v2.common.camera_contracts import CameraStreamStatus
from cardboard_counter_v2.common.schemas import SystemSettings, SystemStatus


def create_config_router(context: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "api",
            "method": "pallet_plane_2roi",
            "database": context.history.status().model_dump(),
        }

    @router.get("/api/config", response_model=SystemSettings)
    def get_config() -> SystemSettings:
        return context.store.load()

    @router.put("/api/config", response_model=SystemSettings)
    async def put_config(settings: SystemSettings) -> SystemSettings:
        previous = context.store.load()
        try:
            validate_camera_settings_update(previous, settings)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        monitoring = context.monitor.running()
        live_alert_update = monitoring and only_live_alert_settings_changed(
            previous,
            settings,
        )
        if monitoring and not live_alert_update:
            raise HTTPException(
                status_code=409,
                detail=(
                    "監視中に変更できるのは低在庫しきい値と"
                    "メール再有効化増加量だけです"
                ),
            )
        if live_alert_update:
            # 測定処理とは独立したDB設定更新。実行中の測定値には触れず、
            # MonitorControllerが次周期の先頭でメモリ上の最新設定を読む。
            return context.store.save(settings)
        if context.operation_lock.locked():
            raise HTTPException(status_code=409, detail="別の撮影・測定を実行中です")
        async with context.operation_lock:
            camera_changes = changed_camera_service_ids(previous, settings)
            if camera_changes:
                await context.services.configure_cameras(settings.cameras)
            try:
                saved = context.store.save(settings)
            except Exception:
                if camera_changes:
                    with suppress(HTTPException):
                        await context.services.configure_cameras(previous.cameras)
                raise
            calibration_camera_changes = changed_camera_calibration_ids(previous, settings)
            if calibration_camera_changes:
                context.state_store.clear(camera_ids=calibration_camera_changes)
            plane_changes = changed_calibration_ids(previous, settings) - calibration_camera_changes
            if plane_changes:
                context.state_store.clear(keep_baseline=True, camera_ids=plane_changes)
            context.monitor.update_interval(saved.monitor_interval_seconds)
            return saved

    @router.get("/api/status", response_model=SystemStatus)
    async def status() -> SystemStatus:
        runtime = context.state_store.load()
        return SystemStatus(
            busy=context.operation_lock.locked(),
            monitor=context.monitor.current_status(),
            cameras=await context.services.camera_statuses(),
            database=context.history.status(),
            calibrated_camera_ids=sorted(
                camera_id for camera_id, state in runtime.cameras.items()
                if state.calibration_id is not None
            ),
        )

    @router.get("/api/cameras/{camera_id}/stream/status", response_model=CameraStreamStatus)
    async def camera_stream_status(camera_id: str) -> CameraStreamStatus:
        return await context.services.camera_status(camera_id)

    @router.get("/api/cameras/{camera_id}/stream.mjpg")
    async def camera_stream(camera_id: str) -> StreamingResponse:
        response = await context.services.open_camera_stream(camera_id)

        async def body():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(
            body(),
            media_type=response.headers.get(
                "content-type", "multipart/x-mixed-replace; boundary=frame"
            ),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    return router


def only_live_alert_settings_changed(
    previous: SystemSettings,
    current: SystemSettings,
) -> bool:
    """監視計画を変えず、次周期から安全に反映できる設定だけか判定する。"""
    before = previous.model_dump(mode="json")
    after = current.model_dump(mode="json")
    for payload in (before, after):
        pallets = payload.get("pallets")
        if not isinstance(pallets, list):
            continue
        for pallet in pallets:
            if isinstance(pallet, dict):
                pallet.pop("low_stock_threshold_liters", None)
                pallet.pop("email_rearm_margin_liters", None)
    return before == after


def changed_camera_service_ids(previous: SystemSettings, current: SystemSettings) -> set[str]:
    before = {camera.camera_id: camera for camera in previous.cameras}
    after = {camera.camera_id: camera for camera in current.cameras}
    return {
        camera_id for camera_id in set(before) | set(after)
        if camera_service_signature(before.get(camera_id))
        != camera_service_signature(after.get(camera_id))
    }


def camera_service_signature(camera) -> tuple[object, ...] | None:
    if camera is None:
        return None
    return (
        camera.driver, camera.ip, camera.port, camera.width, camera.height,
        camera.depth_width, camera.depth_height, camera.fps,
        camera.align_depth_to_color, camera.camera_service_url,
    )


def changed_camera_calibration_ids(
    previous: SystemSettings, current: SystemSettings
) -> set[str]:
    before = {camera.camera_id: camera for camera in previous.cameras}
    after = {camera.camera_id: camera for camera in current.cameras}
    return {
        camera_id for camera_id in set(before) | set(after)
        if camera_calibration_signature(before.get(camera_id))
        != camera_calibration_signature(after.get(camera_id))
    }


def camera_calibration_signature(camera) -> tuple[object, ...] | None:
    if camera is None:
        return None
    return (
        camera.location_id, camera.serial_number, camera.driver,
        camera.width, camera.height, camera.depth_width, camera.depth_height,
        camera.align_depth_to_color,
    )


def changed_calibration_ids(previous: SystemSettings, current: SystemSettings) -> set[str]:
    before = calibration_signatures(previous)
    after = calibration_signatures(current)
    return {
        camera_id for camera_id in set(before) | set(after)
        if before.get(camera_id) != after.get(camera_id)
    }


def calibration_signatures(settings: SystemSettings) -> dict[str, tuple[object, ...]]:
    return {
        camera.camera_id: (
            settings.grid_mm,
            settings.pallet_height_mm,
            tuple(
                (pallet.pallet_id, pallet.enabled, pallet.plane_roi)
                for pallet in sorted(settings.pallets, key=lambda item: item.pallet_id)
                if pallet.camera_id == camera.camera_id
            ),
        )
        for camera in settings.cameras
    }
