from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from tools.camera_service import (
    CameraServiceError,
    command_add,
    command_plan,
    load_deployments,
    repository_status,
)


class Arguments:
    camera_id = "camera_3"
    host_port = None


def temporary_repository(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1]
    (tmp_path / "deploy").mkdir()
    shutil.copy(source / "deploy/cameras.json", tmp_path / "deploy/cameras.json")
    shutil.copy(source / "compose.yaml", tmp_path / "compose.yaml")
    shutil.copy(source / ".env.sample", tmp_path / ".env.sample")
    return tmp_path


def test_add_camera_renders_a_shared_image_service_without_building(
    tmp_path: Path,
) -> None:
    root = temporary_repository(tmp_path)

    planned = command_plan(root, Arguments())
    added = command_add(root, Arguments())

    assert planned["default_host_port"] == 58104
    assert planned["will_build_image"] is False
    assert added["camera_service_url"] == "http://camera-3:8001"
    assert added["image_reused"] is True
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert "  camera-3:" in compose
    assert "${CAMERA_3_SERVICE_HOST_PORT:-58104}:8001" in compose
    assert compose.count("${CAMERA_IMAGE:-cardboard-counter-ir-camera:local}") == 1
    assert "CAMERA_3_SERVICE_HOST_PORT=58104" in (
        root / ".env.sample"
    ).read_text(encoding="utf-8")
    assert [item.camera_id for item in load_deployments(root)] == [
        "camera_1", "camera_2", "camera_3",
    ]
    assert repository_status(root)["valid"] is True


def test_add_camera_rejects_a_port_used_by_another_service(tmp_path: Path) -> None:
    root = temporary_repository(tmp_path)

    with pytest.raises(CameraServiceError, match="58102"):
        command_plan(root, ArgumentsWithPort())


class ArgumentsWithPort:
    camera_id = "camera_3"
    host_port = 58102


def test_validate_detects_generated_compose_drift(tmp_path: Path) -> None:
    root = temporary_repository(tmp_path)
    path = root / "compose.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("camera-2:", "camera-two:"),
        encoding="utf-8",
    )

    with pytest.raises(CameraServiceError, match="一致しません"):
        repository_status(root)


def test_manifest_is_machine_readable_and_versioned() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "deploy/cameras.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert len(payload["cameras"]) >= 2
