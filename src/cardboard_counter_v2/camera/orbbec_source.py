"""Orbbec C++ヘルパーのプロセスとActive IR・Depthフレームを管理する。"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from cardboard_counter_v2.camera.orbbec_build import (
    ensure_helper_built,
    resolve_helper_path,
    resolve_sdk_dir,
)
from cardboard_counter_v2.camera.orbbec_protocol import (
    INFRARED_FRAME_MAGIC,
    DEPTH_FRAME_MAGIC,
    FRAME_HEADER,
    INTRINSICS_FRAME_MAGIC,
    parse_intrinsics_payload,
    read_available_stderr,
    read_exact,
    read_stderr,
)
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics


@dataclass(frozen=True)
class OrbbecSourceConfig:
    ip: str
    port: int = 8090
    width: int = 512
    height: int = 512
    depth_width: int = 512
    depth_height: int = 512
    fps: int = 15
    timeout_ms: int = 1000
    read_timeout_ms: int = 15000
    max_frames: int = 0
    sdk_dir: Path | None = None
    helper_path: Path | None = None
    auto_build: bool = True


@dataclass(frozen=True)
class OrbbecFrameSet:
    ir_gray: np.ndarray
    depth_mm: np.ndarray
    camera_intrinsics: RgbdIntrinsics | None = None


def orbbec_helper_base_command(
    config: OrbbecSourceConfig,
    helper_path: Path,
) -> list[str]:
    return [
        str(helper_path),
        "--ip",
        config.ip,
        "--port",
        str(config.port),
        "--width",
        str(config.width),
        "--height",
        str(config.height),
        "--fps",
        str(config.fps),
        "--timeout-ms",
        str(config.timeout_ms),
    ]


class OrbbecFrameSource:
    """C++ヘルパーを子プロセスとして起動し、同期IR・Depthを読み出す。"""

    def __init__(self, config: OrbbecSourceConfig) -> None:
        self.config = config
        self.sdk_dir = resolve_sdk_dir(config.sdk_dir)
        self.helper_path = resolve_helper_path(config.helper_path)
        self.process: subprocess.Popen[bytes] | None = None
        self.camera_intrinsics: RgbdIntrinsics | None = None

    def __enter__(self) -> "OrbbecFrameSource":
        if self.config.auto_build:
            ensure_helper_built(self.helper_path, self.sdk_dir)
        elif not self.helper_path.exists():
            raise FileNotFoundError(f"Orbbec helper does not exist: {self.helper_path}")

        env = os.environ.copy()
        sdk_lib = str(self.sdk_dir / "SDK" / "lib")
        env["LD_LIBRARY_PATH"] = (
            f"{sdk_lib}:{env['LD_LIBRARY_PATH']}"
            if env.get("LD_LIBRARY_PATH")
            else sdk_lib
        )
        command = orbbec_helper_base_command(self.config, self.helper_path)
        if self.config.max_frames > 0:
            command.extend(["--max-frames", str(self.config.max_frames)])
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def frames(self) -> Iterator[OrbbecFrameSet]:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("OrbbecFrameSource must be used as a context manager")
        while True:
            infrared = self._read_packet(expected_magic=INFRARED_FRAME_MAGIC, dtype=np.uint16)
            if infrared is None:
                return
            depth = self._read_packet(expected_magic=DEPTH_FRAME_MAGIC, dtype=np.uint16)
            if depth is None:
                raise RuntimeError(
                    "Orbbec helper ended after IR frame without depth frame"
                )
            if infrared.shape[:2] != depth.shape[:2]:
                raise RuntimeError("IR画像とDepth画像の解像度が一致しません")
            yield OrbbecFrameSet(
                ir_gray=infrared[:, :, 0],
                depth_mm=depth[:, :, 0],
                camera_intrinsics=self.camera_intrinsics,
            )

    def _read_packet(
        self,
        *,
        expected_magic: bytes,
        dtype: np.dtype,
    ) -> np.ndarray | None:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("OrbbecFrameSource must be used as a context manager")
        try:
            header_data = read_exact(
                self.process.stdout,
                FRAME_HEADER.size,
                timeout_seconds=self.config.read_timeout_ms / 1000,
            )
        except TimeoutError as exc:
            stderr = read_available_stderr(self.process)
            raise TimeoutError(f"{exc} Helper log: {stderr}" if stderr else str(exc)) from exc
        if not header_data:
            stderr = read_stderr(self.process)
            return_code = self.process.poll()
            if return_code not in (0, None):
                raise RuntimeError(
                    f"Orbbec helper exited with code {return_code}: {stderr}".strip()
                )
            return None

        magic, width, height, channels, payload_size, _frame_index = (
            FRAME_HEADER.unpack(header_data)
        )
        if magic == INTRINSICS_FRAME_MAGIC:
            self.camera_intrinsics = parse_intrinsics_payload(
                self._read_payload(payload_size)
            )
            return self._read_packet(expected_magic=expected_magic, dtype=dtype)
        if magic != expected_magic:
            stderr = read_stderr(self.process)
            raise RuntimeError(
                "Invalid frame stream from Orbbec helper. "
                f"Expected magic {expected_magic!r}, got {magic!r}. {stderr}".strip()
            )
        payload = self._read_payload(payload_size)
        expected_size = width * height * channels * np.dtype(dtype).itemsize
        if payload_size != expected_size:
            raise RuntimeError(
                f"Unexpected Orbbec frame size: got {payload_size}, expected {expected_size}"
            )
        return np.frombuffer(payload, dtype=dtype).reshape(
            (height, width, channels)
        ).copy()

    def _read_payload(self, payload_size: int) -> bytes:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("OrbbecFrameSource must be used as a context manager")
        try:
            payload = read_exact(
                self.process.stdout,
                payload_size,
                timeout_seconds=self.config.read_timeout_ms / 1000,
            )
        except TimeoutError as exc:
            stderr = read_available_stderr(self.process)
            raise TimeoutError(f"{exc} Helper log: {stderr}" if stderr else str(exc)) from exc
        if payload is None or len(payload) != payload_size:
            stderr = read_stderr(self.process)
            raise RuntimeError(f"Incomplete Orbbec frame payload. {stderr}".strip())
        return payload
