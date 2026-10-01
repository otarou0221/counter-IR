"""Orbbec SDKとC++ヘルパーの解決・ビルド。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORBBEC_SDK_DIR_ENV = "ORBBEC_SDK_DIR"
ORBBEC_HELPER_PATH_ENV = "ORBBEC_HELPER_PATH"
DEFAULT_ORBBEC_SDK_CANDIDATES = (
    PROJECT_ROOT / "third_party" / "orbbec_sdk",
    Path.home()
    / "Downloads"
    / "OrbbecSDK_C_C++_v1.10.27_20250925_0549823_linux_x64_release"
    / "OrbbecSDK_v1.10.27",
    Path.home()
    / "OrbbecSDK_C_C++_v1.10.27_20250925_0549823_linux_x64_release"
    / "OrbbecSDK_v1.10.27",
)


def resolve_sdk_dir(raw_sdk_dir: Path | None) -> Path:
    if raw_sdk_dir is not None:
        candidates = (raw_sdk_dir,)
    else:
        environment_sdk_dir = os.environ.get(ORBBEC_SDK_DIR_ENV, "").strip()
        environment_candidates = (
            (Path(environment_sdk_dir),) if environment_sdk_dir else ()
        )
        candidates = environment_candidates + DEFAULT_ORBBEC_SDK_CANDIDATES
    for candidate in candidates:
        sdk_dir = candidate.expanduser().resolve()
        if (sdk_dir / "SDK" / "include" / "libobsensor").exists() and (
            sdk_dir / "SDK" / "lib" / "libOrbbecSDK.so"
        ).exists():
            return sdk_dir
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "Could not find Orbbec C/C++ SDK. "
        f"Use ORBBEC_SDK_DIR to specify it. Searched: {searched}"
    )


def resolve_helper_path(raw_helper_path: Path | None) -> Path:
    if raw_helper_path is not None:
        return raw_helper_path.expanduser().resolve()
    environment_helper_path = os.environ.get(ORBBEC_HELPER_PATH_ENV, "").strip()
    if environment_helper_path:
        return Path(environment_helper_path).expanduser().resolve()
    return (Path("build") / "orbbec_ir_depth_stream").resolve()


def ensure_helper_built(helper_path: Path, sdk_dir: Path) -> None:
    source_path = Path("native") / "orbbec_ir_depth_stream.cpp"
    if not source_path.exists():
        raise FileNotFoundError(f"Orbbec helper source does not exist: {source_path}")
    if helper_path.exists() and helper_path.stat().st_mtime >= source_path.stat().st_mtime:
        return
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    include_dir = sdk_dir / "SDK" / "include"
    lib_dir = sdk_dir / "SDK" / "lib"
    command = [
        "g++",
        "-std=c++17",
        str(source_path),
        f"-I{include_dir}",
        f"-L{lib_dir}",
        "-lOrbbecSDK",
        f"-Wl,-rpath,{lib_dir}",
        "-O2",
        "-o",
        str(helper_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to build Orbbec helper.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
