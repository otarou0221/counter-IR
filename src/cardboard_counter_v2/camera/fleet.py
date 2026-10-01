"""複数のIR・Depthカメラの長寿命ストリームをIDで管理する。"""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from cardboard_counter_v2.camera.source import FrameSourceFactory
from cardboard_counter_v2.camera.stream import CameraStreamHub
from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    CameraStreamStatus,
)


class CameraFleet:
    """設定変更時だけHubを生成し、測定ループでは既存Hubを再利用する。"""

    def __init__(
        self,
        *,
        source_factory: FrameSourceFactory,
        hub_factory: Callable[..., CameraStreamHub] = CameraStreamHub,
    ) -> None:
        self._source_factory = source_factory
        self._hub_factory = hub_factory
        self._hubs: dict[str, CameraStreamHub] = {}
        self._settings: dict[str, CameraDeviceSettings] = {}
        self._order: list[str] = []
        self._lock = RLock()

    def launch(self, cameras: list[CameraDeviceSettings]) -> list[CameraStreamStatus]:
        return self.configure(cameras)

    def configure(self, cameras: list[CameraDeviceSettings]) -> list[CameraStreamStatus]:
        requested = {camera.camera_id: camera.model_copy(deep=True) for camera in cameras}
        if len(requested) != len(cameras):
            raise ValueError("camera_idが重複しています")
        with self._lock:
            changed = {
                camera_id for camera_id, settings in requested.items()
                if self._settings.get(camera_id) != settings
            }
            removed = set(self._hubs) - set(requested)
            for camera_id in changed | removed:
                hub = self._hubs.get(camera_id)
                if hub is not None and hub.status().capture_active:
                    raise RuntimeError(f"{camera_id}は測定用フレーム取得中です")
            for camera_id in changed | removed:
                hub = self._hubs.pop(camera_id, None)
                if hub is not None:
                    hub.stop()
                self._settings.pop(camera_id, None)
            for camera_id in changed:
                settings = requested[camera_id]
                hub = self._hub_factory(source_factory=self._source_factory)
                hub.launch(settings)
                self._hubs[camera_id] = hub
                self._settings[camera_id] = settings
            self._order = [camera.camera_id for camera in cameras]
            return self.statuses()

    def get(self, camera_id: str) -> CameraStreamHub:
        with self._lock:
            hub = self._hubs.get(camera_id)
        if hub is None:
            raise KeyError(f"未登録のcamera_idです: {camera_id}")
        return hub

    def statuses(self) -> list[CameraStreamStatus]:
        with self._lock:
            return [self._hubs[camera_id].status() for camera_id in self._order]

    def stop(self) -> None:
        with self._lock:
            hubs = list(self._hubs.values())
            self._hubs.clear()
            self._settings.clear()
            self._order.clear()
        errors: list[Exception] = []
        for hub in hubs:
            try:
                hub.stop()
            except Exception as exc:  # 全カメラの停止を最後まで試みる
                errors.append(exc)
        if errors:
            raise RuntimeError(str(errors[0]))
