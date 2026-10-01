#!/usr/bin/env python3
"""アプリのリリースイメージを一括で作成・保存・固定する。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Sequence


SERVICES = ("web", "api", "postgres", "camera", "measurement")
ENV_NAMES = {
    "web": "WEB_IMAGE",
    "api": "API_IMAGE",
    "postgres": "POSTGRES_IMAGE",
    "camera": "CAMERA_IMAGE",
    "measurement": "MEASUREMENT_IMAGE",
}
LOCAL_IMAGES = {
    service: f"cardboard-counter-ir-{service}:local"
    for service in SERVICES
}
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
Runner = Callable[[Sequence[str], Path], str]


class ReleaseImageError(ValueError):
    """リリース操作を開始前に止める入力・状態エラー。"""


def validate_release(registry: str, version: str) -> tuple[str, str]:
    normalized_registry = registry.strip().strip("/")
    if not normalized_registry or "://" in normalized_registry or any(
        character.isspace() for character in normalized_registry
    ):
        raise ReleaseImageError(
            "registryはhttps://を付けず、host/group/project形式で指定してください"
        )
    if not VERSION_PATTERN.fullmatch(version) or version == "latest":
        raise ReleaseImageError("versionにはlatest以外の固定タグを指定してください")
    return normalized_registry, version


def release_images(registry: str, version: str) -> dict[str, str]:
    registry, version = validate_release(registry, version)
    return {
        service: f"{registry}/{service}:{version}"
        for service in SERVICES
    }


def render_image_env(images: dict[str, str]) -> str:
    return "\n".join(
        f"{ENV_NAMES[service]}={images[service]}"
        for service in SERVICES
    ) + "\n"


def run_command(arguments: Sequence[str], root: Path) -> str:
    completed = subprocess.run(
        list(arguments),
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise ReleaseImageError(
            f"コマンドが失敗しました: {' '.join(arguments)}\n{completed.stdout.strip()}"
        )
    return completed.stdout


def tag_images(root: Path, targets: dict[str, str], runner: Runner) -> None:
    for service in SERVICES:
        runner(["docker", "image", "inspect", LOCAL_IMAGES[service]], root)
        runner(["docker", "image", "tag", LOCAL_IMAGES[service], targets[service]], root)


def pushed_digest_image(
    root: Path,
    tagged_image: str,
    runner: Runner,
) -> str:
    output = runner([
        "docker", "image", "inspect", tagged_image,
        "--format", "{{json .RepoDigests}}",
    ], root).strip()
    try:
        digests = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ReleaseImageError(f"RepoDigestsを読み取れません: {tagged_image}") from exc
    repository = tagged_image.rsplit(":", 1)[0]
    matching = [item for item in digests if item.startswith(f"{repository}@sha256:")]
    if not matching:
        raise ReleaseImageError(
            f"push済みdigestが見つかりません: {tagged_image}"
        )
    return matching[0]


def write_new_file(path: Path, content: str) -> None:
    if path.exists():
        raise ReleaseImageError(f"既存ファイルは上書きしません: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def common_release_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", required=True)
    parser.add_argument("--version", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GitLab Registry向けリリースイメージを管理します",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build", "push", "lock", "export"):
        subparser = subparsers.add_parser(name)
        common_release_arguments(subparser)
        if name == "push":
            subparser.add_argument("--confirm-push", required=True)
        elif name == "lock":
            subparser.add_argument("--output", type=Path, default=Path("deploy/images.env"))
        elif name == "export":
            subparser.add_argument("--output", type=Path, required=True)
    return parser


def execute(
    root: Path,
    args: argparse.Namespace,
    runner: Runner = run_command,
) -> dict[str, object]:
    targets = release_images(args.registry, args.version)
    if args.command == "plan":
        return {"action": "plan", "images": targets}
    if args.command == "build":
        # camera-Nは同じcameraイメージを使うため、代表サービスだけを1回ビルドする。
        runner(["docker", "compose", "build", *SERVICES], root)
        tag_images(root, targets, runner)
        return {"action": "build", "images": targets}
    if args.command == "push":
        if args.confirm_push != args.version:
            raise ReleaseImageError("--confirm-pushにはversionと同じ値を指定してください")
        for service in SERVICES:
            runner(["docker", "image", "push", targets[service]], root)
        return {"action": "push", "images": targets}
    if args.command == "lock":
        locked = {
            service: pushed_digest_image(root, targets[service], runner)
            for service in SERVICES
        }
        output = args.output if args.output.is_absolute() else root / args.output
        write_new_file(output, render_image_env(locked))
        return {"action": "lock", "output": str(output), "images": locked}
    if args.command == "export":
        output = args.output if args.output.is_absolute() else root / args.output
        if output.exists():
            raise ReleaseImageError(f"既存ファイルは上書きしません: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        runner([
            "docker", "image", "save", "--output", str(output),
            *(targets[service] for service in SERVICES),
        ], root)
        return {"action": "export", "output": str(output), "images": targets}
    raise ReleaseImageError(f"未対応の操作です: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute(args.root.resolve(), args)
    except ReleaseImageError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
