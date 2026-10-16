"""RELEASE v1 -- pure tests for the Active Trade page's MANAGEMENT STATUS derivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    derive_system_identity,
)
from empirical_platform.decision_candidate.position_exit import (
    PositionExitAttempt,
    PositionExitState,
)
from empirical_platform.usecases.v1_management_status import management_status

_NOW = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def _plan(**triggered: object) -> ApprovedPlan:
    owner = "OWN-1"
    plan_id = "PLAN-1"
    fields: dict[str, object] = {
        "plan_id": plan_id,
        "candidate_id": "CAND-1",
        "entry_intent_governance_id": "INT-1",
        "symbol": "AAPL",
        "approved_quantity": Decimal("5"),
        "stop_price": Decimal("95"),
        "target_price": Decimal("110"),
        "mandatory_liquidation_at": _NOW + timedelta(hours=2),
        "owner_approval_id": owner,
        "system_identity": derive_system_identity(plan_id=plan_id, owner_approval_id=owner),
        "created_at": _NOW,
    }
    fields.update(triggered)
    return ApprovedPlan(**fields)  # type: ignore[arg-type]


def _attempt(
    state: PositionExitState, *, closed: bool = False, terminal_at: datetime | None = None
) -> PositionExitAttempt:
    return PositionExitAttempt(
        attempt_id="XAT-1",
        entry_intent_governance_id="INT-1",
        authorization_id="XAU-1",
        client_order_id="m087-x1",
        request_fingerprint="a" * 64,
        symbol="AAPL",
        quantity=5,
        state=state,
        claimed_at=_NOW,
        submitted_at=_NOW,
        acknowledged_at=_NOW,
        terminal_at=terminal_at,
        broker_order_id="BRK-1",
        broker_status=state.value,
        filled_quantity=Decimal("5") if state is PositionExitState.FILLED else None,
        filled_avg_price=Decimal("100") if state is PositionExitState.FILLED else None,
        failure_code=None,
        failure_detail=None,
        closed_position_verified_at=_NOW if closed else None,
    )


def test_no_plan_reads_as_monitoring() -> None:
    assert management_status(None, None) == "Monitoring"


def test_an_unclaimed_plan_is_monitoring() -> None:
    assert management_status(_plan(), None) == "Monitoring"


def test_a_claimed_plan_with_no_attempt_yet_shows_the_trigger_itself() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    assert management_status(plan, None) == "Stop triggered"
    plan = _plan(triggered_exit_kind=ExitTriggerKind.TARGET, triggered_exit_at=_NOW)
    assert management_status(plan, None) == "Target triggered"
    plan = _plan(triggered_exit_kind=ExitTriggerKind.MANDATORY_EXIT, triggered_exit_at=_NOW)
    assert management_status(plan, None) == "Mandatory exit triggered"


def test_a_non_terminal_attempt_is_exit_submitted() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.SUBMISSION_IN_PROGRESS)
    assert management_status(plan, attempt) == "Exit submitted"


def test_a_filled_but_unverified_attempt_needs_attention() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.FILLED, terminal_at=_NOW, closed=False)
    assert management_status(plan, attempt) == "Needs attention"


def test_a_verified_closed_attempt_is_closed() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.FILLED, terminal_at=_NOW, closed=True)
    assert management_status(plan, attempt) == "Closed"


def test_a_failed_or_cancelled_attempt_needs_attention() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.CANCELED, terminal_at=_NOW)
    assert management_status(plan, attempt) == "Needs attention"


def test_an_ambiguous_submission_needs_attention() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.SUBMISSION_UNKNOWN)
    assert management_status(plan, attempt) == "Needs attention"
