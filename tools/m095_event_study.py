"""MILESTONE-095 Phases 3-19 -- the event-driven edge research study driver.

    python tools/m095_event_study.py --phase run

READ-ONLY, INFORMATION-VALUE STUDY, NOT A STRATEGY. No entry/stop/target geometry, no
position sizing, no broker-write surface anywhere in this file.

DATASET REUSE. Same 100-session M091-DEVELOPMENT/M092-VALIDATION research window M093/M094
already used (`research_session_dates`, imported verbatim), same 8-symbol universe. Bars are
fetched through `m093_research_framework.fetch_session_bars_guarded` (holdout-guarded);
news is fetched through `m095_event_research.fetch_symbol_news_guarded` (holdout-guarded
independently, over the same window) -- both guards call `assert_not_holdout` before any
network call, and this tool's own `research_session_dates()` import is the SAME, already-
proven-disjoint-from-holdout 100-date list M093/M094 used, never recomputed here.

SCOPE (Phase 1/2 qualification, `external-review/MILESTONE-095/data-source-qualification.md`):
event presence (+ a predeclared earnings-keyword flag) only -- no structured earnings-
surprise magnitude, no analyst-rating data exists in any already-credentialed source. The
observation point is fixed at the session open (not the mission's full open+5/15/30m sweep)
to keep this proportionate to what the qualified source actually supports.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from statistics import fmean, median
from typing import Any
from zoneinfo import ZoneInfo

from tools.m093_family_screening import SYMBOLS, research_session_dates

from empirical_platform.decision_candidate.m093_holdout_guard import HOLDOUT_END, HOLDOUT_START
from empirical_platform.decision_candidate.m095_event_data import EventType
from empirical_platform.decision_candidate.market_data import Bar
from empirical_platform.decision_candidate.opportunity_family_relative_strength import (
    BENCHMARK_SYMBOLS,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases import m093_research_framework as fw
from empirical_platform.usecases import m095_event_research as research
from empirical_platform.usecases.m093_research_framework import COST_MODEL_1, COST_MODEL_2
from empirical_platform.usecases.m094_edge_source_research import spearman_rank_correlation

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-095" / "event-study-results.json"

SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
OPERATOR_TIMEZONE = "America/New_York"
EASTERN = ZoneInfo(OPERATOR_TIMEZONE)

RANKED_SYMBOLS: tuple[str, ...] = tuple(s for s in SYMBOLS if s not in BENCHMARK_SYMBOLS)
assert RANKED_SYMBOLS == ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA")

COST1_ROUND_TRIP_PERCENT = COST_MODEL_1.entry_cost_percent + COST_MODEL_1.exit_cost_percent
COST2_ROUND_TRIP_PERCENT = COST_MODEL_2.entry_cost_percent + COST_MODEL_2.exit_cost_percent

BarCache = dict[tuple[str, date], tuple[Bar, ...]]


def _bars_port() -> AlpacaPaperMarketDataClient:
    credentials = credentials_from_environment(dict(os.environ))
    return AlpacaPaperMarketDataClient(credentials=credentials)


def _fetch_bars(
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


def fetch_all_bars(bars_port: AlpacaPaperMarketDataClient) -> tuple[BarCache, tuple[date, ...]]:
    dates = research_session_dates()
    assert len(dates) == 100
    assert all(not (HOLDOUT_START <= d <= HOLDOUT_END) for d in dates)
    cache: BarCache = {}
    for session_date in dates:
        for symbol in SYMBOLS:
            cache[(symbol, session_date)] = _fetch_bars(bars_port, symbol, session_date)
    return cache, dates


def fetch_all_events(
    news_port: AlpacaPaperMarketDataClient, dates: tuple[date, ...]
) -> dict[str, tuple[Any, ...]]:
    retrieved_at = datetime.now().astimezone()
    window_start, window_end = min(dates), max(dates)
    assert not (HOLDOUT_START <= window_start <= HOLDOUT_END)
    assert not (HOLDOUT_START <= window_end <= HOLDOUT_END)
    events: dict[str, tuple[Any, ...]] = {}
    for symbol in RANKED_SYMBOLS:
        events[symbol] = research.fetch_symbol_news_guarded(
            news_port,
            symbol,
            window_start_date=window_start,
            window_end_date=window_end,
            retrieved_at=retrieved_at,
        )
    return events


def _prior_close_by_date(
    cache: BarCache, symbol: str, dates: tuple[date, ...]
) -> dict[date, Decimal]:
    sorted_dates = sorted(dates)
    result: dict[date, Decimal] = {}
    previous_close: Decimal | None = None
    for session_date in sorted_dates:
        if previous_close is not None:
            result[session_date] = previous_close
        bars = cache.get((symbol, session_date))
        if bars:
            previous_close = bars[-1].close
    return result


def build_observations(
    cache: BarCache, events_by_symbol: dict[str, tuple[Any, ...]], dates: tuple[date, ...]
) -> dict[str, tuple[research.EventGapObservation, ...]]:
    spy_bars_by_date = {d: cache.get(("SPY", d), ()) for d in dates}
    spy_prior_close = _prior_close_by_date(cache, "SPY", dates)
    result: dict[str, tuple[research.EventGapObservation, ...]] = {}
    for symbol in RANKED_SYMBOLS:
        bars_by_date = {d: cache.get((symbol, d), ()) for d in dates}
        prior_close = _prior_close_by_date(cache, symbol, dates)
        result[symbol] = research.observations_for_symbol(
            symbol,
            session_dates=dates,
            bars_by_date=bars_by_date,
            prior_close_by_date=prior_close,
            events=events_by_symbol[symbol],
            spy_bars_by_date=spy_bars_by_date,
            spy_prior_close_by_date=spy_prior_close,
        )
    return result


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "stdev": None, "positive_fraction": None}
    sorted_values = sorted(values)
    n = len(values)
    stdev = (sum((v - fmean(values)) ** 2 for v in values) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {
        "n": n,
        "mean": round(fmean(values), 5),
        "median": round(median(values), 5),
        "stdev": round(stdev, 5),
        "positive_fraction": round(sum(1 for v in values if v > 0) / n, 4),
        "p10": round(sorted_values[max(0, int(n * 0.10) - 1)], 5),
        "p90": round(sorted_values[min(n - 1, int(n * 0.90))], 5),
    }


_HORIZON_FIELDS = (
    ("15m", "forward_return_15m"),
    ("30m", "forward_return_30m"),
    ("60m", "forward_return_60m"),
    ("120m", "forward_return_120m"),
    ("session", "forward_return_session"),
)


def _group_horizon_stats(
    rows: list[research.EventGapObservation],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for label, field in _HORIZON_FIELDS:
        values = [float(getattr(row, field)) for row in rows if getattr(row, field) is not None]
        out[label] = _stats(values)
    return out


def event_vs_control(
    all_rows: list[research.EventGapObservation],
) -> dict[str, Any]:
    """Phase 9 -- gap-up WITH a qualifying event vs gap-up WITHOUT one, matched to the SAME
    gap-magnitude buckets (GAP_UP_SMALL, GAP_UP_LARGE) so the comparison isn't confounded by
    event-tagged gaps simply being bigger gaps."""
    out: dict[str, Any] = {}
    for bucket_name in ("GAP_UP_SMALL", "GAP_UP_LARGE"):
        bucketed = [r for r in all_rows if r.bucket is not None and r.bucket.value == bucket_name]
        with_event = [r for r in bucketed if r.event_present]
        without_event = [r for r in bucketed if not r.event_present]
        out[bucket_name] = {
            "with_event": _group_horizon_stats(with_event),
            "without_event": _group_horizon_stats(without_event),
        }
    return out


def gap_bucket_table(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for bucket in research.GapBucket:
        rows = [r for r in all_rows if r.bucket == bucket]
        out[bucket.value] = _group_horizon_stats(rows)
    return out


def relative_volume_study(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    """Phase 11 -- does event+gap+unusual early volume contain more information than gap
    alone? Compares the 30m forward return for gap-up+event rows split by whether relative
    early volume was above/below its own median among gap-up+event rows."""
    candidates = [
        r
        for r in all_rows
        if r.event_present
        and r.bucket in (research.GapBucket.GAP_UP_SMALL, research.GapBucket.GAP_UP_LARGE)
        and r.relative_early_volume is not None
        and r.forward_return_30m is not None
    ]
    if len(candidates) < 4:
        return {"n": len(candidates), "note": "too few event+gap-up observations with volume data"}
    pairs: list[tuple[float, float]] = [
        (float(r.relative_early_volume), float(r.forward_return_30m))
        for r in candidates
        if r.relative_early_volume is not None and r.forward_return_30m is not None
    ]
    cutoff = median(volume for volume, _ in pairs)
    high = [ret for volume, ret in pairs if volume >= cutoff]
    low = [ret for volume, ret in pairs if volume < cutoff]
    return {
        "median_relative_volume_cutoff": round(cutoff, 3),
        "high_relative_volume": _stats(high),
        "low_relative_volume": _stats(low),
    }


def market_context_study(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    """Phase 12 -- event+gap-up rows split by SPY's own opening-gap sign that same day."""
    candidates = [
        r
        for r in all_rows
        if r.event_present
        and r.bucket in (research.GapBucket.GAP_UP_SMALL, research.GapBucket.GAP_UP_LARGE)
        and r.spy_gap_sign is not None
    ]
    return {
        "spy_gap_positive": _group_horizon_stats(
            [r for r in candidates if r.spy_gap_sign == "POSITIVE"]
        ),
        "spy_gap_negative": _group_horizon_stats(
            [r for r in candidates if r.spy_gap_sign == "NEGATIVE"]
        ),
    }


