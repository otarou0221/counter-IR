import pytest

from cardboard_counter_v2.api.config_validation import (
    validate_camera_settings_update,
)
from cardboard_counter_v2.common.schemas import SystemSettings


def complete_settings() -> SystemSettings:
    settings = SystemSettings()
    return settings.model_copy(update={
        "cameras": [
            camera.model_copy(update={
                "factory_name": "第5工場",
                "building_name": "第5工場",
                "floor_name": "3階",
                "area_name": "資材エリア",
            })
            for camera in settings.cameras
        ]
    })


def test_complete_camera_management_fields_are_accepted() -> None:
    settings = complete_settings()
    validate_camera_settings_update(settings, settings)


def test_factory_building_and_floor_are_required_when_saving() -> None:
    previous = SystemSettings()
    with pytest.raises(ValueError, match="工場名, 建物・工場棟名, フロア名"):
        validate_camera_settings_update(previous, previous)


def test_existing_location_id_cannot_be_changed() -> None:
    previous = complete_settings()
    changed = previous.model_copy(update={
        "cameras": [
            previous.cameras[0].model_copy(update={"location_id": 2})
        ]
    })
    with pytest.raises(ValueError, match="作成後に変更できません"):
        validate_camera_settings_update(previous, changed)


def test_new_camera_must_use_database_generated_location_id() -> None:
    previous = complete_settings()
    added = previous.cameras[0].model_copy(update={
        "camera_id": "camera_2",
        "camera_code": "CAM-002",
        "location_id": 2,
        "ip": "192.168.253.8",
    })
    current = previous.model_copy(update={"cameras": [*previous.cameras, added]})
    with pytest.raises(ValueError, match="自動採番"):
        validate_camera_settings_update(previous, current)
