"""SQLAlchemy ORMで管理する各種マスタ・校正・在庫履歴テーブル。"""

from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from cardboard_counter_v2.common.measurement_defaults import DEFAULT_HEIGHT_GRID_MM


def utc_now() -> datetime:
    return datetime.now(UTC)


json_type = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)
inet_type = String(45).with_variant(INET, "postgresql")


class Base(DeclarativeBase):
    pass


class BoxTypeRecord(Base):
    __tablename__ = "box_types"
    __table_args__ = (
        CheckConstraint("width_mm > 0", name="ck_box_type_width"),
        CheckConstraint("depth_mm > 0", name="ck_box_type_depth"),
        CheckConstraint("height_mm > 0", name="ck_box_type_height"),
    )

    box_type_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    width_mm: Mapped[float] = mapped_column(Float, nullable=False)
    depth_mm: Mapped[float] = mapped_column(Float, nullable=False)
    height_mm: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CameraRecord(Base):
    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    camera_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    installations: Mapped[list[CameraInstallationRecord]] = relationship(
        back_populates="camera"
    )


class CaptureRecord(Base):
    __tablename__ = "captures"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('floor', 'current')", name="ck_capture_purpose"
        ),
        CheckConstraint(
            "retention IN ('persistent', 'transient')",
            name="ck_capture_retention",
        ),
        CheckConstraint("frame_count > 0", name="ck_capture_frame_count"),
    )

    capture_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    camera_installation_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("camera_installations.camera_installation_id"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    retention: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_batch_id: Mapped[str | None] = mapped_column(String(100))
    storage_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    camera_installation: Mapped[CameraInstallationRecord] = relationship(
        back_populates="captures"
    )


class LocationRecord(Base):
    __tablename__ = "locations"

    location_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    factory_name: Mapped[str | None] = mapped_column(String(100))
    building_name: Mapped[str | None] = mapped_column(String(100))
    floor_name: Mapped[str | None] = mapped_column(String(100))
    area_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    installations: Mapped[list[CameraInstallationRecord]] = relationship(
        back_populates="location"
    )


class FactoryMapRecord(Base):
    __tablename__ = "factory_maps"
    __table_args__ = (
        CheckConstraint("image_width > 0", name="ck_factory_map_image_width"),
        CheckConstraint("image_height > 0", name="ck_factory_map_image_height"),
    )

    factory_map_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    factory_name: Mapped[str | None] = mapped_column(String(100))
    building_name: Mapped[str | None] = mapped_column(String(100))
    floor_name: Mapped[str | None] = mapped_column(String(100))
    image_media_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="image/png"
    )
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    pallet_placements: Mapped[list[PalletMapPlacementRecord]] = relationship(
        back_populates="factory_map",
        cascade="all, delete-orphan",
    )


