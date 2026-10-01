"""アプリケーション層が外部HTTP実装へ依存しないための境界。"""

from __future__ import annotations

from typing import Protocol

from cardboard_counter_v2.common.box_catalog import BoxClassSpec
from cardboard_counter_v2.common.camera_contracts import (
    FrameBatchManifest,
    FrameBatchRequest,
)
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition
from cardboard_counter_v2.common.schemas import (
    CalibrationRequest,
    CalibrationResult,
    CaptureManifest,
    MeasurementRequest,
    MeasurementResponse,
    PalletSettings,
    PrepareCaptureRequest,
)


class CameraCaptureGateway(Protocol):
    async def create_frame_batch(
        self,
        camera_id: str,
        request: FrameBatchRequest,
    ) -> FrameBatchManifest: ...

    async def delete_frame_batch(self, camera_id: str, batch_id: str) -> None: ...


class CaptureArtifactGateway(Protocol):
    async def prepare_capture(
        self,
        request: PrepareCaptureRequest,
    ) -> CaptureManifest: ...

    async def delete_capture(self, capture: CaptureManifest) -> None: ...


class CaptureWorkflowGateway(
    CameraCaptureGateway,
    CaptureArtifactGateway,
    Protocol,
):
    """FrameBatchから永続Captureを作る処理に必要な契約。"""


class CalibrationGateway(Protocol):
    async def calibrate(self, request: CalibrationRequest) -> CalibrationResult: ...

    async def prepare_measurement_runtime(
        self,
        calibration: PlanarCalibrationDefinition,
        pallets: list[PalletSettings],
        box_catalog: list[BoxClassSpec],
    ) -> str: ...


class MeasurementExecutionGateway(Protocol):
    async def measure(self, request: MeasurementRequest) -> MeasurementResponse: ...


class WorkflowServices(
    CaptureWorkflowGateway,
    CalibrationGateway,
    MeasurementExecutionGateway,
    Protocol,
):
    """撮影から測定までのワークフローが必要とする最小契約。"""
