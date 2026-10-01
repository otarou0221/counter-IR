"""CaptureのDB台帳と保存件数整理を担当する。"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import HTTPException

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.ports import CaptureArtifactGateway


class CaptureRetentionService:
    def __init__(
        self,
        services: CaptureArtifactGateway,
        history: InventoryHistoryService | None = None,
    ) -> None:
        self.services = services
        self.history = history

    async def delete_capture(self, capture_id: str) -> None:
        if self.history is None:
            raise RuntimeError("Capture削除にはDB台帳が必要です")
        capture = await asyncio.to_thread(self.history.load_capture, capture_id)
        await self.services.delete_capture(capture)
        await asyncio.to_thread(self.history.delete_capture_record, capture_id)

    async def prune_current_captures(self, camera_id: str) -> None:
        if self.history is None:
            return
        excess = await asyncio.to_thread(
            self.history.excess_current_capture_ids,
            camera_id,
        )
        for capture_id in excess:
            with suppress(HTTPException):
                await self.delete_capture(capture_id)
