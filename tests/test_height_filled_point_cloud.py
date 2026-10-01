import numpy as np

from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane
from cardboard_counter_v2.measurement.height_filled_point_cloud import (
    build_height_filled_geometry,
    build_height_filled_point_cloud,
)
from cardboard_counter_v2.measurement.height_palette import (
    height_colors,
    robust_height_color_limit,
)


def geometry(shape: tuple[int, int]) -> PalletProjectionGeometry:
    return PalletProjectionGeometry(
        plane=PalletPlane(
            normal=np.array([0, 0, 1], np.float32),
            offset=-1_000.0,
            fit_rmse_mm=1.0,
            inlier_count=100,
        ),
        origin_xyz=np.zeros(3, np.float32),
        basis_u=np.array([1, 0, 0], np.float32),
        basis_v=np.array([0, 1, 0], np.float32),
        minimum_u=-10.0,
        minimum_v=-20.0,
        width=shape[1],
        height=shape[0],
        polygon_uv=np.zeros((4, 2), np.float32),
        pallet_mask=np.ones(shape, bool),
        cell_size_mm=10.0,
    )


def test_fills_each_box_cell_from_pallet_plane_to_measured_height() -> None:
    grid = np.array([[0.0, 45.0], [20.0, 80.0]], np.float32)
    region = np.array([[False, True], [False, False]])

    cloud = build_height_filled_point_cloud(grid, region, geometry(grid.shape))

    np.testing.assert_allclose(cloud.uvh[:, 0], 5.0)
    np.testing.assert_allclose(cloud.uvh[:, 1], -15.0)
    np.testing.assert_allclose(cloud.uvh[:, 2], [0.0, 20.0, 40.0, 45.0])
    assert cloud.maximum_height_mm == 45.0
    assert cloud.colors_rgb.shape == cloud.uvh.shape
    assert not np.array_equal(cloud.colors_rgb[0], cloud.colors_rgb[-1])


def test_filled_geometry_keeps_source_cell_for_every_vertical_point() -> None:
    grid = np.array([[0.0, 45.0], [25.0, 0.0]], np.float32)
    region = grid > 0

    filled = build_height_filled_geometry(grid, region, geometry(grid.shape))

    first_cell = (filled.source_rows == 0) & (filled.source_columns == 1)
    second_cell = (filled.source_rows == 1) & (filled.source_columns == 0)
    np.testing.assert_allclose(filled.uvh[first_cell, 2], [0.0, 20.0, 40.0, 45.0])
    np.testing.assert_allclose(filled.uvh[second_cell, 2], [0.0, 20.0, 25.0])
    assert np.count_nonzero(first_cell) == 4
    assert np.count_nonzero(second_cell) == 3


def test_increases_vertical_step_to_limit_display_points() -> None:
    grid = np.full((2, 2), 100.0, np.float32)
    cloud = build_height_filled_point_cloud(
        grid,
        np.ones_like(grid, bool),
        geometry(grid.shape),
        vertical_step_mm=10.0,
        maximum_points=20,
    )

    assert cloud.vertical_step_mm > 10.0
    assert len(cloud.uvh) <= 24  # 各セルの上面を必ず残すため、少数の超過は許容する。


def test_height_colors_change_from_gray_to_red() -> None:
    colors = height_colors(np.array([0.0, 50.0, 100.0]), maximum_height_mm=100.0)
    np.testing.assert_array_equal(colors[0], [221, 221, 221])
    np.testing.assert_array_equal(colors[-1], [184, 0, 31])
    assert not np.array_equal(colors[0], colors[1])


def test_height_color_limit_ignores_isolated_high_outlier() -> None:
    heights = np.append(np.full(99, 1_000.0, np.float32), 2_000.0)

    assert robust_height_color_limit(heights) == 1_000.0


def test_empty_box_region_returns_empty_display_cloud() -> None:
    grid = np.zeros((2, 2), np.float32)
    cloud = build_height_filled_point_cloud(
        grid, np.zeros_like(grid, bool), geometry(grid.shape)
    )

    assert cloud.uvh.shape == (0, 3)
    assert cloud.colors_rgb.shape == (0, 3)
    assert cloud.maximum_height_mm == 0.0
