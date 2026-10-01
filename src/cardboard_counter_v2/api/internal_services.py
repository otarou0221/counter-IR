"""cameraとmeasurementの内部HTTP APIを型付き操作に隠蔽する。"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import time
from urllib.parse import urlencode

from fastapi import HTTPException
import httpx

from cardboard_counter_v2.api.service_client import ServiceClient
from cardboard_counter_v2.common.box_catalog import BoxClassSpec
from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    CameraFleetConfiguration,
    CameraFleetStatus,
    CameraStreamStatus,
    FrameBatchManifest,
    FrameBatchRequest,
)
from cardboard_counter_v2.common.schemas import (
    CalibrationResult,
    CalibrationRequest,
    CaptureManifest,
    MeasurementRequest,
    MeasurementResponse,
    PrepareMeasurementRuntimeRequest,
    PrepareCaptureRequest,
    CameraSettings,
    PalletSettings,
)
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition


class InternalServices:
    """サービスURLとHTTP契約の変換を一箇所で管理する。"""

    def __init__(
        self,
        client: ServiceClient,
        *,
        camera_url: str,
        measurement_url: str,
        camera_status_ttl_seconds: float = 5.0,
    ) -> None:
        self.client = client
        self.default_camera_url = camera_url.rstrip("/")
        self.measurement_url = measurement_url.rstrip("/")
        self._camera_urls: dict[str, str] = {}
        self._camera_settings: OrderedDict[str, CameraSettings] = OrderedDict()
        self._configured_urls: set[str] = set()
        self._camera_status_ttl_seconds = max(float(camera_status_ttl_seconds), 0.0)
        self._camera_status_cache: list[CameraStreamStatus] | None = None
        self._camera_status_cached_at = 0.0
        self._camera_status_lock = asyncio.Lock()

    async def camera_statuses(self) -> list[CameraStreamStatus]:
        now = time.monotonic()
        if (
            self._camera_status_cache is not None
            and now - self._camera_status_cached_at < self._camera_status_ttl_seconds
        ):
            return [item.model_copy(deep=True) for item in self._camera_status_cache]
        async with self._camera_status_lock:
            now = time.monotonic()
            if (
                self._camera_status_cache is not None
                and now - self._camera_status_cached_at < self._camera_status_ttl_seconds
            ):
                return [item.model_copy(deep=True) for item in self._camera_status_cache]
            statuses = await self._fetch_camera_statuses()
            self._camera_status_cache = [item.model_copy(deep=True) for item in statuses]
            self._camera_status_cached_at = time.monotonic()
            return statuses

    async def _fetch_camera_statuses(self) -> list[CameraStreamStatus]:
        if not self._camera_settings:
            payload = await self.client.get_json(
                f"{self.default_camera_url}/v1/cameras"
            )
            return CameraFleetStatus.model_validate(payload).cameras

        grouped = self._group_cameras(list(self._camera_settings.values()))

        async def fetch(url: str) -> tuple[dict[str, CameraStreamStatus], str | None]:
            try:
                payload = await self.client.get_json(f"{url}/v1/cameras")
                statuses = CameraFleetStatus.model_validate(payload).cameras
                by_camera = {
                    status.camera.camera_id: status
                    for status in statuses
                    if status.camera is not None
                }
                expected = grouped[url]
                if any(camera.camera_id not in by_camera for camera in expected):
                    configured = await self._configure_camera_url(url, expected)
                    by_camera = {
                        status.camera.camera_id: status
                        for status in configured
                        if status.camera is not None
                    }
                return by_camera, None
            except Exception as exc:
                return {}, error_text(exc)

        fetched = await asyncio.gather(*(fetch(url) for url in grouped))
        by_url = dict(zip(grouped, fetched, strict=True))
        result: list[CameraStreamStatus] = []
        for camera_id, camera in self._camera_settings.items():
            url = self._camera_urls[camera_id]
            statuses, error = by_url[url]
            result.append(
                statuses.get(camera_id)
                or CameraStreamStatus(
                    camera=CameraDeviceSettings.model_validate(camera.model_dump()),
                    error=error or f"{url}からカメラ状態が返されませんでした",
                )
            )
        return result

    async def _configure_camera_url(
        self,
        url: str,
        cameras: list[CameraSettings],
    ) -> list[CameraStreamStatus]:
        devices = [
            CameraDeviceSettings.model_validate(camera.model_dump())
            for camera in cameras
        ]
        payload = await self.client.put_json(
            f"{url}/v1/cameras",
            CameraFleetConfiguration(cameras=devices).model_dump(mode="json"),
        )
        return CameraFleetStatus.model_validate(payload).cameras

    async def camera_status(self, camera_id: str) -> CameraStreamStatus:
        payload = await self.client.get_json(
            f"{self.camera_url(camera_id)}/v1/cameras/{camera_id}/status"
        )
        return CameraStreamStatus.model_validate(payload)

    async def configure_cameras(self, cameras: list[CameraSettings]) -> list[CameraStreamStatus]:
        grouped = self._group_cameras(cameras)
        target_urls = list(grouped)
        target_urls.extend(sorted(self._configured_urls - set(grouped)))

        async def configure(
            url: str,
        ) -> tuple[list[CameraStreamStatus], str | None]:
            try:
                return await self._configure_camera_url(
                    url,
                    grouped.get(url, []),
                ), None
            except Exception as exc:
                return [], error_text(exc)

        responses = await asyncio.gather(*(configure(url) for url in target_urls))
        statuses = {
            status.camera.camera_id: status
            for response, _error in responses
            for status in response
            if status.camera is not None
        }
        errors_by_url = {
            url: error
            for url, (_response, error) in zip(target_urls, responses, strict=True)
            if error is not None
        }
        self._camera_settings = OrderedDict(
            (camera.camera_id, camera.model_copy(deep=True)) for camera in cameras
        )
        self._camera_urls = {
            camera.camera_id: camera.camera_service_url.rstrip("/")
            for camera in cameras
        }
        self._configured_urls = set(grouped)
        self._camera_status_cache = None
        self._camera_status_cached_at = 0.0
        return [
            statuses.get(camera.camera_id)
            or CameraStreamStatus(
                camera=CameraDeviceSettings.model_validate(camera.model_dump()),
                error=(
                    errors_by_url.get(camera.camera_service_url.rstrip("/"))
                    or f"{camera.camera_service_url}からカメラ状態が返されませんでした"
                ),
            )
            for camera in cameras
        ]

    async def create_frame_batch(
        self, camera_id: str, request: FrameBatchRequest
    ) -> FrameBatchManifest:
        payload = await self.client.post_json(
            f"{self.camera_url(camera_id)}/v1/cameras/{camera_id}/frame-batches",
            request.model_dump(),
        )
        return FrameBatchManifest.model_validate(payload)

    async def delete_frame_batch(self, camera_id: str, batch_id: str) -> None:
        await self.client.delete_json(
            f"{self.camera_url(camera_id)}/v1/frame-batches/{batch_id}"
        )

    async def open_camera_stream(self, camera_id: str) -> httpx.Response:
        return await self.client.open_stream(
            f"{self.camera_url(camera_id)}/v1/cameras/{camera_id}/stream.mjpg"
        )

    def camera_url(self, camera_id: str) -> str:
        return self._camera_urls.get(camera_id, self.default_camera_url)

    @staticmethod
    def _group_cameras(
        cameras: list[CameraSettings],
    ) -> OrderedDict[str, list[CameraSettings]]:
        grouped: OrderedDict[str, list[CameraSettings]] = OrderedDict()
        for camera in cameras:
            grouped.setdefault(camera.camera_service_url.rstrip("/"), []).append(camera)
        return grouped

    async def prepare_capture(self, request: PrepareCaptureRequest) -> CaptureManifest:
        payload = await self.client.post_json(
            f"{self.measurement_url}/v1/captures",
            request.model_dump(exclude_none=True),
        )
        return CaptureManifest.model_validate(payload)

    async def delete_capture(self, capture: CaptureManifest) -> None:
        query = urlencode({
            "camera_id": capture.camera_id,
            "purpose": capture.purpose,
            "storage_version": capture.storage_version,
        })
        await self.client.delete_json(
            f"{self.measurement_url}/v1/captures/{capture.capture_id}?{query}"
        )

    async def calibrate(self, request: CalibrationRequest) -> CalibrationResult:
        payload = await self.client.post_json(
            f"{self.measurement_url}/v1/calibrations",
            request.model_dump(),
        )
        return CalibrationResult.model_validate(payload)

    async def measure(self, request: MeasurementRequest) -> MeasurementResponse:
        payload = await self.client.post_json(
            f"{self.measurement_url}/v1/measurements",
            request.model_dump(),
        )
        return MeasurementResponse.model_validate(payload)

    async def prepare_measurement_runtime(
        self,
        calibration: PlanarCalibrationDefinition,
        pallets: list[PalletSettings],
        box_catalog: list[BoxClassSpec],
    ) -> str:
        shape = (
            calibration.projection.height,
            calibration.projection.width,
        )
        payload = await self.client.post_json(
            f"{self.measurement_url}/v1/measurement-runtimes",
            PrepareMeasurementRuntimeRequest(
                calibration=calibration,
                pallets=pallets,
                box_catalog=box_catalog,
                color_shape=shape,
                depth_shape=shape,
            ).model_dump(mode="json"),
        )
        runtime_id = payload.get("runtime_id")
        if not isinstance(runtime_id, str) or not runtime_id:
            raise HTTPException(
                status_code=502,
                detail="測定サービスがruntime_idを返しませんでした",
            )
        return runtime_id


def error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)
