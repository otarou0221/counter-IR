"""既存APIを保ちながら、分割済みワークフローサービスを束ねる。"""

from __future__ import annotations

from typing import Literal

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.ports import WorkflowServices
from cardboard_counter_v2.api.state import RuntimeState, RuntimeStateStore
from cardboard_counter_v2.api.workflow import (
    CalibrationService,
    CameraMeasurementOutcome,
    CaptureRetentionService,
    CaptureService,
    MeasurementJobRunner,
    combine_measurements,
    format_camera_errors,
    monitor_error_text,
)
from cardboard_counter_v2.api.workflow.selectors import (
    active_camera_ids,
    pallets_for_camera,
)
from cardboard_counter_v2.common.schemas import (
    CaptureManifest,
    MeasurementRequest,
    MeasurementResponse,
    PalletSettings,
    SystemSettings,
)


class MeasurementWorkflow:
    """ルーター互換の薄いファサード。実処理は責務別サービスへ委譲する。"""

    def __init__(
        self,
        services: WorkflowServices,
        state_store: RuntimeStateStore,
        history: InventoryHistoryService | None = None,
    ) -> None:
        self.services = services
        self.state_store = state_store
        self.history = history
        self.retention = CaptureRetentionService(services, history)
        self.captures = CaptureService(services, self.retention, history)
        self.calibrations = CalibrationService(services, state_store, history)
        self.jobs = MeasurementJobRunner(
            services,
            self.captures,
            self.calibrations,
        )

        # 移行期間中のテスト・保守コード向け互換参照。
        self._calibration_definitions = self.calibrations.definitions
        self._camera_startup_errors = self.calibrations.camera_startup_errors
        self._measurement_runtime_ids = self.calibrations.measurement_runtime_ids

    @staticmethod
    def active_camera_ids(settings: SystemSettings) -> list[str]:
        return active_camera_ids(settings)

    @staticmethod
    def pallets_for_camera(
        settings: SystemSettings,
        camera_id: str,
    ) -> list[PalletSettings]:
        return pallets_for_camera(settings, camera_id)

    async def capture(
        self,
        settings: SystemSettings,
        camera_id: str,
        *,
        purpose: Literal["floor", "current"],
        persistent: bool = True,
        frame_count: int | None = None,
    ) -> CaptureManifest:
        return await self.captures.capture(
            settings,
            camera_id,
            purpose=purpose,
            persistent=persistent,
            frame_count=frame_count,
        )

    async def capture_floor_reference(
        self,
        settings: SystemSettings,
        camera_id: str,
    ) -> CaptureManifest:
        return await self.captures.capture_floor_reference(settings, camera_id)

    async def delete_capture(self, capture_id: str) -> None:
        await self.retention.delete_capture(capture_id)

    async def ensure_calibrations(self, settings: SystemSettings) -> RuntimeState:
        return await self.calibrations.ensure_calibrations(settings)

    async def ensure_camera_calibration(
        self,
        settings: SystemSettings,
        camera_id: str,
    ) -> RuntimeState:
        return await self.calibrations.ensure_camera_calibration(settings, camera_id)

    async def capture_current_debug(
        self,
        settings: SystemSettings,
        camera_id: str,
    ) -> MeasurementResponse:
        return await self.jobs.capture_current_debug(settings, camera_id)

    async def measure_cycle(
        self,
        settings: SystemSettings,
        runtime: RuntimeState,
        *,
        generate_artifacts: bool,
        persistent: bool,
    ) -> MeasurementResponse:
        return await self.jobs.measure_cycle(
            settings,
            runtime,
            generate_artifacts=generate_artifacts,
            persistent=persistent,
        )

    async def measure_camera_jobs(
        self,
        settings: SystemSettings,
        runtime: RuntimeState,
        *,
        generate_artifacts: bool,
        persistent: bool,
    ) -> list[CameraMeasurementOutcome]:
        return await self.jobs.measure_camera_jobs(
            settings,
            runtime,
            generate_artifacts=generate_artifacts,
            persistent=persistent,
            run_measurement=self.measure_camera,
        )

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
        return await self.jobs.measure_camera(
            settings,
            runtime,
            camera_id,
            generate_artifacts=generate_artifacts,
            persistent=persistent,
            generate_debug_stages=generate_debug_stages,
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
        return MeasurementJobRunner.measurement_request(
            settings,
            runtime_id,
            camera_id,
            current_capture,
            generate_artifacts=generate_artifacts,
            generate_debug_stages=generate_debug_stages,
        )


__all__ = [
    "CameraMeasurementOutcome",
    "MeasurementWorkflow",
    "combine_measurements",
    "format_camera_errors",
    "monitor_error_text",
]
