"""測定に依存しない点群投影と、測定結果を重ねる診断表示を作る。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.height_palette import (
    height_colors,
    robust_height_color_limit,
)


DEFAULT_CONTEXT_MARGIN_RATIO = 0.5
DEFAULT_MINIMUM_CONTEXT_MARGIN_MM = 300.0
DEFAULT_MAXIMUM_VIEW_POINTS = 250_000


@dataclass(frozen=True)
class ProjectedPointCloud:
    """パレット座標の点と、色を取得するための元RGB画素番号。"""

    uvh: np.ndarray
    pixel_indices: np.ndarray


@dataclass(frozen=True)
class ScenePointCloudSource:
    """全パレットで共有する、1撮影分の有効XYZとRGB画素番号。"""

    xyz: np.ndarray
    pixel_indices: np.ndarray


@dataclass(frozen=True)
class RgbPointCloud:
    uvh: np.ndarray
    colors_rgb: np.ndarray
    highlighted_count: int = 0
    height_color_limit_mm: float = 0.0


def build_scene_point_cloud_source(
    xyz: np.ndarray,
    point_valid: np.ndarray,
) -> ScenePointCloudSource:
    """撮影全体から有効点を1回だけ抽出し、パレット間で共有する。"""
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise ValueError("XYZマップは高さ×幅×3である必要があります。")
    if point_valid.shape != xyz.shape[:2]:
        raise ValueError("XYZマップと有効点マスクのサイズが一致しません。")
    pixel_indices = np.flatnonzero(point_valid.reshape(-1))
    points = xyz.reshape(-1, 3)[pixel_indices]
    finite = np.isfinite(points).all(axis=1)
    return ScenePointCloudSource(
        xyz=points[finite].astype(np.float32, copy=True),
        pixel_indices=pixel_indices[finite].copy(),
    )


def project_scene_point_cloud_for_view(
    source: ScenePointCloudSource,
    geometry: PalletProjectionGeometry,
    *,
    context_margin_ratio: float = DEFAULT_CONTEXT_MARGIN_RATIO,
    minimum_context_margin_mm: float = DEFAULT_MINIMUM_CONTEXT_MARGIN_MM,
    maximum_points: int = DEFAULT_MAXIMUM_VIEW_POINTS,
) -> ProjectedPointCloud:
    """パレットとその周辺を、パレット基準の表示座標へ一度だけ変換する。"""
    points = source.xyz
    pixel_indices = source.pixel_indices
    heights = geometry.plane.heights_mm(points)
    finite = np.isfinite(heights)
    points, heights = points[finite], heights[finite]
    pixel_indices = pixel_indices[finite]
    projected = points - heights[:, None] * geometry.plane.normal[None, :]
    u = (projected - geometry.origin_xyz) @ geometry.basis_u
    v = (projected - geometry.origin_xyz) @ geometry.basis_v

    width_mm = geometry.width * geometry.cell_size_mm
    height_mm = geometry.height * geometry.cell_size_mm
    margin_u = max(width_mm * max(float(context_margin_ratio), 0.0), minimum_context_margin_mm)
    margin_v = max(height_mm * max(float(context_margin_ratio), 0.0), minimum_context_margin_mm)
    context = (
        (u >= geometry.minimum_u - margin_u)
        & (u < geometry.minimum_u + width_mm + margin_u)
        & (v >= geometry.minimum_v - margin_v)
        & (v < geometry.minimum_v + height_mm + margin_v)
    )
    uvh = np.column_stack((u[context], v[context], heights[context]))
    return sample_projected_point_cloud(
        uvh,
        pixel_indices[context],
        maximum=maximum_points,
    )


def colorize_measurement_point_cloud(
    points: ProjectedPointCloud,
    rgb_image: np.ndarray,
    *,
    height_grid: np.ndarray,
    box_region: np.ndarray,
    geometry: PalletProjectionGeometry,
    upper_tolerance_mm: float = 30.0,
) -> RgbPointCloud:
    """周辺は実画像色のまま、体積へ採用した柱内の点だけ高さ色にする。"""
    if rgb_image.ndim != 3 or rgb_image.shape[2] != 3:
        raise ValueError(f"RGB画像の形状が不正です: {rgb_image.shape}")
    heights = np.asarray(height_grid, dtype=np.float32)
    region = np.asarray(box_region, dtype=bool)
    if heights.shape != region.shape or heights.shape != geometry.pallet_mask.shape:
        raise ValueError("高さグリッド、箱領域、パレット形状が一致しません")
    colors = rgb_colors_for_pixel_indices(rgb_image, points.pixel_indices)
    selected = measurement_volume_point_mask(
        points,
        height_grid=heights,
        box_region=region,
        geometry=geometry,
        upper_tolerance_mm=upper_tolerance_mm,
    )
    maximum_height = robust_height_color_limit(heights[region])
    if np.any(selected):
        colors[selected] = height_colors(
            points.uvh[selected, 2],
            maximum_height_mm=maximum_height,
        )
    return RgbPointCloud(
        uvh=points.uvh,
        colors_rgb=colors,
        highlighted_count=int(np.count_nonzero(selected)),
        height_color_limit_mm=maximum_height,
    )


def measurement_volume_point_mask(
    points: ProjectedPointCloud,
    *,
    height_grid: np.ndarray,
    box_region: np.ndarray,
    geometry: PalletProjectionGeometry,
    upper_tolerance_mm: float = 30.0,
) -> np.ndarray:
    """点群のうち、最終体積として採用した柱の内側にある点を返す。"""
    heights = np.asarray(height_grid, dtype=np.float32)
    region = np.asarray(box_region, dtype=bool)
    if heights.shape != region.shape or heights.shape != geometry.pallet_mask.shape:
        raise ValueError("高さグリッド、箱領域、パレット形状が一致しません")
    u, v, point_heights = points.uvh.T
    ix = np.floor((u - geometry.minimum_u) / geometry.cell_size_mm).astype(np.int32)
    iy = np.floor((v - geometry.minimum_v) / geometry.cell_size_mm).astype(np.int32)
    inside = (
        (ix >= 0)
        & (ix < geometry.width)
        & (iy >= 0)
        & (iy < geometry.height)
    )
    selected = np.zeros(len(points.uvh), dtype=bool)
    inside_indices = np.flatnonzero(inside)
    if inside_indices.size:
        inside_x, inside_y = ix[inside], iy[inside]
        cell_heights = heights[inside_y, inside_x]
        in_volume = (
            region[inside_y, inside_x]
            & np.isfinite(point_heights[inside])
            & (point_heights[inside] >= 0.0)
            & (point_heights[inside] <= cell_heights + max(float(upper_tolerance_mm), 0.0))
        )
        selected[inside_indices[in_volume]] = True
    return selected


def rgb_colors_for_pixel_indices(
    rgb_image: np.ndarray,
    pixel_indices: np.ndarray,
) -> np.ndarray:
    """IRプレビューの3チャンネル画像から点に対応する表示色を取り出す。"""
    if rgb_image.ndim != 3 or rgb_image.shape[2] != 3:
        raise ValueError(f"RGB画像の形状が不正です: {rgb_image.shape}")
    indices = np.asarray(pixel_indices, dtype=np.int64).reshape(-1)
    flat_rgb = rgb_image.reshape(-1, 3)
    if indices.size and (indices.min() < 0 or indices.max() >= len(flat_rgb)):
        raise ValueError("ポイントクラウドの画素番号がRGB画像範囲外です")
    return flat_rgb[indices].astype(np.uint8, copy=True)


def sample_projected_point_cloud(
    uvh: np.ndarray,
    pixel_indices: np.ndarray,
    *,
    maximum: int = DEFAULT_MAXIMUM_VIEW_POINTS,
) -> ProjectedPointCloud:
    """位置とRGB画素の対応を保ったまま、ビューア用点群を決定的に間引く。"""
    points = np.asarray(uvh, dtype=np.float32).reshape(-1, 3)
    indices = np.asarray(pixel_indices, dtype=np.int64).reshape(-1)
    if len(points) != len(indices):
        raise ValueError("点群とRGB画素番号の個数が一致しません。")
    if len(points) <= maximum:
        return ProjectedPointCloud(points.copy(), indices.copy())
    step = int(np.ceil(len(points) / max(int(maximum), 1)))
    return ProjectedPointCloud(points[::step].copy(), indices[::step].copy())
