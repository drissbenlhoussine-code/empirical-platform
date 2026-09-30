"""MILESTONE-093 Phase 9 -- STRATEGY FAMILY E: RELATIVE STRENGTH.

Compares an individual symbol's bounded prior-interval return against a benchmark's (SPY)
SAME-interval return, using ONLY bars at or before the decision instant on BOTH series.

NO SELF-BENCHMARK LEAKAGE. `BENCHMARK_SYMBOLS` (SPY, QQQ) are EXPLICITLY EXCLUDED from this
family -- `evaluate_relative_strength` refuses immediately, before touching any bar, for
either symbol, with reason `BENCHMARK_SYMBOL_EXCLUDED`. This is the simpler, explicit-reason
option Phase 9 itself offers ("exclude this family for the benchmark symbol with explicit
reason") rather than inventing a synthetic non-self-referential basket, and it structurally
guarantees a symbol's own future bars can never reach this family through the "benchmark"
comparison (SPY is never compared against itself, and no other symbol reads its own bars
twice under two different names).

Benchmark bars are aligned to the symbol's bars BY TIMESTAMP (a dict lookup, not positional
index), so a gap or stale minute in either series cannot silently misalign the comparison --
a decision instant with no matching benchmark bar at the required timestamp is rejected
(`INSUFFICIENT_BENCHMARK_EVIDENCE`), never approximated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from empirical_platform.decision_candidate.market_data import Bar

__all__ = [
    "BENCHMARK_SYMBOLS",
    "FAMILY_NAME",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "RelativeStrengthEvaluation",
    "RelativeStrengthPlanGeometry",
    "RelativeStrengthPolicy",
    "build_benchmark_index",
    "build_relative_strength_plan_geometry",
    "evaluate_relative_strength",
]

FAMILY_NAME = "RELATIVE_STRENGTH_CONTINUATION"
STRUCTURE_MODEL_ID = "BOUNDED_INTERVAL_OUTPERFORMANCE_VS_BENCHMARK_V1"
STRUCTURE_MODEL_VERSION = "1"

#: Excluded from this family entirely -- see module docstring. Comparing either against
#: itself (the only available benchmark) would be self-referential and meaningless.
BENCHMARK_SYMBOLS: frozenset[str] = frozenset({"SPY", "QQQ"})

_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")


def build_benchmark_index(benchmark_bars: Sequence[Bar]) -> dict[datetime, Bar]:
    """One benchmark bar per timestamp. If the benchmark feed ever repeats a timestamp
    (should not happen after `fetch_session_bars_guarded`'s own de-duplication), the LAST
    one wins -- consistent with how the bar-fetch layer itself de-duplicates."""
    return {bar.timestamp: bar for bar in benchmark_bars}


@dataclass(frozen=True, slots=True)
class RelativeStrengthPolicy:
    lookback_bars: int
    minimum_outperformance_percent: Decimal
    #: Benchmark's own return over the same interval must be at least this (a small positive
    #: bar, or zero, is enough -- "constructive", not necessarily strongly trending).
    minimum_benchmark_return_percent: Decimal
    minimum_liquidity_shares: int
    target_range_multiple: Decimal
    minimum_reward_risk_ratio: Decimal


@dataclass(frozen=True, slots=True)
class RelativeStrengthEvaluation:
    is_candidate: bool
    reason: str | None
    symbol_return_percent: Decimal
    benchmark_return_percent: Decimal
    outperformance_percent: Decimal
    current_close: Decimal
    reference_low: Decimal
    reference_average_range: Decimal
    current_volume: int


def evaluate_relative_strength(
    symbol: str,
    bars: Sequence[Bar],
    index: int,
    benchmark_index: Mapping[datetime, Bar],
    *,
    policy: RelativeStrengthPolicy,
) -> RelativeStrengthEvaluation:
    """Reads ONLY `bars[:index+1]` and whatever benchmark bars `benchmark_index` already
    holds at timestamps `<= bars[index].timestamp` -- never a bar after `index` on either
    series, and never `symbol`'s own bars used as its own benchmark."""
    current = bars[index]
    if symbol in BENCHMARK_SYMBOLS:
        return RelativeStrengthEvaluation(
            is_candidate=False,
            reason="BENCHMARK_SYMBOL_EXCLUDED",
            symbol_return_percent=Decimal("0"),
            benchmark_return_percent=Decimal("0"),
            outperformance_percent=Decimal("0"),
            current_close=current.close,
            reference_low=current.low,
            reference_average_range=Decimal("0"),
            current_volume=current.volume,
        )
    if index < policy.lookback_bars:
        return RelativeStrengthEvaluation(
            is_candidate=False,
            reason="INSUFFICIENT_REFERENCE_BARS",
            symbol_return_percent=Decimal("0"),
            benchmark_return_percent=Decimal("0"),
            outperformance_percent=Decimal("0"),
            current_close=current.close,
            reference_low=current.low,
            reference_average_range=Decimal("0"),
            current_volume=current.volume,
        )

    reference_start = bars[index - policy.lookback_bars]
    benchmark_now = benchmark_index.get(current.timestamp)
    benchmark_then = benchmark_index.get(reference_start.timestamp)
    if benchmark_now is None or benchmark_then is None or benchmark_then.close <= 0:
        return RelativeStrengthEvaluation(
            is_candidate=False,
            reason="INSUFFICIENT_BENCHMARK_EVIDENCE",
            symbol_return_percent=Decimal("0"),
            benchmark_return_percent=Decimal("0"),
            outperformance_percent=Decimal("0"),
            current_close=current.close,
            reference_low=current.low,
            reference_average_range=Decimal("0"),
            current_volume=current.volume,
        )

    reference_window = bars[index - policy.lookback_bars : index]
    symbol_return_percent = (
        (current.close - reference_start.close) / reference_start.close
    ) * _HUNDRED
    benchmark_return_percent = (
        (benchmark_now.close - benchmark_then.close) / benchmark_then.close
    ) * _HUNDRED
    outperformance_percent = symbol_return_percent - benchmark_return_percent

    reference_low = min(bar.low for bar in reference_window)
    ranges = [bar.high - bar.low for bar in reference_window]
    reference_average_range = sum(ranges, start=Decimal(0)) / Decimal(len(ranges))

    benchmark_constructive = benchmark_return_percent >= policy.minimum_benchmark_return_percent
    outperforms = outperformance_percent >= policy.minimum_outperformance_percent
    structure_preserved = current.low >= reference_low
    resumption = current.close > max(bar.close for bar in reference_window)
    liquid_enough = current.volume >= policy.minimum_liquidity_shares

    is_candidate = (
        benchmark_constructive
        and outperforms
        and structure_preserved
        and resumption
        and liquid_enough
    )
    reason: str | None = None
    if not is_candidate:
        if not liquid_enough:
            reason = "INSUFFICIENT_LIQUIDITY"
        elif not benchmark_constructive:
            reason = "BENCHMARK_NOT_CONSTRUCTIVE"
        elif not outperforms:
            reason = "INSUFFICIENT_OUTPERFORMANCE"
        elif not structure_preserved:
            reason = "STRUCTURE_BROKEN"
        elif not resumption:
            reason = "NO_RESUMPTION_TRIGGER"

    return RelativeStrengthEvaluation(
        is_candidate=is_candidate,
        reason=reason,
        symbol_return_percent=symbol_return_percent,
        benchmark_return_percent=benchmark_return_percent,
        outperformance_percent=outperformance_percent,
        current_close=current.close,
        reference_low=reference_low,
        reference_average_range=reference_average_range,
        current_volume=current.volume,
    )


@dataclass(frozen=True, slots=True)
class RelativeStrengthPlanGeometry:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_DOWN)


def build_relative_strength_plan_geometry(
    evaluation: RelativeStrengthEvaluation, *, policy: RelativeStrengthPolicy
) -> RelativeStrengthPlanGeometry | None:
    entry = _quantize(evaluation.current_close)
    stop = _quantize(evaluation.reference_low)
    if stop >= entry:
        return None
    risk_per_share = _quantize(entry - stop)
    if risk_per_share <= 0:
        return None
    range_aware_target = entry + policy.target_range_multiple * evaluation.reference_average_range
    floor_target = entry + policy.minimum_reward_risk_ratio * risk_per_share
    target = _quantize(max(range_aware_target, floor_target))
    reward_per_share = _quantize(target - entry)
    reward_risk_ratio = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))
    return RelativeStrengthPlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )
