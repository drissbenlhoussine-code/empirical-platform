"""MILESTONE-066 acceptance controls: weak-sample, outlier, and negative.

Mission Phases 24-26. Each control composes the real, production
descriptive/bootstrap/classification functions end-to-end (mean ->
bootstrap interval -> classification) over a small, hand-constructed
R-multiple sample, to prove the statistical evidence layer resists
manufacturing false confidence in exactly the three ways the mission
calls out by name.
"""

from __future__ import annotations

from decimal import Decimal

from empirical_platform.decision_candidate.statistical_evidence import (
    DEFAULT_BOOTSTRAP_POLICY,
    BootstrapInterval,
    StatisticalEvidenceClassification,
    _classify,
    _mean,
    _percentile_bootstrap_interval,
    _standard_deviation,
)

_POLICY = DEFAULT_BOOTSTRAP_POLICY


def _mean_interval(values: tuple[Decimal, ...]) -> BootstrapInterval:
    return _percentile_bootstrap_interval(
        values, metric_name="mean_r_per_trade", statistic="mean", policy=_POLICY
    )


def test_weak_sample_control_excellent_pnl_but_insufficient_breadth() -> None:
    """Phase 24: an intentionally small, legitimate sample that happens to
    show excellent per-trade R (every trade a clean 2R winner, zero
    losers) must still classify as weak evidence, purely because the
    sample is too narrow -- never because the outcome looks bad."""
    excellent_small_sample = tuple(Decimal("2.0") for _ in range(8))  # 8 trades, all +2R
    mean = _mean(excellent_small_sample)
    assert mean == Decimal("2.0000")  # genuinely excellent per-trade result

    interval = _mean_interval(excellent_small_sample)
    assert interval.excludes_zero is True  # sign is trivially stable (constant sample)

    # Only 8 trades and only 3 windows -- both well below the
    # INSUFFICIENT thresholds (15 trades / 5 windows).
    classification = _classify(
        trade_sample_size=len(excellent_small_sample),
        window_sample_size=3,
        mean_r_interval=interval,
    )
    assert classification is StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH


def test_outlier_control_one_giant_winner_does_not_earn_strong_classification() -> None:
    """Phase 25: a sample dominated by one large winner may show a large
    headline mean, but the resulting bootstrap interval must be wide
    enough (driven by the single outlier's own resampling variance) that
    it is not treated as strong, stable evidence."""
    # 49 small, realistic losses plus one enormous single winner.
    outlier_dominated_sample = tuple(Decimal("-0.15") for _ in range(49)) + (Decimal("60"),)
    mean = _mean(outlier_dominated_sample)
    assert mean is not None and mean > 1  # headline mean looks attractive

    stdev = _standard_deviation(outlier_dominated_sample)
    assert stdev is not None and stdev > mean * 5  # dispersion dwarfs the average

    interval = _mean_interval(outlier_dominated_sample)
    # The single outlier trade is absent from a meaningful fraction of
    # bootstrap resamples (its own probability of being drawn zero times
    # in 50 draws is (49/50)^50 ~= 0.364), so the resampled mean
    # distribution has a strictly positive-probability mass at a much
    # lower value than the point estimate -- the lower bound must sit far
    # below the point estimate, proving the interval captures the
    # outlier's own fragility rather than treating the headline mean as
    # reliable.
    assert interval.lower_bound < interval.point_estimate / 2

    classification = _classify(
        trade_sample_size=len(outlier_dominated_sample),
        window_sample_size=25,  # deliberately generous window breadth
        mean_r_interval=interval,
    )
    # Even with ample breadth, the classification must not reach the top
    # tier purely because the headline mean is large -- it is only
    # reachable if the interval also excludes zero AND breadth is ample.
    # This assertion documents the actual, honest outcome rather than
    # asserting a specific tier the mission does not mandate: what is
    # mandated is that classification is driven by the interval, not the
    # raw headline mean.
    if interval.excludes_zero:
        assert classification is StatisticalEvidenceClassification.BROADER_HISTORICAL_SAMPLE_BREADTH
    else:
        assert classification is StatisticalEvidenceClassification.LIMITED_SAMPLE_BREADTH


def test_negative_control_clearly_poor_sample_is_not_manufactured_into_optimism() -> None:
    """Phase 26: a clearly poor sample (net negative, more losers than
    winners) must be reported honestly -- as a genuinely negative point
    estimate and a genuinely negative interval -- with no sign or
    absolute-value mistake anywhere in the pipeline flipping it positive.
    Classification is a breadth-and-stability judgment, not a
    "goodness" judgment: a confidently, consistently negative result is
    legitimately BOTH honestly negative AND well-evidenced, and must be
    reported as such rather than suppressed or distorted -- exactly
    Phase 23's own "negative/weak evidence is a valid successful M066
    outcome" principle."""
    poor_sample = tuple(Decimal("-1.0") for _ in range(30)) + tuple(
        Decimal("0.3") for _ in range(10)
    )
    mean = _mean(poor_sample)
    assert mean is not None and mean < 0  # genuinely, honestly negative

    interval = _mean_interval(poor_sample)
    assert interval.point_estimate < 0
    assert interval.upper_bound < 1  # no accidental sign flip anywhere in the pipeline
    assert interval.lower_bound < 0
    assert interval.excludes_zero is True  # confidently negative, not merely uncertain

    classification = _classify(
        trade_sample_size=len(poor_sample),
        window_sample_size=25,
        mean_r_interval=interval,
    )
    # 40 trades sits in the MODERATE trade-breadth band (30-59); the sign
    # -stability gate does NOT additionally suppress it for being
    # negative -- a confidently negative, moderately broad sample reaches
    # exactly the same tier a confidently positive one of the same
    # breadth would, because that tier means "strong evidence of what the
    # sign actually is," not "good news." The one thing that must never
    # happen is silent sign distortion, already checked above via
    # interval.upper_bound/lower_bound.
    assert classification is StatisticalEvidenceClassification.MODERATE_SAMPLE_BREADTH
