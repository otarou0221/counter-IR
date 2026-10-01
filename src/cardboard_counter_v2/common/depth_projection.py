"""内部パラメータを使う、ベンダー非依存のDepthからXYZへの変換。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from cardboard_counter_v2.common.rgbd import RgbdIntrinsics, StreamIntrinsics


def pointcloud_intrinsics_for_depth_shape(
    camera: RgbdIntrinsics | None,
    depth_shape: tuple[int, int],
) -> StreamIntrinsics:
    if camera is None:
        raise ValueError("カメラ内部パラメータが必要です")
    if camera.align_depth_to_color and camera.color is not None:
        return camera.color
    if camera.point_cloud_sensor == "color" and camera.color is not None:
        return camera.color
    if camera.depth is not None:
        return camera.depth
    if camera.color is not None:
        return camera.color
    raise ValueError(f"Depth形状{depth_shape}に使える内部パラメータがありません")


def scaled_intrinsics(
    intrinsics: StreamIntrinsics,
    image_shape: tuple[int, int],
) -> tuple[float, float, float, float]:
    image_height, image_width = image_shape
    scale_x = image_width / max(float(intrinsics.width), 1.0)
    scale_y = image_height / max(float(intrinsics.height), 1.0)
    return (
        intrinsics.fx * scale_x,
        intrinsics.fy * scale_y,
        intrinsics.cx * scale_x,
        intrinsics.cy * scale_y,
    )


def undistorted_rays(
    pixel_x: np.ndarray,
    pixel_y: np.ndarray,
    intrinsics: StreamIntrinsics,
    image_shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Brown-Conrady歪みを逆変換して画素ごとの視線を得る。"""
    fx, fy, cx, cy = scaled_intrinsics(intrinsics, image_shape)
    observed_x = (pixel_x - cx) / max(fx, 1e-6)
    observed_y = (pixel_y - cy) / max(fy, 1e-6)
    distortion = intrinsics.distortion
    if distortion is None or not any(vars(distortion).values()):
        return observed_x, observed_y
    x = observed_x.copy()
    y = observed_y.copy()
    for _ in range(8):
        radius2 = x * x + y * y
        radius4 = radius2 * radius2
        radius6 = radius4 * radius2
        radial_num = 1 + distortion.k1 * radius2 + distortion.k2 * radius4 + distortion.k3 * radius6
        radial_den = 1 + distortion.k4 * radius2 + distortion.k5 * radius4 + distortion.k6 * radius6
        radial = radial_num / np.maximum(radial_den, 1e-8)
        tangential_x = 2 * distortion.p1 * x * y + distortion.p2 * (radius2 + 2 * x * x)
        tangential_y = distortion.p1 * (radius2 + 2 * y * y) + 2 * distortion.p2 * x * y
        x = (observed_x - tangential_x) / np.maximum(radial, 1e-8)
        y = (observed_y - tangential_y) / np.maximum(radial, 1e-8)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("広角レンズの歪み補正が収束しません")
    return x, y


@dataclass(frozen=True)
class DepthProjector:
    """内部パラメータと解像度から一度作り、複数Depthへ再利用する投影器。"""

    depth_shape: tuple[int, int]
    ray_x: np.ndarray
    ray_y: np.ndarray

    def project(self, depth_mm: np.ndarray) -> np.ndarray:
        if depth_mm.shape != self.depth_shape:
            raise ValueError(
                f"Depth形状が投影器と一致しません: {depth_mm.shape} != {self.depth_shape}"
            )
        z = depth_mm.astype(np.float32, copy=False)
        valid = np.isfinite(z) & (z > 0)
        xyz = np.empty((*self.depth_shape, 3), dtype=np.float32)
        xyz[:, :, 0] = self.ray_x * z
        xyz[:, :, 1] = self.ray_y * z
        xyz[:, :, 2] = z
        xyz[~valid] = 0.0
        return xyz


def build_depth_projector(
    camera: RgbdIntrinsics,
    depth_shape: tuple[int, int],
) -> DepthProjector:
    intrinsics = pointcloud_intrinsics_for_depth_shape(camera, depth_shape)
    height, width = depth_shape
    pixel_x, pixel_y = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    )
    ray_x, ray_y = undistorted_rays(pixel_x, pixel_y, intrinsics, depth_shape)
    return DepthProjector(depth_shape=depth_shape, ray_x=ray_x, ray_y=ray_y)


@lru_cache(maxsize=16)
def cached_depth_projector(
    camera: RgbdIntrinsics,
    depth_shape: tuple[int, int],
) -> DepthProjector:
    """同じ内部パラメータ・解像度の固定画素光線を再利用する。"""
    return build_depth_projector(camera, depth_shape)


def validate_xyz_depth(xyz: np.ndarray, depth_mm: np.ndarray) -> None:
    """画素対応XYZが同じDepthから作られたことを検証する。"""
    if xyz.shape != (*depth_mm.shape, 3):
        raise ValueError("XYZと中央値Depthの形状が一致しません")
    if not np.isfinite(xyz).all():
        raise ValueError("XYZに非有限値が含まれています")
    if not np.allclose(xyz[:, :, 2], depth_mm, rtol=0.0, atol=0.01):
        raise ValueError("XYZのZ値と中央値Depthが一致しません")
