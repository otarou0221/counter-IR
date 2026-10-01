"""4サービス間のHTTP契約。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from cardboard_counter_v2.common.camera_contracts import (
    CameraDeviceSettings,
    CameraStreamStatus,
)
from cardboard_counter_v2.common.box_catalog import (
    BoxClassSpec,
    default_box_catalog,
    migrate_legacy_box_settings,
    validate_box_selections,
)
from cardboard_counter_v2.common.pallet_layout import (
    PALLETS_PER_CAMERA,
    normalize_fixed_pallet_layout,
)
from cardboard_counter_v2.common.operational_issues import OperationalIssue
from cardboard_counter_v2.common.planar_calibration import (
    PlanarCalibrationDefinition,
    PlanarRegionCalibration,
    ProjectionIntrinsicsSpec,
)


NormalizedRoi = Annotated[
    tuple[float, float, float, float],
    Field(description="left, top, right, bottom。各値は0〜1"),
]


def default_camera_service_url(camera_id: str) -> str:
    """camera_1→camera-1の規則で、専用コンテナの内部URLを作る。"""
    return f"http://{camera_id.replace('_', '-')}:8001"


class CameraSettings(CameraDeviceSettings):
    """Cardboard側だけが持つ、カメラ管理・設置情報付き設定。"""

    camera_code: str = Field(default="CAM-001", min_length=1, max_length=64)
    manufacturer: str | None = Field(default=None, max_length=100)
    model_name: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    location_id: int | None = Field(default=None, ge=1)
    factory_name: str | None = Field(default=None, max_length=100)
    building_name: str | None = Field(default=None, max_length=100)
    floor_name: str | None = Field(default=None, max_length=100)
    area_name: str | None = Field(default=None, max_length=100)
    mounting_note: str | None = Field(default=None, max_length=1000)
    camera_service_url: str = Field(
        default="http://camera-1:8001", min_length=1, max_length=500
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_management_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        camera_id = str(migrated.get("camera_id", "camera_1"))
        if migrated.get("camera_service_url") in (None, "", "http://camera:8000"):
            migrated["camera_service_url"] = default_camera_service_url(camera_id)
        suffix = "".join(character for character in camera_id if character.isdigit()) or "1"
        number = int(suffix)
        migrated.setdefault("camera_code", f"CAM-{number:03d}")
        if isinstance(migrated.get("location_id"), str):
            # 旧JSONのcamera単位文字列IDは、新DBへの保存時に自動採番する。
            migrated["location_id"] = None
        if "factory_name" not in migrated and "site_name" in migrated:
            migrated["factory_name"] = migrated.get("site_name")
        if "mounting_note" not in migrated:
            migrated["mounting_note"] = migrated.get(
                "mount_location_note", migrated.get("position_description")
            )
        return migrated

    @model_validator(mode="after")
    def normalize_management_fields(self) -> "CameraSettings":
        self.camera_code = self.camera_code.strip()
        self.camera_service_url = self.camera_service_url.strip()
        if not self.camera_code:
            raise ValueError("カメラ管理コードは空欄にできません")
        if not self.camera_service_url:
            raise ValueError("cameraサービスURLは空欄にできません")
        for field_name in (
            "manufacturer",
            "model_name",
            "serial_number",
            "factory_name",
            "building_name",
            "floor_name",
            "area_name",
            "mounting_note",
        ):
            value = getattr(self, field_name)
            setattr(self, field_name, value.strip() or None if value is not None else None)
        return self


class PalletSettings(BaseModel):
    pallet_id: int = Field(ge=1)
    pallet_number: int = Field(default=1, ge=1, le=PALLETS_PER_CAMERA)
    camera_id: str = Field(default="camera_1", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    low_stock_threshold_liters: float = Field(default=5.0, gt=0)
    email_rearm_margin_liters: float = Field(default=154.0, gt=0)
    plane_roi: NormalizedRoi
    single_box_labels: list[str] = Field(default_factory=lambda: ["cardboard_box"])
    mixed_box_groups: list[list[str]] = Field(default_factory=list)
    reference_box_label: str = "cardboard_box"

    @model_validator(mode="before")
    @classmethod
    def migrate_box_selection(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        migrated.pop("low_stock_threshold_boxes", None)
        if "pallet_number" not in migrated and isinstance(migrated.get("pallet_id"), int):
            migrated["pallet_number"] = 1 if migrated["pallet_id"] % 2 else 2
        if "display_name" not in migrated:
            migrated["display_name"] = f"パレット {migrated.get('pallet_number', 1)}"
        legacy_labels = migrated.pop("target_box_labels", None)
        if "single_box_labels" not in migrated and isinstance(legacy_labels, list):
            migrated["single_box_labels"] = legacy_labels
        migrated.setdefault("mixed_box_groups", [])
        raw_classes = value.get("box_classes")
        if not isinstance(raw_classes, list) or not raw_classes:
            return migrated
        labels = [str(item.get("label", "")).strip() for item in raw_classes if isinstance(item, dict)]
        labels = [label for label in labels if label]
        migrated.setdefault("single_box_labels", labels)
        if labels:
            migrated.setdefault("reference_box_label", labels[0])
        return migrated

    @model_validator(mode="after")
    def validate_rois(self) -> "PalletSettings":
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("パレット表示名は空欄にできません")
        left, top, right, bottom = self.plane_roi
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("plane_roiは0〜1の範囲でleft<right、top<bottomが必要です")
        self.single_box_labels = [
            label.strip() for label in self.single_box_labels if label.strip()
        ]
        self.mixed_box_groups = [
            [label.strip() for label in group if label.strip()]
            for group in self.mixed_box_groups
        ]
        self.reference_box_label = self.reference_box_label.strip()
        single_keys = [label.casefold() for label in self.single_box_labels]
        if len(single_keys) != len(set(single_keys)):
            raise ValueError("単品箱クラス名が重複しています")
        group_keys: set[tuple[str, ...]] = set()
        for group in self.mixed_box_groups:
            keys = [label.casefold() for label in group]
            if len(keys) < 2:
                raise ValueError("混在可能グループには2種類以上の箱が必要です")
            if len(keys) != len(set(keys)):
                raise ValueError("混在可能グループ内で箱クラス名が重複しています")
            group_key = tuple(sorted(keys))
            if group_key in group_keys:
                raise ValueError("同じ混在可能グループが重複しています")
            group_keys.add(group_key)
        labels = set(single_keys)
        labels.update(
            label.casefold()
            for group in self.mixed_box_groups
            for label in group
        )
        if not labels:
            raise ValueError("単品箱または混在可能グループを1つ以上設定してください")
        if self.reference_box_label.casefold() not in labels:
            raise ValueError("基準箱は対象箱クラスから選択してください")
        return self

    @property
    def box_rule_labels(self) -> list[str]:
        """単品・混在ルールに登場する箱名を、設定順で重複なく返す。"""
        labels: list[str] = []
        seen: set[str] = set()
        for label in self.single_box_labels:
            key = label.casefold()
            if key not in seen:
                seen.add(key)
                labels.append(label)
        for group in self.mixed_box_groups:
            for label in group:
                key = label.casefold()
                if key not in seen:
                    seen.add(key)
                    labels.append(label)
        return labels


def default_pallets() -> list[PalletSettings]:
    return [
        PalletSettings(
            pallet_id=1,
            pallet_number=1,
            camera_id="camera_1",
            plane_roi=(0.05, 0.15, 0.48, 0.95),
        ),
        PalletSettings(
            pallet_id=2,
            pallet_number=2,
            camera_id="camera_1",
            enabled=False,
            plane_roi=(0.52, 0.15, 0.95, 0.95),
        ),
    ]


class SystemSettings(BaseModel):
    method: Literal["pallet_plane_2roi"] = "pallet_plane_2roi"
    cameras: list[CameraSettings] = Field(default_factory=lambda: [CameraSettings()])
    box_catalog: list[BoxClassSpec] = Field(default_factory=default_box_catalog)
    pallets: list[PalletSettings] = Field(default_factory=default_pallets)
    frame_count: int = Field(default=30, ge=3, le=120)
    measurement_frame_count: int = Field(default=1, ge=1, le=120)
    measurement_concurrency: int = Field(default=3, ge=1, le=100)
    warmup_frames: int = Field(default=5, ge=0, le=60)
    grid_mm: float = Field(default=10.0, ge=2.0, le=50.0)
    pallet_height_mm: float = Field(default=150.0, gt=0, le=500.0)
    occupied_height_mm: float = Field(default=30.0, ge=1.0)
    monitor_interval_seconds: float = Field(
        default=600.0, ge=60.0, le=3600.0, multiple_of=60.0
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_settings(cls, value: Any) -> Any:
        migrated = migrate_legacy_box_settings(value)
        if not isinstance(migrated, dict):
            return migrated
        result = dict(migrated)
        if "cameras" not in result:
            camera = result.pop("camera", None)
            if isinstance(camera, dict):
                result["cameras"] = [{"camera_id": "camera_1", "display_name": "カメラ1", **camera}]
            else:
                result["cameras"] = [{"camera_id": "camera_1", "display_name": "カメラ1"}]
        pallets = result.get("pallets")
        if isinstance(pallets, list):
            result["pallets"] = [
                {"camera_id": "camera_1", **item} if isinstance(item, dict) else item
                for item in pallets
            ]
        return normalize_fixed_pallet_layout(result)

    @model_validator(mode="after")
    def validate_pallets(self) -> "SystemSettings":
        if not self.cameras:
            raise ValueError("少なくとも1台のカメラが必要です")
        camera_ids = [camera.camera_id.casefold() for camera in self.cameras]
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError("camera_idが重複しています")
        endpoints = [(camera.driver.casefold(), camera.ip.casefold(), camera.port) for camera in self.cameras]
        if len(endpoints) != len(set(endpoints)):
            raise ValueError("同じカメラ接続先が重複しています")
        for label, values in (
            ("camera_code", [camera.camera_code.casefold() for camera in self.cameras]),
            ("location_id", [camera.location_id for camera in self.cameras if camera.location_id is not None]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label}が重複しています")
        for label, values in (
            ("serial_number", [camera.serial_number.casefold() for camera in self.cameras if camera.serial_number]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label}が重複しています")
        if any(camera.align_depth_to_color for camera in self.cameras):
            raise ValueError("IR版ではRGBへのDepth整列を無効にしてください")
        known_cameras = set(camera_ids)
        ids = [pallet.pallet_id for pallet in self.pallets]
        if len(ids) != len(set(ids)):
            raise ValueError("pallet_idが重複しています")
        if not any(pallet.enabled for pallet in self.pallets):
            raise ValueError("少なくとも1つのパレットを有効にしてください")
        unknown = sorted({
            pallet.camera_id for pallet in self.pallets
            if pallet.camera_id.casefold() not in known_cameras
        })
        if unknown:
            raise ValueError(f"未登録のcamera_idがパレットに指定されています: {', '.join(unknown)}")
        for camera in self.cameras:
            numbers = sorted(
                pallet.pallet_number for pallet in self.pallets
                if pallet.camera_id.casefold() == camera.camera_id.casefold()
            )
            if numbers != list(range(1, PALLETS_PER_CAMERA + 1)):
                raise ValueError(f"{camera.camera_id}にはパレット1・2が1件ずつ必要です")
        validate_box_selections(
            self.box_catalog,
            (
                (
                    pallet.pallet_id,
                    pallet.single_box_labels,
                    pallet.mixed_box_groups,
                    pallet.reference_box_label,
                )
                for pallet in self.pallets
            ),
        )
        return self


class PrepareCaptureRequest(BaseModel):
    camera_id: str = "camera_1"
    batch_id: str
    purpose: Literal["floor", "current"]
    retention: Literal["persistent", "transient"] = "persistent"
    intrinsics: dict[str, object] | None = None


class CaptureManifest(BaseModel):
    """Cardboard撮影台帳。rgb_path/color_shapeはIRプレビューの互換キー。"""
    capture_id: str
    camera_id: str = "camera_1"
    purpose: str
    retention: Literal["persistent", "transient"] = "persistent"
    source_batch_id: str | None = None
    storage_version: int = Field(default=2, ge=1)
    depth_path: str
    xyz_path: str
    rgb_path: str
    ir_path: str | None = None
    projection: ProjectionIntrinsicsSpec | None = None
    distortion: dict[str, object] | None = None
    frame_count: int
    color_shape: tuple[int, int]
    depth_shape: tuple[int, int]
    depth_aligned_to_color: bool
    captured_at: str | None = None


class RoiReferenceCaptureRequest(BaseModel):
    camera_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class RoiReferenceCapture(BaseModel):
    camera_id: str
    capture_id: str
    captured_at: str | None = None
    rgb_path: str


class SavedCaptureSummary(BaseModel):
    capture_id: str
    camera_id: str = "camera_1"
    purpose: str
    retention: Literal["persistent", "transient"]
    captured_at: str
    frame_count: int
    color_shape: tuple[int, int]
    depth_shape: tuple[int, int]
    rgb_path: str


class RoiReferenceCatalog(BaseModel):
    captures: list[RoiReferenceCapture] = Field(default_factory=list)
    floor_captures: list[SavedCaptureSummary] = Field(default_factory=list)
    floor_capture_limit: int = Field(default=5, ge=1)


class SelectFloorCaptureRequest(BaseModel):
    camera_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    capture_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


class RoiReferenceChange(BaseModel):
    reference: RoiReferenceCapture
    removed_capture_ids: list[str] = Field(default_factory=list)


class CalibrationRequest(BaseModel):
    camera_id: str = "camera_1"
    baseline_capture_id: str
    baseline_capture: CaptureManifest | None = None
    pallets: list[PalletSettings]
    grid_mm: float = Field(default=10.0, ge=2.0, le=50.0)
    pallet_height_mm: float = Field(default=150.0, gt=0, le=500.0)


class PalletPlaneCalibrationResult(BaseModel):
    pallet_id: int
    pallet_number: int = Field(ge=1, le=PALLETS_PER_CAMERA)
    plane_roi: NormalizedRoi
    floor_plane_normal: tuple[float, float, float]
    floor_plane_offset: float
    pallet_height_mm: float
    plane_rmse_mm: float
    plane_inlier_count: int
    cell_size_mm: float


class CalibrationResult(BaseModel):
    calibration_id: str
    camera_id: str = "camera_1"
    baseline_capture_id: str
    created_at: str
    projection: ProjectionIntrinsicsSpec
    pallets: list[PalletPlaneCalibrationResult]

    def definition(self) -> PlanarCalibrationDefinition:
        return PlanarCalibrationDefinition(
            calibration_id=self.calibration_id,
            camera_id=self.camera_id,
            calibration_capture_id=self.baseline_capture_id,
            projection=self.projection,
            regions=[
                PlanarRegionCalibration(
                    region_id=pallet.pallet_number,
                    roi=pallet.plane_roi,
                    reference_plane_normal=pallet.floor_plane_normal,
                    reference_plane_offset=pallet.floor_plane_offset,
                    surface_offset_mm=pallet.pallet_height_mm,
                    cell_size_mm=pallet.cell_size_mm,
                )
                for pallet in self.pallets
            ],
        )


class CameraCalibrationResponse(BaseModel):
    camera_id: str
    calibration_id: str


class MeasurementRequest(BaseModel):
    camera_id: str = "camera_1"
    runtime_id: str | None = None
    calibration: PlanarCalibrationDefinition | None = None
    current_capture_id: str
    current_capture: CaptureManifest | None = None
    pallets: list[PalletSettings] = Field(default_factory=list)
    box_catalog: list[BoxClassSpec] = Field(default_factory=default_box_catalog)
    grid_mm: float = Field(default=10.0, ge=2.0, le=50.0)
    occupied_height_mm: float = Field(default=30.0, ge=1.0)
    generate_artifacts: bool = True
    generate_debug_stages: bool = False

    @property
    def calibration_id(self) -> str:
        if self.calibration is not None:
            return self.calibration.calibration_id
        return self.runtime_id or ""

    @model_validator(mode="after")
    def validate_debug_artifacts(self) -> "MeasurementRequest":
        if self.generate_debug_stages and not self.generate_artifacts:
            raise ValueError("段階別診断にはgenerate_artifacts=trueが必要です")
        if self.runtime_id is None and self.calibration is None:
            raise ValueError("runtime_idまたは校正定義が必要です")
        if self.runtime_id is None:
            validate_box_selections(
                self.box_catalog,
                (
                    (
                        pallet.pallet_id,
                        pallet.single_box_labels,
                        pallet.mixed_box_groups,
                        pallet.reference_box_label,
                    )
                    for pallet in self.pallets
                ),
            )
        return self


class PrepareMeasurementRuntimeRequest(BaseModel):
    calibration: PlanarCalibrationDefinition
    pallets: list[PalletSettings]
    box_catalog: list[BoxClassSpec]
    color_shape: tuple[int, int]
    depth_shape: tuple[int, int]

    @model_validator(mode="after")
    def validate_boxes(self) -> "PrepareMeasurementRuntimeRequest":
        validate_box_selections(
            self.box_catalog,
            (
                (
                    pallet.pallet_id,
                    pallet.single_box_labels,
                    pallet.mixed_box_groups,
                    pallet.reference_box_label,
                )
                for pallet in self.pallets
            ),
        )
        return self


class BoxCombinationCandidate(BaseModel):
    counts: dict[str, int]
    fitted_volume_liters: float
    residual_volume_liters: float


class BoxCombinationResult(BaseModel):
    solver_backend: Literal["cp-sat"] = "cp-sat"
    best: BoxCombinationCandidate
    alternatives: list[BoxCombinationCandidate]
    ambiguous: bool


class PalletMeasurement(BaseModel):
    pallet_id: int
    pallet_number: int = Field(default=1, ge=1, le=PALLETS_PER_CAMERA)
    camera_id: str = "camera_1"
    method: Literal["pallet_plane_2roi"] = "pallet_plane_2roi"
    volume_liters: float
    is_low_stock: bool | None = None
    low_stock_threshold_liters: float | None = Field(default=None, ge=0)
    estimated_boxes: float
    occupied_cells: int
    observed_cells: int
    plane_rmse_mm: float
    protrusion_components: int
    protrusion_cells: int
    protrusion_volume_liters: float
    box_combination: BoxCombinationResult | None = None
    height_grid_path: str | None = None
    plot_path: str | None = None
    debug_stages_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_pallet_number(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "pallet_number" in value:
            return value
        migrated = dict(value)
        pallet_id = migrated.get("pallet_id")
        if isinstance(pallet_id, int):
            migrated["pallet_number"] = 1 if pallet_id % 2 else 2
        return migrated


class CameraMeasurementRun(BaseModel):
    camera_id: str
    measurement_id: str
    calibration_id: str
    baseline_capture_id: str
    current_capture_id: str


class MeasurementResponse(BaseModel):
    measurement_id: str
    camera_runs: list[CameraMeasurementRun]
    pallets: list[PalletMeasurement]

    @model_validator(mode="before")
    @classmethod
    def migrate_single_camera_response(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "camera_runs" in value:
            return value
        required = ("measurement_id", "calibration_id", "baseline_capture_id", "current_capture_id")
        if not all(key in value for key in required):
            return value
        migrated = dict(value)
        migrated["camera_runs"] = [{
            "camera_id": str(value.get("camera_id", "camera_1")),
            "measurement_id": value["measurement_id"],
            "calibration_id": value["calibration_id"],
            "baseline_capture_id": value["baseline_capture_id"],
            "current_capture_id": value["current_capture_id"],
        }]
        return migrated


class MonitorStatus(BaseModel):
    running: bool = False
    stopping: bool = False
    interval_seconds: float
    completed_measurements: int = 0
    consecutive_errors: int = 0
    started_at: str | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    last_outcome: Literal["not_run", "success", "partial_failure", "failed"] = "not_run"
    last_issues: list[OperationalIssue] = Field(default_factory=list)
    email_notifications_enabled: bool = False
    last_email_sent_at: str | None = None
    last_email_error: str | None = None
    last_email_issue: OperationalIssue | None = None
    last_result: MeasurementResponse | None = None


class DebugDataCatalog(BaseModel):
    camera_id: str
    floor_captures: list[SavedCaptureSummary] = Field(default_factory=list)
    current_captures: list[SavedCaptureSummary] = Field(default_factory=list)
    current_has_more: bool = False
    current_capture_limit: int = Field(ge=1)


class DebugReplayRequest(BaseModel):
    baseline_capture_id: str
    current_capture_id: str

    @model_validator(mode="after")
    def validate_capture_ids(self) -> "DebugReplayRequest":
        if self.baseline_capture_id == self.current_capture_id:
            raise ValueError("床基準撮影と現在撮影には別のデータを選択してください")
        return self


class DebugCurrentCaptureRequest(BaseModel):
    camera_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class DatabaseStatus(BaseModel):
    enabled: bool
    connected: bool
    last_saved_at: str | None = None
    last_error: str | None = None


class SystemStatus(BaseModel):
    busy: bool
    method: Literal["pallet_plane_2roi"] = "pallet_plane_2roi"
    calibrated_camera_ids: list[str] = Field(default_factory=list)
    monitor: MonitorStatus
    cameras: list[CameraStreamStatus]
    database: DatabaseStatus
