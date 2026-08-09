"""MILESTONE-059 Phase 18: independent mathematical verification of the
risk-gated trade-plan pipeline.

This module deliberately does NOT call `empirical_platform.decision_candidate
.trade_plan.compute_stop_price`, `compute_target_price`, `build_geometry`, or
`build_trade_plan`. `_independently_plan` re-derives entry/stop/target/risk/
reward/reward-risk-ratio and the final APPROVED/REJECTED decision with its
own separately-authored arithmetic, reading only the raw JSON fixture files
-- a second, independently-authored path with no shared code with the
production trade-plan module other than the fixture files themselves and
the frozen, already-independently-verified (M057 Phase 16) `evaluate()`
function, which this module reuses only to obtain `reference_high`/
`current_close` -- not to compute any trade-plan-specific value.

Each test then calls the real production `build_trade_plan()` on the same
source data and asserts the two independently-computed answers agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.scan import build_scan
from empirical_platform.decision_candidate.strategy import (
    StrategyParameters,
    evaluate,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, build_trade_plan
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier

_M058_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m058_market_scan"
    / "synthetic_6instrument_scan_universe.json"
)
_M059_BOUNDARY_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m059_trade_plan"
    / "synthetic_boundary_ratio_universe.json"
)
_REFERENCE_WINDOW_SIZE = 5
_TARGET_PROJECTION_PERCENT = Decimal("0.02")
_MINIMUM_REWARD_RISK_RATIO = Decimal("2.0")
_EVID = EvidencePackageId("EVID-0001")


@dataclass(frozen=True)
class _IndependentPlan:
    symbol: str
    approved: bool
    reason: str | None
    entry: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    risk: Decimal | None
    reward: Decimal | None
    ratio: Decimal | None


def _independent_evaluate(bars_raw: list[dict[str, str]]) -> tuple[str, Decimal, int, Decimal]:
    """Re-derive (decision, current_close, current_volume, reference_high)
    using the same independent max/mean technique already established in
    test_decision_candidate_independent_verification.py (M057) -- kept
    minimal here since strategy-level verification is that module's job,
    not this one's."""
    reference_rows = bars_raw[:-1][-_REFERENCE_WINDOW_SIZE:]
    evaluation_row = bars_raw[-1]
    reference_high = max(Decimal(row["high"]) for row in reference_rows)
    reference_average_volume = sum(Decimal(row["volume"]) for row in reference_rows) / Decimal(
        len(reference_rows)
    )
    current_close = Decimal(evaluation_row["close"])
    current_volume = int(evaluation_row["volume"])
    price_above = current_close > reference_high
    volume_above = Decimal(current_volume) > reference_average_volume
    decision = "LONG_CANDIDATE" if price_above and volume_above else "NO_TRADE"
    return decision, current_close, current_volume, reference_high


def _independently_plan_from_measurements(
    *, symbol: str, decision: str, current_close: Decimal, reference_high: Decimal
) -> _IndependentPlan:
    """A separately-authored reimplementation of the M059 risk-gate
    pipeline, computed as a single expression chain rather than mirroring
    `build_trade_plan()`'s own step-by-step branching shape."""
    if decision != "LONG_CANDIDATE":
        return _IndependentPlan(
            symbol=symbol,
            approved=False,
            reason="SOURCE_NOT_LONG_CANDIDATE",
            entry=None,
            stop=None,
            target=None,
            risk=None,
            reward=None,
            ratio=None,
        )

    entry = current_close
    stop = reference_high  # invalidation level == breakout level
    target = reference_high + (reference_high * _TARGET_PROJECTION_PERCENT)

    if not (stop < entry):
        return _IndependentPlan(
            symbol, False, "INVALID_STOP_GEOMETRY", entry, stop, target, None, None, None
        )
    if not (target > entry):
        return _IndependentPlan(
            symbol, False, "INVALID_TARGET_GEOMETRY", entry, stop, target, None, None, None
        )

    risk = entry - stop
    reward = target - entry
    ratio = reward / risk
    if ratio < _MINIMUM_REWARD_RISK_RATIO:
        return _IndependentPlan(
            symbol, False, "REWARD_RISK_BELOW_MINIMUM", entry, stop, target, risk, reward, ratio
        )
    return _IndependentPlan(symbol, True, None, entry, stop, target, risk, reward, ratio)


def _production_plan_for_instrument(
    fixture_path: Path, symbol: str
) -> tuple[str, bool, str | None, Decimal | None]:
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
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
    outcomes = [evaluate(window, parameters) for window in windows]
    universe = list(zip((w.instrument for w in windows), candidate_ids, outcomes, strict=True))

    scan = build_scan(
        identity=DomainIdentity(
            governance_id=TradingOpportunityScanId("SCAN-0001"),
            runtime_id=RuntimeIdentifier("40000000-0000-4000-8000-000000000001"),
        ),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=windows[0].evaluation_bar.timestamp,
        universe=universe,
    )

    index = next(i for i, w in enumerate(windows) if str(w.instrument) == symbol)
    window = windows[index]
    candidate = DecisionCandidate(
        identity=DomainIdentity(
            governance_id=candidate_ids[index],
            runtime_id=RuntimeIdentifier("50000000-0000-4000-8000-000000000001"),
        ),
        target_evidence_package_id=_EVID,
        instrument=window.instrument,
        interval=window.interval,
        evaluation_timestamp=window.evaluation_bar.timestamp,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        reference_window_size=_REFERENCE_WINDOW_SIZE,
        outcome=outcomes[index],
    )
    plan = build_trade_plan(
        identity=DomainIdentity(
            governance_id=TradePlanId("PLAN-0001"),
            runtime_id=RuntimeIdentifier("60000000-0000-4000-8000-000000000001"),
        ),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=DEFAULT_RISK_POLICY,
    )
    approved = plan.status.value == "APPROVED_PLAN"
    reason = plan.reasons[0].value if plan.reasons else None
    ratio = plan.geometry.reward_risk_ratio if plan.geometry else None
    return plan.status.value, approved, reason, ratio


def _run_case(fixture_path: Path, symbol: str) -> None:
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    bars_raw = next(
        entry["bars"] for entry in raw["instruments"] if entry["bars"][0]["instrument"] == symbol
    )
    decision, current_close, _current_volume, reference_high = _independent_evaluate(bars_raw)
    independent = _independently_plan_from_measurements(
        symbol=symbol,
        decision=decision,
        current_close=current_close,
        reference_high=reference_high,
    )

    _status, production_approved, production_reason, production_ratio = (
        _production_plan_for_instrument(fixture_path, symbol)
    )

    assert independent.approved == production_approved
    assert independent.reason == production_reason
    if independent.ratio is not None:
        assert production_ratio is not None
        assert independent.ratio == production_ratio
    else:
        assert production_ratio is None


def test_independent_verification_aapl_approved() -> None:
    _run_case(_M058_FIXTURE, "AAPL")


def test_independent_verification_amzn_invalid_target() -> None:
    _run_case(_M058_FIXTURE, "AMZN")


def test_independent_verification_nvda_below_minimum_ratio() -> None:
    _run_case(_M058_FIXTURE, "NVDA")


def test_independent_verification_msft_not_long_candidate() -> None:
    _run_case(_M058_FIXTURE, "MSFT")


def test_independent_verification_boundary_exact_ratio() -> None:
    _run_case(_M059_BOUNDARY_FIXTURE, "BNDA")


def test_independent_verification_boundary_just_below_ratio() -> None:
    _run_case(_M059_BOUNDARY_FIXTURE, "BNDB")
