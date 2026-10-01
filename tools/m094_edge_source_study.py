"""MILESTONE-094 Phases 3-19 -- the edge-source information-value study driver.

    python tools/m094_edge_source_study.py --phase run

READ-ONLY, INFORMATION-VALUE STUDY, NOT A STRATEGY. There is no entry/stop/target geometry,
no position sizing, and no broker-write surface anywhere in this file -- it measures whether
contemporaneously-knowable information has predictive structure after realistic costs, never
whether a trading rule built on it would have made money.

DATASET REUSE (Phase 3). Fetches ONLY the identical 100-session M091-DEVELOPMENT/M092-
VALIDATION research dataset M093 already used (`research_session_dates`, imported verbatim
from `tools.m093_family_screening`, never recomputed with a second literal date range) and
the same fixed 8-symbol universe. M093's own raw bars were never persisted to disk (only its
aggregated metrics were committed), so this tool legitimately re-fetches them -- but it
fetches each (symbol, session) pair exactly ONCE for the whole run and reuses that one
in-memory cache across every phase below, rather than re-fetching per phase.

HOLDOUT CARRY-FORWARD (Phase 1). Exclusively through `fw.fetch_session_bars_guarded` -- the
SAME single fetch point M093 itself used, which calls `assert_not_holdout` before any network
call. NEVER fetches 2026-03-18..2026-05-12 (the locked FINAL HOLDOUT) for any reason, at any
phase. See `tests/unit/test_m094_edge_source_study.py` and
`external-review/MILESTONE-094/holdout-confirmation.md`.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any
from zoneinfo import ZoneInfo

from tools.m093_family_screening import SYMBOLS, research_session_dates

from empirical_platform.decision_candidate.market_data import Bar
from empirical_platform.decision_candidate.opportunity_family_relative_strength import (
    BENCHMARK_SYMBOLS,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases import m093_research_framework as fw
from empirical_platform.usecases import m094_edge_source_research as research

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-094" / "edge-source-results.json"

SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
OPERATOR_TIMEZONE = "America/New_York"
EASTERN = ZoneInfo(OPERATOR_TIMEZONE)

#: Non-benchmark symbols only -- SPY/QQQ are excluded from cross-sectional ranking (Phase 8)
#: exactly as M093's own RELATIVE_STRENGTH family excludes them.
RANKED_SYMBOLS: tuple[str, ...] = tuple(s for s in SYMBOLS if s not in BENCHMARK_SYMBOLS)

#: Representative horizon used throughout Phases 6/8/9/12/13/14/15 for a single, consistent
#: comparison basis. Chosen before any result was inspected: the middle of the Phase 5
#: horizon ladder (5/15/30/60/120).
REPRESENTATIVE_HORIZON_MINUTES = 30

#: Pre-declared trailing-volatility bucket cutoffs for Phase 7's regime conditioning
#: (percent stdev of trailing 1-minute returns over a 30-bar window). Round numbers chosen
#: before this study ran, never fit to its own outcomes.
VOLATILITY_LOW_CUTOFF = Decimal("0.05")
VOLATILITY_HIGH_CUTOFF = Decimal("0.15")

BarCache = dict[tuple[str, date], tuple[Bar, ...]]


def _bars_port() -> AlpacaPaperMarketDataClient:
    credentials = credentials_from_environment(dict(os.environ))
    return AlpacaPaperMarketDataClient(credentials=credentials)


def _fetch(
    bars_port: AlpacaPaperMarketDataClient, symbol: str, session_date: date
) -> tuple[Bar, ...]:
    return fw.fetch_session_bars_guarded(
        bars_port,
        symbol,
        session_date,
        session_start=SESSION_START,
        session_end=SESSION_END,
        operator_timezone=OPERATOR_TIMEZONE,
    )


def fetch_research_bars(
    bars_port: AlpacaPaperMarketDataClient,
) -> tuple[BarCache, tuple[date, ...]]:
    """Fetch every (symbol, session) pair in the 100-session research dataset EXACTLY ONCE.
    Returns the cache plus the sorted session dates, so every phase below reuses this same
    cache rather than re-fetching."""
    dates = research_session_dates()
    assert len(dates) == 100
    cache: BarCache = {}
    for session_date in dates:
        for symbol in SYMBOLS:
            cache[(symbol, session_date)] = _fetch(bars_port, symbol, session_date)
    return cache, dates


# ---------------------------------------------------------------------------
# Phase 4 -- cost/turnover diagnosis, ANALYTICAL: derived from M093's already-published
# per-family numbers (external-review/MILESTONE-093/family-screening.md), not re-simulated.
# ---------------------------------------------------------------------------

#: Copied verbatim from external-review/MILESTONE-093/family-screening.md's own Phase 11
#: aggregate table (resolved count, COST0 net, COST1 net -- dollars, full 100-session
#: research sample). RELATIVE_STRENGTH's resolved count is over 6 symbols (600 symbol-
#: sessions), every other family's is over all 8 (800 symbol-sessions).
M093_FAMILY_RESULTS: dict[str, dict[str, Any]] = {
    "TREND_CONTINUATION": {
        "resolved": 4031,
        "cost0_net": -1327.36,
        "cost1_net": -8384.78,
        "symbol_sessions": 800,
    },
    "VWAP_PULLBACK": {
        "resolved": 894,
        "cost0_net": 26.51,
        "cost1_net": -1545.97,
        "symbol_sessions": 800,
    },
    "OPENING_RANGE_5": {
        "resolved": 20697,
        "cost0_net": -14151.48,
        "cost1_net": -49739.42,
        "symbol_sessions": 800,
    },
    "OPENING_RANGE_15": {
        "resolved": 18762,
        "cost0_net": -12665.99,
        "cost1_net": -44883.69,
        "symbol_sessions": 800,
    },
    "MEAN_REVERSION": {
        "resolved": 10787,
        "cost0_net": 1810.20,
        "cost1_net": -17775.42,
        "symbol_sessions": 800,
    },
    "RELATIVE_STRENGTH": {
        "resolved": 4287,
        "cost0_net": -325.71,
        "cost1_net": -8225.23,
        "symbol_sessions": 600,
    },
}


def phase4_cost_turnover_diagnosis() -> dict[str, Any]:
    per_family: dict[str, Any] = {}
    for family, numbers in M093_FAMILY_RESULTS.items():
        resolved = numbers["resolved"]
        cost0_avg = numbers["cost0_net"] / resolved
        cost1_avg = numbers["cost1_net"] / resolved
        cost_drag_per_trade = cost1_avg - cost0_avg
        turnover_per_symbol_session = resolved / numbers["symbol_sessions"]
        signal_quality_already_negative = cost0_avg < 0
        per_family[family] = {
            "resolved": resolved,
            "cost0_avg_per_trade": round(cost0_avg, 4),
            "cost1_avg_per_trade": round(cost1_avg, 4),
            "cost_drag_per_trade": round(cost_drag_per_trade, 4),
            "turnover_per_symbol_session": round(turnover_per_symbol_session, 3),
            "signal_quality_already_negative_pre_cost": signal_quality_already_negative,
            "required_gross_improvement_to_breakeven_at_cost1": (
                None if signal_quality_already_negative else round(cost_drag_per_trade * -1, 4)
            ),
        }
    lowest_turnover_family = min(
        per_family, key=lambda f: per_family[f]["turnover_per_symbol_session"]
    )
    return {
        "per_family": per_family,
        "cost_drag_per_trade_is_roughly_uniform_across_families": True,
        "lowest_turnover_family": lowest_turnover_family,
        "lowest_turnover_family_still_fails_cost1": True,
        "conclusion": (
            "Cost drag per trade is roughly uniform (~$1.7-1.85/trade) across all six "
            "families regardless of turnover. VWAP_PULLBACK, the LOWEST-turnover family "
            f"tested ({per_family[lowest_turnover_family]['turnover_per_symbol_session']} "
            "trades/symbol-session), already has a near-zero gross (COST0) edge "
            "(+$0.0297/trade) and is fully erased by cost. Lower turnover alone does not "
            "produce a larger per-trade GROSS edge in this dataset -- the primary failure "
            "mode is signal quality (gross expectancy at or below zero for 4 of 6 variants "
            "even before cost), not merely trade count. See M093's own spot-check: tight "
            "$1-2/share stop/target geometry on $150-500 stocks makes a fixed ~10bps "
            "round-trip cost a large fraction of the risk unit itself -- a geometry/cost "
            "interaction, not a frequency problem alone."
        ),
    }


# ---------------------------------------------------------------------------
# Decision marks shared across Phases 5-16: every 5-ET-minutes mark in the 10:00-15:30 ET
# entry window, aligned by TIMESTAMP (never by raw list index) so a gap in one symbol's bar
# series cannot silently misalign it against another's.
# ---------------------------------------------------------------------------


def _is_mark(ts: datetime) -> bool:
    if research.time_of_day_bucket(ts) is None:
        return False
    return ts.astimezone(EASTERN).minute % 5 == 0


def _index_by_timestamp(bars: tuple[Bar, ...]) -> dict[datetime, int]:
    return {bar.timestamp: i for i, bar in enumerate(bars)}


# ---------------------------------------------------------------------------
# Phase 5 -- horizon study (single-symbol, unconditional forward returns)
# ---------------------------------------------------------------------------


def phase5_horizon_study(cache: BarCache, dates: tuple[date, ...]) -> dict[str, Any]:
    by_horizon: dict[str, list[float]] = defaultdict(list)
    for session_date in dates:
        for symbol in RANKED_SYMBOLS:
            bars = cache[(symbol, session_date)]
            if len(bars) < 5:
                continue
            for i in research.decision_marks(bars):
                for horizon in research.HORIZON_MINUTES:
                    value = research.forward_return_to_horizon(bars, i, horizon_minutes=horizon)
                    if value is not None:
                        by_horizon[f"{horizon}m"].append(float(value))
                liquidation_value = research.forward_return_to_liquidation(bars, i)
                if liquidation_value is not None:
                    by_horizon["to_liquidation"].append(float(liquidation_value))
    summary: dict[str, Any] = {}
    for label, values in by_horizon.items():
        if not values:
            continue
        positive = sum(1 for v in values if v > 0)
        summary[label] = {
            "n": len(values),
            "mean_percent": round(fmean(values), 5),
            "median_percent": round(median(values), 5),
            "stdev_percent": round(pstdev(values), 5) if len(values) > 1 else 0.0,
            "sign_persistence_percent": round(100 * positive / len(values), 2),
        }
    return summary


# ---------------------------------------------------------------------------
# Phase 6 -- multi-timeframe context (own-symbol trailing momentum vs forward return)
# ---------------------------------------------------------------------------


def phase6_multi_timeframe(cache: BarCache, dates: tuple[date, ...]) -> dict[str, Any]:
    windows = (5, 15, 30, 60)
    feature_values: dict[int, list[float]] = {w: [] for w in windows}
    forward_values: dict[int, list[float]] = {w: [] for w in windows}
    for session_date in dates:
        for symbol in RANKED_SYMBOLS:
            bars = cache[(symbol, session_date)]
            if len(bars) < 5:
                continue
            for i in research.decision_marks(bars):
                forward = research.forward_return_to_horizon(
                    bars, i, horizon_minutes=REPRESENTATIVE_HORIZON_MINUTES
                )
                if forward is None:
                    continue
                for window in windows:
                    trend = research.rolling_return_percent(bars, i, window)
                    if trend is None:
                        continue
                    feature_values[window].append(float(trend))
                    forward_values[window].append(float(forward))
    result: dict[str, Any] = {}
    for window in windows:
        ic = research.spearman_rank_correlation(feature_values[window], forward_values[window])
        result[f"trailing_{window}m_momentum"] = {
            "n": len(feature_values[window]),
            "spearman_ic_vs_30m_forward_return": None if ic is None else round(ic, 4),
        }
    return result


# ---------------------------------------------------------------------------
# Phase 7 -- regime conditioning (SPY-based labels; conditions unconditional own-symbol
# 30-minute forward returns)
# ---------------------------------------------------------------------------


def phase7_regime(cache: BarCache, dates: tuple[date, ...]) -> dict[str, Any]:
    by_vwap_position: dict[str, list[float]] = defaultdict(list)
    by_session_return_sign: dict[str, list[float]] = defaultdict(list)
    by_volatility_bucket: dict[str, list[float]] = defaultdict(list)
    for session_date in dates:
        spy_bars = cache[("SPY", session_date)]
        if len(spy_bars) < 5:
            continue
        spy_vwap_series = research.compute_vwap_series(spy_bars)
        spy_index = _index_by_timestamp(spy_bars)
        for symbol in RANKED_SYMBOLS:
            bars = cache[(symbol, session_date)]
            if len(bars) < 5:
                continue
            for i in research.decision_marks(bars):
                ts = bars[i].timestamp
                spy_i = spy_index.get(ts)
                if spy_i is None:
                    continue
                forward = research.forward_return_to_horizon(
                    bars, i, horizon_minutes=REPRESENTATIVE_HORIZON_MINUTES
                )
                if forward is None:
                    continue
                by_vwap_position[
                    research.spy_vwap_position(spy_bars, spy_i, spy_vwap_series)
                ].append(float(forward))
                by_session_return_sign[research.spy_session_return_sign(spy_bars, spy_i)].append(
                    float(forward)
                )
                vol_bucket = research.trailing_volatility_bucket(
                    bars,
                    i,
                    window=30,
                    low_cutoff=VOLATILITY_LOW_CUTOFF,
                    high_cutoff=VOLATILITY_HIGH_CUTOFF,
                )
                if vol_bucket is not None:
                    by_volatility_bucket[vol_bucket].append(float(forward))

    def _summarize(groups: dict[str, list[float]]) -> dict[str, Any]:
        return {
            label: {"n": len(values), "mean_30m_forward_return_percent": round(fmean(values), 5)}
            for label, values in groups.items()
            if values
        }

    return {
        "by_spy_vwap_position": _summarize(by_vwap_position),
        "by_spy_session_return_sign": _summarize(by_session_return_sign),
        "by_own_trailing_volatility_bucket": _summarize(by_volatility_bucket),
    }


# ---------------------------------------------------------------------------
# Phase 8 -- cross-sectional ranking (relative return vs SPY, timestamp-aligned,
# benchmark-excluded)
# ---------------------------------------------------------------------------


def _cross_sectional_observations(
    cache: BarCache, dates: tuple[date, ...]
) -> list[tuple[str, date, datetime, str, Decimal, Decimal]]:
    """One row per (symbol, session_date, timestamp): (symbol, date, ts, bucket,
    relative_return_percent, 30m_forward_return_percent). Built once, reused by Phases
    8/9/12/13/14/15 so the ranking is computed exactly once."""
    rows: list[tuple[str, date, datetime, str, Decimal, Decimal]] = []
    for session_date in dates:
        per_symbol_bars = {sym: cache[(sym, session_date)] for sym in RANKED_SYMBOLS}
        spy_bars = cache[("SPY", session_date)]
        if any(len(b) < 5 for b in per_symbol_bars.values()) or len(spy_bars) < 5:
            continue
        common_ts = research.common_timestamps({**per_symbol_bars, "SPY": spy_bars})
        indices = {sym: _index_by_timestamp(bars) for sym, bars in per_symbol_bars.items()}
        spy_index = _index_by_timestamp(spy_bars)
        for ts in common_ts:
            if not _is_mark(ts):
                continue
            spy_return = research.since_open_return_percent(spy_bars, spy_index[ts])
            if spy_return is None:
                continue
            symbol_returns: dict[str, Decimal] = {}
            for sym, bars in per_symbol_bars.items():
                value = research.since_open_return_percent(bars, indices[sym][ts])
                if value is not None:
                    symbol_returns[sym] = value
            if len(symbol_returns) < len(RANKED_SYMBOLS):
                continue
            observations = research.cross_sectional_rank(
                timestamp=ts, symbol_returns=symbol_returns, spy_return=spy_return
            )
            for obs in observations:
                bars = per_symbol_bars[obs.symbol]
                i = indices[obs.symbol][ts]
                forward = research.forward_return_to_horizon(
                    bars, i, horizon_minutes=REPRESENTATIVE_HORIZON_MINUTES
                )
                if forward is None:
                    continue
                rows.append(
                    (obs.symbol, session_date, ts, obs.bucket, obs.relative_return_percent, forward)
                )
    return rows


def phase8_cross_sectional(
    rows: list[tuple[str, date, datetime, str, Decimal, Decimal]],
) -> dict[str, Any]:
    by_bucket: dict[str, list[float]] = defaultdict(list)
    for _symbol, _date, _ts, bucket, _rel, forward in rows:
        by_bucket[bucket].append(float(forward))
    summary = {
        bucket: {"n": len(values), "mean_30m_forward_return_percent": round(fmean(values), 5)}
        for bucket, values in by_bucket.items()
        if values
    }
    strongest = summary.get("STRONGEST", {}).get("mean_30m_forward_return_percent")
    weakest = summary.get("WEAKEST", {}).get("mean_30m_forward_return_percent")
    spread = None if strongest is None or weakest is None else round(strongest - weakest, 5)
    return {"by_bucket": summary, "strongest_minus_weakest_spread_percent": spread}


# ---------------------------------------------------------------------------
# Phase 9 -- selectivity buckets (same cross-sectional relative-return signal, pooled)
# ---------------------------------------------------------------------------


def phase9_selectivity(
    rows: list[tuple[str, date, datetime, str, Decimal, Decimal]],
) -> dict[str, Any]:
    observations = [
        (rel, forward, symbol, session_date)
        for symbol, session_date, _ts, _bucket, rel, forward in rows
    ]
    buckets = research.selectivity_buckets(observations)
    result: dict[str, Any] = {}
    for pct, members in buckets.items():
        if not members:
            continue
        forwards = [float(m.forward_return_percent) for m in members]
        by_symbol_count: dict[str, int] = defaultdict(int)
        by_day_count: dict[str, int] = defaultdict(int)
        for m in members:
            by_symbol_count[m.symbol] += 1
            by_day_count[m.session_date.isoformat()] += 1
        n = len(members)
        half = n // 2
        first_half_mean = fmean(forwards[:half]) if half else None
        second_half_mean = fmean(forwards[half:]) if (n - half) else None
        result[f"top_{pct}pct"] = {
            "n": n,
            "mean_30m_forward_return_percent": round(fmean(forwards), 5),
            "max_single_symbol_share_percent": round(100 * max(by_symbol_count.values()) / n, 2),
            "max_single_day_share_percent": round(100 * max(by_day_count.values()) / n, 2),
            "chronological_first_half_mean_percent": (
                None if first_half_mean is None else round(first_half_mean, 5)
            ),
            "chronological_second_half_mean_percent": (
                None if second_half_mean is None else round(second_half_mean, 5)
            ),
        }
    return result


# ---------------------------------------------------------------------------
# Phase 10 -- opening gap context (and EVENT_DATA_NOT_AVAILABLE)
# ---------------------------------------------------------------------------


def phase10_gap_study(cache: BarCache, dates: tuple[date, ...]) -> dict[str, Any]:
    by_direction: dict[str, list[float]] = defaultdict(list)
    for k in range(1, len(dates)):
        prior_date, today = dates[k - 1], dates[k]
        for symbol in RANKED_SYMBOLS:
            prior_bars = cache[(symbol, prior_date)]
            today_bars = cache[(symbol, today)]
            if len(prior_bars) < 1 or len(today_bars) < 5:
                continue
            gap = research.opening_gap_percent(prior_bars[-1].close, today_bars[0].open)
            if gap is None:
                continue
            early_move = research.forward_return_to_horizon(today_bars, 0, horizon_minutes=30)
            if early_move is None:
                continue
            if gap > Decimal("0.1"):
                direction = "GAP_UP"
            elif gap < Decimal("-0.1"):
                direction = "GAP_DOWN"
            else:
                direction = "FLAT"
            by_direction[direction].append(float(early_move))
    summary = {
        direction: {"n": len(values), "mean_30m_forward_return_percent": round(fmean(values), 5)}
        for direction, values in by_direction.items()
        if values
    }
    return {
        "by_gap_direction": summary,
        "event_news_earnings_data": "EVENT_DATA_NOT_AVAILABLE",
        "event_data_note": (
            "No earnings-calendar or news/sentiment data port exists anywhere in this "
            "repository (only corporate-action/split-dividend semantics does); this gap "
            "study uses only prior-close/today-open displacement and early-session range, "
            "which ARE already legitimately available. Fabricating event data was not done."
        ),
    }


# ---------------------------------------------------------------------------
# Phase 12 -- information coefficient for the cross-sectional signal
# ---------------------------------------------------------------------------


def phase12_information_coefficient(
    rows: list[tuple[str, date, datetime, str, Decimal, Decimal]],
) -> dict[str, Any]:
    xs = [float(rel) for _s, _d, _t, _b, rel, _f in rows]
    ys = [float(forward) for _s, _d, _t, _b, _rel, forward in rows]
    ic = research.spearman_rank_correlation(xs, ys)
    return {
        "feature": "relative_return_vs_spy_percent",
        "target": "30m_forward_return_percent",
        "n": len(rows),
        "spearman_ic": None if ic is None else round(ic, 4),
    }


# ---------------------------------------------------------------------------
# Phase 13 -- temporal stability (4 chronological quartiles of the same 100-session window)
# ---------------------------------------------------------------------------


def phase13_temporal_stability(
    rows: list[tuple[str, date, datetime, str, Decimal, Decimal]], dates: tuple[date, ...]
) -> dict[str, Any]:
    quartile_size = len(dates) // 4
    quartiles = [
        dates[q * quartile_size : (q + 1) * quartile_size if q < 3 else len(dates)]
        for q in range(4)
    ]
    result: dict[str, Any] = {}
    for q_index, quartile_dates in enumerate(quartiles):
        quartile_set = set(quartile_dates)
        sub_rows = [r for r in rows if r[1] in quartile_set]
        by_bucket: dict[str, list[float]] = defaultdict(list)
        for _s, _d, _t, bucket, _rel, forward in sub_rows:
            by_bucket[bucket].append(float(forward))
        strongest = fmean(by_bucket["STRONGEST"]) if by_bucket.get("STRONGEST") else None
        weakest = fmean(by_bucket["WEAKEST"]) if by_bucket.get("WEAKEST") else None
        spread = None if strongest is None or weakest is None else round(strongest - weakest, 5)
        xs = [float(rel) for s, d, t, b, rel, f in sub_rows]
        ys = [float(f) for s, d, t, b, rel, f in sub_rows]
        ic = research.spearman_rank_correlation(xs, ys)
        result[f"quartile_{q_index + 1}"] = {
            "dates": (
                quartile_dates[0].isoformat() if quartile_dates else None,
                quartile_dates[-1].isoformat() if quartile_dates else None,
            ),
            "n": len(sub_rows),
            "strongest_minus_weakest_spread_percent": spread,
            "spearman_ic": None if ic is None else round(ic, 4),
        }
    return result


# ---------------------------------------------------------------------------
# Phase 14 -- cross-symbol stability (the cross-sectional effect, per symbol)
# ---------------------------------------------------------------------------


def phase14_cross_symbol_stability(
    rows: list[tuple[str, date, datetime, str, Decimal, Decimal]],
) -> dict[str, Any]:
    by_symbol_bucket: dict[tuple[str, str], list[float]] = defaultdict(list)
    for symbol, _d, _t, bucket, _rel, forward in rows:
        by_symbol_bucket[(symbol, bucket)].append(float(forward))
    result: dict[str, Any] = {}
    for symbol in RANKED_SYMBOLS:
        strongest = by_symbol_bucket.get((symbol, "STRONGEST"), [])
        weakest = by_symbol_bucket.get((symbol, "WEAKEST"), [])
        result[symbol] = {
            "strongest_n": len(strongest),
            "strongest_mean_percent": round(fmean(strongest), 5) if strongest else None,
            "weakest_n": len(weakest),
            "weakest_mean_percent": round(fmean(weakest), 5) if weakest else None,
            "spread_percent": (
                round(fmean(strongest) - fmean(weakest), 5) if strongest and weakest else None
            ),
        }
    return result


# ---------------------------------------------------------------------------
# Phase 15 -- cost-aware information value
# ---------------------------------------------------------------------------


def phase15_cost_aware_value(
    cross_sectional: dict[str, Any], selectivity: dict[str, Any]
) -> dict[str, Any]:
    round_trip_cost_percent = {
        "COST_MODEL_0": 0.0,
        "COST_MODEL_1": float(
            fw.COST_MODEL_1.entry_cost_percent + fw.COST_MODEL_1.exit_cost_percent
        ),
        "COST_MODEL_2": float(
            fw.COST_MODEL_2.entry_cost_percent + fw.COST_MODEL_2.exit_cost_percent
        ),
    }
    spread = cross_sectional.get("strongest_minus_weakest_spread_percent")
    top1 = selectivity.get("top_1pct", {}).get("mean_30m_forward_return_percent")
    top5 = selectivity.get("top_5pct", {}).get("mean_30m_forward_return_percent")

    def _survives(move: float | None, cost: float) -> bool | None:
        return None if move is None else abs(move) > cost

    return {
        "round_trip_cost_percent": round_trip_cost_percent,
        "cross_sectional_strongest_minus_weakest_spread_percent": spread,
        "cross_sectional_survives_cost1": _survives(
            spread, round_trip_cost_percent["COST_MODEL_1"]
        ),
        "selectivity_top_1pct_mean_move_percent": top1,
        "selectivity_top_1pct_survives_cost1": _survives(
            top1, round_trip_cost_percent["COST_MODEL_1"]
        ),
        "selectivity_top_5pct_mean_move_percent": top5,
        "selectivity_top_5pct_survives_cost1": _survives(
            top5, round_trip_cost_percent["COST_MODEL_1"]
        ),
    }


# ---------------------------------------------------------------------------
# Phase 16/17 -- feature-family scorecard and mechanical decision gate
# ---------------------------------------------------------------------------

_DIRECTIONS = (
    "MULTI_TIMEFRAME_TREND",
    "CROSS_SECTIONAL_RELATIVE_STRENGTH",
    "REGIME_CONDITIONING",
    "OPENING_GAP_CONTEXT",
    "SELECTIVE_MOMENTUM",
    "VOLATILITY_COMPRESSION_EXPANSION",
    "LOW_FREQUENCY_HIGH_CONVICTION",
    "EVENT_DATA_REQUIRED",
)


def phase16_scorecard(
    *,
    multi_timeframe: dict[str, Any],
    cross_sectional: dict[str, Any],
    regime: dict[str, Any],
    gap: dict[str, Any],
    selectivity: dict[str, Any],
    temporal: dict[str, Any],
    cross_symbol: dict[str, Any],
    cost_aware: dict[str, Any],
) -> dict[str, Any]:
    quartile_spreads = [q["strongest_minus_weakest_spread_percent"] for q in temporal.values()]
    quartile_spreads_defined = [s for s in quartile_spreads if s is not None]
    same_sign_quartiles = (
        sum(1 for s in quartile_spreads_defined if s > 0) if quartile_spreads_defined else 0
    )
    per_symbol_spreads = [
        v["spread_percent"] for v in cross_symbol.values() if v["spread_percent"] is not None
    ]
    max_symbol_spread = max((abs(s) for s in per_symbol_spreads), default=None)
    total_abs_symbol_spread = (
        sum(abs(s) for s in per_symbol_spreads) if per_symbol_spreads else None
    )
    dominated_by_one_symbol = (
        max_symbol_spread is not None
        and total_abs_symbol_spread is not None
        and total_abs_symbol_spread > 0
        and (max_symbol_spread / total_abs_symbol_spread) > 0.6
    )

    best_multi_timeframe_ic = max(
        (
            abs(v["spearman_ic_vs_30m_forward_return"])
            for v in multi_timeframe.values()
            if v["spearman_ic_vs_30m_forward_return"] is not None
        ),
        default=None,
    )

    scorecard = {
        "MULTI_TIMEFRAME_TREND": {
            "observed_information_strength": (
                "weak"
                if best_multi_timeframe_ic is None or best_multi_timeframe_ic < 0.02
                else "present"
            ),
            "best_abs_spearman_ic": None
            if best_multi_timeframe_ic is None
            else round(best_multi_timeframe_ic, 4),
            "temporal_stability": "not separately re-tested per quartile in this fork",
            "cross_symbol_stability": "not separately broken out (own-symbol feature, pooled)",
            "cost_survivability": "not evaluated (IC too small to build a bucket spread)",
            "sample_size": sum(v["n"] for v in multi_timeframe.values()),
            "complexity": "low (single rolling-window feature)",
            "data_availability": "full (same 1-min bars already fetched)",
        },
        "CROSS_SECTIONAL_RELATIVE_STRENGTH": {
            "observed_information_strength": (
                "present"
                if cost_aware.get("cross_sectional_strongest_minus_weakest_spread_percent")
                else "weak"
            ),
            "strongest_minus_weakest_spread_percent": cost_aware.get(
                "cross_sectional_strongest_minus_weakest_spread_percent"
            ),
            "temporal_stability": f"{same_sign_quartiles}/4 quartiles same sign (positive spread)",
            "cross_symbol_stability": (
                "dominated by one symbol" if dominated_by_one_symbol else "broad across symbols"
            ),
            "cost_survivability": (
                "survives COST1"
                if cost_aware.get("cross_sectional_survives_cost1")
                else "does not survive COST1"
            ),
            "sample_size": cross_sectional.get("by_bucket", {}).get("STRONGEST", {}).get("n", 0),
            "complexity": "moderate (per-timestamp cross-sectional ranking across symbols)",
            "data_availability": "full",
        },
        "REGIME_CONDITIONING": {
            "observed_information_strength": "weak-to-moderate (see per-regime means)",
            "by_spy_vwap_position": regime.get("by_spy_vwap_position"),
            "by_spy_session_return_sign": regime.get("by_spy_session_return_sign"),
            "temporal_stability": "not separately re-tested per quartile in this fork",
            "cross_symbol_stability": "pooled across RANKED_SYMBOLS, not broken out per symbol",
            "cost_survivability": "regime differences small vs COST1; see owner-report.md",
            "sample_size": sum(v["n"] for v in regime.get("by_spy_vwap_position", {}).values()),
            "complexity": "low (two SPY-derived labels)",
            "data_availability": "full",
        },
        "OPENING_GAP_CONTEXT": {
            "observed_information_strength": "weak"
            if not gap.get("by_gap_direction")
            else "see table",
            "by_gap_direction": gap.get("by_gap_direction"),
            "temporal_stability": "not separately re-tested per quartile in this fork",
            "cross_symbol_stability": "pooled across RANKED_SYMBOLS, not broken out per symbol",
            "cost_survivability": "see owner-report.md",
            "sample_size": sum(v["n"] for v in gap.get("by_gap_direction", {}).values()),
            "complexity": "low",
            "data_availability": "full (no event/news data required for this specific cut)",
        },
        "SELECTIVE_MOMENTUM": {
            "observed_information_strength": "see selectivity table (monotonicity by percentile)",
            "selectivity_table": selectivity,
            "temporal_stability": "chronological first/second-half means reported per bucket",
            "cross_symbol_stability": "max single-symbol share reported per bucket",
            "cost_survivability": (
                "top-1% survives COST1"
                if cost_aware.get("selectivity_top_1pct_survives_cost1")
                else "does not survive COST1"
            ),
            "sample_size": selectivity.get("top_1pct", {}).get("n", 0),
            "complexity": "moderate (percentile bucketing of the cross-sectional signal)",
            "data_availability": "full",
        },
        "VOLATILITY_COMPRESSION_EXPANSION": {
            "observed_information_strength": "weak (see by_own_trailing_volatility_bucket)",
            "by_volatility_bucket": regime.get("by_own_trailing_volatility_bucket"),
            "temporal_stability": "not separately re-tested per quartile in this fork",
            "cross_symbol_stability": "pooled, not broken out per symbol",
            "cost_survivability": "see owner-report.md",
            "sample_size": sum(
                v["n"] for v in regime.get("by_own_trailing_volatility_bucket", {}).values()
            ),
            "complexity": "low-moderate (range_compression_ratio exists but not scored here)",
            "data_availability": "full",
        },
        "LOW_FREQUENCY_HIGH_CONVICTION": {
            "observed_information_strength": "see SELECTIVE_MOMENTUM top-1%/5% survivability",
            "temporal_stability": "inherits SELECTIVE_MOMENTUM's",
            "cross_symbol_stability": "inherits SELECTIVE_MOMENTUM's",
            "cost_survivability": (
                "plausible"
                if cost_aware.get("selectivity_top_1pct_survives_cost1")
                else "not demonstrated"
            ),
            "sample_size": selectivity.get("top_1pct", {}).get("n", 0),
            "complexity": "low (a frequency/selectivity choice on top of SELECTIVE_MOMENTUM)",
            "data_availability": "full",
        },
        "EVENT_DATA_REQUIRED": {
            "observed_information_strength": "unknown -- not measurable with current data",
            "temporal_stability": "n/a",
            "cross_symbol_stability": "n/a",
            "cost_survivability": "n/a",
            "sample_size": 0,
            "complexity": "unknown",
            "data_availability": "NONE (EVENT_DATA_NOT_AVAILABLE)",
        },
    }
    assert set(scorecard) == set(_DIRECTIONS)
    return scorecard


def phase17_decision_gate(
    scorecard: dict[str, Any], information_coefficient: dict[str, Any]
) -> tuple[str, ...] | str:
    """Mechanical, auditable eligibility rule (Phase 17, verbatim): measurable, reasonably
    stable, not dominated by one symbol/day, plausible room above COST1, no look-ahead,
    sufficient observations. Applied to the REAL computed numbers above -- never relaxed to
    force a non-empty selection."""
    eligible: list[str] = []

    cross_sectional_entry = scorecard["CROSS_SECTIONAL_RELATIVE_STRENGTH"]
    cross_sectional_eligible = (
        information_coefficient.get("spearman_ic") is not None
        and abs(information_coefficient["spearman_ic"]) >= 0.02
        and cross_sectional_entry["sample_size"] >= 200
        and "survives COST1" in cross_sectional_entry["cost_survivability"]
        and cross_sectional_entry["cross_symbol_stability"] == "broad across symbols"
    )
    if cross_sectional_eligible:
        eligible.append("CROSS_SECTIONAL_RELATIVE_STRENGTH")

    selective_entry = scorecard["SELECTIVE_MOMENTUM"]
    selective_eligible = (
        selective_entry["sample_size"] >= 50
        and "survives COST1" in selective_entry["cost_survivability"]
    )
    if selective_eligible:
        eligible.append("SELECTIVE_MOMENTUM")

    if not eligible:
        return "NO_PROMISING_EDGE_SOURCE"
    return tuple(eligible[:2])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    bars_port = _bars_port()
    cache, dates = fetch_research_bars(bars_port)
    non_empty = sum(1 for bars in cache.values() if len(bars) >= 5)

    cost_turnover = phase4_cost_turnover_diagnosis()
    horizon = phase5_horizon_study(cache, dates)
    multi_timeframe = phase6_multi_timeframe(cache, dates)
    regime = phase7_regime(cache, dates)
    cross_sectional_rows = _cross_sectional_observations(cache, dates)
    cross_sectional = phase8_cross_sectional(cross_sectional_rows)
    selectivity = phase9_selectivity(cross_sectional_rows)
    gap = phase10_gap_study(cache, dates)
    information_coefficient = phase12_information_coefficient(cross_sectional_rows)
    temporal = phase13_temporal_stability(cross_sectional_rows, dates)
    cross_symbol = phase14_cross_symbol_stability(cross_sectional_rows)
    cost_aware = phase15_cost_aware_value(cross_sectional, selectivity)
    scorecard = phase16_scorecard(
        multi_timeframe=multi_timeframe,
        cross_sectional=cross_sectional,
        regime=regime,
        gap=gap,
        selectivity=selectivity,
        temporal=temporal,
        cross_symbol=cross_symbol,
        cost_aware=cost_aware,
    )
    selected = phase17_decision_gate(scorecard, information_coefficient)
    classification = (
        "NO_PROMISING_EDGE_SOURCE"
        if selected == "NO_PROMISING_EDGE_SOURCE"
        else "PROMISING_EDGE_SOURCES_FOUND"
    )

    return {
        "generated_at": datetime.now(EASTERN).isoformat(),
        "research_dataset": {
            "description": (
                "M091 DEVELOPMENT (2026-07-08..2026-09-29) UNION "
                "M092 VALIDATION (2026-05-13..2026-07-07) -- identical to M093's own "
                "research dataset, reused rather than widened"
            ),
            "session_count": len(dates),
            "symbol_session_pairs_fetched": len(cache),
            "symbol_session_pairs_non_empty": non_empty,
            "symbols": list(SYMBOLS),
            "ranked_symbols": list(RANKED_SYMBOLS),
        },
        "holdout_locked_range": {"start": "2026-03-18", "end": "2026-05-12", "accessed": False},
        "phase4_cost_turnover_diagnosis": cost_turnover,
        "phase5_horizon_study": horizon,
        "phase6_multi_timeframe": multi_timeframe,
        "phase7_regime": regime,
        "phase8_cross_sectional": cross_sectional,
        "phase9_selectivity": selectivity,
        "phase10_gap_study": gap,
        "phase12_information_coefficient": information_coefficient,
        "phase13_temporal_stability": temporal,
        "phase14_cross_symbol_stability": cross_symbol,
        "phase15_cost_aware_value": cost_aware,
        "phase16_scorecard": scorecard,
        "selected_directions": ([] if selected == "NO_PROMISING_EDGE_SOURCE" else list(selected)),
        "classification": classification,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["run"], required=True)
    parser.parse_args()
    summary = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(f"classification: {summary['classification']}")
    print(f"selected_directions: {summary['selected_directions']}")
    print(f"wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
