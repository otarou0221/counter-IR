"""Sparse diagnostic stages must not abort an otherwise valid replay."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from cardboard_counter_v2.measurement import artifacts
from cardboard_counter_v2.measurement.debug_point_cloud import (
    DebugPointCloudBundle,
    DebugPointCloudStage,
)
from cardboard_counter_v2.measurement.point_cloud_view import RgbPointCloud


def test_one_point_stage_does_not_abort_debug_artifacts(tmp_path: Path, monkeypatch) -> None:
    def cloud(points: list[list[float]]) -> RgbPointCloud:
        coordinates = np.asarray(points, dtype=np.float32).reshape(-1, 3)
        return RgbPointCloud(coordinates, np.zeros(coordinates.shape, dtype=np.uint8))

    whole = cloud([[0, 0, 0], [100, 100, 100]])
    one_point = cloud([[50, 50, 50]])
    stages = DebugPointCloudBundle(
        context=whole,
        stages=(
            DebugPointCloudStage("single", "1 一点", one_point),
            DebugPointCloudStage("valid", "2 有効", whole),
        ),
    )
    converted: list[str] = []

    def fake_convert(source: Path, output: Path) -> Path:
        converted.append(source.stem)
        output.mkdir(parents=True)
        metadata = output / "metadata.json"
        metadata.write_text("{}", encoding="utf-8")
        return metadata

    def fake_las(path: Path, _points: np.ndarray, _colors: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"LAS")

    monkeypatch.setattr(artifacts, "convert_las_to_potree", fake_convert)
    monkeypatch.setattr(artifacts, "write_rgb_las", fake_las)
    monkeypatch.setattr(artifacts, "build_height_grid_volume_mesh", lambda *a, **kw: object())
    monkeypatch.setattr(artifacts, "write_height_plot", lambda path, **kw: path.write_text("height"))
    monkeypatch.setattr(artifacts, "write_debug_stages_plot", lambda path, **kw: path.write_text("debug"))
    monkeypatch.setattr(
        artifacts,
        "build_height_filled_point_cloud",
        lambda *a, **kw: SimpleNamespace(uvh=np.empty((0, 3))),
    )
    empty = np.zeros((2, 2), dtype=np.float32)
    mask = np.zeros((2, 2), dtype=bool)
    artifacts.save_measurement_artifacts(
        tmp_path / "pallet_2",
        height_grid=empty,
        original_height_grid=empty,
        box_region=mask,
        observed_mask=mask,
        protrusion_mask=mask,
        point_cloud=whole,
        geometry=SimpleNamespace(minimum_u=0, minimum_v=0, cell_size_mm=20),
        summary={"volume_liters": 0},
        debug_points=object(),
        debug_point_clouds=stages,
    )
    html = (tmp_path / "pallet_2" / "debug_point_cloud.html").read_text()
    assert converted == ["point_cloud", "context", "valid"]
    assert '"key":"single","title":"1 一点","metadata":null' in html
    assert '"key":"valid","title":"2 有効","metadata":"debug_point_cloud/valid/metadata.json"' in html
    assert "この段階に表示できる点はありません。" in html
