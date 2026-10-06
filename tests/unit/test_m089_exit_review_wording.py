"""MILESTONE-089 -- capability-aware wording on the exit review/confirm surfaces.

M087's exit console and HTML rendering were written for SIMULATION only and hardcoded that
fact into several operator-facing strings. MILESTONE-089 widened the exit path to PAPER and
fixed each hardcoded string this session found, mirroring the wording
`usecases.operator_console.OperatorConsoleService._broker_noun` already established for entry
orders. These tests pin the fix: SIMULATION text is byte-for-byte unchanged, and PAPER text
never says "simulated" or "simulation" about a real Alpaca broker action.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from empirical_platform.usecases.operator_console import HumanState
from empirical_platform.usecases.operator_console_exits import (
    DEADLINE_MISSED_TRUTH,
    ExitReviewView,
    _account_noun,
    _broker_noun,
    _closed_round_trip_label,
    deadline_status,
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
    # RELEASE v1: PAPER also carries its own distinct badge class (`env-badge-paper`), so the
    # always-running SIMULATION console and the real-Alpaca PAPER one are never color-twins.
    assert '<span class="env-badge env-badge-paper">PAPER</span>' in page
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


# ---------------------------------------------------------------------------
# deadline_status: the deadline banner must name the SAME instant as the terms
# table, in UTC, regardless of operator_timezone -- and the urgency/danger
# comparisons must not change with the fix.
# ---------------------------------------------------------------------------


def test_a_non_utc_deadline_is_converted_to_utc_before_display() -> None:
    deadline = datetime(2026, 6, 10, 15, 45, tzinfo=ZoneInfo("Europe/Helsinki"))
    expected_utc = deadline.astimezone(UTC)
    now = expected_utc - timedelta(hours=1)  # well outside the urgency window
    tone, message = deadline_status(
        deadline=deadline, now=now, position_open=True, position_closed=False
    )
    assert tone == "info"
    assert expected_utc.strftime("%Y-%m-%d %H:%M UTC") in message
    # The un-converted local wall-clock reading must NOT appear (the mislabeling this fixes).
    assert deadline.strftime("%H:%M") not in message or deadline.strftime(
        "%H:%M"
    ) == expected_utc.strftime("%H:%M")


def test_an_already_utc_deadline_is_unchanged() -> None:
    deadline = datetime(2026, 6, 10, 12, 45, tzinfo=UTC)
    now = deadline - timedelta(hours=2)
    tone, message = deadline_status(
        deadline=deadline, now=now, position_open=True, position_closed=False
    )
    assert tone == "info"
    assert "2026-06-10 12:45 UTC" in message


def test_the_banner_and_the_terms_table_name_the_same_instant() -> None:
    from empirical_platform.entrypoints._operator_console_html import _when

    deadline = datetime(2026, 6, 10, 15, 45, tzinfo=ZoneInfo("Europe/Helsinki"))
    now = deadline.astimezone(UTC) - timedelta(hours=1)
    _tone, message = deadline_status(
        deadline=deadline, now=now, position_open=True, position_closed=False
    )
    terms_table_text = _when(deadline)
    # Same date and hour:minute in both (the terms table additionally carries seconds).
    shared = deadline.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
    assert shared in message
    assert shared in terms_table_text


def test_urgency_and_danger_thresholds_are_unaffected_by_timezone_representation() -> None:
    """The SAME instant, expressed in UTC vs. a non-UTC zone, must yield the identical tone."""
    deadline_utc = datetime(2026, 6, 10, 12, 45, tzinfo=UTC)
    deadline_helsinki = deadline_utc.astimezone(ZoneInfo("Europe/Helsinki"))
    assert deadline_utc == deadline_helsinki  # same instant, different tzinfo

    # Outside the 30-minute urgency window: info.
    far_now = deadline_utc - timedelta(hours=1)
    assert (
        deadline_status(
            deadline=deadline_utc, now=far_now, position_open=True, position_closed=False
        )[0]
        == deadline_status(
            deadline=deadline_helsinki, now=far_now, position_open=True, position_closed=False
        )[0]
        == "info"
    )

    # Inside the 30-minute urgency window: warn.
    near_now = deadline_utc - timedelta(minutes=10)
    tone_utc, message_utc = deadline_status(
        deadline=deadline_utc, now=near_now, position_open=True, position_closed=False
    )
    tone_helsinki, message_helsinki = deadline_status(
        deadline=deadline_helsinki, now=near_now, position_open=True, position_closed=False
    )
    assert tone_utc == tone_helsinki == "warn"
    assert "10 minute" in message_utc and "10 minute" in message_helsinki

    # At or past the deadline: danger, with the missed-deadline truth.
    late_now = deadline_utc + timedelta(minutes=1)
    tone_utc, message_utc = deadline_status(
        deadline=deadline_utc, now=late_now, position_open=True, position_closed=False
    )
    tone_helsinki, message_helsinki = deadline_status(
        deadline=deadline_helsinki, now=late_now, position_open=True, position_closed=False
    )
    assert tone_utc == tone_helsinki == "danger"
    assert DEADLINE_MISSED_TRUTH in message_utc and DEADLINE_MISSED_TRUTH in message_helsinki


def test_deadline_status_position_closed_and_not_open_branches_use_utc_too() -> None:
    deadline = datetime(2026, 6, 10, 15, 45, tzinfo=ZoneInfo("Europe/Helsinki"))
    expected = deadline.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")

    tone, message = deadline_status(
        deadline=deadline, now=deadline, position_open=True, position_closed=True
    )
    assert tone == "info" and expected in message

    tone, message = deadline_status(
        deadline=deadline, now=deadline, position_open=False, position_closed=False
    )
    assert tone == "info" and expected in message
