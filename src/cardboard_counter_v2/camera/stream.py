"""Orbbecへの1本の常時接続をライブ表示と測定撮影で共有する。"""

from __future__ import annotations

from datetime import UTC, datetime
import threading
import time
from typing import Iterator

import cv2
import numpy as np

from cardboard_counter_v2.camera.ir_preview import ir_preview
from cardboard_counter_v2.camera.source import FrameSourceFactory
from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    CameraStreamStatus,
    FrameBatchRequest,
)
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics


def now_iso() -> str:
    return datetime.now(UTC).isoformat()

class CameraStreamHub:
    """HTTPサーバーと同じ期間動作し、切断時はSDK接続を再生成する。"""

    def __init__(
        self,
        *,
        reconnect_seconds: float = 3.0,
        source_factory: FrameSourceFactory,
    ) -> None:
        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._camera: CameraDeviceSettings | None = None
        self._running = False
        self._connected = False
        self._sequence = 0
        self._connection_generation = 0
        self._connection_frames = 0
        self._latest_ir: np.ndarray | None = None
        self._latest_depth: np.ndarray | None = None
        self._latest_intrinsics: RgbdIntrinsics | None = None
        self._latest_jpeg: bytes | None = None
        self._started_at: str | None = None
        self._last_frame_at: str | None = None
        self._error: str | None = None
        self._viewers = 0
        self._capture_users = 0
        self._reconnect_seconds = reconnect_seconds
        self._source_factory = source_factory

    def status(self) -> CameraStreamStatus:
        with self._condition:
            return self._status_locked()

    def launch(self, camera: CameraDeviceSettings) -> CameraStreamStatus:
        """待機せず監視スレッドを開始する。FastAPI起動時に使用する。"""
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                if self._camera != camera:
                    raise ValueError("カメラ設定が変わっています。設定反映には再起動が必要です")
                return self._status_locked()

            self._stop_event.clear()
            self._camera = camera.model_copy(deep=True)
            self._running = True
            self._connected = False
            self._sequence = 0
            self._connection_generation = 0
            self._connection_frames = 0
            self._latest_ir = None
            self._latest_depth = None
            self._latest_intrinsics = None
            self._latest_jpeg = None
            self._started_at = now_iso()
            self._last_frame_at = None
            self._error = None
            self._thread = threading.Thread(
                target=self._run,
                name=f"ir-depth-{camera.camera_id}-lifecycle",
                daemon=True,
            )
            self._thread.start()
            return self._status_locked()

    def start(self, camera: CameraDeviceSettings, *, wait_timeout: float = 20.0) -> CameraStreamStatus:
        """ストリームを保証し、最初のフレームまで待つ。"""
        self.launch(camera)
        with self._condition:
            deadline = time.monotonic() + wait_timeout
            while self._running and not self._connected:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    detail = f": {self._error}" if self._error else ""
                    raise TimeoutError(f"Orbbecの最初のフレームを取得できませんでした{detail}")
                self._condition.wait(timeout=remaining)
            if not self._connected:
                raise RuntimeError("Orbbecストリームがフレーム取得前に終了しました")
            return self._status_locked()

    def restart(self, camera: CameraDeviceSettings) -> CameraStreamStatus:
        self.stop()
        return self.launch(camera)

    def stop(self, *, wait_timeout: float = 20.0) -> CameraStreamStatus:
        """FastAPI終了時に監視スレッドとC++サブプロセスを停止する。"""
        with self._condition:
            thread = self._thread
            self._stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=wait_timeout)
            if thread.is_alive():
                raise TimeoutError("Orbbecストリームを停止できませんでした")
        return self.status()

    def collect_frame_batch(
        self,
        request: FrameBatchRequest,
        *,
        frame_timeout: float = 20.0,
    ) -> tuple[np.ndarray, np.ndarray, RgbdIntrinsics, list[str]]:
        camera = self._camera
        if camera is None:
            raise RuntimeError("カメラ設定がありません")
        self.start(camera, wait_timeout=frame_timeout)
        depth_frames: np.ndarray | None = None
        captured_count = 0
        latest_ir_reference: np.ndarray | None = None
        intrinsics: RgbdIntrinsics | None = None
        frame_timestamps: list[str] = []

        with self._condition:
            self._capture_users += 1
            previous_sequence = self._sequence
            generation = self._connection_generation
            warmup_remaining = max(request.warmup_frames - self._connection_frames, 0)
        try:
            while captured_count < request.frame_count:
                with self._condition:
                    deadline = time.monotonic() + frame_timeout
                    while self._sequence <= previous_sequence and self._running:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            detail = f": {self._error}" if self._error else ""
                            raise TimeoutError(f"測定用の次フレームを取得できませんでした{detail}")
                        self._condition.wait(timeout=remaining)
                    if not self._running or self._latest_depth is None or self._latest_ir is None:
                        raise RuntimeError("測定用フレームの取得中にストリームが終了しました")
                    previous_sequence = self._sequence
                    current_generation = self._connection_generation
                    connection_frames = self._connection_frames
                    depth_reference = self._latest_depth
                    ir_reference = self._latest_ir
                    current_intrinsics = self._latest_intrinsics
                    timestamp = self._last_frame_at or now_iso()
                if generation != current_generation:
                    generation = current_generation
                    depth_frames = None
                    captured_count = 0
                    frame_timestamps.clear()
                    latest_ir_reference = None
                    intrinsics = None
                    warmup_remaining = max(request.warmup_frames - connection_frames, 0)
                if warmup_remaining > 0:
                    warmup_remaining -= 1
                    continue
                # 配列は生成後に書き換えず参照ごと交換される。
                # ロック外で連続配列へ直接書き込み、list→stackの追加コピーを作らない。
                if depth_frames is None:
                    depth_frames = np.empty(
                        (request.frame_count, *depth_reference.shape),
                        dtype=depth_reference.dtype,
                    )
                if depth_reference.shape != depth_frames.shape[1:]:
                    raise RuntimeError("Depthフレームの形状が取得中に変わりました")
                depth_frames[captured_count] = depth_reference
                captured_count += 1
                latest_ir_reference = ir_reference
                intrinsics = current_intrinsics
                frame_timestamps.append(timestamp)
        finally:
            with self._condition:
                self._capture_users = max(0, self._capture_users - 1)
                self._condition.notify_all()

        if depth_frames is None or latest_ir_reference is None or intrinsics is None:
            raise RuntimeError("IRまたはカメラ内部パラメータを取得できませんでした")
        return depth_frames, latest_ir_reference.copy(), intrinsics, frame_timestamps

    def mjpeg_frames(self) -> Iterator[bytes]:
        previous_sequence = -1
        with self._condition:
            self._viewers += 1
        try:
            while True:
                with self._condition:
                    while self._sequence <= previous_sequence and self._running:
                        self._condition.wait(timeout=5.0)
                    if not self._running:
                        return
                    jpeg = self._latest_jpeg
                    previous_sequence = self._sequence
                if jpeg is None:
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                    + jpeg
                    + b"\r\n"
                )
        finally:
            with self._condition:
                self._viewers = max(0, self._viewers - 1)
                self._condition.notify_all()

    def _run(self) -> None:
        camera = self._camera
        if camera is None:
            return
        try:
            while not self._stop_event.is_set():
                try:
                    with self._source_factory(camera) as source:
                        with self._condition:
                            self._connected = False
                            self._connection_generation += 1
                            self._connection_frames = 0
                        for frame in source.frames():
                            if self._stop_event.is_set():
                                break
                            with self._condition:
                                needs_jpeg = self._viewers > 0
                            jpeg: bytes | None = None
                            if needs_jpeg:
                                ok, encoded = cv2.imencode(
                                    ".jpg",
                                    ir_preview(frame.ir_gray),
                                    [cv2.IMWRITE_JPEG_QUALITY, 82],
                                )
                                if not ok:
                                    raise RuntimeError("ライブ映像をJPEGへ変換できませんでした")
                                jpeg = encoded.tobytes()
                            with self._condition:
                                self._latest_ir = frame.ir_gray
                                self._latest_depth = frame.depth_mm
                                self._latest_intrinsics = frame.camera_intrinsics
                                if jpeg is not None:
                                    self._latest_jpeg = jpeg
                                self._sequence += 1
                                self._connection_frames += 1
                                self._connected = True
                                self._error = None
                                self._last_frame_at = now_iso()
                                self._condition.notify_all()
                        if not self._stop_event.is_set():
                            raise RuntimeError("Orbbecストリームが終了しました")
                except Exception as exc:
                    with self._condition:
                        self._connected = False
                        self._error = str(exc)
                        self._condition.notify_all()
                    self._stop_event.wait(self._reconnect_seconds)
        finally:
            with self._condition:
                self._running = False
                self._connected = False
                self._condition.notify_all()

    def _status_locked(self) -> CameraStreamStatus:
        return CameraStreamStatus(
            running=self._running,
            connected=self._connected,
            frames_received=self._sequence,
            started_at=self._started_at,
            last_frame_at=self._last_frame_at,
            error=self._error,
            camera=self._camera,
            viewers=self._viewers,
            capture_active=self._capture_users > 0,
        )
