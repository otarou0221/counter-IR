from pathlib import Path
import struct

import numpy as np

from cardboard_counter_v2.measurement.point_cloud_export import write_rgb_las


def test_write_rgb_las_preserves_coordinates_and_colors(tmp_path: Path) -> None:
    coordinates = np.array([[-100.0, 250.0, 0.0], [900.0, 1_250.0, 335.0]])
    colors = np.array([[1, 2, 3], [255, 128, 0]], dtype=np.uint8)
    output = tmp_path / "cloud.las"

    write_rgb_las(output, coordinates, colors)

    payload = output.read_bytes()
    assert payload[:4] == b"LASF"
    assert payload[24:26] == bytes([1, 2])
    assert struct.unpack_from("<BH", payload, 104) == (2, 26)
    assert struct.unpack_from("<I", payload, 107)[0] == 2
    scales = np.array(struct.unpack_from("<3d", payload, 131))
    offsets = np.array(struct.unpack_from("<3d", payload, 155))
    first = struct.unpack_from("<iiiHBBbBHHHH", payload, 227)
    second = struct.unpack_from("<iiiHBBbBHHHH", payload, 227 + 26)
    np.testing.assert_allclose(np.array(first[:3]) * scales + offsets, [-0.1, 0.25, 0.0])
    np.testing.assert_allclose(np.array(second[:3]) * scales + offsets, [0.9, 1.25, 0.335])
    assert first[-3:] == (257, 514, 771)
    assert second[-3:] == (65_535, 32_896, 0)
    header_maximum = np.array(struct.unpack_from("<6d", payload, 179))[[0, 2, 4]]
    reconstructed = np.array(second[:3]) * scales + offsets
    assert np.all(header_maximum >= reconstructed)


def test_write_rgb_las_rejects_empty_cloud(tmp_path: Path) -> None:
    try:
        write_rgb_las(
            tmp_path / "empty.las",
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 3), dtype=np.uint8),
        )
    except ValueError as error:
        assert "空の点群" in str(error)
    else:
        raise AssertionError("空の点群を受理しています")
