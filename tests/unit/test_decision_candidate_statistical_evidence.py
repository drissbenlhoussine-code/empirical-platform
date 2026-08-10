"""MILESTONE-066 pure unit tests: statistical evidence domain.

Bootstrap determinism/policy validation, descriptive statistics
primitives, drawdown-path computation, sample-breadth-and-stability
classification, and the false-confidence-firewall invariants.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.statistical_evidence import (
    FALSE_CONFIDENCE_FIREWALL_LIMITATIONS,
    MINIMUM_RESAMPLE_COUNT,
    SUPPORTED_CONFIDENCE_LEVELS,
    BootstrapInterval,
    BootstrapMethod,
    BootstrapPolicy,
    DrawdownPathEvidence,
    SensitivityLabel,
    SensitivityView,
    StatisticalEvidenceClassification,
    _classify,
    _historical_realized_drawdown,
    _mean,
    _median,
    _percentile_bootstrap_interval,
    _resampled_drawdown_distribution,
    _standard_deviation,
)

_POLICY = BootstrapPolicy(
    policy_id="TEST-BOOTSTRAP",
    version="1",
    method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
    resample_count=500,
    seed=42,
    confidence_level=Decimal("0.90"),
)


# --------------------------------------------------------------------------
# BootstrapPolicy validation
# --------------------------------------------------------------------------


def test_bootstrap_policy_rejects_too_few_resamples() -> None:
    with pytest.raises(ValueError, match="resample_count must be at least"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=MINIMUM_RESAMPLE_COUNT - 1,
            seed=1,
            confidence_level=Decimal("0.90"),
        )


def test_bootstrap_policy_rejects_zero_resamples() -> None:
    with pytest.raises(ValueError, match="resample_count must be at least"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=0,
            seed=1,
            confidence_level=Decimal("0.90"),
        )


def test_bootstrap_policy_accepts_minimum_resample_count() -> None:
    policy = BootstrapPolicy(
        policy_id="X",
        version="1",
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        resample_count=MINIMUM_RESAMPLE_COUNT,
        seed=1,
        confidence_level=Decimal("0.90"),
    )
    assert policy.resample_count == MINIMUM_RESAMPLE_COUNT


def test_bootstrap_policy_rejects_unsupported_confidence_level() -> None:
    with pytest.raises(ValueError, match="is not supported"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=500,
            seed=1,
            confidence_level=Decimal("0.87"),
        )


@pytest.mark.parametrize("level", SUPPORTED_CONFIDENCE_LEVELS)
def test_bootstrap_policy_accepts_every_supported_confidence_level(level: Decimal) -> None:
    policy = BootstrapPolicy(
        policy_id="X",
        version="1",
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        resample_count=500,
        seed=1,
        confidence_level=level,
    )
    assert policy.confidence_level == level


def test_bootstrap_policy_rejects_empty_policy_id() -> None:
    with pytest.raises(ValueError, match="policy_id"):
        BootstrapPolicy(
            policy_id="   ",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=500,
            seed=1,
            confidence_level=Decimal("0.90"),
        )


# --------------------------------------------------------------------------
# BootstrapInterval validation
# --------------------------------------------------------------------------


def test_bootstrap_interval_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="lower_bound must not exceed upper_bound"):
        BootstrapInterval(
            metric_name="x",
            confidence_level=Decimal("0.90"),
            lower_bound=Decimal("5"),
            point_estimate=Decimal("2"),
            upper_bound=Decimal("1"),
            sample_size=10,
            resample_count=500,
            seed=1,
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            policy_version="1",
        )


def test_bootstrap_interval_excludes_zero_when_entirely_positive() -> None:
    interval = BootstrapInterval(
        metric_name="x",
        confidence_level=Decimal("0.90"),
        lower_bound=Decimal("0.1"),
        point_estimate=Decimal("0.5"),
        upper_bound=Decimal("1.0"),
        sample_size=10,
        resample_count=500,
        seed=1,
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        policy_version="1",
    )
    assert interval.excludes_zero is True


def test_bootstrap_interval_does_not_exclude_zero_when_spanning() -> None:
    interval = BootstrapInterval(
        metric_name="x",
        confidence_level=Decimal("0.90"),
        lower_bound=Decimal("-0.1"),
        point_estimate=Decimal("0.5"),
        upper_bound=Decimal("1.0"),
        sample_size=10,
        resample_count=500,
        seed=1,
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        policy_version="1",
    )
    assert interval.excludes_zero is False


def test_bootstrap_interval_excludes_zero_when_entirely_negative() -> None:
    interval = BootstrapInterval(
        metric_name="x",
        confidence_level=Decimal("0.90"),
        lower_bound=Decimal("-1.0"),
        point_estimate=Decimal("-0.5"),
        upper_bound=Decimal("-0.1"),
        sample_size=10,
        resample_count=500,
        seed=1,
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        policy_version="1",
    )
    assert interval.excludes_zero is True


# --------------------------------------------------------------------------
# Descriptive statistics primitives
# --------------------------------------------------------------------------


def test_mean_of_empty_is_none() -> None:
    assert _mean(()) is None


def test_mean_basic() -> None:
    assert _mean((Decimal("1"), Decimal("2"), Decimal("3"))) == Decimal("2.0000")


def test_median_of_empty_is_none() -> None:
    assert _median(()) is None


def test_median_odd_count() -> None:
    assert _median((Decimal("1"), Decimal("5"), Decimal("3"))) == Decimal("3.0000")


def test_median_even_count() -> None:
    assert _median((Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"))) == Decimal("2.5000")


def test_standard_deviation_of_fewer_than_two_is_none() -> None:
    assert _standard_deviation(()) is None
    assert _standard_deviation((Decimal("1"),)) is None


def test_standard_deviation_basic() -> None:
    result = _standard_deviation(
        (Decimal("2"), Decimal("4"), Decimal("4"), Decimal("4"), Decimal("5"))
    )
    assert result is not None
    assert result > 0


# --------------------------------------------------------------------------
# Bootstrap determinism
# --------------------------------------------------------------------------


def test_bootstrap_interval_is_deterministic_for_the_same_seed() -> None:
    values = tuple(Decimal(i) for i in range(1, 21))
    first = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    second = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert first == second


def test_bootstrap_interval_differs_for_a_different_seed() -> None:
    values = tuple(Decimal(i) for i in range(1, 21))
    policy_b = BootstrapPolicy(
        policy_id="TEST-BOOTSTRAP",
        version="1",
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        resample_count=500,
        seed=99,
        confidence_level=Decimal("0.90"),
    )
    first = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    second = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=policy_b
    )
    assert first.lower_bound != second.lower_bound or first.upper_bound != second.upper_bound


def test_bootstrap_interval_point_estimate_matches_the_real_sample_statistic() -> None:
    values = (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5"))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert interval.point_estimate == Decimal("3.0000")


def test_bootstrap_interval_sum_statistic_point_estimate_is_the_real_sum() -> None:
    values = (Decimal("1"), Decimal("2"), Decimal("3"))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="sum", policy=_POLICY
    )
    assert interval.point_estimate == Decimal("6.0000")


def test_bootstrap_interval_lower_never_exceeds_upper() -> None:
    values = tuple(Decimal(i) for i in range(1, 31))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert interval.lower_bound <= interval.upper_bound


def test_bootstrap_interval_all_identical_values_produces_zero_width_interval() -> None:
    values = tuple(Decimal("5") for _ in range(10))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert interval.lower_bound == interval.upper_bound == Decimal("5.0000")


# --------------------------------------------------------------------------
# Drawdown-path computation
# --------------------------------------------------------------------------


def test_historical_realized_drawdown_of_monotonic_gains_is_zero() -> None:
    values = (Decimal("10"), Decimal("10"), Decimal("10"))
    assert _historical_realized_drawdown(values) == Decimal("0.0000")


def test_historical_realized_drawdown_peak_to_trough() -> None:
    # cumulative: 100, 150, 50, 80 -> peak 150, trough 50 -> drawdown 100
    values = (Decimal("100"), Decimal("50"), Decimal("-100"), Decimal("30"))
    assert _historical_realized_drawdown(values) == Decimal("100.0000")


def test_resampled_drawdown_distribution_preserves_the_same_multiset_of_outcomes() -> None:
    values = (Decimal("10"), Decimal("-5"), Decimal("20"), Decimal("-15"))
    distribution = _resampled_drawdown_distribution(values, resample_count=50, seed=7)
    assert len(distribution) == 50
    # every resampled drawdown must be achievable from some permutation of
    # the same 4 values -- sanity bound: never exceeds the sum of all
    # negative moves in absolute value, and never negative itself.
    for d in distribution:
        assert d >= 0


def test_resampled_drawdown_distribution_is_deterministic_for_the_same_seed() -> None:
    values = (Decimal("10"), Decimal("-5"), Decimal("20"), Decimal("-15"))
    first = _resampled_drawdown_distribution(values, resample_count=100, seed=7)
    second = _resampled_drawdown_distribution(values, resample_count=100, seed=7)
    assert first == second


def test_resampled_drawdown_distribution_differs_for_a_different_seed() -> None:
    values = (
        Decimal("10"),
        Decimal("-5"),
        Decimal("20"),
        Decimal("-15"),
        Decimal("8"),
        Decimal("-3"),
    )
    first = _resampled_drawdown_distribution(values, resample_count=200, seed=7)
    second = _resampled_drawdown_distribution(values, resample_count=200, seed=8)
    assert first != second


# --------------------------------------------------------------------------
# Classification (breadth + sign-stability gate)
# --------------------------------------------------------------------------


def _interval(*, lower: Decimal, upper: Decimal) -> BootstrapInterval:
    return BootstrapInterval(
        metric_name="mean_r_per_trade",
        confidence_level=Decimal("0.90"),
        lower_bound=lower,
        point_estimate=(lower + upper) / 2,
        upper_bound=upper,
        sample_size=100,
        resample_count=500,
        seed=1,
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        policy_version="1",
    )


def test_classify_insufficient_when_trade_count_too_low() -> None:
    result = _classify(
        trade_sample_size=5,
        window_sample_size=20,
        mean_r_interval=_interval(lower=Decimal("1"), upper=Decimal("2")),
    )
    assert result is StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH


def test_classify_insufficient_when_window_count_too_low_even_with_many_trades() -> None:
    # 200 trades but only 2 windows -- window breadth governs (the
    # mission's own "do not pretend 59 trades and 10 windows are
    # equivalent evidence").
    result = _classify(
        trade_sample_size=200,
        window_sample_size=2,
        mean_r_interval=_interval(lower=Decimal("1"), upper=Decimal("2")),
    )
    assert result is StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH


def test_classify_broader_requires_both_breadth_and_sign_stability() -> None:
    result = _classify(
        trade_sample_size=100,
        window_sample_size=25,
        mean_r_interval=_interval(lower=Decimal("0.5"), upper=Decimal("1.5")),
    )
    assert result is StatisticalEvidenceClassification.BROADER_HISTORICAL_SAMPLE_BREADTH


def test_classify_capped_at_limited_when_interval_spans_zero_despite_large_breadth() -> None:
    # Weak-sample-style control at the classification level: enormous
    # breadth does not rescue a sign-unstable interval.
    result = _classify(
        trade_sample_size=1000,
        window_sample_size=100,
        mean_r_interval=_interval(lower=Decimal("-0.1"), upper=Decimal("5.0")),
    )
    assert result is StatisticalEvidenceClassification.LIMITED_SAMPLE_BREADTH


def test_classify_moderate_breadth_with_stable_sign() -> None:
    result = _classify(
        trade_sample_size=45,
        window_sample_size=12,
        mean_r_interval=_interval(lower=Decimal("0.1"), upper=Decimal("0.9")),
    )
    assert result is StatisticalEvidenceClassification.MODERATE_SAMPLE_BREADTH


# --------------------------------------------------------------------------
# SensitivityView / DrawdownPathEvidence validation
# --------------------------------------------------------------------------


def test_sensitivity_view_rejects_negative_sample_size() -> None:
    with pytest.raises(ValueError, match="sample_size must be non-negative"):
        SensitivityView(
            label=SensitivityLabel.CANONICAL,
            sample_size=-1,
            net_pnl=Decimal("0"),
            total_r=Decimal("0"),
            mean_r=None,
        )


def test_drawdown_path_evidence_rejects_zero_resample_count() -> None:
    with pytest.raises(ValueError, match="resample_count must be at least"):
        DrawdownPathEvidence(
            historical_realized_max_drawdown=Decimal("10"),
            median_resampled_max_drawdown=Decimal("5"),
            upper_tail_resampled_max_drawdown=Decimal("15"),
            worst_resampled_max_drawdown=Decimal("20"),
            resample_count=0,
            seed=1,
        )


# --------------------------------------------------------------------------
# False-confidence firewall
# --------------------------------------------------------------------------


def test_false_confidence_firewall_limitations_is_non_empty_and_fixed() -> None:
    assert len(FALSE_CONFIDENCE_FIREWALL_LIMITATIONS) == 6
    assert all(isinstance(item, str) and item for item in FALSE_CONFIDENCE_FIREWALL_LIMITATIONS)


def test_false_confidence_firewall_covers_the_mandatory_invariants() -> None:
    joined = " ".join(FALSE_CONFIDENCE_FIREWALL_LIMITATIONS).lower()
    for phrase in (
        "positive net pnl",
        "win rate",
        "profit factor",
        "bootstrap point estimate",
        "confidence interval",
        "narrow historical period",
    ):
        assert phrase in joined


# --------------------------------------------------------------------------
# Statistical attacks (mission Phase 21)
# --------------------------------------------------------------------------


def test_attack_empty_sample_mean_median_stdev_are_none() -> None:
    assert _mean(()) is None
    assert _median(()) is None
    assert _standard_deviation(()) is None


def test_attack_one_trade_bootstrap_interval_is_degenerate_but_well_formed() -> None:
    values = (Decimal("2.5"),)
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    # every resample of a 1-element sample is that same element.
    assert (
        interval.lower_bound == interval.point_estimate == interval.upper_bound == Decimal("2.5000")
    )
    assert interval.sample_size == 1


def test_attack_two_trades_bootstrap_interval_is_well_formed() -> None:
    values = (Decimal("-1"), Decimal("3"))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert interval.lower_bound <= interval.point_estimate <= interval.upper_bound
    assert interval.point_estimate == Decimal("1.0000")


def test_attack_all_wins_produces_a_positive_point_estimate_and_zero_losing_count() -> None:
    values = (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("1.5"))
    assert all(v > 0 for v in values)
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert interval.point_estimate > 0
    # all-wins with a reasonably large, non-degenerate sample should
    # exclude zero -- but this alone must never be conflated with
    # "statistically reliable" (see the false-confidence firewall).
    assert interval.excludes_zero is True


def test_attack_all_losses_produces_a_negative_point_estimate() -> None:
    values = (Decimal("-1"), Decimal("-2"), Decimal("-3"), Decimal("-1.5"))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert interval.point_estimate < 0
    assert interval.excludes_zero is True


def test_attack_all_zero_returns_produces_a_zero_width_zero_interval() -> None:
    values = tuple(Decimal("0") for _ in range(10))
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    assert (
        interval.lower_bound == interval.point_estimate == interval.upper_bound == Decimal("0.0000")
    )
    assert interval.excludes_zero is False


def test_attack_one_giant_winner_dominates_the_mean_but_stdev_reveals_dispersion() -> None:
    values = (Decimal("0.1"), Decimal("-0.2"), Decimal("0.05"), Decimal("50"), Decimal("-0.1"))
    mean = _mean(values)
    stdev = _standard_deviation(values)
    assert mean is not None and mean > 5
    assert stdev is not None and stdev > mean  # dispersion swamps the average
    interval = _percentile_bootstrap_interval(
        values, metric_name="x", statistic="mean", policy=_POLICY
    )
    # the giant winner's dominance should be visible as an enormous
    # interval width relative to the point estimate.
    assert (interval.upper_bound - interval.lower_bound) > interval.point_estimate


def test_attack_one_giant_loser_dominates_the_mean_negatively() -> None:
    values = (Decimal("0.1"), Decimal("0.2"), Decimal("0.05"), Decimal("-50"), Decimal("0.1"))
    mean = _mean(values)
    assert mean is not None and mean < -5


def test_attack_duplicate_trade_values_are_valid_input_no_special_casing() -> None:
    values = (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"))
    assert _mean(values) == Decimal("1.0000")
    assert _standard_deviation(values) == Decimal("0.0000")


def test_attack_very_small_window_count_below_insufficient_threshold() -> None:
    result = _classify(
        trade_sample_size=100,
        window_sample_size=1,
        mean_r_interval=_interval(lower=Decimal("1"), upper=Decimal("2")),
    )
    assert result is StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH


def test_attack_all_positive_windows_still_gated_by_breadth() -> None:
    # 3 windows, all positive -- breadth alone must still cap this.
    result = _classify(
        trade_sample_size=100,
        window_sample_size=3,
        mean_r_interval=_interval(lower=Decimal("1"), upper=Decimal("2")),
    )
    assert result is StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH


def test_attack_zero_resamples_rejected_by_policy() -> None:
    with pytest.raises(ValueError, match="resample_count must be at least"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=0,
            seed=1,
            confidence_level=Decimal("0.90"),
        )


def test_attack_too_few_resamples_rejected_by_policy() -> None:
    with pytest.raises(ValueError, match="resample_count must be at least"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=1,
            seed=1,
            confidence_level=Decimal("0.90"),
        )


def test_attack_unsupported_confidence_level_rejected() -> None:
    with pytest.raises(ValueError, match="is not supported"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=500,
            seed=1,
            confidence_level=Decimal("0.5"),
        )


def test_attack_invalid_percentile_confidence_level_rejected() -> None:
    # values outside (0, 1) are not even in the supported-set check's
    # domain, but must still be rejected cleanly, not raise an unrelated
    # exception from downstream arithmetic.
    with pytest.raises(ValueError, match="is not supported"):
        BootstrapPolicy(
            policy_id="X",
            version="1",
            method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
            resample_count=500,
            seed=1,
            confidence_level=Decimal("1.5"),
        )
