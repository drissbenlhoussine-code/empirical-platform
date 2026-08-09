"""MILESTONE-058 unit tests for the trading opportunity scan domain:
universe validation, ranking assembly, and the `TradingOpportunityScan`
record's own invariants and derived properties. Pure, no PostgreSQL.
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
from empirical_platform.decision_candidate.scan import (
    ScanEvaluationEntry,
    TradingOpportunityScan,
    build_scan,
    validate_scan_universe,
)
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

_CUTOFF = datetime(2026, 8, 10, 13, 40, 0, tzinfo=UTC)
_EVID = EvidencePackageId("EVID-0001")


def _bar(*, instrument: Instrument, minute_offset: int, close: str, high: str, volume: int) -> Bar:
    close_decimal = Decimal(close)
    high_decimal = Decimal(high)
    low_decimal = min(close_decimal, high_decimal) - Decimal("0.10")
    return Bar(
        instrument=instrument,
        interval=BarInterval.ONE_MINUTE,
        timestamp=_CUTOFF - timedelta(minutes=5) + timedelta(minutes=minute_offset),
        open=close_decimal,
        high=high_decimal,
        low=low_decimal,
        close=close_decimal,
        volume=volume,
    )


def _window(
    *,
    symbol: str,
    reference_highs: list[str],
    reference_volumes: list[int],
    eval_close: str,
    eval_high: str,
    eval_volume: int,
) -> ObservationWindow:
    instrument = Instrument(symbol)
    reference = [
        _bar(instrument=instrument, minute_offset=i, close=h, high=h, volume=v)
        for i, (h, v) in enumerate(zip(reference_highs, reference_volumes, strict=True))
    ]
    evaluation = _bar(
        instrument=instrument,
        minute_offset=len(reference),
        close=eval_close,
        high=eval_high,
        volume=eval_volume,
    )
    return ObservationWindow(bars=(*reference, evaluation))


def _long_candidate_window(
    symbol: str, *, close: str = "101.00", volume: int = 1600
) -> ObservationWindow:
    return _window(
        symbol=symbol,
        reference_highs=["100.00", "100.20", "100.30", "100.40", "100.50"],
        reference_volumes=[1000, 1050, 980, 1020, 1010],
        eval_close=close,
        eval_high=str(Decimal(close) + Decimal("0.10")),
        eval_volume=volume,
    )


def _no_trade_window(symbol: str) -> ObservationWindow:
    return _window(
        symbol=symbol,
        reference_highs=["100.00", "100.20", "100.30", "100.40", "100.50"],
        reference_volumes=[1000, 1050, 980, 1020, 1010],
        eval_close="100.40",
        eval_high="100.45",
        eval_volume=900,
    )


def _candidate_id(n: int) -> DecisionCandidateId:
    return DecisionCandidateId(f"DCAND-{n:04d}")


def _scan_identity(n: int = 1) -> DomainIdentity[TradingOpportunityScanId]:
    return DomainIdentity(
        governance_id=TradingOpportunityScanId(f"SCAN-{n:04d}"),
        runtime_id=RuntimeIdentifier(f"a000000{n}-0000-4000-8000-000000000001"),
    )


# --- validate_scan_universe ---------------------------------------------


def test_validate_scan_universe_accepts_consistent_windows() -> None:
    windows = [_long_candidate_window("AAAA"), _no_trade_window("BBBB")]
    validate_scan_universe(windows)  # must not raise


def test_validate_scan_universe_rejects_empty_universe() -> None:
    with pytest.raises(ValueError, match="at least 1 instrument"):
        validate_scan_universe([])


def test_validate_scan_universe_rejects_mismatched_interval() -> None:
    aaaa = _long_candidate_window("AAAA")
    bbbb_bars = tuple(
        Bar(
            instrument=Instrument("BBBB"),
            interval=BarInterval.FIVE_MINUTE,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for bar in _no_trade_window("BBBB").bars
    )
    bbbb = ObservationWindow(bars=bbbb_bars)
    with pytest.raises(ValueError, match="one bar interval"):
        validate_scan_universe([aaaa, bbbb])


def test_validate_scan_universe_rejects_mismatched_cutoff() -> None:
    aaaa = _long_candidate_window("AAAA")
    shifted_bars = tuple(
        Bar(
            instrument=bar.instrument,
            interval=bar.interval,
            timestamp=bar.timestamp + timedelta(minutes=1),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for bar in _no_trade_window("BBBB").bars
    )
    bbbb = ObservationWindow(bars=shifted_bars)
    with pytest.raises(ValueError, match="one evaluation cutoff"):
        validate_scan_universe([aaaa, bbbb])


def test_validate_scan_universe_rejects_duplicate_instrument() -> None:
    aaaa_1 = _long_candidate_window("AAAA")
    aaaa_2 = _no_trade_window("AAAA")
    with pytest.raises(ValueError, match="duplicate instrument"):
        validate_scan_universe([aaaa_1, aaaa_2])


# --- ScanEvaluationEntry invariants --------------------------------------


def test_scan_evaluation_entry_rejects_long_candidate_without_rank_or_score() -> None:
    window = _long_candidate_window("AAAA")
    outcome = evaluate(window, StrategyParameters())
    with pytest.raises(ValueError, match="must carry both rank and score"):
        ScanEvaluationEntry(
            instrument=window.instrument,
            decision_candidate_id=_candidate_id(1),
            decision=outcome.decision,
            measurements=outcome.measurements,
            reasons=outcome.reasons,
            rank=None,
            score=None,
        )


def test_scan_evaluation_entry_rejects_no_trade_with_rank_or_score() -> None:
    window = _no_trade_window("BBBB")
    outcome = evaluate(window, StrategyParameters())
    with pytest.raises(ValueError, match="must carry neither rank nor score"):
        ScanEvaluationEntry(
            instrument=window.instrument,
            decision_candidate_id=_candidate_id(1),
            decision=outcome.decision,
            measurements=outcome.measurements,
            reasons=outcome.reasons,
            rank=1,
            score=Decimal("1.0"),
        )


# --- build_scan -----------------------------------------------------------


def test_build_scan_ranks_only_long_candidates() -> None:
    windows = {
        "AAAA": _long_candidate_window("AAAA"),
        "BBBB": _no_trade_window("BBBB"),
        "CCCC": _long_candidate_window("CCCC", close="105.00", volume=3000),
    }
    parameters = StrategyParameters()
    universe = [
        (window.instrument, _candidate_id(i + 1), evaluate(window, parameters))
        for i, window in enumerate(windows.values())
    ]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    assert scan.total_instruments == 3
    assert scan.candidate_count == 2
    assert scan.no_trade_count == 1
    ranked_symbols = [str(entry.instrument) for entry in scan.ranked_opportunities]
    assert set(ranked_symbols) == {"AAAA", "CCCC"}
    assert "BBBB" not in ranked_symbols


def test_build_scan_assigns_contiguous_ranks_by_score_descending() -> None:
    parameters = StrategyParameters()
    weak = _long_candidate_window("AAAA", close="100.60", volume=1100)
    strong = _long_candidate_window("BBBB", close="110.00", volume=5000)
    universe = [
        (weak.instrument, _candidate_id(1), evaluate(weak, parameters)),
        (strong.instrument, _candidate_id(2), evaluate(strong, parameters)),
    ]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    ranked = scan.ranked_opportunities
    assert [entry.rank for entry in ranked] == [1, 2]
    assert str(ranked[0].instrument) == "BBBB"
    assert str(ranked[1].instrument) == "AAAA"
    assert ranked[0].score > ranked[1].score  # type: ignore[operator]


def test_build_scan_tie_breaks_by_instrument_symbol_ascending() -> None:
    """Two instruments with byte-for-byte identical measurements (hence
    identical scores) must break the tie by symbol, deterministically."""
    parameters = StrategyParameters()
    zzzz = _long_candidate_window("ZZZZ")
    aaaa = _long_candidate_window("AAAA")
    universe = [
        (zzzz.instrument, _candidate_id(1), evaluate(zzzz, parameters)),
        (aaaa.instrument, _candidate_id(2), evaluate(aaaa, parameters)),
    ]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    ranked = scan.ranked_opportunities
    assert ranked[0].score == ranked[1].score
    assert [str(entry.instrument) for entry in ranked] == ["AAAA", "ZZZZ"]
    assert [entry.rank for entry in ranked] == [1, 2]


def test_build_scan_ranking_is_independent_of_universe_input_order() -> None:
    """The ranked order must depend only on scores (and, on ties, instrument
    symbol) -- never on the order instruments happened to be supplied in.
    `scan.evaluations` deliberately preserves universe order (see the test
    below), but `ranked_opportunities` must not."""
    parameters = StrategyParameters()
    weak = _long_candidate_window("AAAA", close="100.60", volume=1100)
    strong = _long_candidate_window("BBBB", close="110.00", volume=5000)
    middle = _long_candidate_window("CCCC", close="103.00", volume=2000)

    forward_universe = [
        (weak.instrument, _candidate_id(1), evaluate(weak, parameters)),
        (middle.instrument, _candidate_id(2), evaluate(middle, parameters)),
        (strong.instrument, _candidate_id(3), evaluate(strong, parameters)),
    ]
    reversed_universe = list(reversed(forward_universe))

    forward_scan = build_scan(
        identity=_scan_identity(1),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=forward_universe,
    )
    reversed_scan = build_scan(
        identity=_scan_identity(2),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=reversed_universe,
    )

    forward_order = [str(e.instrument) for e in forward_scan.ranked_opportunities]
    reversed_order = [str(e.instrument) for e in reversed_scan.ranked_opportunities]
    assert forward_order == reversed_order == ["BBBB", "CCCC", "AAAA"]


def test_build_scan_preserves_strategy_and_ranking_model_identity() -> None:
    """Both the strategy identity and the ranking-model identity must be
    recorded verbatim on the scan, independent of each other -- a future
    ranking-model version bump must never silently alter the recorded
    strategy_id/strategy_version, and vice versa."""
    window = _long_candidate_window("AAAA")
    outcome = evaluate(window, StrategyParameters())
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=[(window.instrument, _candidate_id(1), outcome)],
    )
    assert scan.strategy_id == "PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION"
    assert scan.strategy_version == "1"
    assert scan.ranking_model_id == "BREAKOUT_VOLUME_STRENGTH_SUM"
    assert scan.ranking_model_version == "1"


def test_build_scan_preserves_universe_order_in_evaluations() -> None:
    parameters = StrategyParameters()
    windows = [
        _no_trade_window("CCCC"),
        _long_candidate_window("AAAA"),
        _no_trade_window("BBBB"),
    ]
    universe = [
        (window.instrument, _candidate_id(i + 1), evaluate(window, parameters))
        for i, window in enumerate(windows)
    ]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    assert [str(entry.instrument) for entry in scan.evaluations] == ["CCCC", "AAAA", "BBBB"]


# --- TradingOpportunityScan invariants ------------------------------------


def test_trading_opportunity_scan_rejects_empty_evaluations() -> None:
    with pytest.raises(ValueError, match="at least 1 instrument"):
        TradingOpportunityScan(
            identity=_scan_identity(),
            target_evidence_package_id=_EVID,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            evaluation_cutoff=_CUTOFF,
            evaluations=(),
        )


def test_trading_opportunity_scan_rejects_non_contiguous_ranks() -> None:
    window = _long_candidate_window("AAAA")
    outcome = evaluate(window, StrategyParameters())
    entry = ScanEvaluationEntry(
        instrument=window.instrument,
        decision_candidate_id=_candidate_id(1),
        decision=outcome.decision,
        measurements=outcome.measurements,
        reasons=outcome.reasons,
        rank=2,  # not contiguous from 1
        score=Decimal("1.0"),
    )
    with pytest.raises(ValueError, match="contiguous 1..N"):
        TradingOpportunityScan(
            identity=_scan_identity(),
            target_evidence_package_id=_EVID,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            evaluation_cutoff=_CUTOFF,
            evaluations=(entry,),
        )


def test_trading_opportunity_scan_rejects_naive_evaluation_cutoff() -> None:
    window = _no_trade_window("AAAA")
    outcome = evaluate(window, StrategyParameters())
    entry = ScanEvaluationEntry(
        instrument=window.instrument,
        decision_candidate_id=_candidate_id(1),
        decision=outcome.decision,
        measurements=outcome.measurements,
        reasons=outcome.reasons,
        rank=None,
        score=None,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        TradingOpportunityScan(
            identity=_scan_identity(),
            target_evidence_package_id=_EVID,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            evaluation_cutoff=datetime(2026, 8, 10, 13, 40, 0),  # naive
            evaluations=(entry,),
        )


def test_build_scan_all_no_trade_universe_has_no_ranked_opportunities() -> None:
    parameters = StrategyParameters()
    windows = [_no_trade_window("AAAA"), _no_trade_window("BBBB")]
    universe = [
        (window.instrument, _candidate_id(i + 1), evaluate(window, parameters))
        for i, window in enumerate(windows)
    ]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    assert scan.candidate_count == 0
    assert scan.no_trade_count == 2
    assert scan.ranked_opportunities == ()


def test_build_scan_all_long_candidate_universe_ranks_every_instrument() -> None:
    parameters = StrategyParameters()
    windows = [
        _long_candidate_window("AAAA"),
        _long_candidate_window("BBBB", close="103.00", volume=2500),
    ]
    universe = [
        (window.instrument, _candidate_id(i + 1), evaluate(window, parameters))
        for i, window in enumerate(windows)
    ]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    assert scan.candidate_count == 2
    assert scan.no_trade_count == 0
    assert {entry.rank for entry in scan.ranked_opportunities} == {1, 2}


def test_build_scan_single_instrument_universe() -> None:
    parameters = StrategyParameters()
    window = _long_candidate_window("AAAA")
    universe = [(window.instrument, _candidate_id(1), evaluate(window, parameters))]
    scan = build_scan(
        identity=_scan_identity(),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )
    assert scan.total_instruments == 1
    assert scan.candidate_count == 1
    assert scan.ranked_opportunities[0].rank == 1


def test_scan_decision_type_is_trading_decision() -> None:
    window = _long_candidate_window("AAAA")
    outcome = evaluate(window, StrategyParameters())
    assert outcome.decision is TradingDecision.LONG_CANDIDATE
