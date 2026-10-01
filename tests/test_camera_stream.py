from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest

from cardboard_counter_v2.camera import stream as stream_module
from cardboard_counter_v2.camera.fleet import CameraFleet
from cardboard_counter_v2.common.camera_contracts import CameraStreamStatus
from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    FrameBatchRequest,
)
from cardboard_counter_v2.camera.stream import CameraStreamHub
from cardboard_counter_v2.camera.source import FrameSourceRegistry


def test_live_stream_and_frame_batch_share_one_camera_source(monkeypatch) -> None:
    source_count = 0

    class FakeSource:
        def __init__(self, _config) -> None:
            nonlocal source_count
            source_count += 1

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def frames(self):
            index = 0
            while True:
                index += 1
                time.sleep(0.003)
                yield SimpleNamespace(
                    ir_gray=np.full((12, 16), index % 255, dtype=np.uint16),
                    depth_mm=np.full((12, 16), 1000 + index, dtype=np.uint16),
                    camera_intrinsics=SimpleNamespace(fx=500.0),
                )

    hub = CameraStreamHub(source_factory=FakeSource)
    camera = CameraDeviceSettings()

    started = hub.start(camera, wait_timeout=1)
    assert started.connected is True
    mjpeg = hub.mjpeg_frames()
    assert next(mjpeg).startswith(b"--frame\r\nContent-Type: image/jpeg")

    depths, infrared, intrinsics, timestamps = hub.collect_frame_batch(
        FrameBatchRequest(
            frame_count=3,
            warmup_frames=1,
        ),
        frame_timeout=1,
    )

    assert len(depths) == 3
    assert infrared.shape == (12, 16)
    assert intrinsics.fx == 500.0
    assert len(timestamps) == 3
    assert source_count == 1
    mjpeg.close()
    stopped = hub.stop(wait_timeout=1)
    assert stopped.running is False


def test_stream_follows_server_lifecycle_and_reconnects(monkeypatch) -> None:
    source_count = 0

    class FakeSource:
        def __init__(self, _config) -> None:
            nonlocal source_count
            source_count += 1
            self.attempt = source_count

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def frames(self):
            if self.attempt == 1:
                raise RuntimeError("temporary camera error")
            while True:
                time.sleep(0.003)
                yield SimpleNamespace(
                    ir_gray=np.zeros((8, 8), dtype=np.uint16),
                    depth_mm=np.full((8, 8), 1000, dtype=np.uint16),
                    camera_intrinsics=SimpleNamespace(fx=500.0),
                )

    hub = CameraStreamHub(reconnect_seconds=0.01, source_factory=FakeSource)
    hub.launch(CameraDeviceSettings())

    deadline = time.monotonic() + 1
    while not hub.status().connected and time.monotonic() < deadline:
        time.sleep(0.01)

    assert source_count >= 2
    assert hub.status().connected is True
    assert hub.status().running is True
    time.sleep(0.07)
    assert hub.status().running is True
    hub.stop(wait_timeout=1)
    assert hub.status().running is False
    assert hub.status().error is None


def test_jpeg_encoding_runs_only_while_live_viewer_exists(monkeypatch) -> None:
    encoded_count = 0

    class FakeSource:
        def __init__(self, _config) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def frames(self):
            while True:
                time.sleep(0.003)
                yield SimpleNamespace(
                    ir_gray=np.zeros((8, 8), dtype=np.uint16),
                    depth_mm=np.full((8, 8), 1000, dtype=np.uint16),
                    camera_intrinsics=SimpleNamespace(fx=500.0),
                )

    def fake_encode(*_args, **_kwargs):
        nonlocal encoded_count
        encoded_count += 1
        return True, np.asarray([1, 2, 3], dtype=np.uint8)

    monkeypatch.setattr(stream_module.cv2, "imencode", fake_encode)
    hub = CameraStreamHub(source_factory=FakeSource)
    hub.start(CameraDeviceSettings(), wait_timeout=1)
    time.sleep(0.03)
    assert encoded_count == 0

    viewer = hub.mjpeg_frames()
    assert next(viewer).startswith(b"--frame")
    assert encoded_count > 0
    viewer.close()
    hub.stop(wait_timeout=1)


def test_camera_driver_registry_keeps_hub_vendor_independent() -> None:
    registry = FrameSourceRegistry()
    marker = object()
    registry.register("fake_rgbd", lambda _settings: marker)  # type: ignore[arg-type]
    assert registry.create(CameraDeviceSettings(driver="fake_rgbd")) is marker
    with pytest.raises(ValueError, match="未対応"):
        registry.create(CameraDeviceSettings(driver="unknown"))


def test_camera_fleet_reuses_unchanged_hubs_and_restarts_only_changed_camera() -> None:
    hubs = []

    class FakeHub:
        def __init__(self, **_kwargs) -> None:
            self.camera = None
            self.stopped = False
            hubs.append(self)

        def launch(self, camera):
            self.camera = camera
            return self.status()

        def stop(self):
            self.stopped = True
            return self.status()

        def status(self):
            return CameraStreamStatus(running=not self.stopped, camera=self.camera)

    fleet = CameraFleet(source_factory=lambda _settings: object(), hub_factory=FakeHub)  # type: ignore[arg-type]
    cameras = [
        CameraDeviceSettings(camera_id="camera_1", display_name="1", ip="192.168.1.1"),
        CameraDeviceSettings(camera_id="camera_2", display_name="2", ip="192.168.1.2"),
    ]
    fleet.launch(cameras)
    assert len(hubs) == 2
    camera_1_hub = fleet.get("camera_1")
    camera_2_hub = fleet.get("camera_2")

    fleet.configure(cameras)
    assert len(hubs) == 2

    changed = cameras[1].model_copy(update={"ip": "192.168.1.20"})
    fleet.configure([cameras[0], changed])
    assert len(hubs) == 3
    assert camera_1_hub.stopped is False
    assert camera_2_hub.stopped is True
    assert fleet.get("camera_1") is camera_1_hub

    assert fleet.configure([]) == []
    assert camera_1_hub.stopped is True
