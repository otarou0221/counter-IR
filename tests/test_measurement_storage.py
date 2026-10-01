from __future__ import annotations

from pathlib import Path

from cardboard_counter_v2.measurement.storage import delete_capture


def test_delete_v3_capture_uses_camera_and_purpose(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    target = tmp_path / "captures/camera_2/current/capture_1"
    target.mkdir(parents=True)

    removed = delete_capture(
        "capture_1",
        camera_id="camera_2",
        purpose="current",
        storage_version=3,
    )

    assert removed is True
    assert not target.exists()
    assert (tmp_path / "captures/camera_2/current").is_dir()


def test_delete_v2_capture_remains_supported(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    target = tmp_path / "captures/legacy_capture"
    target.mkdir(parents=True)

    assert delete_capture("legacy_capture", storage_version=2) is True
    assert not target.exists()
