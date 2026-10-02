import pytest
from pydantic import ValidationError

from cardboard_counter_v2.common.planar_calibration import PlanarRegionCalibration
from cardboard_counter_v2.common.schemas import (
    CalibrationRequest,
    CameraSettings,
    MeasurementRequest,
    PalletSettings,
    SystemSettings,
)


def test_measurement_method_is_fixed() -> None:
    settings = SystemSettings()
    assert settings.method == "pallet_plane_2roi"

    with pytest.raises(ValidationError):
        SystemSettings(method="roi_median")


def test_ir_default_grid_is_20mm_and_older_grid_can_be_loaded() -> None:
    assert SystemSettings().grid_mm == 20.0
    assert CalibrationRequest(baseline_capture_id="floor", pallets=[]).grid_mm == 20.0
    assert (
        MeasurementRequest(current_capture_id="current", runtime_id="calibration").grid_mm
        == 20.0
    )
    assert SystemSettings(grid_mm=10).grid_mm == 10.0


def test_monitor_interval_is_bounded() -> None:
    assert SystemSettings().monitor_interval_seconds == 600.0
    assert SystemSettings(monitor_interval_seconds=60).monitor_interval_seconds == 60

    with pytest.raises(ValidationError):
        SystemSettings(monitor_interval_seconds=59)
    with pytest.raises(ValidationError):
        SystemSettings(monitor_interval_seconds=90)


def test_floor_and_measurement_frame_counts_are_independent() -> None:
    settings = SystemSettings()
    assert settings.frame_count == 30
    assert settings.measurement_frame_count == 1

    assert SystemSettings(measurement_frame_count=120).measurement_frame_count == 120
    with pytest.raises(ValidationError):
        SystemSettings(measurement_frame_count=0)


def test_floor_reference_height_is_bounded() -> None:
    settings = SystemSettings()
    assert settings.pallet_height_mm == 150.0

    with pytest.raises(ValidationError):
        SystemSettings(pallet_height_mm=0)


def test_legacy_pallet_roi_margin_is_ignored() -> None:
    settings = SystemSettings.model_validate({"pallet_roi_margin_mm": 100.0})
    assert "pallet_roi_margin_mm" not in settings.model_dump()


def test_legacy_calibration_mask_inset_is_ignored() -> None:
    region = PlanarRegionCalibration.model_validate({
        "region_id": 1,
        "roi": [0.1, 0.1, 0.9, 0.9],
        "reference_plane_normal": [0.0, 0.0, -1.0],
        "reference_plane_offset": 1_000.0,
        "surface_offset_mm": 150.0,
        "mask_inset_mm": 100.0,
        "cell_size_mm": 10.0,
    })
    assert "mask_inset_mm" not in region.model_dump()


def test_legacy_monitor_artifact_flag_is_removed() -> None:
    settings = SystemSettings.model_validate({"monitor_generate_artifacts": True})
    assert "monitor_generate_artifacts" not in settings.model_dump()


def test_default_camera_uses_current_site_address() -> None:
    assert SystemSettings().cameras[0].ip == "192.168.253.7"
    assert SystemSettings().cameras[0].camera_id == "camera_1"
    assert [pallet.pallet_number for pallet in SystemSettings().pallets] == [1, 2]


@pytest.mark.parametrize("ip", ["camera.local", "192.168.1", "192.168.1.256", "192.168.001.1"])
def test_camera_ip_requires_canonical_ipv4(ip: str) -> None:
    with pytest.raises(ValidationError, match="IPv4"):
        CameraSettings(ip=ip)


def test_camera_ip_trims_surrounding_whitespace() -> None:
    assert CameraSettings(ip=" 192.168.100.50 ").ip == "192.168.100.50"


def test_inventory_threshold_and_rearm_margin_require_positive_liters() -> None:
    payload = SystemSettings().model_dump(mode="json")
    payload["pallets"][0]["low_stock_threshold_liters"] = 12.5
    payload["pallets"][0]["email_rearm_margin_liters"] = 154.0
    pallet = SystemSettings.model_validate(payload).pallets[0]
    assert pallet.low_stock_threshold_liters == 12.5
    assert pallet.email_rearm_margin_liters == 154.0

    for field_name in ("low_stock_threshold_liters", "email_rearm_margin_liters"):
        invalid = SystemSettings().model_dump(mode="json")
        invalid["pallets"][0][field_name] = 0
        with pytest.raises(ValidationError):
            SystemSettings.model_validate(invalid)


def test_box_arrangement_rules_accept_singles_and_mixed_groups() -> None:
    pallet = PalletSettings(
        pallet_id=1,
        display_name="パレット 1",
        plane_roi=(0.1, 0.1, 0.4, 0.8),
        single_box_labels=["A", "B"],
        mixed_box_groups=[["B", "C"]],
        reference_box_label="C",
    )

    assert pallet.box_rule_labels == ["A", "B", "C"]


