"""要求された場合だけ、IR・Depthバッチから汎用XYZ成果物を作る。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.common.depth_aggregation import temporal_median_depth
from cardboard_counter_v2.common.depth_projection import cached_depth_projector
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics


@dataclass(frozen=True)
class MedianPointCloud:
    depth_mm: np.ndarray
    xyz_mm: np.ndarray


def build_median_point_cloud(
    depth_frames: np.ndarray,
    intrinsics: RgbdIntrinsics,
) -> MedianPointCloud:
    """時間中央値とXYZを各1回だけ計算する。"""
    depth = temporal_median_depth(depth_frames)
    xyz = cached_depth_projector(intrinsics, depth.shape).project(depth)
    return MedianPointCloud(depth_mm=depth, xyz_mm=xyz)
