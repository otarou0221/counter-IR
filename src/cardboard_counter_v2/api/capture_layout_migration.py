"""DB登録済みCaptureをカメラ別・用途別の保存構成へ移行する。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import CaptureRecord
from cardboard_counter_v2.common.capture_policy import CURRENT_CAPTURE_STORAGE_VERSION
from cardboard_counter_v2.common.storage import capture_relative_dir, data_root


@dataclass(frozen=True)
class CaptureLayoutPlan:
    capture_id: str
    camera_id: str
    purpose: str
    source: Path
    destination: Path


@dataclass
class CaptureLayoutMigrationReport:
    candidates: int = 0
    migrated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.errors


class CaptureLayoutMigrator:
    """v2以前の平坦なCaptureを、再実行可能な手順でv3へ移す。"""

    def __init__(self, database: Database, root: Path | None = None) -> None:
        self.database = database
        self.root = (root or data_root()).resolve()

    def plans(self) -> list[CaptureLayoutPlan]:
        with self.database.session() as session:
            records = session.scalars(
                select(CaptureRecord)
                .options(selectinload(CaptureRecord.camera_installation))
                .where(
                    CaptureRecord.storage_version < CURRENT_CAPTURE_STORAGE_VERSION
                )
                .order_by(CaptureRecord.captured_at, CaptureRecord.capture_id)
            ).all()
            return [self._build_plan(record) for record in records]

    def validate(self) -> CaptureLayoutMigrationReport:
        report = CaptureLayoutMigrationReport()
        try:
            plans = self.plans()
        except Exception as exc:
            report.errors.append(str(exc))
            return report
        report.candidates = len(plans)
        for plan in plans:
            try:
                self._validate_plan(plan)
            except Exception as exc:
                report.errors.append(f"{plan.capture_id}: {exc}")
        return report

    def apply(self) -> CaptureLayoutMigrationReport:
        report = CaptureLayoutMigrationReport()
        try:
            plans = self.plans()
        except Exception as exc:
            report.errors.append(str(exc))
            return report
        report.candidates = len(plans)
        for plan in plans:
            try:
                active_path = self._validate_plan(plan)
                if active_path == plan.source:
                    plan.destination.parent.mkdir(parents=True, exist_ok=True)
                    plan.source.rename(plan.destination)
                self._mark_migrated(plan)
                report.migrated += 1
            except Exception as exc:
                report.errors.append(f"{plan.capture_id}: {exc}")
        return report

    def _build_plan(self, record: CaptureRecord) -> CaptureLayoutPlan:
        camera_id = record.camera_installation.camera_id
        source = self.root / capture_relative_dir(
            record.capture_id,
            camera_id=camera_id,
            purpose=record.purpose,
            storage_version=record.storage_version,
        )
        destination = self.root / capture_relative_dir(
            record.capture_id,
            camera_id=camera_id,
            purpose=record.purpose,
            storage_version=CURRENT_CAPTURE_STORAGE_VERSION,
        )
        return CaptureLayoutPlan(
            capture_id=record.capture_id,
            camera_id=camera_id,
            purpose=record.purpose,
            source=source,
            destination=destination,
        )

    @staticmethod
    def _validate_plan(plan: CaptureLayoutPlan) -> Path:
        source_exists = plan.source.exists()
        destination_exists = plan.destination.exists()
        if source_exists and destination_exists:
            raise ValueError("旧保存先と新保存先の両方が存在します")
        if not source_exists and not destination_exists:
            raise ValueError("Captureディレクトリが見つかりません")
        active = plan.source if source_exists else plan.destination
        if active.is_symlink() or not active.is_dir():
            raise ValueError(f"Captureディレクトリの形式が不正です: {active}")
        missing = [
            name for name in ("rgb.jpg", "depth.npz", "xyz.npz")
            if not (active / name).is_file()
        ]
        if missing:
            raise ValueError("必要なファイルがありません: " + ", ".join(missing))
        return active

    def _mark_migrated(self, plan: CaptureLayoutPlan) -> None:
        with self.database.session() as session:
            record = session.get(CaptureRecord, plan.capture_id)
            if record is None:
                raise ValueError("撮影台帳が見つかりません")
            if record.camera_installation.camera_id != plan.camera_id:
                raise ValueError("移行中にカメラ設置情報が変更されました")
            if record.purpose != plan.purpose:
                raise ValueError("移行中に撮影用途が変更されました")
            record.storage_version = CURRENT_CAPTURE_STORAGE_VERSION

