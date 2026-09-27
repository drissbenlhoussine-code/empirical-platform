"""MILESTONE-086 -- the Operator Console services, end to end, in memory.

The REAL M084 paper-bound handlers propose, decide and issue; the REAL M085 handlers
preview, authorize, dispatch, reconcile and cancel; the REAL simulation broker answers.
Only persistence is in memory. Every scenario the mission names is exercised here, and the
PostgreSQL suite repeats the restart-sensitive ones against the database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus
from empirical_platform.shared.brokerage.simulation_paper import SimulationScenario
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.operator_console import (
    CapabilityRefusedError,
    ConsoleRefusalError,
    HumanState,
    refuse_requested_environment,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path)


def _approve(world: World, symbol: str) -> tuple[str, object]:
    proposal_id = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal_id)
    return proposal_id, world.service.confirm_approval(proposal_id, view.ticket)


def _card(world: World, symbol: str) -> object:
    return world.service.opportunity(world.proposal_id(symbol))


# ---------------------------------------------------------------------------
# The simulation day and Today
# ---------------------------------------------------------------------------


def test_loading_the_day_creates_real_proposals_through_the_m084_handler(world: World) -> None:
    report = world.load_day()
    assert report.refused == ()
    assert len(report.proposed) == 12
    again = world.load_day()
    assert again.proposed == () and len(again.already_present) == 12  # idempotent
    today = world.service.today()
    assert today.capability.capability.value == "SIMULATION"
    assert today.needs_action_count == 12
    assert all(c.state is HumanState.NEEDS_DECISION for c in today.opportunities)
    aapl = _card(world, "AAPL")
    assert aapl.terms.side == "BUY" and aapl.terms.time_in_force == "DAY"  # type: ignore[attr-defined]
    assert aapl.terms.extended_hours == "No"  # type: ignore[attr-defined]
    assert aapl.stop_price != "Not available" and aapl.target_price != "Not available"  # type: ignore[attr-defined]
    assert aapl.scenario == "ACCEPTED_THEN_FILLED"  # type: ignore[attr-defined]
    assert "Open" in today.market_status and today.system_status == "Operating"


def test_missing_data_reads_not_available_rather_than_a_number(world: World) -> None:
    world.load_day(("AAPL",))
    # Quantities derive from the engine; the console invents nothing when a field is absent.
    summary = world.service.today().opportunities[0].execution
    assert summary is None
    entries = world.service.history()
    assert entries[0].result == "Not available"


# ---------------------------------------------------------------------------
# Approve: the happy path and every staged scenario
# ---------------------------------------------------------------------------


def test_confirm_approval_runs_the_whole_chain_and_the_order_fills(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id, outcome = _approve(world, "AAPL")
    assert outcome.ok and outcome.sent == "sent"  # type: ignore[attr-defined]
    proposal = world.repositories.proposals.get(proposal_id)
    assert proposal is not None and proposal.status is ProposalStatus.APPROVED
    assert world.repositories.decisions.for_proposal(proposal_id) is not None
    intent = world.repositories.intents.for_proposal(proposal_id)
    assert intent is not None and intent.intent_governance_id == f"INT-{proposal_id}"
    attempt = world.repositories.attempts.for_intent(intent.intent_governance_id)
    assert attempt is not None and attempt.state is PaperExecutionState.PAPER_ACCEPTED
    assert len(world.broker.store.orders()) == 1
    card = _card(world, "AAPL")
    assert card.state is HumanState.ACCEPTED  # type: ignore[attr-defined]
    # Reconciliation, as the background pass does it: accepted, then filled.
    world.clock.advance(5)
    assert world.service.refresh_executions() == (intent.intent_governance_id,)
    assert _card(world, "AAPL").state is HumanState.ACCEPTED  # type: ignore[attr-defined]
    world.clock.advance(5)
    world.service.refresh_executions()
    filled = world.service.execution(intent.intent_governance_id)
    assert filled.state is HumanState.FILLED and filled.is_terminal
    assert filled.filled_quantity == str(intent.quantity)
    assert filled.filled_avg_price != "Not available"
    assert [s.label for s in filled.timeline] == [
        "Proposal",
        "Owner approved",
        "Intent issued",
        "Authorized",
        "Submitted",
        "Accepted",
        "Filled",
    ]
    assert all(s.reached for s in filled.timeline)
    # A FILLED BUY entry is an OPEN POSITION: it stays in Active trades with its exit locked
    # (M086-REV-EXIT-01); the M085 state is still FILLED and nothing can be cancelled or sent.
    (open_position,) = world.service.active_trades()
    assert open_position.intent_id == intent.intent_governance_id
    assert open_position.position_open and open_position.is_terminal
    assert open_position.state is HumanState.FILLED and not open_position.can_cancel
    assert "exit locked pending M087" in open_position.exit_status
    assert open_position.raw_state == "FILLED"
    history = world.service.history()
    assert history[0].final_state is HumanState.FILLED
    assert history[0].execution_kind == "Simulation execution"
    assert history[0].decision == "Approved"
    assert world.service.today().active_positions_count == 1


@pytest.mark.parametrize(
    ("symbol", "scenario", "state", "sent"),
    [
        ("MSFT", SimulationScenario.PARTIAL_FILL, HumanState.PARTIALLY_FILLED, "sent"),
        ("NVDA", SimulationScenario.ACCEPTED_NOT_FILLED, HumanState.ACCEPTED, "sent"),
        ("AMZN", SimulationScenario.BROKER_REJECTION, HumanState.REJECTED, "sent"),
        ("GOOGL", SimulationScenario.AMBIGUOUS_SUBMISSION, HumanState.NEEDS_ATTENTION, "unknown"),
        (
            "META",
            SimulationScenario.NETWORK_FAILURE_BEFORE_SEND,
            HumanState.BLOCKED,
            "nothing_sent",
        ),
        (
            "JPM",
            SimulationScenario.NETWORK_FAILURE_AFTER_POSSIBLE_SEND,
            HumanState.NEEDS_ATTENTION,
            "unknown",
        ),
    ],
)
def test_each_staged_broker_behaviour_shows_the_honest_state(
    world: World, symbol: str, scenario: SimulationScenario, state: HumanState, sent: str
) -> None:
    world.load_day((symbol,))
    assert world.store.scenario_for(symbol) is scenario
    _, outcome = _approve(world, symbol)
    assert outcome.sent == sent  # type: ignore[attr-defined]
    world.clock.advance(5)
    world.service.refresh_executions()
    world.clock.advance(5)
    world.service.refresh_executions()
    card = _card(world, symbol)
    if state is HumanState.NEEDS_ATTENTION:
        # Delivered-but-ambiguous: reconciliation FINDS the order and it proceeds honestly.
        assert card.state in {HumanState.ACCEPTED, HumanState.FILLED}  # type: ignore[attr-defined]
        assert "Outcome unknown" in outcome.title  # type: ignore[attr-defined]
    else:
        assert card.state is state  # type: ignore[attr-defined]
    if state is HumanState.BLOCKED:
        assert "Nothing was sent" in outcome.title  # type: ignore[attr-defined]
        assert world.broker.store.orders() == ()
    if state is HumanState.REJECTED:
        assert world.broker.store.orders() == ()
    if state is HumanState.PARTIALLY_FILLED:
        assert world.service.execution(f"INT-{world.proposal_id(symbol)}").pending_reason


def test_an_ambiguous_submission_is_reported_unknown_and_never_resent(world: World) -> None:
    world.load_day(("GOOGL",))
    proposal_id, outcome = _approve(world, "GOOGL")
    assert outcome.sent == "unknown" and "do not retry" in outcome.title  # type: ignore[attr-defined]
    attempt = world.repositories.attempts.for_intent(f"INT-{proposal_id}")
    assert attempt is not None and attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    card = _card(world, "GOOGL")
    assert card.state is HumanState.NEEDS_ATTENTION  # type: ignore[attr-defined]
    assert "do not retry" in (card.attention_note or "")  # type: ignore[attr-defined]
    # A second confirmation of the same page finds the attempt and sends nothing new.
    view_token = world.service.prepare_approval  # noqa: F841 - prepare is refused: already decided
    with pytest.raises(ConsoleRefusalError):
        world.service.prepare_approval(proposal_id)
    assert len(world.broker.store.orders()) == 1
    # Reconciliation finds the delivered order; UNKNOWN resolves to what the broker says.
    world.clock.advance(5)
    world.service.refresh_executions()
    assert _card(world, "GOOGL").state is HumanState.ACCEPTED  # type: ignore[attr-defined]
    assert len(world.broker.store.orders()) == 1


def test_a_lost_request_resolves_rejected_only_through_the_bounded_absence_policy(
    world: World,
) -> None:
    world.load_day(("XOM",))
    proposal_id, outcome = _approve(world, "XOM")
    assert outcome.sent == "unknown"  # type: ignore[attr-defined]
    world.clock.advance(61)
    world.service.refresh_executions()
    assert _card(world, "XOM").state is HumanState.NEEDS_ATTENTION  # type: ignore[attr-defined]
    world.clock.advance(61)
    world.service.refresh_executions()
    card = _card(world, "XOM")
    assert card.state is HumanState.REJECTED  # type: ignore[attr-defined]
    attempt = world.repositories.attempts.for_intent(f"INT-{proposal_id}")
    assert attempt is not None and attempt.failure_code == "NOT_FOUND_AT_BROKER"
    assert world.broker.store.orders() == ()


def test_cancel_success_and_the_cancel_fill_race_are_both_honest(world: World) -> None:
    world.load_day(("V", "JNJ"))
    for symbol in ("V", "JNJ"):
        _approve(world, symbol)
    v = world.service.cancel_execution(f"INT-{world.proposal_id('V')}")
    j = world.service.cancel_execution(f"INT-{world.proposal_id('JNJ')}")
    assert v.state is HumanState.CANCEL_REQUESTED and j.state is HumanState.CANCEL_REQUESTED
    world.clock.advance(5)
    world.service.refresh_executions()
    assert _card(world, "V").state is HumanState.CANCELLED  # type: ignore[attr-defined]
    assert _card(world, "JNJ").state is HumanState.FILLED  # type: ignore[attr-defined]
    with pytest.raises(ConsoleRefusalError):
        world.service.cancel_execution(f"INT-{world.proposal_id('V')}")


# ---------------------------------------------------------------------------
# Decision safety
# ---------------------------------------------------------------------------


def test_rejection_needs_one_confirmation_and_sends_nothing(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_rejection(proposal_id)
    outcome = world.service.confirm_rejection(proposal_id, view.ticket)
    assert outcome.state is HumanState.REJECTED and outcome.sent == "nothing_sent"
    assert world.repositories.intents.for_proposal(proposal_id) is None
    assert world.broker.store.orders() == ()
    again = world.service.confirm_rejection(proposal_id, view.ticket)
    assert again.title == "Already rejected"
    with pytest.raises(ConsoleRefusalError):
        world.service.prepare_approval(proposal_id)


def test_a_duplicated_confirmation_creates_no_second_action(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)
    first = world.service.confirm_approval(proposal_id, view.ticket)
    second = world.service.confirm_approval(proposal_id, view.ticket)  # browser retried
    assert first.ok and second.title == "Already confirmed"
    assert len(world.broker.store.orders()) == 1
    assert len(world.repositories.attempts.rows) == 1  # type: ignore[attr-defined]
    assert len(world.repositories.authorizations.rows) == 1  # type: ignore[attr-defined]
    assert len(world.repositories.intents.rows) == 1  # type: ignore[attr-defined]


def test_two_tabs_cannot_approve_twice(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    tab_a = world.service.prepare_approval(proposal_id)
    tab_b = world.service.prepare_approval(proposal_id)
    world.service.confirm_approval(proposal_id, tab_a.ticket)
    outcome = world.service.confirm_approval(proposal_id, tab_b.ticket)
    assert outcome.title == "Already confirmed"
    assert len(world.broker.store.orders()) == 1


def test_a_proposal_that_expires_while_the_page_is_open_is_refused(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)
    world.clock.advance(3601)  # past the configured proposal expiry
    with pytest.raises(ConsoleRefusalError) as refused:
        world.service.confirm_approval(proposal_id, view.ticket)
    assert "Nothing was" in refused.value.message
    assert world.repositories.decisions.for_proposal(proposal_id) is None
    assert world.broker.store.orders() == ()


def test_a_stale_tab_with_an_older_proposal_version_is_refused(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)
    current = world.repositories.proposals.get(proposal_id)
    assert current is not None
    import copy
    from dataclasses import replace

    from empirical_platform.decision_candidate.trade_proposal import compute_fingerprint

    # A genuine new version of the same proposal: the version is part of the fingerprint.
    draft = copy.copy(current)
    object.__setattr__(draft, "proposal_version", current.proposal_version + 1)
    world.repositories.proposals.replace_row(  # type: ignore[attr-defined]
        replace(
            current,
            proposal_version=current.proposal_version + 1,
            content_fingerprint=compute_fingerprint(draft),
        )
    )
    with pytest.raises(ConsoleRefusalError) as refused:
        world.service.confirm_approval(proposal_id, view.ticket)
    assert refused.value.title == "Terms changed"
    assert world.repositories.decisions.for_proposal(proposal_id) is None


def test_a_forged_or_foreign_ticket_is_refused(world: World) -> None:
    world.load_day(("AAPL", "MSFT"))
    aapl = world.proposal_id("AAPL")
    msft = world.proposal_id("MSFT")
    view = world.service.prepare_approval(aapl)
    with pytest.raises(ConsoleRefusalError):
        world.service.confirm_approval(msft, view.ticket)  # ticket for another proposal
    tampered = view.ticket[:-4] + "0000"
    with pytest.raises(ConsoleRefusalError):
        world.service.confirm_approval(aapl, tampered)
    reject_view = world.service.prepare_rejection(aapl)
    with pytest.raises(ConsoleRefusalError):
        world.service.confirm_approval(aapl, reject_view.ticket)  # a REJECT ticket cannot approve
    world.clock.advance(16 * 60)
    with pytest.raises(ConsoleRefusalError) as old:
        world.service.confirm_approval(aapl, view.ticket)
    assert old.value.title == "Confirmation expired"
    assert world.repositories.decisions.for_proposal(aapl) is None


def test_a_ticket_from_a_previous_process_is_refused_after_restart(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)
    restarted = world.restart()
    with pytest.raises(ConsoleRefusalError):
        restarted.service.confirm_approval(proposal_id, view.ticket)
    fresh = restarted.service.prepare_approval(proposal_id)
    assert restarted.service.confirm_approval(proposal_id, fresh.ticket).ok


def test_the_kill_switch_engaged_just_before_confirmation_blocks_it(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)
    world.service.set_kill_switch(engaged=True, reason="test")
    with pytest.raises(ConsoleRefusalError) as refused:
        world.service.confirm_approval(proposal_id, view.ticket)
    assert (
        "kill switch" in refused.value.message.lower()
        and "Nothing was sent" in refused.value.message
    )
    assert world.repositories.decisions.for_proposal(proposal_id) is None
    card = _card(world, "AAPL")
    assert card.state is HumanState.NEEDS_DECISION and card.blocked_note  # type: ignore[attr-defined]
    assert world.service.today().system_status == "Execution stopped by the kill switch"
    world.service.set_kill_switch(engaged=False, reason="")
    assert world.service.confirm_approval(
        proposal_id, world.service.prepare_approval(proposal_id).ticket
    ).ok


def test_the_engine_not_the_console_owns_the_authorization_terms(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id, _ = _approve(world, "AAPL")
    authorization = world.repositories.authorizations.latest_for_intent(f"INT-{proposal_id}")
    proposal = world.repositories.proposals.get(proposal_id)
    assert authorization is not None and proposal is not None
    assert authorization.symbol == proposal.symbol
    assert authorization.quantity == proposal.quantity
    assert authorization.limit_price == proposal.limit_price
    attempt = world.repositories.attempts.for_intent(f"INT-{proposal_id}")
    assert attempt is not None and attempt.authorization_id == authorization.authorization_id
    preview = world.repositories.previews.get(authorization.preview_id)
    assert preview is not None and preview.request_fingerprint == authorization.request_fingerprint


# ---------------------------------------------------------------------------
# Capability firewall and restart
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"environment": "PAPER"},
        {"environment": "LIVE"},
        {"mode": "paper"},
        {"environment": "SIMULATION"},
    ],
)
def test_a_browser_cannot_choose_an_environment(payload: dict[str, str]) -> None:
    with pytest.raises(CapabilityRefusedError):
        refuse_requested_environment(payload)
    refuse_requested_environment({"proposal": "x"})  # ordinary fields pass


def test_the_service_cannot_be_composed_for_paper_or_live(world: World) -> None:
    from empirical_platform.usecases.operator_console import CAPABILITIES, OperatorConsoleService

    for capability in CAPABILITIES[1:]:
        with pytest.raises(CapabilityRefusedError):
            OperatorConsoleService(
                repositories=world.repositories,
                broker=world.broker,
                market_data=world.market_data,
                signer=world.signer,
                capability=capability,
            )


def test_restart_reconstructs_state_from_durable_records_and_creates_nothing(world: World) -> None:
    world.load_day(("KO", "MSFT", "NVDA"))
    _approve(world, "KO")  # RESTART_WHILE_UNKNOWN: delivered, answer lost
    _approve(world, "MSFT")  # will be partially filled
    assert _card(world, "KO").state is HumanState.NEEDS_ATTENTION  # type: ignore[attr-defined]
    orders_before = len(world.broker.store.orders())
    restarted = world.restart()
    ko = restarted.service.opportunity(world.proposal_id("KO"))
    assert ko.state is HumanState.NEEDS_ATTENTION  # reconstructed, not remembered
    assert restarted.service.today().needs_action_count == 1  # NVDA still awaits a decision
    assert len(restarted.service.active_trades()) == 2
    restarted.clock.advance(5)
    restarted.service.refresh_executions()
    assert restarted.service.opportunity(world.proposal_id("KO")).state is HumanState.ACCEPTED
    restarted.clock.advance(5)
    restarted.service.refresh_executions()
    assert restarted.service.opportunity(world.proposal_id("KO")).state is HumanState.FILLED
    assert (
        restarted.service.opportunity(world.proposal_id("MSFT")).state
        is HumanState.PARTIALLY_FILLED
    )
    assert len(restarted.broker.store.orders()) == orders_before  # a refresh sends nothing


def test_history_filters_and_kinds(world: World) -> None:
    world.load_day(("AAPL", "MSFT", "NVDA"))
    _approve(world, "AAPL")
    view = world.service.prepare_rejection(world.proposal_id("MSFT"))
    world.service.confirm_rejection(world.proposal_id("MSFT"), view.ticket)
    rows = world.service.history()
    assert {r.symbol for r in rows} == {"AAPL", "MSFT", "NVDA"}
    kinds = {r.symbol: r.execution_kind for r in rows}
    assert kinds == {
        "AAPL": "Simulation execution",
        "MSFT": "Owner decision",
        "NVDA": "Model proposal",
    }
    assert [r.symbol for r in world.service.history(decision="Rejected")] == ["MSFT"]
    assert [r.symbol for r in world.service.history(symbol="aapl")] == ["AAPL"]
    assert world.service.history(date="1999-01-01") == ()
    assert all(r.result == "Not available" for r in rows)


def test_safety_rules_come_from_the_configuration(world: World) -> None:
    world.load_day(("AAPL",))
    from empirical_platform.usecases.operator_console_fixtures import SIMULATION_CONFIGURATION_ID

    view = world.service.safety(SIMULATION_CONFIGURATION_ID)
    labels = {r.label: r.value for r in view.rules}
    assert labels["Direction"].startswith("Long only")
    assert labels["Short selling"] == "Not permitted"
    assert labels["Overnight positions"] == "Not permitted"
    assert labels["Leverage"] == "Maximum 1x"
    assert "AAPL" in labels["Watchlist"]
    assert labels["Quote freshness"] == "60 seconds"
    assert labels["Spread limit"] == "1%"
    assert "Etc/GMT+4" in labels["Trading window"]  # 14:00 UTC reads 10:00 there
    assert [c.enabled for c in view.capabilities] == [True, False, False]
    assert "Locked pending M085 Paper Acceptance" in view.capabilities[1].label
    assert "Not authorized" in view.capabilities[2].label


def test_unknown_identifiers_are_refused_not_invented(world: World) -> None:
    with pytest.raises(NotFoundError):
        world.service.opportunity("PRP-NOPE")
    with pytest.raises(NotFoundError):
        world.service.execution("INT-NOPE")
    with pytest.raises(NotFoundError):
        world.service.prepare_approval("PRP-NOPE")


@pytest.mark.parametrize("hour", range(24))
def test_the_simulation_day_can_be_opened_at_any_hour(tmp_path: Path, hour: int) -> None:
    from datetime import UTC, datetime

    from empirical_platform.usecases.operator_console_fixtures import simulation_timezone_for

    start = datetime(2026, 9, 26, hour, 25, tzinfo=UTC)
    zone = simulation_timezone_for(start)
    assert zone == "Etc/GMT" or zone.startswith("Etc/GMT")
    late = simulation_world(tmp_path / str(hour), start=start)
    report = late.load_day(("AAPL", "XOM"))
    assert report.refused == () and set(report.proposed) == {"AAPL", "XOM"}
    # Opening the SAME day again from another hour of it re-uses the proposals and, when the
    # zone had to move, records a new configuration version rather than editing the old one.
    same_day_later = min(6 * 3600, (23 - hour) * 3600 + 30 * 60)
    late.clock.advance(same_day_later)
    again = late.load_day(("AAPL", "XOM"))
    assert again.proposed == () and set(again.already_present) == {"AAPL", "XOM"}
    versions = {k[1] for k in late.repositories.configurations.rows}  # type: ignore[attr-defined]
    assert versions in ({1}, {1, 2})


def test_open_positions_stay_visible_and_closed_or_rejected_ones_do_not(world: World) -> None:
    world.load_day(("AAPL", "MSFT", "AMZN", "V"))
    for symbol in ("AAPL", "MSFT", "AMZN", "V"):
        _approve(world, symbol)
    world.service.cancel_execution(f"INT-{world.proposal_id('V')}")
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    active = {row.symbol: row for row in world.service.active_trades()}
    assert set(active) == {"AAPL", "MSFT"}  # filled and partially filled are open positions
    assert active["AAPL"].position_open and active["AAPL"].state is HumanState.FILLED
    assert active["MSFT"].position_open and active["MSFT"].state is HumanState.PARTIALLY_FILLED
    assert active["MSFT"].can_cancel and not active["AAPL"].can_cancel
    # AMZN was rejected by the broker and V was cancelled: nothing is held, nothing is listed.
    assert _card(world, "AMZN").state is HumanState.REJECTED  # type: ignore[attr-defined]
    assert _card(world, "V").state is HumanState.CANCELLED  # type: ignore[attr-defined]
    assert world.service.today().active_positions_count == 2
    # The M085 record is untouched by the console's reading of it.
    attempt = world.repositories.attempts.for_intent(f"INT-{world.proposal_id('AAPL')}")
    assert attempt is not None and attempt.state.value == "FILLED" and attempt.is_terminal
