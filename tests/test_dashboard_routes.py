from __future__ import annotations

import struct

import pytest

from cardboard_counter_v2.api.dashboard_routes import validate_png


def png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
    )


def test_png_map_header_returns_image_size() -> None:
    assert validate_png(png_header(1076, 621)) == (1076, 621)


@pytest.mark.parametrize("payload", [b"", b"not-png", png_header(20_001, 100)])
def test_png_map_rejects_invalid_input(payload: bytes) -> None:
    with pytest.raises(ValueError):
        validate_png(payload)
