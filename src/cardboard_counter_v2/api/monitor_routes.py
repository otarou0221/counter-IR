"""常時監視の開始・停止・状態取得ルーター。"""

from __future__ import annotations

from fastapi import APIRouter

from cardboard_counter_v2.api.monitoring import MonitorController
from cardboard_counter_v2.common.schemas import MonitorStatus


def create_monitor_router(monitor: MonitorController) -> APIRouter:
    router = APIRouter()

    @router.get("/api/monitor", response_model=MonitorStatus)
    def get_monitor() -> MonitorStatus:
        return monitor.current_status()

    @router.post("/api/monitor/start", response_model=MonitorStatus)
    async def start_monitor() -> MonitorStatus:
        return await monitor.start()

    @router.post("/api/monitor/stop", response_model=MonitorStatus)
    def stop_monitor() -> MonitorStatus:
        return monitor.stop()

    return router
