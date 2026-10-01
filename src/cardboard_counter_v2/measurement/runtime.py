"""DB由来の平面校正定義から、測定中不変の形状を1回だけ作る。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock

import numpy as np

from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics
from cardboard_counter_v2.measurement.core.models import normalized_roi
from cardboard_counter_v2.measurement.core.pallet_geometry import (
    PalletProjectionGeometry,
    build_pallet_projection_geometry,
)
from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane


@dataclass(frozen=True)
class MeasurementRuntime:
    calibration: PlanarCalibrationDefinition
    intrinsics: RgbdIntrinsics
    geometries: dict[int, PalletProjectionGeometry]
    plans: OrderedDict[tuple[object, ...], object] = field(
        default_factory=OrderedDict,
        compare=False,
    )
    plan_lock: Lock = field(default_factory=Lock, compare=False)


class MeasurementRuntimeCache:
    def __init__(self, *, capacity: int = 4) -> None:
        self._capacity = max(int(capacity), 1)
        self._items: OrderedDict[
            tuple[str, str, tuple[int, int], tuple[int, int]],
            MeasurementRuntime,
        ] = OrderedDict()
        self._lock = Lock()

    def get(
        self,
        calibration: PlanarCalibrationDefinition,
        *,
        color_shape: tuple[int, int],
        depth_shape: tuple[int, int],
    ) -> MeasurementRuntime:
        key = (
            calibration.calibration_id,
            calibration.model_dump_json(),
            color_shape,
            depth_shape,
        )
        with self._lock:
            cached = self._items.get(key)
            if cached is not None:
                self._items.move_to_end(key)
                return cached

            intrinsics = calibration.projection.to_rgbd_intrinsics()
            geometries: dict[int, PalletProjectionGeometry] = {}
            for region in calibration.regions:
                floor_plane = PalletPlane(
                    normal=np.asarray(
                        region.reference_plane_normal, dtype=np.float32
                    ),
                    offset=region.reference_plane_offset,
                    fit_rmse_mm=0.0,
                    inlier_count=0,
                )
                geometries[region.region_id] = build_pallet_projection_geometry(
                    normalized_roi(region.roi, color_shape),
                    color_shape=color_shape,
                    depth_shape=depth_shape,
                    camera_intrinsics=intrinsics,
                    reference_plane=floor_plane,
                    surface_offset_mm=region.surface_offset_mm,
                    cell_size_mm=region.cell_size_mm,
                )

            runtime = MeasurementRuntime(
                calibration=calibration,
                intrinsics=intrinsics,
                geometries=geometries,
            )
            self._items[key] = runtime
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
            return runtime

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


# 30台構成でも監視開始前に準備したランタイムを全台分保持する。
runtime_cache = MeasurementRuntimeCache(capacity=64)
