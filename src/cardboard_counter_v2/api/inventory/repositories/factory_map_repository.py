"""工場マップ画像とパレット配置を永続化する。"""

from __future__ import annotations

from sqlalchemy import delete, select

from cardboard_counter_v2.api.dashboard_schemas import (
    FactoryMapSummary,
    PalletMapPlacement,
    PalletMapPlacementInput,
)
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import (
    FactoryMapRecord,
    PalletMapPlacementRecord,
    PalletSlotRecord,
)


class FactoryMapRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_map(
        self,
        *,
        display_name: str,
        factory_name: str | None,
        building_name: str | None,
        floor_name: str | None,
        image_data: bytes,
        image_width: int,
        image_height: int,
    ) -> FactoryMapSummary:
        with self.database.session() as session:
            record = FactoryMapRecord(
                display_name=display_name,
                factory_name=factory_name,
                building_name=building_name,
                floor_name=floor_name,
                image_media_type="image/png",
                image_width=image_width,
                image_height=image_height,
                image_data=image_data,
            )
            session.add(record)
            session.flush()
            return map_summary(record)

    def map_image(self, factory_map_id: int) -> tuple[str, bytes]:
        with self.database.session() as session:
            record = session.get(FactoryMapRecord, factory_map_id)
            if record is None:
                raise LookupError("工場マップが見つかりません")
            return record.image_media_type, record.image_data

    def delete_map(self, factory_map_id: int) -> FactoryMapSummary:
        """マップ画像と配置だけを削除し、在庫データは維持する。"""
        with self.database.session() as session:
            record = session.get(FactoryMapRecord, factory_map_id)
            if record is None:
                raise LookupError("工場マップが見つかりません")
            deleted = map_summary(record)
            session.delete(record)
            return deleted

    def save_placements(
        self,
        factory_map_id: int,
        placements: list[PalletMapPlacementInput],
    ) -> list[PalletMapPlacement]:
        requested = {item.pallet_slot_id: item for item in placements}
        if len(requested) != len(placements):
            raise ValueError("同じパレットの配置が重複しています")
        with self.database.session() as session:
            if session.get(FactoryMapRecord, factory_map_id) is None:
                raise LookupError("工場マップが見つかりません")
            enabled_slot_ids = set(session.scalars(
                select(PalletSlotRecord.pallet_slot_id).where(
                    PalletSlotRecord.monitoring_enabled.is_(True)
                )
            ).all())
            unknown = sorted(set(requested) - enabled_slot_ids)
            if unknown:
                raise ValueError(
                    "有効な監視対象パレットではありません: "
                    + ", ".join(str(item) for item in unknown)
                )

            current_on_map = session.scalars(
                select(PalletMapPlacementRecord).where(
                    PalletMapPlacementRecord.factory_map_id == factory_map_id
                )
            ).all()
            removed_ids = {
                record.pallet_map_placement_id
                for record in current_on_map
                if record.pallet_slot_id not in requested
            }
            if removed_ids:
                session.execute(delete(PalletMapPlacementRecord).where(
                    PalletMapPlacementRecord.pallet_map_placement_id.in_(removed_ids)
                ))

            existing = {
                record.pallet_slot_id: record
                for record in session.scalars(
                    select(PalletMapPlacementRecord).where(
                        PalletMapPlacementRecord.pallet_slot_id.in_(requested)
                    )
                ).all()
            }
            for pallet_slot_id, item in requested.items():
                record = existing.get(pallet_slot_id)
                if record is None:
                    record = PalletMapPlacementRecord(
                        pallet_slot_id=pallet_slot_id
                    )
                    session.add(record)
                record.factory_map_id = factory_map_id
                record.position_x_ratio = item.position_x_ratio
                record.position_y_ratio = item.position_y_ratio
            session.flush()
            return [
                placement_schema(record)
                for record in session.scalars(
                    select(PalletMapPlacementRecord)
                    .where(PalletMapPlacementRecord.factory_map_id == factory_map_id)
                    .order_by(PalletMapPlacementRecord.pallet_slot_id)
                ).all()
            ]


def map_summary(record: FactoryMapRecord) -> FactoryMapSummary:
    return FactoryMapSummary(
        factory_map_id=record.factory_map_id,
        display_name=record.display_name,
        factory_name=record.factory_name,
        building_name=record.building_name,
        floor_name=record.floor_name,
        image_width=record.image_width,
        image_height=record.image_height,
        image_url=f"/api/dashboard/maps/{record.factory_map_id}/image",
    )


def placement_schema(record: PalletMapPlacementRecord) -> PalletMapPlacement:
    return PalletMapPlacement(
        factory_map_id=record.factory_map_id,
        pallet_slot_id=record.pallet_slot_id,
        position_x_ratio=record.position_x_ratio,
        position_y_ratio=record.position_y_ratio,
    )
