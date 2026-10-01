"""汎用Active IR・DepthカメラサービスのHTTP契約。"""

from __future__ import annotations

from ipaddress import AddressValueError, IPv4Address
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CameraDeviceSettings(BaseModel):
    """業務情報を含まない、IR・Depthカメラの接続・取得設定。"""

    camera_id: str = Field(default="camera_1", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    display_name: str = Field(default="カメラ1", min_length=1, max_length=100)
    driver: str = "orbbec_network"
    ip: str = Field(default="192.168.253.7", min_length=1, max_length=255)
    port: int = Field(default=8090, ge=1, le=65535)
    width: int = Field(default=512, ge=1)
    height: int = Field(default=512, ge=1)
    depth_width: int = Field(default=512, ge=1)
    depth_height: int = Field(default=512, ge=1)
    fps: int = Field(default=15, ge=1, le=60)
    align_depth_to_color: bool = False

    @field_validator("ip", mode="before")
    @classmethod
    def validate_ipv4_address(cls, value: object) -> str:
        address = str(value).strip()
        try:
            return str(IPv4Address(address))
        except AddressValueError as exc:
            raise ValueError("カメラ接続先は有効なIPv4アドレスで入力してください") from exc

    @model_validator(mode="after")
    def normalize_name(self) -> "CameraDeviceSettings":
        for field_name in ("display_name", "ip"):
            setattr(self, field_name, str(getattr(self, field_name)).strip())
        if not self.display_name:
            raise ValueError("カメラ表示名は空欄にできません")
        if not self.ip:
            raise ValueError("カメラ接続先は空欄にできません")
        if (self.width, self.height) != (self.depth_width, self.depth_height):
            raise ValueError("IRとDepthの解像度は同一にしてください")
        if self.align_depth_to_color:
            raise ValueError("IR版ではRGBへの位置合わせを無効にしてください")
        return self


class CameraFleetConfiguration(BaseModel):
    cameras: list[CameraDeviceSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CameraFleetConfiguration":
        ids = [camera.camera_id.casefold() for camera in self.cameras]
        if len(ids) != len(set(ids)):
            raise ValueError("camera_idが重複しています")
        endpoints = [(camera.driver.casefold(), camera.ip.casefold(), camera.port) for camera in self.cameras]
        if len(endpoints) != len(set(endpoints)):
            raise ValueError("同じカメラ接続先が重複しています")
        return self


class FrameBatchRequest(BaseModel):
    frame_count: int = Field(default=30, ge=1, le=120)
    warmup_frames: int = Field(default=5, ge=0, le=60)
    include_xyz: bool = False
    include_raw_frames: bool = True


class FrameBatchManifest(BaseModel):
    """IR生データとDepthを公開する。rgb_path/color_shapeは既存UIの互換キー。"""
    batch_id: str
    camera_id: str = "camera_1"
    captured_at: str
    frame_timestamps: list[str]
    depth_frames_path: str | None = None
    ir_path: str | None = None
    preview_path: str | None = None
    rgb_path: str  # 内容はIRプレビューJPEG。撮影にRGBカメラは使用しない。
    intrinsics_path: str
    intrinsics: dict[str, object] | None = None
    metadata_path: str
    median_depth_path: str | None = None
    xyz_path: str | None = None
    xyz_source: Literal["temporal_median_ignore_zero"] | None = None
    frame_count: int
    color_shape: tuple[int, int]  # IRプレビューの画素数。
    reference_shape: tuple[int, int] | None = None
    depth_shape: tuple[int, int]
    depth_aligned_to_color: bool


class CameraStreamStatus(BaseModel):
    running: bool = False
    connected: bool = False
    frames_received: int = 0
    started_at: str | None = None
    last_frame_at: str | None = None
    error: str | None = None
    camera: CameraDeviceSettings | None = None
    viewers: int = 0
    capture_active: bool = False


class CameraFleetStatus(BaseModel):
    cameras: list[CameraStreamStatus]
