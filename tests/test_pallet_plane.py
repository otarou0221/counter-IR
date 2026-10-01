import cv2
import numpy as np
import pytest

from cardboard_counter_v2.common.rgbd import RgbdIntrinsics, StreamIntrinsics
from cardboard_counter_v2.measurement.core.component_geometry import oriented_mask_spans
from cardboard_counter_v2.measurement.core.height_grid import (
    build_surface_normal_map,
    height_grid_from_frame,
)
from cardboard_counter_v2.measurement.core.models import RegionOfInterest
from cardboard_counter_v2.measurement.core.pallet_geometry import (
    PalletProjectionGeometry,
    build_pallet_projection_geometry,
)
from cardboard_counter_v2.measurement.core.plane_estimation import PalletPlane
from cardboard_counter_v2.measurement.core.protrusion_filter import (
    _highest_supported_surrounding_level,
    suppress_small_height_protrusions,
)


def test_floor_polygon_is_lifted_in_3d_without_reprojecting_pixel_rays() -> None:
    floor_plane = PalletPlane(
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        offset=1_000.0,
        fit_rmse_mm=1.0,
        inlier_count=1_000,
    )
    intrinsics = RgbdIntrinsics(
        color=StreamIntrinsics(
            width=120, height=120, fx=100, fy=100, cx=60, cy=60,
        ),
        depth=None,
        align_depth_to_color=True,
        point_cloud_sensor="color",
    )

    geometry = build_pallet_projection_geometry(
        RegionOfInterest(40, 40, 80, 80),
        color_shape=(120, 120),
        depth_shape=(120, 120),
        camera_intrinsics=intrinsics,
        reference_plane=floor_plane,
        surface_offset_mm=150.0,
        cell_size_mm=10.0,
    )

    # 床の左上は(-200,-200,1000)。視線へ再投影するとx=-170になるが、
    # 正しい方式ではx/yを保ったまま床法線方向へ150mm持ち上げる。
    np.testing.assert_allclose(
        geometry.origin_xyz,
        np.array([-200.0, -200.0, 850.0], dtype=np.float32),
    )
    assert geometry.plane.offset == pytest.approx(850.0)

def test_height_grid_has_no_box_layer_height_ceiling() -> None:
    """箱段数から作る上限を使わず、物理外周内の高い面も採用する。"""
    rows, columns = np.indices((5, 5), dtype=np.float32)
    xyz = np.dstack((columns, -rows, np.full((5, 5), 100.0, np.float32)))
    plane = PalletPlane(
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        offset=2_000.0,
        fit_rmse_mm=0.0,
        inlier_count=25,
    )
    geometry = PalletProjectionGeometry(
        plane=plane,
        origin_xyz=np.array([0.0, 0.0, 2_000.0], dtype=np.float32),
        basis_u=np.array([1.0, 0.0, 0.0], dtype=np.float32),
        basis_v=np.array([0.0, -1.0, 0.0], dtype=np.float32),
        minimum_u=0.0,
        minimum_v=0.0,
        width=1,
        height=1,
        polygon_uv=np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32),
        pallet_mask=np.ones((1, 1), dtype=bool),
        cell_size_mm=10.0,
    )

    result = height_grid_from_frame(
        xyz,
        geometry=geometry,
        surface_normals=build_surface_normal_map(xyz),
    )

    assert result.observed_mask[0, 0]
    assert result.height_grid[0, 0] == pytest.approx(1_900.0)


def test_folded_sign_is_lowered_but_box_top_is_kept() -> None:
    heights = np.full((100, 100), 700.0, dtype=np.float32)
    heights[20:61, 20:77] = 1_035.0  # 570 x 410mmの箱
    heights[30:48, 32:62] = 1_185.0  # 300 x 180mmの看板

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=570.0,
        box_depth_mm=410.0,
    )

    assert result.component_count == 1
    assert result.suppressed_cells > 0
    assert np.median(result.height_grid[32:46, 35:59]) == 1_035
    assert result.height_grid[25, 25] == 1_035


def test_230_by_470mm_folded_sign_is_lowered() -> None:
    heights = np.full((100, 100), 1_035.0, dtype=np.float32)
    sign = np.zeros(heights.shape, dtype=np.uint8)
    cv2.rectangle(sign, (25, 25), (69, 45), 1, 2)
    heights[sign.astype(bool)] = 1_185.0

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=570.0,
        box_depth_mm=410.0,
    )

    assert oriented_mask_spans(sign, cell_size_mm=10.0) == (230.0, 470.0)
    assert result.component_count == 1
    assert np.median(result.height_grid[sign.astype(bool)]) == 1_035.0


def test_isolated_fixed_sign_is_lowered_to_pallet_surface() -> None:
    heights = np.zeros((100, 100), dtype=np.float32)
    heights[30:47, 25:64] = 110.0  # 実測投影170 x 390mmの固定看板

    result = suppress_small_height_protrusions(
        heights,
        heights > 0,
        cell_size_mm=10.0,
        box_width_mm=570.0,
        box_depth_mm=410.0,
    )

    assert result.component_count == 1
    assert result.suppressed_volume_mm3 == pytest.approx(7_293_000.0)
    assert not np.any(result.height_grid)


def test_isolated_registered_box_is_not_mistaken_for_fixed_sign() -> None:
    heights = np.zeros((100, 100), dtype=np.float32)
    heights[25:65, 20:65] = 240.0  # 再生250P相当 400 x 450mm

    result = suppress_small_height_protrusions(
        heights,
        heights > 0,
        cell_size_mm=10.0,
        box_width_mm=450.0,
        box_depth_mm=400.0,
    )

    assert result.component_count == 0
    np.testing.assert_array_equal(result.height_grid, heights)