class PalletMapPlacementRecord(Base):
    __tablename__ = "pallet_map_placements"
    __table_args__ = (
        CheckConstraint(
            "position_x_ratio >= 0 AND position_x_ratio <= 1",
            name="ck_pallet_map_placement_x_ratio",
        ),
        CheckConstraint(
            "position_y_ratio >= 0 AND position_y_ratio <= 1",
            name="ck_pallet_map_placement_y_ratio",
        ),
        UniqueConstraint("pallet_slot_id", name="uq_pallet_map_placement_slot"),
    )

    pallet_map_placement_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    factory_map_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("factory_maps.factory_map_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pallet_slot_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("pallet_slots.pallet_slot_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position_x_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    position_y_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    factory_map: Mapped[FactoryMapRecord] = relationship(
        back_populates="pallet_placements"
    )
    pallet_slot: Mapped[PalletSlotRecord] = relationship(
        back_populates="map_placement"
    )


class CameraInstallationRecord(Base):
    __tablename__ = "camera_installations"
    __table_args__ = (
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_installation_port"),
        CheckConstraint("color_width > 0 AND color_height > 0", name="ck_installation_color_size"),
        CheckConstraint("depth_width > 0 AND depth_height > 0", name="ck_installation_depth_size"),
        CheckConstraint("fps BETWEEN 1 AND 60", name="ck_installation_fps"),
        CheckConstraint(
            "removed_at IS NULL OR removed_at >= installed_at", name="ck_installation_period"
        ),
    )

    camera_installation_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.camera_id"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("locations.location_id"), nullable=False, index=True
    )
    ip_address: Mapped[str] = mapped_column(inet_type, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    camera_service_url: Mapped[str] = mapped_column(Text, nullable=False)
    driver: Mapped[str] = mapped_column(
        String(64), nullable=False, default="orbbec_network"
    )
    color_width: Mapped[int] = mapped_column(Integer, nullable=False, default=1280)
    color_height: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    depth_width: Mapped[int] = mapped_column(Integer, nullable=False, default=640)
    depth_height: Mapped[int] = mapped_column(Integer, nullable=False, default=576)
    fps: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    align_depth_to_color: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    intrinsics: Mapped[dict[str, object] | None] = mapped_column(json_type)
    distortion: Mapped[dict[str, object] | None] = mapped_column(json_type)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    mounting_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    camera: Mapped[CameraRecord] = relationship(back_populates="installations")
    location: Mapped[LocationRecord] = relationship(
        back_populates="installations"
    )
    pallet_calibrations: Mapped[list[PalletCalibrationRecord]] = relationship(
        back_populates="camera_installation"
    )
    captures: Mapped[list[CaptureRecord]] = relationship(
        back_populates="camera_installation"
    )
    pallet_slots: Mapped[list[PalletSlotRecord]] = relationship(
        back_populates="camera_installation"
    )


class PalletSlotRecord(Base):
    __tablename__ = "pallet_slots"
    __table_args__ = (
        UniqueConstraint(
            "camera_installation_id",
            "pallet_number",
            name="uq_pallet_slot_installation_number",
        ),
        CheckConstraint("pallet_number IN (1, 2)", name="ck_pallet_slot_number"),
        CheckConstraint(
            "low_stock_threshold_liters > 0",
            name="ck_pallet_slot_low_stock_threshold",
        ),
        CheckConstraint(
            "email_rearm_margin_liters > 0",
            name="ck_pallet_slot_email_rearm_margin",
        ),
    )

    pallet_slot_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    camera_installation_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("camera_installations.camera_installation_id"),
        nullable=False,
        index=True,
    )
    pallet_number: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    low_stock_threshold_liters: Mapped[float] = mapped_column(Float, nullable=False)
    email_rearm_margin_liters: Mapped[float] = mapped_column(Float, nullable=False)
    single_box_labels: Mapped[list[str]] = mapped_column(json_type, nullable=False)
    mixed_box_groups: Mapped[list[list[str]]] = mapped_column(json_type, nullable=False)
    reference_box_label: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    camera_installation: Mapped[CameraInstallationRecord] = relationship(
        back_populates="pallet_slots"
    )
    pallet_calibrations: Mapped[list[PalletCalibrationRecord]] = relationship(
        back_populates="pallet_slot"
    )
    map_placement: Mapped[PalletMapPlacementRecord | None] = relationship(
        back_populates="pallet_slot",
        cascade="all, delete-orphan",
        uselist=False,
    )


