"""MILESTONE-059 Phase 19: look-ahead / data-time audit for the risk-gated
trade-plan pipeline.

`build_trade_plan()` (`decision_candidate/trade_plan.py`) reads exactly two
values from its `candidate` argument's own `outcome.measurements`:
`current_close` and `reference_high`. Both are immutable fields on an
already-persisted `DecisionCandidate`, computed once, at candidate-build
time, by the M057 `strategy.evaluate()` function -- which has its own
independent, already-audited (M057 Phase 18) look-ahead defense. M059
introduces no new market-data access of its own: `build_trade_plan()`
never touches a raw `Bar`, `ObservationWindow`, or wall clock, and the
handler that calls it (`usecases/build_trade_plan.py`) loads only the
exact, already-identified `scan`/`candidate` records -- nothing "later" or
"latest". There is no new surface for future data to enter through.

This module proves that claim two ways: structurally (by inspecting
`build_trade_plan()`'s own signature) and empirically, by reusing M057's
own look-ahead regression fixture (`synthetic_aapl_1min_lookahead_probe
.json` -- an evaluation bar whose own extreme high/volume would corrupt
`reference_high` to 200.00 if it ever leaked into the M057 strategy's
reference-window computation) as a *cross-milestone* regression trap: if
M057's look-ahead protection were ever broken, the resulting `TradePlan`
here would silently flip from one rejection reason to a different, easily
distinguishable one.
"""

from __future__ import annotations

import inspect
import json
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
    EvaluationOutcome,
    StrategyParameters,
    evaluate,
)
from empirical_platform.decision_candidate.trade_plan import (
    DEFAULT_RISK_POLICY,
    TradePlan,
    TradePlanRejectionReason,
    TradePlanStatus,
    build_trade_plan,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier

_M057_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "m057_market_data"
_LOOKAHEAD_PROBE_FIXTURE = _M057_FIXTURES_DIR / "synthetic_aapl_1min_lookahead_probe.json"
_LONG_CANDIDATE_FIXTURE = _M057_FIXTURES_DIR / "synthetic_aapl_1min_long_candidate.json"
_EVID = EvidencePackageId("EVID-0001")


def _plan_for_m057_fixture(fixture_path: Path) -> tuple[TradePlan, EvaluationOutcome]:
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
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
        for row in raw
    )
    window = ObservationWindow(bars=bars)
    outcome = evaluate(window, StrategyParameters(reference_window_size=5))

    candidate_identity = DomainIdentity(
        governance_id=DecisionCandidateId("DCAND-0001"),
        runtime_id=RuntimeIdentifier("10000000-0000-4000-8000-000000000001"),
    )
    candidate = DecisionCandidate(
        identity=candidate_identity,
        target_evidence_package_id=_EVID,
        instrument=window.instrument,
        interval=window.interval,
        evaluation_timestamp=window.evaluation_bar.timestamp,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        reference_window_size=5,
        outcome=outcome,
    )
    scan = build_scan(
        identity=DomainIdentity(
            governance_id=TradingOpportunityScanId("SCAN-0001"),
            runtime_id=RuntimeIdentifier("20000000-0000-4000-8000-000000000001"),
        ),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=window.evaluation_bar.timestamp,
        universe=[(window.instrument, candidate_identity.governance_id, outcome)],
    )
    return build_trade_plan(
        identity=DomainIdentity(
            governance_id=TradePlanId("PLAN-0001"),
            runtime_id=RuntimeIdentifier("30000000-0000-4000-8000-000000000001"),
        ),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=DEFAULT_RISK_POLICY,
    ), outcome


def test_build_trade_plan_reads_no_raw_bars_or_wall_clock() -> None:
    """Structural proof: `build_trade_plan()`'s own signature accepts only
    already-persisted `scan`/`candidate` domain objects (plus identity and
    policy) -- no `Bar`, `ObservationWindow`, or timestamp-generation
    parameter exists for future data to enter through."""
    signature = inspect.signature(build_trade_plan)
    parameter_names = set(signature.parameters)
    assert parameter_names == {
        "identity",
        "scan",
        "candidate",
        "target_evidence_package_id",
        "policy",
    }
    for forbidden in ("bars", "window", "observation_window", "now", "clock"):
        assert forbidden not in parameter_names


def test_lookahead_probe_trade_plan_uses_uncorrupted_reference_high() -> None:
    """Cross-milestone regression trap. The lookahead-probe evaluation bar
    carries close=150.00 with an extreme high=200.00/volume=5000 that would
    corrupt reference_high to 200.00 if M057's own look-ahead defense were
    ever broken.

    With the correct, uncorrupted reference_high (100.50, from the five
    true reference bars only): stop_price=100.50 < entry=150.00 (valid
    stop), but target_price=100.50*1.02=102.51 <= entry=150.00 -- so the
    plan is REJECTED for INVALID_TARGET_GEOMETRY (an extended breakout that
    already overshot even a generous target).

    If reference_high were ever corrupted to 200.00 instead, stop_price
    would become 200.00 >= entry=150.00 -- REJECTED for the completely
    different INVALID_STOP_GEOMETRY. The two rejection reasons are mutually
    exclusive and immediately diagnostic: this test would fail loudly,
    with a different reason code, if M057's look-ahead protection were
    ever broken.
    """
    plan, outcome = _plan_for_m057_fixture(_LOOKAHEAD_PROBE_FIXTURE)

    # Confirm the fixture still produces the expected, uncorrupted M057
    # measurements before trusting the M059-level assertion below.
    assert outcome.measurements.reference_high == Decimal("100.50")
    assert outcome.measurements.current_close == Decimal("150.00")

    assert plan.status is TradePlanStatus.REJECTED_PLAN
    assert plan.reasons == (TradePlanRejectionReason.INVALID_TARGET_GEOMETRY,)
    assert plan.geometry is None


def test_normal_fixture_trade_plan_is_unaffected_by_lookahead_probe() -> None:
    """Positive control: the ordinary M057 long-candidate fixture (no
    extreme future-looking bar at all) produces a normal, valid,
    APPROVED_PLAN -- proving the rejection above is specifically about the
    probe's own extreme geometry, not a general defect in the pipeline."""
    plan, outcome = _plan_for_m057_fixture(_LONG_CANDIDATE_FIXTURE)

    assert outcome.measurements.reference_high == Decimal("100.50")
    assert outcome.measurements.current_close == Decimal("101.10")
    assert plan.status is TradePlanStatus.APPROVED_PLAN
    assert plan.geometry is not None
    assert plan.geometry.stop_price == Decimal("100.50")