@pytest.mark.parametrize(
    ("box_width_mm", "box_depth_mm"),
    [(570.0, 410.0), (450.0, 400.0), (520.0, 330.0)],
)
def test_legitimate_full_box_step_is_not_lowered(
    box_width_mm: float,
    box_depth_mm: float,
) -> None:
    heights = np.full((100, 100), 700.0, dtype=np.float32)
    width_cells = int(round(box_width_mm / 10.0))
    depth_cells = int(round(box_depth_mm / 10.0))
    heights[20 : 20 + depth_cells, 20 : 20 + width_cells] = 1_035.0

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=box_width_mm,
        box_depth_mm=box_depth_mm,
    )

    assert result.component_count == 0
    np.testing.assert_array_equal(result.height_grid, heights)


def test_diagonal_folded_sign_on_450mm_box_is_lowered() -> None:
    heights = np.full((100, 100), 700.0, dtype=np.float32)
    heights[20:60, 20:65] = 940.0
    sign = np.zeros(heights.shape, dtype=np.uint8)
    corners = cv2.boxPoints(((43.0, 40.0), (38.0, 13.0), -25.0))
    cv2.fillPoly(sign, [np.round(corners).astype(np.int32)], 1)
    heights[sign.astype(bool)] = 1_090.0

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=450.0,
        box_depth_mm=400.0,
    )

    assert result.component_count == 1
    assert result.suppressed_cells > 0
    assert np.median(result.height_grid[sign.astype(bool)]) == 940
    assert result.height_grid[25, 25] == 940


def test_diagonal_full_box_step_is_not_lowered() -> None:
    heights = np.full((120, 120), 700.0, dtype=np.float32)
    box = np.zeros(heights.shape, dtype=np.uint8)
    corners = cv2.boxPoints(((60.0, 60.0), (45.0, 40.0), -25.0))
    cv2.fillPoly(box, [np.round(corners).astype(np.int32)], 1)
    heights[box.astype(bool)] = 940.0

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=450.0,
        box_depth_mm=400.0,
    )

    assert result.component_count == 0
    np.testing.assert_array_equal(result.height_grid, heights)


def test_oriented_spans_follow_component_rotation() -> None:
    mask = np.zeros((80, 80), dtype=np.uint8)
    corners = cv2.boxPoints(((40.0, 40.0), (38.0, 13.0), -25.0))
    cv2.fillPoly(mask, [np.round(corners).astype(np.int32)], 1)

    short_span, long_span = oriented_mask_spans(mask, cell_size_mm=10.0)

    assert 120.0 <= short_span <= 170.0
    assert 380.0 <= long_span <= 420.0


def test_long_folded_sign_on_450mm_box_is_lowered() -> None:
    heights = np.full((100, 100), 700.0, dtype=np.float32)
    heights[20:61, 20:66] = 940.0  # 450 x 400mm級の箱面
    heights[32:46, 23:63] = 1_090.0  # 400 x 140mmの細長い看板

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=450.0,
        box_depth_mm=400.0,
    )

    assert result.component_count == 1
    assert result.suppressed_cells > 0
    assert np.median(result.height_grid[34:44, 26:60]) == 940
    assert result.height_grid[25, 25] == 940


def test_surrounding_level_ignores_an_adjacent_higher_box_layer() -> None:
    heights = np.full((80, 80), 500.0, dtype=np.float32)
    candidate = np.zeros(heights.shape, dtype=bool)
    candidate[30:45, 28:52] = True
    heights[candidate] = 650.0
    heights[25:50, 55:70] = 740.0

    level = _highest_supported_surrounding_level(
        heights,
        candidate,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
    )

    assert level == 500.0


def test_wide_non_elongated_box_step_is_not_lowered() -> None:
    heights = np.full((100, 100), 700.0, dtype=np.float32)
    heights[30:60, 30:70] = 940.0  # 400 x 300mmで看板ほど細長くない

    result = suppress_small_height_protrusions(
        heights,
        np.ones(heights.shape, dtype=bool),
        cell_size_mm=10.0,
        box_width_mm=450.0,
        box_depth_mm=400.0,
    )

    assert result.component_count == 0
    np.testing.assert_array_equal(result.height_grid, heights)


def test_boundary_wall_ribbon_is_lowered_but_box_beneath_is_kept() -> None:
    heights = np.zeros((100, 100), dtype=np.float32)
    heights[40:100, 20:77] = 335.0
    heights[98:100, 28:69] = 1_000.0

    result = suppress_small_height_protrusions(
        heights,
        heights > 0,
        cell_size_mm=10.0,
        box_width_mm=570.0,
        box_depth_mm=410.0,
    )

    assert result.component_count > 0
    assert np.median(result.height_grid[98:100, 28:69]) < 500
    assert result.height_grid[80, 40] == 335


def test_full_box_top_touching_boundary_is_not_lowered() -> None:
    heights = np.zeros((100, 100), dtype=np.float32)
    heights[59:100, 20:77] = 335.0

    result = suppress_small_height_protrusions(
        heights,
        heights > 0,
        cell_size_mm=10.0,
        box_width_mm=570.0,
        box_depth_mm=410.0,
    )

    assert result.component_count == 0
    np.testing.assert_array_equal(result.height_grid, heights)
