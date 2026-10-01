"""DBテーブル群を用途別に分離したSQLAlchemyリポジトリ。"""

from cardboard_counter_v2.api.inventory.repositories.calibration_repository import (
    CalibrationRepository,
)
from cardboard_counter_v2.api.inventory.repositories.capture_repository import (
    CaptureRepository,
)
from cardboard_counter_v2.api.inventory.repositories.history_repository import (
    InventoryHistoryRepository,
)
from cardboard_counter_v2.api.inventory.repositories.dashboard_repository import (
    DashboardRepository,
)
from cardboard_counter_v2.api.inventory.repositories.factory_map_repository import (
    FactoryMapRepository,
)
from cardboard_counter_v2.api.inventory.repositories.measurement_repository import (
    MeasurementRepository,
)
from cardboard_counter_v2.api.inventory.repositories.settings_repository import (
    SettingsRepository,
)

__all__ = [
    "CalibrationRepository",
    "CaptureRepository",
    "DashboardRepository",
    "FactoryMapRepository",
    "InventoryHistoryRepository",
    "MeasurementRepository",
    "SettingsRepository",
]
