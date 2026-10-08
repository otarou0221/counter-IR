"""校正・設定が変わるまで再利用する測定実行計画。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from cardboard_counter_v2.common.box_catalog import BoxClassSpec, catalog_by_label
from cardboard_counter_v2.common.schemas import PalletSettings
from cardboard_counter_v2.common.depth_projection import (
    pointcloud_intrinsics_for_depth_shape,
    scaled_intrinsics,
)
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.core.high_surface_filter import HighSurfaceFilter
from cardboard_counter_v2.measurement.runtime import MeasurementRuntime
from cardboard_counter_v2.measurement.optimization.volume_fitting import (
    PreparedVolumeRuleOptimizer,
    VolumeItem,
)


@dataclass(frozen=True)
class PalletMeasurementPlan:
    """監視ループ中で変わらない、1パレット分の計算済み値。"""

    settings: PalletSettings
    geometry: PalletProjectionGeometry
    reference_box: BoxClassSpec
    high_surface_filter: HighSurfaceFilter
    box_optimizer: PreparedVolumeRuleOptimizer


@dataclass(frozen=True)
class MeasurementPlan:
    calibration_id: str
    color_shape: tuple[int, int]
    depth_shape: tuple[int, int]
    pallets: tuple[PalletMeasurementPlan, ...]
    normal_bounds: tuple[int, int, int, int]


def _settings_key(
    settings: list[PalletSettings],
    box_catalog: list[BoxClassSpec],
) -> tuple[object, ...]:
    pallets = tuple(
        (
            item.pallet_id,
            item.enabled,
            tuple(item.plane_roi),
            tuple(item.single_box_labels),
            tuple(tuple(group) for group in item.mixed_box_groups),
            item.reference_box_label,
        )
        for item in settings
    )
    catalog = tuple(
        (box.label, box.width_mm, box.depth_mm, box.height_mm)
        for box in box_catalog
    )
    return pallets, catalog


def get_measurement_plan(
    runtime: MeasurementRuntime,
    settings: list[PalletSettings],
    box_catalog: list[BoxClassSpec],
    *,
    color_shape: tuple[int, int],
    depth_shape: tuple[int, int],
) -> MeasurementPlan:
    """ROI変換・箱定数・法線計算範囲を校正ランタイム内で再利用する。"""
    key = (color_shape, depth_shape, _settings_key(settings, box_catalog))
    with runtime.plan_lock:
        cached = runtime.plans.get(key)
        if cached is not None:
            runtime.plans.move_to_end(key)
            return cast(MeasurementPlan, cached)

        calibrated = {
            item.region_id: item for item in runtime.calibration.regions
        }
        catalog = catalog_by_label(box_catalog)
        plans: list[PalletMeasurementPlan] = []
        for item in settings:
            if not item.enabled:
                continue
            saved = calibrated.get(item.pallet_number)
            if saved is None:
                raise ValueError(f"パレット{item.pallet_number}の校正データがありません")
            if tuple(item.plane_roi) != tuple(saved.roi):
                raise ValueError(f"パレット{item.pallet_id}の平面ROIが校正後に変更されています")
            geometry = runtime.geometries[item.pallet_number]
            selected_labels = item.box_rule_labels
            selected_boxes = [
                catalog[label.casefold()]
                for label in selected_labels
                if label.casefold() in catalog
            ]
            if len(selected_boxes) != len(selected_labels):
                raise ValueError(f"パレット{item.pallet_id}の箱クラスがカタログにありません")
            reference_box = catalog.get(item.reference_box_label.casefold())
            if reference_box is None or all(
                reference_box.label.casefold() != box.label.casefold()
                for box in selected_boxes
            ):
                raise ValueError(f"パレット{item.pallet_id}の基準箱が対象クラスにありません")
            plans.append(
                PalletMeasurementPlan(
                    settings=item.model_copy(deep=True),
                    geometry=geometry,
                    reference_box=reference_box,
                    high_surface_filter=HighSurfaceFilter.for_box_footprints(
                        (box.width_mm, box.depth_mm) for box in selected_boxes
                    ),
                    box_optimizer=PreparedVolumeRuleOptimizer(
                        single_items=[
                            VolumeItem(
                                catalog[label.casefold()].label,
                                catalog[label.casefold()].volume_mm3,
                            )
                            for label in item.single_box_labels
                        ],
                        mixed_item_groups=[
                            [
                                VolumeItem(
                                    catalog[label.casefold()].label,
                                    catalog[label.casefold()].volume_mm3,
                                )
                                for label in group
                            ]
                            for group in item.mixed_box_groups
                        ],
                    ),
                )
            )
        if not plans:
            raise ValueError("有効なパレットがありません")
        normal_bounds = _surface_normal_bounds(
            runtime,
            plans,
            depth_shape=depth_shape,
        )
        plan = MeasurementPlan(
            calibration_id=runtime.calibration.calibration_id,
            color_shape=color_shape,
            depth_shape=depth_shape,
            pallets=tuple(plans),
            normal_bounds=normal_bounds,
        )
        runtime.plans[key] = plan
        while len(runtime.plans) > 4:
            runtime.plans.popitem(last=False)
        return plan


def _surface_normal_bounds(
    runtime: MeasurementRuntime,
    plans: list[PalletMeasurementPlan],
    *,
    depth_shape: tuple[int, int],
) -> tuple[int, int, int, int]:
    """固定ROIと床法線の消失点から、積載物が写り得る保守的範囲を作る。"""
    height, width = depth_shape
    stream = pointcloud_intrinsics_for_depth_shape(runtime.intrinsics, depth_shape)
    fx, fy, cx, cy = scaled_intrinsics(stream, depth_shape)
    calibrated = {
        item.region_id: item for item in runtime.calibration.regions
    }
    xs: list[float] = []
    ys: list[float] = []
    for plan in plans:
        region = calibrated[plan.settings.pallet_number]
        left, top, right, bottom = region.roi
        nx, ny, nz = region.reference_plane_normal
        if abs(nz) < 1e-6:
            return (0, height, 0, width)
        vanishing_x = cx + fx * nx / nz
        vanishing_y = cy + fy * ny / nz
        left_px, right_px = left * width, right * width
        top_px, bottom_px = top * height, bottom * height
        # 平面法線方向へ高くなる物体は、画像上では消失点から外側へ伸びる。
        # 高さ上限を持たないため、その方向の画像端まで含めて欠落を防ぐ。
        if vanishing_x < left_px:
            xs.extend((left_px, float(width)))
        elif vanishing_x > right_px:
            xs.extend((0.0, right_px))
        else:
            xs.extend((0.0, float(width)))
        if vanishing_y < top_px:
            ys.extend((top_px, float(height)))
        elif vanishing_y > bottom_px:
            ys.extend((0.0, bottom_px))
        else:
            ys.extend((0.0, float(height)))
    padding = 2
    x1 = max(int(min(xs)) - padding, 0)
    y1 = max(int(min(ys)) - padding, 0)
    x2 = min(int(max(xs)) + padding + 1, width)
    y2 = min(int(max(ys)) + padding + 1, height)
    if x2 - x1 < 3 or y2 - y1 < 3:
        return (0, height, 0, width)
    return (y1, y2, x1, x2)
