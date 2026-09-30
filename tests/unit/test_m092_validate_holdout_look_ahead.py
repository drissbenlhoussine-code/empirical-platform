"""MILESTONE-092 Phase 17 -- the look-ahead audit, re-proven through the VALIDATION/FINAL
HOLDOUT orchestration's own code path.

The research fork already proved this property for the V2 domain functions in isolation
(hand-built bars) and for `replay_session_v2` generally. This file re-proves it end to end
using a REAL, previously-fetched 60-bar snapshot of NVDA 1-minute bars
(`_m092_real_bar_snapshot.json`, captured from the real Alpaca Paper IEX feed for session
2026-06-11 -- one of the 40 VALIDATION sessions this milestone's own `tools/
m092_validate_holdout.py` actually evaluated) -- never a live network call during the test
suite itself, so this stays fast and offline while still exercising real market-bar shapes
through the EXACT frozen candidate (`candidate_v2_c` from `tools.m092_validation`) this
milestone's VALIDATION run used.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import tools.m092_validation as m092_validation

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.usecases.opportunity_engine_v2_replay import replay_session_v2

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "_m092_real_bar_snapshot.json"


def _load_real_bars() -> tuple[Bar, ...]:
    payload = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    instrument = Instrument(payload["symbol"])
    return tuple(
        Bar(
            instrument=instrument,
            interval=BarInterval.ONE_MINUTE,
            timestamp=datetime.fromisoformat(b["timestamp"]),
            open=Decimal(b["open"]),
            high=Decimal(b["high"]),
            low=Decimal(b["low"]),
            close=Decimal(b["close"]),
            volume=b["volume"],
        )
        for b in payload["bars"]
    )


def _decision_terms(decisions: tuple) -> list[tuple[object, ...]]:  # type: ignore[type-arg]
    return [
        (
            d.bar_index,
            d.decided_at,
            d.rejection_reasons,
            d.entry_price,
            d.stop_price,
            d.target_price,
            d.quantity,
            d.reward_risk_ratio,
        )
        for d in decisions
    ]


def test_a_poisoned_future_bar_never_changes_any_earlier_v2_decision_over_real_bars() -> None:
    """The frozen V2-C candidate, run over a REAL fetched VALIDATION-period bar sequence:
    appending one impossible, extreme future bar must not change any decision's TERMS at or
    before the bar that preceded it -- proving this milestone's own VALIDATION/HOLDOUT
    orchestration path is look-ahead-safe end to end, not only the isolated V2 domain unit
    fixtures."""
    real_bars = _load_real_bars()
    policy = m092_validation.candidate_v2_c()
    configuration = m092_validation._configuration()  # noqa: SLF001 - test reuses the frozen builder
    liquidation_at = datetime(2026, 6, 11, 23, 59, tzinfo=UTC)

    baseline = replay_session_v2(
        symbol="NVDA",
        session_date=real_bars[0].timestamp.date(),
        bars=real_bars,
        policy=policy,
        configuration=configuration,
        deployable_capital=configuration.maximum_deployable_capital,
        mandatory_liquidation_at=liquidation_at,
    )

    instrument = Instrument("NVDA")
    poisoned_bar = Bar(
        instrument=instrument,
        interval=BarInterval.ONE_MINUTE,
        timestamp=real_bars[-1].timestamp + (real_bars[-1].timestamp - real_bars[-2].timestamp),
        open=Decimal("999999"),
        high=Decimal("999999"),
        low=Decimal("999999"),
        close=Decimal("999999"),
        volume=999_999_999,
    )
    poisoned_bars = (*real_bars, poisoned_bar)

    poisoned = replay_session_v2(
        symbol="NVDA",
        session_date=real_bars[0].timestamp.date(),
        bars=poisoned_bars,
        policy=policy,
        configuration=configuration,
        deployable_capital=configuration.maximum_deployable_capital,
        mandatory_liquidation_at=liquidation_at,
    )

    baseline_terms = _decision_terms(baseline.decisions)
    poisoned_terms = _decision_terms(poisoned.decisions[: len(baseline.decisions)])
    assert poisoned_terms == baseline_terms


def test_real_bar_snapshot_is_well_formed_and_chronological() -> None:
    real_bars = _load_real_bars()
    assert all(isinstance(b, Bar) for b in real_bars)
    assert len(real_bars) == 60
    for earlier, later in zip(real_bars, real_bars[1:], strict=False):
        assert later.timestamp > earlier.timestamp


def test_snapshot_session_is_within_the_actually_evaluated_validation_block() -> None:
    """The snapshot's own session date must fall inside the 40-session VALIDATION block this
    milestone's orchestration script actually fetched and evaluated (2026-05-13 ->
    2026-07-07) -- otherwise this test would be proving look-ahead safety for bars the real
    run never touched."""
    payload = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    session_date = date.fromisoformat(payload["session_date"])
    assert date(2026, 5, 13) <= session_date <= date(2026, 7, 7)
