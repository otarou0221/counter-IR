"""APIルーター間で共有する長寿命サービス。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from cardboard_counter_v2.api.internal_services import InternalServices
from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.monitoring import MonitorController
from cardboard_counter_v2.api.settings import SettingsStore
from cardboard_counter_v2.api.state import RuntimeStateStore
from cardboard_counter_v2.api.workflows import MeasurementWorkflow


@dataclass(frozen=True)
class ApiContext:
    store: SettingsStore
    state_store: RuntimeStateStore
    operation_lock: asyncio.Lock
    services: InternalServices
    workflow: MeasurementWorkflow
    monitor: MonitorController
    history: InventoryHistoryService
