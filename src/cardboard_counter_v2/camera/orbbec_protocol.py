"""Orbbec C++ヘルパーのバイナリフレーム形式を読み取る。"""

from __future__ import annotations

import json
import os
import select
import struct
import subprocess

from cardboard_counter_v2.common.rgbd import RgbdIntrinsics, parse_rgbd_intrinsics


FRAME_HEADER = struct.Struct("<4sIIIIQ")
INFRARED_FRAME_MAGIC = b"OBIF"
DEPTH_FRAME_MAGIC = b"OBDF"
INTRINSICS_FRAME_MAGIC = b"OBIN"


def parse_intrinsics_payload(payload: bytes) -> RgbdIntrinsics:
    raw = json.loads(payload.decode("utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("Invalid Orbbec intrinsics metadata")
    return parse_rgbd_intrinsics(raw)


def read_exact(
    stream: object,
    size: int,
    *,
    timeout_seconds: float | None = None,
) -> bytes | None:
    chunks = []
    remaining = size
    fd = stream.fileno() if hasattr(stream, "fileno") else None  # type: ignore[attr-defined]
    while remaining > 0:
        if fd is not None and timeout_seconds is not None:
            ready, _, _ = select.select([fd], [], [], timeout_seconds)
            if not ready:
                raise TimeoutError(
                    f"Timed out waiting for {size} bytes from Orbbec helper. "
                    "Close Orbbec Viewer or any other app using the camera, then try again. "
                    "If the camera was just switched from Viewer to CLI, wait a few seconds or power-cycle it."
                )
        chunk = stream.read(remaining)  # type: ignore[attr-defined]
        if not chunk:
            if not chunks:
                return None
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_stderr(process: subprocess.Popen[bytes]) -> str:
    if process.stderr is None or process.poll() is None:
        return ""
    try:
        return process.stderr.read().decode(errors="replace").strip()
    except Exception:
        return ""


def read_available_stderr(process: subprocess.Popen[bytes]) -> str:
    if process.stderr is None:
        return ""
    try:
        fd = process.stderr.fileno()
        chunks = []
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode(errors="replace").strip()
    except Exception:
        return ""
