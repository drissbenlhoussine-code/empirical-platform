"""RELEASE v1 OVERDUE RECOVERY UI -- the two-step Owner action through the REAL WSGI
router (`build_paper_application`), reusing the already-reviewed, already-tested
`grant_overdue_recovery_approval` / `confirm_overdue_recovery` usecase pair
(`test_v1_overdue_position_recovery.py` proves their own adversarial boundaries; this file
proves the NEW routes wire them correctly, never duplicating that coverage).

Every scenario here goes through the real, approved, filled plan the prepare -> approve ->
confirm-approval HTTP round trip creates (the same path
`test_v1_paper_console_app_routes.py::test_approving_through_http_creates_the_plan...`
already proves), backdated to overdue by directly rewriting the fake repository's stored
`ApprovedPlan.mandatory_liquidation_at` -- never by weakening or mocking any safety check.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from tests.unit._m085_fakes import FakeMarketData
from tests.unit.test_m086_operator_console_routes import Client, Reply
from tests.unit.test_m088_paper_operator_console import (
    APPROVED_SYMBOL,
    _FreshQuote,
    _OpenMarketClock,
)
from tests.unit.test_v1_paper_console_app_routes import _backend, _now

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints._paper_operator_console_composition import PaperConsoleBackend
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.usecases.paper_operator_console import prepare_paper_candidate


@dataclass
class _Position:
    quantity: Decimal


def _approved_overdue_backend(
    *, base_path: str = "", market_data: FakeMarketData | None = None
) -> tuple[PaperConsoleBackend, Client, str]:
    """A real, filled, approved plan -- backdated to overdue -- behind a fresh WSGI client."""
    market_data = market_data if market_data is not None else FakeMarketData(quote=_FreshQuote())
    backend = _backend(market_data=market_data)
    client = Client(
        build_paper_application(backend, security=SecuritySession(), base_path=base_path)
    )  # type: ignore[arg-type]

    proposal = prepare_paper_candidate(
        configurations=backend._repositories.configurations,
        contexts=backend._repositories.contexts,
        proposals=backend._repositories.proposals,
        watermarks=backend._watermarks,
        time_bases=backend._repositories.time_bases,
        broker=backend._broker,  # type: ignore[arg-type]
        market_data=backend._market_data,  # type: ignore[arg-type]
        time_source=backend._time_source,
        now=_now(),
    )
    assert proposal.symbol == APPROVED_SYMBOL

    # Routes are registered bare (never prefixed) -- a reverse proxy strips `base_path`
    # before the request reaches this process; only GENERATED links/actions carry it (see
    # `test_v1_paper_base_path.py`). The in-process test client has no such proxy, so every
    # request below targets the bare path regardless of `base_path`.
    review = client.get(f"/confirm?action=APPROVE&proposal={proposal.proposal_governance_id}")
    ticket = re.search(r'name="ticket" value="([^"]+)"', review.body)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', review.body)
    assert ticket and csrf, review.body
    confirm = client.post(
        "/confirm-approval",
        form={
            "proposal": proposal.proposal_governance_id,
            "ticket": ticket.group(1),
            "csrf_token": csrf.group(1),
        },
    )
    assert confirm.code == 303, confirm.body

    intent = backend._repositories.intents.for_proposal(proposal.proposal_governance_id)
    assert intent is not None
    plans = backend._plans
    assert plans is not None
    plan = plans.for_entry(intent.intent_governance_id)  # type: ignore[attr-defined]
    assert plan is not None
    past = _now() - timedelta(hours=1)
    # `GrantOverduePositionRecoveryApprovalHandler`/`PreviewPositionExitHandler` both read
    # the ORIGINAL deadline from the persisted intent, never from the plan's own copy of it
    # -- backdating only the plan would leave the real overdue gate unsatisfied. Both are
    # rewritten here, test-only, to the exact same instant so they stay consistent.
    backend._repositories.intents.rows[intent.intent_governance_id] = dataclasses.replace(  # type: ignore[attr-defined]
        intent, mandatory_liquidation_at=past
    )
    plans.rows[plan.plan_id] = dataclasses.replace(  # type: ignore[attr-defined]
        plan, mandatory_liquidation_at=past
    )
    # The prepare -> approve HTTP round trip only creates the entry order in its
    # just-dispatched state (PAPER_ACCEPTED); it does not itself simulate a broker fill.
    # `AssessPositionExitHandler` (shared by every exit path, normal or recovery) requires
    # a FILLED entry AND an agreeing broker-reported position before anything is eligible
    # to close -- both rewritten here, test-only, to the exact quantity the plan approved.
    entry = backend._repositories.attempts.for_intent(intent.intent_governance_id)  # type: ignore[attr-defined]
    assert entry is not None
    quantity = plan.approved_quantity
    backend._repositories.attempts.rows[entry.attempt_id] = dataclasses.replace(  # type: ignore[attr-defined]
        entry,
        state=PaperExecutionState.FILLED,
        filled_quantity=quantity,
        filled_avg_price=plan.stop_price + (plan.target_price - plan.stop_price) / 2,
        terminal_at=past,
    )
    backend._broker.position = _Position(quantity=quantity)  # type: ignore[attr-defined]
    return backend, client, intent.intent_governance_id


def _csrf_of(reply: Reply) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', reply.body)
    assert match, reply.body
    return match.group(1)


# ---------------------------------------------------------------------------
# Step 1: GET /exit/recovery -- the overdue gate
# ---------------------------------------------------------------------------


def test_recovery_landing_refuses_a_position_that_is_not_actually_overdue() -> None:
    backend = _backend(market_data=FakeMarketData(quote=_FreshQuote()))
    client = Client(build_paper_application(backend, security=SecuritySession()))  # type: ignore[arg-type]
    proposal = prepare_paper_candidate(
        configurations=backend._repositories.configurations,
        contexts=backend._repositories.contexts,
        proposals=backend._repositories.proposals,
        watermarks=backend._watermarks,
        time_bases=backend._repositories.time_bases,
        broker=backend._broker,  # type: ignore[arg-type]
        market_data=backend._market_data,  # type: ignore[arg-type]
        time_source=backend._time_source,
        now=_now(),
    )
    review = client.get(f"/confirm?action=APPROVE&proposal={proposal.proposal_governance_id}")
    ticket = re.search(r'name="ticket" value="([^"]+)"', review.body)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', review.body)
    assert ticket and csrf
    client.post(
        "/confirm-approval",
        form={
            "proposal": proposal.proposal_governance_id,
            "ticket": ticket.group(1),
            "csrf_token": csrf.group(1),
        },
    )
    intent = backend._repositories.intents.for_proposal(proposal.proposal_governance_id)
    assert intent is not None

    reply = client.get(f"/exit/recovery?intent={intent.intent_governance_id}")
    assert reply.code == 200
    assert "Not overdue" in reply.body
    assert "GRANT RECOVERY APPROVAL" not in reply.body


def test_recovery_landing_refuses_an_entry_with_no_managed_plan() -> None:
    backend = _backend(market_data=FakeMarketData(quote=_FreshQuote()))
    client = Client(build_paper_application(backend, security=SecuritySession()))  # type: ignore[arg-type]
    reply = client.get("/exit/recovery?intent=INT-DOES-NOT-EXIST")
    assert reply.code == 400
    assert "No managed plan" in reply.body


def test_recovery_landing_offers_the_grant_action_for_a_genuinely_overdue_position() -> None:
    _backend_obj, client, intent_id = _approved_overdue_backend()
    reply = client.get(f"/exit/recovery?intent={intent_id}")
    assert reply.code == 200
    assert "GRANT RECOVERY APPROVAL" in reply.body
    assert "OVERDUE POSITION RECOVERY" in reply.body


# ---------------------------------------------------------------------------
# Step 2: POST /exit/recovery/grant
# ---------------------------------------------------------------------------


def test_grant_route_records_a_real_approval_and_redirects_to_review() -> None:
    backend, client, intent_id = _approved_overdue_backend()
    landing = client.get(f"/exit/recovery?intent={intent_id}")
    csrf = _csrf_of(landing)

    reply = client.post("/exit/recovery/grant", form={"intent": intent_id, "csrf_token": csrf})
    assert reply.code == 303, reply.body
    assert "/exit/recovery/review" in reply.headers["location"]
    assert "recovery=RCV-" in reply.headers["location"]

    service = backend.service
    assert service.exits is not None
    events = service.exits._x.events  # type: ignore[attr-defined]
    recorded = [e for e in events.rows if e.event_type.startswith("EXIT_OVERDUE_RECOVERY")]
    assert len(recorded) == 1


def test_grant_route_requires_csrf() -> None:
    _backend_obj, client, intent_id = _approved_overdue_backend()
    reply = client.post("/exit/recovery/grant", form={"intent": intent_id, "csrf_token": "forged"})
    assert reply.code == 403


# ---------------------------------------------------------------------------
# Step 3: GET /exit/recovery/review
# ---------------------------------------------------------------------------


def test_review_route_requires_a_recovery_id() -> None:
    _backend_obj, client, intent_id = _approved_overdue_backend()
    reply = client.get(f"/exit/recovery/review?intent={intent_id}")
    assert reply.code == 400
    assert "Recovery approval required" in reply.body


def test_review_route_shows_the_exact_frozen_terms_and_recovery_label() -> None:
    backend, client, intent_id = _approved_overdue_backend()
    csrf = _csrf_of(client.get(f"/exit/recovery?intent={intent_id}"))
    grant = client.post("/exit/recovery/grant", form={"intent": intent_id, "csrf_token": csrf})
    location = grant.headers["location"]

    reply = client.get(location)
    assert reply.code == 200
    assert "OVERDUE POSITION RECOVERY" in reply.body
    assert "CONFIRM OVERDUE RECOVERY SELL" in reply.body
    assert "SELL TO CLOSE" in reply.body
    assert 'action="/exit/recovery/confirm"' in reply.body
    assert 'name="recovery" value="RCV-' in reply.body


# ---------------------------------------------------------------------------
# Step 4: POST /exit/recovery/confirm -- dispatch, idempotency, refusals
# ---------------------------------------------------------------------------


def _grant_and_review(client: Client, intent_id: str) -> tuple[str, str, str]:
    csrf = _csrf_of(client.get(f"/exit/recovery?intent={intent_id}"))
    grant = client.post("/exit/recovery/grant", form={"intent": intent_id, "csrf_token": csrf})
    review = client.get(grant.headers["location"])
    ticket = re.search(r'name="ticket" value="([^"]+)"', review.body)
    recovery = re.search(r'name="recovery" value="([^"]+)"', review.body)
    confirm_csrf = re.search(r'name="csrf_token" value="([^"]+)"', review.body)
    assert ticket and recovery and confirm_csrf, review.body
    return ticket.group(1), recovery.group(1), confirm_csrf.group(1)


def test_confirm_route_dispatches_exactly_once_even_on_a_double_click() -> None:
    backend, client, intent_id = _approved_overdue_backend()
    ticket, recovery, csrf = _grant_and_review(client, intent_id)
    form = {"intent": intent_id, "ticket": ticket, "recovery": recovery, "csrf_token": csrf}

    first = client.post("/exit/recovery/confirm", form=form)
    assert first.code == 200, first.body

    second = client.post("/exit/recovery/confirm", form=form)
    assert second.code == 200, second.body
    assert "Already confirmed" in second.body or "already" in second.body.lower()

    attempts = backend._exits.attempts  # type: ignore[attr-defined]
    dispatched = [a for a in attempts.rows.values() if a.entry_intent_governance_id == intent_id]
    assert len(dispatched) == 1, "a double-click must never create a second broker order"


def test_confirm_route_refuses_without_a_prior_grant() -> None:
    backend, client, intent_id = _approved_overdue_backend()
    review_page = client.get(f"/exit/recovery?intent={intent_id}")
    csrf = _csrf_of(review_page)
    # Build a review ticket the normal way (reusing /exit/review, same ticket machinery)
    # but never grant -- confirm must refuse, not fabricate an approval from the id alone.
    exit_review = client.get(f"/exit/review?intent={intent_id}")
    ticket = re.search(r'name="ticket" value="([^"]+)"', exit_review.body)
    assert ticket
    reply = client.post(
        "/exit/recovery/confirm",
        form={
            "intent": intent_id,
            "ticket": ticket.group(1),
            "recovery": "RCV-FORGED-NEVER-GRANTED",
            "csrf_token": csrf,
        },
    )
    assert reply.code == 400
    assert "Exit refused" in reply.body or "refused" in reply.body.lower()


def test_confirm_route_refuses_a_recovery_id_that_does_not_match_the_granted_one() -> None:
    backend, client, intent_id = _approved_overdue_backend()
    ticket, _recovery, csrf = _grant_and_review(client, intent_id)
    reply = client.post(
        "/exit/recovery/confirm",
        form={
            "intent": intent_id,
            "ticket": ticket,
            "recovery": "RCV-SOME-OTHER-APPROVAL-NEVER-GRANTED",
            "csrf_token": csrf,
        },
    )
    assert reply.code == 400
    attempts = backend._exits.attempts  # type: ignore[attr-defined]
    assert len(attempts.rows) == 0, "nothing may dispatch on a mismatched recovery id"


def test_confirm_route_refuses_a_stale_ticket() -> None:
    _backend_obj, client, intent_id = _approved_overdue_backend()
    _ticket, recovery, csrf = _grant_and_review(client, intent_id)
    reply = client.post(
        "/exit/recovery/confirm",
        form={
            "intent": intent_id,
            "ticket": "not-a-real-ticket",
            "recovery": recovery,
            "csrf_token": csrf,
        },
    )
    assert reply.code in (400, 500)


def test_confirm_route_refuses_outside_regular_trading_hours() -> None:
    backend, client, intent_id = _approved_overdue_backend()
    ticket, recovery, csrf = _grant_and_review(client, intent_id)
    backend._broker.fetch_clock = lambda: _OpenMarketClock(is_open=False)  # type: ignore[method-assign]
    reply = client.post(
        "/exit/recovery/confirm",
        form={"intent": intent_id, "ticket": ticket, "recovery": recovery, "csrf_token": csrf},
    )
    assert reply.code == 400
    assert "regular trading session" in reply.body
    attempts = backend._exits.attempts  # type: ignore[attr-defined]
    assert len(attempts.rows) == 0


def test_confirm_route_requires_csrf() -> None:
    _backend_obj, client, intent_id = _approved_overdue_backend()
    ticket, recovery, _csrf = _grant_and_review(client, intent_id)
    reply = client.post(
        "/exit/recovery/confirm",
        form={"intent": intent_id, "ticket": ticket, "recovery": recovery, "csrf_token": "forged"},
    )
    assert reply.code == 403


# ---------------------------------------------------------------------------
# Normal exit path is untouched
# ---------------------------------------------------------------------------


def test_normal_exit_review_and_confirm_routes_are_unaffected_by_recovery_routes() -> None:
    _backend_obj, client, intent_id = _approved_overdue_backend()
    reply = client.get(f"/exit/review?intent={intent_id}")
    assert reply.code == 200
    assert "CONFIRM EXIT" in reply.body
    assert "RECOVERY" not in reply.body


# ---------------------------------------------------------------------------
# Base-path (RELEASE v1 /paper base-path escape correction stays in force)
# ---------------------------------------------------------------------------


def test_recovery_flow_stays_under_the_configured_base_path() -> None:
    """Routes register bare (a proxy strips `base_path` before the request arrives -- see
    `test_v1_paper_base_path.py`); only GENERATED links/form-actions must carry the prefix."""
    backend, client, intent_id = _approved_overdue_backend(base_path="/paper")
    landing = client.get(f"/exit/recovery?intent={intent_id}")
    assert landing.code == 200
    assert 'action="/paper/exit/recovery/grant"' in landing.body
    csrf = _csrf_of(landing)
    grant = client.post("/exit/recovery/grant", form={"intent": intent_id, "csrf_token": csrf})
    assert grant.code == 303
    location = grant.headers["location"]
    assert location.startswith("/paper/exit/recovery/review")
    review = client.get(location.removeprefix("/paper"))
    assert review.code == 200
    assert 'action="/paper/exit/recovery/confirm"' in review.body
