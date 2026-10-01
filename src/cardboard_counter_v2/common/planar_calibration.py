"""カメラ投影と平面領域校正のベンダー非依存契約。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from cardboard_counter_v2.common.rgbd import CameraDistortion, RgbdIntrinsics, StreamIntrinsics


NormalizedRectangle = tuple[float, float, float, float]


class ProjectionIntrinsicsSpec(BaseModel):
    """XYZの投影に必要な1ストリーム分の内部パラメータ。"""

    point_cloud_sensor: Literal["color", "depth"] = "depth"
    align_depth_to_color: bool = False
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fx: float = Field(gt=0)
    fy: float = Field(gt=0)
    cx: float
    cy: float
    distortion: dict[str, float] | None = None

    def to_rgbd_intrinsics(self) -> RgbdIntrinsics:
        stream = StreamIntrinsics(
            width=self.width,
            height=self.height,
            fx=self.fx,
            fy=self.fy,
            cx=self.cx,
            cy=self.cy,
            distortion=CameraDistortion(**self.distortion) if self.distortion else None,
        )
        return RgbdIntrinsics(
            color=stream if self.point_cloud_sensor == "color" else None,
            depth=stream if self.point_cloud_sensor == "depth" else None,
            align_depth_to_color=self.align_depth_to_color,
            point_cloud_sensor=self.point_cloud_sensor,
        )


class PlanarRegionCalibration(BaseModel):
    """用途非依存の「平面上の1領域」の校正定義。"""

    region_id: int = Field(ge=1)
    roi: NormalizedRectangle
    reference_plane_normal: tuple[float, float, float]
    reference_plane_offset: float
    surface_offset_mm: float = Field(ge=0)
    cell_size_mm: float = Field(ge=2)

    @model_validator(mode="after")
    def validate_roi(self) -> "PlanarRegionCalibration":
        left, top, right, bottom = self.roi
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("roiは0〜1の範囲でleft<right、top<bottomが必要です")
        return self


class PlanarCalibrationDefinition(BaseModel):
    """DBや他システムから測定エンジンへ渡す最小校正定義。"""

    calibration_id: str
    camera_id: str
    calibration_capture_id: str
    projection: ProjectionIntrinsicsSpec
    regions: list[PlanarRegionCalibration] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_regions(self) -> "PlanarCalibrationDefinition":
        ids = [region.region_id for region in self.regions]
        if len(ids) != len(set(ids)):
            raise ValueError("region_idが重複しています")
        return self


class PreparePlanarRuntimeRequest(BaseModel):
    calibration: PlanarCalibrationDefinition
    color_shape: tuple[int, int]
    depth_shape: tuple[int, int]
