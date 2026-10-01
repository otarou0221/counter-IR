from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegionOfInterest:
    x1: int
    y1: int
    x2: int
    y2: int


def normalized_roi(
    values: tuple[float, float, float, float],
    shape: tuple[int, int],
) -> RegionOfInterest:
    height, width = shape
    left, top, right, bottom = values
    return RegionOfInterest(
        x1=max(0, min(int(round(left * width)), width - 1)),
        y1=max(0, min(int(round(top * height)), height - 1)),
        x2=max(1, min(int(round(right * width)), width)),
        y2=max(1, min(int(round(bottom * height)), height)),
    )
