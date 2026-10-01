"""PotreeConverterを診断成果物生成時だけ起動する外部ツール境界。"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


DEFAULT_POTREE_CONVERTER = "/usr/local/bin/PotreeConverter"
DEFAULT_CONVERSION_TIMEOUT_SECONDS = 120


def convert_las_to_potree(
    source_las: Path,
    output_dir: Path,
    *,
    executable: str | Path | None = None,
    timeout_seconds: int = DEFAULT_CONVERSION_TIMEOUT_SECONDS,
) -> Path:
    """LASをPotree 2形式へ変換し、生成されたmetadata.jsonを返す。"""
    requested_converter = str(
        executable
        or os.environ.get("POTREE_CONVERTER_PATH")
        or DEFAULT_POTREE_CONVERTER
    )
    converter = shutil.which(requested_converter) or requested_converter
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [converter, str(source_las), "-o", str(output_dir), "-m", "poisson"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"PotreeConverterが見つかりません: {converter}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"PotreeConverterが{timeout_seconds}秒以内に完了しませんでした"
        ) from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2_000:]
        raise RuntimeError(
            f"PotreeConverterに失敗しました (終了コード {result.returncode}): {detail}"
        )
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.is_file():
        raise RuntimeError("PotreeConverterは成功しましたがmetadata.jsonがありません")
    return metadata_path
