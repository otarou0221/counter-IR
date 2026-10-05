import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import _robust_height_grid


def test_default_grid_keeps_two_point_cells_but_rejects_singletons() -> None:
    ix = np.array([0, 0, 1, 2, 2, 2])
    iy = np.zeros(6, dtype=np.int32)
    heights = np.array([220, 260, 900, 300, 340, 380], dtype=np.float32)
    pixels = np.array([10, 11, 12, 13, 14, 15])

    grid, observed, representative_pixels = _robust_height_grid(
        ix, iy, heights, pixels, shape=(1, 3)
    )

    np.testing.assert_array_equal(observed, [[True, False, True]])
    np.testing.assert_array_equal(grid, [[220, 0, 340]])
    np.testing.assert_array_equal(representative_pixels, [[10, -1, 14]])

    _, strict_observed, _ = _robust_height_grid(
        ix, iy, heights, pixels, shape=(1, 3), min_points=3
    )
    np.testing.assert_array_equal(strict_observed, [[False, False, True]])
