"""RELEASE v1 -- `active_plan_block_for_row` / `history_plan_cell_for_row`, the per-row
helpers `paper_operator_console_app.py`'s `/active` and `/history` route overrides call.
Pulled out of the route closures so this computation (unrealized P&L, max loss, the
History "Plan" cell's facts) is directly testable without a WSGI client or real PAPER
credentials.
"""

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
from empirical_platform.entrypoints.paper_operator_console_app import (
    active_plan_block_for_row,
    history_plan_cell_for_row,
)
from empirical_platform.usecases.operator_console import ExecutionSummary, HumanState, TermsView

_NOW = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def _plan(**overrides: object) -> ApprovedPlan:
    owner = "OWN-1"
    plan_id = "PLAN-1"
    fields: dict[str, object] = {
        "plan_id": plan_id,
        "candidate_id": "OPP-1",
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
    fields.update(overrides)
    return ApprovedPlan(**fields)  # type: ignore[arg-type]


def _summary() -> ExecutionSummary:
    return ExecutionSummary(
        intent_id="INT-1",
        proposal_id="PRP-1",
        symbol="AAPL",
        state=HumanState.FILLED,
        raw_state="FILLED",
        terms=TermsView(
            symbol="AAPL",
            side="BUY",
            quantity=5,
            order_type="LIMIT",
            limit_price="100.00",
            time_in_force="DAY",
            extended_hours="No",
            currency="USD",
            notional="500.00",
            fingerprint_short="test-fp-ref",
        ),
        decision_by="owner",
        decided_at=_NOW,
        broker_order_id="BRK-1",
        claimed_at=_NOW,
        submitted_at=_NOW,
        acknowledged_at=_NOW,
        terminal_at=_NOW,
        filled_quantity="5",
        filled_avg_price="100.00",
        pending_reason=None,
        reconciliation="",
        warnings=(),
        timeline=(),
        is_terminal=True,
        outcome_known=True,
        can_cancel=False,
        execution_kind="entry",
        position_open=True,
        exit_status="open",
        category="Open position",
        can_review_exit=True,
    )


_NON_TERMINAL_STATES = {
    PositionExitState.DISPATCH_CLAIMED,
    PositionExitState.SUBMISSION_IN_PROGRESS,
    PositionExitState.SUBMITTED,
    PositionExitState.ACCEPTED,
    PositionExitState.PARTIALLY_FILLED,
    PositionExitState.CANCEL_REQUESTED,
    PositionExitState.SUBMISSION_UNKNOWN,
}


def _attempt(state: PositionExitState, *, closed: bool = False) -> PositionExitAttempt:
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
        terminal_at=None if state in _NON_TERMINAL_STATES else _NOW,
        broker_order_id="BRK-2",
        broker_status=state.value,
        filled_quantity=Decimal("5") if state is PositionExitState.FILLED else None,
        filled_avg_price=Decimal("95.00") if state is PositionExitState.FILLED else None,
        failure_code=None,
        failure_detail=None,
        closed_position_verified_at=_NOW if closed else None,
    )


# ---------------------------------------------------------------------------
# active_plan_block_for_row
# ---------------------------------------------------------------------------


def test_no_plan_produces_no_block() -> None:
    assert active_plan_block_for_row(_summary(), None, None, "99.00") is None


def test_a_monitoring_plan_computes_unrealized_pnl_and_max_loss() -> None:
    block = active_plan_block_for_row(_summary(), _plan(), None, "105.00")
    assert block is not None
    assert "Monitoring" in block
    assert "25.00" in block  # unrealized P&L: (105-100)*5
    assert "25.00" in block  # max loss: 5*(100-95)


def test_a_missing_quote_reads_as_not_available() -> None:
    block = active_plan_block_for_row(_summary(), _plan(), None, None)
    assert block is not None
    assert "Not available" in block


def test_a_claimed_plan_with_an_in_progress_attempt_shows_exit_submitted() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.SUBMISSION_IN_PROGRESS)
    block = active_plan_block_for_row(_summary(), plan, attempt, "95.00")
    assert block is not None
    assert "Exit submitted" in block


def test_a_filled_but_unverified_attempt_needs_attention_on_the_block() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.FILLED, closed=False)
    block = active_plan_block_for_row(_summary(), plan, attempt, "95.00")
    assert block is not None
    assert "Needs attention" in block


def test_a_verified_closed_attempt_shows_closed_and_no_manual_exit_link() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.FILLED, closed=True)
    summary = _summary()
    block = active_plan_block_for_row(summary, plan, attempt, "95.00")
    assert block is not None
    assert "Closed" in block


# ---------------------------------------------------------------------------
# history_plan_cell_for_row
# ---------------------------------------------------------------------------


def test_no_plan_produces_no_cell() -> None:
    assert history_plan_cell_for_row(None, None, "100.00") is None


def test_an_unclaimed_plan_still_shows_candidate_and_owner() -> None:
    cell = history_plan_cell_for_row(_plan(), None, "100.00")
    assert cell is not None
    assert "Candidate OPP-1" in cell
    assert "Owner OWN-1" in cell
    assert "Trigger —" in cell
    assert "Exit order —" in cell
    assert "Not filled" in cell
    assert "Not available" in cell


def test_a_closed_plan_shows_the_full_trade_lineage() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.TARGET, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.FILLED, closed=True)
    cell = history_plan_cell_for_row(plan, attempt, "100.00")
    assert cell is not None
    assert "Trigger TARGET" in cell
    assert "Exit order BRK-2" in cell
    assert "Exit fill 5 @ 95.00" in cell
    assert "Zero-verified Yes" in cell
    # gross P&L = (95.00 - 100.00) * 5 = -25.00
    assert "-25.00" in cell


def test_an_ambiguous_exit_shows_zero_verified_no_and_no_fabricated_pnl() -> None:
    plan = _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=_NOW)
    attempt = _attempt(PositionExitState.SUBMISSION_UNKNOWN)
    cell = history_plan_cell_for_row(plan, attempt, "100.00")
    assert cell is not None
    assert "Zero-verified No" in cell
    assert "Not filled" in cell
    assert "Not available" in cell
