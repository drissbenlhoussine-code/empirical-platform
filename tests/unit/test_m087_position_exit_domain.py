"""MILESTONE-087 -- the exit domain: SELL-TO-CLOSE only, full close only, proven P&L only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import PaperOrderRequest
from empirical_platform.decision_candidate.position_exit import (
    ALLOWED_EXIT_TRANSITIONS,
    EXIT_SIDE,
    TERMINAL_EXIT_STATES,
    PositionExitAttempt,
    PositionExitRequest,
    PositionExitState,
    PositionSnapshot,
    derive_exit_client_order_id,
    exit_eligibility,
    exit_order_terms_mismatches,
    exit_request_fingerprint,
    is_exit_transition_allowed,
    realized_result,
)

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
DIGEST = "b" * 64


def a_request(**overrides: object) -> PositionExitRequest:
    fields: dict[str, object] = {
        "symbol": "AAPL",
        "side": EXIT_SIDE,
        "quantity": 8,
        "order_type": OrderType.LIMIT,
        "limit_price": Decimal("227.40"),
        "time_in_force": "DAY",
        "extended_hours": False,
        "client_order_id": "m087-" + "c" * 40,
        "entry_intent_governance_id": "INT-1",
        "account_reference": "ref:abc",
        "environment": "SIMULATION",
    }
    fields.update(overrides)
    return PositionExitRequest(**fields)  # type: ignore[arg-type]


def a_snapshot(**overrides: object) -> PositionSnapshot:
    fields: dict[str, object] = {
        "symbol": "AAPL",
        "entry_intent_governance_id": "INT-1",
        "entry_attempt_id": "ATT-1",
        "entry_state": "FILLED",
        "entry_filled_quantity": Decimal(8),
        "entry_avg_fill_price": Decimal("227.50"),
        "exits_filled_quantity": Decimal(0),
        "broker_position_quantity": 8,
        "competing_entry_attempt_ids": (),
        "captured_at": NOW,
    }
    fields.update(overrides)
    return PositionSnapshot(**fields)  # type: ignore[arg-type]


def an_attempt(**overrides: object) -> PositionExitAttempt:
    fields: dict[str, object] = {
        "attempt_id": "XAT-1",
        "entry_intent_governance_id": "INT-1",
        "authorization_id": "XAU-1",
        "client_order_id": "m087-" + "c" * 40,
        "request_fingerprint": DIGEST,
        "symbol": "AAPL",
        "quantity": 8,
        "state": PositionExitState.ACCEPTED,
        "claimed_at": NOW,
        "submitted_at": NOW,
        "acknowledged_at": NOW,
        "terminal_at": None,
        "broker_order_id": "sim-000002",
        "broker_status": "accepted",
        "filled_quantity": Decimal(0),
        "filled_avg_price": None,
        "failure_code": None,
        "failure_detail": None,
        "closed_position_verified_at": None,
    }
    fields.update(overrides)
    return PositionExitAttempt(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The request type
# ---------------------------------------------------------------------------


def test_m085_paper_order_request_is_still_buy_only_and_untouched() -> None:
    with pytest.raises(ValueError, match="long-only"):
        PaperOrderRequest(
            symbol="AAPL",
            side="SELL",
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("1"),
            time_in_force="DAY",
            extended_hours=False,
            client_order_id="m085-x",
        )
    assert not issubclass(PositionExitRequest, PaperOrderRequest)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"side": "SELL"}, "SELL_TO_CLOSE"),
        ({"side": "BUY"}, "SELL_TO_CLOSE"),
        ({"quantity": 0}, "positive"),
        ({"quantity": -3}, "positive"),
        ({"quantity": Decimal("1.5")}, "int"),
        # MILESTONE-089 widened ALLOWED_EXIT_ENVIRONMENTS to {"SIMULATION", "PAPER"}; LIVE
        # remains the one environment this request can never bind (see
        # test_the_request_still_refuses_live_and_only_live below for the positive case).
        ({"environment": "LIVE"}, "cannot be bound"),
        ({"client_order_id": "m085-" + "c" * 40}, "m087-"),
        ({"time_in_force": "GTC"}, "DAY"),
        ({"extended_hours": True}, "extended_hours"),
        ({"order_type": OrderType.LIMIT, "limit_price": None}, "limit_price"),
        ({"order_type": OrderType.MARKET}, "must not carry"),
    ],
)
def test_the_request_cannot_express_anything_but_a_whole_sell_to_close(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        a_request(**overrides)


def test_the_request_still_refuses_live_and_only_live() -> None:
    """MILESTONE-089: SIMULATION and PAPER both construct; LIVE alone is refused, and no
    other value silently passes (the frozenset itself is the single source of truth)."""
    from empirical_platform.decision_candidate.position_exit import ALLOWED_EXIT_ENVIRONMENTS

    assert ALLOWED_EXIT_ENVIRONMENTS == frozenset({"SIMULATION", "PAPER"})
    a_request(environment="SIMULATION")
    a_request(environment="PAPER")
    with pytest.raises(ValueError, match="cannot be bound"):
        a_request(environment="LIVE")
    with pytest.raises(ValueError, match="cannot be bound"):
        a_request(environment="live")


def test_the_broker_identity_is_derived_and_differs_per_preview() -> None:
    one = derive_exit_client_order_id(
        entry_intent_governance_id="INT-1", account_reference="ref:abc", preview_id="XPV-INT-1-1"
    )
    same = derive_exit_client_order_id(
        entry_intent_governance_id="INT-1", account_reference="ref:abc", preview_id="XPV-INT-1-1"
    )
    other = derive_exit_client_order_id(
        entry_intent_governance_id="INT-1", account_reference="ref:abc", preview_id="XPV-INT-1-2"
    )
    assert one == same and one != other and one.startswith("m087-") and len(one) == 45


def test_the_fingerprint_binds_position_evidence_and_deadline() -> None:
    request = a_request()
    base = exit_request_fingerprint(
        request=request,
        entry_attempt_id="ATT-1",
        position_digest=a_snapshot().digest,
        liquidation_deadline=NOW + timedelta(hours=5),
    )
    later_observation = exit_request_fingerprint(
        request=request,
        entry_attempt_id="ATT-1",
        position_digest=a_snapshot(captured_at=NOW + timedelta(minutes=3)).digest,
        liquidation_deadline=NOW + timedelta(hours=5),
    )
    assert later_observation == base  # the same position seen again is the same position
    moved = exit_request_fingerprint(
        request=request,
        entry_attempt_id="ATT-1",
        position_digest=a_snapshot(broker_position_quantity=9).digest,
        liquidation_deadline=NOW + timedelta(hours=5),
    )
    assert moved != base


# ---------------------------------------------------------------------------
# Eligibility: the conservative rule
# ---------------------------------------------------------------------------


def test_a_clean_filled_entry_with_an_agreeing_broker_is_eligible() -> None:
    snapshot = a_snapshot()
    assert snapshot.attributable_quantity == 8
    assert exit_eligibility(snapshot, existing_exit=None) == ()


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"broker_position_quantity": 0}, "no long position"),
        ({"broker_position_quantity": 9}, "does not equal"),  # larger than the entry evidence
        ({"broker_position_quantity": 7}, "does not equal"),  # smaller than the entry evidence
        ({"entry_state": "PARTIALLY_FILLED"}, "partially filled"),
        ({"entry_state": "SUBMISSION_UNKNOWN"}, "unknown"),
        ({"entry_state": "PAPER_ACCEPTED"}, "only a filled entry"),
        ({"entry_filled_quantity": Decimal(0), "broker_position_quantity": 0}, "filled nothing"),
        ({"entry_filled_quantity": Decimal("7.5")}, "whole number"),
        ({"competing_entry_attempt_ids": ("ATT-9",)}, "ambiguous"),
        ({"exits_filled_quantity": Decimal(8)}, "already sold"),
        ({"entry_attempt_id": None, "entry_state": None}, "no entry execution"),
    ],
)
def test_every_uncertainty_refuses_rather_than_guesses(
    overrides: dict[str, object], reason: str
) -> None:
    refusals = exit_eligibility(a_snapshot(**overrides), existing_exit=None)
    assert refusals and any(reason in r for r in refusals), refusals


def test_a_cancelled_entry_that_filled_shares_is_a_stable_position() -> None:
    snapshot = a_snapshot(
        entry_state="CANCELED", entry_filled_quantity=Decimal(4), broker_position_quantity=4
    )
    assert exit_eligibility(snapshot, existing_exit=None) == ()
    assert snapshot.attributable_quantity == 4


def test_an_exit_in_progress_or_filled_forbids_another_and_a_rejected_one_does_not() -> None:
    snapshot = a_snapshot()
    assert exit_eligibility(snapshot, existing_exit=an_attempt())[0].startswith(
        "an exit is already"
    )
    filled = an_attempt(
        state=PositionExitState.FILLED,
        terminal_at=NOW,
        filled_quantity=Decimal(8),
        filled_avg_price=Decimal("227.40"),
    )
    assert any("not yet verified" in r for r in exit_eligibility(snapshot, existing_exit=filled))
    closed = an_attempt(
        state=PositionExitState.FILLED,
        terminal_at=NOW,
        filled_quantity=Decimal(8),
        filled_avg_price=Decimal("227.40"),
        closed_position_verified_at=NOW,
    )
    assert any("already closed" in r for r in exit_eligibility(snapshot, existing_exit=closed))
    rejected = an_attempt(
        state=PositionExitState.REJECTED, terminal_at=NOW, failure_code="HTTP_403"
    )
    assert exit_eligibility(snapshot, existing_exit=rejected) == ()


# ---------------------------------------------------------------------------
# Attempt invariants, transitions, closed position, P&L
# ---------------------------------------------------------------------------


def test_an_attempt_can_never_record_an_over_sold_quantity_or_a_premature_close() -> None:
    with pytest.raises(ValueError, match="never over-sold"):
        an_attempt(filled_quantity=Decimal(9))
    with pytest.raises(ValueError, match="FILLED attempt for its whole quantity"):
        an_attempt(closed_position_verified_at=NOW)
    with pytest.raises(ValueError, match="FILLED attempt for its whole quantity"):
        an_attempt(
            state=PositionExitState.FILLED,
            terminal_at=NOW,
            filled_quantity=Decimal(7),
            closed_position_verified_at=NOW,
        )


def test_filled_is_not_closed_until_verified() -> None:
    filled = an_attempt(
        state=PositionExitState.FILLED,
        terminal_at=NOW,
        filled_quantity=Decimal(8),
        filled_avg_price=Decimal("227.40"),
    )
    assert filled.fully_filled and not filled.position_closed
    assert realized_result(entry_avg_fill_price=Decimal("227.50"), exit_attempt=filled) is None
    closed = an_attempt(
        state=PositionExitState.FILLED,
        terminal_at=NOW,
        filled_quantity=Decimal(8),
        filled_avg_price=Decimal("227.40"),
        closed_position_verified_at=NOW,
    )
    result = realized_result(entry_avg_fill_price=Decimal("227.50"), exit_attempt=closed)
    assert result is not None and result.realized_pnl == Decimal("-0.80") and result.quantity == 8
    assert realized_result(entry_avg_fill_price=None, exit_attempt=closed) is None  # no estimate


def test_the_transition_table_is_closed_and_unknown_never_returns_to_in_progress() -> None:
    for terminal in TERMINAL_EXIT_STATES:
        assert ALLOWED_EXIT_TRANSITIONS[terminal] == frozenset()
    assert not is_exit_transition_allowed(
        PositionExitState.SUBMISSION_UNKNOWN, PositionExitState.SUBMISSION_IN_PROGRESS
    )
    assert is_exit_transition_allowed(PositionExitState.CANCEL_REQUESTED, PositionExitState.FILLED)
    assert set(ALLOWED_EXIT_TRANSITIONS) == set(PositionExitState)


def test_mismatched_broker_terms_are_named_and_a_buy_under_our_identity_is_a_mismatch() -> None:
    request = a_request()

    class View:
        client_order_id = request.client_order_id
        symbol = "AAPL"
        side = "buy"
        quantity = "8"
        order_type = "limit"
        limit_price = "227.40"
        time_in_force = "day"
        extended_hours = False
        broker_order_id = "sim-1"

    assert exit_order_terms_mismatches(expected=request, actual=View()) == ("side",)
    View.side = "sell"
    View.quantity = "9"
    assert exit_order_terms_mismatches(expected=request, actual=View()) == ("quantity",)
    View.quantity = "8"
    assert exit_order_terms_mismatches(expected=request, actual=View()) == ()
    assert exit_order_terms_mismatches(
        expected=request, actual=View(), bound_broker_order_id="sim-2"
    ) == ("broker_order_id",)
