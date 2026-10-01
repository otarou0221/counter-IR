"""カメラ用途に依存しないDepthフレーム群の集約。"""

from __future__ import annotations

import warnings

import numpy as np


def temporal_median_depth(frames: np.ndarray) -> np.ndarray:
    """無効値0を除外し、フレーム軸の中央値Depthをfloat32で返す。"""
    values = np.asarray(frames)
    if values.ndim != 3 or values.shape[0] < 1:
        raise ValueError(f"Depthフレーム群の形状が不正です: {values.shape}")
    if values.shape[0] == 1:
        # 正式測定の既定値は1枚。中央値用のNaN配列とソートを作らない。
        single = values[0].astype(np.float32, copy=False)
        if np.isfinite(single).all() and np.all(single >= 0):
            return single
        return np.where(np.isfinite(single) & (single > 0), single, 0.0).astype(
            np.float32,
            copy=False,
        )
    stack = values.astype(np.float32, copy=True)
    stack[stack <= 0] = np.nan
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        depth = np.nanmedian(stack, axis=0)
    return np.where(np.isfinite(depth), depth, 0.0).astype(np.float32)
