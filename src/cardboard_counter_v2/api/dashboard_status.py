"""ダッシュボードに表示するカメラ状態を判定する。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cardboard_counter_v2.api.dashboard_schemas import DashboardPalletState


def as_aware(value: datetime) -> datetime:
    """DBが返す日時をUTCのtimezone-aware datetimeへ統一する。"""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def camera_state(
    *,
    monitor_running: bool,
    current_time: datetime,
    stale_after: timedelta,
    has_installation: bool,
    pallets: list[DashboardPalletState],
    last_success: datetime | None,
    last_failure: datetime | None,
    failure_message: str | None,
) -> tuple[str, str]:
    """測定状況を正常・低在庫・確認必要のいずれかへ集約する。"""
    if not monitor_running:
        return "unavailable", "監視停止中"
    if not has_installation:
        return "unavailable", "有効な設置情報がありません"
    if last_failure is not None and (
        last_success is None or last_failure >= last_success
    ):
        return "unavailable", f"測定エラー: {failure_message or '詳細なし'}"
    if not pallets:
        return "unavailable", "監視対象パレットがありません"
    if last_success is None or any(item.measured_at is None for item in pallets):
        return "unavailable", "未測定または未校正"
    oldest_measurement = min(
        as_aware(datetime.fromisoformat(item.measured_at))
        for item in pallets
        if item.measured_at is not None
    )
    if current_time - oldest_measurement > stale_after:
        return "unavailable", "測定結果の更新が遅れています"
    if any(item.state == "low_stock" for item in pallets):
        return "low_stock", "低在庫"
    return "normal", "正常"
