#!/usr/bin/env python3
"""1カメラ1コンテナのCompose定義を安全に追加・検証する。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence


MANIFEST_PATH = Path("deploy/cameras.json")
COMPOSE_PATH = Path("compose.yaml")
ENV_SAMPLE_PATH = Path(".env.sample")
COMPOSE_BEGIN = "  # camera-service:begin"
COMPOSE_END = "  # camera-service:end"
ENV_BEGIN = "# camera-service:begin"
ENV_END = "# camera-service:end"
CAMERA_ID_PATTERN = re.compile(r"camera_([1-9][0-9]*)\Z")
COMPOSE_PORT_PATTERN = re.compile(
    r"\$\{(?P<name>[A-Z][A-Z0-9_]*):-?(?P<default>[0-9]+)\}(?=:[0-9]+)"
)


class CameraServiceError(ValueError):
    """利用者が修正できるカメラサービス定義エラー。"""


@dataclass(frozen=True, order=True)
class CameraDeployment:
    number: int
    default_host_port: int

    @property
    def camera_id(self) -> str:
        return f"camera_{self.number}"

    @property
    def service_name(self) -> str:
        return "camera" if self.number == 1 else f"camera-{self.number}"

    @property
    def host_port_env(self) -> str:
        return (
            "CAMERA_SERVICE_HOST_PORT"
            if self.number == 1
            else f"CAMERA_{self.number}_SERVICE_HOST_PORT"
        )

    @property
    def internal_url(self) -> str:
        return f"http://camera-{self.number}:8001"

    def to_json(self) -> dict[str, object]:
        return {
            "camera_id": self.camera_id,
            "default_host_port": self.default_host_port,
        }


def camera_number(camera_id: str) -> int:
    match = CAMERA_ID_PATTERN.fullmatch(camera_id)
    if match is None:
        raise CameraServiceError(
            "camera_idはcamera_1、camera_2の形式で指定してください"
        )
    return int(match.group(1))


def load_deployments(root: Path) -> list[CameraDeployment]:
    path = root / MANIFEST_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CameraServiceError(f"カメラ配置定義を読み込めません: {path}") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cameras"), list):
        raise CameraServiceError("deploy/cameras.jsonの形式が正しくありません")
    deployments: list[CameraDeployment] = []
    for item in payload["cameras"]:
        if not isinstance(item, dict):
            raise CameraServiceError("camerasの各要素はオブジェクトで指定してください")
        number = camera_number(str(item.get("camera_id", "")))
        port = item.get("default_host_port")
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise CameraServiceError(
                f"{item.get('camera_id', 'camera')}のポートは1024〜65535で指定してください"
            )
        deployments.append(CameraDeployment(number, port))
    validate_deployments(deployments)
    return sorted(deployments)


def validate_deployments(deployments: Sequence[CameraDeployment]) -> None:
    if not deployments or not any(item.number == 1 for item in deployments):
        raise CameraServiceError("camera_1は必須です")
    numbers = [item.number for item in deployments]
    if len(numbers) != len(set(numbers)):
        raise CameraServiceError("camera_idが重複しています")
    ports = [item.default_host_port for item in deployments]
    if len(ports) != len(set(ports)):
        raise CameraServiceError("カメラの既定ホストポートが重複しています")


def render_compose_camera_block(deployments: Sequence[CameraDeployment]) -> str:
    lines = [COMPOSE_BEGIN]
    for deployment in sorted(deployments):
        lines.extend([
            f"  {deployment.service_name}:",
            "    <<: *camera-common",
            "    ports:",
            (
                "      - \"127.0.0.1:"
                f"${{{deployment.host_port_env}:-{deployment.default_host_port}}}:8001\""
            ),
        ])
        if deployment.number == 1:
            lines.extend([
                "    networks:",
                "      internal:",
                "        aliases: [camera-1]",
                "      camera-lan:",
            ])
        else:
            lines.append("    networks: [internal, camera-lan]")
        lines.append("")
    lines.append(COMPOSE_END)
    return "\n".join(lines)


def render_env_camera_block(deployments: Sequence[CameraDeployment]) -> str:
    lines = [ENV_BEGIN]
    lines.extend(
        f"{item.host_port_env}={item.default_host_port}"
        for item in sorted(deployments)
    )
    lines.append(ENV_END)
    return "\n".join(lines)


def replace_managed_block(text: str, begin: str, end: str, replacement: str) -> str:
    try:
        start = text.index(begin)
        finish = text.index(end, start) + len(end)
    except ValueError as exc:
        raise CameraServiceError(f"管理マーカーが見つかりません: {begin} / {end}") from exc
    return f"{text[:start]}{replacement}{text[finish:]}"


def render_repository_files(
    root: Path,
    deployments: Sequence[CameraDeployment],
) -> tuple[str, str]:
    compose_path = root / COMPOSE_PATH
    env_path = root / ENV_SAMPLE_PATH
    try:
        compose = compose_path.read_text(encoding="utf-8")
        env_sample = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CameraServiceError(f"生成対象を読み込めません: {exc.filename}") from exc
    return (
        replace_managed_block(
            compose,
            COMPOSE_BEGIN,
            COMPOSE_END,
            render_compose_camera_block(deployments),
        ),
        replace_managed_block(
            env_sample,
            ENV_BEGIN,
            ENV_END,
            render_env_camera_block(deployments),
        ),
    )


def parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_effective_ports(root: Path, compose: str) -> None:
    env = parse_env(root / ".env")
    owners: dict[int, str] = {}
    for match in COMPOSE_PORT_PATTERN.finditer(compose):
        name = match.group("name")
        raw_port = env.get(name, match.group("default"))
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise CameraServiceError(f"{name}がポート番号ではありません: {raw_port}") from exc
        previous = owners.get(port)
        if previous is not None and previous != name:
            raise CameraServiceError(
                f"有効なホストポート{port}が{previous}と{name}で重複しています"
            )
        owners[port] = name


def repository_status(root: Path) -> dict[str, object]:
    deployments = load_deployments(root)
    expected_compose, expected_env = render_repository_files(root, deployments)
    actual_compose = (root / COMPOSE_PATH).read_text(encoding="utf-8")
    actual_env = (root / ENV_SAMPLE_PATH).read_text(encoding="utf-8")
    if actual_compose != expected_compose:
        raise CameraServiceError(
            "compose.yamlのカメラ定義がdeploy/cameras.jsonと一致しません。renderを実行してください"
        )
    if actual_env != expected_env:
        raise CameraServiceError(
            ".env.sampleのカメラポートがdeploy/cameras.jsonと一致しません。renderを実行してください"
        )
    validate_effective_ports(root, actual_compose)
    return {
        "valid": True,
        "camera_count": len(deployments),
        "cameras": [deployment_details(item) for item in deployments],
    }


def deployment_details(deployment: CameraDeployment) -> dict[str, object]:
    return {
        "camera_id": deployment.camera_id,
        "service_name": deployment.service_name,
        "host_port_env": deployment.host_port_env,
        "default_host_port": deployment.default_host_port,
        "camera_service_url": deployment.internal_url,
    }


def next_available_port(root: Path, deployments: Sequence[CameraDeployment]) -> int:
    compose = (root / COMPOSE_PATH).read_text(encoding="utf-8")
    used = {item.default_host_port for item in deployments}
    used.update(int(match.group("default")) for match in COMPOSE_PORT_PATTERN.finditer(compose))
    port = 58101
    while port in used:
        port += 1
    return port


def planned_deployment(
    root: Path,
    camera_id: str,
    host_port: int | None,
) -> tuple[list[CameraDeployment], CameraDeployment]:
    deployments = load_deployments(root)
    number = camera_number(camera_id)
    if any(item.number == number for item in deployments):
        raise CameraServiceError(f"すでに登録されています: {camera_id}")
    deployment = CameraDeployment(
        number=number,
        default_host_port=(
            host_port if host_port is not None else next_available_port(root, deployments)
        ),
    )
    if not 1024 <= deployment.default_host_port <= 65535:
        raise CameraServiceError("ホストポートは1024〜65535で指定してください")
    updated = sorted([*deployments, deployment])
    validate_deployments(updated)
    compose, _env = render_repository_files(root, updated)
    validate_effective_ports(root, compose)
    return updated, deployment


def write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_manifest(root: Path, deployments: Sequence[CameraDeployment]) -> None:
    payload = {
        "schema_version": 1,
        "cameras": [item.to_json() for item in sorted(deployments)],
    }
    write_text_atomic(
        root / MANIFEST_PATH,
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
    )


def render_files(root: Path, deployments: Sequence[CameraDeployment]) -> None:
    compose, env_sample = render_repository_files(root, deployments)
    write_text_atomic(root / COMPOSE_PATH, compose)
    write_text_atomic(root / ENV_SAMPLE_PATH, env_sample)


def run_compose(root: Path, arguments: Sequence[str]) -> None:
    completed = subprocess.run(
        ["docker", "compose", *arguments],
        cwd=root,
        check=False,
    )
    if completed.returncode != 0:
        raise CameraServiceError(
            f"docker compose {' '.join(arguments)}が失敗しました"
        )


def command_plan(root: Path, args: argparse.Namespace) -> dict[str, object]:
    _updated, deployment = planned_deployment(root, args.camera_id, args.host_port)
    return {"action": "plan", "will_build_image": False, **deployment_details(deployment)}


def command_add(root: Path, args: argparse.Namespace) -> dict[str, object]:
    updated, deployment = planned_deployment(root, args.camera_id, args.host_port)
    write_manifest(root, updated)
    render_files(root, updated)
    repository_status(root)
    return {"action": "add", "image_reused": True, **deployment_details(deployment)}


def command_render(root: Path, _args: argparse.Namespace) -> dict[str, object]:
    deployments = load_deployments(root)
    render_files(root, deployments)
    return {"action": "render", **repository_status(root)}


def command_validate(root: Path, args: argparse.Namespace) -> dict[str, object]:
    status = repository_status(root)
    if args.compose:
        run_compose(root, ["config", "--quiet"])
    return {"action": "validate", "compose_checked": args.compose, **status}


def command_start(root: Path, args: argparse.Namespace) -> dict[str, object]:
    deployments = load_deployments(root)
    number = camera_number(args.camera_id)
    deployment = next((item for item in deployments if item.number == number), None)
    if deployment is None:
        raise CameraServiceError(f"未登録のカメラです: {args.camera_id}")
    repository_status(root)
    run_compose(root, [
        "up", "-d", "--no-deps", "--no-build", "--pull", "missing",
        deployment.service_name,
    ])
    return {"action": "start", "image_reused": True, **deployment_details(deployment)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="カメラごとのComposeサービスを追加・検証します",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "add"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("camera_id")
        subparser.add_argument("--host-port", type=int)
    subparsers.add_parser("render")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--compose", action="store_true")
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("camera_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    commands = {
        "plan": command_plan,
        "add": command_add,
        "render": command_render,
        "validate": command_validate,
        "start": command_start,
    }
    try:
        result = commands[args.command](root, args)
    except CameraServiceError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
