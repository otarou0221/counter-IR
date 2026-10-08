import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import (
    SurfaceNormalMap,
    height_grid_from_frame,
)
from cardboard_counter_v2.measurement.core.high_surface_filter import (
    HighSurfaceFilter,
    small_high_surface_mask,
)
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane


def test_narrow_background_is_selected_but_full_six_tier_box_top_is_kept() -> None:
    heights = np.zeros((80, 80), dtype=np.float32)
    heights[5:8, 5:15] = 1_800.0  # 細い天井・梁の投影
    heights[20:41, 20:49] = 1_980.0  # 長岡金型570×410mmの6段目
    rule = HighSurfaceFilter.for_box_footprints(((450, 400), (520, 330)))

    discarded = small_high_surface_mask(
        heights, heights > 0, cell_size_mm=20.0, rule=rule,
    )

    assert np.all(discarded[5:8, 5:15])
    assert not np.any(discarded[20:41, 20:49])


def test_high_point_removal_recovers_lower_points_in_same_cell() -> None:
    xyz = np.zeros((6, 6, 3), dtype=np.float32)
    source_pixels = np.array([0, 1, 2, 3, 4, 5])
    xyz.reshape(-1, 3)[source_pixels] = (10.0, 10.0, 1_400.0)
    xyz.reshape(-1, 3)[source_pixels[:2], 2] = 2_500.0
    point_valid = np.zeros((6, 6), dtype=bool)
    point_valid.reshape(-1)[source_pixels] = True
    vectors = np.zeros((6, 6, 3), dtype=np.float32)
    vectors.reshape(-1, 3)[source_pixels] = (0.0, 0.0, -1.0)
    normals = SurfaceNormalMap(vectors, point_valid, point_valid)
    plane = PalletPlane(
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        offset=3_000.0, fit_rmse_mm=0.0, inlier_count=6,
    )
    geometry = PalletProjectionGeometry(
        plane=plane,
        origin_xyz=np.array([0.0, 0.0, 3_000.0], dtype=np.float32),
        basis_u=np.array([1.0, 0.0, 0.0], dtype=np.float32),
        basis_v=np.array([0.0, 1.0, 0.0], dtype=np.float32),
        minimum_u=0.0, minimum_v=0.0,
        width=2, height=2,
        polygon_uv=np.array([[0, 0], [40, 0], [40, 40], [0, 40]], dtype=np.float32),
        pallet_mask=np.ones((2, 2), dtype=bool), cell_size_mm=20.0,
    )

    original = height_grid_from_frame(xyz, geometry=geometry, surface_normals=normals)
    filtered = height_grid_from_frame(
        xyz,
        geometry=geometry,
        surface_normals=normals,
        high_surface_filter=HighSurfaceFilter.for_box_footprints(((450, 400),)),
        collect_debug=True,
    )

    assert original.height_grid[0, 0] == 1_600.0
    assert filtered.height_grid[0, 0] == 500.0
    assert filtered.observed_mask[0, 0]
    assert filtered.debug_points is not None
    assert len(filtered.debug_points.projected_uvh) == 2
    assert np.all(filtered.debug_points.projected_uvh[:, 2] == 500.0)
