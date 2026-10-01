"""カメラ・設置場所・監視枠・測定設定の読込みと同期。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    BoxTypeRecord,
    CameraInstallationRecord,
    CameraRecord,
    LocationRecord,
    MeasurementSettingsRecord,
    PalletCalibrationRecord,
    PalletSlotRecord,
)
from cardboard_counter_v2.common.box_catalog import BoxClassSpec
from cardboard_counter_v2.common.pallet_layout import default_pallet_payload
from cardboard_counter_v2.common.schemas import (
    CameraSettings,
    PalletSettings,
    SystemSettings,
)


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self, settings: SystemSettings) -> None:
        self.database.initialize()
        self.sync(settings)

    def sync(self, settings: SystemSettings) -> None:
        with self.database.session() as session:
            self.sync_in_session(session, settings)

    def load(self) -> SystemSettings | None:
        with self.database.session() as session:
            measurement = session.get(MeasurementSettingsRecord, 1)
            cameras = session.scalars(
                select(CameraRecord)
                .where(CameraRecord.active.is_(True))
                .order_by(CameraRecord.camera_id)
            ).all()
            if measurement is None or not cameras:
                return None
            installations = session.scalars(
                select(CameraInstallationRecord)
                .where(CameraInstallationRecord.removed_at.is_(None))
                .order_by(CameraInstallationRecord.camera_installation_id)
            ).all()
            installation_by_camera: dict[str, CameraInstallationRecord] = {}
            for installation in installations:
                if installation.camera_id in installation_by_camera:
                    raise ValueError(
                        "有効なカメラ設置履歴が複数あります: "
                        f"{installation.camera_id}"
                    )
                installation_by_camera[installation.camera_id] = installation

            camera_settings: list[CameraSettings] = []
            pallet_settings: list[PalletSettings] = []
            active_roi_by_slot = active_calibration_rois(session)
            for camera in cameras:
                installation = installation_by_camera.get(camera.camera_id)
                if installation is None:
                    raise ValueError(
                        f"有効なカメラ設置履歴がありません: {camera.camera_id}"
                    )
                location = installation.location
                camera_settings.append(CameraSettings(
                    camera_id=camera.camera_id,
                    display_name=camera.display_name,
                    driver=installation.driver,
                    ip=str(installation.ip_address),
                    port=installation.port,
                    width=installation.color_width,
                    height=installation.color_height,
                    depth_width=installation.depth_width,
                    depth_height=installation.depth_height,
                    fps=installation.fps,
                    align_depth_to_color=installation.align_depth_to_color,
                    camera_code=camera.camera_code,
                    manufacturer=camera.manufacturer,
                    model_name=camera.model_name,
                    serial_number=camera.serial_number,
                    location_id=location.location_id,
                    factory_name=location.factory_name,
                    building_name=location.building_name,
                    floor_name=location.floor_name,
                    area_name=location.area_name,
                    mounting_note=installation.mounting_note,
                    camera_service_url=installation.camera_service_url,
                ))
                slots = session.scalars(
                    select(PalletSlotRecord)
                    .where(
                        PalletSlotRecord.camera_installation_id
                        == installation.camera_installation_id
                    )
                    .order_by(PalletSlotRecord.pallet_number)
                ).all()
                for slot in slots:
                    pallet_settings.append(PalletSettings(
                        pallet_id=slot.pallet_slot_id,
                        pallet_number=slot.pallet_number,
                        camera_id=camera.camera_id,
                        display_name=slot.display_name,
                        enabled=slot.monitoring_enabled,
                        low_stock_threshold_liters=(
                            slot.low_stock_threshold_liters
                        ),
                        email_rearm_margin_liters=(
                            slot.email_rearm_margin_liters
                        ),
                        plane_roi=active_roi_by_slot.get(
                            slot.pallet_slot_id,
                            default_pallet_payload(slot.pallet_number)["plane_roi"],
                        ),
                        single_box_labels=slot.single_box_labels,
                        mixed_box_groups=slot.mixed_box_groups,
                        reference_box_label=slot.reference_box_label,
                    ))

            catalog = [
                BoxClassSpec(
                    box_type_id=record.box_type_id,
                    label=record.label,
                    width_mm=record.width_mm,
                    depth_mm=record.depth_mm,
                    height_mm=record.height_mm,
                )
                for record in session.scalars(
                    select(BoxTypeRecord).order_by(BoxTypeRecord.box_type_id)
                ).all()
            ]
            return SystemSettings(
                cameras=camera_settings,
                pallets=pallet_settings,
                box_catalog=catalog,
                frame_count=measurement.floor_frame_count,
                measurement_frame_count=measurement.measurement_frame_count,
                measurement_concurrency=measurement.measurement_concurrency,
                warmup_frames=measurement.warmup_frames,
                grid_mm=measurement.grid_mm,
                pallet_height_mm=measurement.pallet_height_mm,
                occupied_height_mm=measurement.occupied_height_mm,
                monitor_interval_seconds=measurement.measurement_interval_seconds,
            )

    @staticmethod
    def sync_in_session(session: Session, settings: SystemSettings) -> None:
        now = datetime.now(UTC)
        requested_cameras = {camera.camera_id: camera for camera in settings.cameras}
        existing_cameras = {
            item.camera_id: item
            for item in session.scalars(select(CameraRecord)).all()
        }
        for camera_id, camera in requested_cameras.items():
            record = existing_cameras.get(camera_id)
            values = {
                "camera_code": camera.camera_code,
                "manufacturer": camera.manufacturer,
                "model_name": camera.model_name,
                "serial_number": camera.serial_number,
                "display_name": camera.display_name,
                "active": True,
            }
            if record is None:
                session.add(CameraRecord(camera_id=camera_id, **values))
            else:
                for field_name, value in values.items():
                    setattr(record, field_name, value)
        for camera_id, record in existing_cameras.items():
            if camera_id not in requested_cameras:
                record.active = False

        existing_locations = {
            item.location_id: item
            for item in session.scalars(select(LocationRecord)).all()
        }
        for camera in settings.cameras:
            record = (
                existing_locations.get(camera.location_id)
                if camera.location_id is not None
                else None
            )
            values = {
                "factory_name": camera.factory_name,
                "building_name": camera.building_name,
                "floor_name": camera.floor_name,
                "area_name": camera.area_name,
            }
            if record is None:
                if camera.location_id is not None:
                    raise ValueError(
                        f"場所IDがDBにありません: {camera.location_id}"
                    )
                record = LocationRecord(**values)
                session.add(record)
                session.flush()
                camera.location_id = record.location_id
                existing_locations[record.location_id] = record
            else:
                for field_name, value in values.items():
                    setattr(record, field_name, value)
        session.flush()

        active_installations = {
            item.camera_id: item
            for item in session.scalars(
                select(CameraInstallationRecord)
                .where(CameraInstallationRecord.removed_at.is_(None))
                .order_by(CameraInstallationRecord.camera_installation_id)
            ).all()
        }
        for camera_id, camera in requested_cameras.items():
            if camera.location_id is None:
                raise ValueError(f"場所IDを採番できませんでした: {camera_id}")
            installation = active_installations.get(camera_id)
            if installation is not None and installation_geometry_changed(
                installation, camera
            ):
                installation.removed_at = now
                installation = None
            if installation is None:
                session.add(CameraInstallationRecord(
                    camera_id=camera_id,
                    location_id=camera.location_id,
                    installed_at=now,
                    ip_address=camera.ip,
                    port=camera.port,
                    camera_service_url=camera.camera_service_url,
                    driver=camera.driver,
                    color_width=camera.width,
                    color_height=camera.height,
                    depth_width=camera.depth_width,
                    depth_height=camera.depth_height,
                    fps=camera.fps,
                    align_depth_to_color=camera.align_depth_to_color,
                    intrinsics=None,
                    distortion=None,
                    mounting_note=camera.mounting_note,
                ))
            else:
                installation.ip_address = camera.ip
                installation.port = camera.port
                installation.camera_service_url = camera.camera_service_url
                installation.driver = camera.driver
                installation.color_width = camera.width
                installation.color_height = camera.height
                installation.depth_width = camera.depth_width
                installation.depth_height = camera.depth_height
                installation.fps = camera.fps
                installation.align_depth_to_color = camera.align_depth_to_color
                installation.mounting_note = camera.mounting_note
        for camera_id, installation in active_installations.items():
            if camera_id not in requested_cameras:
                installation.removed_at = now

        session.flush()
        current_installations = {
            item.camera_id: item
            for item in session.scalars(
                select(CameraInstallationRecord).where(
                    CameraInstallationRecord.removed_at.is_(None)
                )
            ).all()
        }
        requested_slots = {
            (
                current_installations[pallet.camera_id].camera_installation_id,
                pallet.pallet_number,
            ): pallet
            for pallet in settings.pallets
            if pallet.camera_id in current_installations
        }
        existing_slots = {
            (slot.camera_installation_id, slot.pallet_number): slot
            for slot in session.scalars(select(PalletSlotRecord)).all()
        }
        for key, pallet in requested_slots.items():
            slot = existing_slots.get(key)
            values = {
                "display_name": pallet.display_name,
                "monitoring_enabled": pallet.enabled,
                "low_stock_threshold_liters": pallet.low_stock_threshold_liters,
                "email_rearm_margin_liters": pallet.email_rearm_margin_liters,
                "single_box_labels": list(pallet.single_box_labels),
                "mixed_box_groups": [list(group) for group in pallet.mixed_box_groups],
                "reference_box_label": pallet.reference_box_label,
            }
            if slot is None:
                session.add(PalletSlotRecord(
                    camera_installation_id=key[0],
                    pallet_number=key[1],
                    **values,
                ))
            else:
                for field_name, value in values.items():
                    setattr(slot, field_name, value)
        for key, slot in existing_slots.items():
            if key not in requested_slots:
                slot.monitoring_enabled = False

        measurement = session.get(MeasurementSettingsRecord, 1)
        values = {
            "measurement_interval_seconds": int(settings.monitor_interval_seconds),
            "measurement_frame_count": settings.measurement_frame_count,
            "measurement_concurrency": settings.measurement_concurrency,
            "floor_frame_count": settings.frame_count,
            "warmup_frames": settings.warmup_frames,
            "grid_mm": settings.grid_mm,
            "pallet_height_mm": settings.pallet_height_mm,
            "occupied_height_mm": settings.occupied_height_mm,
        }
        if measurement is None:
            session.add(MeasurementSettingsRecord(
                measurement_settings_id=1,
                **values,
            ))
        else:
            for field_name, value in values.items():
                setattr(measurement, field_name, value)


def installation_geometry_changed(
    installation: CameraInstallationRecord,
    camera: CameraSettings,
) -> bool:
    """過去Capture・校正と同じ撮影幾何として扱えない変更を判定する。"""
    return (
        installation.location_id,
        installation.driver,
        installation.color_width,
        installation.color_height,
        installation.depth_width,
        installation.depth_height,
        installation.align_depth_to_color,
    ) != (
        camera.location_id,
        camera.driver,
        camera.width,
        camera.height,
        camera.depth_width,
        camera.depth_height,
        camera.align_depth_to_color,
    )


def active_calibration_rois(session: Session) -> dict[int, list[float]]:
    """各パレット枠の現在有効な校正から、UI表示用ROIを復元する。"""
    rows = session.scalars(
        select(PalletCalibrationRecord)
        .where(PalletCalibrationRecord.status == "active")
        .order_by(
            PalletCalibrationRecord.created_at,
            PalletCalibrationRecord.pallet_calibration_id,
        )
    ).all()
    result: dict[int, list[float]] = {}
    for row in rows:
        roi = row.calibration_data.get("roi")
        if not isinstance(roi, list) or len(roi) != 4:
            raise ValueError(
                "有効なパレット校正のROIが不正です: "
                f"{row.pallet_calibration_id}"
            )
        result[row.pallet_slot_id] = [float(value) for value in roi]
    return result
