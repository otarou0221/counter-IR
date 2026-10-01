import numpy as np

from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane
from cardboard_counter_v2.measurement.point_cloud_view import (
    ProjectedPointCloud,
    build_scene_point_cloud_source,
    colorize_measurement_point_cloud,
    project_scene_point_cloud_for_view,
    sample_projected_point_cloud,
)


def geometry() -> PalletProjectionGeometry:
    return PalletProjectionGeometry(
        plane=PalletPlane(
            normal=np.array([0, 0, 1], np.float32),
            offset=0.0,
            fit_rmse_mm=1.0,
            inlier_count=100,
        ),
        origin_xyz=np.zeros(3, np.float32),
        basis_u=np.array([1, 0, 0], np.float32),
        basis_v=np.array([0, 1, 0], np.float32),
        minimum_u=0.0,
        minimum_v=0.0,
        width=2,
        height=2,
        polygon_uv=np.zeros((4, 2), np.float32),
        pallet_mask=np.ones((2, 2), bool),
        cell_size_mm=10.0,
    )


def test_rgb_colors_follow_original_aligned_pixel_indices() -> None:
    rgb = np.array(
        [
            [[255, 0, 0], [0, 255, 0]],
            [[0, 0, 255], [255, 255, 255]],
        ],
        dtype=np.uint8,
    )
    points = ProjectedPointCloud(
        uvh=np.array([[10, 20, 30], [40, 50, 60]], dtype=np.float32),
        pixel_indices=np.array([2, 1], dtype=np.int64),
    )

    result = colorize_measurement_point_cloud(
        points,
        rgb,
        height_grid=np.array([[30.0, 0.0], [0.0, 0.0]], np.float32),
        box_region=np.array([[True, False], [False, False]]),
        geometry=geometry(),
    )

    np.testing.assert_array_equal(result.uvh, points.uvh)
    np.testing.assert_array_equal(
        result.colors_rgb,
        np.array([[0, 0, 255], [0, 255, 0]], dtype=np.uint8),
    )


def test_colors_only_points_inside_estimated_volume() -> None:
    rgb = np.full((1, 3, 3), [10, 20, 30], dtype=np.uint8)
    points = ProjectedPointCloud(
        uvh=np.array([[5, 5, 40], [15, 5, 40], [5, 5, 200]], np.float32),
        pixel_indices=np.array([0, 1, 2], np.int64),
    )

    result = colorize_measurement_point_cloud(
        points,
        rgb,
        height_grid=np.array([[100.0, 100.0], [0.0, 0.0]], np.float32),
        box_region=np.array([[True, False], [False, False]]),
        geometry=geometry(),
    )

    assert result.highlighted_count == 1
    assert result.height_color_limit_mm == 100.0
    assert not np.array_equal(result.colors_rgb[0], rgb[0, 0])
    np.testing.assert_array_equal(result.colors_rgb[1:], rgb[0, 1:])


def test_scene_projection_keeps_context_outside_pallet() -> None:
    xyz = np.array([[[5, 5, 40], [25, 5, 50], [400, 5, 60]]], np.float32)

    source = build_scene_point_cloud_source(xyz, np.ones((1, 3), bool))
    result = project_scene_point_cloud_for_view(
        source,
        geometry(),
        context_margin_ratio=0.0,
        minimum_context_margin_mm=20.0,
    )

    np.testing.assert_array_equal(result.pixel_indices, [0, 1])
    np.testing.assert_allclose(result.uvh, [[5, 5, 40], [25, 5, 50]])


def test_scene_projection_does_not_require_surface_normal_filter() -> None:
    """診断表示は測定用の上面法線がない側面・周辺点も残す。"""
    rows, columns = np.indices((2, 2), dtype=np.float32)
    xyz = np.dstack((columns + 1, rows + 1, np.full((2, 2), 40, np.float32)))

    source = build_scene_point_cloud_source(xyz, np.ones((2, 2), bool))
    result = project_scene_point_cloud_for_view(
        source,
        geometry(),
    )

    assert len(result.uvh) == 4


def test_point_cloud_sampling_keeps_position_and_pixel_pairs() -> None:
    uvh = np.arange(30, dtype=np.float32).reshape(10, 3)
    indices = np.arange(100, 110, dtype=np.int64)

    result = sample_projected_point_cloud(uvh, indices, maximum=4)

    np.testing.assert_array_equal(result.uvh, uvh[::3])
    np.testing.assert_array_equal(result.pixel_indices, indices[::3])
