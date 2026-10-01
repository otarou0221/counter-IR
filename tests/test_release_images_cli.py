from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tools.release_images import (
    ReleaseImageError,
    SERVICES,
    execute,
    release_images,
    render_image_env,
)


def arguments(command: str, **updates: object) -> argparse.Namespace:
    values = {
        "command": command,
        "registry": "gitlab.example/group/cardboard-counter",
        "version": "v1.2.3",
    }
    values.update(updates)
    return argparse.Namespace(**values)


def test_release_plan_uses_one_version_for_all_service_images(tmp_path: Path) -> None:
    result = execute(tmp_path, arguments("plan"))

    assert result["images"] == {
        service: f"gitlab.example/group/cardboard-counter/{service}:v1.2.3"
        for service in SERVICES
    }


def test_latest_and_registry_urls_are_rejected() -> None:
    with pytest.raises(ReleaseImageError, match="latest"):
        release_images("gitlab.example/group/project", "latest")
    with pytest.raises(ReleaseImageError, match="https"):
        release_images("https://gitlab.example/group/project", "v1.0.0")


def test_push_requires_the_exact_version_confirmation(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    with pytest.raises(ReleaseImageError, match="confirm-push"):
        execute(
            tmp_path,
            arguments("push", confirm_push="v1.2.2"),
            runner=lambda command, _root: calls.append(list(command)) or "",
        )

    assert calls == []


def test_build_targets_the_shared_camera_image_only_once(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    execute(
        tmp_path,
        arguments("build"),
        runner=lambda command, _root: calls.append(list(command)) or "",
    )

    assert calls[0] == ["docker", "compose", "build", *SERVICES]
    assert calls[0].count("camera") == 1


def test_lock_writes_digest_pinned_environment(tmp_path: Path) -> None:
    def runner(command, _root):
        tagged = command[3]
        repository = tagged.rsplit(":", 1)[0]
        return json.dumps([f"{repository}@sha256:{'a' * 64}"])

    output = Path("deploy/images.env")
    result = execute(
        tmp_path,
        arguments("lock", output=output),
        runner=runner,
    )

    rendered = (tmp_path / output).read_text(encoding="utf-8")
    assert result["action"] == "lock"
    assert rendered == render_image_env(result["images"])
    assert rendered.count("@sha256:") == len(SERVICES)


def test_all_official_dockerfile_bases_are_digest_pinned() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfiles = sorted((root / "docker").glob("*/Dockerfile"))

    assert dockerfiles
    for dockerfile in dockerfiles:
        from_lines = [
            line for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if line.startswith("FROM ")
        ]
        assert from_lines
        assert all("@sha256:" in line for line in from_lines), dockerfile


def test_compose_images_can_be_overridden_by_a_locked_environment() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "compose.yaml").read_text(encoding="utf-8")

    for environment_name in (
        "WEB_IMAGE", "API_IMAGE", "POSTGRES_IMAGE", "CAMERA_IMAGE",
        "MEASUREMENT_IMAGE",
    ):
        assert f"${{{environment_name}:-" in compose
