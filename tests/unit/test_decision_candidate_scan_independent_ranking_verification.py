"""MILESTONE-058 Phase 13: independent mathematical verification of ranking.

This module deliberately does NOT call `empirical_platform.decision_candidate
.ranking.compute_ranking_score`, `ranking.rank_sort_key`, or
`scan.build_scan()`. `_independently_rank` re-derives each LONG_CANDIDATE's
score with its own separately-authored formula and sorts the results with
Python's own built-in `sorted()` over a hand-rolled key -- a second,
independently-authored path with no shared code with the production ranking
module. It DOES reuse the frozen, already-independently-verified (M057
Phase 16) `strategy.evaluate()` function: this module verifies RANKING, not
strategy evaluation, which is out of scope here and already covered.

Each test then calls the real production `build_scan()` on the same
universe and asserts the two independently-computed answers agree, on both
score and complete ordering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.scan import TradingOpportunityScan, build_scan
from empirical_platform.decision_candidate.strategy import (
    StrategyParameters,
    TradingDecision,
    evaluate,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m058_market_scan"
    / "synthetic_6instrument_scan_universe.json"
)
_REFERENCE_WINDOW_SIZE = 5


@dataclass(frozen=True)
class _IndependentRankedResult:
    symbol: str
    score: Decimal


def _independent_score(
    *, close: Decimal, volume: int, reference_high: Decimal, reference_average_volume: Decimal
) -> Decimal:
    """A separately-authored reimplementation of the ranking formula,
    computed term-by-term rather than mirroring `compute_ranking_score`'s
    own expression shape."""
    price_gain = close - reference_high
    breakout_term = price_gain / reference_high
    volume_term = Decimal(volume) / reference_average_volume
    total = breakout_term + volume_term
    return total


def _independently_rank(fixture_path: Path) -> list[_IndependentRankedResult]:
    """Re-derive the full ranked order using only `dict`/`list`/`sorted()`
    primitives and a hand-rolled comparison key -- no call into
    `ranking.py` or `scan.py`'s own sorting logic."""
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    scored: list[tuple[str, Decimal]] = []
    for instrument_entry in raw["instruments"]:
        bars = [
            Bar(
                instrument=Instrument(row["instrument"]),
                interval=BarInterval(row["interval"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=int(row["volume"]),
            )
            for row in instrument_entry["bars"]
        ]
        window = ObservationWindow(bars=tuple(bars))
        outcome = evaluate(window, StrategyParameters(reference_window_size=_REFERENCE_WINDOW_SIZE))
        if outcome.decision is not TradingDecision.LONG_CANDIDATE:
            continue
        symbol = str(window.instrument)
        score = _independent_score(
            close=outcome.measurements.current_close,
            volume=outcome.measurements.current_volume,
            reference_high=outcome.measurements.reference_high,
            reference_average_volume=outcome.measurements.reference_average_volume,
        )
        scored.append((symbol, score))

    # Hand-rolled insertion sort by (-score, symbol) -- deliberately not
    # reusing Python's key-tuple idiom from `ranking.rank_sort_key`.
    ordered: list[tuple[str, Decimal]] = []
    for symbol, score in scored:
        insert_at = len(ordered)
        for i, (existing_symbol, existing_score) in enumerate(ordered):
            if score > existing_score or (score == existing_score and symbol < existing_symbol):
                insert_at = i
                break
        ordered.insert(insert_at, (symbol, score))

    return [_IndependentRankedResult(symbol=symbol, score=score) for symbol, score in ordered]


def _production_scan() -> TradingOpportunityScan:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    windows = []
    candidate_ids = []
    for instrument_entry in raw["instruments"]:
        bars = tuple(
            Bar(
                instrument=Instrument(row["instrument"]),
                interval=BarInterval(row["interval"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=int(row["volume"]),
            )
            for row in instrument_entry["bars"]
        )
        windows.append(ObservationWindow(bars=bars))
        candidate_ids.append(
            DecisionCandidateId(instrument_entry["decision_candidate_governance_id"])
        )

    parameters = StrategyParameters(reference_window_size=_REFERENCE_WINDOW_SIZE)
    universe = [
        (window.instrument, candidate_id, evaluate(window, parameters))
        for window, candidate_id in zip(windows, candidate_ids, strict=True)
    ]
    scan_identity = DomainIdentity(
        governance_id=TradingOpportunityScanId("SCAN-0001"),
        runtime_id=RuntimeIdentifier("70000000-0000-4000-8000-000000000001"),
    )
    scan = build_scan(
        identity=scan_identity,
        target_evidence_package_id=EvidencePackageId("EVID-0001"),
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=windows[0].evaluation_bar.timestamp,
        universe=universe,
    )
    return scan


def test_independent_ranking_matches_production_scores() -> None:
    independent = _independently_rank(_FIXTURE)
    scan = _production_scan()

    production_by_symbol = {
        str(entry.instrument): entry.score for entry in scan.ranked_opportunities
    }
    for result in independent:
        assert production_by_symbol[result.symbol] == result.score


def test_independent_ranking_matches_production_complete_order() -> None:
    independent = _independently_rank(_FIXTURE)
    scan = _production_scan()

    independent_order = [result.symbol for result in independent]
    production_order = [str(entry.instrument) for entry in scan.ranked_opportunities]
    assert independent_order == production_order
    assert independent_order == ["AMZN", "NVDA", "TSLA", "AAPL"]


def test_independent_ranking_excludes_no_trade_instruments() -> None:
    independent = _independently_rank(_FIXTURE)
    independent_symbols = {result.symbol for result in independent}
    assert "MSFT" not in independent_symbols
    assert "GOOG" not in independent_symbols
