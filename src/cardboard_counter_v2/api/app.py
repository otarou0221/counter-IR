"""Cardboard Counter v2 APIの構成とライフサイクルだけを定義する。"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from cardboard_counter_v2.api.box_catalog_repository import BoxCatalogRepository
from cardboard_counter_v2.api.config_routes import create_config_router
from cardboard_counter_v2.api.context import ApiContext
from cardboard_counter_v2.api.debug_routes import create_debug_router
from cardboard_counter_v2.api.dashboard_routes import create_dashboard_router
from cardboard_counter_v2.api.field_routes import create_field_router
from cardboard_counter_v2.api.internal_services import InternalServices
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.api.inventory.repositories.dashboard_repository import (
    DashboardRepository,
)
from cardboard_counter_v2.api.inventory.repositories.factory_map_repository import (
    FactoryMapRepository,
)
from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.monitor_routes import create_monitor_router
from cardboard_counter_v2.api.monitoring import MonitorController
from cardboard_counter_v2.api.notifications import SmtpLowStockNotifier
from cardboard_counter_v2.api.roi_routes import create_roi_router
from cardboard_counter_v2.api.roi_references import RoiReferenceService
from cardboard_counter_v2.api.service_client import ServiceClient
from cardboard_counter_v2.api.settings import SettingsStore
from cardboard_counter_v2.api.state import RuntimeStateStore
from cardboard_counter_v2.api.workflows import MeasurementWorkflow
from cardboard_counter_v2.common.storage import data_root
from cardboard_counter_v2.common.retention import run_periodic_cleanup


CAMERA_URL = os.environ.get(
    "CAMERA_SERVICE_URL", "http://127.0.0.1:8001"
).rstrip("/")
MEASUREMENT_URL = os.environ.get(
    "MEASUREMENT_SERVICE_URL", "http://127.0.0.1:8002"
).rstrip("/")

service_client = ServiceClient()
services = InternalServices(
    service_client,
    camera_url=CAMERA_URL,
    measurement_url=MEASUREMENT_URL,
)
database = Database()
box_catalog_repository = BoxCatalogRepository(database)
settings_repository = InventoryRepository(database)
store = SettingsStore(settings_repository, box_catalog_repository)
state_store = RuntimeStateStore()
operation_lock = asyncio.Lock()
history = InventoryHistoryService(database)
dashboard_repository = DashboardRepository(database)
factory_map_repository = FactoryMapRepository(database)
roi_references = RoiReferenceService(state_store, history)
workflow = MeasurementWorkflow(services, state_store, history)
monitor = MonitorController(
    store=store,
    workflow=workflow,
    operation_lock=operation_lock,
    history=history,
    notifier=SmtpLowStockNotifier.from_environment(),
)
context = ApiContext(
    store=store,
    state_store=state_store,
    operation_lock=operation_lock,
    services=services,
    workflow=workflow,
    monitor=monitor,
    history=history,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # DB導入前の結果キャッシュは正式履歴・HTTP応答へ移行済みのため残さない。
    (data_root() / "state" / "last_result.json").unlink(missing_ok=True)
    (data_root() / "state" / "last_debug_result.json").unlink(missing_ok=True)
    await service_client.start()
    try:
        settings = store.load()
        monitor.update_interval(settings.monitor_interval_seconds)
        await asyncio.to_thread(history.initialize, settings)
        active_calibrations = await asyncio.to_thread(
            history.load_active_calibrations
        )
        state_store.restore_calibrations(active_calibrations)
        await services.configure_cameras(settings.cameras)
        history_cleanup_task = asyncio.create_task(
            run_periodic_cleanup(
                history.prune_inventory_history,
                interval_seconds=float(
                    os.environ.get("DB_RETENTION_CLEANUP_INTERVAL_SECONDS", "86400")
                ),
            )
        )
        try:
            yield
        finally:
            history_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await history_cleanup_task
    finally:
        await monitor.shutdown()
        await service_client.close()
        await asyncio.to_thread(history.dispose)


app = FastAPI(
    title="Cardboard Counter v2 API",
    version="0.4.0",
    lifespan=lifespan,
)
app.include_router(create_config_router(context))
app.include_router(create_dashboard_router(
    dashboard_repository,
    factory_map_repository,
    monitor,
))
app.include_router(create_field_router(context))
app.include_router(create_roi_router(context, roi_references))
app.include_router(create_monitor_router(monitor))
app.include_router(
    create_debug_router(
        store=store,
        operation_lock=operation_lock,
        monitoring=monitor.running,
        request_calibration=services.calibrate,
        request_measurement=services.measure,
        prepare_measurement_runtime=services.prepare_measurement_runtime,
        request_current_debug=workflow.capture_current_debug,
        history=history,
    )
)
app.mount("/artifacts", StaticFiles(directory=data_root(), html=True), name="artifacts")
