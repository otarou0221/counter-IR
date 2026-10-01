from pathlib import Path

import pytest

from cardboard_counter_v2.api.box_catalog_repository import BoxCatalogRepository
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.api.settings import SettingsStore
from cardboard_counter_v2.api.state import RuntimeStateStore
from cardboard_counter_v2.common.schemas import SystemSettings
from cardboard_counter_v2.common.storage import atomic_write_json, read_json


def test_legacy_settings_json_is_migrated_to_database_and_deleted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    atomic_write_json(path, {
        "pallets": [{
            "pallet_id": 1,
            "plane_roi": [0.1, 0.1, 0.4, 0.4],
            "box_width_mm": 570,
            "box_depth_mm": 410,
            "box_height_mm": 335,
        }],
    })

    database = Database(f"sqlite+pysqlite:///{tmp_path / 'settings.sqlite'}")
    store = SettingsStore(
        InventoryRepository(database), BoxCatalogRepository(database), path
    )
    assert store.migrate_legacy_json() is True
    loaded = store.load()

    assert loaded.box_catalog[0].label == "cardboard_box"
    assert loaded.pallets[0].single_box_labels == ["cardboard_box"]
    assert loaded.pallets[0].mixed_box_groups == []
    assert not path.exists()
    assert store.migrate_legacy_json() is False
    database.dispose()


def test_all_settings_are_loaded_and_updated_from_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    payload = SystemSettings().model_dump(mode="json")
    payload["box_catalog"] = [{
        "label": "standard",
        "width_mm": 450,
        "depth_mm": 400,
        "height_mm": 240,
    }]
    for pallet in payload["pallets"]:
        pallet["single_box_labels"] = ["standard"]
        pallet["mixed_box_groups"] = []
        pallet["reference_box_label"] = "standard"
    atomic_write_json(path, payload)
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'settings.sqlite'}")
    box_repository = BoxCatalogRepository(database)
    repository = InventoryRepository(database)
    store = SettingsStore(repository, box_repository, path)

    assert store.migrate_legacy_json() is True
    loaded = store.load()

    assert loaded.box_catalog[0].box_type_id == 1
    assert loaded.box_catalog[0].label == "standard"
    assert not path.exists()
    assert box_repository.load() == loaded.box_catalog

    changed_box = loaded.box_catalog[0].model_copy(update={"height_mm": 250.0})
    saved = store.save(loaded.model_copy(update={"box_catalog": [changed_box]}))

    assert saved.box_catalog[0].box_type_id == 1
    assert box_repository.load()[0].height_mm == 250.0
    assert repository.load_settings().box_catalog[0].height_mm == 250.0  # type: ignore[union-attr]

    invalid = changed_box.model_copy(update={"box_type_id": 999})
    with pytest.raises(ValueError, match="DBに存在しません"):
        store.save(loaded.model_copy(update={"box_catalog": [invalid]}))
    database.dispose()


def test_uncalibrated_roi_is_transient_until_calibration(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'roi.sqlite'}")
    repository = InventoryRepository(database)
    boxes = BoxCatalogRepository(database)
    store = SettingsStore(repository, boxes)
    loaded = store.load()
    first, second = loaded.pallets
    changed_roi = (0.1, 0.2, 0.4, 0.8)
    changed = loaded.model_copy(update={
        "pallets": [first.model_copy(update={"plane_roi": changed_roi}), second]
    })

    saved = store.save(changed)

    assert saved.pallets[0].plane_roi == changed_roi
    reloaded = SettingsStore(repository, boxes).load()
    assert reloaded.pallets[0].plane_roi == (0.05, 0.15, 0.48, 0.95)
    database.dispose()


def test_database_box_catalog_keeps_id_when_renamed_and_removes_deleted_rows(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'catalog.sqlite'}")
    repository = BoxCatalogRepository(database)
    repository.initialize()
    initial = repository.replace(SystemSettings().box_catalog)
    first_id = initial[0].box_type_id

    renamed = initial[0].model_copy(update={"label": "standard"})
    saved = repository.replace([
        renamed,
        renamed.model_copy(update={
            "box_type_id": None,
            "label": "small",
            "width_mm": 300.0,
        }),
    ])

    assert saved[0].box_type_id == first_id
    assert [item.label for item in repository.load()] == ["standard", "small"]

    reassigned = repository.replace([
        saved[0].model_copy(update={"label": "small"}),
        saved[0].model_copy(update={
            "box_type_id": None,
            "label": "standard",
            "width_mm": 500.0,
        }),
    ])

    assert reassigned[0].box_type_id == first_id
    assert reassigned[1].box_type_id not in {first_id, saved[1].box_type_id}

    repository.replace([reassigned[1]])

    remaining = repository.load()
    assert [item.label for item in remaining] == ["standard"]
    assert remaining[0].box_type_id == reassigned[1].box_type_id
    database.dispose()


def test_missing_database_configuration_does_not_fall_back_to_json(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    path = tmp_path / "settings.json"
    atomic_write_json(path, SystemSettings().model_dump(mode="json"))
    database = Database()
    store = SettingsStore(
        InventoryRepository(database), BoxCatalogRepository(database), path
    )

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        store.migrate_legacy_json()

    assert read_json(path)["box_catalog"][0]["label"] == "cardboard_box"


def test_runtime_state_restores_active_calibration_from_database_values() -> None:
    store = RuntimeStateStore()
    state = store.restore_calibrations({
        "camera_1": ("empty_old", "calibration_old"),
    })
    assert state.camera("camera_1").calibration_id == "calibration_old"
    assert state.camera("camera_1").baseline_capture_id == "empty_old"
