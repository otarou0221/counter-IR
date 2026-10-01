"""汎用カメラサービスの保存先。"""

from __future__ import annotations

import os
from pathlib import Path
import time

from cardboard_counter_v2.common.storage import remove_managed_directory, safe_id


def camera_data_root() -> Path:
    root = Path(
        os.environ.get(
            "CAMERA_DATA_ROOT",
            os.environ.get("CARDBOARD_DATA_ROOT", "data"),
        )
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def frame_batch_dir(batch_id: str) -> Path:
    return camera_data_root() / "camera" / "frame_batches" / safe_id(batch_id)


def relative_camera_path(path: Path) -> str:
    return str(path.resolve().relative_to(camera_data_root()))


def delete_frame_batch(batch_id: str) -> bool:
    """カメラが所有する一時バッチを削除する。"""
    return remove_managed_directory(
        camera_data_root() / "camera" / "frame_batches",
        batch_id,
    )


def prune_stale_frame_batches(*, exclude: set[str] | None = None) -> list[str]:
    """異常終了で消費されなかった一時バッチだけを期限後に削除する。"""
    maximum_age = max(
        int(os.environ.get("CAMERA_BATCH_MAX_AGE_SECONDS", "86400")),
        60,
    )
    root = camera_data_root() / "camera" / "frame_batches"
    if not root.is_dir():
        return []
    protected = exclude or set()
    cutoff = time.time() - maximum_age
    removed: list[str] = []
    for path in root.iterdir():
        if path.name in protected or path.is_symlink() or not path.is_dir():
            continue
        try:
            if path.stat().st_mtime < cutoff and delete_frame_batch(path.name):
                removed.append(path.name)
        except (OSError, ValueError):
            continue
    return removed
