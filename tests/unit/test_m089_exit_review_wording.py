"""MILESTONE-089 -- capability-aware wording on the exit review/confirm surfaces.

M087's exit console and HTML rendering were written for SIMULATION only and hardcoded that
fact into several operator-facing strings. MILESTONE-089 widened the exit path to PAPER and
fixed each hardcoded string this session found, mirroring the wording
`usecases.operator_console.OperatorConsoleService._broker_noun` already established for entry
orders. These tests pin the fix: SIMULATION text is byte-for-byte unchanged, and PAPER text
never says "simulated" or "simulation" about a real Alpaca broker action.
"""

from __future__ import annotations

from datetime import UTC, datetime

from empirical_platform.usecases.operator_console import HumanState
from empirical_platform.usecases.operator_console_exits import (
    ExitReviewView,
    _account_noun,
    _broker_noun,
    _closed_round_trip_label,
)

_NOW = datetime(2026, 9, 29, 15, 0, tzinfo=UTC)


def test_broker_noun_is_simulated_for_simulation_and_alpaca_for_paper() -> None:
    assert _broker_noun("SIMULATION") == "simulated broker"
    assert _broker_noun("PAPER") == "Alpaca paper endpoint"


def test_account_noun_is_capability_aware() -> None:
    assert _account_noun("SIMULATION") == "Simulation account"
    assert _account_noun("PAPER") == "Alpaca Paper account"


def test_closed_round_trip_label_is_capability_aware() -> None:
    assert _closed_round_trip_label("SIMULATION") == "simulation"
    assert _closed_round_trip_label("PAPER") == "Alpaca Paper"


def _a_review_view(*, environment: str) -> ExitReviewView:
    return ExitReviewView(
        intent_id="INT-089-0001",
        preview_id="XPV-INT-089-0001-1",
        preview_version=1,
        symbol="AAPL",
        current_holding="10",
        exit_quantity="10",
        side="SELL TO CLOSE",
        order_type="LIMIT",
        limit_price="200.00",
        account=f"{_account_noun(environment)} (deadbeefdeadbeef…)",
        environment=environment,
        entry_avg_fill_price="195.00",
        current_bid="199.90",
        current_ask="200.10",
        quote_captured_at=_NOW,
        position_captured_at=_NOW,
        client_order_id="m087-" + "a" * 40,
        fingerprint_short="0123456789ab",
        liquidation_deadline=_NOW,
        deadline_tone="info",
        deadline_note="Mandatory liquidation deadline 2026-09-29 20:00 UTC.",
        authorization_expires_at=_NOW,
        ticket="TICKET",
        kill_switch_engaged=False,
        full_close_warning=(
            "Confirming will close the WHOLE attributable position in AAPL (10 shares) -- a "
            "full close, not a partial reduction."
        ),
    )


def test_exit_review_page_shows_the_broker_position_evidence_timestamp_and_client_order_id() -> (
    None
):
    from empirical_platform.entrypoints._operator_console_html import exit_review_page

    view = _a_review_view(environment="PAPER")
    page = exit_review_page(view, "csrf-token", "Paper")
    assert "Broker position evidence captured" in page
    assert view.client_order_id in page
    assert "Client order id" in page
    assert view.full_close_warning in page
    # MILESTONE-089 REGRESSION GUARD: the badge used to be hardcoded "Simulation" regardless
    # of the capability actually composed; it must reflect what the caller passed.
    assert '<span class="env-badge">PAPER</span>' in page
    assert "Simulation" not in page.split("<footer")[0]


def test_exit_review_page_simulation_text_is_unchanged() -> None:
    from empirical_platform.entrypoints._operator_console_html import exit_review_page

    view = _a_review_view(environment="SIMULATION")
    page = exit_review_page(view, "csrf-token", "Simulation")
    assert '<span class="env-badge">SIMULATION</span>' in page


def test_exit_cancel_confirmation_page_names_the_alpaca_endpoint_for_paper() -> None:
    from empirical_platform.decision_candidate.position_exit import PositionExitState
    from empirical_platform.entrypoints._operator_console_html import exit_cancel_confirmation_page
    from empirical_platform.usecases.operator_console import ExecutionSummary, TermsView
    from empirical_platform.usecases.operator_console_exits import ExitSummary

    exit_summary = ExitSummary(
        attempt_id="XAT-INT-089-0001-1",
        state=HumanState.SUBMITTED,
        raw_state=PositionExitState.SUBMITTED.value,
        quantity="10",
        filled_quantity="0",
        filled_avg_price="n/a",
        limit_price="200.00",
        broker_order_id="BRK-1",
        claimed_at=_NOW,
        submitted_at=_NOW,
        terminal_at=None,
        position_closed=False,
        closed_verified_at=None,
        outcome_known=True,
        can_cancel=True,
        pending_reason=None,
        warnings=(),
        timeline=(),
        realized=None,
        result_text="n/a",
    )
    summary = ExecutionSummary(
        intent_id="INT-089-0001",
        proposal_id="PRP-089-0001",
        symbol="AAPL",
        state=HumanState.FILLED,
        raw_state="FILLED",
        terms=TermsView(
            symbol="AAPL",
            side="BUY",
            quantity=10,
            order_type="LIMIT",
            limit_price="195.00",
            time_in_force="DAY",
            extended_hours="No",
            currency="USD",
            notional="1,950.00",
            fingerprint_short="0123456789ab",
        ),
        decision_by="owner",
        decided_at=_NOW,
        broker_order_id="BRK-0",
        claimed_at=_NOW,
        submitted_at=_NOW,
        acknowledged_at=_NOW,
        terminal_at=_NOW,
        filled_quantity="10",
        filled_avg_price="195.00",
        pending_reason=None,
        reconciliation="",
        warnings=(),
        timeline=(),
        is_terminal=True,
        outcome_known=True,
        can_cancel=False,
        execution_kind="entry",
        position_open=True,
        exit_status="in_progress",
        category="Exit in progress",
        exit=exit_summary,
        deadline_tone="info",
        deadline_note="",
    )
    page = exit_cancel_confirmation_page(summary, "csrf-token", "Paper", False)
    assert "Alpaca paper endpoint" in page
    assert "simulated broker" not in page


def test_history_legend_is_capability_aware() -> None:
    from empirical_platform.entrypoints._operator_console_html import history_page

    simulation_page = history_page(
        (), filters={}, capability_label="Simulation", kill_switch_engaged=False
    )
    assert "simulation execution. Broker/Paper execution — future only." in simulation_page

    paper_page = history_page((), filters={}, capability_label="Paper", kill_switch_engaged=False)
    assert "Alpaca Paper execution" in paper_page
    assert "future only" not in paper_page
    assert "simulation execution" not in paper_page
