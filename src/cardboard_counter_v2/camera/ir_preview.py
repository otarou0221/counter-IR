"""Active IR の16 bit値を画面表示用の8 bit画像へ変換する。"""

from __future__ import annotations

import numpy as np


def ir_preview(ir_gray: np.ndarray) -> np.ndarray:
    """有効画素の明るさを引き伸ばす。測定には元のIR値を使わない。"""
    if ir_gray.ndim != 2 or ir_gray.dtype != np.uint16:
        raise ValueError("Active IR画像は2次元のuint16である必要があります")
    valid = ir_gray[ir_gray > 0]
    if valid.size == 0:
        return np.zeros(ir_gray.shape, dtype=np.uint8)
    low, high = np.percentile(valid, (1, 99))
    if high <= low:
        return np.where(ir_gray > 0, 128, 0).astype(np.uint8)
    # ROI表示とMJPEGのためだけに実施する。深度計算は生データを使用する。
    return np.clip((ir_gray.astype(np.float32) - low) * (255 / (high - low)), 0, 255).astype(np.uint8)