class MeasurementSettingsRecord(Base):
    __tablename__ = "measurement_settings"
    __table_args__ = (
        CheckConstraint(
            "measurement_settings_id = 1", name="ck_measurement_settings_singleton"
        ),
        CheckConstraint(
            "measurement_interval_seconds >= 60 AND "
            "measurement_interval_seconds <= 3600 AND "
            "measurement_interval_seconds % 60 = 0",
            name="ck_measurement_interval",
        ),
        CheckConstraint(
            "measurement_frame_count > 0", name="ck_measurement_frame_count"
        ),
        CheckConstraint(
            "measurement_concurrency > 0", name="ck_measurement_concurrency"
        ),
        CheckConstraint("floor_frame_count > 0", name="ck_floor_frame_count"),
        CheckConstraint("warmup_frames >= 0", name="ck_warmup_frames"),
        CheckConstraint("grid_mm > 0", name="ck_measurement_grid"),
        CheckConstraint("pallet_height_mm > 0", name="ck_pallet_height"),
        CheckConstraint("pallet_roi_margin_mm >= 0", name="ck_pallet_roi_margin"),
        CheckConstraint("occupied_height_mm > 0", name="ck_occupied_height"),
    )

    measurement_settings_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, default=1
    )
    measurement_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600
    )
    measurement_frame_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    measurement_concurrency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )
    floor_frame_count: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    warmup_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    grid_mm: Mapped[float] = mapped_column(
        Float, nullable=False, default=DEFAULT_HEIGHT_GRID_MM
    )
    pallet_height_mm: Mapped[float] = mapped_column(
        Float, nullable=False, default=150.0
    )
    pallet_roi_margin_mm: Mapped[float] = mapped_column(
        # 旧バージョンのDBとの互換用。測定処理では使用しない。
        Float, nullable=False, default=0.0
    )
    occupied_height_mm: Mapped[float] = mapped_column(
        Float, nullable=False, default=30.0
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PalletCalibrationRecord(Base):
    __tablename__ = "pallet_calibrations"
    __table_args__ = (
        UniqueConstraint(
            "calibration_id",
            "pallet_slot_id",
            name="uq_pallet_calibration_number",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded', 'invalid')",
            name="ck_pallet_calibration_status",
        ),
        CheckConstraint("grid_mm > 0", name="ck_pallet_calibration_grid"),
    )

    pallet_calibration_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    calibration_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    camera_installation_id: Mapped[int] = mapped_column(
        ForeignKey("camera_installations.camera_installation_id"),
        nullable=False,
        index=True,
    )
    pallet_slot_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("pallet_slots.pallet_slot_id"),
        nullable=False,
        index=True,
    )
    calibration_capture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    grid_mm: Mapped[float] = mapped_column(Float, nullable=False)
    calibration_data: Mapped[dict[str, object]] = mapped_column(
        json_type, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera_installation: Mapped[CameraInstallationRecord] = relationship(
        back_populates="pallet_calibrations"
    )
    pallet_slot: Mapped[PalletSlotRecord] = relationship(
        back_populates="pallet_calibrations"
    )
    realtime_measurements: Mapped[list[RealtimeMeasurementRecord]] = relationship(
        back_populates="pallet_calibration"
    )
    inventory_history: Mapped[list[InventoryHistoryRecord]] = relationship(
        back_populates="pallet_calibration"
    )


class RealtimeMeasurementRecord(Base):
    __tablename__ = "realtime_measurements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'failed')", name="ck_realtime_measurement_status"
        ),
        UniqueConstraint(
            "pallet_calibration_id",
            "finished_at",
            name="uq_realtime_measurement_pallet",
        ),
        CheckConstraint(
            "inventory_count IS NULL OR inventory_count >= 0",
            name="ck_realtime_measurement_inventory_count",
        ),
        CheckConstraint(
            "volume_liters IS NULL OR volume_liters >= 0",
            name="ck_realtime_measurement_volume",
        ),
        CheckConstraint(
            "low_stock_threshold_liters IS NULL OR low_stock_threshold_liters >= 0",
            name="ck_realtime_measurement_threshold",
        ),
        CheckConstraint(
            "email_rearm_margin_liters IS NULL OR email_rearm_margin_liters >= 0",
            name="ck_realtime_measurement_rearm_margin",
        ),
        CheckConstraint(
            "(status = 'success'"
            " AND measurement_capture_id IS NOT NULL"
            " AND inventory_count IS NOT NULL"
            " AND volume_liters IS NOT NULL"
            " AND box_counts IS NOT NULL"
            " AND is_low_stock IS NOT NULL"
            " AND low_stock_threshold_liters IS NOT NULL"
            " AND email_rearm_margin_liters IS NOT NULL"
            " AND error_message IS NULL)"
            " OR (status = 'failed'"
            " AND measurement_capture_id IS NULL"
            " AND inventory_count IS NULL"
            " AND volume_liters IS NULL"
            " AND box_counts IS NULL"
            " AND is_low_stock IS NULL"
            " AND low_stock_threshold_liters IS NULL"
            " AND email_rearm_margin_liters IS NULL"
            " AND email_sent_at IS NULL"
            " AND error_message IS NOT NULL)",
            name="ck_realtime_measurement_result_shape",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    pallet_calibration_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("pallet_calibrations.pallet_calibration_id"),
        nullable=False,
        index=True,
    )
    measurement_capture_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    inventory_count: Mapped[int | None] = mapped_column(Integer)
    volume_liters: Mapped[float | None] = mapped_column(Float)
    box_counts: Mapped[dict[str, int] | None] = mapped_column(json_type)
    is_low_stock: Mapped[bool | None] = mapped_column(Boolean)
    low_stock_threshold_liters: Mapped[float | None] = mapped_column(Float)
    email_rearm_margin_liters: Mapped[float | None] = mapped_column(Float)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    pallet_calibration: Mapped[PalletCalibrationRecord] = relationship(
        back_populates="realtime_measurements"
    )


class InventoryHistoryRecord(Base):
    __tablename__ = "inventory_history"
    __table_args__ = (
        UniqueConstraint(
            "pallet_calibration_id",
            "finished_at",
            name="uq_inventory_history_pallet_time",
        ),
        CheckConstraint(
            "inventory_count >= 0", name="ck_inventory_history_inventory_count"
        ),
        CheckConstraint(
            "volume_liters >= 0", name="ck_inventory_history_volume"
        ),
        CheckConstraint(
            "low_stock_threshold_liters >= 0",
            name="ck_inventory_history_threshold",
        ),
        CheckConstraint(
            "email_rearm_margin_liters >= 0",
            name="ck_inventory_history_rearm_margin",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    pallet_calibration_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("pallet_calibrations.pallet_calibration_id"),
        nullable=False,
        index=True,
    )
    measurement_capture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    inventory_count: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_liters: Mapped[float] = mapped_column(Float, nullable=False)
    box_counts: Mapped[dict[str, int]] = mapped_column(json_type, nullable=False)
    is_low_stock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    low_stock_threshold_liters: Mapped[float] = mapped_column(Float, nullable=False)
    email_rearm_margin_liters: Mapped[float] = mapped_column(Float, nullable=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    pallet_calibration: Mapped[PalletCalibrationRecord] = relationship(
        back_populates="inventory_history"
    )
