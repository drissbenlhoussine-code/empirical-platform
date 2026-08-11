"""MILESTONE-068 pure unit tests: cross-instrument dependence domain.

Return-series derivation (including the temporal firewall), pairwise
Pearson correlation math (perfect positive/negative, zero variance,
insufficient observations), matrix canonicalization/symmetry/diagonal
semantics, dependence-weighted concentration, concurrent-exposure-state
derivation, and classification thresholds. Exercises the internal
computational core directly with hand-constructed synthetic bar series
and M067 allocation decisions -- mirroring the established M066/M067
precedent of unit-testing private domain helpers directly, while
`build_portfolio_dependence_report`'s full upstream-binding pipeline is
exercised via real PostgreSQL acceptance tests against the real M064/M067
fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.historical_backtest import HistoricalInstrumentSeries
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.portfolio_dependence import (
    DEFAULT_DEPENDENCE_ESTIMATION_POLICY,
    ConcurrentExposureState,
    DependenceEstimationPolicy,
    DependenceEvidenceClassification,
    PairDependenceStatus,
    PairwiseDependenceEvidence,
    _classify,
    _dependence_weighted_concentration,
    _derive_return_series,
    _pearson_correlation,
    _simple_returns,
    build_concurrent_exposure_states,
    build_pairwise_dependence,
)
from empirical_platform.decision_candidate.portfolio_study import (
    PortfolioAllocationDecision,
    PortfolioAllocationOutcome,
)

_T0 = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
_INTERVAL = BarInterval.ONE_MINUTE


def _bar(symbol: str, minute_offset: int, close: str) -> Bar:
    price = Decimal(close)
    return Bar(
        instrument=Instrument(symbol),
        interval=_INTERVAL,
        timestamp=_T0 + timedelta(minutes=minute_offset),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=100,
    )


def _series(symbol: str, closes: list[str]) -> HistoricalInstrumentSeries:
    return HistoricalInstrumentSeries(
        instrument=Instrument(symbol),
        bars=tuple(_bar(symbol, i, c) for i, c in enumerate(closes)),
    )


_POLICY = DependenceEstimationPolicy(
    policy_id="TEST-POLICY", version="1", lookback_bar_count=10, minimum_overlapping_observations=3
)


# --------------------------------------------------------------------------
# DependenceEstimationPolicy validation
# --------------------------------------------------------------------------


def test_estimation_policy_rejects_too_small_lookback() -> None:
    with pytest.raises(ValueError, match="lookback_bar_count must be at least 3"):
        DependenceEstimationPolicy(
            policy_id="X", version="1", lookback_bar_count=2, minimum_overlapping_observations=2
        )


def test_estimation_policy_rejects_too_small_minimum_overlap() -> None:
    with pytest.raises(ValueError, match="minimum_overlapping_observations must be at least 2"):
        DependenceEstimationPolicy(
            policy_id="X", version="1", lookback_bar_count=10, minimum_overlapping_observations=1
        )


def test_estimation_policy_rejects_minimum_overlap_exceeding_lookback() -> None:
    with pytest.raises(ValueError, match="must not exceed lookback_bar_count"):
        DependenceEstimationPolicy(
            policy_id="X", version="1", lookback_bar_count=5, minimum_overlapping_observations=6
        )


def test_default_estimation_policy_is_valid() -> None:
    assert DEFAULT_DEPENDENCE_ESTIMATION_POLICY.lookback_bar_count == 20


# --------------------------------------------------------------------------
# PairwiseDependenceEvidence validation
# --------------------------------------------------------------------------


def test_pair_rejects_non_canonical_order() -> None:
    with pytest.raises(ValueError, match="canonical pair order"):
        PairwiseDependenceEvidence(
            instrument_a="MSFT",
            instrument_b="AAPL",
            observation_count=10,
            estimation_start=_T0,
            estimation_end=_T0,
            correlation=Decimal("0.5"),
            status=PairDependenceStatus.DEFINED,
        )


def test_pair_rejects_defined_without_correlation() -> None:
    with pytest.raises(ValueError, match="a DEFINED pair must carry a correlation value"):
        PairwiseDependenceEvidence(
            instrument_a="AAPL",
            instrument_b="MSFT",
            observation_count=10,
            estimation_start=_T0,
            estimation_end=_T0,
            correlation=None,
            status=PairDependenceStatus.DEFINED,
        )


def test_pair_rejects_non_defined_with_correlation() -> None:
    with pytest.raises(ValueError, match="a non-DEFINED pair must not carry a correlation value"):
        PairwiseDependenceEvidence(
            instrument_a="AAPL",
            instrument_b="MSFT",
            observation_count=1,
            estimation_start=_T0,
            estimation_end=_T0,
            correlation=Decimal("0.5"),
            status=PairDependenceStatus.INSUFFICIENT_OBSERVATIONS,
        )


def test_pair_rejects_correlation_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"correlation must be in \[-1, 1\]"):
        PairwiseDependenceEvidence(
            instrument_a="AAPL",
            instrument_b="MSFT",
            observation_count=10,
            estimation_start=_T0,
            estimation_end=_T0,
            correlation=Decimal("1.5"),
            status=PairDependenceStatus.DEFINED,
        )


# --------------------------------------------------------------------------
# ConcurrentExposureState validation
# --------------------------------------------------------------------------


def test_concurrent_state_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        ConcurrentExposureState(
            state_sequence=1,
            as_of_timestamp=_T0,
            open_instruments=("AAPL", "MSFT"),
            weights=(Decimal("1.0"),),
            nominal_concentration=Decimal("1.0"),
            dependence_aware_concentration=Decimal("1.0"),
            undefined_pair_count=0,
        )


def test_concurrent_state_rejects_empty_instruments() -> None:
    with pytest.raises(ValueError, match="at least 1 open instrument"):
        ConcurrentExposureState(
            state_sequence=1,
            as_of_timestamp=_T0,
            open_instruments=(),
            weights=(),
            nominal_concentration=Decimal("0"),
            dependence_aware_concentration=None,
            undefined_pair_count=0,
        )


# --------------------------------------------------------------------------
# Return series derivation
# --------------------------------------------------------------------------


def test_simple_returns_basic() -> None:
    bars = (
        (_T0, Decimal("100")),
        (_T0 + timedelta(minutes=1), Decimal("110")),
        (_T0 + timedelta(minutes=2), Decimal("99")),
    )
    returns = _simple_returns(bars)
    assert returns[_T0 + timedelta(minutes=1)] == Decimal("0.1")
    assert returns[_T0 + timedelta(minutes=2)] == Decimal("-0.1")


def test_simple_returns_skips_zero_close() -> None:
    bars = ((_T0, Decimal("0")), (_T0 + timedelta(minutes=1), Decimal("10")))
    returns = _simple_returns(bars)
    assert returns == {}


def test_derive_return_series_respects_temporal_firewall() -> None:
    """Bars strictly after `as_of` must never influence the derived
    return series (mission Phase 6)."""
    series = _series("AAPL", [str(100 + i) for i in range(20)])
    cutoff = _T0 + timedelta(minutes=5)
    early = _derive_return_series(series, as_of=cutoff, lookback_bar_count=100)
    assert all(ts <= cutoff for ts in early)
    assert max(early) == cutoff


def test_derive_return_series_respects_lookback_limit() -> None:
    series = _series("AAPL", [str(100 + i) for i in range(50)])
    cutoff = _T0 + timedelta(minutes=49)
    returns = _derive_return_series(series, as_of=cutoff, lookback_bar_count=5)
    assert len(returns) <= 5


def test_derive_return_series_empty_when_no_bars_at_or_before_cutoff() -> None:
    series = _series("AAPL", ["100", "101", "102"])
    cutoff = _T0 - timedelta(minutes=1)
    returns = _derive_return_series(series, as_of=cutoff, lookback_bar_count=10)
    assert returns == {}


# --------------------------------------------------------------------------
# Pearson correlation
# --------------------------------------------------------------------------


def test_pearson_correlation_perfect_positive() -> None:
    timestamps = [_T0 + timedelta(minutes=i) for i in range(5)]
    returns_a = {
        ts: Decimal(v) for ts, v in zip(timestamps, ["1", "2", "-1", "3", "0.5"], strict=True)
    }
    returns_b = dict(returns_a)  # identical series -> correlation 1
    correlation, n, status = _pearson_correlation(
        returns_a, returns_b, minimum_overlapping_observations=3
    )
    assert status is PairDependenceStatus.DEFINED
    assert correlation == Decimal("1.0000")
    assert n == 5


def test_pearson_correlation_perfect_negative() -> None:
    timestamps = [_T0 + timedelta(minutes=i) for i in range(5)]
    values = ["1", "2", "-1", "3", "0.5"]
    returns_a = {ts: Decimal(v) for ts, v in zip(timestamps, values, strict=True)}
    returns_b = {ts: -Decimal(v) for ts, v in zip(timestamps, values, strict=True)}
    correlation, _n, status = _pearson_correlation(
        returns_a, returns_b, minimum_overlapping_observations=3
    )
    assert status is PairDependenceStatus.DEFINED
    assert correlation == Decimal("-1.0000")


def test_pearson_correlation_zero_variance_is_undefined() -> None:
    timestamps = [_T0 + timedelta(minutes=i) for i in range(5)]
    returns_a = {ts: Decimal("0.01") for ts in timestamps}  # constant
    returns_b = {ts: Decimal(str(i)) for i, ts in enumerate(timestamps)}
    correlation, _n, status = _pearson_correlation(
        returns_a, returns_b, minimum_overlapping_observations=3
    )
    assert status is PairDependenceStatus.UNDEFINED_ZERO_VARIANCE
    assert correlation is None


def test_pearson_correlation_insufficient_observations() -> None:
    timestamps = [_T0 + timedelta(minutes=i) for i in range(2)]
    returns_a = {ts: Decimal(str(i)) for i, ts in enumerate(timestamps)}
    returns_b = {ts: Decimal(str(i * 2)) for i, ts in enumerate(timestamps)}
    correlation, n, status = _pearson_correlation(
        returns_a, returns_b, minimum_overlapping_observations=5
    )
    assert status is PairDependenceStatus.INSUFFICIENT_OBSERVATIONS
    assert correlation is None
    assert n == 2


def test_pearson_correlation_no_overlap_is_insufficient() -> None:
    returns_a = {_T0: Decimal("1")}
    returns_b = {_T0 + timedelta(days=1): Decimal("1")}
    correlation, n, status = _pearson_correlation(
        returns_a, returns_b, minimum_overlapping_observations=2
    )
    assert status is PairDependenceStatus.INSUFFICIENT_OBSERVATIONS
    assert n == 0
    assert correlation is None


def test_pearson_correlation_uses_only_aligned_timestamps() -> None:
    """No forward-filling: only genuinely shared timestamps are used
    (mission Phase 5/15)."""
    shared = [_T0 + timedelta(minutes=i) for i in range(4)]
    returns_a = {ts: Decimal(str(i)) for i, ts in enumerate(shared)}
    returns_a[_T0 + timedelta(hours=1)] = Decimal("999")  # not shared with b
    returns_b = {ts: Decimal(str(i * 2)) for i, ts in enumerate(shared)}
    correlation, n, status = _pearson_correlation(
        returns_a, returns_b, minimum_overlapping_observations=3
    )
    assert n == 4
    assert status is PairDependenceStatus.DEFINED
    assert correlation == Decimal("1.0000")  # b = 2*a is still perfectly linear


# --------------------------------------------------------------------------
# Matrix construction: canonicalization, symmetry, diagonal
# --------------------------------------------------------------------------


def test_build_pairwise_dependence_canonical_order_independent_of_dict_order() -> None:
    series_forward = {
        "AAPL": _series("AAPL", [str(100 + i) for i in range(15)]),
        "MSFT": _series("MSFT", [str(200 + i * 2) for i in range(15)]),
    }
    series_reversed = {"MSFT": series_forward["MSFT"], "AAPL": series_forward["AAPL"]}
    cutoff = _T0 + timedelta(minutes=14)
    forward = build_pairwise_dependence(series_forward, as_of=cutoff, policy=_POLICY)
    reversed_ = build_pairwise_dependence(series_reversed, as_of=cutoff, policy=_POLICY)
    assert forward == reversed_


def test_build_pairwise_dependence_includes_diagonal() -> None:
    series = {"AAPL": _series("AAPL", [str(100 + i) for i in range(15)])}
    cutoff = _T0 + timedelta(minutes=14)
    pairs = build_pairwise_dependence(series, as_of=cutoff, policy=_POLICY)
    assert len(pairs) == 1
    assert pairs[0].instrument_a == pairs[0].instrument_b == "AAPL"
    assert pairs[0].correlation == Decimal("1.0000")


def test_build_pairwise_dependence_no_duplicate_semantic_pairs() -> None:
    series = {
        "AAPL": _series("AAPL", [str(100 + i) for i in range(15)]),
        "MSFT": _series("MSFT", [str(200 - i) for i in range(15)]),
        "GOOG": _series("GOOG", [str(50 + i * 3) for i in range(15)]),
    }
    cutoff = _T0 + timedelta(minutes=14)
    pairs = build_pairwise_dependence(series, as_of=cutoff, policy=_POLICY)
    keys = [(p.instrument_a, p.instrument_b) for p in pairs]
    assert len(keys) == len(set(keys))
    # 3 instruments -> 3 diagonal + 3 off-diagonal = 6 canonical pairs
    assert len(pairs) == 6


# --------------------------------------------------------------------------
# Dependence-weighted concentration
# --------------------------------------------------------------------------


def test_dependence_weighted_concentration_perfect_correlation_equals_one() -> None:
    weights = (Decimal("0.3"), Decimal("0.3"), Decimal("0.4"))
    instruments = ("A", "B", "C")
    pairs = {
        (a, b): PairwiseDependenceEvidence(
            instrument_a=a,
            instrument_b=b,
            observation_count=10,
            estimation_start=_T0,
            estimation_end=_T0,
            correlation=Decimal("1.0000"),
            status=PairDependenceStatus.DEFINED,
        )
        for a in instruments
        for b in instruments
        if a <= b
    }
    result, undefined = _dependence_weighted_concentration(instruments, weights, pairs)
    assert result == Decimal("1.0000")
    assert undefined == 0


def test_dependence_weighted_concentration_zero_correlation_equals_hhi() -> None:
    weights = (Decimal("0.5"), Decimal("0.5"))
    instruments = ("A", "B")
    pairs = {
        ("A", "B"): PairwiseDependenceEvidence(
            instrument_a="A",
            instrument_b="B",
            observation_count=10,
            estimation_start=_T0,
            estimation_end=_T0,
            correlation=Decimal("0.0000"),
            status=PairDependenceStatus.DEFINED,
        ),
    }
    result, undefined = _dependence_weighted_concentration(instruments, weights, pairs)
    # w'Cw with off-diagonal 0 reduces to sum(w_i^2) = 0.25 + 0.25 = 0.5 (HHI)
    assert result == Decimal("0.5000")
    assert undefined == 0


def test_dependence_weighted_concentration_undefined_pair_treated_conservatively() -> None:
    """An undefined pair is treated as correlation=1 for concentration
    weighting -- never silently assumed independent (mission Phase 10)."""
    weights = (Decimal("0.5"), Decimal("0.5"))
    instruments = ("A", "B")
    result, undefined = _dependence_weighted_concentration(instruments, weights, {})
    assert result == Decimal("1.0000")
    assert undefined == 1


# --------------------------------------------------------------------------
# Concurrent exposure state derivation
# --------------------------------------------------------------------------


def _decision(
    seq: int, symbol: str, entry_min: int, exit_min: int, risk: str = "100"
) -> PortfolioAllocationDecision:
    return PortfolioAllocationDecision(
        opportunity_sequence=seq,
        source_window_id="BTRUN-0001",
        trade_sequence=seq,
        instrument_symbol=symbol,
        scan_rank=1,
        entry_timestamp=_T0 + timedelta(minutes=entry_min),
        exit_timestamp=_T0 + timedelta(minutes=exit_min),
        risk_amount=Decimal(risk),
        net_pnl=Decimal("10"),
        decision=PortfolioAllocationOutcome.ALLOCATED,
        rejection_reason=None,
    )


class _FakePortfolio:
    """Minimal stand-in exposing only `allocation_decisions`, matching
    what `build_concurrent_exposure_states` actually reads."""

    def __init__(self, decisions: tuple[PortfolioAllocationDecision, ...]) -> None:
        self.allocation_decisions = decisions


def test_concurrent_states_non_overlapping_positions_are_separate_states() -> None:
    decisions = (
        _decision(1, "AAPL", 0, 5),
        _decision(2, "MSFT", 10, 15),
    )
    states = build_concurrent_exposure_states(_FakePortfolio(decisions), {})  # type: ignore[arg-type]
    assert len(states) == 2
    assert all(len(s.open_instruments) == 1 for s in states)


def test_concurrent_states_overlapping_positions_combine_into_one_state() -> None:
    decisions = (
        _decision(1, "AAPL", 0, 10, risk="100"),
        _decision(2, "MSFT", 5, 15, risk="100"),
    )
    states = build_concurrent_exposure_states(_FakePortfolio(decisions), {})  # type: ignore[arg-type]
    # Two OPEN instants: t=0 (only AAPL open) and t=5 (both AAPL and MSFT open)
    assert len(states) == 2
    combined = next(s for s in states if len(s.open_instruments) == 2)
    assert set(combined.open_instruments) == {"AAPL", "MSFT"}
    assert combined.weights == (Decimal("0.5000"), Decimal("0.5000"))
    assert combined.nominal_concentration == Decimal("0.5000")


def test_concurrent_states_weights_reflect_risk_amount_proportions() -> None:
    decisions = (
        _decision(1, "AAPL", 0, 10, risk="300"),
        _decision(2, "MSFT", 0, 10, risk="100"),
    )
    states = build_concurrent_exposure_states(_FakePortfolio(decisions), {})  # type: ignore[arg-type]
    assert len(states) == 1
    state = states[0]
    assert state.weights == (Decimal("0.7500"), Decimal("0.2500"))
    # HHI = 0.75^2 + 0.25^2 = 0.5625 + 0.0625 = 0.625
    assert state.nominal_concentration == Decimal("0.6250")


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def _state(dep_aware: Decimal | None, count: int = 2) -> ConcurrentExposureState:
    return ConcurrentExposureState(
        state_sequence=1,
        as_of_timestamp=_T0,
        open_instruments=tuple(f"SYM{i}" for i in range(count)),
        weights=tuple(Decimal("1") / count for _ in range(count)),
        nominal_concentration=Decimal("0.5"),
        dependence_aware_concentration=dep_aware,
        undefined_pair_count=0,
    )


def test_classify_insufficient_when_no_multi_position_states() -> None:
    result = _classify(concurrent_states=(_state(None, count=1),), defined_pair_count=5)
    assert result is DependenceEvidenceClassification.INSUFFICIENT_DEPENDENCE_EVIDENCE


def test_classify_insufficient_when_no_defined_pairs() -> None:
    result = _classify(concurrent_states=(_state(Decimal("0.9")),), defined_pair_count=0)
    assert result is DependenceEvidenceClassification.INSUFFICIENT_DEPENDENCE_EVIDENCE


def test_classify_low_dependence() -> None:
    result = _classify(concurrent_states=(_state(Decimal("0.30")),), defined_pair_count=3)
    assert result is DependenceEvidenceClassification.LOW_OBSERVED_DEPENDENCE


def test_classify_mixed_dependence() -> None:
    result = _classify(concurrent_states=(_state(Decimal("0.55")),), defined_pair_count=3)
    assert result is DependenceEvidenceClassification.MIXED_OBSERVED_DEPENDENCE


def test_classify_high_dependence() -> None:
    result = _classify(concurrent_states=(_state(Decimal("0.90")),), defined_pair_count=3)
    assert result is DependenceEvidenceClassification.HIGH_OBSERVED_DEPENDENCE
