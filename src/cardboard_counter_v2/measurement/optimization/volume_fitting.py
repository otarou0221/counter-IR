"""OR-Tools CP-SATで実測体積へ整数個の品目構成を当てはめる。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ortools.sat.python import cp_model


VOLUME_UNIT_MM3 = 1_000.0
DEFAULT_ALTERNATIVE_COUNT = 5
MAX_ENUMERATED_SOLUTIONS = 64
AMBIGUITY_RELATIVE_MARGIN = 0.025
AMBIGUITY_MINIMUM_ITEM_RATIO = 0.05


def ambiguity_margin_mm3(
    measured_volume_mm3: float,
    minimum_item_volume_mm3: float,
) -> float:
    """第2候補まで曖昧とみなす体積残差幅を返す。"""
    return max(
        max(float(measured_volume_mm3), 0.0) * AMBIGUITY_RELATIVE_MARGIN,
        max(float(minimum_item_volume_mm3), 0.0)
        * AMBIGUITY_MINIMUM_ITEM_RATIO,
    )


@dataclass(frozen=True)
class VolumeItem:
    label: str
    volume_mm3: float


@dataclass(frozen=True)
class VolumeCombination:
    counts: tuple[tuple[str, int], ...]
    fitted_volume_mm3: float
    residual_volume_mm3: float

    @property
    def total_count(self) -> int:
        return sum(count for _label, count in self.counts)


@dataclass(frozen=True)
class VolumeFitResult:
    best: VolumeCombination
    alternatives: tuple[VolumeCombination, ...]
    ambiguous: bool
    solver_backend: str = "cp-sat"


class PreparedVolumeOptimizer:
    """設定が変わるまで再利用する、体積整数最適化の固定情報。"""

    def __init__(
        self,
        items: Sequence[VolumeItem],
        *,
        max_alternatives: int = DEFAULT_ALTERNATIVE_COUNT,
    ) -> None:
        if not items:
            raise ValueError("最適化対象の品目がありません")
        labels: set[str] = set()
        normalized: list[VolumeItem] = []
        for item in items:
            label = item.label.strip()
            key = label.casefold()
            if not label or key in labels:
                raise ValueError("品目ラベルは空欄・重複にできません")
            if item.volume_mm3 <= 0:
                raise ValueError(f"{label}の体積は0より大きい値が必要です")
            labels.add(key)
            normalized.append(VolumeItem(label, float(item.volume_mm3)))
        self.items = tuple(normalized)
        self.volume_units = tuple(
            _volume_to_units(item.volume_mm3) for item in self.items
        )
        if any(volume <= 0 for volume in self.volume_units):
            raise ValueError("品目体積は1mL以上が必要です")
        self.max_alternatives = max(int(max_alternatives), 1)
        self.minimum_volume_mm3 = min(item.volume_mm3 for item in self.items)

    def solve(self, measured_volume_mm3: float) -> VolumeFitResult:
        """変化する実測体積だけを受け取り、最小誤差の整数構成を返す。"""
        measured = max(float(measured_volume_mm3), 0.0)
        target_units = _volume_to_units(measured)
        candidates = self._solve_candidates(
            target_units,
            ambiguity_margin_mm3=ambiguity_margin_mm3(
                measured,
                self.minimum_volume_mm3,
            ),
        )
        combinations = tuple(self._combination(measured, counts) for counts in candidates)
        best = combinations[0]
        ambiguity_margin = ambiguity_margin_mm3(
            measured,
            self.minimum_volume_mm3,
        )
        ambiguous = any(
            candidate.counts != best.counts
            and abs(candidate.residual_volume_mm3)
            <= abs(best.residual_volume_mm3) + ambiguity_margin
            for candidate in combinations[1:]
        )
        return VolumeFitResult(
            best=best,
            alternatives=combinations,
            ambiguous=ambiguous,
        )

    def _solve_candidates(
        self,
        target_units: int,
        *,
        ambiguity_margin_mm3: float,
    ) -> list[tuple[int, ...]]:
        if target_units <= 0:
            return [tuple(0 for _item in self.items)]
        model, count_vars, residual = _build_model(target_units, self.volume_units)
        model.minimize(residual)
        solver = _configured_solver()
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("箱構成の整数最適化に失敗しました")
        best = tuple(int(solver.value(variable)) for variable in count_vars)
        if self.max_alternatives <= 1:
            return [best]

        best_error = int(solver.value(residual))
        candidate_model, candidate_vars, candidate_residual = _build_model(
            target_units,
            self.volume_units,
        )
        candidate_model.add(
            candidate_residual
            <= best_error + _volume_to_units(ambiguity_margin_mm3)
        )
        collector = _CandidateCollector(candidate_vars)
        candidate_solver = _configured_solver()
        candidate_solver.parameters.enumerate_all_solutions = True
        candidate_solver.solve(candidate_model, collector)
        candidates = set(collector.counts)
        candidates.add(best)
        return sorted(
            candidates,
            key=lambda counts: (
                abs(
                    target_units
                    - sum(
                        count * volume
                        for count, volume in zip(counts, self.volume_units)
                    )
                ),
                counts,
            ),
        )[: self.max_alternatives]

    def _combination(
        self,
        measured_volume_mm3: float,
        counts: Sequence[int],
    ) -> VolumeCombination:
        fitted = sum(
            count * item.volume_mm3 for count, item in zip(counts, self.items)
        )
        return VolumeCombination(
            counts=tuple(
                (item.label, int(count))
                for item, count in zip(self.items, counts)
                if count > 0
            ),
            fitted_volume_mm3=fitted,
            residual_volume_mm3=measured_volume_mm3 - fitted,
        )


class PreparedVolumeRuleOptimizer:
    """単品候補と混在可能グループをまたいで、許可された構成だけを比較する。"""

    def __init__(
        self,
        single_items: Sequence[VolumeItem],
        mixed_item_groups: Sequence[Sequence[VolumeItem]],
        *,
        max_alternatives: int = DEFAULT_ALTERNATIVE_COUNT,
    ) -> None:
        rule_items = [(item,) for item in single_items]
        rule_items.extend(tuple(group) for group in mixed_item_groups)
        if not rule_items:
            raise ValueError("箱の単品候補または混在可能グループが必要です")
        if any(len(group) < 2 for group in mixed_item_groups):
            raise ValueError("混在可能グループには2種類以上の箱が必要です")
        self.optimizers = tuple(
            PreparedVolumeOptimizer(group, max_alternatives=max_alternatives)
            for group in rule_items
        )
        self.max_alternatives = max(int(max_alternatives), 1)
        self.minimum_volume_mm3 = min(
            item.volume_mm3 for group in rule_items for item in group
        )

    def solve(self, measured_volume_mm3: float) -> VolumeFitResult:
        measured = max(float(measured_volume_mm3), 0.0)
        by_counts: dict[tuple[tuple[str, int], ...], VolumeCombination] = {}
        for optimizer in self.optimizers:
            result = optimizer.solve(measured)
            for candidate in result.alternatives:
                counts = tuple(sorted(candidate.counts, key=lambda item: item[0].casefold()))
                normalized = VolumeCombination(
                    counts=counts,
                    fitted_volume_mm3=candidate.fitted_volume_mm3,
                    residual_volume_mm3=candidate.residual_volume_mm3,
                )
                previous = by_counts.get(counts)
                if previous is None or abs(normalized.residual_volume_mm3) < abs(
                    previous.residual_volume_mm3
                ):
                    by_counts[counts] = normalized
        combinations = sorted(
            by_counts.values(),
            key=lambda candidate: (
                abs(candidate.residual_volume_mm3),
                candidate.counts,
            ),
        )
        if not combinations:
            raise RuntimeError("箱構成の許可ルールから候補を作成できません")
        best = combinations[0]
        ambiguity_margin = ambiguity_margin_mm3(
            measured,
            self.minimum_volume_mm3,
        )
        alternatives = tuple(combinations[: self.max_alternatives])
        ambiguous = any(
            candidate.counts != best.counts
            and abs(candidate.residual_volume_mm3)
            <= abs(best.residual_volume_mm3) + ambiguity_margin
            for candidate in alternatives[1:]
        )
        return VolumeFitResult(
            best=best,
            alternatives=alternatives,
            ambiguous=ambiguous,
        )


def _build_model(
    target_units: int,
    volume_units: Sequence[int],
) -> tuple[cp_model.CpModel, list[cp_model.IntVar], cp_model.IntVar]:
    model = cp_model.CpModel()
    search_ceiling = target_units + max(volume_units)
    upper_bounds = [max(search_ceiling // volume + 1, 1) for volume in volume_units]
    count_vars = [
        model.new_int_var(0, upper, f"item_count_{index}")
        for index, upper in enumerate(upper_bounds)
    ]
    max_fitted = sum(
        upper * volume for upper, volume in zip(upper_bounds, volume_units)
    )
    fitted = model.new_int_var(0, max_fitted, "fitted_volume")
    model.add(
        fitted
        == sum(
            variable * volume
            for variable, volume in zip(count_vars, volume_units)
        )
    )
    max_delta = max(target_units, max_fitted - target_units)
    delta = model.new_int_var(-max_delta, max_delta, "volume_delta")
    residual = model.new_int_var(0, max_delta, "absolute_volume_error")
    model.add(delta == fitted - target_units)
    model.add_abs_equality(residual, delta)
    return model, count_vars, residual


def _configured_solver() -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    return solver


class _CandidateCollector(cp_model.CpSolverSolutionCallback):
    def __init__(self, count_vars: Sequence[cp_model.IntVar]) -> None:
        super().__init__()
        self._count_vars = tuple(count_vars)
        self.counts: list[tuple[int, ...]] = []

    def on_solution_callback(self) -> None:
        self.counts.append(
            tuple(int(self.value(variable)) for variable in self._count_vars)
        )
        if len(self.counts) >= MAX_ENUMERATED_SOLUTIONS:
            self.stop_search()


def _volume_to_units(volume_mm3: float) -> int:
    """CP-SATへ渡す連続体積を1mL単位の整数へ変換する。"""
    return max(int(round(float(volume_mm3) / VOLUME_UNIT_MM3)), 0)
