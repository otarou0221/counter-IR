"""Cardboard測定サービスが所有する保存データのライフサイクル。"""

from __future__ import annotations

from cardboard_counter_v2.common.storage import capture_dir, remove_managed_directory


def delete_capture(
    capture_id: str,
    *,
    camera_id: str | None = None,
    purpose: str | None = None,
    storage_version: int = 2,
) -> bool:
    """指定された保存形式のCaptureだけを安全に削除する。"""
    target = capture_dir(
        capture_id,
        camera_id=camera_id,
        purpose=purpose,
        storage_version=storage_version,
    )
    return remove_managed_directory(target.parent, capture_id)
