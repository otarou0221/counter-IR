"""保存静止画を使う床基準ROI設定専用のHTTPルーター。"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import APIRouter, HTTPException

from cardboard_counter_v2.api.context import ApiContext
from cardboard_counter_v2.api.roi_references import RoiReferenceService, reference_from_manifest
from cardboard_counter_v2.common.schemas import (
    RoiReferenceChange,
    RoiReferenceCaptureRequest,
    RoiReferenceCatalog,
    SelectFloorCaptureRequest,
)


def create_roi_router(context: ApiContext, references: RoiReferenceService) -> APIRouter:
    router = APIRouter(prefix="/api/roi-references", tags=["roi-settings"])

    @router.get("", response_model=RoiReferenceCatalog)
    def catalog() -> RoiReferenceCatalog:
        return references.catalog()

    @router.post("/capture", response_model=RoiReferenceChange)
    async def capture_reference(request: RoiReferenceCaptureRequest) -> RoiReferenceChange:
        assert_available(context)
        settings = context.store.load()
        async with context.operation_lock:
            manifest = await context.workflow.capture_floor_reference(
                settings,
                request.camera_id,
            )
            references.activate(manifest)
            removed = await prune_floor_captures(context, references, request.camera_id)
            return RoiReferenceChange(
                reference=reference_from_manifest(manifest),
                removed_capture_ids=removed,
            )

    @router.post("/select-floor", response_model=RoiReferenceChange)
    async def select_floor(request: SelectFloorCaptureRequest) -> RoiReferenceChange:
        assert_available(context)
        settings = context.store.load()
        if not any(camera.camera_id == request.camera_id for camera in settings.cameras):
            raise HTTPException(status_code=404, detail=f"カメラ設定が見つかりません: {request.camera_id}")
        async with context.operation_lock:
            try:
                manifest = references.select_floor(request.camera_id, request.capture_id)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            removed = await prune_floor_captures(context, references, request.camera_id)
            return RoiReferenceChange(
                reference=reference_from_manifest(manifest),
                removed_capture_ids=removed,
            )

    return router


def assert_available(context: ApiContext) -> None:
    if context.monitor.running():
        raise HTTPException(status_code=409, detail="常時監視を停止してからROI画像を変更してください")
    if context.operation_lock.locked():
        raise HTTPException(status_code=409, detail="別の撮影・測定を実行中です")


async def prune_floor_captures(
    context: ApiContext,
    references: RoiReferenceService,
    camera_id: str,
) -> list[str]:
    """選択成功後だけ、使用中を除く古い空撮影を5件まで整理する。"""
    removed: list[str] = []
    for capture_id in references.excess_floor_capture_ids(camera_id):
        with suppress(HTTPException):
            await context.workflow.delete_capture(capture_id)
            removed.append(capture_id)
    return removed
