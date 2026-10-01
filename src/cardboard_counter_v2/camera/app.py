"""複数のActive IR・Depthカメラを常駐管理する汎用FastAPIサービス。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from cardboard_counter_v2.camera.fleet import CameraFleet
from cardboard_counter_v2.camera.frame_batch import save_frame_batch
from cardboard_counter_v2.camera.orbbec_adapter import default_source_registry
from cardboard_counter_v2.camera.storage import delete_frame_batch, prune_stale_frame_batches
from cardboard_counter_v2.common.camera_contracts import (
    CameraFleetConfiguration,
    CameraFleetStatus,
    CameraStreamStatus,
    FrameBatchManifest,
    FrameBatchRequest,
)
from cardboard_counter_v2.common.retention import run_periodic_cleanup


fleet = CameraFleet(source_factory=default_source_registry().create)
batch_locks: dict[str, asyncio.Lock] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 永続設定はAPI/DBだけが所有する。cameraサービスは空で起動し、
    # APIからPUTされた担当カメラだけをメモリ上で管理する。
    fleet.launch([])
    cleanup_task = asyncio.create_task(
        run_periodic_cleanup(
            prune_stale_frame_batches,
            interval_seconds=float(os.environ.get("RETENTION_CLEANUP_INTERVAL_SECONDS", "3600")),
        )
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        with suppress(RuntimeError):
            await asyncio.to_thread(fleet.stop)


def camera_hub(camera_id: str):
    try:
        return fleet.get(camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def batch_lock(camera_id: str) -> asyncio.Lock:
    return batch_locks.setdefault(camera_id, asyncio.Lock())


app = FastAPI(title="IR-Depth Camera Service", version="0.5.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "camera",
        "cameras": [status.model_dump() for status in fleet.statuses()],
    }


@app.get("/v1/cameras", response_model=CameraFleetStatus)
def camera_statuses() -> CameraFleetStatus:
    return CameraFleetStatus(cameras=fleet.statuses())


@app.put("/v1/cameras", response_model=CameraFleetStatus)
async def configure_cameras(configuration: CameraFleetConfiguration) -> CameraFleetStatus:
    if any(lock.locked() for lock in batch_locks.values()):
        raise HTTPException(status_code=409, detail="測定用フレーム取得中はカメラ設定を変更できません")
    try:
        statuses = await asyncio.to_thread(fleet.configure, configuration.cameras)
        active_ids = {camera.camera_id for camera in configuration.cameras}
        for camera_id in set(batch_locks) - active_ids:
            batch_locks.pop(camera_id, None)
        return CameraFleetStatus(cameras=statuses)
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/cameras/{camera_id}/status", response_model=CameraStreamStatus)
def camera_status(camera_id: str) -> CameraStreamStatus:
    return camera_hub(camera_id).status()


@app.get("/v1/cameras/{camera_id}/stream.mjpg")
def live_stream(camera_id: str) -> StreamingResponse:
    hub = camera_hub(camera_id)
    status = hub.status()
    if not status.running or not status.connected:
        raise HTTPException(status_code=409, detail="ライブ映像は停止しています")
    return StreamingResponse(
        hub.mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.post("/v1/cameras/{camera_id}/frame-batches", response_model=FrameBatchManifest)
async def create_frame_batch(camera_id: str, request: FrameBatchRequest) -> FrameBatchManifest:
    hub = camera_hub(camera_id)
    lock = batch_lock(camera_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail=f"{camera_id}は別のフレーム取得で使用中です")
    async with lock:
        try:
            camera = hub.status().camera
            if camera is None:
                raise RuntimeError("カメラ設定がありません")
            depth_frames, latest_ir, intrinsics, timestamps = await asyncio.to_thread(
                hub.collect_frame_batch, request
            )
            return await asyncio.to_thread(
                save_frame_batch,
                request,
                camera,
                depth_frames,
                latest_ir,
                intrinsics,
                timestamps,
            )
        except (FileNotFoundError, RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/v1/frame-batches/{batch_id}")
async def remove_frame_batch(batch_id: str) -> dict[str, object]:
    try:
        removed = await asyncio.to_thread(delete_frame_batch, batch_id)
        return {"batch_id": batch_id, "removed": removed}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
