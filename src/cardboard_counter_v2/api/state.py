"""設定と分離した、DBから再生成できるプロセス内実行状態。"""

from __future__ import annotations

from threading import Lock

from typing import Any

from pydantic import BaseModel, Field, model_validator

class CameraRuntimeState(BaseModel):
    baseline_capture_id: str | None = None
    calibration_id: str | None = None


class RuntimeState(BaseModel):
    cameras: dict[str, CameraRuntimeState] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def migrate_single_camera_state(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "cameras" in value:
            return value
        baseline = value.get("baseline_capture_id")
        calibration = value.get("calibration_id")
        if baseline is None and calibration is None:
            return value
        return {"cameras": {"camera_1": {
            "baseline_capture_id": baseline,
            "calibration_id": calibration,
        }}}

    def camera(self, camera_id: str) -> CameraRuntimeState:
        return self.cameras.get(camera_id, CameraRuntimeState())


class RuntimeStateStore:
    """未校正の床撮影選択だけを一時保持し、有効校正はDBから復元する。"""

    def __init__(self) -> None:
        self.lock = Lock()
        self._state = RuntimeState()

    def load(self) -> RuntimeState:
        with self.lock:
            return self._state.model_copy(deep=True)

    def save(self, state: RuntimeState) -> RuntimeState:
        with self.lock:
            self._state = state.model_copy(deep=True)
            return self._state.model_copy(deep=True)

    def restore_calibrations(
        self, calibrations: dict[str, tuple[str, str]]
    ) -> RuntimeState:
        """camera_id→(床撮影ID, 校正ID)をDBから復元する。"""
        return self.save(RuntimeState(cameras={
            camera_id: CameraRuntimeState(
                baseline_capture_id=capture_id,
                calibration_id=calibration_id,
            )
            for camera_id, (capture_id, calibration_id) in calibrations.items()
        }))

    def clear(self, *, keep_baseline: bool = False, camera_ids: set[str] | None = None) -> RuntimeState:
        current = self.load()
        targets = camera_ids or set(current.cameras)
        cameras = dict(current.cameras)
        for camera_id in targets:
            previous = current.camera(camera_id)
            cameras[camera_id] = CameraRuntimeState(
                baseline_capture_id=previous.baseline_capture_id if keep_baseline else None,
                calibration_id=None,
            )
        return self.save(RuntimeState(cameras=cameras))
