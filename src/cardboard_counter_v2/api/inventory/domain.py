"""DBやHTTPに依存しない低在庫状態の判定。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LowStockDecision:
    is_low_stock: bool


def evaluate_low_stock(
    volume_liters: float,
    threshold_liters: float,
) -> LowStockDecision:
    return LowStockDecision(is_low_stock=volume_liters <= threshold_liters)
