"""MILESTONE-094 Phases 1, 5-16 -- information-value research primitives.

THIS IS NOT A STRATEGY. Every function here answers "does this contemporaneously-knowable
piece of information carry predictive structure after realistic costs", never "would this
have made money as a trading rule". There is no entry/stop/target geometry, no position
sizing, no broker-write surface anywhere in this module.

HOLDOUT CARRY-FORWARD (Phase 1). M094 does not define a second holdout guard -- it reuses
`m093_holdout_guard.assert_not_holdout` (via `m093_research_framework.fetch_session_bars_guarded`)
verbatim, the same single fetch point M093 itself used. See `tools/m094_edge_source_study.py`,
the one and only place M094 fetches a bar, and `tests/unit/test_m094_holdout_carry_forward.py`,
which proves that path still refuses before any network call for the locked range.

LOOK-AHEAD SAFETY. Every feature/label function below takes `bars: Sequence[Bar]` and an
index `i`, and is contractually allowed to read `bars[0:i+1]` ONLY. `tests/unit/
test_m094_edge_source_research.py` proves this with the same "poison a future bar, assert
the value at `i` is unchanged" technique already used for M057's ObservationWindow, M093's
`compute_vwap_series`, and M093's Opening Range/Relative Strength families.

TIMEZONE DISCIPLINE. Fetched bar timestamps are UTC. All time-of-day bucketing, gap
measurement, and session-boundary logic below converts to `America/New_York` FIRST -- this
is the exact bug M093's own `regime-analysis.md` caught and fixed (an early pass bucketed by
raw UTC and produced zero trades in two of three buckets); every function here is written to
avoid that mistake from the start rather than needing the same fix twice.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.market_data import Bar
from empirical_platform.decision_candidate.opportunity_family_relative_strength import (
    BENCHMARK_SYMBOLS,
)
from empirical_platform.decision_candidate.opportunity_family_vwap_pullback import (
    compute_vwap_series,
)

__all__ = [
    "BENCHMARK_SYMBOLS",
    "ENTRY_WINDOW_END_ET",
    "ENTRY_WINDOW_START_ET",
    "EASTERN",
    "HORIZON_MINUTES",
    "MANDATORY_LIQUIDATION_ET",
    "CrossSectionalObservation",
    "ForwardReturnObservation",
    "RegimeLabel",
    "TimeOfDayBucket",
    "compute_vwap_series",
    "common_timestamps",
    "cross_sectional_rank",
    "decision_marks",
    "forward_return_percent",
    "forward_return_to_horizon",
    "forward_return_to_liquidation",
    "momentum_sign",
    "opening_gap_percent",
    "range_compression_ratio",
    "realized_volatility_percent",
    "rolling_return_percent",
    "selectivity_buckets",
    "since_open_return_percent",
    "spearman_rank_correlation",
    "spy_session_return_sign",
    "spy_vwap_position",
    "time_of_day_bucket",
    "trailing_volatility_bucket",
    "vwap_distance_percent",
]

EASTERN = ZoneInfo("America/New_York")

ENTRY_WINDOW_START_ET = time(10, 0)
ENTRY_WINDOW_END_ET = time(15, 30)
MANDATORY_LIQUIDATION_ET = time(15, 45)

#: Minutes ahead of a decision mark the horizon study measures (Phase 5). "To liquidation"
#: is handled separately since it is a variable, not fixed, horizon.
HORIZON_MINUTES: tuple[int, ...] = (5, 15, 30, 60, 120)

_HUNDRED = Decimal("100")


def _et(ts: datetime) -> datetime:
    return ts.astimezone(EASTERN)


# ---------------------------------------------------------------------------
# Phase 5/6 -- backward-looking per-symbol features (rolling, trailing-only)
# ---------------------------------------------------------------------------


def rolling_return_percent(bars: Sequence[Bar], i: int, window: int) -> Decimal | None:
    """Trailing `window`-bar close-to-close return ending at `i`, using ONLY
    `bars[i-window+1 : i+1]`. `None` if fewer than `window` bars are available yet."""
    if i - window + 1 < 0:
        return None
    start = bars[i - window + 1]
    current = bars[i]
    if start.open == 0:
        return None
    return (current.close - start.open) / start.open * _HUNDRED


def realized_volatility_percent(bars: Sequence[Bar], i: int, window: int) -> Decimal | None:
    """Population stdev of trailing 1-minute returns over `bars[i-window+1 : i+1]`, in
    percent. Needs at least 2 trailing returns (`window + 1` bars) to be defined."""
    if i - window < 0:
        return None
    closes = [bars[j].close for j in range(i - window, i + 1)]
    returns = []
    for prior, current in zip(closes[:-1], closes[1:], strict=True):
        if prior == 0:
            return None
        returns.append(float((current - prior) / prior * _HUNDRED))
    if len(returns) < 2:
        return None
    return Decimal(str(statistics.pstdev(returns)))


def range_compression_ratio(
    bars: Sequence[Bar], i: int, *, short_window: int, long_window: int
) -> Decimal | None:
    """(high-low range over the trailing `short_window` bars) / (same over `long_window`
    bars), both ending at `i`. &lt; 1 means the recent range is compressed relative to the
    longer lookback; &gt; 1 means recent expansion. `None` if `long_window` bars aren't
    available yet, or the long-window range is zero."""
    if i - long_window + 1 < 0:
        return None
    long_slice = bars[i - long_window + 1 : i + 1]
    short_slice = bars[i - short_window + 1 : i + 1]
    long_range = max(b.high for b in long_slice) - min(b.low for b in long_slice)
    short_range = max(b.high for b in short_slice) - min(b.low for b in short_slice)
    if long_range == 0:
        return None
    return short_range / long_range


def momentum_sign(bars: Sequence[Bar], i: int, window: int) -> int | None:
    """+1 / -1 / 0 sign of the trailing `window`-bar return ending at `i`. `None` if not
    enough bars yet."""
    value = rolling_return_percent(bars, i, window)
    if value is None:
        return None
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def vwap_distance_percent(
    bars: Sequence[Bar], i: int, vwap_series: Sequence[Decimal]
) -> Decimal | None:
    """`(close - session VWAP) / session VWAP`, in percent, at `i`. `vwap_series` must be
    `compute_vwap_series(bars)` (cumulative-only by construction -- see that function's own
    look-ahead proof)."""
    vwap = vwap_series[i]
    if vwap == 0:
        return None
    return (bars[i].close - vwap) / vwap * _HUNDRED


# ---------------------------------------------------------------------------
# Phase 7 -- contemporaneously-measurable regime labels
# ---------------------------------------------------------------------------


class RegimeLabel(StrEnum):
    SPY_ABOVE_VWAP = "SPY_ABOVE_VWAP"
    SPY_BELOW_VWAP = "SPY_BELOW_VWAP"
    SPY_SESSION_POSITIVE = "SPY_SESSION_POSITIVE"
    SPY_SESSION_NEGATIVE = "SPY_SESSION_NEGATIVE"
    SPY_SESSION_FLAT = "SPY_SESSION_FLAT"


def spy_vwap_position(spy_bars: Sequence[Bar], i: int, spy_vwap_series: Sequence[Decimal]) -> str:
    """ABOVE/BELOW SPY's own session VWAP at `i` -- label uses ONLY `spy_bars[0:i+1]`
    (through `spy_vwap_series`, itself cumulative-only)."""
    distance = vwap_distance_percent(spy_bars, i, spy_vwap_series)
    if distance is None or distance >= 0:
        return RegimeLabel.SPY_ABOVE_VWAP.value
    return RegimeLabel.SPY_BELOW_VWAP.value


def since_open_return_percent(bars: Sequence[Bar], i: int) -> Decimal | None:
    """Return from this session's first bar OPEN through `bars[i].close`, in percent. Uses
    ONLY `bars[0:i+1]` -- the shared basis for both the SPY session-return regime label and
    the Phase 8 cross-sectional ranking (a symbol's own trailing performance since the
    session began)."""
    opening = bars[0].open
    if opening == 0:
        return None
    return (bars[i].close - opening) / opening * _HUNDRED


def spy_session_return_sign(spy_bars: Sequence[Bar], i: int) -> str:
    """SPY's own return from the session's first bar open through `spy_bars[i].close` --
    POSITIVE/NEGATIVE/FLAT. Uses ONLY `spy_bars[0:i+1]`."""
    change = since_open_return_percent(spy_bars, i)
    if change is None or change == 0:
        return RegimeLabel.SPY_SESSION_FLAT.value
    if change > 0:
        return RegimeLabel.SPY_SESSION_POSITIVE.value
    return RegimeLabel.SPY_SESSION_NEGATIVE.value


def trailing_volatility_bucket(
    bars: Sequence[Bar], i: int, *, window: int, low_cutoff: Decimal, high_cutoff: Decimal
) -> str | None:
    """LOW/NORMAL/HIGH bucket for the symbol's OWN trailing realized volatility at `i`,
    against fixed, pre-declared cutoffs (never fit to this dataset's own outcomes) -- uses
    only `bars[0:i+1]`."""
    vol = realized_volatility_percent(bars, i, window)
    if vol is None:
        return None
    if vol < low_cutoff:
        return "LOW"
    if vol > high_cutoff:
        return "HIGH"
    return "NORMAL"


def opening_gap_percent(prior_session_close: Decimal, first_bar_open: Decimal) -> Decimal | None:
    """Prior session's last close -> this session's first bar open, in percent. Known in
    full at the very first bar of the session -- the most contemporaneous feature in this
    module."""
    if prior_session_close == 0:
        return None
    return (first_bar_open - prior_session_close) / prior_session_close * _HUNDRED


# ---------------------------------------------------------------------------
# Phase 8 -- cross-sectional ranking (timestamp-aligned, benchmark-excluded)
# ---------------------------------------------------------------------------


def common_timestamps(per_symbol_bars: Mapping[str, Sequence[Bar]]) -> tuple[datetime, ...]:
    """Timestamps present in EVERY symbol's bar sequence, sorted ascending. Cross-sectional
    ranking must only ever compare symbols at a timestamp every symbol actually has a bar
    for -- a session with one symbol's minute gap must not silently misalign against the
    others (the same risk `RelativeStrengthEvaluation`'s own `build_benchmark_index` guards
    against, here applied across many symbols at once rather than one benchmark)."""
    sets = [{bar.timestamp for bar in bars} for bars in per_symbol_bars.values()]
    if not sets:
        return ()
    common = set.intersection(*sets)
    return tuple(sorted(common))


@dataclass(frozen=True, slots=True)
class CrossSectionalObservation:
    symbol: str
    timestamp: datetime
    relative_return_percent: Decimal
    rank: int
    bucket: str


def cross_sectional_rank(
    *,
    timestamp: datetime,
    symbol_returns: Mapping[str, Decimal],
    spy_return: Decimal,
) -> tuple[CrossSectionalObservation, ...]:
    """Rank `symbol_returns` (each symbol's OWN trailing return-since-open at `timestamp`,
    already computed by the caller using only that symbol's own bars through `timestamp`)
    by outperformance vs `spy_return` (SPY's trailing return-since-open at the SAME
    `timestamp`). Refuses any benchmark symbol in `symbol_returns` -- see
    `BENCHMARK_SYMBOLS` -- so a benchmark can never rank itself.

    Buckets (6 symbols -> thirds of 2; fewer/more symbols split as evenly as the count
    allows): STRONGEST / MIDDLE / WEAKEST, by descending relative return.
    """
    for symbol in symbol_returns:
        if symbol in BENCHMARK_SYMBOLS:
            raise ValueError(f"{symbol} is a benchmark symbol and must never be ranked")
    relative = {symbol: ret - spy_return for symbol, ret in symbol_returns.items()}
    ordered = sorted(relative.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ordered)
    third = max(1, round(n / 3))
    observations: list[CrossSectionalObservation] = []
    for rank, (symbol, rel_return) in enumerate(ordered):
        if rank < third:
            bucket = "STRONGEST"
        elif rank >= n - third:
            bucket = "WEAKEST"
        else:
            bucket = "MIDDLE"
        observations.append(
            CrossSectionalObservation(
                symbol=symbol,
                timestamp=timestamp,
                relative_return_percent=rel_return,
                rank=rank,
                bucket=bucket,
            )
        )
    return tuple(observations)


# ---------------------------------------------------------------------------
# Phase 5 -- forward returns (the ONLY place "the future" is touched, and only strictly
# after the decision mark)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForwardReturnObservation:
    symbol: str
    session_date: date
    decided_at: datetime
    horizon_label: str
    forward_return_percent: Decimal


def forward_return_percent(entry_close: Decimal, future_close: Decimal) -> Decimal | None:
    if entry_close == 0:
        return None
    return (future_close - entry_close) / entry_close * _HUNDRED


def _bar_at_or_after(bars: Sequence[Bar], start_index: int, target: datetime) -> Bar | None:
    """First bar at `start_index` or later whose timestamp is `>= target`. Only ever called
    with `start_index > i` (the decision index) by this module's own callers -- this is the
    one place M094 reads bars strictly after the decision instant."""
    for bar in bars[start_index:]:
        if bar.timestamp >= target:
            return bar
    return None


def forward_return_to_horizon(
    bars: Sequence[Bar], i: int, *, horizon_minutes: int
) -> Decimal | None:
    """Forward return from `bars[i].close` to the first bar at/after `bars[i].timestamp +
    horizon_minutes`, reading only `bars[i+1:]` for the future side. `None` if the session
    ends before that horizon is reached (never fabricated)."""
    from datetime import timedelta

    target = bars[i].timestamp + timedelta(minutes=horizon_minutes)
    future = _bar_at_or_after(bars, i + 1, target)
    if future is None:
        return None
    return forward_return_percent(bars[i].close, future.close)


def forward_return_to_liquidation(bars: Sequence[Bar], i: int) -> Decimal | None:
    """Forward return from `bars[i].close` to the last bar at/before the mandatory
    liquidation time (15:45 ET) in this session, or the session's last bar if the session
    ends before 15:45 ET. Reads only `bars[i+1:]`."""
    liquidation_date = _et(bars[i].timestamp).date()
    liquidation_at = datetime.combine(
        liquidation_date, MANDATORY_LIQUIDATION_ET, tzinfo=EASTERN
    ).astimezone(bars[i].timestamp.tzinfo)
    candidate: Bar | None = None
    for bar in bars[i + 1 :]:
        if bar.timestamp <= liquidation_at:
            candidate = bar
        else:
            break
    if candidate is None:
        candidate = bars[-1] if len(bars) > i + 1 else None
    if candidate is None:
        return None
    return forward_return_percent(bars[i].close, candidate.close)


# ---------------------------------------------------------------------------
# Time-of-day bucketing and decision marks -- ET, matching M093's own (corrected) convention
# ---------------------------------------------------------------------------


class TimeOfDayBucket(StrEnum):
    MORNING = "MORNING_10_12_ET"
    MIDDAY = "MIDDAY_12_14_ET"
    AFTERNOON = "AFTERNOON_14_1530_ET"


def time_of_day_bucket(ts: datetime) -> str | None:
    et = _et(ts).time()
    if time(10, 0) <= et < time(12, 0):
        return TimeOfDayBucket.MORNING.value
    if time(12, 0) <= et < time(14, 0):
        return TimeOfDayBucket.MIDDAY.value
    if time(14, 0) <= et < time(15, 30):
        return TimeOfDayBucket.AFTERNOON.value
    return None


def decision_marks(bars: Sequence[Bar], *, every_minutes: int = 5) -> tuple[int, ...]:
    """Indices of bars that fall on an `every_minutes`-aligned mark (by ET minute-of-hour)
    inside the entry window (10:00-15:30 ET) -- the same window M093's framework uses. A
    smaller, regularly-spaced subset of all bars keeps the research study's output size
    proportionate without biasing which part of the session is sampled."""
    marks: list[int] = []
    for index, bar in enumerate(bars):
        et = _et(bar.timestamp).time()
        if not (ENTRY_WINDOW_START_ET <= et < ENTRY_WINDOW_END_ET):
            continue
        if et.minute % every_minutes == 0:
            marks.append(index)
    return tuple(marks)


# ---------------------------------------------------------------------------
# Phase 9 -- selectivity buckets (deterministic: stable sort, no randomness, no ties broken
# arbitrarily)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Scored:
    strength: Decimal
    tie_key: tuple[object, ...]
    forward_return_percent: Decimal
    symbol: str
    session_date: date


def selectivity_buckets(
    observations: Sequence[tuple[Decimal, Decimal, str, date]],
    *,
    percentiles: tuple[int, ...] = (50, 25, 10, 5, 1),
) -> dict[int, tuple[_Scored, ...]]:
    """`observations` is `(strength, forward_return_percent, symbol, session_date)` tuples.
    Sorts DETERMINISTICALLY by `(-strength, session_date, symbol)` -- ties broken by a fixed,
    data-derived key, never by insertion order or any random tiebreak -- then returns the
    top `p`% (by count, `ceil`) for each requested percentile. Calling this twice on the same
    input is byte-for-byte identical (see `test_m094_edge_source_research.py`)."""
    import math

    scored = [
        _Scored(
            strength=strength,
            tie_key=(session_date.isoformat(), symbol),
            forward_return_percent=forward_return,
            symbol=symbol,
            session_date=session_date,
        )
        for strength, forward_return, symbol, session_date in observations
    ]
    scored.sort(key=lambda s: (-s.strength, s.tie_key))
    total = len(scored)
    result: dict[int, tuple[_Scored, ...]] = {}
    for pct in percentiles:
        count = max(1, math.ceil(total * pct / 100)) if total else 0
        result[pct] = tuple(scored[:count])
    return result


# ---------------------------------------------------------------------------
# Phase 12 -- transparent rank statistics (no scipy dependency; matches the rest of this
# repository's pure-stdlib convention)
# ---------------------------------------------------------------------------


def _ranks(values: Sequence[float]) -> list[float]:
    """Average (fractional) ranks, ties split evenly -- the standard Spearman convention."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        i = j + 1
    return ranks


def spearman_rank_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman rank correlation of `xs` against `ys`. `None` if fewer than 2 observations,
    or either series has zero variance (correlation undefined)."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _ranks(list(xs))
    ry = _ranks(list(ys))
    if statistics.pvariance(rx) == 0 or statistics.pvariance(ry) == 0:
        return None
    mean_x = statistics.fmean(rx)
    mean_y = statistics.fmean(ry)
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return None
    return float(covariance / (var_x**0.5 * var_y**0.5))
