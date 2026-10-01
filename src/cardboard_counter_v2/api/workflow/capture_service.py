"""汎用cameraサービスからCardboard用Captureを作成する。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Literal

from fastapi import HTTPException

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.ports import CaptureWorkflowGateway
from cardboard_counter_v2.api.workflow.retention_service import CaptureRetentionService
from cardboard_counter_v2.common.camera_contracts import FrameBatchRequest
from cardboard_counter_v2.common.schemas import (
    CaptureManifest,
    PrepareCaptureRequest,
    SystemSettings,
)


class CaptureService:
    def __init__(
        self,
        services: CaptureWorkflowGateway,
        retention: CaptureRetentionService,
        history: InventoryHistoryService | None = None,
    ) -> None:
        self.services = services
        self.retention = retention
        self.history = history

    async def capture(
        self,
        settings: SystemSettings,
        camera_id: str,
        *,
        purpose: Literal["floor", "current"],
        persistent: bool = True,
        frame_count: int | None = None,
    ) -> CaptureManifest:
        batch = await self.services.create_frame_batch(
            camera_id,
            FrameBatchRequest(
                frame_count=frame_count or settings.frame_count,
                warmup_frames=settings.warmup_frames,
                include_xyz=True,
                include_raw_frames=False,
            ),
        )
        try:
            if batch.xyz_path is None or batch.median_depth_path is None:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "カメラサービスが要求された中央値Depth・XYZを"
                        "返しませんでした"
                    ),
                )
            capture = await self.services.prepare_capture(
                PrepareCaptureRequest(
                    camera_id=camera_id,
                    batch_id=batch.batch_id,
                    purpose=purpose,
                    retention="persistent" if persistent else "transient",
                    intrinsics=getattr(batch, "intrinsics", None),
                )
            )
            if capture.xyz_path is None:
                with suppress(HTTPException):
                    await self.services.delete_capture(capture)
                raise HTTPException(
                    status_code=502,
                    detail="測定サービスがXYZ付きCaptureを返しませんでした",
                )
            await self._register_capture(capture)
            if capture.purpose == "current":
                await self.retention.prune_current_captures(camera_id)
            return capture
        finally:
            with suppress(HTTPException):
                await self.services.delete_frame_batch(camera_id, batch.batch_id)

    async def _register_capture(self, capture: CaptureManifest) -> None:
        if self.history is None:
            return
        saved = await asyncio.to_thread(self.history.register_capture, capture)
        if saved:
            return
        with suppress(HTTPException):
            await self.services.delete_capture(capture)
        status = self.history.status()
        raise HTTPException(
            status_code=503,
            detail=status.last_error or "撮影台帳をDBへ保存できません",
        )

    async def capture_floor_reference(
        self,
        settings: SystemSettings,
        camera_id: str,
    ) -> CaptureManifest:
        if not any(camera.camera_id == camera_id for camera in settings.cameras):
            raise HTTPException(
                status_code=404,
                detail=f"カメラ設定が見つかりません: {camera_id}",
            )
        return await self.capture(
            settings,
            camera_id,
            purpose="floor",
            persistent=True,
            frame_count=settings.frame_count,
        )