def cost_survivability(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    event_gap_up = [
        r
        for r in all_rows
        if r.event_present
        and r.bucket in (research.GapBucket.GAP_UP_SMALL, research.GapBucket.GAP_UP_LARGE)
    ]
    stats_30m = _group_horizon_stats(event_gap_up)["30m"]
    mean_move = stats_30m.get("mean")
    return {
        "event_gap_up_30m_mean_move_percent": mean_move,
        "cost1_round_trip_percent": float(COST1_ROUND_TRIP_PERCENT),
        "cost2_round_trip_percent": float(COST2_ROUND_TRIP_PERCENT),
        "survives_cost1": mean_move is not None and mean_move >= float(COST1_ROUND_TRIP_PERCENT),
        "survives_cost2": mean_move is not None and mean_move >= float(COST2_ROUND_TRIP_PERCENT),
    }


def temporal_stability(
    all_rows: list[research.EventGapObservation], dates: tuple[date, ...]
) -> dict[str, Any]:
    """Phase 15 -- chronological halves of the SAME 100-session research window (never the
    locked holdout)."""
    sorted_dates = sorted(dates)
    midpoint = sorted_dates[len(sorted_dates) // 2]
    first_half = [r for r in all_rows if r.session_date < midpoint]
    second_half = [r for r in all_rows if r.session_date >= midpoint]

    def _event_gap_up_30m_mean(rows: list[research.EventGapObservation]) -> float | None:
        candidates = [
            r
            for r in rows
            if r.event_present
            and r.bucket in (research.GapBucket.GAP_UP_SMALL, research.GapBucket.GAP_UP_LARGE)
            and r.forward_return_30m is not None
        ]
        if not candidates:
            return None
        return round(fmean(float(r.forward_return_30m) for r in candidates), 5)  # type: ignore[arg-type]

    return {
        "first_half_mean_event_gap_up_30m": _event_gap_up_30m_mean(first_half),
        "second_half_mean_event_gap_up_30m": _event_gap_up_30m_mean(second_half),
        "first_half_n": len(first_half),
        "second_half_n": len(second_half),
    }


def cross_symbol_stability(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    by_symbol: dict[str, Any] = {}
    for symbol in RANKED_SYMBOLS:
        rows = [
            r
            for r in all_rows
            if r.symbol == symbol
            and r.event_present
            and r.bucket in (research.GapBucket.GAP_UP_SMALL, research.GapBucket.GAP_UP_LARGE)
            and r.forward_return_30m is not None
        ]
        values = [float(r.forward_return_30m) for r in rows]  # type: ignore[arg-type]
        by_symbol[symbol] = {
            "n": len(values),
            "mean_30m": round(fmean(values), 5) if values else None,
        }
    return by_symbol


def selectivity_study(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    """Phase 17 -- does a larger gap (stronger evidence) correspond to a larger subsequent
    move, among event-present gap-up rows? Spearman IC between gap magnitude and 30m forward
    return, computed BEFORE any bucket cutoff is chosen."""
    candidates = [
        r
        for r in all_rows
        if r.event_present
        and r.gap_percent is not None
        and r.gap_percent > 0
        and r.forward_return_30m is not None
    ]
    if len(candidates) < 5:
        return {"n": len(candidates), "spearman_ic": None}
    xs = [float(r.gap_percent) for r in candidates]  # type: ignore[arg-type]
    ys = [float(r.forward_return_30m) for r in candidates]  # type: ignore[arg-type]
    ic = spearman_rank_correlation(xs, ys)
    return {"n": len(candidates), "spearman_ic": round(ic, 4) if ic is not None else None}


def frequency_study(
    all_rows: list[research.EventGapObservation], session_count: int
) -> dict[str, Any]:
    event_present_count = sum(1 for r in all_rows if r.event_present)
    event_gap_up_count = sum(
        1
        for r in all_rows
        if r.event_present
        and r.bucket in (research.GapBucket.GAP_UP_SMALL, research.GapBucket.GAP_UP_LARGE)
    )
    return {
        "events_per_symbol_month": round(
            float(
                research.opportunities_per_month(event_present_count, session_count=session_count)
            )
            / len(RANKED_SYMBOLS),
            2,
        ),
        "event_gap_up_opportunities_per_month_all_symbols": round(
            float(
                research.opportunities_per_month(event_gap_up_count, session_count=session_count)
            ),
            2,
        ),
        "event_gap_up_opportunities_per_week_all_symbols": round(
            float(research.opportunities_per_month(event_gap_up_count, session_count=session_count))
            / 4.33,
            2,
        ),
    }


def event_type_breakdown(all_rows: list[research.EventGapObservation]) -> dict[str, Any]:
    earnings = [r for r in all_rows if r.event_type == EventType.EARNINGS_KEYWORD_NEWS]
    other = [r for r in all_rows if r.event_type == EventType.OTHER_NEWS]
    return {
        "earnings_keyword_news": {
            "n": len(earnings),
            "horizons_30m": _group_horizon_stats(earnings)["30m"],
        },
        "other_news": {"n": len(other), "horizons_30m": _group_horizon_stats(other)["30m"]},
    }


def classify(
    control: dict[str, Any],
    cost: dict[str, Any],
    temporal: dict[str, Any],
    cross_symbol: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Phase 19 -- the decision gate, mechanical. A direction qualifies only if: cost1
    survivability holds on the primary metric, the sign is stable across both temporal
    halves, and no single symbol supplies the entire effect (every symbol with n>=3 must
    share the full-sample sign, OR the symbol with the largest n must not exceed 60% of the
    total qualifying n)."""
    directions: list[dict[str, Any]] = []
    survives_cost1 = bool(cost.get("survives_cost1"))
    first_half = temporal.get("first_half_mean_event_gap_up_30m")
    second_half = temporal.get("second_half_mean_event_gap_up_30m")
    temporally_stable = (
        first_half is not None and second_half is not None and (first_half > 0) == (second_half > 0)
    )
    total_n = sum(v["n"] for v in cross_symbol.values())
    max_symbol_n = max((v["n"] for v in cross_symbol.values()), default=0)
    concentrated = total_n > 0 and max_symbol_n / total_n > 0.60
    signs = {
        s: v["mean_30m"]
        for s, v in cross_symbol.items()
        if v["n"] >= 3 and v["mean_30m"] is not None
    }
    sign_agreement = len({s >= 0 for s in signs.values()}) <= 1 if signs else False

    eligible = survives_cost1 and temporally_stable and not concentrated and sign_agreement
    directions.append(
        {
            "direction": "EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP",
            "survives_cost1": survives_cost1,
            "temporally_stable": temporally_stable,
            "cross_symbol_concentrated": concentrated,
            "cross_symbol_sign_agreement": sign_agreement,
            "eligible": eligible,
        }
    )
    classification = "EVENT_EDGE_DIRECTIONS_FOUND" if eligible else "NO_EVENT_EDGE_FOUND"
    return classification, directions


def run() -> dict[str, Any]:
    bars_port = _bars_port()
    cache, dates = fetch_all_bars(bars_port)
    events_by_symbol = fetch_all_events(bars_port, dates)
    observations_by_symbol = build_observations(cache, events_by_symbol, dates)
    all_rows = [row for rows in observations_by_symbol.values() for row in rows]

    control = event_vs_control(all_rows)
    gap_table = gap_bucket_table(all_rows)
    rel_vol = relative_volume_study(all_rows)
    market_context = market_context_study(all_rows)
    cost = cost_survivability(all_rows)
    temporal = temporal_stability(all_rows, dates)
    cross_symbol = cross_symbol_stability(all_rows)
    selectivity = selectivity_study(all_rows)
    frequency = frequency_study(all_rows, session_count=len(dates))
    event_types = event_type_breakdown(all_rows)
    classification, directions = classify(control, cost, temporal, cross_symbol)

    event_count_total = sum(len(v) for v in events_by_symbol.values())
    earnings_count = sum(
        1
        for events in events_by_symbol.values()
        for e in events
        if e.event_type == EventType.EARNINGS_KEYWORD_NEWS
    )

    results: dict[str, Any] = {
        "milestone": "M095",
        "research_dataset": {
            "session_count": len(dates),
            "first_date": min(dates).isoformat(),
            "last_date": max(dates).isoformat(),
            "symbols_ranked": list(RANKED_SYMBOLS),
            "symbols_benchmark": sorted(BENCHMARK_SYMBOLS),
        },
        "event_data": {
            "total_company_specific_articles": event_count_total,
            "earnings_keyword_articles": earnings_count,
            "other_news_articles": event_count_total - earnings_count,
            "source": "alpaca-news-v1beta1 (Benzinga)",
        },
        "event_type_breakdown": event_types,
        "gap_bucket_table": gap_table,
        "event_vs_control": control,
        "relative_volume": rel_vol,
        "market_context": market_context,
        "cost_survivability": cost,
        "temporal_stability": temporal,
        "cross_symbol_stability": cross_symbol,
        "selectivity": selectivity,
        "frequency": frequency,
        "selected_directions": directions,
        "classification": classification,
        "locked_holdout": {
            "start": HOLDOUT_START.isoformat(),
            "end": HOLDOUT_END.isoformat(),
            "accessed": False,
        },
        "broker_writes": {"buy": 0, "sell": 0, "cancel": 0, "live": 0},
    }
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="run", choices=["run"])
    parser.parse_args()
    results = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {RESULTS_PATH}")
    print(f"classification: {results['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
