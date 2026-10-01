"""測定専用FastAPIサービス。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from cardboard_counter_v2.common.schemas import (
    CalibrationResult,
    CalibrationRequest,
    CaptureManifest,
    MeasurementRequest,
    MeasurementResponse,
    PrepareMeasurementRuntimeRequest,
    PrepareCaptureRequest,
)
from cardboard_counter_v2.measurement.calibration import calibrate
from cardboard_counter_v2.measurement.engine import measure
from cardboard_counter_v2.measurement.preprocessing import prepare_capture
from cardboard_counter_v2.measurement.storage import delete_capture
from cardboard_counter_v2.measurement.runtime import runtime_cache
from cardboard_counter_v2.measurement.prepared_runtime import prepared_runtime_registry
from cardboard_counter_v2.common.planar_calibration import PreparePlanarRuntimeRequest


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="Cardboard Measurement Service", version="0.1.0", lifespan=lifespan)
measurement_locks: dict[str, asyncio.Lock] = {}


def measurement_lock(camera_id: str) -> asyncio.Lock:
    """同一カメラの順序だけを直列化し、別カメラは並列処理する。"""
    return measurement_locks.setdefault(camera_id, asyncio.Lock())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "measurement", "method": "pallet_plane_2roi"}


@app.post("/v1/calibrations", response_model=CalibrationResult)
async def create_calibration(request: CalibrationRequest) -> CalibrationResult:
    lock = measurement_lock(request.camera_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail=f"{request.camera_id}の別処理を実行中です")
    async with lock:
        try:
            return await asyncio.to_thread(calibrate, request)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/measurements", response_model=MeasurementResponse)
async def create_measurement(request: MeasurementRequest) -> MeasurementResponse:
    lock = measurement_lock(request.camera_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail=f"{request.camera_id}の別処理を実行中です")
    async with lock:
        try:
            return await asyncio.to_thread(measure, request)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/planar-runtimes")
async def prepare_planar_runtime(
    request: PreparePlanarRuntimeRequest,
) -> dict[str, str]:
    try:
        await asyncio.to_thread(
            runtime_cache.get,
            request.calibration,
            color_shape=request.color_shape,
            depth_shape=request.depth_shape,
        )
        return {"calibration_id": request.calibration.calibration_id}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/measurement-runtimes")
async def prepare_measurement_runtime(
    request: PrepareMeasurementRuntimeRequest,
) -> dict[str, str]:
    try:
        prepared = await asyncio.to_thread(
            prepared_runtime_registry.prepare,
            request.calibration,
            request.pallets,
            request.box_catalog,
            color_shape=request.color_shape,
            depth_shape=request.depth_shape,
        )
        return {
            "calibration_id": request.calibration.calibration_id,
            "runtime_id": prepared.runtime_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/captures", response_model=CaptureManifest)
async def create_capture(request: PrepareCaptureRequest) -> CaptureManifest:
    lock = measurement_lock(request.camera_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail=f"{request.camera_id}の別処理を実行中です")
    async with lock:
        try:
            return await asyncio.to_thread(prepare_capture, request)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/v1/captures/{capture_id}")
async def remove_capture(
    capture_id: str,
    camera_id: str | None = None,
    purpose: str | None = None,
    storage_version: int = 2,
) -> dict[str, object]:
    try:
        removed = await asyncio.to_thread(
            delete_capture,
            capture_id,
            camera_id=camera_id,
            purpose=purpose,
            storage_version=storage_version,
        )
        return {"capture_id": capture_id, "removed": removed}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
