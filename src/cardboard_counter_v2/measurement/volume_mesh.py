"""高さグリッドを表示用の柱状体積メッシュへ変換する。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VolumeMesh:
    """Plotlyなどの描画実装に依存しない三角形メッシュ。"""

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    i: np.ndarray
    j: np.ndarray
    k: np.ndarray


def build_height_grid_volume_mesh(
    height_grid: np.ndarray,
    region_mask: np.ndarray,
    *,
    minimum_u: float,
    minimum_v: float,
    cell_size_mm: float,
    minimum_side_step_mm: float = 5.0,
) -> VolumeMesh:
    """採用セルの上面と外壁・段差面を作り、体積として見える形にする。"""
    heights = np.asarray(height_grid, dtype=np.float32)
    region = np.asarray(region_mask, dtype=bool)
    if heights.ndim != 2 or region.shape != heights.shape:
        raise ValueError("高さグリッドと領域マスクの形が一致しません。")
    cell = float(cell_size_mm)
    if cell <= 0:
        raise ValueError("セルサイズは0より大きい必要があります。")

    active = region & np.isfinite(heights) & (heights > 0)
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []

    def add_quad(corners: tuple[tuple[float, float, float], ...]) -> None:
        start = len(vertices)
        vertices.extend(corners)
        triangles.extend(
            ((start, start + 1, start + 2), (start, start + 2, start + 3))
        )

    rows, columns = heights.shape
    side_step = max(float(minimum_side_step_mm), 0.0)
    for row, column in np.argwhere(active):
        height = float(heights[row, column])
        u0 = float(minimum_u) + float(column) * cell
        u1 = u0 + cell
        v0 = float(minimum_v) + float(row) * cell
        v1 = v0 + cell
        add_quad(
            ((u0, v0, height), (u1, v0, height), (u1, v1, height), (u0, v1, height))
        )

        neighbours = (
            (row, column - 1, ((u0, v1), (u0, v0))),
            (row, column + 1, ((u1, v0), (u1, v1))),
            (row - 1, column, ((u0, v0), (u1, v0))),
            (row + 1, column, ((u1, v1), (u0, v1))),
        )
        for neighbour_row, neighbour_column, ((a_u, a_v), (b_u, b_v)) in neighbours:
            neighbour_height = 0.0
            if (
                0 <= neighbour_row < rows
                and 0 <= neighbour_column < columns
                and active[neighbour_row, neighbour_column]
            ):
                neighbour_height = float(heights[neighbour_row, neighbour_column])
            if height - neighbour_height <= side_step:
                continue
            add_quad(
                (
                    (a_u, a_v, neighbour_height),
                    (b_u, b_v, neighbour_height),
                    (b_u, b_v, height),
                    (a_u, a_v, height),
                )
            )

    if not vertices:
        empty_float = np.empty(0, dtype=np.float32)
        empty_int = np.empty(0, dtype=np.int32)
        return VolumeMesh(empty_float, empty_float, empty_float, empty_int, empty_int, empty_int)
    vertex_array = np.asarray(vertices, dtype=np.float32)
    triangle_array = np.asarray(triangles, dtype=np.int32)
    return VolumeMesh(
        x=vertex_array[:, 0],
        y=vertex_array[:, 1],
        z=vertex_array[:, 2],
        i=triangle_array[:, 0],
        j=triangle_array[:, 1],
        k=triangle_array[:, 2],
    )
