"""ベンダーに依存しないActive IR・Depthフレーム取得契約。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol, Self

import numpy as np

from cardboard_counter_v2.common.camera_contracts import CameraDeviceSettings
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics


class IrDepthFrame(Protocol):
    ir_gray: np.ndarray
    depth_mm: np.ndarray
    camera_intrinsics: RgbdIntrinsics | None


class IrDepthFrameSource(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def frames(self) -> Iterator[IrDepthFrame]: ...


FrameSourceFactory = Callable[[CameraDeviceSettings], IrDepthFrameSource]


class FrameSourceRegistry:
    """設定のdriver名からベンダー別ソースを選ぶ。"""

    def __init__(self) -> None:
        self._factories: dict[str, FrameSourceFactory] = {}

    def register(self, driver: str, factory: FrameSourceFactory) -> None:
        key = driver.strip().casefold()
        if not key:
            raise ValueError("driver名が空です")
        self._factories[key] = factory

    def create(self, camera: CameraDeviceSettings) -> IrDepthFrameSource:
        factory = self._factories.get(camera.driver.strip().casefold())
        if factory is None:
            available = ", ".join(sorted(self._factories)) or "none"
            raise ValueError(
                f"未対応のカメラdriverです: {camera.driver} (available: {available})"
            )
        return factory(camera)
