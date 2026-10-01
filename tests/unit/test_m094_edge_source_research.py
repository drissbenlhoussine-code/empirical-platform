"""MILESTONE-094 Phase 21 -- look-ahead safety, contemporaneity, alignment, and determinism
proofs for `usecases.m094_edge_source_research`.

Same "poison a future bar and confirm the value at `i` is unchanged" technique already
established for M057's ObservationWindow, M093's `compute_vwap_series`, and M093's Opening
Range/Relative Strength families.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.usecases import m094_edge_source_research as research

UTC = UTC
EASTERN = ZoneInfo("America/New_York")
_INSTRUMENT = Instrument("AAPL")


def _bar(minute: int, *, price: Decimal, volume: int = 1000, day: date = date(2026, 6, 1)) -> Bar:
    """`minute` is minutes since 09:30 ET on `day`. Flat OHLC at `price` unless the caller
    wants otherwise -- callers that need distinct high/low build `Bar(...)` directly."""
    start = datetime.combine(day, research.ENTRY_WINDOW_START_ET, tzinfo=EASTERN) - timedelta(
        minutes=30
    )
    ts = (start + timedelta(minutes=minute)).astimezone(UTC)
    return Bar(
        instrument=_INSTRUMENT,
        interval=BarInterval.ONE_MINUTE,
        timestamp=ts,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=volume,
    )


def _session(prices: list[int], *, day: date = date(2026, 6, 1)) -> tuple[Bar, ...]:
    return tuple(_bar(i, price=Decimal(p), day=day) for i, p in enumerate(prices))


# ---------------------------------------------------------------------------
# Look-ahead safety: rolling/backward-looking features
# ---------------------------------------------------------------------------


def test_rolling_return_percent_ignores_bars_after_i() -> None:
    base = [100, 101, 102, 103, 104, 105, 106]
    poisoned = [100, 101, 102, 103, 104, 999, 1]
    i = 4
    bars_base = _session(base)
    bars_poisoned = _session(poisoned)
    base_value = research.rolling_return_percent(bars_base, i, window=3)
    poisoned_value = research.rolling_return_percent(bars_poisoned, i, window=3)
    assert base_value == poisoned_value


def test_rolling_return_percent_none_before_window_available() -> None:
    bars = _session([100, 101, 102])
    assert research.rolling_return_percent(bars, 1, window=5) is None


def test_realized_volatility_percent_ignores_bars_after_i() -> None:
    base = [100, 102, 99, 103, 101, 104, 100]
    poisoned = [100, 102, 99, 103, 101, 500, 1]
    i = 4
    assert research.realized_volatility_percent(
        _session(base), i, window=4
    ) == research.realized_volatility_percent(_session(poisoned), i, window=4)


def test_range_compression_ratio_ignores_bars_after_i() -> None:
    base = [100, 105, 95, 102, 101, 103, 100]
    poisoned = [100, 105, 95, 102, 101, 999, 1]
    i = 4
    assert research.range_compression_ratio(
        _session(base), i, short_window=2, long_window=4
    ) == research.range_compression_ratio(_session(poisoned), i, short_window=2, long_window=4)


def test_momentum_sign_ignores_bars_after_i() -> None:
    base = [100, 101, 102, 103, 104]
    poisoned = [100, 101, 102, 103, 5]
    i = 2
    assert research.momentum_sign(_session(base), i, window=2) == research.momentum_sign(
        _session(poisoned), i, window=2
    )


def test_vwap_distance_percent_matches_cumulative_vwap_series() -> None:
    bars = _session([100, 101, 99, 102, 103])
    vwap_series = research.compute_vwap_series(bars)
    # vwap_series[i] is itself proven cumulative-only (M093's own test); confirm this
    # module's distance function derives purely from it, introducing no extra future read.
    for i in range(len(bars)):
        distance = research.vwap_distance_percent(bars, i, vwap_series)
        expected = (bars[i].close - vwap_series[i]) / vwap_series[i] * Decimal("100")
        assert distance == expected


# ---------------------------------------------------------------------------
# Contemporaneity: regime labels
# ---------------------------------------------------------------------------


def test_spy_vwap_position_ignores_bars_after_i() -> None:
    base = [100, 101, 99, 102, 103]
    poisoned = [100, 101, 99, 102, 1]
    i = 3
    vwap_base = research.compute_vwap_series(_session(base))
    vwap_poisoned = research.compute_vwap_series(_session(poisoned))
    assert research.spy_vwap_position(_session(base), i, vwap_base) == research.spy_vwap_position(
        _session(poisoned), i, vwap_poisoned
    )


def test_spy_session_return_sign_ignores_bars_after_i() -> None:
    base = [100, 101, 102, 103, 104]
    poisoned = [100, 101, 102, 103, 1]
    i = 3
    assert research.spy_session_return_sign(_session(base), i) == research.spy_session_return_sign(
        _session(poisoned), i
    )


def test_spy_session_return_sign_values() -> None:
    up = _session([100, 101, 102])
    down = _session([100, 99, 98])
    flat = _session([100, 100, 100])
    assert research.spy_session_return_sign(up, 2) == "SPY_SESSION_POSITIVE"
    assert research.spy_session_return_sign(down, 2) == "SPY_SESSION_NEGATIVE"
    assert research.spy_session_return_sign(flat, 2) == "SPY_SESSION_FLAT"


def test_trailing_volatility_bucket_ignores_bars_after_i() -> None:
    base = [100, 100.1, 99.9, 100.2, 100, 100.1, 100]
    poisoned = [100, 100.1, 99.9, 100.2, 100, 500, 1]
    bars_base = tuple(_bar(i, price=Decimal(str(p))) for i, p in enumerate(base))
    bars_poisoned = tuple(_bar(i, price=Decimal(str(p))) for i, p in enumerate(poisoned))
    i = 4
    low, high = Decimal("0.05"), Decimal("1")
    assert research.trailing_volatility_bucket(
        bars_base, i, window=4, low_cutoff=low, high_cutoff=high
    ) == research.trailing_volatility_bucket(
        bars_poisoned, i, window=4, low_cutoff=low, high_cutoff=high
    )


# ---------------------------------------------------------------------------
# Time-of-day bucketing must use Eastern time, not raw UTC (the exact bug M093 caught)
# ---------------------------------------------------------------------------


def test_time_of_day_bucket_uses_eastern_time_not_utc() -> None:
    # 14:30 UTC on a summer date is 10:30 ET (EDT, UTC-4) -- MORNING. If this function
    # bucketed by raw UTC hour (14), it would misclassify as AFTERNOON.
    ts = datetime(2026, 6, 1, 14, 30, tzinfo=UTC)
    assert research.time_of_day_bucket(ts) == "MORNING_10_12_ET"


def test_time_of_day_bucket_outside_entry_window_is_none() -> None:
    ts = datetime(2026, 6, 1, 13, 20, tzinfo=UTC)  # 09:20 ET, before the entry window
    assert research.time_of_day_bucket(ts) is None


def test_decision_marks_only_within_entry_window_and_on_alignment() -> None:
    bars = _session(list(range(100, 100 + 400)))  # 09:30..16:09 ET, 1-min bars
    marks = research.decision_marks(bars, every_minutes=5)
    for index in marks:
        et = bars[index].timestamp.astimezone(EASTERN).time()
        assert research.ENTRY_WINDOW_START_ET <= et < research.ENTRY_WINDOW_END_ET
        assert et.minute % 5 == 0


# ---------------------------------------------------------------------------
# Forward returns: must read ONLY strictly-after-i bars, and never fabricate a horizon the
# session doesn't reach
# ---------------------------------------------------------------------------


def test_forward_return_to_horizon_reads_strictly_after_i() -> None:
    bars = _session([100, 101, 102, 103, 104, 110])
    i = 0
    result = research.forward_return_to_horizon(bars, i, horizon_minutes=5)
    assert result == (Decimal("110") - Decimal("100")) / Decimal("100") * Decimal("100")


def test_forward_return_to_horizon_none_when_session_ends_first() -> None:
    bars = _session([100, 101, 102])
    i = 0
    assert research.forward_return_to_horizon(bars, i, horizon_minutes=60) is None


def test_forward_return_to_liquidation_uses_last_bar_at_or_before_1545_et() -> None:
    day = date(2026, 6, 1)
    minutes_to_1545 = 6 * 60 + 15  # 09:30 -> 15:45
    prices = [100] * (minutes_to_1545 + 10)
    prices[minutes_to_1545] = 150
    prices[minutes_to_1545 + 1] = 999  # after liquidation cutoff -- must be ignored
    bars = _session(prices, day=day)
    result = research.forward_return_to_liquidation(bars, 0)
    assert result == Decimal("50")


def test_forward_return_to_liquidation_none_at_last_bar() -> None:
    bars = _session([100, 101])
    assert research.forward_return_to_liquidation(bars, 1) is None


# ---------------------------------------------------------------------------
# Cross-sectional ranking: benchmark exclusion, timestamp alignment, deterministic order
# ---------------------------------------------------------------------------


def test_cross_sectional_rank_refuses_benchmark_symbols() -> None:
    with pytest.raises(ValueError, match="benchmark"):
        research.cross_sectional_rank(
            timestamp=datetime(2026, 6, 1, 14, 30, tzinfo=UTC),
            symbol_returns={"AAPL": Decimal("1"), "SPY": Decimal("0.5")},
            spy_return=Decimal("0.2"),
        )


def test_cross_sectional_rank_orders_by_outperformance_descending() -> None:
    ts = datetime(2026, 6, 1, 14, 30, tzinfo=UTC)
    observations = research.cross_sectional_rank(
        timestamp=ts,
        symbol_returns={"AAPL": Decimal("2"), "MSFT": Decimal("-1"), "NVDA": Decimal("5")},
        spy_return=Decimal("0"),
    )
    assert [o.symbol for o in observations] == ["NVDA", "AAPL", "MSFT"]
    assert [o.rank for o in observations] == [0, 1, 2]


def test_cross_sectional_rank_buckets_strongest_middle_weakest() -> None:
    ts = datetime(2026, 6, 1, 14, 30, tzinfo=UTC)
    returns = {
        sym: Decimal(val)
        for sym, val in zip(["A", "B", "C", "D", "E", "F"], [6, 5, 4, 3, 2, 1], strict=True)
    }
    observations = research.cross_sectional_rank(
        timestamp=ts, symbol_returns=returns, spy_return=Decimal("0")
    )
    by_symbol = {o.symbol: o.bucket for o in observations}
    assert by_symbol["A"] == "STRONGEST"
    assert by_symbol["B"] == "STRONGEST"
    assert by_symbol["E"] == "WEAKEST"
    assert by_symbol["F"] == "WEAKEST"
    assert by_symbol["C"] == "MIDDLE"
    assert by_symbol["D"] == "MIDDLE"


def test_common_timestamps_excludes_a_symbols_gap() -> None:
    full = _session([100, 101, 102, 103])
    gapped = tuple(b for i, b in enumerate(_session([100, 101, 102, 103])) if i != 2)
    common = research.common_timestamps({"FULL": full, "GAPPED": gapped})
    assert len(common) == 3
    assert full[2].timestamp not in common


def test_common_timestamps_empty_input() -> None:
    assert research.common_timestamps({}) == ()


# ---------------------------------------------------------------------------
# Selectivity buckets: deterministic
# ---------------------------------------------------------------------------


def test_selectivity_buckets_deterministic_across_repeated_calls() -> None:
    observations = [
        (Decimal(str(10 - i)), Decimal(str(i)), f"SYM{i % 3}", date(2026, 6, 1 + (i % 5)))
        for i in range(20)
    ]
    first = research.selectivity_buckets(observations)
    second = research.selectivity_buckets(observations)
    assert first == second


def test_selectivity_buckets_top_percentile_sizes() -> None:
    observations = [
        (Decimal(str(100 - i)), Decimal("0"), "SYM", date(2026, 6, 1)) for i in range(100)
    ]
    buckets = research.selectivity_buckets(observations, percentiles=(50, 10, 1))
    assert len(buckets[50]) == 50
    assert len(buckets[10]) == 10
    assert len(buckets[1]) == 1
    # Top-1 by count must be the single highest-strength observation (strength=100).
    assert buckets[1][0].strength == Decimal("100")


def test_selectivity_buckets_ties_broken_by_fixed_key_not_insertion_order() -> None:
    a = (Decimal("5"), Decimal("1"), "ZZZ", date(2026, 6, 2))
    b = (Decimal("5"), Decimal("2"), "AAA", date(2026, 6, 1))
    first = research.selectivity_buckets([a, b], percentiles=(100,))[100]
    second = research.selectivity_buckets([b, a], percentiles=(100,))[100]
    assert first == second
    assert [o.symbol for o in first] == ["AAA", "ZZZ"]


# ---------------------------------------------------------------------------
# Spearman rank correlation: transparent, no scipy
# ---------------------------------------------------------------------------


def test_spearman_rank_correlation_perfect_positive() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = research.spearman_rank_correlation(xs, ys)
    assert result is not None
    assert result == pytest.approx(1.0)


def test_spearman_rank_correlation_perfect_negative() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [50.0, 40.0, 30.0, 20.0, 10.0]
    result = research.spearman_rank_correlation(xs, ys)
    assert result is not None
    assert result == pytest.approx(-1.0)


def test_spearman_rank_correlation_none_for_too_few_observations() -> None:
    assert research.spearman_rank_correlation([1.0], [2.0]) is None


def test_spearman_rank_correlation_none_for_zero_variance() -> None:
    assert research.spearman_rank_correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


def test_opening_gap_percent_basic() -> None:
    assert research.opening_gap_percent(Decimal("100"), Decimal("102")) == Decimal("2")


def test_opening_gap_percent_zero_prior_close_is_none() -> None:
    assert research.opening_gap_percent(Decimal("0"), Decimal("100")) is None
