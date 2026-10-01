"""空Depthからパレット平面を1度だけ推定する。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardboard_counter_v2.measurement.core.models import RegionOfInterest
from cardboard_counter_v2.measurement.core.pallet_geometry import roi_bounds_for_depth


@dataclass(frozen=True)
class PalletPlane:
    """カメラ座標上のパレット平面。normalはカメラ側を向く。"""

    normal: np.ndarray
    offset: float
    fit_rmse_mm: float
    inlier_count: int

    def heights_mm(self, points: np.ndarray) -> np.ndarray:
        return points @ self.normal + float(self.offset)


def fit_pallet_plane(
    baseline_depth_mm: np.ndarray,
    baseline_xyz: np.ndarray,
    *,
    color_shape: tuple[int, int],
    roi: RegionOfInterest,
    expected_depth_mm: float | None,
    residual_threshold_mm: float = 12.0,
) -> PalletPlane:
    """空DepthのROI内から、想定距離に最も一致する平面をRANSACで求める。"""
    if baseline_xyz.shape != (*baseline_depth_mm.shape, 3):
        raise ValueError("空DepthとXYZマップの形状が一致しません。")
    valid = baseline_depth_mm > 0
    x1, y1, x2, y2 = roi_bounds_for_depth(
        roi,
        color_shape=color_shape,
        depth_shape=baseline_depth_mm.shape,
    )
    roi_mask = np.zeros(valid.shape, dtype=bool)
    roi_mask[y1:y2, x1:x2] = True
    valid &= roi_mask

    if expected_depth_mm is not None and expected_depth_mm > 0:
        window = max(150.0, float(expected_depth_mm) * 0.15)
        near_expected = (
            np.abs(baseline_depth_mm.astype(np.float32) - float(expected_depth_mm))
            <= window
        )
        if np.count_nonzero(valid & near_expected) >= 100:
            valid &= near_expected
    points = baseline_xyz[valid]
    if len(points) < 100:
        raise ValueError("パレット平面に使えるDepth点が不足しています。")

    if len(points) > 8_000:
        sample_indexes = np.linspace(0, len(points) - 1, 8_000, dtype=np.int64)
        sample = points[sample_indexes]
    else:
        sample = points
    rng = np.random.default_rng(0)
    best_mask: np.ndarray | None = None
    best_score = -1
    threshold = max(float(residual_threshold_mm), 1.0)
    for _ in range(240):
        selected = sample[rng.choice(len(sample), size=3, replace=False)]
        normal = np.cross(selected[1] - selected[0], selected[2] - selected[0])
        norm = float(np.linalg.norm(normal))
        if norm < 1e-6:
            continue
        normal /= norm
        offset = -float(normal @ selected[0])
        mask = np.abs(sample @ normal + offset) <= threshold
        score = int(np.count_nonzero(mask))
        if score > best_score:
            best_score = score
            best_mask = mask
    if best_mask is None or best_score < 100:
        raise ValueError("パレット平面を安定して推定できません。")

    seed_normal, seed_offset = _least_squares_plane(sample[best_mask])
    inliers = points[np.abs(points @ seed_normal + seed_offset) <= threshold]
    if len(inliers) < 100:
        raise ValueError("パレット平面の有効点が不足しています。")
    normal, offset = _least_squares_plane(inliers)
    if offset < 0:
        normal = -normal
        offset = -offset
    residuals = inliers @ normal + offset
    return PalletPlane(
        normal=normal.astype(np.float32),
        offset=float(offset),
        fit_rmse_mm=float(np.sqrt(np.mean(residuals**2))),
        inlier_count=int(len(inliers)),
    )


def _least_squares_plane(points: np.ndarray) -> tuple[np.ndarray, float]:
    center = np.mean(points, axis=0)
    _u, _s, vh = np.linalg.svd(points - center, full_matrices=False)
    normal = vh[-1].astype(np.float64)
    normal /= max(float(np.linalg.norm(normal)), 1e-9)
    return normal, -float(normal @ center)


def inset_roi(roi: RegionOfInterest, *, ratio: float = 0.05) -> RegionOfInterest:
    """外周・穴の影響を減らすため、パレットROIを自動的に縮める。"""
    inset_x = max(int(round((roi.x2 - roi.x1) * max(float(ratio), 0.0))), 1)
    inset_y = max(int(round((roi.y2 - roi.y1) * max(float(ratio), 0.0))), 1)
    if roi.x2 - roi.x1 <= inset_x * 2 + 2 or roi.y2 - roi.y1 <= inset_y * 2 + 2:
        return roi
    return RegionOfInterest(
        roi.x1 + inset_x,
        roi.y1 + inset_y,
        roi.x2 - inset_x,
        roi.y2 - inset_y,
    )
