"""床校正の生成、復元、Measurementランタイム準備を担当する。"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from fastapi import HTTPException

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.ports import CalibrationGateway
from cardboard_counter_v2.api.state import (
    CameraRuntimeState,
    RuntimeState,
    RuntimeStateStore,
)
from cardboard_counter_v2.api.workflow.selectors import (
    active_camera_ids,
    pallets_for_camera,
)
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition
from cardboard_counter_v2.common.schemas import CalibrationRequest, SystemSettings


class CalibrationService:
    def __init__(
        self,
        services: CalibrationGateway,
        state_store: RuntimeStateStore,
        history: InventoryHistoryService | None = None,
    ) -> None:
        self.services = services
        self.state_store = state_store
        self.history = history
        self.definitions: OrderedDict[str, PlanarCalibrationDefinition] = OrderedDict()
        self.camera_startup_errors: dict[str, str] = {}
        self.measurement_runtime_ids: dict[str, str] = {}

    async def ensure_calibrations(self, settings: SystemSettings) -> RuntimeState:
        state = self.state_store.load()
        camera_ids = active_camera_ids(settings)
        errors: dict[str, str] = {}
        missing = [
            camera_id
            for camera_id in camera_ids
            if state.camera(camera_id).calibration_id is None
        ]
        absent = [
            camera_id
            for camera_id in missing
            if state.camera(camera_id).baseline_capture_id is None
        ]
        errors.update({
            camera_id: "先に設定画面で床画像を撮影してください"
            for camera_id in absent
        })

        async def rebuild(camera_id: str) -> tuple[str, str]:
            baseline_id = state.camera(camera_id).baseline_capture_id
            assert baseline_id is not None
            calibration_id = await self.create_calibration(
                settings,
                camera_id,
                baseline_id,
            )
            return camera_id, calibration_id

        rebuild_ids = [camera_id for camera_id in missing if camera_id not in errors]
        if rebuild_ids:
            rebuilt = await asyncio.gather(
                *(rebuild(camera_id) for camera_id in rebuild_ids),
                return_exceptions=True,
            )
            states = dict(state.cameras)
            for camera_id, rebuilt_result in zip(rebuild_ids, rebuilt, strict=True):
                if isinstance(rebuilt_result, Exception):
                    errors[camera_id] = error_text(rebuilt_result)
                    continue
                _, calibration_id = rebuilt_result
                states[camera_id] = CameraRuntimeState(
                    baseline_capture_id=state.camera(camera_id).baseline_capture_id,
                    calibration_id=calibration_id,
                )
            state = self.state_store.save(RuntimeState(cameras=states))

        prepare_ids = [
            camera_id
            for camera_id in camera_ids
            if camera_id not in errors
            and state.camera(camera_id).calibration_id is not None
        ]

        async def prepare(camera_id: str) -> None:
            calibration_id = state.camera(camera_id).calibration_id
            assert calibration_id is not None
            definition = await self.calibration_definition(calibration_id)
            await self.prepare_measurement_runtime(settings, definition)

        prepared = await asyncio.gather(
            *(prepare(camera_id) for camera_id in prepare_ids),
            return_exceptions=True,
        )
        for camera_id, prepared_result in zip(prepare_ids, prepared, strict=True):
            if isinstance(prepared_result, Exception):
                errors[camera_id] = error_text(prepared_result)

        self.camera_startup_errors.clear()
        self.camera_startup_errors.update(errors)
        if camera_ids and len(errors) == len(camera_ids):
            detail = "; ".join(
                f"{camera_id}: {errors[camera_id]}" for camera_id in camera_ids
            )
            raise HTTPException(status_code=409, detail=detail)
        return state

    async def ensure_camera_calibration(
        self,
        settings: SystemSettings,
        camera_id: str,
    ) -> RuntimeState:
        if camera_id not in active_camera_ids(settings):
            raise HTTPException(
                status_code=409,
                detail=f"{camera_id}に有効なパレットがありません",
            )
        state = self.state_store.load()
        camera_state = state.camera(camera_id)
        if camera_state.calibration_id is not None:
            definition = await self.calibration_definition(
                camera_state.calibration_id
            )
            await self.prepare_measurement_runtime(settings, definition)
            self.camera_startup_errors.pop(camera_id, None)
            return state
        if camera_state.baseline_capture_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "先に設定画面で床画像を撮影してください: "
                    f"{camera_id}"
                ),
            )
        calibration_id = await self.create_calibration(
            settings,
            camera_id,
            camera_state.baseline_capture_id,
        )
        states = dict(state.cameras)
        states[camera_id] = CameraRuntimeState(
            baseline_capture_id=camera_state.baseline_capture_id,
            calibration_id=calibration_id,
        )
        state = self.state_store.save(RuntimeState(cameras=states))
        definition = await self.calibration_definition(calibration_id)
        await self.prepare_measurement_runtime(settings, definition)
        self.camera_startup_errors.pop(camera_id, None)
        return state

    async def prepare_measurement_runtime(
        self,
        settings: SystemSettings,
        definition: PlanarCalibrationDefinition,
    ) -> str:
        runtime_id = await self.services.prepare_measurement_runtime(
            definition,
            pallets_for_camera(settings, definition.camera_id),
            settings.box_catalog,
        )
        runtime_id = runtime_id or definition.calibration_id
        self.measurement_runtime_ids[definition.camera_id] = runtime_id
        return runtime_id

    async def create_calibration(
        self,
        settings: SystemSettings,
        camera_id: str,
        baseline_capture_id: str,
    ) -> str:
        if self.history is None:
            raise RuntimeError("DB由来の撮影台帳を取得できません")
        baseline_capture = await asyncio.to_thread(
            self.history.load_capture,
            baseline_capture_id,
        )
        calibration = await self.services.calibrate(
            CalibrationRequest(
                camera_id=camera_id,
                baseline_capture_id=baseline_capture_id,
                baseline_capture=baseline_capture,
                pallets=pallets_for_camera(settings, camera_id),
                grid_mm=settings.grid_mm,
                pallet_height_mm=settings.pallet_height_mm,
            )
        )
        saved = await asyncio.to_thread(
            self.history.record_calibration,
            calibration,
            settings,
        )
        if not saved:
            status = self.history.status()
            raise HTTPException(
                status_code=503,
                detail=status.last_error or "校正結果をDBへ保存できません",
            )
        self.remember_definition(
            await asyncio.to_thread(
                self.history.load_calibration_definition,
                calibration.calibration_id,
            )
        )
        return calibration.calibration_id

    async def calibration_definition(
        self,
        calibration_id: str,
    ) -> PlanarCalibrationDefinition:
        cached = self.definitions.get(calibration_id)
        if cached is not None:
            self.definitions.move_to_end(calibration_id)
            return cached
        if self.history is None:
            raise RuntimeError("DB由来の校正定義を取得できません")
        definition = await asyncio.to_thread(
            self.history.load_calibration_definition,
            calibration_id,
        )
        self.remember_definition(definition)
        return definition

    def remember_definition(self, definition: PlanarCalibrationDefinition) -> None:
        self.definitions[definition.calibration_id] = definition
        self.definitions.move_to_end(definition.calibration_id)
        while len(self.definitions) > 64:
            self.definitions.popitem(last=False)


def error_text(exc: Exception) -> str:
    return str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