def test_legacy_target_box_labels_become_safe_single_candidates() -> None:
    pallet = PalletSettings.model_validate({
        "pallet_id": 1,
        "display_name": "パレット 1",
        "plane_roi": (0.1, 0.1, 0.4, 0.8),
        "target_box_labels": ["A", "B"],
        "reference_box_label": "A",
    })

    assert pallet.single_box_labels == ["A", "B"]
    assert pallet.mixed_box_groups == []


def test_ir_method_rejects_depth_to_color_alignment() -> None:
    with pytest.raises(ValidationError):
        SystemSettings(cameras=[CameraSettings(align_depth_to_color=True)])


def test_legacy_single_camera_is_migrated_and_assigned_to_pallets() -> None:
    settings = SystemSettings.model_validate({
        "camera": {"ip": "192.168.253.9", "port": 8090},
    })
    assert [(camera.camera_id, camera.ip) for camera in settings.cameras] == [
        ("camera_1", "192.168.253.9")
    ]
    assert {pallet.camera_id for pallet in settings.pallets} == {"camera_1"}


def test_pallet_must_reference_registered_camera() -> None:
    payload = SystemSettings().model_dump(mode="json")
    payload["pallets"][0]["camera_id"] = "missing"
    with pytest.raises(ValidationError, match="未登録"):
        SystemSettings.model_validate(payload)


def test_camera_endpoint_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="接続先"):
        SystemSettings(cameras=[
            CameraSettings(camera_id="camera_1", display_name="1"),
            CameraSettings(camera_id="camera_2", display_name="2"),
        ])


def test_existing_multi_camera_settings_receive_two_disabled_pallet_slots() -> None:
    payload = SystemSettings().model_dump(mode="json")
    payload["cameras"].append({
        **payload["cameras"][0],
        "camera_id": "camera_2",
        "camera_code": "CAM-002",
        "display_name": "カメラ2",
        "location_id": None,
        "port": 9001,
    })
    settings = SystemSettings.model_validate(payload)
    camera_2 = [pallet for pallet in settings.pallets if pallet.camera_id == "camera_2"]
    assert [pallet.pallet_number for pallet in camera_2] == [1, 2]
    assert not any(pallet.enabled for pallet in camera_2)


def test_more_than_two_pallets_for_one_camera_is_rejected() -> None:
    payload = SystemSettings().model_dump(mode="json")
    extra = {**payload["pallets"][0], "pallet_id": 3}
    payload["pallets"].append(extra)
    with pytest.raises(ValidationError):
        SystemSettings.model_validate(payload)


def test_legacy_single_box_dimensions_are_migrated_once() -> None:
    settings = SystemSettings.model_validate({"pallets": [{
        "pallet_id": 1,
        "plane_roi": (0.1, 0.1, 0.4, 0.4),
        "box_width_mm": 100,
        "box_depth_mm": 200,
        "box_height_mm": 300,
    }]})

    assert len(settings.box_catalog) == 1
    assert settings.box_catalog[0].label == "cardboard_box"
    assert settings.box_catalog[0].volume_mm3 == 6_000_000
    assert settings.pallets[0].single_box_labels == ["cardboard_box"]
    assert settings.pallets[0].mixed_box_groups == []
    assert settings.pallets[0].reference_box_label == "cardboard_box"


def test_box_catalog_labels_are_unique() -> None:
    payload = {
        "box_catalog": [
            {"label": "box", "width_mm": 100, "depth_mm": 100, "height_mm": 100},
            {"label": "BOX", "width_mm": 200, "depth_mm": 100, "height_mm": 100},
        ],
        "pallets": [{
            "pallet_id": 1,
            "plane_roi": (0.1, 0.1, 0.4, 0.4),
            "single_box_labels": ["box"],
            "reference_box_label": "box",
        }],
    }
    with pytest.raises(ValidationError):
        SystemSettings.model_validate(payload)


def test_per_pallet_box_classes_migrate_to_shared_catalog_and_selection() -> None:
    settings = SystemSettings.model_validate({"pallets": [
        {
            "pallet_id": 1,
            "plane_roi": (0.05, 0.1, 0.45, 0.9),
            "box_classes": [
                {"label": "standard", "width_mm": 570, "depth_mm": 410, "height_mm": 335},
                {"label": "long", "width_mm": 700, "depth_mm": 300, "height_mm": 200},
            ],
        },
        {
            "pallet_id": 2,
            "enabled": False,
            "plane_roi": (0.55, 0.1, 0.95, 0.9),
            "box_classes": [
                {"label": "long", "width_mm": 700, "depth_mm": 300, "height_mm": 200},
            ],
        },
    ]})

    assert [item.label for item in settings.box_catalog] == ["standard", "long"]
    assert settings.pallets[0].single_box_labels == ["standard", "long"]
    assert settings.pallets[0].mixed_box_groups == []
    assert settings.pallets[0].reference_box_label == "standard"
    assert settings.pallets[1].single_box_labels == ["long"]
