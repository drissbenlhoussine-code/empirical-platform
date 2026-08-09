"""MILESTONE-058 Phase 14: scan-level look-ahead / cutoff-synchronization
audit.

M057's own look-ahead defense (an `ObservationWindow` cannot contain a bar
dated after its own evaluation bar -- see `market_data.py`) is inherited
unchanged: nothing in M058 touches `Bar`/`ObservationWindow`/`evaluate()`.
This module audits the one *new* risk a multi-instrument scan introduces:
one instrument's window silently running "ahead" of its peers -- carrying a
later evaluation cutoff than the rest of the universe, so its own decision
reflects information the other instruments' evaluations could not possibly
have had access to at the shared scan cutoff.

The defense is `validate_scan_universe()` (`scan.py`): every window in a
scan universe must share the exact same evaluation-bar timestamp. Since a
window's evaluation bar is structurally its own *last* bar, "one instrument
sees a bar dated after the common cutoff" and "one instrument's evaluation
cutoff differs from its peers'" are the same condition -- so this one check
is a complete defense, not a heuristic. This module proves it fails loudly,
BEFORE any evaluation or ranking is attempted, and proves an otherwise
identical, correctly-synchronized universe ranks normally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.scan import build_scan, validate_scan_universe
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

_CUTOFF = datetime(2026, 8, 10, 13, 45, 0, tzinfo=UTC)
_REFERENCE_HIGHS = ["100.00", "100.20", "100.30", "100.40", "100.50"]
_REFERENCE_VOLUMES = [1000, 1050, 980, 1020, 1010]
_EVID = EvidencePackageId("EVID-0001")


def _bar(*, instrument: Instrument, timestamp: datetime, close: str, high: str, volume: int) -> Bar:
    close_decimal = Decimal(close)
    high_decimal = Decimal(high)
    low_decimal = min(close_decimal, high_decimal) - Decimal("0.10")
    return Bar(
        instrument=instrument,
        interval=BarInterval.ONE_MINUTE,
        timestamp=timestamp,
        open=close_decimal,
        high=high_decimal,
        low=low_decimal,
        close=close_decimal,
        volume=volume,
    )


def _reference_bars(instrument: Instrument) -> list[Bar]:
    return [
        _bar(
            instrument=instrument,
            timestamp=_CUTOFF - timedelta(minutes=5 - i),
            close=h,
            high=h,
            volume=v,
        )
        for i, (h, v) in enumerate(zip(_REFERENCE_HIGHS, _REFERENCE_VOLUMES, strict=True))
    ]


def _synced_window(symbol: str, *, close: str = "100.40", volume: int = 900) -> ObservationWindow:
    """A correctly-synchronized window: evaluation bar exactly at `_CUTOFF`."""
    instrument = Instrument(symbol)
    reference = _reference_bars(instrument)
    evaluation = _bar(
        instrument=instrument,
        timestamp=_CUTOFF,
        close=close,
        high=str(Decimal(close) + Decimal("0.05")),
        volume=volume,
    )
    return ObservationWindow(bars=(*reference, evaluation))


def _smuggled_future_window(symbol: str) -> ObservationWindow:
    """A window carrying one extra bar *after* the common scan cutoff, with
    an extreme close/volume that would win the entire ranking outright if it
    were ever allowed to influence the scan."""
    instrument = Instrument(symbol)
    reference = _reference_bars(instrument)
    at_cutoff = _bar(
        instrument=instrument, timestamp=_CUTOFF, close="100.40", high="100.45", volume=900
    )
    smuggled_future_bar = _bar(
        instrument=instrument,
        timestamp=_CUTOFF + timedelta(minutes=1),
        close="500.00",
        high="500.00",
        volume=50_000,
    )
    return ObservationWindow(bars=(*reference, at_cutoff, smuggled_future_bar))


def test_validate_scan_universe_rejects_instrument_running_ahead_of_peers() -> None:
    """A universe where one instrument's evaluation bar is dated after the
    common scan cutoff must be rejected outright, before any strategy
    evaluation or ranking is attempted -- proving the extreme, would-be
    rank-winning future bar never gets the chance to influence anything."""
    honest_windows = [_synced_window("AAAA"), _synced_window("BBBB")]
    smuggled_window = _smuggled_future_window("CCCC")

    with pytest.raises(ValueError, match="one evaluation cutoff"):
        validate_scan_universe([*honest_windows, smuggled_window])


def test_smuggled_future_bar_would_have_dominated_ranking_if_permitted() -> None:
    """Positive control: confirm the smuggled bar's own numbers really are
    extreme enough that, if the validation gate did not exist, it would
    trivially win the ranking -- proving the rejected scenario is a genuine
    attack, not a vacuous one."""
    window = _smuggled_future_window("CCCC")
    # Evaluating the smuggled window in isolation (as the scan itself never
    # would, since validate_scan_universe rejects it first) shows exactly
    # how dominant this future bar's own numbers are.
    outcome = evaluate(window, StrategyParameters(reference_window_size=5))
    assert outcome.decision is TradingDecision.LONG_CANDIDATE
    assert outcome.measurements.current_close == Decimal("500.00")
    assert outcome.measurements.current_volume == 50_000


def test_correctly_synchronized_universe_ranks_normally() -> None:
    """The same instruments, synchronized correctly at the common cutoff
    (no smuggled future bar), pass validation and rank exactly as expected
    -- proving the rejection above is about cutoff synchronization
    specifically, not about the instrument's data being intrinsically
    rejected."""
    windows = [
        _synced_window("AAAA", close="101.00", volume=1500),
        _synced_window("BBBB"),  # NO_TRADE
    ]
    validate_scan_universe(windows)  # must not raise

    parameters = StrategyParameters(reference_window_size=5)
    universe = [
        (window.instrument, DecisionCandidateId(f"DCAND-000{i + 1}"), evaluate(window, parameters))
        for i, window in enumerate(windows)
    ]
    scan = build_scan(
        identity=DomainIdentity(
            governance_id=TradingOpportunityScanId("SCAN-0001"),
            runtime_id=RuntimeIdentifier("80000000-0000-4000-8000-000000000001"),
        ),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    assert scan.candidate_count == 1
    assert scan.no_trade_count == 1
    assert str(scan.ranked_opportunities[0].instrument) == "AAAA"
