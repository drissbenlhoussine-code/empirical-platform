"""MILESTONE-087 -- the exit over HTTP: review page, CONFIRM EXIT, refusals, no resend."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit.test_m086_operator_console_routes import Backend, Client

from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints.operator_console_app import build_application
from empirical_platform.shared.brokerage.simulation_paper import SimulationExitScenario


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


@pytest.fixture
def client(world: World) -> Client:
    return Client(build_application(Backend(world), security=SecuritySession()))  # type: ignore[arg-type]


def _ticket(page: str) -> str:
    match = re.search(r'name="ticket" value="([^"]+)"', page)
    assert match, "no ticket on the review page"
    return match.group(1)


def _open_position(
    client: Client, world: World, exit_scenario: SimulationExitScenario | None = None
) -> str:
    world.load_day(
        ("AAPL",), exit_scenarios=None if exit_scenario is None else {"AAPL": exit_scenario}
    )
    proposal = world.proposal_id("AAPL")
    confirm = client.get(f"/confirm?action=APPROVE&proposal={proposal}")
    ticket = re.search(r'name="ticket" value="([^"]+)"', confirm.body).group(1)  # type: ignore[union-attr]
    client.post(
        "/confirm-approval", {"csrf_token": client.csrf(), "proposal": proposal, "ticket": ticket}
    )
    for _ in range(2):
        world.clock.advance(5)
        client.post("/active/refresh", {"csrf_token": client.csrf()})
    return f"INT-{proposal}"


def test_the_review_page_shows_the_exact_terms_and_sends_nothing(
    client: Client, world: World
) -> None:
    intent = _open_position(client, world)
    active = client.get("/active")
    assert "Open position" in active.body and f"/exit/review?intent={intent}" in active.body
    assert "Liquidation deadline" in active.body
    review = client.get(f"/exit/review?intent={intent}")
    assert review.code == 200
    body = review.body
    for expected in (
        ">SIMULATION<",
        "Review exit",
        "SELL TO CLOSE",
        "<dt>Current verified holding</dt><dd>8 shares</dd>",
        "<dt>Exit quantity</dt><dd>8 shares (full close)</dd>",
        "<dt>Order type</dt><dd>LIMIT</dd>",
        "<dt>Limit price</dt><dd>227.40</dd>",
        "<dt>Entry average fill price</dt><dd>227.50</dd>",
        "<dt>Environment</dt><dd>SIMULATION</dd>",
        "Mandatory liquidation deadline",
        "Authorization expires",
        "Exit reference",
        "CONFIRM EXIT",
        'action="/exit/confirm"',
    ):
        assert expected in body, expected
    assert "<script" not in body
    assert world.exits.attempts.for_entry(intent) == ()  # GET never sends


def test_confirm_exit_sends_once_and_a_refresh_or_replay_never_sends_again(
    client: Client, world: World
) -> None:
    intent = _open_position(client, world)
    ticket = _ticket(client.get(f"/exit/review?intent={intent}").body)
    reply = client.post(
        "/exit/confirm", {"csrf_token": client.csrf(), "intent": intent, "ticket": ticket}
    )
    assert reply.code == 303 and reply.headers["location"] == f"/execution?intent={intent}"
    page = client.follow(reply)
    assert "Exit confirmed and sent" in page.body and "Exit in progress" in page.body
    # Refreshing the redirected page re-reads; replaying the POST reports the same exit.
    again = client.get(f"/execution?intent={intent}")
    assert "Exit in progress" in again.body and "Exit confirmed and sent" not in again.body
    replay = client.post(
        "/exit/confirm", {"csrf_token": client.csrf(), "intent": intent, "ticket": ticket}
    )
    assert "Already confirmed" in client.follow(replay).body
    assert len(world.exits.attempts.for_entry(intent)) == 1
    assert len([o for o in world.store.orders() if o.side == "sell"]) == 1
    for _ in range(2):
        world.clock.advance(5)
        client.post("/active/refresh", {"csrf_token": client.csrf()})
    closed = client.get(f"/execution?intent={intent}")
    assert "Position closed" in closed.body and "verified" in closed.body
    assert "realized" in closed.body and "simulation" in closed.body
    assert "No active trades" in client.get("/active").body
    history = client.get("/history")
    assert "Position closed (simulation)" in history.body and "realized" in history.body


@pytest.mark.parametrize("field", ["environment", "capability", "mode", "venue"])
def test_an_exit_confirmation_that_chooses_an_environment_fails_closed(
    client: Client, world: World, field: str
) -> None:
    intent = _open_position(client, world)
    ticket = _ticket(client.get(f"/exit/review?intent={intent}").body)
    reply = client.post(
        "/exit/confirm",
        {"csrf_token": client.csrf(), "intent": intent, "ticket": ticket, field: "PAPER"},
    )
    assert reply.code == 403 and "cannot select an execution environment" in reply.body
    assert world.exits.attempts.for_entry(intent) == ()


def test_a_post_without_the_csrf_token_or_a_stale_ticket_sends_nothing(
    client: Client, world: World
) -> None:
    intent = _open_position(client, world)
    ticket = _ticket(client.get(f"/exit/review?intent={intent}").body)
    no_csrf = client.post("/exit/confirm", {"intent": intent, "ticket": ticket})
    assert no_csrf.code == 403
    stale = client.post(
        "/exit/confirm", {"csrf_token": client.csrf(), "intent": intent, "ticket": ticket + "x"}
    )
    assert stale.code == 400 and (
        "Nothing was done" in stale.body or "Nothing was sent" in stale.body
    )
    assert world.exits.attempts.for_entry(intent) == ()


def test_an_ineligible_position_shows_the_attention_message(client: Client, world: World) -> None:
    world.load_day(("NVDA",))
    proposal = world.proposal_id("NVDA")
    confirm = client.get(f"/confirm?action=APPROVE&proposal={proposal}")
    ticket = re.search(r'name="ticket" value="([^"]+)"', confirm.body).group(1)  # type: ignore[union-attr]
    client.post(
        "/confirm-approval", {"csrf_token": client.csrf(), "proposal": proposal, "ticket": ticket}
    )
    reply = client.get(f"/exit/review?intent=INT-{proposal}")
    assert reply.code == 400
    assert "Position requires operator attention before it can be closed safely" in reply.body
    assert "Nothing was sent" in reply.body


def test_an_unknown_exit_is_shown_as_needs_attention_do_not_retry(
    client: Client, world: World
) -> None:
    intent = _open_position(
        client, world, SimulationExitScenario.EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND
    )
    ticket = _ticket(client.get(f"/exit/review?intent={intent}").body)
    page = client.follow(
        client.post(
            "/exit/confirm", {"csrf_token": client.csrf(), "intent": intent, "ticket": ticket}
        )
    )
    assert "Outcome unknown" in page.body and "do not retry" in page.body
    assert "Needs attention" in page.body
    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.state is PositionExitState.SUBMISSION_UNKNOWN
    review_again = client.get(f"/exit/review?intent={intent}")
    assert review_again.code == 400 and "already in progress" in review_again.body


def test_the_exit_cancel_flow_needs_its_own_confirmation(client: Client, world: World) -> None:
    intent = _open_position(client, world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    ticket = _ticket(client.get(f"/exit/review?intent={intent}").body)
    client.post("/exit/confirm", {"csrf_token": client.csrf(), "intent": intent, "ticket": ticket})
    (attempt,) = world.exits.attempts.for_entry(intent)
    page = client.get(f"/execution?intent={intent}")
    assert f"/exit/cancel?attempt={attempt.attempt_id}" in page.body
    form = client.get(f"/exit/cancel?attempt={attempt.attempt_id}")
    assert form.code == 200 and "CONFIRM EXIT CANCEL REQUEST" in form.body
    assert world.exits.attempts.get(attempt.attempt_id).state is PositionExitState.ACCEPTED  # type: ignore[union-attr]
    reply = client.post(
        "/exit/confirm-cancel",
        {"csrf_token": client.csrf(), "attempt": attempt.attempt_id, "intent": intent},
    )
    assert "Exit cancel requested" in client.follow(reply).body
    assert world.exits.attempts.get(attempt.attempt_id).state is PositionExitState.CANCEL_REQUESTED  # type: ignore[union-attr]
