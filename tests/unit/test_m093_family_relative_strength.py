"""MILESTONE-093 Phase 9 -- Family E (relative strength): the "no self-benchmark leakage"
proof required by the mission (SPY/QQQ excluded, and no symbol's own future bars can reach a
decision through the benchmark comparison), plus determinism tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.opportunity_family_relative_strength import (
    BENCHMARK_SYMBOLS,
    RelativeStrengthPolicy,
    build_benchmark_index,
    build_relative_strength_plan_geometry,
    evaluate_relative_strength,
)


def _bar(*, symbol: str, minute: int, o: str, h: str, low: str, c: str, v: int = 1000) -> Bar:
    return Bar(
        instrument=Instrument(symbol),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 8, 3, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _policy(**overrides: object) -> RelativeStrengthPolicy:
    defaults: dict[str, object] = dict(
        lookback_bars=3,
        minimum_outperformance_percent=Decimal("1"),
        minimum_benchmark_return_percent=Decimal("0"),
        minimum_liquidity_shares=500,
        target_range_multiple=Decimal("2"),
        minimum_reward_risk_ratio=Decimal("1.2"),
    )
    defaults.update(overrides)
    return RelativeStrengthPolicy(**defaults)  # type: ignore[arg-type]


def test_benchmark_symbols_are_spy_and_qqq() -> None:
    assert BENCHMARK_SYMBOLS == frozenset({"SPY", "QQQ"})


def test_spy_and_qqq_are_excluded_before_any_bar_is_read() -> None:
    """THE NO-SELF-LEAKAGE PROOF the mission requires: for a benchmark symbol, the function
    refuses immediately -- an EMPTY benchmark index and a single, otherwise-insufficient bar
    are enough to prove no reference/lookback/benchmark-alignment logic ever runs for it."""
    policy = _policy(lookback_bars=5)
    single_bar = [_bar(symbol="SPY", minute=0, o="400", h="401", low="399", c="400.50")]
    for benchmark_symbol in ("SPY", "QQQ"):
        evaluation = evaluate_relative_strength(benchmark_symbol, single_bar, 0, {}, policy=policy)
        assert not evaluation.is_candidate
        assert evaluation.reason == "BENCHMARK_SYMBOL_EXCLUDED"
        assert evaluation.symbol_return_percent == Decimal("0")
        assert evaluation.benchmark_return_percent == Decimal("0")


def _outperformance_bars() -> tuple[list[Bar], list[Bar]]:
    symbol_bars = [
        _bar(symbol="AAPL", minute=0, o="100.00", h="100.50", low="99.50", c="100.00"),
        _bar(symbol="AAPL", minute=1, o="100.00", h="101.20", low="99.80", c="101.00"),
        _bar(symbol="AAPL", minute=2, o="101.00", h="102.20", low="100.80", c="102.00"),
        _bar(symbol="AAPL", minute=3, o="102.00", h="105.50", low="101.50", c="105.00", v=2000),
    ]
    benchmark_bars = [
        _bar(symbol="SPY", minute=0, o="400.00", h="400.50", low="399.50", c="400.00", v=5000),
        _bar(symbol="SPY", minute=1, o="400.00", h="401.00", low="399.80", c="400.50", v=5000),
        _bar(symbol="SPY", minute=2, o="400.50", h="401.20", low="400.20", c="401.00", v=5000),
        _bar(symbol="SPY", minute=3, o="401.00", h="401.80", low="400.80", c="401.50", v=5000),
    ]
    return symbol_bars, benchmark_bars


def test_a_genuine_outperformance_case_is_accepted() -> None:
    symbol_bars, benchmark_bars = _outperformance_bars()
    benchmark_index = build_benchmark_index(benchmark_bars)
    policy = _policy()
    evaluation = evaluate_relative_strength(
        "AAPL", symbol_bars, len(symbol_bars) - 1, benchmark_index, policy=policy
    )
    assert evaluation.is_candidate
    assert evaluation.reason is None
    geometry = build_relative_strength_plan_geometry(evaluation, policy=policy)
    assert geometry is not None
    assert geometry.stop_price == Decimal("99.50")  # reference window's own low


def test_appending_future_benchmark_bars_does_not_change_the_evaluation() -> None:
    """Proves the benchmark comparison reads ONLY the two exact timestamps it needs (now and
    lookback-bars-ago) -- extra bars in the benchmark index at LATER timestamps than the
    current decision instant must have zero effect on the result."""
    symbol_bars, benchmark_bars = _outperformance_bars()
    baseline_index = build_benchmark_index(benchmark_bars)
    policy = _policy()
    baseline = evaluate_relative_strength(
        "AAPL", symbol_bars, len(symbol_bars) - 1, baseline_index, policy=policy
    )

    poisoned_bars = [
        *benchmark_bars,
        _bar(symbol="SPY", minute=4, o="1000", h="1000", low="1000", c="1000", v=999_999),
        _bar(symbol="SPY", minute=5, o="1", h="1", low="1", c="1", v=999_999),
    ]
    poisoned_index = build_benchmark_index(poisoned_bars)
    poisoned_result = evaluate_relative_strength(
        "AAPL", symbol_bars, len(symbol_bars) - 1, poisoned_index, policy=policy
    )
    assert poisoned_result == baseline


def test_a_symbol_that_underperforms_the_benchmark_is_rejected() -> None:
    symbol_bars, benchmark_bars = _outperformance_bars()
    # Flatten the symbol's own move so it no longer outperforms SPY's ~0.375% return.
    symbol_bars[3] = _bar(
        symbol="AAPL", minute=3, o="100.00", h="100.90", low="99.80", c="100.80", v=2000
    )
    benchmark_index = build_benchmark_index(benchmark_bars)
    policy = _policy()
    evaluation = evaluate_relative_strength(
        "AAPL", symbol_bars, len(symbol_bars) - 1, benchmark_index, policy=policy
    )
    assert not evaluation.is_candidate
    assert evaluation.reason == "INSUFFICIENT_OUTPERFORMANCE"


def test_missing_benchmark_bar_at_the_required_timestamp_is_rejected_not_approximated() -> None:
    symbol_bars, benchmark_bars = _outperformance_bars()
    # Drop the benchmark bar at the reference-start timestamp -- no silent fallback allowed.
    sparse_benchmark_bars = [b for b in benchmark_bars if b.timestamp != symbol_bars[0].timestamp]
    benchmark_index = build_benchmark_index(sparse_benchmark_bars)
    policy = _policy()
    evaluation = evaluate_relative_strength(
        "AAPL", symbol_bars, len(symbol_bars) - 1, benchmark_index, policy=policy
    )
    assert not evaluation.is_candidate
    assert evaluation.reason == "INSUFFICIENT_BENCHMARK_EVIDENCE"
