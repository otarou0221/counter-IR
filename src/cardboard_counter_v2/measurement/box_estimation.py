"""汎用体積最適化結果をCardboard測定APIの型へ変換する。"""

from __future__ import annotations

from cardboard_counter_v2.common.schemas import (
    BoxCombinationCandidate,
    BoxCombinationResult,
)
from cardboard_counter_v2.measurement.optimization.volume_fitting import (
    PreparedVolumeRuleOptimizer,
    VolumeCombination,
)


def estimate_box_combination(
    optimizer: PreparedVolumeRuleOptimizer,
    measured_volume_mm3: float,
) -> BoxCombinationResult:
    result = optimizer.solve(measured_volume_mm3)
    return BoxCombinationResult(
        solver_backend="cp-sat",
        best=_candidate(result.best),
        alternatives=[_candidate(item) for item in result.alternatives],
        ambiguous=result.ambiguous,
    )


def _candidate(value: VolumeCombination) -> BoxCombinationCandidate:
    return BoxCombinationCandidate(
        counts=dict(value.counts),
        fitted_volume_liters=value.fitted_volume_mm3 / 1_000_000.0,
        residual_volume_liters=value.residual_volume_mm3 / 1_000_000.0,
    )
