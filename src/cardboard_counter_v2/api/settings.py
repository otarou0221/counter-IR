"""DBを唯一の正本とするアプリ設定ストア。"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from cardboard_counter_v2.api.box_catalog_repository import BoxCatalogRepository
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.common.schemas import SystemSettings
from cardboard_counter_v2.common.storage import data_root, read_json


class SettingsStore:
    def __init__(
        self,
        repository: InventoryRepository,
        box_catalog_repository: BoxCatalogRepository,
        legacy_path: Path | None = None,
    ) -> None:
        self.repository = repository
        self.box_catalog_repository = box_catalog_repository
        self.legacy_path = legacy_path or data_root() / "config" / "settings.json"
        self.lock = Lock()
        self._cached: SystemSettings | None = None

    def migrate_legacy_json(self) -> bool:
        """旧settings.jsonをDBへ一度だけ移し、成功後に削除する。"""
        with self.lock:
            self.repository.database.initialize()
            if not self.legacy_path.is_file():
                return False
            settings = SystemSettings.model_validate(read_json(self.legacy_path))
            settings = self._save_to_database(settings)
            self.legacy_path.unlink()
            self._cached = settings.model_copy(deep=True)
            return True

    def load(self) -> SystemSettings:
        with self.lock:
            if self._cached is not None:
                return self._cached.model_copy(deep=True)
            self.repository.database.initialize()
            settings = self.repository.load_settings()
            if settings is None:
                settings = self._save_to_database(SystemSettings())
            self._cached = settings.model_copy(deep=True)
            return settings.model_copy(deep=True)

    def save(self, settings: SystemSettings) -> SystemSettings:
        with self.lock:
            saved = self._save_to_database(settings)
            self._cached = saved.model_copy(deep=True)
            return saved.model_copy(deep=True)

    def _save_to_database(self, settings: SystemSettings) -> SystemSettings:
        self.repository.database.initialize()
        with self.repository.database.session() as session:
            catalog = self.box_catalog_repository.replace_in_session(
                session,
                settings.box_catalog,
            )
            saved = settings.model_copy(update={"box_catalog": catalog})
            self.repository.sync_settings_in_session(session, saved)
        loaded = self.repository.load_settings()
        if loaded is None:
            raise RuntimeError("DBへ保存した設定を再読込みできません")
        return settings_with_transient_rois(loaded, settings)


def settings_with_transient_rois(
    loaded: SystemSettings,
    submitted: SystemSettings,
) -> SystemSettings:
    """校正確定前のROIだけをAPIメモリへ引き継ぐ。"""
    roi_by_slot = {
        (pallet.camera_id, pallet.pallet_number): pallet.plane_roi
        for pallet in submitted.pallets
    }
    return loaded.model_copy(update={
        "pallets": [
            pallet.model_copy(update={
                "plane_roi": roi_by_slot.get(
                    (pallet.camera_id, pallet.pallet_number),
                    pallet.plane_roi,
                )
            })
            for pallet in loaded.pallets
        ]
    })
