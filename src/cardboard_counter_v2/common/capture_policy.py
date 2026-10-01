"""Captureの保存形式と保持件数に関する共通方針。"""

from __future__ import annotations

import os


CURRENT_CAPTURE_STORAGE_VERSION = 3
FLOOR_CAPTURES_PER_CAMERA = 5


def current_captures_per_camera() -> int:
    """current Captureの保持件数。0はデータ取得用の無制限。"""
    raw = os.environ.get("CURRENT_CAPTURE_MAX_PER_CAMERA", "2100").strip()
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError(
            "CURRENT_CAPTURE_MAX_PER_CAMERAは0以上の整数で指定してください"
        ) from exc
    if limit < 0:
        raise ValueError(
            "CURRENT_CAPTURE_MAX_PER_CAMERAは0以上の整数で指定してください"
        )
    return limit


CURRENT_CAPTURES_PER_CAMERA = current_captures_per_camera()
