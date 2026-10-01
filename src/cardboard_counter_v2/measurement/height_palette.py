"""高さを診断表示用の共通RGBパレットへ変換する。"""

from __future__ import annotations

import numpy as np


DEFAULT_UPPER_PERCENTILE = 98.0


def height_colors(
    heights_mm: np.ndarray,
    *,
    maximum_height_mm: float,
) -> np.ndarray:
    """Plotly体積表示と同系統の灰色→橙→赤で高さをRGB化する。"""
    heights = np.asarray(heights_mm, dtype=np.float32).reshape(-1)
    normalized = np.clip(heights / max(float(maximum_height_mm), 1.0), 0.0, 1.0)
    positions = np.array([0.0, 0.35, 0.70, 1.0], dtype=np.float32)
    anchors = np.array(
        [
            [221, 221, 221],
            [246, 178, 125],
            [232, 92, 63],
            [184, 0, 31],
        ],
        dtype=np.float32,
    )
    colors = np.column_stack(
        [np.interp(normalized, positions, anchors[:, channel]) for channel in range(3)]
    )
    return np.rint(colors).astype(np.uint8)


def robust_height_color_limit(
    heights_mm: np.ndarray,
    *,
    upper_percentile: float = DEFAULT_UPPER_PERCENTILE,
) -> float:
    """孤立した高点で色幅を潰さない、表示専用の高さ上限を返す。"""
    heights = np.asarray(heights_mm, dtype=np.float32).reshape(-1)
    valid = heights[np.isfinite(heights) & (heights > 0.0)]
    if valid.size == 0:
        return 0.0
    return float(np.percentile(valid, np.clip(upper_percentile, 0.0, 100.0)))
