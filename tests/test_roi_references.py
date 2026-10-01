from __future__ import annotations

from pathlib import Path

import pytest

from cardboard_counter_v2.api.roi_references import (
    MAX_FLOOR_CAPTURES_PER_CAMERA,
    RoiReferenceService,
)
from cardboard_counter_v2.api.state import RuntimeStateStore
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec
from cardboard_counter_v2.common.schemas import CaptureManifest


def save_empty(root: Path, capture_id: str, camera_id: str, order: int) -> CaptureManifest:
    directory = root / "captures" / capture_id
    directory.mkdir(parents=True)
    (directory / "depth.npz").write_bytes(b"depth")
    (directory / "xyz.npz").write_bytes(b"xyz")
    (directory / "rgb.jpg").write_bytes(b"rgb")
    (directory / "ir.npz").write_bytes(b"infrared")
    return CaptureManifest(
        capture_id=capture_id,
        camera_id=camera_id,
        purpose="floor",
        retention="persistent",
        depth_path=f"captures/{capture_id}/depth.npz",
        xyz_path=f"captures/{capture_id}/xyz.npz",
        rgb_path=f"captures/{capture_id}/rgb.jpg",
        ir_path=f"captures/{capture_id}/ir.npz",
        projection=ProjectionIntrinsicsSpec(
            width=1280, height=720, fx=750, fy=750, cx=640, cy=360,
        ),
        frame_count=30,
        color_shape=(720, 1280),
        depth_shape=(720, 1280),
        depth_aligned_to_color=False,
        captured_at=f"2026-08-04T00:00:{order:02d}+00:00",
    )


class History:
    def __init__(self, captures):
        self.captures = {capture.capture_id: capture for capture in captures}

    def load_capture(self, capture_id):
        return self.captures[capture_id]

    def list_captures(self, *, camera_id=None, purpose=None, retention=None):
        return [
            capture for capture in self.captures.values()
            if (camera_id is None or capture.camera_id == camera_id)
            and (purpose is None or capture.purpose == purpose)
            and (retention is None or capture.retention == retention)
        ][::-1]


def test_empty_capture_selection_and_limit_are_per_camera(tmp_path: Path) -> None:
    captures = [
        save_empty(tmp_path, f"camera1_{index}", "camera_1", index + 1)
        for index in range(7)
    ] + [
        save_empty(tmp_path, f"camera2_{index}", "camera_2", index + 20)
        for index in range(2)
    ]

    service = RoiReferenceService(
        RuntimeStateStore(),
        History(captures),  # type: ignore[arg-type]
        root=tmp_path,
    )
    selected = service.select_floor("camera_1", "camera1_0")

    assert selected.capture_id == "camera1_0"
    assert service.state_store.load().camera("camera_1").baseline_capture_id == "camera1_0"
    # 使用中の最古データを保護し、次に古い未使用データから2件を整理する。
    assert service.excess_floor_capture_ids("camera_1") == ["camera1_1", "camera1_2"]
    assert service.excess_floor_capture_ids("camera_2") == []
    catalog = service.catalog()
    assert catalog.floor_capture_limit == MAX_FLOOR_CAPTURES_PER_CAMERA
    assert len(catalog.floor_captures) == 9
    assert catalog.captures[0].capture_id == "camera1_0"


def test_empty_capture_selection_rejects_a_different_camera(tmp_path: Path) -> None:
    capture = save_empty(tmp_path, "camera1_empty", "camera_1", 1)
    service = RoiReferenceService(
        RuntimeStateStore(),
        History([capture]),  # type: ignore[arg-type]
        root=tmp_path,
    )

    with pytest.raises(ValueError, match="カメラが一致"):
        service.select_floor("camera_2", "camera1_empty")
