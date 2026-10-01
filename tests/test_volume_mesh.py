import numpy as np

from cardboard_counter_v2.measurement.volume_mesh import build_height_grid_volume_mesh


def test_equal_adjacent_columns_share_their_internal_wall() -> None:
    mesh = build_height_grid_volume_mesh(
        np.array([[100.0, 100.0]], dtype=np.float32),
        np.ones((1, 2), dtype=bool),
        minimum_u=10.0,
        minimum_v=20.0,
        cell_size_mm=10.0,
    )

    # 上面2枚と外壁6枚。2セル間の重複壁は作らない。
    assert len(mesh.i) == 16
    assert float(mesh.x.min()) == 10.0
    assert float(mesh.x.max()) == 30.0
    assert float(mesh.y.min()) == 20.0
    assert float(mesh.y.max()) == 30.0
    assert float(mesh.z.min()) == 0.0
    assert float(mesh.z.max()) == 100.0


def test_height_step_adds_only_the_taller_column_side() -> None:
    mesh = build_height_grid_volume_mesh(
        np.array([[100.0, 150.0]], dtype=np.float32),
        np.ones((1, 2), dtype=bool),
        minimum_u=0.0,
        minimum_v=0.0,
        cell_size_mm=10.0,
    )

    # 同じ外形に加え、高いセル側の50mm段差が1面増える。
    assert len(mesh.i) == 18
    assert float(mesh.z.max()) == 150.0


def test_empty_region_returns_empty_mesh() -> None:
    mesh = build_height_grid_volume_mesh(
        np.zeros((2, 2), dtype=np.float32),
        np.zeros((2, 2), dtype=bool),
        minimum_u=0.0,
        minimum_v=0.0,
        cell_size_mm=10.0,
    )

    assert mesh.x.size == 0
    assert mesh.i.size == 0
