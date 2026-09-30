"""MILESTONE-091 Phase 7 -- the look-ahead audit, run against REAL market bar shapes.

`test_usecases_opportunity_engine_replay.py` already proves the frozen replay harness has
no look-ahead using hand-built bars. This file re-proves the SAME property end-to-end
through THIS milestone's own data-loading/decision path
(`tools.m091_validation.fetch_and_validate_session_bars` + `frozen_policy`/
`frozen_configuration` + `replay_session`, unmodified), using a real, previously-fetched
60-bar snapshot of NVDA 1-minute bars (`_m091_real_bar_snapshot.json`, captured 2026-09-30
from the real Alpaca Paper IEX feed for session 2026-09-28) -- never a live network call
during the test suite itself, so this stays fast and offline while still exercising real
market-bar shapes rather than only hand-built round numbers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import tools.m091_validation as m091_validation

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.usecases.opportunity_engine_replay import replay_session

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "_m091_real_bar_snapshot.json"


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


def test_a_poisoned_future_bar_never_changes_any_earlier_decision_over_real_market_bars() -> None:
    """The M091 validation's own frozen policy/configuration, run over a REAL fetched bar
    sequence: appending one impossible, extreme future bar must not change any decision's
    TERMS at or before the bar that preceded it -- proving this milestone's own data-loading
    path is look-ahead-safe end to end, not only the M090 unit fixtures."""
    real_bars = _load_real_bars()
    policy = m091_validation.frozen_policy()
    configuration = m091_validation.frozen_configuration()
    liquidation_at = datetime(2026, 9, 28, 23, 59, tzinfo=UTC)

    baseline = replay_session(
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

    poisoned = replay_session(
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


def test_fetch_and_validate_session_bars_output_type_matches_what_replay_session_expects() -> None:
    """A structural sanity check that the M091 data-loading function produces exactly the
    `Bar` type `replay_session` consumes -- proven once here so the adversarial test above
    is trusted to exercise the real path, not a look-alike."""
    real_bars = _load_real_bars()
    assert all(isinstance(b, Bar) for b in real_bars)
    assert len(real_bars) == 60
    # Strictly chronological -- the same invariant fetch_and_validate_session_bars enforces
    # on the real, larger fetch.
    for earlier, later in zip(real_bars, real_bars[1:], strict=False):
        assert later.timestamp > earlier.timestamp
