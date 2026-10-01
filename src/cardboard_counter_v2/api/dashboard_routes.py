"""工場マップ型ダッシュボードのAPI。"""

from __future__ import annotations

import asyncio
import struct

from fastapi import APIRouter, HTTPException, Query, Request, Response

from cardboard_counter_v2.api.dashboard_schemas import (
    FactoryDashboard,
    FactoryMapSummary,
    PalletMapPlacement,
    PalletMapPlacementsUpdate,
)
from cardboard_counter_v2.api.inventory.repositories.dashboard_repository import (
    DashboardRepository,
)
from cardboard_counter_v2.api.inventory.repositories.factory_map_repository import (
    FactoryMapRepository,
)
from cardboard_counter_v2.api.monitoring import MonitorController


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_MAP_IMAGE_BYTES = 15 * 1024 * 1024
MAX_MAP_DIMENSION = 20_000
IMMUTABLE_IMAGE_CACHE_SECONDS = 365 * 24 * 60 * 60


def create_dashboard_router(
    dashboard_repository: DashboardRepository,
    factory_map_repository: FactoryMapRepository,
    monitor: MonitorController,
) -> APIRouter:
    router = APIRouter(prefix="/api/dashboard")

    @router.get("", response_model=FactoryDashboard)
    async def dashboard() -> FactoryDashboard:
        status = monitor.current_status()
        return await asyncio.to_thread(
            dashboard_repository.load_dashboard,
            monitor_running=status.running,
            measurement_interval_seconds=status.interval_seconds,
        )

    @router.post("/maps", response_model=FactoryMapSummary, status_code=201)
    async def create_map(
        request: Request,
        display_name: str = Query(min_length=1, max_length=100),
        factory_name: str = Query(min_length=1, max_length=100),
        building_name: str = Query(min_length=1, max_length=100),
        floor_name: str = Query(min_length=1, max_length=100),
    ) -> FactoryMapSummary:
        if request.headers.get("content-type", "").split(";", 1)[0] != "image/png":
            raise HTTPException(status_code=415, detail="工場マップはPNG形式で登録してください")
        image_data = await request.body()
        try:
            width, height = validate_png(image_data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        required_names = {
            "マップ表示名": display_name.strip(),
            "工場名": factory_name.strip(),
            "建物・工場棟名": building_name.strip(),
            "フロア名": floor_name.strip(),
        }
        for label, value in required_names.items():
            if not value:
                raise HTTPException(status_code=422, detail=f"{label}を入力してください")
        return await asyncio.to_thread(
            factory_map_repository.create_map,
            display_name=required_names["マップ表示名"],
            factory_name=required_names["工場名"],
            building_name=required_names["建物・工場棟名"],
            floor_name=required_names["フロア名"],
            image_data=image_data,
            image_width=width,
            image_height=height,
        )

    @router.get("/maps/{factory_map_id}/image")
    async def map_image(factory_map_id: int) -> Response:
        try:
            media_type, image_data = await asyncio.to_thread(
                factory_map_repository.map_image, factory_map_id
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=image_data,
            media_type=media_type,
            headers={
                "Cache-Control": (
                    f"private, max-age={IMMUTABLE_IMAGE_CACHE_SECONDS}, immutable"
                )
            },
        )

    @router.delete(
        "/maps/{factory_map_id}",
        response_model=FactoryMapSummary,
    )
    async def delete_map(factory_map_id: int) -> FactoryMapSummary:
        try:
            return await asyncio.to_thread(
                factory_map_repository.delete_map, factory_map_id
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put(
        "/maps/{factory_map_id}/placements",
        response_model=list[PalletMapPlacement],
    )
    async def save_placements(
        factory_map_id: int,
        payload: PalletMapPlacementsUpdate,
    ) -> list[PalletMapPlacement]:
        try:
            return await asyncio.to_thread(
                factory_map_repository.save_placements,
                factory_map_id,
                payload.placements,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


def validate_png(image_data: bytes) -> tuple[int, int]:
    if not image_data:
        raise ValueError("PNGファイルが空です")
    if len(image_data) > MAX_MAP_IMAGE_BYTES:
        raise ValueError("PNGファイルは15MB以下にしてください")
    if len(image_data) < 24 or not image_data.startswith(PNG_SIGNATURE):
        raise ValueError("正しいPNGファイルではありません")
    if image_data[12:16] != b"IHDR":
        raise ValueError("PNGの画像サイズを確認できません")
    width, height = struct.unpack(">II", image_data[16:24])
    if width <= 0 or height <= 0 or width > MAX_MAP_DIMENSION or height > MAX_MAP_DIMENSION:
        raise ValueError("PNGの縦横サイズは1～20000pxにしてください")
    return width, height
