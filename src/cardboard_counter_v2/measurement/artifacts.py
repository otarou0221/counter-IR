"""手動診断時にだけ作る3Dプロットと中間配列。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import HeightGridDebugPoints
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.debug_point_cloud import DebugPointCloudBundle
from cardboard_counter_v2.measurement.height_filled_point_cloud import (
    build_height_filled_point_cloud,
)
from cardboard_counter_v2.measurement.plotly_html import (
    write_debug_stages_plot,
    write_height_plot,
)
from cardboard_counter_v2.measurement.point_cloud_view import RgbPointCloud
from cardboard_counter_v2.measurement.point_cloud_export import write_rgb_las
from cardboard_counter_v2.measurement.potree_adapter import convert_las_to_potree
from cardboard_counter_v2.measurement.potree_html import (
    write_artifact_index,
    write_debug_point_cloud_viewer,
    write_empty_point_cloud_viewer,
    write_potree_viewer,
)
from cardboard_counter_v2.measurement.volume_mesh import build_height_grid_volume_mesh


def save_measurement_artifacts(
    output_dir: Path,
    *,
    height_grid: np.ndarray,
    original_height_grid: np.ndarray,
    box_region: np.ndarray,
    observed_mask: np.ndarray,
    protrusion_mask: np.ndarray,
    point_cloud: RgbPointCloud | None,
    geometry: PalletProjectionGeometry,
    summary: dict[str, object],
    debug_points: HeightGridDebugPoints | None = None,
    debug_point_clouds: DebugPointCloudBundle | None = None,
) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    grid_path = output_dir / "height_grid.npz"
    plot_path = output_dir / "plot.html"
    volume_path = output_dir / "volume.html"
    point_cloud_path = output_dir / "point_cloud.html"
    height_filled_path = output_dir / "height_filled.html"
    np.savez_compressed(
        grid_path,
        height_mm=height_grid,
        original_height_mm=original_height_grid,
        box_region=box_region,
        observed_mask=observed_mask,
        protrusion_mask=protrusion_mask,
    )
    # 体積メッシュは診断成果物を要求した時だけ1回生成し、体積表示と段階表示で共有する。
    volume_mesh = build_height_grid_volume_mesh(
        height_grid,
        box_region,
        minimum_u=geometry.minimum_u,
        minimum_v=geometry.minimum_v,
        cell_size_mm=geometry.cell_size_mm,
    )
    write_height_plot(
        volume_path,
        height_grid=height_grid,
        original_height_grid=original_height_grid,
        box_region=box_region,
        protrusion_mask=protrusion_mask,
        geometry=geometry,
        volume_mesh=volume_mesh,
        summary=summary,
    )
    if point_cloud is None:
        raise ValueError("Potree表示に必要なRGB点群がありません")
    # 外部形式への書き出しと変換は、手動診断成果物を要求した時だけ各1回行う。
    source_las_path = output_dir / "point_cloud.las"
    potree_dir = output_dir / "potree"
    write_rgb_las(source_las_path, point_cloud.uvh, point_cloud.colors_rgb)
    convert_las_to_potree(source_las_path, potree_dir)
    write_potree_viewer(
        point_cloud_path,
        metadata_relative_url="potree/metadata.json",
        point_count=len(point_cloud.uvh),
        title="周辺＋体積推定領域ポイントクラウド",
        description=(
            "周辺は実画像色のまま表示し、体積推定へ採用した領域だけを"
            "パレット面からの高さで色分け"
        ),
        height_range_mm=(0.0, point_cloud.height_color_limit_mm)
        if point_cloud.highlighted_count
        else None,
        color_by_elevation=False,
    )
    # 解析済み高さだけから表示用の充填点群を作る。測定値や体積計算には戻さない。
    height_filled = build_height_filled_point_cloud(height_grid, box_region, geometry)
    if len(height_filled.uvh) == 0:
        write_empty_point_cloud_viewer(height_filled_path)
    else:
        height_filled_las_path = output_dir / "height_filled.las"
        height_filled_potree_dir = output_dir / "height_filled"
        write_rgb_las(
            height_filled_las_path,
            height_filled.uvh,
            height_filled.colors_rgb,
        )
        convert_las_to_potree(height_filled_las_path, height_filled_potree_dir)
        write_potree_viewer(
            height_filled_path,
            metadata_relative_url="height_filled/metadata.json",
            point_count=len(height_filled.uvh),
            title="高さ充填ポイントクラウド",
            description=(
                f"採用した{geometry.cell_size_mm:g}mmセルを"
                "パレット面から測定高まで表示用に充填。"
                f"縦方向の表示間隔は{height_filled.vertical_step_mm:g}mm"
            ),
            height_range_mm=(0.0, height_filled.maximum_height_mm),
            adaptive_point_size=False,
            point_size=3.0,
        )
    write_artifact_index(
        plot_path,
        summary=summary,
        cell_size_mm=geometry.cell_size_mm,
        volume_relative_url=volume_path.name,
        point_cloud_relative_url=point_cloud_path.name,
        height_filled_relative_url=height_filled_path.name,
    )
    debug_path: Path | None = None
    if debug_points is not None:
        if debug_point_clouds is None:
            raise ValueError("段階別Potree表示に必要な点群がありません")
        debug_cloud_path = output_dir / "debug_point_cloud.html"
        debug_cloud_dir = output_dir / "debug_point_cloud"
        context_metadata: str | None = None
        if len(debug_point_clouds.context.uvh):
            context_las = debug_cloud_dir / "context.las"
            context_output = debug_cloud_dir / "context"
            write_rgb_las(
                context_las,
                debug_point_clouds.context.uvh,
                debug_point_clouds.context.colors_rgb,
            )
            convert_las_to_potree(context_las, context_output)
            context_metadata = "debug_point_cloud/context/metadata.json"
        stage_payload: list[dict[str, object]] = []
        solid_metadata_by_key: dict[str, str | None] = {}
        for stage in debug_point_clouds.stages:
            metadata: str | None = None
            uses_context = stage.key == "raw" and context_metadata is not None
            if uses_context:
                metadata = context_metadata
            elif len(stage.cloud.uvh):
                stage_las = debug_cloud_dir / f"{stage.key}.las"
                stage_output = debug_cloud_dir / stage.key
                write_rgb_las(stage_las, stage.cloud.uvh, stage.cloud.colors_rgb)
                convert_las_to_potree(stage_las, stage_output)
                metadata = f"debug_point_cloud/{stage.key}/metadata.json"
            solid_metadata: str | None = None
            solid_point_count = 0
            if stage.solid_cloud is not None and stage.solid_key is not None:
                solid_point_count = len(stage.solid_cloud.uvh)
                if stage.solid_key in solid_metadata_by_key:
                    solid_metadata = solid_metadata_by_key[stage.solid_key]
                elif solid_point_count:
                    solid_las = debug_cloud_dir / f"{stage.solid_key}.las"
                    solid_output = debug_cloud_dir / stage.solid_key
                    write_rgb_las(
                        solid_las,
                        stage.solid_cloud.uvh,
                        stage.solid_cloud.colors_rgb,
                    )
                    convert_las_to_potree(solid_las, solid_output)
                    solid_metadata = (
                        f"debug_point_cloud/{stage.solid_key}/metadata.json"
                    )
                solid_metadata_by_key[stage.solid_key] = solid_metadata
            stage_payload.append(
                {
                    "key": stage.key,
                    "title": stage.title,
                    "metadata": metadata,
                    "point_count": len(stage.cloud.uvh),
                    "uses_context": uses_context,
                    "solid_metadata": solid_metadata,
                    "solid_point_count": solid_point_count,
                    "solid_vertical_step_mm": stage.solid_vertical_step_mm,
                }
            )
        write_debug_point_cloud_viewer(
            debug_cloud_path,
            context_metadata_relative_url=context_metadata,
            context_point_count=len(debug_point_clouds.context.uvh),
            stages=stage_payload,
        )
        debug_path = output_dir / "debug_stages.html"
        write_debug_stages_plot(
            debug_path,
            debug_points=debug_points,
            height_grid=height_grid,
            original_height_grid=original_height_grid,
            box_region=box_region,
            protrusion_mask=protrusion_mask,
            geometry=geometry,
            volume_mesh=volume_mesh,
            summary=summary,
            point_cloud_relative_url=debug_cloud_path.name,
        )
    return grid_path, plot_path, debug_path
