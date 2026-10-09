"""RELEASE v1 -- pure domain tests for `ApprovedPlan` and `evaluate_exit_trigger`.

No I/O, no fakes: every case here is a direct claim against the frozen dataclass's own
construction rules and the pure trigger-evaluation function. This is the layer the
automatic position-plan manager (tested separately, with the real exit pipeline fakes)
depends on for its decisions, so it is proven exhaustively on its own first.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.approved_plan import (
    MANDATORY_EXIT_SAFETY_BUFFER_SECONDS,
    ApprovedPlan,
    ExitTriggerKind,
    derive_system_identity,
    evaluate_exit_trigger,
)

_NOW = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def _plan(**overrides: object) -> ApprovedPlan:
    owner_approval_id = overrides.pop("owner_approval_id", "OWN-1")
    plan_id = overrides.pop("plan_id", "PLAN-1")
    fields: dict[str, object] = {
        "plan_id": plan_id,
        "candidate_id": "CAND-1",
        "entry_intent_governance_id": "INT-1",
        "symbol": "AAPL",
        "approved_quantity": Decimal("3"),
        "stop_price": Decimal("95"),
        "target_price": Decimal("110"),
        "mandatory_liquidation_at": _NOW + timedelta(hours=2),
        "owner_approval_id": owner_approval_id,
        "system_identity": derive_system_identity(
            plan_id=str(plan_id), owner_approval_id=str(owner_approval_id)
        ),
        "created_at": _NOW,
    }
    fields.update(overrides)
    return ApprovedPlan(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construction invariants
# ---------------------------------------------------------------------------


def test_a_plan_with_stop_at_or_above_target_is_refused() -> None:
    with pytest.raises(ValueError, match="stop_price must be strictly below target_price"):
        _plan(stop_price=Decimal("110"), target_price=Decimal("110"))
    with pytest.raises(ValueError, match="stop_price must be strictly below target_price"):
        _plan(stop_price=Decimal("111"), target_price=Decimal("110"))


def test_a_plan_with_nonpositive_quantity_or_prices_is_refused() -> None:
    with pytest.raises(ValueError, match="approved_quantity must be positive"):
        _plan(approved_quantity=Decimal("0"))
    with pytest.raises(ValueError, match="stop_price and target_price must be positive"):
        _plan(stop_price=Decimal("0"))


def test_a_plan_cannot_carry_a_freeform_or_mismatched_system_identity() -> None:
    with pytest.raises(ValueError, match="system_identity must be exactly"):
        _plan(system_identity="system:whatever-i-want")


def test_a_plan_cannot_claim_kind_without_claim_time_or_vice_versa() -> None:
    with pytest.raises(ValueError, match="must be set, or unset, together"):
        _plan(triggered_exit_kind=ExitTriggerKind.STOP, triggered_exit_at=None)
    with pytest.raises(ValueError, match="must be set, or unset, together"):
        _plan(triggered_exit_kind=None, triggered_exit_at=_NOW)


def test_system_identity_is_deterministic_and_traces_to_the_one_approval() -> None:
    a = derive_system_identity(plan_id="PLAN-7", owner_approval_id="OWN-9")
    b = derive_system_identity(plan_id="PLAN-7", owner_approval_id="OWN-9")
    assert a == b
    assert a == "system:approved-plan:PLAN-7:owner-approval:OWN-9"
    assert derive_system_identity(plan_id="PLAN-8", owner_approval_id="OWN-9") != a
    assert derive_system_identity(plan_id="PLAN-7", owner_approval_id="OWN-10") != a


# ---------------------------------------------------------------------------
# Trigger evaluation
# ---------------------------------------------------------------------------


def test_no_trigger_fires_inside_the_band_well_before_the_deadline() -> None:
    plan = _plan()
    assert evaluate_exit_trigger(plan, last_price=Decimal("100"), now=_NOW) is None


def test_stop_fires_at_or_below_the_stop_price() -> None:
    plan = _plan(stop_price=Decimal("95"))
    assert evaluate_exit_trigger(plan, last_price=Decimal("95"), now=_NOW) is ExitTriggerKind.STOP
    assert evaluate_exit_trigger(plan, last_price=Decimal("94.99"), now=_NOW) is (
        ExitTriggerKind.STOP
    )
    assert evaluate_exit_trigger(plan, last_price=Decimal("95.01"), now=_NOW) is None


def test_target_fires_at_or_above_the_target_price() -> None:
    plan = _plan(target_price=Decimal("110"))
    assert evaluate_exit_trigger(plan, last_price=Decimal("110"), now=_NOW) is (
        ExitTriggerKind.TARGET
    )
    assert evaluate_exit_trigger(plan, last_price=Decimal("110.01"), now=_NOW) is (
        ExitTriggerKind.TARGET
    )
    assert evaluate_exit_trigger(plan, last_price=Decimal("109.99"), now=_NOW) is None


def test_mandatory_exit_fires_at_the_safety_buffer_before_liquidation() -> None:
    deadline = _NOW + timedelta(hours=1)
    plan = _plan(mandatory_liquidation_at=deadline)
    just_before_buffer = deadline - timedelta(seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS + 1)
    at_buffer = deadline - timedelta(seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS)
    assert evaluate_exit_trigger(plan, last_price=Decimal("100"), now=just_before_buffer) is None
    assert evaluate_exit_trigger(plan, last_price=Decimal("100"), now=at_buffer) is (
        ExitTriggerKind.MANDATORY_EXIT
    )


def test_stop_takes_priority_over_a_simultaneous_mandatory_exit_deadline() -> None:
    deadline = _NOW
    plan = _plan(stop_price=Decimal("95"), mandatory_liquidation_at=deadline)
    at_buffer = deadline - timedelta(seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS)
    assert evaluate_exit_trigger(plan, last_price=Decimal("90"), now=at_buffer) is (
        ExitTriggerKind.STOP
    )


def test_target_takes_priority_over_a_simultaneous_mandatory_exit_deadline() -> None:
    deadline = _NOW
    plan = _plan(target_price=Decimal("110"), mandatory_liquidation_at=deadline)
    at_buffer = deadline - timedelta(seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS)
    assert evaluate_exit_trigger(plan, last_price=Decimal("120"), now=at_buffer) is (
        ExitTriggerKind.TARGET
    )


def test_an_already_claimed_plan_never_fires_again() -> None:
    plan = _plan(
        stop_price=Decimal("95"),
        triggered_exit_kind=ExitTriggerKind.STOP,
        triggered_exit_at=_NOW,
    )
    # Price far below stop, well past the mandatory deadline -- still no second trigger.
    far_future = plan.mandatory_liquidation_at + timedelta(days=1)
    assert evaluate_exit_trigger(plan, last_price=Decimal("1"), now=far_future) is None
