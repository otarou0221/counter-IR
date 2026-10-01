"""現在撮影と保存撮影を、新方式の段階別診断へつなぐルーター。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.settings import SettingsStore
from cardboard_counter_v2.common.capture_policy import CURRENT_CAPTURES_PER_CAMERA
from cardboard_counter_v2.common.schemas import (
    CalibrationResult,
    CalibrationRequest,
    CaptureManifest,
    DebugCurrentCaptureRequest,
    DebugDataCatalog,
    DebugReplayRequest,
    MeasurementRequest,
    MeasurementResponse,
    PalletSettings,
    SystemSettings,
)
from cardboard_counter_v2.common.box_catalog import BoxClassSpec
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition


CalibrationCall = Callable[[CalibrationRequest], Awaitable[CalibrationResult]]
MeasurementCall = Callable[[MeasurementRequest], Awaitable[MeasurementResponse]]
RuntimePreparationCall = Callable[
    [PlanarCalibrationDefinition, list[PalletSettings], list[BoxClassSpec]],
    Awaitable[str],
]
CurrentDebugCall = Callable[[SystemSettings, str], Awaitable[MeasurementResponse]]


def create_debug_router(
    *,
    store: SettingsStore,
    operation_lock: asyncio.Lock,
    monitoring: Callable[[], bool],
    request_calibration: CalibrationCall,
    request_measurement: MeasurementCall,
    prepare_measurement_runtime: RuntimePreparationCall,
    request_current_debug: CurrentDebugCall,
    history: InventoryHistoryService,
) -> APIRouter:
    router = APIRouter(prefix="/api/debug", tags=["debug"])

    @router.get("/catalog", response_model=DebugDataCatalog)
    def catalog(
        camera_id: Annotated[
            str,
            Query(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"),
        ],
        current_offset: Annotated[
            int,
            Query(ge=0, le=CURRENT_CAPTURES_PER_CAMERA),
        ] = 0,
        current_limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> DebugDataCatalog:
        settings = store.load()
        if not any(camera.camera_id == camera_id for camera in settings.cameras):
            raise HTTPException(
                status_code=404,
                detail=f"カメラ設定が見つかりません: {camera_id}",
            )
        floor = history.list_captures(
            camera_id=camera_id,
            purpose="floor",
            retention="persistent",
        )
        page_limit = min(
            current_limit,
            CURRENT_CAPTURES_PER_CAMERA - current_offset,
        )
        current_page = [] if page_limit <= 0 else history.list_captures(
            camera_id=camera_id,
            purpose="current",
            limit=page_limit + 1,
            offset=current_offset,
        )
        return DebugDataCatalog(
            camera_id=camera_id,
            floor_captures=[saved_capture_summary(item) for item in floor],
            current_captures=[
                saved_capture_summary(item)
                for item in current_page[:page_limit]
            ],
            current_has_more=(
                len(current_page) > page_limit
                and current_offset + page_limit < CURRENT_CAPTURES_PER_CAMERA
            ),
            current_capture_limit=CURRENT_CAPTURES_PER_CAMERA,
        )

    @router.post("/replay", response_model=MeasurementResponse)
    async def replay(request: DebugReplayRequest) -> MeasurementResponse:
        if monitoring():
            raise HTTPException(status_code=409, detail="常時監視を停止してから再解析してください")
        if operation_lock.locked():
            raise HTTPException(status_code=409, detail="別の撮影・測定を実行中です")
        settings = store.load()
        async with operation_lock:
            try:
                baseline = history.load_capture(request.baseline_capture_id)
                current = history.load_capture(request.current_capture_id)
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if baseline.camera_id != current.camera_id:
                raise HTTPException(
                    status_code=409,
                    detail="床基準撮影と積載撮影のカメラが一致しません",
                )
            pallets = [
                pallet for pallet in settings.pallets
                if pallet.enabled and pallet.camera_id == baseline.camera_id
            ]
            if not pallets:
                raise HTTPException(status_code=409, detail="このカメラに有効なパレットがありません")
            calibration = await request_calibration(
                CalibrationRequest(
                    camera_id=baseline.camera_id,
                    baseline_capture_id=request.baseline_capture_id,
                    baseline_capture=baseline,
                    pallets=pallets,
                    grid_mm=settings.grid_mm,
                    pallet_height_mm=settings.pallet_height_mm,
                )
            )
            runtime_id = await prepare_measurement_runtime(
                calibration.definition(),
                pallets,
                settings.box_catalog,
            )
            result = await request_measurement(
                MeasurementRequest(
                    camera_id=baseline.camera_id,
                    runtime_id=runtime_id,
                    current_capture_id=request.current_capture_id,
                    current_capture=current,
                    occupied_height_mm=settings.occupied_height_mm,
                    generate_artifacts=True,
                    generate_debug_stages=True,
                )
            )
            return result

    @router.post("/capture-current", response_model=MeasurementResponse)
    async def capture_current(request: DebugCurrentCaptureRequest) -> MeasurementResponse:
        if monitoring():
            raise HTTPException(status_code=409, detail="常時監視を停止してから診断撮影してください")
        if operation_lock.locked():
            raise HTTPException(status_code=409, detail="別の撮影・測定を実行中です")
        settings = store.load()
        if not any(camera.camera_id == request.camera_id for camera in settings.cameras):
            raise HTTPException(status_code=404, detail=f"カメラ設定が見つかりません: {request.camera_id}")
        async with operation_lock:
            result = await request_current_debug(settings, request.camera_id)
            return result

    return router


def saved_capture_summary(manifest: CaptureManifest):
    from cardboard_counter_v2.common.schemas import SavedCaptureSummary

    return SavedCaptureSummary(
        capture_id=manifest.capture_id,
        camera_id=manifest.camera_id,
        purpose=manifest.purpose,
        retention=manifest.retention,
        captured_at=manifest.captured_at or "",
        frame_count=manifest.frame_count,
        color_shape=manifest.color_shape,
        depth_shape=manifest.depth_shape,
        rgb_path=manifest.rgb_path,
    )
