"""床基準校正のHTTPルーター。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cardboard_counter_v2.api.context import ApiContext
from cardboard_counter_v2.common.schemas import CameraCalibrationResponse


def create_field_router(context: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/cameras/{camera_id}/calibration",
        response_model=CameraCalibrationResponse,
    )
    async def calibrate_camera(camera_id: str) -> CameraCalibrationResponse:
        """ROI保存後または失敗後の再試行時に、指定カメラだけを校正する。"""
        assert_available(
            context,
            monitor_message="常時監視を停止してから床基準校正を実行してください",
        )
        settings = context.store.load()
        async with context.operation_lock:
            runtime = await context.workflow.ensure_camera_calibration(
                settings, camera_id
            )
            calibration_id = runtime.camera(camera_id).calibration_id
            if calibration_id is None:
                raise HTTPException(status_code=500, detail="校正IDを保存できませんでした")
            return CameraCalibrationResponse(
                camera_id=camera_id,
                calibration_id=calibration_id,
            )

    return router


def assert_available(context: ApiContext, *, monitor_message: str) -> None:
    if context.monitor.running():
        raise HTTPException(status_code=409, detail=monitor_message)
    if context.operation_lock.locked():
        raise HTTPException(status_code=409, detail="別の撮影・測定を実行中です")
