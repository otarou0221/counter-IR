"""カメラベンダーに依存しない画像・Depth内部パラメータ契約。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class CameraDistortion:
    k1: float
    k2: float
    k3: float
    k4: float
    k5: float
    k6: float
    p1: float
    p2: float


@dataclass(frozen=True)
class StreamIntrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    distortion: CameraDistortion | None = None


@dataclass(frozen=True)
class RgbdIntrinsics:
    """旧クラス名を維持。IR版ではir/depthを使い、colorはNone。"""

    color: StreamIntrinsics | None
    depth: StreamIntrinsics | None
    align_depth_to_color: bool
    point_cloud_sensor: str
    ir: StreamIntrinsics | None = None

    @property
    def depth_is_color_aligned(self) -> bool:
        return self.align_depth_to_color and self.point_cloud_sensor == "color"


def parse_rgbd_intrinsics(payload: dict[str, Any]) -> RgbdIntrinsics:
    return RgbdIntrinsics(
        color=_parse_stream(payload.get("color")),
        depth=_parse_stream(payload.get("depth")),
        align_depth_to_color=bool(payload.get("align_depth_to_color")),
        point_cloud_sensor=str(payload.get("point_cloud_sensor") or ""),
        ir=_parse_stream(payload.get("ir")),
    )


def intrinsics_compatible(left: RgbdIntrinsics, right: RgbdIntrinsics) -> bool:
    """現在のDepth投影に使う内部パラメータが実質同一か判定する。"""
    if left.align_depth_to_color != right.align_depth_to_color:
        return False
    if left.point_cloud_sensor != right.point_cloud_sensor:
        return False
    left_stream = _point_cloud_stream(left)
    right_stream = _point_cloud_stream(right)
    if left_stream is None or right_stream is None:
        return False
    if (left_stream.width, left_stream.height) != (right_stream.width, right_stream.height):
        return False
    # SDK JSONの小数表現差が投影に影響しないよう、1/1000 pixel未満だけ許容する。
    if left_stream.distortion != right_stream.distortion:
        return False
    return all(
        math.isclose(left_value, right_value, rel_tol=1e-9, abs_tol=1e-3)
        for left_value, right_value in (
            (left_stream.fx, right_stream.fx),
            (left_stream.fy, right_stream.fy),
            (left_stream.cx, right_stream.cx),
            (left_stream.cy, right_stream.cy),
        )
    )


def _point_cloud_stream(value: RgbdIntrinsics) -> StreamIntrinsics | None:
    if value.point_cloud_sensor == "color":
        return value.color
    if value.point_cloud_sensor == "depth":
        return value.depth
    return None


def _parse_stream(value: Any) -> StreamIntrinsics | None:
    if not isinstance(value, dict):
        return None
    return StreamIntrinsics(
        width=int(value["width"]),
        height=int(value["height"]),
        fx=float(value["fx"]),
        fy=float(value["fy"]),
        cx=float(value["cx"]),
        cy=float(value["cy"]),
        distortion=_parse_distortion(value.get("distortion")),
    )


def _parse_distortion(value: Any) -> CameraDistortion | None:
    if not isinstance(value, dict):
        return None
    return CameraDistortion(
        k1=float(value["k1"]),
        k2=float(value["k2"]),
        k3=float(value["k3"]),
        k4=float(value["k4"]),
        k5=float(value["k5"]),
        k6=float(value["k6"]),
        p1=float(value["p1"]),
        p2=float(value["p2"]),
    )
