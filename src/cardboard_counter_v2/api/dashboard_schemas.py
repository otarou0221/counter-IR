"""工場マップ型ダッシュボードのHTTP契約。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DashboardState = Literal[
    "normal",
    "low_stock",
    "unavailable",
]


class FactoryMapSummary(BaseModel):
    factory_map_id: int
    display_name: str
    factory_name: str | None = None
    building_name: str | None = None
    floor_name: str | None = None
    image_width: int
    image_height: int
    image_url: str


class PalletMapPlacement(BaseModel):
    factory_map_id: int
    pallet_slot_id: int
    position_x_ratio: float = Field(ge=0.0, le=1.0)
    position_y_ratio: float = Field(ge=0.0, le=1.0)


class PalletMapPlacementInput(BaseModel):
    pallet_slot_id: int = Field(gt=0)
    position_x_ratio: float = Field(ge=0.0, le=1.0)
    position_y_ratio: float = Field(ge=0.0, le=1.0)


class PalletMapPlacementsUpdate(BaseModel):
    placements: list[PalletMapPlacementInput]


class DashboardPalletState(BaseModel):
    pallet_slot_id: int
    pallet_number: int
    display_name: str
    state: DashboardState
    inventory_count: int | None = None
    volume_liters: float | None = None
    box_counts: dict[str, int] | None = None
    low_stock_threshold_liters: float
    measured_at: str | None = None
    placement: PalletMapPlacement | None = None


class DashboardCameraState(BaseModel):
    camera_id: str
    camera_code: str
    display_name: str
    factory_name: str | None = None
    building_name: str | None = None
    floor_name: str | None = None
    area_name: str | None = None
    state: DashboardState
    state_message: str
    last_success_at: str | None = None
    last_failure_at: str | None = None
    pallets: list[DashboardPalletState]


class FactoryDashboard(BaseModel):
    generated_at: str
    monitor_running: bool
    measurement_interval_seconds: float
    maps: list[FactoryMapSummary]
    cameras: list[DashboardCameraState]
