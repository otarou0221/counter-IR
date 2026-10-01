"""RGB点群を外部ビューアへ渡せる標準LASファイルへ書き出す。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import struct

import numpy as np


LAS_HEADER_SIZE = 227
LAS_POINT_FORMAT = 2
LAS_POINT_RECORD_SIZE = 26
MILLIMETERS_PER_METER = 1_000.0
LAS_SCALE_METERS = 0.001


def write_rgb_las(
    path: Path,
    coordinates_mm: np.ndarray,
    colors_rgb: np.ndarray,
) -> None:
    """Z-upのXYZ(mm)とRGBをLAS 1.2（座標単位m）で保存する。"""
    coordinates_mm = np.asarray(coordinates_mm, dtype=np.float64)
    colors = np.asarray(colors_rgb, dtype=np.uint8)
    if coordinates_mm.ndim != 2 or coordinates_mm.shape[1] != 3:
        raise ValueError("点群座標は(N, 3)である必要があります")
    if colors.shape != coordinates_mm.shape:
        raise ValueError("点群座標とRGBの形状が一致しません")
    if len(coordinates_mm) == 0:
        raise ValueError("空の点群はLASへ書き出せません")
    if not np.isfinite(coordinates_mm).all():
        raise ValueError("点群座標に非有限値が含まれています")

    coordinates_m = coordinates_mm / MILLIMETERS_PER_METER
    offsets = coordinates_m.min(axis=0)
    integer_coordinates = np.rint(
        (coordinates_m - offsets) / LAS_SCALE_METERS
    ).astype(np.int64)
    if np.any(integer_coordinates > np.iinfo(np.int32).max):
        raise ValueError("点群の座標範囲がLAS 1.2の上限を超えています")
    # ヘッダー境界も量子化後の格納値から作り、丸めで点が境界外になるのを防ぐ。
    stored_coordinates_m = integer_coordinates * LAS_SCALE_METERS + offsets

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(
            _las_header(
                point_count=len(coordinates_m),
                minimum=stored_coordinates_m.min(axis=0),
                maximum=stored_coordinates_m.max(axis=0),
                offsets=offsets,
            )
        )
        color_16bit = colors.astype(np.uint16) * 257
        for coordinate, color in zip(integer_coordinates, color_16bit, strict=True):
            stream.write(
                struct.pack(
                    "<iiiHBBbBHHHH",
                    int(coordinate[0]),
                    int(coordinate[1]),
                    int(coordinate[2]),
                    0,  # intensity
                    0b001001,  # return 1 of 1
                    1,  # unclassified
                    0,  # scan angle rank
                    0,  # user data
                    0,  # point source id
                    int(color[0]),
                    int(color[1]),
                    int(color[2]),
                )
            )


def _las_header(
    *,
    point_count: int,
    minimum: np.ndarray,
    maximum: np.ndarray,
    offsets: np.ndarray,
) -> bytes:
    if point_count > np.iinfo(np.uint32).max:
        raise ValueError("LAS 1.2で保存できる点数を超えています")
    now = datetime.now().astimezone()
    header = bytearray(LAS_HEADER_SIZE)
    struct.pack_into("<4s", header, 0, b"LASF")
    struct.pack_into("<BB", header, 24, 1, 2)
    header[26:58] = _fixed_ascii("Cardboard Counter v2", 32)
    header[58:90] = _fixed_ascii("cardboard-counter-v2", 32)
    struct.pack_into("<HH", header, 90, int(now.strftime("%j")), now.year)
    struct.pack_into("<HI", header, 94, LAS_HEADER_SIZE, LAS_HEADER_SIZE)
    struct.pack_into("<I", header, 100, 0)  # VLR count
    struct.pack_into("<BH", header, 104, LAS_POINT_FORMAT, LAS_POINT_RECORD_SIZE)
    struct.pack_into("<I", header, 107, point_count)
    struct.pack_into("<5I", header, 111, point_count, 0, 0, 0, 0)
    struct.pack_into(
        "<3d3d",
        header,
        131,
        LAS_SCALE_METERS,
        LAS_SCALE_METERS,
        LAS_SCALE_METERS,
        float(offsets[0]),
        float(offsets[1]),
        float(offsets[2]),
    )
    struct.pack_into(
        "<6d",
        header,
        179,
        float(maximum[0]),
        float(minimum[0]),
        float(maximum[1]),
        float(minimum[1]),
        float(maximum[2]),
        float(minimum[2]),
    )
    return bytes(header)


def _fixed_ascii(value: str, length: int) -> bytes:
    encoded = value.encode("ascii", errors="replace")[:length]
    return encoded.ljust(length, b"\0")
