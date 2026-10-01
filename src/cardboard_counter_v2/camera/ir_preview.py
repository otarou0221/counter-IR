"""Active IR の16 bit値を画面表示用の8 bit画像へ変換する。"""

from __future__ import annotations

from functools import lru_cache
import math
import os

import numpy as np


try:
    _DEFAULT_GAMMA = float(os.environ.get("IR_PREVIEW_GAMMA", "0.55"))
except ValueError as exc:
    raise ValueError("IR_PREVIEW_GAMMAは数値にしてください") from exc


@lru_cache(maxsize=8)
def _gamma_lut(gamma: float) -> np.ndarray:
    """表示補正の表を一度作り、ライブ映像の各フレームで再利用する。"""
    if not math.isfinite(gamma) or not 0.2 <= gamma <= 2.0:
        raise ValueError("IR_PREVIEW_GAMMAは0.2～2.0の数値にしてください")
    levels = np.arange(256, dtype=np.float32) / 255.0
    return np.rint(255.0 * np.power(levels, gamma)).astype(np.uint8)


# 設定値の誤りはcameraサービス起動時に検出する。
_gamma_lut(_DEFAULT_GAMMA)


def ir_preview(ir_gray: np.ndarray, *, gamma: float = _DEFAULT_GAMMA) -> np.ndarray:
    """有効画素を引き伸ばして暗い中間調を持ち上げる。生IRとDepthは変更しない。"""
    if ir_gray.ndim != 2 or ir_gray.dtype != np.uint16:
        raise ValueError("Active IR画像は2次元のuint16である必要があります")
    valid = ir_gray[ir_gray > 0]
    if valid.size == 0:
        return np.zeros(ir_gray.shape, dtype=np.uint8)
    lut = _gamma_lut(gamma)
    low, high = np.percentile(valid, (1, 99))
    if high <= low:
        return np.where(ir_gray > 0, lut[128], 0).astype(np.uint8)
    # ROI画像とMJPEGだけに適用し、測定に使うDepth/XYZには触れない。
    linear = np.clip(
        (ir_gray.astype(np.float32) - low) * (255 / (high - low)), 0, 255
    ).astype(np.uint8)
    return lut[linear]
