from pathlib import Path

import cv2
import numpy as np
import pytest

from cardboard_counter_v2.common.box_catalog import BoxClassSpec, default_box_catalog
from cardboard_counter_v2.common.schemas import (
    CalibrationRequest, CaptureManifest, MeasurementRequest, PalletSettings,
)
from cardboard_counter_v2.common.planar_calibration import ProjectionIntrinsicsSpec
from cardboard_counter_v2.common.rgbd import RgbdIntrinsics, StreamIntrinsics
from cardboard_counter_v2.measurement.engine import measure
from cardboard_counter_v2.measurement.calibration import calibrate
from cardboard_counter_v2.measurement import calibration as calibration_module
from cardboard_counter_v2.measurement import engine as engine_module
from cardboard_counter_v2.measurement import artifacts as artifacts_module
from cardboard_counter_v2.measurement import runtime as runtime_module
from cardboard_counter_v2.measurement import planning as planning_module
from cardboard_counter_v2.measurement.prepared_runtime import prepared_runtime_registry
from cardboard_counter_v2.common.depth_projection import DepthProjector, build_depth_projector


def write_capture(
    root: Path,
    capture_id: str,
    depth: np.ndarray,
    intrinsics: RgbdIntrinsics,
    *,
    include_xyz: bool = True,
) -> CaptureManifest:
    directory = root / "captures" / capture_id
    directory.mkdir(parents=True)
    np.savez_compressed(directory / "depth.npz", depth_mm=depth)
    if include_xyz:
        np.savez_compressed(
            directory / "xyz.npz",
            xyz_mm=build_depth_projector(intrinsics, depth.shape).project(depth),
        )
    rgb = np.zeros((*depth.shape, 3), dtype=np.uint8)
    rgb[:, :, 2] = 255
    assert cv2.imwrite(str(directory / "rgb.jpg"), rgb)
    stream = intrinsics.color if intrinsics.point_cloud_sensor == "color" else intrinsics.depth
    assert stream is not None
    return CaptureManifest(
        capture_id=capture_id,
        purpose="floor" if capture_id == "empty" else "current",
        depth_path=f"captures/{capture_id}/depth.npz",
        xyz_path=f"captures/{capture_id}/xyz.npz",
        rgb_path=f"captures/{capture_id}/rgb.jpg",
        projection=ProjectionIntrinsicsSpec(
            point_cloud_sensor=intrinsics.point_cloud_sensor,
            align_depth_to_color=intrinsics.align_depth_to_color,
            width=stream.width, height=stream.height,
            fx=stream.fx, fy=stream.fy, cx=stream.cx, cy=stream.cy,
        ),
        frame_count=30,
        color_shape=depth.shape,
        depth_shape=depth.shape,
        depth_aligned_to_color=False,
    )


