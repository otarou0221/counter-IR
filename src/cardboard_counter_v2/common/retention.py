"""保持期限の整理をリクエスト処理から分離する。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable


async def run_periodic_cleanup(
    cleanup: Callable[[], object],
    *,
    interval_seconds: float = 3600.0,
) -> None:
    """起動時と一定間隔で整理し、撮影・測定ループをブロックしない。"""
    interval = max(float(interval_seconds), 60.0)
    while True:
        try:
            await asyncio.to_thread(cleanup)
        except (OSError, ValueError):
            # 保持期限整理の失敗で本体サービスを停止しない。
            pass
        await asyncio.sleep(interval)
