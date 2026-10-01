"""1台測定と複数カメラジョブの並列実行を担当する。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import uuid

from fastapi import HTTPException

from cardboard_counter_v2.api.ports import MeasurementExecutionGateway
from cardboard_counter_v2.api.state import RuntimeState
from cardboard_counter_v2.api.workflow.calibration_service import CalibrationService
from cardboard_counter_v2.api.workflow.capture_service import CaptureService
from cardboard_counter_v2.api.workflow.selectors import active_camera_ids
from cardboard_counter_v2.common.schemas import (
    CaptureManifest,
    MeasurementRequest,
    MeasurementResponse,
    SystemSettings,
)


class MeasurementJobRunner:
    def __init__(
        self,
        services: MeasurementExecutionGateway,
        captures: CaptureService,
        calibrations: CalibrationService,
    ) -> None:
        self.services = services
        self.captures = captures
        self.calibrations = calibrations

    async def capture_current_debug(
        self,
        settings: SystemSettings,
        camera_id: str,
    ) -> MeasurementResponse:
        runtime = await self.calibrations.ensure_camera_calibration(
            settings,
            camera_id,
        )
        return await self.measure_camera(
            settings,
            runtime,
            camera_id,
            generate_artifacts=True,
            generate_debug_stages=True,
            persistent=True,
        )

    async def measure_cycle(
        self,
        settings: SystemSettings,
        runtime: RuntimeState,
        *,
        generate_artifacts: bool,
        persistent: bool,
    ) -> MeasurementResponse:
        outcomes = await self.measure_camera_jobs(
            settings,
            runtime,
            generate_artifacts=generate_artifacts,
            persistent=persistent,
        )
        failures = [outcome for outcome in outcomes if outcome.error is not None]
        if failures:
            raise RuntimeError(format_camera_errors(failures))
        return combine_measurements([
            outcome.result for outcome in outcomes if outcome.result is not None
        ])

    async def measure_camera_jobs(
        self,
        settings: SystemSettings,
        runtime: RuntimeState,
        *,
        generate_artifacts: bool,
        persistent: bool,
        run_measurement: Callable[..., Awaitable[MeasurementResponse]] | None = None,
    ) -> list[CameraMeasurementOutcome]:
        camera_ids = active_camera_ids(settings)
        if not camera_ids:
            raise ValueError("測定対象カメラがありません")
        semaphore = asyncio.Semaphore(settings.measurement_concurrency)
        measure = run_measurement or self.measure_camera

        async def run(camera_id: str) -> CameraMeasurementOutcome:
            async with semaphore:
                started_at = datetime.now(UTC)
                try:
                    result = await measure(
                        settings,
                        runtime,
                        camera_id,
                        generate_artifacts=generate_artifacts,
                        persistent=persistent,
                    )
                except Exception as exc:
                    return CameraMeasurementOutcome(
                        camera_id=camera_id,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error=exc,
                    )
                return CameraMeasurementOutcome(
                    camera_id=camera_id,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    result=result,
                )

        return await asyncio.gather(*(run(camera_id) for camera_id in camera_ids))

    async def measure_camera(
        self,
        settings: SystemSettings,
        runtime: RuntimeState,
        camera_id: str,
        *,
        generate_artifacts: bool,
        persistent: bool,
        generate_debug_stages: bool = False,
    ) -> MeasurementResponse:
        if camera_id not in active_camera_ids(settings):
            raise HTTPException(
                status_code=409,
                detail=f"{camera_id}に有効なパレットがありません",
            )
        startup_error = self.calibrations.camera_startup_errors.get(camera_id)
        if startup_error is not None:
            raise HTTPException(
                status_code=409,
                detail=f"{camera_id}を測定できません: {startup_error}",
            )
        calibration_id = runtime.camera(camera_id).calibration_id
        if calibration_id is None:
            raise HTTPException(
                status_code=409,
                detail=f"{camera_id}の校正IDがありません",
            )
        calibration = await self.calibrations.calibration_definition(calibration_id)
        runtime_id = self.calibrations.measurement_runtime_ids.get(camera_id)
        if runtime_id is None:
            runtime_id = await self.calibrations.prepare_measurement_runtime(
                settings,
                calibration,
            )
        current = await self.captures.capture(
            settings,
            camera_id,
            purpose="current",
            persistent=persistent,
            frame_count=settings.measurement_frame_count,
        )
        request = self.measurement_request(
            settings,
            runtime_id,
            camera_id,
            current,
            generate_artifacts=generate_artifacts,
            generate_debug_stages=generate_debug_stages,
        )
        try:
            return await self.services.measure(request)
        except HTTPException as exc:
            if "測定ランタイムが見つかりません" not in str(exc.detail):
                raise
            runtime_id = await self.calibrations.prepare_measurement_runtime(
                settings,
                calibration,
            )
            return await self.services.measure(
                request.model_copy(update={"runtime_id": runtime_id})
            )

    @staticmethod
    def measurement_request(
        settings: SystemSettings,
        runtime_id: str,
        camera_id: str,
        current_capture: CaptureManifest,
        *,
        generate_artifacts: bool,
        generate_debug_stages: bool = False,
    ) -> MeasurementRequest:
        return MeasurementRequest(
            camera_id=camera_id,
            runtime_id=runtime_id,
            current_capture_id=current_capture.capture_id,
            current_capture=current_capture,
            occupied_height_mm=settings.occupied_height_mm,
            generate_artifacts=generate_artifacts,
            generate_debug_stages=generate_debug_stages,
        )


def combine_measurements(results: list[MeasurementResponse]) -> MeasurementResponse:
    if not results:
        raise ValueError("測定対象カメラがありません")
    if len(results) == 1:
        return results[0]
    return MeasurementResponse(
        measurement_id=(
            datetime.now(UTC).strftime("%Y%m%d_%H%M%S_multi_")
            + uuid.uuid4().hex[:8]
        ),
        camera_runs=[run for result in results for run in result.camera_runs],
        pallets=[pallet for result in results for pallet in result.pallets],
    )


@dataclass(frozen=True)
class CameraMeasurementOutcome:
    camera_id: str
    started_at: datetime
    finished_at: datetime
    result: MeasurementResponse | None = None
    error: Exception | None = None


def format_camera_errors(outcomes: list[CameraMeasurementOutcome]) -> str:
    return "; ".join(
        f"{outcome.camera_id}: {monitor_error_text(outcome.error)}"
        for outcome in outcomes
        if outcome.error is not None
    )


def monitor_error_text(exc: Exception | None) -> str:
    if exc is None:
        return "不明なエラー"
    return str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
