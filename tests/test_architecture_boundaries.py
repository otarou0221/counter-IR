"""責務分割したファサードが専用サービスへ委譲することを固定する。"""

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repositories import (
    CalibrationRepository,
    CaptureRepository,
    InventoryHistoryRepository,
    MeasurementRepository,
    SettingsRepository,
)
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.api.workflow import (
    CalibrationService,
    CaptureRetentionService,
    CaptureService,
    MeasurementJobRunner,
)
from cardboard_counter_v2.api.workflows import MeasurementWorkflow


def test_measurement_workflow_composes_responsibility_services() -> None:
    workflow = MeasurementWorkflow(object(), object())  # type: ignore[arg-type]

    assert isinstance(workflow.captures, CaptureService)
    assert isinstance(workflow.calibrations, CalibrationService)
    assert isinstance(workflow.jobs, MeasurementJobRunner)
    assert isinstance(workflow.retention, CaptureRetentionService)


def test_inventory_facade_composes_table_group_repositories() -> None:
    repository = InventoryRepository(Database())

    assert isinstance(repository.settings, SettingsRepository)
    assert isinstance(repository.captures, CaptureRepository)
    assert isinstance(repository.calibrations, CalibrationRepository)
    assert isinstance(repository.measurements, MeasurementRepository)
    assert isinstance(repository.inventory_history, InventoryHistoryRepository)
