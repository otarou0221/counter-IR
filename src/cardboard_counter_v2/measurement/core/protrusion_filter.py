"""固定寸法の看板と基準箱に対して小さい突起・境界壁を除外する。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from cardboard_counter_v2.measurement.core.component_geometry import oriented_mask_spans


@lru_cache(maxsize=16)
def ellipse_kernel(size: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


@lru_cache(maxsize=16)
def expansion_kernel(radius: int) -> np.ndarray:
    size = radius * 2 + 1
    return np.ones((size, size), dtype=np.uint8)


@dataclass(frozen=True)
class HeightProtrusionFilterResult:
    """局所突起を下にある面まで戻した結果。"""

    height_grid: np.ndarray
    suppressed_mask: np.ndarray
    component_count: int
    suppressed_cells: int
    suppressed_volume_mm3: float


@dataclass(frozen=True)
class ProtrusionShapeRules:
    """小物を基準箱の寸法と比較するルール。"""

    minimum_area_ratio: float = 0.04
    maximum_area_ratio: float = 0.35
    small_object_max_span_ratio: float = 0.8


@dataclass(frozen=True)
class FixedSignRules:
    """基準箱の寸法に依存しない看板の実寸ルール。"""

    attached_min_area_mm2: float = 35_000.0
    attached_max_area_mm2: float = 60_000.0
    attached_max_short_span_mm: float = 180.0
    attached_max_long_span_mm: float = 500.0
    attached_min_aspect_ratio: float = 2.29
    attached_opening_mm: float = 300.0
    attached_prominence_mm: float = 60.0
    attached_weak_prominence_mm: float = 20.0
    isolated_sign_min_short_span_mm: float = 130.0
    isolated_sign_max_short_span_mm: float = 340.0
    isolated_sign_min_long_span_mm: float = 350.0
    isolated_sign_max_long_span_mm: float = 520.0
    isolated_sign_min_area_mm2: float = 35_000.0
    isolated_sign_max_area_mm2: float = 140_000.0
    isolated_sign_min_volume_mm3: float = 2_000_000.0
    isolated_sign_max_volume_mm3: float = 40_000_000.0
    isolated_sign_min_median_height_mm: float = 60.0
    isolated_sign_max_median_height_mm: float = 270.0
    isolated_sign_max_height_mm: float = 500.0


DEFAULT_SHAPE_RULES = ProtrusionShapeRules()
DEFAULT_SIGN_RULES = FixedSignRules()


def suppress_small_height_protrusions(
    height_grid: np.ndarray,
    region_mask: np.ndarray,
    *,
    cell_size_mm: float,
    box_width_mm: float,
    box_depth_mm: float,
    prominence_mm: float = 60.0,
    shape_rules: ProtrusionShapeRules = DEFAULT_SHAPE_RULES,
    sign_rules: FixedSignRules = DEFAULT_SIGN_RULES,
) -> HeightProtrusionFilterResult:
    """看板を固定実寸で、小物と境界壁を基準箱の寸法で除外する。"""
    heights = np.asarray(height_grid, dtype=np.float32)
    region = np.asarray(region_mask, dtype=bool)
    if heights.ndim != 2 or region.shape != heights.shape:
        raise ValueError("高さグリッドと領域マスクの形が一致しません。")
    corrected = heights.copy()
    suppressed = np.zeros(heights.shape, dtype=bool)
    cell = max(float(cell_size_mm), 2.0)
    box_width = max(float(box_width_mm), 0.0)
    box_depth = max(float(box_depth_mm), 0.0)
    active = region & np.isfinite(heights) & (heights > 0)
    if not np.any(active):
        return HeightProtrusionFilterResult(corrected, suppressed, 0, 0, 0.0)

    isolated_signs, isolated_sign_count = _isolated_fixed_signs(
        heights,
        active,
        cell_size_mm=cell,
        rules=sign_rules,
    )
    if np.any(isolated_signs):
        corrected[isolated_signs] = 0.0
        suppressed |= isolated_signs
    local_active = active & ~isolated_signs
    if not np.any(local_active):
        return _result(
            heights,
            corrected,
            suppressed,
            component_count=isolated_sign_count,
            cell_size_mm=cell,
        )

    source = np.where(local_active, heights, 0.0).astype(np.float32)
    # 補間は撮影ごとに1回だけ行い、固定看板と箱基準の除外で共有する。
    filled = cv2.inpaint(
        source,
        (~local_active).astype(np.uint8),
        max(int(round(50.0 / cell)), 1),
        cv2.INPAINT_TELEA,
    )
    sign_corrected, sign_mask, attached_sign_count = _suppress_attached_fixed_signs(
        heights, local_active, filled, cell_size_mm=cell, rules=sign_rules,
    )
    box_corrected, box_mask, box_component_count = _suppress_box_relative_protrusions(
        heights, local_active, filled,
        cell_size_mm=cell,
        box_width_mm=box_width,
        box_depth_mm=box_depth,
        prominence_mm=prominence_mm,
        rules=shape_rules,
    )
    corrected = np.minimum(corrected, np.minimum(sign_corrected, box_corrected))
    suppressed |= sign_mask | box_mask
    return _result(
        heights,
        corrected,
        suppressed,
        component_count=isolated_sign_count + attached_sign_count + box_component_count,
        cell_size_mm=cell,
    )


def _opening_kernel_size(
    diameter_mm: float,
    *,
    cell_size_mm: float,
    grid_shape: tuple[int, int],
) -> int:
    size = max(int(round(diameter_mm / cell_size_mm)), 3)
    if size % 2 == 0:
        size += 1
    maximum = min(grid_shape)
    if maximum % 2 == 0:
        maximum -= 1
    return min(size, maximum)


def _suppress_attached_fixed_signs(
    heights: np.ndarray,
    active: np.ndarray,
    filled: np.ndarray,
    *,
    cell_size_mm: float,
    rules: FixedSignRules,
) -> tuple[np.ndarray, np.ndarray, int]:
    """箱面に接した細長い看板を、固定実寸の形状と周囲高さで判定する。"""
    corrected = heights.copy()
    suppressed = np.zeros(heights.shape, dtype=bool)
    kernel_size = _opening_kernel_size(
        rules.attached_opening_mm,
        cell_size_mm=cell_size_mm,
        grid_shape=heights.shape,
    )
    if kernel_size < 3:
        return corrected, suppressed, 0
    base_surface = cv2.morphologyEx(
        filled, cv2.MORPH_OPEN, ellipse_kernel(kernel_size)
    )
    residual = heights - base_surface
    strong = active & (residual >= rules.attached_prominence_mm)
    if not np.any(strong):
        return corrected, suppressed, 0
    weak = active & (residual >= rules.attached_weak_prominence_mm)
    total, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        strong.astype(np.uint8), connectivity=8
    )
    expansion = expansion_kernel(max(int(math.ceil(30.0 / cell_size_mm)), 1))
    count = 0
    for label in range(1, total):
        component = labels == label
        area_mm2 = float(stats[label, cv2.CC_STAT_AREA]) * cell_size_mm**2
        if not (rules.attached_min_area_mm2 <= area_mm2 <= rules.attached_max_area_mm2):
            continue
        short_span_mm, long_span_mm = oriented_mask_spans(
            component, cell_size_mm=cell_size_mm
        )
        if not _is_fixed_attached_sign(short_span_mm, long_span_mm, rules=rules):
            continue
        expanded = cv2.dilate(component.astype(np.uint8), expansion).astype(bool)
        candidate = expanded & weak
        surrounding_level = _highest_supported_surrounding_level(
            heights, candidate, active, cell_size_mm=cell_size_mm
        )
        if surrounding_level is None:
            continue
        corrected[candidate] = np.minimum(
            corrected[candidate],
            np.maximum(base_surface[candidate], surrounding_level),
        )
        suppressed |= candidate
        count += 1
    return corrected, suppressed, count


def _is_fixed_attached_sign(
    short_span_mm: float,
    long_span_mm: float,
    *,
    rules: FixedSignRules,
) -> bool:
    return (
        short_span_mm > 0
        and short_span_mm <= rules.attached_max_short_span_mm
        and long_span_mm <= rules.attached_max_long_span_mm
        and long_span_mm / short_span_mm >= rules.attached_min_aspect_ratio
    )


def _suppress_box_relative_protrusions(
    heights: np.ndarray,
    active: np.ndarray,
    filled: np.ndarray,
    *,
    cell_size_mm: float,
    box_width_mm: float,
    box_depth_mm: float,
    prominence_mm: float,
    rules: ProtrusionShapeRules,
) -> tuple[np.ndarray, np.ndarray, int]:
    """小物とパレット境界の薄い壁だけを、基準箱の寸法で判定する。"""
    corrected = heights.copy()
    suppressed = np.zeros(heights.shape, dtype=bool)
    if box_width_mm <= 0 or box_depth_mm <= 0:
        return corrected, suppressed, 0
    kernel_size = _opening_kernel_size(
        min(box_width_mm, box_depth_mm) * 0.75,
        cell_size_mm=cell_size_mm,
        grid_shape=heights.shape,
    )
    if kernel_size < 3:
        return corrected, suppressed, 0
    base_surface = cv2.morphologyEx(
        filled, cv2.MORPH_OPEN, ellipse_kernel(kernel_size)
    )
    residual = heights - base_surface
    strong = active & (residual >= max(float(prominence_mm), 1.0))
    if not np.any(strong):
        return corrected, suppressed, 0

    total, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        strong.astype(np.uint8), connectivity=8
    )
    box_area_mm2 = box_width_mm * box_depth_mm
    min_area_mm2 = box_area_mm2 * rules.minimum_area_ratio
    max_area_mm2 = box_area_mm2 * rules.maximum_area_ratio
    expansion = expansion_kernel(max(int(math.ceil(30.0 / cell_size_mm)), 1))
    weak = active & (residual >= max(float(prominence_mm) / 3.0, 15.0))
    surrounding_surface = np.full(heights.shape, -np.inf, dtype=np.float32)
    count = 0
    for label in range(1, total):
        x, y, width, height, area_cells = stats[label]
        area_mm2 = float(area_cells) * cell_size_mm**2
        component = labels == label
        is_small_object = False
        if min_area_mm2 <= area_mm2 <= max_area_mm2:
            short_span_mm, long_span_mm = oriented_mask_spans(
                component, cell_size_mm=cell_size_mm
            )
            is_small_object = _is_small_height_object(
                short_span_mm=short_span_mm,
                long_span_mm=long_span_mm,
                area_mm2=area_mm2,
                box_width_mm=box_width_mm,
                box_depth_mm=box_depth_mm,
                minimum_area_mm2=min_area_mm2,
                maximum_area_mm2=max_area_mm2,
                rules=rules,
            )
        is_boundary_ribbon = _is_boundary_height_ribbon(
            x=int(x), y=int(y), width=int(width), height=int(height),
            area_mm2=area_mm2, residual_mm=residual[component],
            grid_shape=heights.shape, cell_size_mm=cell_size_mm,
            box_width_mm=box_width_mm, box_depth_mm=box_depth_mm,
            prominence_mm=prominence_mm,
        )
        if not is_small_object and not is_boundary_ribbon:
            continue
        expanded = cv2.dilate(component.astype(np.uint8), expansion).astype(bool)
        candidate = expanded & weak
        surrounding_level = _highest_supported_surrounding_level(
            heights, candidate, active, cell_size_mm=cell_size_mm
        )
        if surrounding_level is None:
            # 境界の壁は、周囲の箱面が見えない場合も下地へ戻す。
            if not is_boundary_ribbon:
                continue
        else:
            surrounding_surface[candidate] = np.maximum(
                surrounding_surface[candidate], surrounding_level
            )
        suppressed |= candidate
        count += 1

    if np.any(suppressed):
        replacement_surface = np.maximum(base_surface, surrounding_surface)
        corrected[suppressed] = np.minimum(
            heights[suppressed], replacement_surface[suppressed]
        )
    return corrected, suppressed, count


def _highest_supported_surrounding_level(
    heights: np.ndarray,
    candidate_mask: np.ndarray,
    active: np.ndarray,
    *,
    cell_size_mm: float,
) -> float | None:
    """看板候補の周囲から、その直下にある最も高い安定層を求める。"""
    cell = max(float(cell_size_mm), 2.0)
    outer_radius = max(int(round(50.0 / cell)), 1)
    inner_radius = max(int(round(10.0 / cell)), 1)
    outer = cv2.dilate(
        candidate_mask.astype(np.uint8),
        expansion_kernel(outer_radius),
    ).astype(bool)
    inner = cv2.dilate(
        candidate_mask.astype(np.uint8),
        expansion_kernel(inner_radius),
    ).astype(bool)
    valid = active & np.isfinite(heights) & (heights > 0)
    ring = outer & ~inner & valid
    values = heights[ring]
    core = heights[candidate_mask & valid]
    if values.size < 12 or core.size < 8:
        return None

    bin_mm = 20.0
    low = math.floor(float(np.min(values)) / bin_mm) * bin_mm
    high = math.ceil(float(np.max(values)) / bin_mm) * bin_mm + bin_mm
    edges = np.arange(low, high + bin_mm, bin_mm)
    if edges.size < 2:
        return None
    counts, edges = np.histogram(values, edges)
    support = np.convolve(counts, np.ones(3, dtype=np.int32), mode="same")
    minimum_support = max(
        8,
        int(math.ceil(np.count_nonzero(candidate_mask) * 0.015)),
    )
    # 候補自体の低い側より高い層は、隣接する上段の箱とみなして除外する。
    ceiling = float(np.quantile(core, 0.25)) + 20.0
    candidates: list[float] = []
    for index in range(counts.size):
        left = support[index - 1] if index else -1
        right = support[index + 1] if index + 1 < support.size else -1
        if (
            support[index] < minimum_support
            or support[index] < left
            or support[index] < right
        ):
            continue
        center = float((edges[index] + edges[index + 1]) / 2.0)
        cluster_values = heights[ring & (np.abs(heights - center) <= 30.0)]
        if cluster_values.size < minimum_support:
            continue
        lower, upper = np.quantile(cluster_values, (0.1, 0.9))
        selected = cluster_values[
            (cluster_values >= lower) & (cluster_values <= upper)
        ]
        if selected.size < minimum_support:
            continue
        # 傾きや低めの深度点に引かれにくい、採用層の75%分位を使う。
        level = float(np.quantile(selected, 0.75))
        if level <= ceiling:
            candidates.append(level)
    return max(candidates, default=None)


def _isolated_fixed_signs(
    heights: np.ndarray,
    active: np.ndarray,
    *,
    cell_size_mm: float,
    rules: FixedSignRules,
) -> tuple[np.ndarray, int]:
    """箱面と連結していない、固定看板の実測形状に合う成分を選ぶ。"""
    result = np.zeros(active.shape, dtype=bool)
    total, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        active.astype(np.uint8), connectivity=8
    )
    count = 0
    cell_area_mm2 = cell_size_mm * cell_size_mm
    for label in range(1, total):
        component = labels == label
        area_mm2 = float(stats[label, cv2.CC_STAT_AREA]) * cell_area_mm2
        if not (
            rules.isolated_sign_min_area_mm2
            <= area_mm2
            <= rules.isolated_sign_max_area_mm2
        ):
            continue
        short_span_mm, long_span_mm = oriented_mask_spans(
            component,
            cell_size_mm=cell_size_mm,
        )
        values = heights[component]
        volume_mm3 = float(np.sum(values) * cell_area_mm2)
        if not (
            rules.isolated_sign_min_short_span_mm
            <= short_span_mm
            <= rules.isolated_sign_max_short_span_mm
            and rules.isolated_sign_min_long_span_mm
            <= long_span_mm
            <= rules.isolated_sign_max_long_span_mm
            and rules.isolated_sign_min_volume_mm3
            <= volume_mm3
            <= rules.isolated_sign_max_volume_mm3
            and rules.isolated_sign_min_median_height_mm
            <= float(np.median(values))
            <= rules.isolated_sign_max_median_height_mm
            and float(np.max(values)) <= rules.isolated_sign_max_height_mm
        ):
            continue
        result |= component
        count += 1
    return result, count


def _result(
    original: np.ndarray,
    corrected: np.ndarray,
    suppressed: np.ndarray,
    *,
    component_count: int,
    cell_size_mm: float,
) -> HeightProtrusionFilterResult:
    removed_height_mm = np.maximum(original[suppressed] - corrected[suppressed], 0.0)
    return HeightProtrusionFilterResult(
        height_grid=corrected,
        suppressed_mask=suppressed,
        component_count=component_count,
        suppressed_cells=int(np.count_nonzero(suppressed)),
        suppressed_volume_mm3=float(
            np.sum(removed_height_mm) * cell_size_mm * cell_size_mm
        ),
    )


def _is_small_height_object(
    *,
    short_span_mm: float,
    long_span_mm: float,
    area_mm2: float,
    box_width_mm: float,
    box_depth_mm: float,
    minimum_area_mm2: float,
    maximum_area_mm2: float,
    rules: ProtrusionShapeRules,
) -> bool:
    """基準箱の縦横とも80%以下に収まる小物を判定する。"""
    short_box = min(float(box_width_mm), float(box_depth_mm))
    long_box = max(float(box_width_mm), float(box_depth_mm))
    return (
        minimum_area_mm2 <= area_mm2 <= maximum_area_mm2
        and short_span_mm <= short_box * rules.small_object_max_span_ratio
        and long_span_mm <= long_box * rules.small_object_max_span_ratio
    )


def _is_boundary_height_ribbon(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    area_mm2: float,
    residual_mm: np.ndarray,
    grid_shape: tuple[int, int],
    cell_size_mm: float,
    box_width_mm: float,
    box_depth_mm: float,
    prominence_mm: float,
) -> bool:
    """パレット境界に接する薄い壁状成分だけを判定する。"""
    rows, columns = grid_shape
    cell = max(float(cell_size_mm), 2.0)
    short_box = min(float(box_width_mm), float(box_depth_mm))
    box_area_mm2 = float(box_width_mm) * float(box_depth_mm)
    if short_box <= 0 or box_area_mm2 <= 0 or residual_mm.size == 0:
        return False

    border_cells = max(int(math.ceil(20.0 / cell)), 1)
    touches_horizontal = y <= border_cells or y + height >= rows - border_cells
    touches_vertical = x <= border_cells or x + width >= columns - border_cells
    candidate_spans: list[tuple[float, float]] = []
    if touches_horizontal:
        candidate_spans.append((float(height) * cell, float(width) * cell))
    if touches_vertical:
        candidate_spans.append((float(width) * cell, float(height) * cell))
    if not candidate_spans:
        return False

    max_inward_span_mm = short_box * 0.12
    min_along_span_mm = short_box * 0.20
    shape_matches = any(
        inward_span <= max_inward_span_mm
        and along_span >= min_along_span_mm
        and along_span >= inward_span * 3.0
        for inward_span, along_span in candidate_spans
    )
    if not shape_matches or area_mm2 > box_area_mm2 * 0.12:
        return False
    required_prominence_mm = max(float(prominence_mm) * 2.0, short_box * 0.5)
    return float(np.median(residual_mm)) >= required_prominence_mm
