"""MILESTONE-057 Phase 16: independent mathematical verification.

This module deliberately does NOT call `empirical_platform.decision_candidate
.strategy.evaluate()`, and does not construct `Bar`/`ObservationWindow`
objects to do its own arithmetic. `_independently_recompute` re-derives
`reference_high`, `reference_average_volume`, and the resulting decision
straight from the raw JSON fixture files using only `json`, `statistics`,
and `decimal` -- a second, separately-authored path with no shared code
with the production strategy module other than the fixture files
themselves. Each test then calls the real production `evaluate()` on the
same fixture and asserts the two independently-computed answers agree.
"""

from __future__ import annotations

import json
import statistics
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
from empirical_platform.decision_candidate.strategy import StrategyParameters, evaluate

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "m057_market_data"
_REFERENCE_WINDOW_SIZE = 5


@dataclass(frozen=True)
class _IndependentResult:
    decision: str
    reference_high: Decimal
    reference_average_volume: Decimal
    current_close: Decimal
    current_volume: int


def _independently_recompute(fixture_name: str) -> _IndependentResult:
    """Re-derive the strategy's measurements and decision from raw JSON,
    without using any of the production `Bar`/`ObservationWindow`/
    `evaluate()` machinery."""
    raw_bars = json.loads((_FIXTURES_DIR / fixture_name).read_text(encoding="utf-8"))
    reference_rows = raw_bars[:-1][-_REFERENCE_WINDOW_SIZE:]
    evaluation_row = raw_bars[-1]

    reference_high = max(Decimal(row["high"]) for row in reference_rows)
    reference_average_volume = statistics.mean(Decimal(row["volume"]) for row in reference_rows)
    current_close = Decimal(evaluation_row["close"])
    current_volume = int(evaluation_row["volume"])

    price_above = current_close > reference_high
    volume_above = Decimal(current_volume) > reference_average_volume
    decision = "LONG_CANDIDATE" if price_above and volume_above else "NO_TRADE"

    return _IndependentResult(
        decision=decision,
        reference_high=reference_high,
        reference_average_volume=reference_average_volume,
        current_close=current_close,
        current_volume=current_volume,
    )


def _production_evaluate(fixture_name: str) -> ObservationWindow:
    raw_bars = json.loads((_FIXTURES_DIR / fixture_name).read_text(encoding="utf-8"))
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
        for row in raw_bars
    )
    return ObservationWindow(bars=bars)


def _assert_production_matches_independent(fixture_name: str) -> None:
    independent = _independently_recompute(fixture_name)
    window = _production_evaluate(fixture_name)
    outcome = evaluate(window, StrategyParameters(reference_window_size=_REFERENCE_WINDOW_SIZE))

    assert outcome.decision.value == independent.decision
    assert outcome.measurements.reference_high == independent.reference_high
    assert outcome.measurements.reference_average_volume == independent.reference_average_volume
    assert outcome.measurements.current_close == independent.current_close
    assert outcome.measurements.current_volume == independent.current_volume


def test_long_candidate_fixture_matches_independent_recomputation() -> None:
    _assert_production_matches_independent("synthetic_aapl_1min_long_candidate.json")


def test_no_trade_fixture_matches_independent_recomputation() -> None:
    _assert_production_matches_independent("synthetic_aapl_1min_no_trade.json")


def test_lookahead_probe_fixture_matches_independent_recomputation() -> None:
    _assert_production_matches_independent("synthetic_aapl_1min_lookahead_probe.json")
