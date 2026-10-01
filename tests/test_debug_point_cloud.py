import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import HeightGridDebugPoints
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane
from cardboard_counter_v2.measurement.debug_point_cloud import (
    build_debug_point_cloud_bundle,
)
from cardboard_counter_v2.measurement.point_cloud_view import ProjectedPointCloud


def test_debug_bundle_keeps_rgb_and_builds_six_processing_stages() -> None:
    geometry = PalletProjectionGeometry(
        plane=PalletPlane(
            normal=np.array([0, 0, 1], np.float32),
            offset=0.0,
            fit_rmse_mm=1.0,
            inlier_count=10,
        ),
        origin_xyz=np.zeros(3, np.float32),
        basis_u=np.array([1, 0, 0], np.float32),
        basis_v=np.array([0, 1, 0], np.float32),
        minimum_u=0.0,
        minimum_v=0.0,
        width=2,
        height=2,
        polygon_uv=np.array([[0, 0], [20, 0], [20, 20], [0, 20]], np.float32),
        pallet_mask=np.ones((2, 2), bool),
        cell_size_mm=10.0,
    )
    rgb = np.array([[[10, 20, 30], [40, 50, 60], [70, 80, 90]]], np.uint8)
    debug = HeightGridDebugPoints(
        raw_xyz=np.array([[5, 5, 50], [15, 5, 40], [25, 5, 30]], np.float32),
        candidate_xyz=np.array([[5, 5, 50], [15, 5, 40]], np.float32),
        candidate_pixel_indices=np.array([0, 1]),
        projected_uvh=np.array([[5, 5, 50]], np.float32),
        projected_pixel_indices=np.array([0]),
        grid_pixel_indices=np.array([[0, -1], [-1, -1]]),
    )
    context = ProjectedPointCloud(
        uvh=np.array([[5, 5, 50], [15, 5, 40], [25, 5, 30]], np.float32),
        pixel_indices=np.array([0, 1, 2]),
    )

    bundle = build_debug_point_cloud_bundle(
        debug_points=debug,
        context_points=context,
        rgb_image=rgb,
        original_height_grid=np.array([[120, 0], [0, 0]], np.float32),
        height_grid=np.array([[100, 0], [0, 0]], np.float32),
        box_region=np.array([[True, False], [False, False]]),
        geometry=geometry,
    )

    assert len(bundle.stages) == 6
    assert [stage.key for stage in bundle.stages] == [
        "raw",
        "candidate",
        "projected",
        "grid",
        "corrected",
        "volume",
    ]
    np.testing.assert_array_equal(bundle.context.colors_rgb, rgb.reshape(-1, 3))
    np.testing.assert_array_equal(bundle.stages[2].cloud.colors_rgb, [[10, 20, 30]])
    np.testing.assert_allclose(bundle.stages[3].cloud.uvh, [[5, 5, 120]])
    np.testing.assert_allclose(bundle.stages[4].cloud.uvh, [[5, 5, 100]])
    np.testing.assert_array_equal(bundle.stages[5].cloud.colors_rgb, [[10, 20, 30]])
    assert all(stage.solid_cloud is None for stage in bundle.stages[:3])
    np.testing.assert_allclose(
        bundle.stages[3].solid_cloud.uvh[:, 2],
        [0, 20, 40, 60, 80, 100, 120],
    )
    np.testing.assert_allclose(
        bundle.stages[4].solid_cloud.uvh[:, 2],
        [0, 20, 40, 60, 80, 100],
    )
    np.testing.assert_array_equal(
        bundle.stages[3].solid_cloud.colors_rgb,
        np.tile([10, 20, 30], (7, 1)),
    )
    assert bundle.stages[4].solid_cloud is bundle.stages[5].solid_cloud
    assert bundle.stages[4].solid_key == bundle.stages[5].solid_key
