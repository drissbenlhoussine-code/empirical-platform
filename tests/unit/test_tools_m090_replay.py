"""MILESTONE-090 Phase 19/20 -- non-network logic of the `tools/m090_replay.py` CLI.

No test here touches the network: `collect_results` is exercised against `FakeBars`
(`tests/unit/_m090_fakes.py`), never `AlpacaPaperMarketDataClient`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import tools.m090_replay as m090_replay
from tests.unit._m090_fakes import FakeBars, FakeBarView

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.usecases.opportunity_engine_replay import (
    ReplayDecision,
    ReplaySessionResult,
)

_SYMBOL = "AAPL"


def test_recent_completed_session_dates_skips_weekends_and_excludes_today() -> None:
    # 2026-06-10 is a Wednesday.
    dates = m090_replay.recent_completed_session_dates(5, before=date(2026, 6, 10))
    assert date(2026, 6, 10) not in dates
    assert all(d.weekday() < 5 for d in dates)
    assert dates == tuple(sorted(dates))
    assert len(dates) == 5


def test_recent_completed_session_dates_crosses_a_weekend_correctly() -> None:
    # 2026-06-08 is a Monday; the immediately preceding weekdays skip Sat/Sun back to Friday.
    dates = m090_replay.recent_completed_session_dates(3, before=date(2026, 6, 8))
    assert dates == (date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 5))


def test_recent_completed_session_dates_refuses_a_non_positive_count() -> None:
    with pytest.raises(ValueError, match="count must be at least 1"):
        m090_replay.recent_completed_session_dates(0, before=date(2026, 6, 10))


def test_parse_args_splits_and_upper_cases_symbols() -> None:
    args = m090_replay._parse_args(["--symbols", "aapl, msft,spy", "--sessions", "3"])
    assert args.symbols == ("AAPL", "MSFT", "SPY")
    assert args.sessions == 3


def test_parse_args_defaults() -> None:
    args = m090_replay._parse_args([])
    assert args.symbols == m090_replay.DEFAULT_SYMBOLS
    assert args.sessions == 5
    assert args.report_path is None


def test_parse_args_rejects_a_non_positive_session_count() -> None:
    with pytest.raises(SystemExit):
        m090_replay._parse_args(["--sessions", "0"])


def test_parse_args_rejects_an_empty_symbol_list() -> None:
    with pytest.raises(SystemExit):
        m090_replay._parse_args(["--symbols", " , ,"])


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 6, 10, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _breakout_bars() -> list[Bar]:
    return [
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        _bar(minute=5, o="100.50", h="101.80", low="100.10", c="101.50", v=2500),
        _bar(minute=6, o="101.50", h="106.60", low="101.00", c="106.00", v=2000),
    ]


def _bar_view(bar: Bar) -> FakeBarView:
    return FakeBarView(
        symbol=_SYMBOL,
        timestamp=bar.timestamp,
        open=str(bar.open),
        high=str(bar.high),
        low=str(bar.low),
        close=str(bar.close),
        volume=bar.volume,
    )


def test_collect_results_skips_a_session_symbol_pair_with_no_bars() -> None:
    bars_port = FakeBars(bars={})
    configuration = m090_replay.default_configuration((_SYMBOL,))
    policy = m090_replay.default_policy()
    results = m090_replay.collect_results(
        bars_port,
        (_SYMBOL,),
        (date(2026, 6, 10),),
        policy=policy,
        configuration=configuration,
    )
    assert results == ()


def test_collect_results_produces_one_result_per_session_with_bars() -> None:
    views = tuple(_bar_view(b) for b in _breakout_bars())
    bars_port = FakeBars(bars={_SYMBOL: views})
    configuration = m090_replay.default_configuration((_SYMBOL,))
    policy = m090_replay.default_policy()
    results = m090_replay.collect_results(
        bars_port,
        (_SYMBOL,),
        (date(2026, 6, 10),),
        policy=policy,
        configuration=configuration,
    )
    assert len(results) == 1
    assert results[0].symbol == _SYMBOL
    assert results[0].session_date == date(2026, 6, 10)
    # At least the breakout bar (index 5) should have reached an ACTIONABLE decision.
    assert any(not d.rejection_reasons for d in results[0].decisions)


def _decision(
    *,
    rejection_reasons: tuple[object, ...] = (),
    reward_risk_ratio: Decimal | None = None,
    risk_per_share: Decimal | None = None,
    quantity: int | None = None,
    decided_hour: int = 14,
    outcome: object | None = None,
) -> ReplayDecision:
    return ReplayDecision(
        bar_index=5,
        decided_at=datetime(2026, 6, 10, decided_hour, 5, tzinfo=UTC),
        symbol=_SYMBOL,
        rejection_reasons=rejection_reasons,  # type: ignore[arg-type]
        entry_price=Decimal("101.50") if not rejection_reasons else None,
        stop_price=Decimal("99.00") if not rejection_reasons else None,
        target_price=Decimal("106.50") if not rejection_reasons else None,
        risk_per_share=risk_per_share,
        reward_per_share=None,
        reward_risk_ratio=reward_risk_ratio,
        quantity=quantity,
        quality_score=None,
        outcome=outcome,  # type: ignore[arg-type]
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )


def test_build_report_separates_engine_signal_quality_from_hypothetical_outcome() -> None:
    from empirical_platform.decision_candidate.opportunity_engine import RejectionReason
    from empirical_platform.usecases.opportunity_engine_replay import ReplayOutcome

    actionable = _decision(
        reward_risk_ratio=Decimal("2.5"),
        risk_per_share=Decimal("2.50"),
        quantity=40,
        decided_hour=15,
        outcome=ReplayOutcome.TARGET_HIT,
    )
    rejected = _decision(rejection_reasons=(RejectionReason.NO_BREAKOUT_STRUCTURE,))
    result = ReplaySessionResult(
        symbol=_SYMBOL,
        session_date=date(2026, 6, 10),
        bar_count=7,
        decisions=(actionable, rejected),
    )
    report = m090_replay.build_report(
        (result,),
        symbols=(_SYMBOL,),
        session_dates=(date(2026, 6, 10),),
        generated_at=datetime(2026, 6, 11, 0, 0, tzinfo=UTC),
    )
    assert "## ENGINE SIGNAL QUALITY" in report
    assert "## HYPOTHETICAL HISTORICAL OUTCOME" in report
    assert "Total observations (bar-evaluations with enough reference history): 2" in report
    assert "ACTIONABLE (opportunities generated): 1" in report
    assert "REJECTED: 1" in report
    assert "- NO_BREAKOUT_STRUCTURE: 1" in report
    assert "min=2.5, median=2.5, max=2.5, n=1" in report
    assert "min=100.00, median=100.00, max=100.00, n=1" in report  # 2.50 * 40
    assert "15:00 UTC x1" in report
    assert "- TARGET_HIT: 1" in report
    assert "No expected-value, win-rate or profitability claim is made" in report


def test_build_report_with_no_results_states_n_a_rather_than_crashing() -> None:
    report = m090_replay.build_report(
        (),
        symbols=(_SYMBOL,),
        session_dates=(date(2026, 6, 10),),
        generated_at=datetime(2026, 6, 11, 0, 0, tzinfo=UTC),
    )
    assert "Total observations (bar-evaluations with enough reference history): 0" in report
    assert "n/a (no ACTIONABLE decisions)" in report
    assert "(no rejections)" in report
    assert "(no ACTIONABLE decisions to resolve)" in report
