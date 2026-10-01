"""10mm高さグリッドから安定した箱領域を作る。"""

from __future__ import annotations

import cv2
import numpy as np
from functools import lru_cache


@lru_cache(maxsize=16)
def square_kernel(size: int) -> np.ndarray:
    """監視ループで不変のOpenCVカーネルを再利用する。"""
    return np.ones((size, size), dtype=np.uint8)


def extract_box_region_mask(occupied_mask: np.ndarray) -> np.ndarray:
    if not np.any(occupied_mask):
        return occupied_mask.copy()
    candidate = cleanup_occupied_mask(occupied_mask)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        candidate.astype(np.uint8), connectivity=8
    )
    minimum_area = max(4, int(candidate.shape[0] * candidate.shape[1] * 0.002))
    result = np.zeros(candidate.shape, dtype=bool)
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= minimum_area:
            result |= labels == label
    return result if np.any(result) else occupied_mask.copy()


def recover_nearby_box_pixels(
    box_region: np.ndarray,
    height_map: np.ndarray,
    valid_mask: np.ndarray,
    *,
    occupied_height_mm: float,
) -> np.ndarray:
    if not np.any(box_region):
        return box_region.copy()
    support = (height_map >= max(5.0, occupied_height_mm * 0.5)) & valid_mask
    count, labels = cv2.connectedComponents(support.astype(np.uint8), connectivity=8)
    connected = np.zeros(support.shape, dtype=bool)
    for label in range(1, count):
        component = labels == label
        if np.any(component & box_region):
            connected |= component
    if not np.any(connected):
        return box_region.copy()
    kernel_size = max(3, min(7, int(round(min(box_region.shape) * 0.015))))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = square_kernel(kernel_size)
    region = box_region.astype(np.uint8)
    nearby = cv2.dilate(region, kernel, iterations=2).astype(bool)
    closed = cv2.morphologyEx(region, cv2.MORPH_CLOSE, kernel).astype(bool)
    return (((nearby | closed) & connected) | box_region).astype(bool)


def cleanup_occupied_mask(mask: np.ndarray) -> np.ndarray:
    if min(mask.shape) < 12:
        return mask.copy()
    kernel_size = max(3, min(9, int(round(min(mask.shape) * 0.015))))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = square_kernel(kernel_size)
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
    return opened.astype(bool) if np.any(opened) else mask.copy()
