"""RELEASE v1 -- `paper_operator_console_app.py`'s plan-aware route overrides, driven
through the REAL WSGI router (`build_paper_application`) over an in-memory, PAPER-shaped
`PaperConsoleBackend` -- the same fake-broker/fake-market-data discipline
`test_m088_paper_operator_console.py` already establishes for this console, extended with
an `ApprovedPlanRepository` and `ExitRepositories` so the v1-specific overrides
(`/confirm-approval`, `/active`, `/history`) are exercised end-to-end, not just their pure
per-row helpers.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from tests.unit._m085_fakes import (
    FakeMarketData,
)
from tests.unit._m086_fakes import (
    MemoryWatermarks,
)
from tests.unit._m087_fakes import (
    FakeExitAcknowledgements,
    FakeExitAttempts,
    FakeExitAuthorizations,
    FakeExitEvents,
    FakeExitPreviews,
    FakeExitRounds,
)
from tests.unit._v1_fakes import FakeApprovedPlans
from tests.unit.test_m086_operator_console_routes import Client
from tests.unit.test_m088_paper_operator_console import (
    APPROVED_SYMBOL,
    _FreshQuote,
    _open_broker,
    _paper_repositories,
)

from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints._paper_operator_console_composition import (
    PAPER_CAPABILITY,
    PaperConsoleBackend,
)
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource
from empirical_platform.usecases.operator_console import HmacSigner, OperatorConsoleService
from empirical_platform.usecases.operator_console_exits import ExitRepositories, PositionExitConsole


def _now() -> datetime:
    return datetime.now(UTC)


def _backend(*, market_data: FakeMarketData | None = None) -> PaperConsoleBackend:
    repositories = _paper_repositories()
    broker = _open_broker()
    market_data = market_data if market_data is not None else FakeMarketData(quote=None)
    authorizations = FakeExitAuthorizations()
    attempts = FakeExitAttempts(authorizations)
    acknowledgements = FakeExitAcknowledgements()
    events = FakeExitEvents()
    exits = ExitRepositories(
        previews=FakeExitPreviews(),
        authorizations=authorizations,
        attempts=attempts,
        acknowledgements=acknowledgements,
        rounds=FakeExitRounds(attempts, acknowledgements, events),
        events=events,
    )
    signer = HmacSigner(b"x" * 32)
    time_source = SystemPaperTimeSource()
    exit_console = PositionExitConsole(
        exits=exits,
        intents=repositories.intents,
        entry_attempts=repositories.attempts,
        configurations=repositories.configurations,
        kill_switch=repositories.kill_switch,
        broker=broker,  # type: ignore[arg-type]
        market_data=market_data,  # type: ignore[arg-type]
        signer=signer,
        time_source=time_source,
        clock=_now,
        environment="PAPER",
    )
    service = OperatorConsoleService(
        repositories=repositories,
        broker=broker,  # type: ignore[arg-type]
        market_data=market_data,  # type: ignore[arg-type]
        signer=signer,
        capability=PAPER_CAPABILITY,
        time_source=time_source,
        exits=exit_console,
    )
    return PaperConsoleBackend(
        service=service,
        configuration_id="CFG-089-PAPER",
        _repositories=repositories,
        _watermarks=MemoryWatermarks(),  # type: ignore[arg-type]
        _broker=broker,  # type: ignore[arg-type]
        _market_data=market_data,  # type: ignore[arg-type]
        _time_source=time_source,
        _plans=FakeApprovedPlans(),
        _plan_manager=None,
        _exits=exits,
    )


@pytest.fixture
def client() -> Client:
    return Client(build_paper_application(_backend(), security=SecuritySession()))  # type: ignore[arg-type]


def test_active_route_is_overridden_and_renders_with_no_managed_plans(client: Client) -> None:
    reply = client.get("/active")
    assert reply.code == 200
    assert "Active trades" in reply.body
    assert "Approved plan" not in reply.body


def test_history_route_is_overridden_and_renders_without_the_plan_column_when_empty(
    client: Client,
) -> None:
    reply = client.get("/history")
    assert reply.code == 200
    assert "<th>Plan</th>" not in reply.body


def test_confirm_approval_override_refuses_a_nonexistent_proposal_gracefully(
    client: Client,
) -> None:
    """The override must translate a refusal into the SAME graceful error page the rest of
    this console already shows -- never an uncaught exception/raw 500 traceback."""
    reply = client.post("/confirm-approval", form={"proposal": "PRP-DOES-NOT-EXIST", "ticket": "x"})
    assert reply.code in (400, 403, 404, 500)
    assert "<html" in reply.body.lower()


def test_confirm_approval_override_is_registered_only_when_plans_is_set() -> None:
    from empirical_platform.entrypoints._paper_operator_console_composition import (
        PaperConsoleBackend as _Backend,
    )

    backend = _backend()
    plain = _Backend(
        service=backend.service,
        configuration_id=backend.configuration_id,
        _repositories=backend._repositories,
        _watermarks=backend._watermarks,
        _broker=backend._broker,
        _market_data=backend._market_data,
        _time_source=backend._time_source,
        # _plans/_plan_manager/_exits default to None -- the plain M088 composition shape.
    )
    plain_client = Client(build_paper_application(plain, security=SecuritySession()))  # type: ignore[arg-type]
    reply = plain_client.get("/active")
    assert reply.code == 200
    assert "Approved plan" not in reply.body


def test_approving_through_http_creates_the_plan_and_renders_it_on_active_and_history() -> None:
    """The full real round trip, through HTTP: prepare -> review -> POST /confirm-approval
    (the v1 override) -> the ApprovedPlan now exists -> /active shows its managed-plan
    block and /history shows its Plan column, both via the SAME route overrides. This is
    what closes the gap `active_plan_block_for_row`/`history_plan_cell_for_row`'s own direct
    unit tests cannot: the ROUTE's own wiring (repository lookups, quote fetch, loop) that
    calls them."""
    from empirical_platform.usecases.paper_operator_console import prepare_paper_candidate

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
    assert proposal.symbol == APPROVED_SYMBOL

    review = client.get(f"/confirm?action=APPROVE&proposal={proposal.proposal_governance_id}")
    assert review.code == 200
    ticket_match = re.search(r'name="ticket" value="([^"]+)"', review.body)
    assert ticket_match, review.body
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', review.body)
    assert csrf_match, review.body

    confirm = client.post(
        "/confirm-approval",
        form={
            "proposal": proposal.proposal_governance_id,
            "ticket": ticket_match.group(1),
            "csrf_token": csrf_match.group(1),
        },
    )
    assert confirm.code == 303, confirm.body

    intent = backend._repositories.intents.for_proposal(proposal.proposal_governance_id)
    assert intent is not None
    plan = backend._plans.for_entry(intent.intent_governance_id)  # type: ignore[union-attr]
    assert plan is not None
    assert plan.candidate_id == proposal.proposal_governance_id

    active_page = client.get("/active")
    assert active_page.code == 200
    assert "Approved plan" in active_page.body
    assert "Monitoring" in active_page.body

    history_page = client.get("/history")
    assert history_page.code == 200
    assert "<th>Plan</th>" in history_page.body
    assert f"Candidate {proposal.proposal_governance_id}" in history_page.body
