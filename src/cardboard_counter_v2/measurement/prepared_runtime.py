"""監視開始前に構築し、測定ごとにIDで再利用する実行計画。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from threading import Lock

from cardboard_counter_v2.common.box_catalog import BoxClassSpec
from cardboard_counter_v2.common.planar_calibration import PlanarCalibrationDefinition
from cardboard_counter_v2.common.schemas import PalletSettings
from cardboard_counter_v2.measurement.planning import (
    MeasurementPlan,
    get_measurement_plan,
)
from cardboard_counter_v2.measurement.runtime import MeasurementRuntime, runtime_cache


@dataclass(frozen=True)
class PreparedMeasurementRuntime:
    runtime_id: str
    runtime: MeasurementRuntime
    plan: MeasurementPlan


class PreparedMeasurementRuntimeRegistry:
    """校正・ROI・箱設定から作った不変計画を、短いIDで保持する。"""

    def __init__(self, *, capacity: int = 64) -> None:
        self._capacity = max(int(capacity), 1)
        self._items: OrderedDict[str, PreparedMeasurementRuntime] = OrderedDict()
        self._lock = Lock()

    def prepare(
        self,
        calibration: PlanarCalibrationDefinition,
        pallets: list[PalletSettings],
        box_catalog: list[BoxClassSpec],
        *,
        color_shape: tuple[int, int],
        depth_shape: tuple[int, int],
    ) -> PreparedMeasurementRuntime:
        payload = "|".join((
            calibration.model_dump_json(),
            "[" + ",".join(item.model_dump_json() for item in pallets) + "]",
            "[" + ",".join(item.model_dump_json() for item in box_catalog) + "]",
            repr(color_shape),
            repr(depth_shape),
        ))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        runtime_id = f"{calibration.calibration_id}_{digest}"
        with self._lock:
            cached = self._items.get(runtime_id)
            if cached is not None:
                self._items.move_to_end(runtime_id)
                return cached

        runtime = runtime_cache.get(
            calibration,
            color_shape=color_shape,
            depth_shape=depth_shape,
        )
        plan = get_measurement_plan(
            runtime,
            pallets,
            box_catalog,
            color_shape=color_shape,
            depth_shape=depth_shape,
        )
        prepared = PreparedMeasurementRuntime(
            runtime_id=runtime_id,
            runtime=runtime,
            plan=plan,
        )
        with self._lock:
            self._items[runtime_id] = prepared
            self._items.move_to_end(runtime_id)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
        return prepared

    def get(self, runtime_id: str) -> PreparedMeasurementRuntime:
        with self._lock:
            prepared = self._items.get(runtime_id)
            if prepared is None:
                raise ValueError(
                    f"測定ランタイムが見つかりません。再準備してください: {runtime_id}"
                )
            self._items.move_to_end(runtime_id)
            return prepared

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


prepared_runtime_registry = PreparedMeasurementRuntimeRegistry()
