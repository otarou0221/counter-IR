import pytest

from cardboard_counter_v2.measurement.optimization.volume_fitting import (
    PreparedVolumeOptimizer,
    PreparedVolumeRuleOptimizer,
    VolumeItem,
)


@pytest.fixture
def optimizer() -> PreparedVolumeOptimizer:
    return PreparedVolumeOptimizer(
        [
            VolumeItem("small", 1_000_000.0),
            VolumeItem("large", 2_000_000.0),
        ]
    )


def test_cp_sat_finds_integer_box_combination(
    optimizer: PreparedVolumeOptimizer,
) -> None:
    result = optimizer.solve(5_000_000.0)

    assert result.solver_backend == "cp-sat"
    assert result.best.residual_volume_mm3 == 0
    assert sum(dict(result.best.counts).values()) >= 3


def test_equal_volume_compositions_are_reported_as_ambiguous(
    optimizer: PreparedVolumeOptimizer,
) -> None:
    result = optimizer.solve(4_000_000.0)
    exact = [
        candidate
        for candidate in result.alternatives
        if abs(candidate.residual_volume_mm3) < 1.0
    ]

    assert len(exact) >= 2
    assert result.ambiguous is True


def test_prepared_dimensions_are_reused_between_measurements(
    optimizer: PreparedVolumeOptimizer,
) -> None:
    prepared_units = optimizer.volume_units
    first = optimizer.solve(1_000_000.0)
    second = optimizer.solve(2_000_000.0)

    assert optimizer.volume_units is prepared_units
    assert first.best.total_count == 1
    assert second.best.residual_volume_mm3 == 0


def test_rule_optimizer_excludes_impossible_cross_group_combinations() -> None:
    optimizer = PreparedVolumeRuleOptimizer(
        single_items=[
            VolumeItem("A", 5_000_000.0),
            VolumeItem("B", 7_000_000.0),
        ],
        mixed_item_groups=[[
            VolumeItem("B", 7_000_000.0),
            VolumeItem("C", 3_000_000.0),
        ]],
    )

    result = optimizer.solve(13_000_000.0)

    assert dict(result.best.counts) == {"B": 1, "C": 2}
    assert all(
        not ({"A", "B"} <= set(dict(candidate.counts)))
        for candidate in result.alternatives
    )


def test_rule_optimizer_keeps_second_single_type_within_2_5_percent() -> None:
    optimizer = PreparedVolumeRuleOptimizer(
        single_items=[
            VolumeItem("再生250P", 43_200_000.0),
            VolumeItem("長岡金型50P・250P類", 77_121_000.0),
        ],
        mixed_item_groups=[],
    )

    result = optimizer.solve(1_311_258_240.0)

    assert dict(result.best.counts) == {"長岡金型50P・250P類": 17}
    assert any(
        dict(candidate.counts) == {"再生250P": 30}
        for candidate in result.alternatives
    )
    assert result.ambiguous is True
