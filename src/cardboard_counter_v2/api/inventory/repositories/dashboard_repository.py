"""現場ダッシュボード用の最新測定状態を読み出す。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import load_only, selectinload

from cardboard_counter_v2.api.dashboard_schemas import (
    DashboardCameraState,
    DashboardPalletState,
    FactoryDashboard,
)
from cardboard_counter_v2.api.dashboard_status import as_aware, camera_state
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    CameraInstallationRecord,
    CameraRecord,
    FactoryMapRecord,
    PalletCalibrationRecord,
    PalletSlotRecord,
    PalletMapPlacementRecord,
)
from cardboard_counter_v2.api.inventory.repositories.factory_map_repository import (
    map_summary,
    placement_schema,
)
from cardboard_counter_v2.api.inventory.repositories.realtime_measurement_queries import (
    latest_failure_by_installation,
    latest_success_by_calibration,
)


class DashboardRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_dashboard(
        self,
        *,
        monitor_running: bool,
        measurement_interval_seconds: float,
        now: datetime | None = None,
    ) -> FactoryDashboard:
        current_time = as_aware(now or datetime.now(UTC))
        stale_after = timedelta(
            seconds=max(measurement_interval_seconds * 2.0 + 300.0, 300.0)
        )
        with self.database.session() as session:
            maps = [
                map_summary(record)
                for record in session.scalars(
                    select(FactoryMapRecord)
                    .options(load_only(
                        FactoryMapRecord.factory_map_id,
                        FactoryMapRecord.display_name,
                        FactoryMapRecord.factory_name,
                        FactoryMapRecord.building_name,
                        FactoryMapRecord.floor_name,
                        FactoryMapRecord.image_width,
                        FactoryMapRecord.image_height,
                    ))
                    .order_by(FactoryMapRecord.factory_map_id)
                ).all()
            ]
            placements = {
                record.pallet_slot_id: placement_schema(record)
                for record in session.scalars(
                    select(PalletMapPlacementRecord)
                ).all()
            }
            cameras = session.scalars(
                select(CameraRecord)
                .where(CameraRecord.active.is_(True))
                .order_by(CameraRecord.camera_id)
            ).all()
            installations = session.scalars(
                select(CameraInstallationRecord)
                .options(selectinload(CameraInstallationRecord.location))
                .where(CameraInstallationRecord.removed_at.is_(None))
                .order_by(CameraInstallationRecord.camera_installation_id)
            ).all()
            installation_by_camera = {
                installation.camera_id: installation
                for installation in installations
            }
            slots_by_installation: dict[int, list[PalletSlotRecord]] = {}
            for slot in session.scalars(
                select(PalletSlotRecord)
                .where(PalletSlotRecord.monitoring_enabled.is_(True))
                .order_by(
                    PalletSlotRecord.camera_installation_id,
                    PalletSlotRecord.pallet_number,
                )
            ).all():
                slots_by_installation.setdefault(
                    slot.camera_installation_id, []
                ).append(slot)

            installation_ids = [item.camera_installation_id for item in installations]
            active_calibrations = session.scalars(
                select(PalletCalibrationRecord).where(
                    PalletCalibrationRecord.status == "active",
                    PalletCalibrationRecord.camera_installation_id.in_(installation_ids),
                )
            ).all() if installation_ids else []
            calibration_by_slot = {
                item.pallet_slot_id: item for item in active_calibrations
            }
            calibration_ids = [item.pallet_calibration_id for item in active_calibrations]
            latest_success = latest_success_by_calibration(session, calibration_ids)
            latest_failure = latest_failure_by_installation(session, calibration_ids)

            dashboard_cameras: list[DashboardCameraState] = []
            for camera in cameras:
                installation = installation_by_camera.get(camera.camera_id)
                slots = (
                    slots_by_installation.get(
                        installation.camera_installation_id, []
                    )
                    if installation is not None else []
                )
                pallet_states: list[DashboardPalletState] = []
                success_times: list[datetime] = []
                for slot in slots:
                    calibration = calibration_by_slot.get(slot.pallet_slot_id)
                    reading = (
                        latest_success.get(calibration.pallet_calibration_id)
                        if calibration is not None else None
                    )
                    if reading is None:
                        pallet_states.append(DashboardPalletState(
                            pallet_slot_id=slot.pallet_slot_id,
                            pallet_number=slot.pallet_number,
                            display_name=slot.display_name,
                            state="unavailable",
                            low_stock_threshold_liters=slot.low_stock_threshold_liters,
                            placement=placements.get(slot.pallet_slot_id),
                        ))
                        continue
                    success_times.append(as_aware(reading.finished_at))
                    pallet_states.append(DashboardPalletState(
                        pallet_slot_id=slot.pallet_slot_id,
                        pallet_number=slot.pallet_number,
                        display_name=slot.display_name,
                        state="low_stock" if reading.is_low_stock else "normal",
                        inventory_count=reading.inventory_count,
                        volume_liters=reading.volume_liters,
                        box_counts=reading.box_counts,
                        low_stock_threshold_liters=(
                            reading.low_stock_threshold_liters
                            if reading.low_stock_threshold_liters is not None
                            else slot.low_stock_threshold_liters
                        ),
                        measured_at=as_aware(reading.finished_at).isoformat(),
                        placement=placements.get(slot.pallet_slot_id),
                    ))

                failure = (
                    latest_failure.get(installation.camera_installation_id)
                    if installation is not None else None
                )
                last_success = max(success_times) if success_times else None
                last_failure = as_aware(failure.finished_at) if failure is not None else None
                state, message = camera_state(
                    monitor_running=monitor_running,
                    current_time=current_time,
                    stale_after=stale_after,
                    has_installation=installation is not None,
                    pallets=pallet_states,
                    last_success=last_success,
                    last_failure=last_failure,
                    failure_message=failure.error_message if failure is not None else None,
                )
                location = installation.location if installation is not None else None
                dashboard_cameras.append(DashboardCameraState(
                    camera_id=camera.camera_id,
                    camera_code=camera.camera_code,
                    display_name=camera.display_name,
                    factory_name=location.factory_name if location is not None else None,
                    building_name=location.building_name if location is not None else None,
                    floor_name=location.floor_name if location is not None else None,
                    area_name=location.area_name if location is not None else None,
                    state=state,
                    state_message=message,
                    last_success_at=last_success.isoformat() if last_success else None,
                    last_failure_at=last_failure.isoformat() if last_failure else None,
                    pallets=pallet_states,
                ))

            return FactoryDashboard(
                generated_at=current_time.isoformat(),
                monitor_running=monitor_running,
                measurement_interval_seconds=measurement_interval_seconds,
                maps=maps,
                cameras=dashboard_cameras,
            )
