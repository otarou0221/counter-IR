"""校正済みパレットの物理座標と外周マスクを作る。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import cv2
import numpy as np

from cardboard_counter_v2.common.depth_projection import (
    pointcloud_intrinsics_for_depth_shape,
    undistorted_rays,
)
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics
from cardboard_counter_v2.measurement.core.models import RegionOfInterest

if TYPE_CHECKING:
    from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane


@dataclass(frozen=True)
class PalletProjectionGeometry:
    """床基準校正から一度だけ作るパレット上面グリッド座標系。"""

    plane: PalletPlane
    origin_xyz: np.ndarray
    basis_u: np.ndarray
    basis_v: np.ndarray
    minimum_u: float
    minimum_v: float
    width: int
    height: int
    polygon_uv: np.ndarray
    pallet_mask: np.ndarray
    cell_size_mm: float


def build_pallet_projection_geometry(
    roi: RegionOfInterest,
    *,
    color_shape: tuple[int, int],
    depth_shape: tuple[int, int],
    camera_intrinsics: RgbdIntrinsics,
    reference_plane: PalletPlane,
    surface_offset_mm: float,
    cell_size_mm: float,
) -> PalletProjectionGeometry:
    """床ROIの3D外周を平行移動し、固定のパレット上面座標系を作る。"""
    cell = max(float(cell_size_mm), 2.0)
    offset_mm = max(float(surface_offset_mm), 0.0)
    floor_polygon_xyz = _roi_plane_polygon(
        roi,
        color_shape=color_shape,
        depth_shape=depth_shape,
        camera_intrinsics=camera_intrinsics,
        plane=reference_plane,
    )
    # 同じ画素の視線を上面と再交差させない。床で確定した3D四隅を、
    # 床法線（カメラ側）へパレット高さ分だけ平行移動する。
    polygon_xyz = (
        floor_polygon_xyz
        + offset_mm * reference_plane.normal[None, :]
    )
    surface_plane = replace(
        reference_plane,
        normal=reference_plane.normal.copy(),
        offset=float(reference_plane.offset - offset_mm),
    )
    basis_u, basis_v = _plane_basis(surface_plane.normal)
    origin = polygon_xyz[0]
    polygon_uv = np.column_stack(
        ((polygon_xyz - origin) @ basis_u, (polygon_xyz - origin) @ basis_v)
    )
    minimum_u, minimum_v = np.min(polygon_uv, axis=0) - cell
    maximum_u, maximum_v = np.max(polygon_uv, axis=0) + cell
    width = max(int(np.ceil((maximum_u - minimum_u) / cell)), 1)
    height = max(int(np.ceil((maximum_v - minimum_v) / cell)), 1)
    if width * height > 2_000_000:
        raise ValueError("パレット平面グリッドが大きすぎます。ROIを確認してください。")

    polygon_cells = np.round(
        np.column_stack(
            (
                (polygon_uv[:, 0] - minimum_u) / cell,
                (polygon_uv[:, 1] - minimum_v) / cell,
            )
        )
    ).astype(np.int32)
    pallet_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(pallet_mask, [polygon_cells], 1)
    return PalletProjectionGeometry(
        plane=surface_plane,
        origin_xyz=origin.astype(np.float32),
        basis_u=basis_u.astype(np.float32),
        basis_v=basis_v.astype(np.float32),
        minimum_u=float(minimum_u),
        minimum_v=float(minimum_v),
        width=width,
        height=height,
        polygon_uv=polygon_uv.astype(np.float32),
        pallet_mask=pallet_mask.astype(bool),
        cell_size_mm=cell,
    )


def _plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    camera_x = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    basis_u = camera_x - float(camera_x @ normal) * normal
    if np.linalg.norm(basis_u) < 1e-5:
        camera_x = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        basis_u = camera_x - float(camera_x @ normal) * normal
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(normal, basis_u)
    basis_v /= np.linalg.norm(basis_v)
    return basis_u, basis_v


def _roi_plane_polygon(
    roi: RegionOfInterest,
    *,
    color_shape: tuple[int, int],
    depth_shape: tuple[int, int],
    camera_intrinsics: RgbdIntrinsics,
    plane: PalletPlane,
) -> np.ndarray:
    x1, y1, x2, y2 = roi_bounds_for_depth(
        roi,
        color_shape=color_shape,
        depth_shape=depth_shape,
    )
    intrinsics = pointcloud_intrinsics_for_depth_shape(camera_intrinsics, depth_shape)
    corners = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
    ray_x, ray_y = undistorted_rays(
        np.asarray([corner[0] for corner in corners], dtype=np.float32),
        np.asarray([corner[1] for corner in corners], dtype=np.float32),
        intrinsics,
        depth_shape,
    )
    intersections = []
    for x, y in zip(ray_x, ray_y):
        ray = np.array([x, y, 1.0], dtype=np.float32)
        denominator = float(plane.normal @ ray)
        if abs(denominator) < 1e-7:
            raise ValueError("ROIの視線とパレット平面が交差しません。")
        distance = -float(plane.offset) / denominator
        if distance <= 0:
            raise ValueError("パレット平面がカメラの後方になっています。")
        intersections.append(ray * distance)
    return np.asarray(intersections, dtype=np.float32)


def roi_bounds_for_depth(
    roi: RegionOfInterest,
    *,
    color_shape: tuple[int, int],
    depth_shape: tuple[int, int],
) -> tuple[int, int, int, int]:
    depth_height, depth_width = depth_shape
    color_height, color_width = color_shape
    x1 = int(np.floor(roi.x1 / max(color_width, 1) * depth_width))
    y1 = int(np.floor(roi.y1 / max(color_height, 1) * depth_height))
    x2 = int(np.ceil(roi.x2 / max(color_width, 1) * depth_width))
    y2 = int(np.ceil(roi.y2 / max(color_height, 1) * depth_height))
    return (
        max(0, min(x1, depth_width - 1)),
        max(0, min(y1, depth_height - 1)),
        max(1, min(x2, depth_width)),
        max(1, min(y2, depth_height)),
    )