def test_measurement_uses_empty_roi_plane_method(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    shape = (120, 120)
    baseline = np.full(shape, 1_000.0, dtype=np.float32)
    current = baseline.copy()
    current[20:101, 20:101] = 500.0
    intrinsics = RgbdIntrinsics(
        color=None,
        depth=StreamIntrinsics(
            width=120, height=120, fx=100.0, fy=100.0, cx=60.0, cy=60.0
        ),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    captures = {
        capture_id: write_capture(tmp_path, capture_id, depth, intrinsics)
        for capture_id, depth in (("empty", baseline), ("current", current))
    }

    def fake_potree_conversion(_source: Path, output: Path) -> Path:
        output.mkdir(parents=True)
        metadata = output / "metadata.json"
        metadata.write_text('{"version":"2.0"}', encoding="utf-8")
        (output / "octree.bin").write_bytes(b"octree")
        (output / "hierarchy.bin").write_bytes(b"hierarchy")
        return metadata

    monkeypatch.setattr(artifacts_module, "convert_las_to_potree", fake_potree_conversion)

    pallet = PalletSettings(
        pallet_id=1,
        plane_roi=(0.3333, 0.3333, 0.675, 0.675),
        single_box_labels=["test_box"],
        mixed_box_groups=[],
        reference_box_label="test_box",
    )
    box_catalog = [BoxClassSpec(label="test_box", width_mm=100, depth_mm=100, height_mm=100)]
    calibration = calibrate(
        CalibrationRequest(
            baseline_capture_id="empty", baseline_capture=captures["empty"],
            pallets=[pallet], grid_mm=10,
        )
    )
    result = measure(
        MeasurementRequest(
            calibration=calibration.definition(),
            current_capture_id="current",
            current_capture=captures["current"],
            pallets=[pallet],
            box_catalog=box_catalog,
            grid_mm=10,
            occupied_height_mm=30,
            generate_debug_stages=True,
        )
    )

    assert len(result.pallets) == 1
    assert result.camera_runs[0].calibration_id == calibration.calibration_id
    assert result.pallets[0].method == "pallet_plane_2roi"
    assert result.pallets[0].volume_liters > 50
    assert result.pallets[0].box_combination is not None
    assert result.pallets[0].box_combination.solver_backend == "cp-sat"
    assert result.pallets[0].estimated_boxes == sum(
        result.pallets[0].box_combination.best.counts.values()
    )
    assert (tmp_path / result.pallets[0].plot_path).is_file()
    assert result.pallets[0].debug_stages_path is not None
    debug_html = (tmp_path / result.pallets[0].debug_stages_path).read_text(encoding="utf-8")
    assert "1 生点群" in debug_html
    assert "2 現在フレーム候補" in debug_html
    assert "6 最終体積" in debug_html
    assert "type:'mesh3d'" in debug_html
    assert "10mmセル柱状体積" in debug_html
    assert "高さカラーマップ" in debug_html
    assert "ポイントクラウド" in debug_html
    assert "背景＋処理対象を赤強調" in debug_html
    assert "表面点群" in debug_html
    assert "立体充填" in debug_html
    assert "debug-shape" in debug_html
    assert "debug_point_cloud.html" in debug_html
    assert "カメラ奥行きZ mm（小さいほど高い）" in debug_html
    assert debug_html.count("autorange:'reversed'") == 1
    assert 'src="/vendor/plotly/plotly.min.js"' in debug_html
    assert "cdn.plot.ly" not in debug_html
    pallet_dir = (tmp_path / result.pallets[0].plot_path).parent
    plot_html = (pallet_dir / "plot.html").read_text(encoding="utf-8")
    assert "10mmセルの柱状体積" in plot_html
    assert "周辺＋体積推定領域ポイントクラウド（Potree）" in plot_html
    assert "高さ充填ポイントクラウド（Potree）" in plot_html
    assert "volume.html" in plot_html
    assert "point_cloud.html" in plot_html
    assert "height_filled.html" in plot_html
    volume_html = (pallet_dir / "volume.html").read_text(encoding="utf-8")
    assert "最終柱状体積" in volume_html
    assert "type:'mesh3d'" in volume_html
    assert 'src="/vendor/plotly/plotly.min.js"' in volume_html
    assert "cdn.plot.ly" not in volume_html
    point_html = (pallet_dir / "point_cloud.html").read_text(encoding="utf-8")
    assert "Potree.Viewer" in point_html
    assert "potree/metadata.json" in point_html
    assert "周辺＋体積推定領域ポイントクラウド" in point_html
    assert 'activeAttributeName="rgba"' in point_html
    assert "/vendor/potree/build/potree/potree.js" in point_html
    assert (pallet_dir / "point_cloud.las").is_file()
    assert (pallet_dir / "potree" / "metadata.json").is_file()
    height_filled_html = (pallet_dir / "height_filled.html").read_text(encoding="utf-8")
    assert "高さ充填ポイントクラウド" in height_filled_html
    assert "height_filled/metadata.json" in height_filled_html
    assert "height-legend" in height_filled_html
    assert 'activeAttributeName="elevation"' in height_filled_html
    assert "elevationRange=[0," in height_filled_html
    assert (pallet_dir / "height_filled.las").is_file()
    assert (pallet_dir / "height_filled" / "metadata.json").is_file()
    debug_point_html = (pallet_dir / "debug_point_cloud.html").read_text(
        encoding="utf-8"
    )
    assert "段階別ポイントクラウド" in debug_point_html
    assert 'activeAttributeName="rgba"' in debug_point_html
    assert 'activeAttributeName="color"' in debug_point_html
    assert "表面点群" in debug_point_html
    assert "立体充填" in debug_point_html
    assert "背景＋処理対象を赤強調" in debug_point_html
    assert (pallet_dir / "debug_point_cloud" / "context" / "metadata.json").is_file()
    assert '"uses_context":true' in debug_point_html
    for stage in ("candidate", "projected", "grid", "corrected", "volume"):
        assert (pallet_dir / "debug_point_cloud" / stage / "metadata.json").is_file()
    assert (
        pallet_dir / "debug_point_cloud" / "grid_filled" / "metadata.json"
    ).is_file()
    assert (
        pallet_dir / "debug_point_cloud" / "corrected_filled" / "metadata.json"
    ).is_file()
    assert not (pallet_dir / "debug_point_cloud" / "volume_filled").exists()
    assert debug_point_html.count(
        '"solid_metadata":"debug_point_cloud/corrected_filled/metadata.json"'
    ) == 2
    assert debug_point_html.count('"solid_metadata":null') == 3


def test_monitor_measurement_can_skip_heavy_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    shape = (40, 40)
    intrinsics = RgbdIntrinsics(
        color=None,
        depth=StreamIntrinsics(width=40, height=40, fx=80, fy=80, cx=20, cy=20),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    captures = {
        capture_id: write_capture(
            tmp_path, capture_id, np.full(shape, 1000, np.float32), intrinsics
        )
        for capture_id in ("empty", "current")
    }
    pallet = PalletSettings(
        pallet_id=1,
        plane_roi=(0.2, 0.2, 0.8, 0.8),
    )
    calibration = calibrate(CalibrationRequest(
        baseline_capture_id="empty", baseline_capture=captures["empty"],
        pallets=[pallet], grid_mm=10,
    ))
    monkeypatch.setattr(
        engine_module,
        "load_rgb_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("監視測定でRGBを読み込んでいます")
        ),
    )
    result = measure(
        MeasurementRequest(
            calibration=calibration.definition(),
            current_capture_id="current",
            current_capture=captures["current"],
            pallets=[pallet],
            grid_mm=10,
            generate_artifacts=False,
        )
    )
    assert result.pallets[0].plot_path is None
    assert result.pallets[0].height_grid_path is None
    assert not (tmp_path / "measurements" / result.measurement_id).exists()


def test_prepared_runtime_measures_without_resending_fixed_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    prepared_runtime_registry.clear()
    shape = (40, 40)
    intrinsics = RgbdIntrinsics(
        color=None,
        depth=StreamIntrinsics(width=40, height=40, fx=80, fy=80, cx=20, cy=20),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    baseline = write_capture(
        tmp_path, "empty", np.full(shape, 1000, np.float32), intrinsics
    )
    current = write_capture(
        tmp_path, "current", np.full(shape, 900, np.float32), intrinsics
    )
    pallet = PalletSettings(pallet_id=1, plane_roi=(0.2, 0.2, 0.8, 0.8))
    calibration = calibrate(CalibrationRequest(
        baseline_capture_id="empty",
        baseline_capture=baseline,
        pallets=[pallet],
        grid_mm=10,
    ))
    prepared = prepared_runtime_registry.prepare(
        calibration.definition(),
        [pallet],
        default_box_catalog(),
        color_shape=shape,
        depth_shape=shape,
    )

    result = measure(MeasurementRequest(
        runtime_id=prepared.runtime_id,
        current_capture_id="current",
        current_capture=current,
        occupied_height_mm=30,
        generate_artifacts=False,
    ))

    assert result.camera_runs[0].calibration_id == calibration.calibration_id
    assert len(result.pallets) == 1


def test_new_method_rejects_capture_without_xyz_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    runtime_module.runtime_cache.clear()
    shape = (80, 80)
    intrinsics = RgbdIntrinsics(
        color=None,
        depth=StreamIntrinsics(width=80, height=80, fx=80, fy=80, cx=40, cy=40),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    captures = {}
    for capture_id in ("empty", "current"):
        captures[capture_id] = write_capture(
            tmp_path,
            capture_id,
            np.full(shape, 1000, np.float32),
            intrinsics,
            include_xyz=False,
        )
    pallet = PalletSettings(pallet_id=1, plane_roi=(0.2, 0.2, 0.8, 0.8))
    with pytest.raises(ValueError, match="XYZファイル"):
        calibrate(
            CalibrationRequest(
                baseline_capture_id="empty", baseline_capture=captures["empty"],
                pallets=[pallet], grid_mm=10,
            )
        )


def test_calibration_does_not_create_manifest_or_mask_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    shape = (80, 80)
    intrinsics = RgbdIntrinsics(
        color=None,
        depth=StreamIntrinsics(width=80, height=80, fx=80, fy=80, cx=40, cy=40),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    empty_capture = write_capture(
        tmp_path, "empty", np.full(shape, 1000, np.float32), intrinsics
    )
    pallet = PalletSettings(
        pallet_id=1,
        plane_roi=(0.2, 0.2, 0.8, 0.8),
    )
    request = CalibrationRequest(
        baseline_capture_id="empty", baseline_capture=empty_capture,
        pallets=[pallet], grid_mm=10,
    )
    result = calibrate(request)

    assert result.pallets[0].plane_inlier_count > 0
    assert not (tmp_path / "calibrations").exists()


def test_calibration_is_reused_and_current_3d_preprocessing_runs_once(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CARDBOARD_DATA_ROOT", str(tmp_path))
    shape = (120, 120)
    intrinsics = RgbdIntrinsics(
        color=None,
        depth=StreamIntrinsics(width=120, height=120, fx=100, fy=100, cx=60, cy=60),
        align_depth_to_color=False,
        point_cloud_sensor="depth",
    )
    captures = {
        capture_id: write_capture(
            tmp_path, capture_id, np.full(shape, 1000, np.float32), intrinsics
        )
        for capture_id in ("empty", "current")
    }
    pallets = [
        PalletSettings(
            pallet_id=1,
            plane_roi=(0.05, 0.2, 0.45, 0.8),
        ),
        PalletSettings(
            pallet_id=2,
            pallet_number=2,
            plane_roi=(0.55, 0.2, 0.95, 0.8),
        ),
    ]
    xyz_count = 0
    runtime_module.runtime_cache.clear()
    original_project = DepthProjector.project

    def counted_project(*args, **kwargs):
        nonlocal xyz_count
        xyz_count += 1
        return original_project(*args, **kwargs)

    monkeypatch.setattr(DepthProjector, "project", counted_project)
    calibration = calibrate(
        CalibrationRequest(
            baseline_capture_id="empty", baseline_capture=captures["empty"],
            pallets=pallets, grid_mm=10,
        )
    )
    assert xyz_count == 0
    xyz_count = 0
    monkeypatch.setattr(
        calibration_module,
        "fit_pallet_plane",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected refit")),
    )
    geometry_count = 0
    original_geometry = runtime_module.build_pallet_projection_geometry

    def counted_geometry(*args, **kwargs):
        nonlocal geometry_count
        geometry_count += 1
        return original_geometry(*args, **kwargs)

    monkeypatch.setattr(
        runtime_module, "build_pallet_projection_geometry", counted_geometry
    )
    normal_count = 0
    original_normals = engine_module.build_surface_normal_map

    def counted_normals(*args, **kwargs):
        nonlocal normal_count
        normal_count += 1
        return original_normals(*args, **kwargs)

    monkeypatch.setattr(engine_module, "build_surface_normal_map", counted_normals)
    result = measure(
        MeasurementRequest(
            calibration=calibration.definition(),
            current_capture_id="current",
            current_capture=captures["current"],
            pallets=pallets,
            grid_mm=10,
            generate_artifacts=False,
        )
    )
    assert len(result.pallets) == 2
    assert xyz_count == 0
    assert geometry_count == 2
    assert normal_count == 1

    cached_plan = planning_module.get_measurement_plan(
        runtime_module.runtime_cache.get(
            calibration.definition(), color_shape=shape, depth_shape=shape
        ),
        pallets,
        default_box_catalog(),
        color_shape=shape,
        depth_shape=shape,
    )

    repeated = measure(
        MeasurementRequest(
            calibration=calibration.definition(),
            current_capture_id="current",
            current_capture=captures["current"],
            pallets=pallets,
            grid_mm=10,
            generate_artifacts=False,
        )
    )
    assert len(repeated.pallets) == 2
    assert geometry_count == 2
    assert planning_module.get_measurement_plan(
        runtime_module.runtime_cache.get(
            calibration.definition(), color_shape=shape, depth_shape=shape
        ),
        pallets,
        default_box_catalog(),
        color_shape=shape,
        depth_shape=shape,
    ) is cached_plan
