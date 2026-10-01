"""共有dataディレクトリの安全なパス解決。"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def data_root() -> Path:
    root = Path(os.environ.get("CARDBOARD_DATA_ROOT", "data")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise ValueError(f"不正なIDです: {value!r}")
    return value


def capture_relative_dir(
    capture_id: str,
    *,
    camera_id: str | None = None,
    purpose: str | None = None,
    storage_version: int = 2,
) -> Path:
    """保存形式に対応するCaptureのdataルート相対パスを返す。"""
    capture = safe_id(capture_id)
    if storage_version <= 2:
        return Path("captures") / capture
    if storage_version != 3:
        raise ValueError(f"未対応のCapture保存形式です: {storage_version}")
    if camera_id is None:
        raise ValueError("storage_version=3にはcamera_idが必要です")
    if purpose not in {"floor", "current"}:
        raise ValueError(f"不正なCapture用途です: {purpose!r}")
    return Path("captures") / safe_id(camera_id) / purpose / capture


def capture_dir(
    capture_id: str,
    *,
    camera_id: str | None = None,
    purpose: str | None = None,
    storage_version: int = 2,
) -> Path:
    return data_root() / capture_relative_dir(
        capture_id,
        camera_id=camera_id,
        purpose=purpose,
        storage_version=storage_version,
    )


def frame_batch_dir(batch_id: str) -> Path:
    return data_root() / "camera" / "frame_batches" / safe_id(batch_id)


def measurement_dir(measurement_id: str) -> Path:
    return data_root() / "measurements" / safe_id(measurement_id)


def remove_managed_directory(parent: Path, item_id: str) -> bool:
    """IDで管理する1ディレクトリだけを安全に削除する。"""
    target = parent.resolve() / safe_id(item_id)
    if not target.exists():
        return False
    if target.is_symlink() or not target.is_dir():
        raise ValueError(f"管理ディレクトリの形式が不正です: {target}")
    shutil.rmtree(target)
    return True


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
