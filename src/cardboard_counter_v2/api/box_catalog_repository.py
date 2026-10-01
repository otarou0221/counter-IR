"""DBを正本とする共通箱種類マスタ。"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import BoxTypeRecord
from cardboard_counter_v2.common.box_catalog import BoxClassSpec


class BoxCatalogRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.initialize()

    def load(self) -> list[BoxClassSpec]:
        with self.database.session() as session:
            records = session.scalars(
                select(BoxTypeRecord).order_by(BoxTypeRecord.box_type_id)
            ).all()
            return [self._to_spec(record) for record in records]

    def replace(self, catalog: list[BoxClassSpec]) -> list[BoxClassSpec]:
        """画面のカタログ全体でDBを同期する。

        IDがある行は名称変更後も同じ行として更新し、IDのない新規行は
        箱名で既存行を確認してから追加する。
        """
        with self.database.session() as session:
            return self.replace_in_session(session, catalog)

    def replace_in_session(
        self,
        session: Session,
        catalog: list[BoxClassSpec],
    ) -> list[BoxClassSpec]:
        """設定全体の保存と同じトランザクションで箱マスターを同期する。"""
        existing = session.scalars(select(BoxTypeRecord)).all()
        by_id = {record.box_type_id: record for record in existing}
        by_label = {record.label.casefold(): record for record in existing}
        claimed_ids: set[int] = set()
        resolved: list[tuple[BoxClassSpec, BoxTypeRecord]] = []

        for item in catalog:
            record = None
            if item.box_type_id is not None:
                record = by_id.get(item.box_type_id)
                if record is None:
                    raise ValueError(
                        f"箱種類IDがDBに存在しません: {item.box_type_id}"
                    )
            if record is None:
                label_match = by_label.get(item.label.casefold())
                if (
                    label_match is not None
                    and label_match.box_type_id not in claimed_ids
                ):
                    record = label_match
            if record is None:
                record = BoxTypeRecord(
                    label=f"__new_{uuid4().hex}",
                    width_mm=item.width_mm,
                    depth_mm=item.depth_mm,
                    height_mm=item.height_mm,
                )
                session.add(record)
                session.flush()
            if record.box_type_id in claimed_ids:
                raise ValueError(f"箱種類IDが重複しています: {record.box_type_id}")
            claimed_ids.add(record.box_type_id)
            resolved.append((item, record))

        for record in existing:
            if record.box_type_id not in claimed_ids:
                session.delete(record)
        session.flush()

        # UNIQUE制約に抵触せず、同じ保存で箱名の入れ替えも許可する。
        for item, record in resolved:
            if record.label != item.label:
                record.label = f"__renaming_{record.box_type_id}_{uuid4().hex}"
        session.flush()

        records: list[BoxTypeRecord] = []
        for item, record in resolved:
            record.label = item.label
            record.width_mm = item.width_mm
            record.depth_mm = item.depth_mm
            record.height_mm = item.height_mm
            records.append(record)
        session.flush()
        return [self._to_spec(record) for record in records]

    @staticmethod
    def _to_spec(record: BoxTypeRecord) -> BoxClassSpec:
        return BoxClassSpec(
            box_type_id=record.box_type_id,
            label=record.label,
            width_mm=record.width_mm,
            depth_mm=record.depth_mm,
            height_mm=record.height_mm,
        )
