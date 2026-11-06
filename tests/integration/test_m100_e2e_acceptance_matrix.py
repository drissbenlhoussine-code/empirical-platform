"""M100 END-TO-END ACCEPTANCE MATRIX -- the Owner's 24 numbered steps, ACC-01 ... ACC-24.

WHAT THIS DRIVES. The REAL production composition `paper_operator_console_with_exit_runtime()`
(the function the deployed console calls) over REAL PostgreSQL test databases -- Store A/B
migrated to head, Store C to its own head -- with the real `AlpacaPaperClient` and
`AlpacaPaperMarketDataClient`, the real `OperatorConsoleService`, the real WSGI routes
(`build_paper_application`), the real M085 PaperExecution handlers, the real `ApprovedPlan` +
`PositionPlanManager`, and the real position-exit handlers. The ONLY fake is the broker /
market-data WIRE: a scripted exchange on 127.0.0.1 (`tests/integration/_m100_fake_alpaca.py`),
reached by redirecting `HTTPSConnection.connect` while every host pin stays in force. No real
broker, no real network, no secret.

EVIDENCE. Each test records what it OBSERVED (ids, states, refusal texts, row counts, row
hashes) through the `evidence` fixture (`_acceptance_evidence.py`); the session writes
`$M100_EVIDENCE_DIR/acceptance-evidence.json`, rendered by
`tools/m100_render_acceptance_report.py`. A step that cannot be driven with real code is not
faked here -- see each docstring's "NOT END-TO-END" notes, if any.

OPT-IN. Skipped unless `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` (plus the usual disposable
`_test` database variables); the repo-wide `pytest` run is unaffected.

Test names carry the exact identifier (`test_ACC_07_...`); a trailing letter (`ACC_04b`) names
an additional test under the same numbered step (the new D1 / D3 controls).
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from tests.integration._m085_support import build_engine, config, postgres_enabled
from tests.integration._m089_support import build_engine_c
from tests.integration._m100_fake_alpaca import FakeAlpacaExchange, VirtualClock, serve_exchange
from tests.integration._m100_world import SYMBOL, Stack, World, empty_database, v1_configuration

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    PaperExecutionState,
    PaperOrderRequest,
)
from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.decision_candidate.trade_approval import OperatorAction
from empirical_platform.shared.brokerage import paper_time
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.opportunity_engine_repositories import (  # noqa: E501
    PostgresOpportunityEngineRuntime,
)
from empirical_platform.usecases.opportunity_engine import (
    GenerateOpportunitiesCommand,
    GenerateOpportunitiesHandler,
)
from empirical_platform.usecases.paper_execution import (
    DecidePaperBoundTradeProposalCommand,
    DecidePaperBoundTradeProposalHandler,
    IssuePaperBoundOrderIntentCommand,
    IssuePaperBoundOrderIntentHandler,
    PaperExecutionRefusedError,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)
from empirical_platform.usecases.paper_operator_console import (
    V1PaperCandidateRefusedError,
)
from empirical_platform.usecases.position_plan_manager import PlanOutcomeKind

if TYPE_CHECKING:
    from tests.integration._acceptance_evidence import EvidenceRecorder

pytest_plugins = ["tests.integration._acceptance_evidence"]
pytestmark = pytest.mark.integration

_CI_PLACEHOLDER_A = "empirical-ci-only-key-0001"
_CI_PLACEHOLDER_B = "empirical-ci-only-secret-0001"


# ---------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def stores() -> Iterator[tuple[Engine, Engine]]:
    """Store A/B at head and Store C at its head, built once from the real migration chains."""
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    for name in (
        "EMPIRICAL_PLATFORM_POSTGRES_DATABASE",
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE",
    ):
        if not os.environ.get(name, "").endswith("_test"):
            pytest.fail(f"{name} must explicitly name a disposable _test database")
    generator_b = build_engine("head")
    generator_c = build_engine_c("head")
    engine_b = next(generator_b)
    engine_c = next(generator_c)
    try:
        yield engine_b, engine_c
    finally:
        for generator in (generator_c, generator_b):
            try:
                next(generator)
            except StopIteration:
                pass


@pytest.fixture
def world(stores: tuple[Engine, Engine], monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    engine_b, engine_c = stores
    empty_database(engine_b)
    empty_database(engine_c)
    monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_CI_PLACEHOLDER_A", _CI_PLACEHOLDER_A)
    monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_CI_PLACEHOLDER_B", _CI_PLACEHOLDER_B)
    monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_BASE_URL", f"https://{PAPER_ENDPOINT_HOST}")
    clock = VirtualClock()
    monkeypatch.setattr(paper_time.SystemPaperTimeSource, "read", lambda self: clock.reading())
    exchange = FakeAlpacaExchange(clock)
    with serve_exchange(exchange, monkeypatch):
        the_world = World(engine_b, engine_c, exchange, clock, monkeypatch)
        the_world.save_configuration(v1_configuration())
        yield the_world


# ---------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------


def rows(engine: Engine, sql: str, **params: Any) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(r) for r in connection.execute(text(sql), params).mappings().all()]


def count(engine: Engine, table: str) -> int:
    return int(rows(engine, f"SELECT count(*) AS n FROM public.{table}")[0]["n"])  # noqa: S608


def page_text(body: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def sell_posts(exchange: FakeAlpacaExchange) -> list[dict[str, Any]]:
    return [p for p in exchange.posts() if p["side"] == "sell"]


def buy_posts(exchange: FakeAlpacaExchange) -> list[dict[str, Any]]:
    return [p for p in exchange.posts() if p["side"] == "buy"]


def approve_refused(stack: Stack, proposal_id: str, *, resume: bool = False) -> str:
    """Approve through the real route and return WHY nothing was sent, from durable evidence.

    A refusal raised by the submit handler is an error page (4xx). An approval that was
    RECORDED but whose preview is not authorizable redirects (303) back to the opportunity
    page; the reasons then live in the stored preview row's `refusals`, which is what is
    returned (the v1 route override does not show the outcome flash -- see the ACC report).
    """
    reply = stack.approve_via_route(proposal_id, resume=resume)
    if reply.code == 303:
        stored = rows(
            stack.world.engine_b,
            "SELECT refusals FROM public.paper_submission_preview "
            "WHERE preview_id LIKE :prefix ORDER BY created_at DESC LIMIT 1",
            prefix=f"PVW-{proposal_id}-%",
        )
        assert stored, "an approval redirect without a stored preview: nothing explains it"
        reasons = stored[0]["refusals"]
        reasons = reasons if isinstance(reasons, list) else [str(reasons)]
        assert reasons, "a blocked approval must carry its refusal reasons"
        landed = page_text(stack.client.get(reply.headers["location"]).body)
        assert "nothing was sent" in landed.lower()
        return "execution is blocked: " + "; ".join(reasons)
    assert reply.code >= 400, f"expected a refusal, got {reply.code}"
    return page_text(reply.body)


# ---------------------------------------------------------------------------------------
# ACC-01 .. ACC-04  data, signal, candidate, risk
# ---------------------------------------------------------------------------------------


def test_ACC_01_market_data_received(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-01 -- the real `AlpacaPaperMarketDataClient` (composed by the production runtime)
    and `AlpacaPaperClient` read the quote, minute bars, recent quote ticks and the broker
    clock off the wire; an unavailable feed yields NO data (and therefore no candidate) rather
    than a guess."""
    ex = world.exchange
    with world.stack() as stack:
        market_data = stack.backend._market_data  # noqa: SLF001
        broker = stack.backend._broker  # noqa: SLF001
        now = world.clock.now()
        quote = market_data.fetch_quote(SYMBOL)
        bars = market_data.fetch_minute_bars(SYMBOL, start=now - timedelta(minutes=10), end=now)
        ticks = market_data.fetch_recent_quotes(SYMBOL, start=now - timedelta(seconds=15), end=now)
        clock = broker.fetch_clock()
        assert quote is not None and (quote.bid, quote.ask) == ("99.98", "100.0")
        assert quote.source == "alpaca-iex"
        age = (world.clock.now() - quote.captured_at).total_seconds()
        assert 0 <= age < 10
        assert len(bars) == 3 and all(b.volume == 400_000 for b in bars)
        assert len(ticks) == 12 and clock.is_open is True
        assert market_data.endpoint_host == "data.alpaca.markets"
        assert broker.endpoint_host == PAPER_ENDPOINT_HOST
        wire = {path.split("?")[0] for _, path, _ in ex.requests}
        assert {
            f"/v2/stocks/{SYMBOL}/quotes/latest",
            f"/v2/stocks/{SYMBOL}/bars",
            f"/v2/stocks/{SYMBOL}/quotes",
            "/v2/clock",
        } <= wire
        # An unavailable feed is NOT data: the adapter reports None and the candidate step
        # refuses, writing nothing.
        ex.fail_paths["/v2/stocks"] = 503
        assert market_data.fetch_quote(SYMBOL) is None
        with pytest.raises(V1PaperCandidateRefusedError, match="no live quote"):
            stack.prepare()
        ex.fail_paths.clear()
        assert count(world.engine_b, "trade_proposal") == 0
        assert buy_posts(ex) == []
    evidence.record(
        quote={"bid": quote.bid, "ask": quote.ask, "age_seconds": round(age, 2)},
        bars_received=len(bars),
        recent_quote_ticks=len(ticks),
        broker_clock_open=clock.is_open,
        endpoints={"trading": broker.endpoint_host, "data": market_data.endpoint_host},
        wire_paths=sorted(wire),
        unavailable_feed_refusal="no live quote",
        proposals_written_on_outage=0,
        orders_posted=0,
    )


def test_ACC_02_signal_generated(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-02 -- the REAL M090 `GenerateOpportunitiesHandler` evaluates real minute bars off the
    wire (breakout + higher low + volume) and persists a TradingOpportunity in Postgres; flat
    bars produce a REJECTED row with a reason, not a signal. Read-only: zero orders."""
    from empirical_platform.entrypoints._opportunity_engine_composition import (
        DEFAULT_OPPORTUNITY_ENGINE_POLICY,
    )

    ex = world.exchange
    ex.set_quote("100.38", "100.40")
    ex.bars = [
        (6, "99.50", "99.80", "99.40", "99.70", 30000),
        (5, "99.70", "99.90", "99.60", "99.80", 30000),
        (4, "99.80", "100.00", "99.70", "99.90", 30000),
        (3, "99.90", "100.00", "99.75", "99.95", 30000),
        (2, "99.95", "100.00", "99.80", "99.98", 30000),
        (1, "100.00", "100.45", "99.90", "100.40", 60000),
    ]
    with world.stack() as stack:
        service = PostgresPersistenceService(config())
        service.initialize()
        try:
            runtime = PostgresOpportunityEngineRuntime(service)

            def generate(session_date: str) -> Any:
                return GenerateOpportunitiesHandler(
                    configuration=v1_configuration(),
                    policy=DEFAULT_OPPORTUNITY_ENGINE_POLICY,
                    broker=stack.backend._broker,  # noqa: SLF001
                    market_data=stack.backend._market_data,  # noqa: SLF001
                    bars=stack.backend._market_data,  # noqa: SLF001
                    opportunities=runtime.opportunities,
                ).handle(
                    GenerateOpportunitiesCommand(
                        session_date=session_date, generated_at=world.clock.now()
                    )
                )

            signal = generate("2026-11-06")[0]
            assert signal.status.value == "ACTIONABLE" and signal.rejection_reasons == ()
            assert signal.entry_price == Decimal("100.40")
            assert signal.stop_price < signal.entry_price < signal.target_price
            assert signal.reward_risk_ratio >= 2
            stored = runtime.opportunities.get(signal.opportunity_id)
            assert stored == signal
            # Control: flat bars -> no breakout -> a REJECTED row, not a signal.
            ex.bars = [(m, "100.00", "100.10", "99.90", "100.00", 30000) for m in range(6, 0, -1)]
            no_signal = generate("2026-11-07")[0]
            assert no_signal.status.value == "REJECTED" and no_signal.rejection_reasons
        finally:
            service.close()
        persisted = rows(
            world.engine_b, "SELECT status, count(*) AS n FROM public.opportunity GROUP BY status"
        )
        assert buy_posts(ex) == [] and ex.posts() == []
    evidence.record(
        signal={
            "opportunity_id": signal.opportunity_id,
            "status": signal.status,
            "entry": signal.entry_price,
            "stop": signal.stop_price,
            "target": signal.target_price,
            "quantity": signal.quantity,
            "reward_risk": signal.reward_risk_ratio,
            "evidence": signal.evidence,
        },
        control_flat_bars={
            "status": no_signal.status,
            "reasons": no_signal.rejection_reasons,
        },
        opportunity_rows_by_status={r["status"]: r["n"] for r in persisted},
        opportunity_table=evidence.digest(world.engine_b, "opportunity"),
        orders_posted=0,
    )


def test_ACC_03_candidate_prepared(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-03 -- the Owner's 'Prepare' button: POST /prepare-candidate through the real WSGI
    app -> `prepare_v1_paper_candidate` under CFG-089-PAPER with live wire evidence. Writes ONE
    PREPARED proposal (+ context + risk-check rows) and NOTHING else: no decision, intent,
    preview, authorization, attempt or order."""
    ex = world.exchange
    with world.stack() as stack:
        csrf = stack.client.csrf()
        reply = stack.client.post("/prepare-candidate", {"csrf_token": csrf})
        assert reply.code == 200, reply.body[:400]
        message = page_text(reply.body)
        assert "Candidate prepared" in message
        proposal_id = re.search(r"Proposal (PRP-089-PAPER-\w+)", message).group(1)  # type: ignore[union-attr]
        stored = stack.repositories.proposals.get(proposal_id)
        assert stored is not None and stored.status.value == "PREPARED"
        assert stored.side == "BUY" and stored.symbol == SYMBOL
        assert stored.configuration_governance_id == "CFG-089-PAPER"
        assert (stored.stop_loss_price, stored.profit_exit_price) == (
            Decimal("99.00000000"),
            Decimal("102.00000000"),
        )
        downstream = {
            t: count(world.engine_b, t)
            for t in (
                "trade_approval_decision",
                "approved_order_intent",
                "paper_submission_preview",
                "paper_execution_authorization",
                "paper_execution_attempt",
                "approved_plan",
            )
        }
        assert set(downstream.values()) == {0}
        assert ex.posts() == []
    evidence.record(
        proposal_id=proposal_id,
        status=stored.status,
        symbol=stored.symbol,
        quantity=stored.quantity,
        limit_price=stored.limit_price,
        stop=stored.stop_loss_price,
        target=stored.profit_exit_price,
        content_fingerprint=stored.content_fingerprint,
        route_message=message[:160],
        rows_written=evidence.digest(world.engine_b, "trade_proposal"),
        downstream_row_counts=downstream,
        orders_posted=0,
    )


def test_ACC_04_risk_checks_performed(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-04 -- M084's risk checks run on real wire evidence at Prepare, are persisted with the
    proposal, and each negative control (wide spread, stale quote, market closed, price out of
    bounds) REFUSES with its check named and persists no proposal."""
    ex = world.exchange
    with world.stack() as stack:
        prepared = stack.prepare()
        checks = prepared.proposal.risk_checks
        ids = [c.check_id for c in checks]
        assert len(ids) >= 20 and all(c.outcome.value == "PASSED" for c in checks)
        assert {"spread", "market_data_age", "no_existing_position", "daily_loss"} <= set(ids)
        persisted = count(world.engine_b, "trade_proposal_risk_check")
        assert persisted == len(checks)
        proposals_before = count(world.engine_b, "trade_proposal")

        refusals: dict[str, str] = {}

        def refused(label: str, mutate: Any, restore: Any, fragment: str) -> None:
            mutate()
            with pytest.raises(V1PaperCandidateRefusedError) as raised:
                stack.prepare()
            restore()
            assert fragment in str(raised.value), str(raised.value)
            refusals[label] = str(raised.value)

        refused(
            "wide_spread",
            lambda: ex.set_quote("95.00", "100.00"),
            lambda: ex.set_quote("99.98", "100.00"),
            "spread",
        )
        refused(
            "stale_quote",
            lambda: setattr(ex, "quote_age_seconds", 300.0),
            lambda: setattr(ex, "quote_age_seconds", 1.0),
            "market_data_age",
        )
        refused(
            "market_closed",
            lambda: setattr(ex, "market_open", False),
            lambda: setattr(ex, "market_open", True),
            "market is closed",
        )
        refused(
            "price_out_of_bounds",
            lambda: ex.set_quote("1499.00", "1500.00"),
            lambda: ex.set_quote("99.98", "100.00"),
            "price_bounds",
        )
        assert count(world.engine_b, "trade_proposal") == proposals_before
        assert buy_posts(ex) == []
    evidence.record(
        checks_performed=len(checks),
        check_ids=ids,
        all_passed=True,
        risk_check_rows_persisted=persisted,
        negative_controls=refusals,
        proposals_written_by_refused_prepares=0,
        orders_posted=0,
    )


def close_position_by_stop(world: World, stack: Stack, intent_id: str) -> None:
    """Drive the real manager through a STOP exit until the position is closed AND verified."""
    ex = world.exchange
    ex.set_quote("98.90", "99.00")
    stack.tick()
    attempt = stack.exit_attempts(intent_id)[-1]
    ex.fill(attempt.client_order_id, attempt.quantity, "98.90")
    stack.tick()
    assert stack.exit_attempts(intent_id)[-1].closed_position_verified_at is not None
    ex.set_quote("99.98", "100.00")


def blocked_excerpt(message: str) -> str:
    """Just the refusal sentence (not the page chrome around it)."""
    page = re.search(r"Execution blocked: (.*?) No order was sent", message)
    if page:
        return page.group(1).replace("&gt;", ">")
    stored = message.find("execution is blocked:")
    return (message[stored:] if stored >= 0 else message)[:300]


def test_ACC_04b_d1_portfolio_limits_refuse_at_the_submission_boundary(
    world: World, evidence: EvidenceRecorder
) -> None:
    """ACC-04b (NEW CONTROL D1) -- daily loss, daily order count, simultaneous positions and
    total exposure are judged at the PAPER submission boundary on FRESH broker reads: a
    candidate that passed Prepare is refused at confirm when the account moved, with ZERO
    BUY orders reaching the wire -- while an EXIT is never blocked by any of these limits."""
    ex = world.exchange
    scenarios: dict[str, Any] = {}

    def refused_at_boundary(
        stack: Stack, label: str, expected: str, mutate: Any, undo: Any
    ) -> None:
        proposal_id = stack.prepare().proposal.proposal_governance_id
        buys_before = len(buy_posts(ex))
        mutate()
        message = approve_refused(stack, proposal_id)
        undo()
        assert expected in message, message
        assert len(buy_posts(ex)) == buys_before, "a BUY reached the wire despite the refusal"
        attempt = stack.entry_attempt(proposal_id)
        scenarios[label] = {
            "proposal_id": proposal_id,
            "refusal": blocked_excerpt(message),
            "buy_orders_on_wire": len(buy_posts(ex)),
            "attempt_state": None if attempt is None else attempt.state.value,
        }

    with world.stack() as stack:
        # 1. daily loss
        refused_at_boundary(
            stack,
            "daily_loss",
            "daily loss limit reached",
            lambda: setattr(ex, "equity", ex.last_equity - Decimal(600)),
            lambda: setattr(ex, "equity", ex.last_equity),
        )
        # 2. simultaneous positions (limit 1; an unrelated holding appears after Prepare)
        world.save_configuration(
            v1_configuration(configuration_version=2, maximum_simultaneous_positions=1)
        )
        refused_at_boundary(
            stack,
            "position_count",
            "simultaneous position limit reached",
            lambda: ex.seed_position("MSFT", 1, "50"),
            lambda: ex.positions.clear(),
        )
        # 3. total exposure (limit 500; an unrelated holding worth ~200 + this 400 order)
        world.save_configuration(
            v1_configuration(configuration_version=3, maximum_deployable_capital=Decimal("500"))
        )
        refused_at_boundary(
            stack,
            "total_exposure",
            "total exposure limit reached",
            lambda: ex.seed_position("MSFT", 2, "50"),
            lambda: ex.positions.clear(),
        )
        # 4. daily order count (limit 1): two candidates prepared while the count is still 0;
        #    the first is sent, filled and fully closed; the second is then refused on count.
        world.save_configuration(
            v1_configuration(configuration_version=4, maximum_daily_order_count=1)
        )
        first = stack.prepare().proposal.proposal_governance_id
        second = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(first).code == 303
        first_attempt = stack.entry_attempt(first)
        assert first_attempt is not None
        ex.fill(first_attempt.client_order_id, 4, "100.00")
        stack.refresh()
        first_intent = stack.repositories.intents.for_proposal(first)
        assert first_intent is not None
        close_position_by_stop(world, stack, first_intent.intent_governance_id)
        assert ex.positions == {} and ex.open_orders() == []
        buys_before = len(buy_posts(ex))
        message = approve_refused(stack, second)
        assert "daily order count limit reached" in message, message
        assert len(buy_posts(ex)) == buys_before
        scenarios["daily_order_count"] = {
            "first_proposal": first,
            "second_proposal": second,
            "refusal": blocked_excerpt(message),
            "buy_orders_on_wire_total": len(buy_posts(ex)),
            "buy_orders_added_by_the_refused_approval": len(buy_posts(ex)) - buys_before,
        }

        # 5. EXITS ARE NOT BLOCKED: loss limit breached, position held, stop reached.
        world.save_configuration(v1_configuration(configuration_version=5))
        held = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(held).code == 303
        held_attempt = stack.entry_attempt(held)
        assert held_attempt is not None
        ex.fill(held_attempt.client_order_id, 4, "100.00")
        stack.refresh()
        held_intent = stack.repositories.intents.for_proposal(held)
        assert held_intent is not None
        ex.equity = ex.last_equity - Decimal(600)  # the daily-loss limit is now breached
        sells_before = len(sell_posts(ex))
        close_position_by_stop(world, stack, held_intent.intent_governance_id)
        assert len(sell_posts(ex)) == sells_before + 1 and ex.positions == {}
        exit_attempt = stack.exit_attempts(held_intent.intent_governance_id)[-1]
        scenarios["exit_under_breached_loss_limit"] = {
            "exit_attempt": exit_attempt.attempt_id,
            "state": exit_attempt.state.value,
            "closed_verified": exit_attempt.closed_position_verified_at is not None,
            "sell_orders_on_wire": len(sell_posts(ex)),
        }
        assert exit_attempt.state is PositionExitState.FILLED
    evidence.record(
        scenarios=scenarios,
        entry_attempt_rows=count(world.engine_b, "paper_execution_attempt"),
        admission_events=rows(
            world.engine_b,
            "SELECT count(*) AS n FROM public.paper_execution_event "
            "WHERE event_type = 'ENTRY_ADMITTED'",
        )[0]["n"],
    )


# ---------------------------------------------------------------------------------------
# ACC-05 .. ACC-07  existing positions, open orders, conflicts
# ---------------------------------------------------------------------------------------


def test_ACC_05_existing_positions_detected(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-05 -- positions the broker already holds are detected from FRESH wire reads: at
    Prepare (same symbol -> EXISTING_POSITION_CONFLICT; other symbol -> counted), at the
    submission boundary (a position that appears after Prepare), and by the exit assessment
    (a broker quantity that disagrees with the attributable fills is refused)."""
    ex = world.exchange
    with world.stack() as stack:
        broker = stack.backend._broker  # noqa: SLF001
        # (a) an external holding in the target symbol
        ex.seed_position(SYMBOL, 3, "100")
        with pytest.raises(V1PaperCandidateRefusedError) as same_symbol:
            stack.prepare()
        assert "EXISTING_POSITION_CONFLICT" in str(same_symbol.value)
        seen = [(p.symbol, p.quantity) for p in broker.fetch_all_positions()]
        assert seen == [(SYMBOL, "3")]
        ex.positions.clear()
        # (b) an unrelated holding is counted (not a conflict) by the position-count check
        ex.seed_position("MSFT", 1, "50")
        other = stack.prepare()
        position_count_detail = next(
            c.detail for c in other.proposal.risk_checks if c.check_id == "position_count"
        )
        assert position_count_detail == "1/2 positions"
        ex.positions.clear()
        # (c) a position appearing AFTER Prepare is caught at confirm, nothing is sent
        pending = stack.prepare().proposal.proposal_governance_id
        ex.seed_position(SYMBOL, 3, "100")
        late_refusal = approve_refused(stack, pending)
        assert buy_posts(ex) == []
        ex.positions.clear()
        # (d) our own filled entry: the exit assessment ties broker truth to attributed fills
        proposal_id, intent_id, quantity = world.enter_position(stack)
        assessment = stack.service.exits.assess(intent_id)
        assert assessment.eligible and assessment.snapshot.broker_position_quantity == quantity
        ex.positions[SYMBOL].qty = quantity + 5  # the broker disagrees with our records
        mismatch = stack.service.exits.assess(intent_id)
        assert not mismatch.eligible
        ex.positions[SYMBOL].qty = quantity
    evidence.record(
        external_same_symbol_refusal=str(same_symbol.value),
        broker_positions_read=seen,
        other_symbol_position_count_check=position_count_detail,
        late_position_refusal=blocked_excerpt(late_refusal),
        buy_orders_on_wire_before_own_entry=0,
        own_position={
            "proposal_id": proposal_id,
            "intent_id": intent_id,
            "broker_quantity": assessment.snapshot.broker_position_quantity,
            "entry_filled_quantity": assessment.snapshot.entry_filled_quantity,
        },
        mismatch_refusals=mismatch.refusals,
    )


def test_ACC_06_existing_open_orders_detected(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-06 -- working orders at the broker are detected from FRESH wire reads: at Prepare
    (OPEN_ORDER_CONFLICT), at the submission boundary (an order that appears after Prepare is
    folded into 'already exposed' and refuses the dispatch), and our own accepted entry is
    itself visible as a working BUY carrying our client_order_id."""
    ex = world.exchange
    with world.stack() as stack:
        broker = stack.backend._broker  # noqa: SLF001
        ex.seed_open_order(
            symbol=SYMBOL, side="buy", qty=1, limit_price="99.50", client_order_id="ext-open-1"
        )
        with pytest.raises(V1PaperCandidateRefusedError) as at_prepare:
            stack.prepare()
        assert "OPEN_ORDER_CONFLICT" in str(at_prepare.value)
        listed = [(o.client_order_id, o.side, o.quantity) for o in broker.fetch_all_open_orders()]
        assert listed == [("ext-open-1", "buy", "1")]
        ex.orders.clear()

        pending = stack.prepare().proposal.proposal_governance_id
        ex.seed_open_order(
            symbol=SYMBOL, side="buy", qty=1, limit_price="99.50", client_order_id="ext-open-2"
        )
        at_confirm = approve_refused(stack, pending)
        assert buy_posts(ex) == [] and stack.entry_attempt(pending) is None
        ex.orders.clear()

        accepted = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(accepted).code == 303
        own = stack.entry_attempt(accepted)
        assert own is not None and own.state is PaperExecutionState.PAPER_ACCEPTED
        working = [(o.client_order_id, o.side) for o in broker.fetch_all_open_orders()]
        assert working == [(own.client_order_id, "buy")]
    evidence.record(
        prepare_refusal=str(at_prepare.value),
        open_orders_read=listed,
        confirm_refusal=blocked_excerpt(at_confirm),
        buy_orders_on_wire_before_own_entry=0,
        own_entry_visible_as_working_buy=working,
    )


def test_ACC_07_conflicting_entry_refused(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-07 -- two candidates for the same symbol are prepared BEFORE either is sent (so both
    pass Prepare). The first is approved and sent; the second is then REFUSED at the submission
    boundary (working order, then held position) and exactly ONE BUY ever reaches the wire.
    Re-confirming the first is an idempotent duplicate, not a second order."""
    ex = world.exchange
    with world.stack() as stack:
        first = stack.prepare().proposal.proposal_governance_id
        second = stack.prepare().proposal.proposal_governance_id
        assert first != second
        assert stack.approve_via_route(first).code == 303
        first_attempt = stack.entry_attempt(first)
        assert (
            first_attempt is not None and first_attempt.state is PaperExecutionState.PAPER_ACCEPTED
        )
        assert len(buy_posts(ex)) == 1
        while_working = approve_refused(stack, second)
        assert len(buy_posts(ex)) == 1 and stack.entry_attempt(second) is None
        ex.fill(first_attempt.client_order_id, 4, "100.00")
        stack.refresh()
        while_held = approve_refused(stack, second, resume=True)
        assert len(buy_posts(ex)) == 1 and stack.entry_attempt(second) is None
        again = stack.approve_via_route(first, resume=True)  # a duplicate of the FIRST
        assert again.code == 303 and len(buy_posts(ex)) == 1
    evidence.record(
        first_proposal=first,
        second_proposal=second,
        first_client_order_id=first_attempt.client_order_id,
        refusal_while_first_order_working=blocked_excerpt(while_working),
        refusal_while_first_position_held=blocked_excerpt(while_held),
        buy_orders_on_wire=len(buy_posts(ex)),
        second_proposal_attempt_rows=0,
        duplicate_confirm_of_first_sent_nothing=True,
    )


# ---------------------------------------------------------------------------------------
# ACC-08 .. ACC-09  approval enforced, payload validated
# ---------------------------------------------------------------------------------------


def test_ACC_08_owner_approval_enforced(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-08 -- NO APPROVAL, NO ORDER. A prepared candidate sends nothing; an issued intent
    with no human authorization is refused by the real `SubmitAuthorizedPaperOrderHandler`; a
    forged or foreign confirmation ticket is refused by the real route; a REJECTED proposal can
    no longer be approved. Only the genuine Owner approval (positive control) reaches the wire
    -- exactly once."""
    from empirical_platform.usecases.operator_console import ConsoleRefusalError

    ex = world.exchange
    with world.stack() as stack:
        repos = stack.repositories
        backend = stack.backend
        # (a) prepared only: the card can be read, nothing is decided or sent
        prepared = stack.prepare().proposal.proposal_governance_id
        stack.service.today()
        assert count(world.engine_b, "trade_approval_decision") == 0
        assert count(world.engine_b, "paper_execution_attempt") == 0 and ex.posts() == []

        # (b) an intent exists (decision + issue) but NO authorization: the submit handler refuses
        decided = stack.prepare().proposal.proposal_governance_id
        DecidePaperBoundTradeProposalHandler(
            configurations=repos.configurations,
            decisions=repos.decisions,
            proposals=repos.proposals,
            time_bases=repos.time_bases,
            broker=backend._broker,  # noqa: SLF001
            time_source=backend._time_source,  # noqa: SLF001
        ).handle(
            DecidePaperBoundTradeProposalCommand(
                proposal_governance_id=decided,
                decision_governance_id=f"DEC-{decided}",
                action=OperatorAction.APPROVE,
                operator_identity="owner",
            )
        )
        intent = (
            IssuePaperBoundOrderIntentHandler(
                approval_decisions=repos.decisions,
                intents=repos.intents,
                proposals=repos.proposals,
                time_bases=repos.time_bases,
                broker=backend._broker,  # noqa: SLF001
                time_source=backend._time_source,  # noqa: SLF001
            )
            .handle(
                IssuePaperBoundOrderIntentCommand(
                    intent_governance_id=f"INT-{decided}",
                    proposal_governance_id=decided,
                    idempotency_key=f"IDEM-{decided}",
                )
            )
            .intent
        )
        submit = SubmitAuthorizedPaperOrderHandler(
            intents=repos.intents,
            configurations=repos.configurations,
            time_bases=repos.time_bases,
            previews=repos.previews,
            authorizations=repos.authorizations,
            attempts=repos.attempts,
            acknowledgements=repos.acknowledgements,
            events=repos.events,
            snapshots=repos.snapshots,
            broker=backend._broker,  # noqa: SLF001
            market_data=backend._market_data,  # noqa: SLF001
            kill_switch=repos.kill_switch,
            time_source=backend._time_source,  # noqa: SLF001
        )
        with pytest.raises(PaperExecutionRefusedError) as unauthorized:
            submit.handle(
                SubmitAuthorizedPaperOrderCommand(
                    intent_governance_id=intent.intent_governance_id,
                    attempt_id=f"ATT-{decided}",
                    account_snapshot_id=f"SNP-{decided}",
                    at=world.clock.now(),
                )
            )
        assert "no human authorization" in str(unauthorized.value)
        assert count(world.engine_b, "paper_execution_attempt") == 0 and ex.posts() == []

        # (c) a forged ticket, and a genuine ticket presented for ANOTHER proposal
        victim = stack.prepare().proposal.proposal_governance_id
        page = stack.review_page(victim)
        genuine_ticket, csrf = stack.ticket_of(page)
        forged = stack.client.post(
            "/confirm-approval",
            {"proposal": victim, "ticket": "forged.ticket", "csrf_token": csrf},
        )
        foreign = stack.client.post(
            "/confirm-approval",
            {"proposal": prepared, "ticket": genuine_ticket, "csrf_token": csrf},
        )
        assert forged.code >= 400 and foreign.code >= 400
        assert repos.intents.for_proposal(victim) is None
        assert repos.intents.for_proposal(prepared) is None
        assert ex.posts() == []

        # (d) a REJECTED proposal can no longer be approved, even with its old approve ticket
        rejected = stack.prepare().proposal.proposal_governance_id
        approve_ticket = stack.service.prepare_approval(rejected).ticket
        reject_ticket = stack.service.prepare_rejection(rejected).ticket
        stack.service.confirm_rejection(rejected, reject_ticket)
        with pytest.raises(ConsoleRefusalError) as after_rejection:
            stack.service.confirm_approval(rejected, approve_ticket)
        assert "rejected" in str(after_rejection.value).lower() or "Already" in str(
            after_rejection.value
        )
        assert ex.posts() == [] and repos.intents.for_proposal(rejected) is None

        # positive control: the genuine Owner approval is what finally reaches the wire, once
        control = stack.approve_via_route(victim)
        assert control.code == 303 and len(buy_posts(ex)) == 1
    evidence.record(
        prepared_only={"proposal": prepared, "decisions": 0, "attempts": 0, "orders_posted": 0},
        intent_without_authorization={
            "intent_id": intent.intent_governance_id,
            "refusal": str(unauthorized.value)[:200],
            "attempts": 0,
            "orders_posted": 0,
        },
        forged_ticket_http_status=forged.code,
        foreign_ticket_http_status=foreign.code,
        rejected_then_approve_refusal=str(after_rejection.value)[:200],
        orders_posted_before_the_genuine_approval=0,
        genuine_approval_orders_posted=len(buy_posts(ex)),
    )


def test_ACC_09_order_payload_validated(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-09 -- payloads are validated at every layer: the domain type refuses a malformed
    order; over-cap sizing is refused at Prepare; the DATABASE refuses an over-cap issued
    intent; the adapter refuses a non-request; and a broker acknowledgement that differs from
    the order sent is NOT bound to the attempt (it is recorded as UNKNOWN and reconciled)."""
    from dataclasses import replace

    ex = world.exchange
    good: dict[str, Any] = dict(
        symbol="AAPL",
        side="BUY",
        quantity=4,
        order_type=a_limit(),
        limit_price=Decimal("100"),
        time_in_force="DAY",
        extended_hours=False,
        client_order_id="m085-validation",
    )
    PaperOrderRequest(**good)  # the control is valid
    malformed: dict[str, str] = {}
    for label, override in {
        "zero_quantity": {"quantity": 0},
        "negative_quantity": {"quantity": -3},
        "bool_quantity": {"quantity": True},
        "lowercase_symbol": {"symbol": "aapl"},
        "sell_side": {"side": "SELL"},
        "gtc": {"time_in_force": "GTC"},
        "extended_hours": {"extended_hours": True},
        "limit_without_price": {"limit_price": None},
        "zero_limit_price": {"limit_price": Decimal("0")},
        "empty_client_order_id": {"client_order_id": ""},
        "oversized_client_order_id": {"client_order_id": "x" * 200},
    }.items():
        with pytest.raises(ValueError) as refused:
            PaperOrderRequest(**{**good, **override})
        malformed[label] = str(refused.value)

    with world.stack() as stack:
        broker = stack.backend._broker  # noqa: SLF001
        with pytest.raises(ValueError, match="PaperOrderRequest"):
            broker.submit_order({"symbol": "AAPL", "qty": 1})  # type: ignore[arg-type]

        # over-cap sizing refused at Prepare (capital cap below one share; loss cap below the stop)
        over_cap: dict[str, str] = {}
        world.save_configuration(
            v1_configuration(configuration_version=2, maximum_capital_per_trade=Decimal("50"))
        )
        with pytest.raises(V1PaperCandidateRefusedError) as capital:
            stack.prepare()
        over_cap["capital_per_trade_below_one_share"] = str(capital.value)
        world.save_configuration(
            v1_configuration(
                configuration_version=3, maximum_planned_loss_per_trade=Decimal("0.50")
            )
        )
        with pytest.raises(V1PaperCandidateRefusedError) as loss:
            stack.prepare()
        over_cap["planned_loss_below_one_share_risk"] = str(loss.value)
        world.save_configuration(v1_configuration(configuration_version=4))
        assert buy_posts(ex) == [] and count(world.engine_b, "trade_proposal") == 0

        # an issued intent above the governed quantity cap (4): refused by the DOMAIN type,
        # and -- bypassing the domain with raw SQL -- by the DATABASE itself
        proposal_id = stack.prepare().proposal.proposal_governance_id
        stack.approve_via_route(proposal_id)
        intent = stack.repositories.intents.for_proposal(proposal_id)
        assert intent is not None
        with pytest.raises(ValueError) as domain_refusal:
            replace(
                intent,
                intent_governance_id="INT-TAMPERED-OVER-CAP",
                idempotency_key="IDEM-TAMPERED-OVER-CAP",
                quantity=9,
            )
        before = evidence.digest(world.engine_b, "approved_order_intent")
        with pytest.raises(DBAPIError) as db_refusal:
            with world.engine_b.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.approved_order_intent SET quantity = 9 "
                        "WHERE intent_governance_id = :i"
                    ),
                    {"i": intent.intent_governance_id},
                )
        assert evidence.digest(world.engine_b, "approved_order_intent") == before
        db_text = str(db_refusal.value.orig).splitlines()[0][:240]

    evidence.record(
        control_order_valid=True,
        malformed_refusals=malformed,
        non_request_refused_by_adapter=True,
        over_cap_prepare_refusals=over_cap,
        domain_over_cap_intent_refusal=str(domain_refusal.value),
        db_over_cap_intent_update_refusal=db_text,
        intent_table_unchanged_by_tamper=before,
    )


def a_limit() -> Any:
    from empirical_platform.decision_candidate.operator_trading_configuration import OrderType

    return OrderType.LIMIT


def test_ACC_09b_broker_acknowledgement_that_differs_is_not_trusted(
    world: World, evidence: EvidenceRecorder
) -> None:
    """ACC-09b -- the broker's answer is validated too: an acknowledgement whose quantity differs
    from the order sent is rejected by the real adapter, the attempt is NOT bound to it
    (SUBMISSION_UNKNOWN, no broker order id taken from it), exactly one order was sent, and the
    next reconciliation by client_order_id binds the REAL order."""
    ex = world.exchange
    ex.script_post("accept", ack_overrides={"qty": "1"})
    with world.stack() as stack:
        proposal_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(proposal_id).code == 303
        attempt = stack.entry_attempt(proposal_id)
        assert attempt is not None
        assert attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert attempt.broker_order_id is None and attempt.failure_code == "AMBIGUOUS"
        assert len(buy_posts(ex)) == 1
        stack.refresh()
        reconciled = stack.entry_attempt(proposal_id)
        assert reconciled is not None
        assert reconciled.state is PaperExecutionState.PAPER_ACCEPTED
        assert reconciled.broker_order_id == ex.order_by_client_id(attempt.client_order_id).id  # type: ignore[union-attr]
        assert len(buy_posts(ex)) == 1
    evidence.record(
        acknowledgement_quantity_sent_by_broker="1",
        order_quantity_sent=4,
        state_after_mismatched_ack=attempt.state,
        broker_order_id_bound_from_bad_ack=attempt.broker_order_id,
        failure_code=attempt.failure_code,
        state_after_reconcile=reconciled.state,
        broker_order_id_after_reconcile=reconciled.broker_order_id,
        buy_orders_on_wire=len(buy_posts(ex)),
    )


# ---------------------------------------------------------------------------------------
# ACC-10 .. ACC-14  order, acknowledgement, fills, position
# ---------------------------------------------------------------------------------------


def test_ACC_10_paper_order_simulated(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-10 -- an approved entry becomes exactly ONE order on the pinned PAPER endpoint:
    `confirm_approval` -> preview -> authorization -> claim -> `AlpacaPaperClient.submit_order`.
    The wire body is the exact authorized order (BUY, LIMIT, DAY, no extended hours, our
    client_order_id); credentials ride the headers only. (The 'broker' is the scripted
    exchange -- a PAPER simulation by construction.)"""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(proposal_id).code == 303
        attempt = stack.entry_attempt(proposal_id)
        assert attempt is not None and attempt.state is PaperExecutionState.PAPER_ACCEPTED
        sent = ex.posts()
        assert len(sent) == 1
        body = sent[0]
        proposal = stack.repositories.proposals.get(proposal_id)
        assert proposal is not None
        assert body == {
            "client_order_id": attempt.client_order_id,
            "extended_hours": False,
            "limit_price": "100.00000000",
            "qty": str(proposal.quantity),
            "side": "buy",
            "symbol": SYMBOL,
            "time_in_force": "day",
            "type": "limit",
        }
        assert attempt.client_order_id.startswith("m085-")
        assert ex.key_ids_seen - {""} == {_CI_PLACEHOLDER_A}
        assert not any(
            _CI_PLACEHOLDER_A in path or _CI_PLACEHOLDER_B in path for _, path, _ in ex.requests
        )
        assert not any(_CI_PLACEHOLDER_A in b or _CI_PLACEHOLDER_B in b for _, _, b in ex.requests)
        assert stack.backend._broker.endpoint_host == PAPER_ENDPOINT_HOST  # noqa: SLF001
        chain = {
            "preview_rows": count(world.engine_b, "paper_submission_preview"),
            "authorization_rows": count(world.engine_b, "paper_execution_authorization"),
            "attempt_rows": count(world.engine_b, "paper_execution_attempt"),
        }
        assert set(chain.values()) == {1}
        consumed = rows(
            world.engine_b,
            "SELECT consumed_at IS NOT NULL AS used FROM public.paper_execution_authorization",
        )
        assert consumed == [{"used": True}]
        events = [
            r["event_type"]
            for r in rows(
                world.engine_b, "SELECT event_type FROM public.paper_execution_event ORDER BY 1"
            )
        ]
    evidence.record(
        proposal_id=proposal_id,
        attempt_id=attempt.attempt_id,
        client_order_id=attempt.client_order_id,
        wire_post_body=body,
        orders_posted=len(sent),
        endpoint_host=PAPER_ENDPOINT_HOST,
        credential_key_ids_on_wire_headers=len(ex.key_ids_seen - {""}),
        credentials_in_paths_or_bodies=False,
        state=attempt.state,
        authorization_consumed=True,
        chain_row_counts=chain,
        event_types=sorted(set(events)),
    )


def test_ACC_11_broker_acknowledgement_handled(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-11 -- the broker's answer is recorded as said and drives the state machine: an
    acknowledgement saying 'new' binds the broker order id and is stored with broker_status
    'new'; the next reconciliation (the broker now says 'accepted') appends a second
    acknowledgement and updates the attempt's broker_status. Each answer is an append-only
    `paper_broker_acknowledgement` row carrying the broker order id, the client_order_id echo and
    a digest of the sanitized body."""
    ex = world.exchange
    ex.script_post("accept", ack_overrides={"status": "new"})
    with world.stack() as stack:
        proposal_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(proposal_id).code == 303
        submitted = stack.entry_attempt(proposal_id)
        assert submitted is not None and submitted.broker_status == "new"
        assert submitted.state is PaperExecutionState.PAPER_ACCEPTED
        assert submitted.broker_order_id is not None
        stack.refresh()
        accepted = stack.entry_attempt(proposal_id)
        assert accepted is not None and accepted.state is PaperExecutionState.PAPER_ACCEPTED
        assert accepted.broker_status == "accepted"
        order = ex.order_by_client_id(accepted.client_order_id)
        assert order is not None and accepted.broker_order_id == order.id
        acks = rows(
            world.engine_b,
            "SELECT kind, http_status, broker_order_id, broker_status, client_order_id_echo, "
            "payload_digest, sequence FROM public.paper_broker_acknowledgement "
            "ORDER BY sequence",
        )
        assert len(acks) >= 2 and acks[0]["kind"] == "SUBMIT" and acks[0]["http_status"] == 200
        assert {a["broker_order_id"] for a in acks} == {order.id}
        assert {a["client_order_id_echo"] for a in acks} == {accepted.client_order_id}
        assert [a["broker_status"] for a in acks][:2] == ["new", "accepted"]
        assert all(len(a["payload_digest"]) == 64 for a in acks)
    evidence.record(
        state_after_ack_new=submitted.state,
        broker_status_after_ack_new=submitted.broker_status,
        state_after_reconcile=accepted.state,
        broker_status_after_reconcile=accepted.broker_status,
        broker_order_id=accepted.broker_order_id,
        acknowledgement_rows=[
            {k: a[k] for k in ("sequence", "kind", "http_status", "broker_status")} for a in acks
        ],
        acknowledgement_digests=[a["payload_digest"] for a in acks],
        acknowledgement_table=evidence.digest(world.engine_b, "paper_broker_acknowledgement"),
    )


def test_ACC_12_partial_fill_reconciled(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-12 -- a PARTIAL fill is reconciled from the broker (never assumed): 1 of 4 shares,
    then 2 of 4 at a different price (volume-weighted average), PARTIALLY_FILLED each time;
    re-reconciling with nothing new changes nothing. The position is NOT closable-as-complete
    while the entry is still working, and no exit is invented."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(proposal_id).code == 303
        attempt = stack.entry_attempt(proposal_id)
        assert attempt is not None
        ex.fill(attempt.client_order_id, 1, "100.00")
        stack.refresh()
        first = stack.entry_attempt(proposal_id)
        assert first is not None and first.state is PaperExecutionState.PARTIALLY_FILLED
        assert first.filled_quantity == Decimal(1) and first.filled_avg_price == Decimal(100)
        ex.fill(attempt.client_order_id, 1, "100.20")
        stack.refresh()
        second = stack.entry_attempt(proposal_id)
        assert second is not None and second.state is PaperExecutionState.PARTIALLY_FILLED
        assert second.filled_quantity == Decimal(2)
        assert second.filled_avg_price == Decimal("100.10")
        digest_before = evidence.digest(world.engine_b, "paper_execution_attempt")
        stack.refresh()
        assert evidence.digest(world.engine_b, "paper_execution_attempt") == digest_before
        intent = stack.repositories.intents.for_proposal(proposal_id)
        assert intent is not None
        assessment = stack.service.exits.assess(intent.intent_governance_id)
        manager_outcomes = [
            (o.kind.value, o.detail[:120]) for o in stack.tick() if o.entry_intent_governance_id
        ]
        assert sell_posts(ex) == []
        rounds = count(world.engine_b, "paper_reconciliation_round")
    evidence.record(
        client_order_id=attempt.client_order_id,
        after_first_fill={
            "state": first.state,
            "filled": first.filled_quantity,
            "avg": first.filled_avg_price,
        },
        after_second_fill={
            "state": second.state,
            "filled": second.filled_quantity,
            "avg": second.filled_avg_price,
        },
        idempotent_re_reconcile_changed_nothing=True,
        attempt_table_digest=digest_before,
        reconciliation_rounds=rounds,
        exit_assessment_eligible_while_working=assessment.eligible,
        exit_assessment_refusals=assessment.refusals,
        plan_manager_outcomes=manager_outcomes,
        sell_orders_on_wire=0,
    )


def test_ACC_13_full_fill_reconciled(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-13 -- the remaining shares fill: the attempt becomes FILLED with the volume-weighted
    average price, a terminal_at, and from then on the row is IMMUTABLE (the database refuses
    to rewrite a terminal attempt); further reconciles are no-ops."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(proposal_id).code == 303
        attempt = stack.entry_attempt(proposal_id)
        assert attempt is not None
        ex.fill(attempt.client_order_id, 1, "100.00")
        stack.refresh()
        ex.fill(attempt.client_order_id, 1, "100.20")
        ex.fill(attempt.client_order_id, 2, "100.30")
        stack.refresh()
        final = stack.entry_attempt(proposal_id)
        assert final is not None and final.state is PaperExecutionState.FILLED
        assert final.filled_quantity == Decimal(4)
        assert final.filled_avg_price == Decimal("100.20")  # (100 + 100.2 + 2*100.3) / 4
        assert final.terminal_at is not None and final.broker_status == "filled"
        digest_before = evidence.digest(world.engine_b, "paper_execution_attempt")
        stack.refresh()
        assert evidence.digest(world.engine_b, "paper_execution_attempt") == digest_before
        with pytest.raises(DBAPIError) as rewrite:
            with world.engine_b.begin() as connection:
                connection.execute(
                    text("UPDATE public.paper_execution_attempt SET state = 'CANCELED'")
                )
        assert evidence.digest(world.engine_b, "paper_execution_attempt") == digest_before
    evidence.record(
        client_order_id=attempt.client_order_id,
        final_state=final.state,
        filled_quantity=final.filled_quantity,
        volume_weighted_average_price=final.filled_avg_price,
        terminal_at=final.terminal_at,
        broker_status=final.broker_status,
        later_reconcile_changed_nothing=True,
        terminal_row_rewrite_refused_by_database=str(rewrite.value.orig).splitlines()[0][:200],
        attempt_table_digest=digest_before,
    )


def test_ACC_14_position_recorded(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-14 -- once the entry is FILLED the position is recorded and consistent three ways:
    the durable ApprovedPlan (quantity, stop, target, liquidation deadline) in Store A, the
    exit assessment (broker position == attributable fills), and the operator's Active page
    (the managed-plan block). The plan is created by the ONE Owner approval, not afterwards."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        plan = stack.plan_for(proposal_id)
        assert plan is not None and plan.entry_intent_governance_id == intent_id
        assert plan.approved_quantity == Decimal(quantity)
        assert (plan.stop_price, plan.target_price) == (
            Decimal("99.00000000"),
            Decimal("102.00000000"),
        )
        assert plan.triggered_exit_kind is None and plan.symbol == SYMBOL
        assessment = stack.service.exits.assess(intent_id)
        assert assessment.eligible and assessment.snapshot.broker_position_quantity == quantity
        assert assessment.snapshot.entry_filled_quantity == Decimal(quantity)
        broker_position = stack.backend._broker.fetch_position(SYMBOL)  # noqa: SLF001
        assert broker_position is not None and broker_position.quantity == quantity
        active = stack.client.get("/active")
        assert active.code == 200 and "Approved plan" in active.body
        shown = stack.service.active_trades()
        assert [row.intent_id for row in shown] == [intent_id]
        plan_rows = count(world.engine_b, "approved_plan")
    evidence.record(
        proposal_id=proposal_id,
        intent_id=intent_id,
        plan={
            "plan_id": plan.plan_id,
            "quantity": plan.approved_quantity,
            "stop": plan.stop_price,
            "target": plan.target_price,
            "mandatory_liquidation_at": plan.mandatory_liquidation_at,
            "owner_approval_id": plan.owner_approval_id,
            "system_identity": plan.system_identity,
        },
        broker_position={
            "symbol": broker_position.symbol,
            "quantity": broker_position.quantity,
            "average_entry_price": broker_position.average_entry_price,
        },
        exit_assessment_eligible=assessment.eligible,
        attributable_entry_quantity=assessment.snapshot.entry_filled_quantity,
        active_page_shows_managed_plan=True,
        approved_plan_rows=plan_rows,
        approved_plan_table=evidence.digest(world.engine_b, "approved_plan"),
        positions_on_wire=ex.position_qty(SYMBOL),
    )


# ---------------------------------------------------------------------------------------
# ACC-15 .. ACC-18  stop, target, exit, duplicate exit
# ---------------------------------------------------------------------------------------


def outcome_row(outcomes: Any) -> list[tuple[str, str]]:
    return [(o.kind.value, o.detail[:200]) for o in outcomes]


def plan_row(world: World, plan_id: str) -> dict[str, Any]:
    stored = rows(
        world.engine_b, "SELECT * FROM public.approved_plan WHERE plan_id = :p", p=plan_id
    )
    assert len(stored) == 1
    return {k: (str(v) if v is not None else None) for k, v in stored[0].items()}


def test_ACC_15_stop_loss_evaluated(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-15 -- the REAL `PositionPlanManager` evaluates the Owner-approved stop on fresh
    quotes: above the stop it only MONITORS; a single-print dip that the recent quote history
    does not corroborate is NOT claimed (TRIGGER_EVIDENCE_UNCERTAIN); a genuine, sustained
    breach CLAIMS the STOP durably, persists the exact quote that drove it, and submits one
    SELL."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        plan = stack.plan_for(proposal_id)
        assert plan is not None

        ex.set_quote("99.50", "99.60")
        above = outcome_row(stack.tick())
        assert above[0][0] == PlanOutcomeKind.MONITORING.value
        assert sell_posts(ex) == [] and plan_row(world, plan.plan_id)["triggered_exit_kind"] is None

        # a flickering single print below the stop, against a history that stayed above it
        ex.set_quote("98.90", "99.00")
        ex.recent_bids = [Decimal("99.98")] * 11 + [Decimal("98.90")]
        flicker = outcome_row(stack.tick())
        assert flicker[0][0] == PlanOutcomeKind.TRIGGER_EVIDENCE_UNCERTAIN.value
        assert sell_posts(ex) == [] and plan_row(world, plan.plan_id)["triggered_exit_kind"] is None

        # a sustained breach
        ex.recent_bids = None
        breach = outcome_row(stack.tick())
        assert breach[0][0] == PlanOutcomeKind.EXIT_CLAIMED.value and "trigger=STOP" in breach[0][1]
        claimed = plan_row(world, plan.plan_id)
        assert claimed["triggered_exit_kind"] == "STOP"
        assert claimed["triggered_exit_quote_bid"] == "98.90000000"
        assert claimed["triggered_exit_quote_ask"] == "99.00000000"
        assert claimed["triggered_exit_quote_source"] == "alpaca-iex"
        assert len(sell_posts(ex)) == 1
    evidence.record(
        proposal_id=proposal_id,
        plan_id=plan.plan_id,
        stop_price=plan.stop_price,
        tick_above_stop=above,
        tick_flicker_not_corroborated=flicker,
        tick_sustained_breach=breach,
        claimed_plan_row=claimed,
        sell_orders_on_wire=len(sell_posts(ex)),
    )


def test_ACC_16_target_evaluated(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-16 -- the same manager evaluates the Owner-approved TARGET: below it, MONITORING;
    at/above it the TARGET trigger is claimed with its quote evidence and one SELL is sent."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        plan = stack.plan_for(proposal_id)
        assert plan is not None
        ex.set_quote("101.90", "101.95")
        below = outcome_row(stack.tick())
        assert below[0][0] == PlanOutcomeKind.MONITORING.value and sell_posts(ex) == []
        ex.set_quote("102.10", "102.15")
        hit = outcome_row(stack.tick())
        assert hit[0][0] == PlanOutcomeKind.EXIT_CLAIMED.value and "trigger=TARGET" in hit[0][1]
        claimed = plan_row(world, plan.plan_id)
        assert claimed["triggered_exit_kind"] == "TARGET" and len(sell_posts(ex)) == 1
        exit_attempt = stack.exit_attempts(intent_id)[-1]
        ex.fill(exit_attempt.client_order_id, quantity, "102.10")
        stack.tick()
        closed = stack.exit_attempts(intent_id)[-1]
        assert closed.state is PositionExitState.FILLED
        assert closed.closed_position_verified_at is not None and ex.positions == {}
    evidence.record(
        proposal_id=proposal_id,
        target_price=plan.target_price,
        tick_below_target=below,
        tick_at_target=hit,
        claimed_plan_row=claimed,
        exit_limit_price=sell_posts(ex)[0]["limit_price"],
        exit_state=closed.state,
        closed_position_verified_at=closed.closed_position_verified_at,
    )


def test_ACC_17_exit_submitted_in_simulation(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-17 -- a triggered exit is ONE SELL_TO_CLOSE through the real exit chain (preview ->
    authorization by the plan's system identity -> claim -> `submit_close_order`) in Store C;
    the body is exactly the authorized close; the broker fills it; the next reconciliation
    verifies the broker position at zero and stamps `closed_position_verified_at`."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        ex.set_quote("98.90", "99.00")
        claimed = outcome_row(stack.tick())
        assert claimed[0][0] == PlanOutcomeKind.EXIT_CLAIMED.value
        sells = sell_posts(ex)
        assert len(sells) == 1
        attempt = stack.exit_attempts(intent_id)[-1]
        assert sells[0] == {
            "client_order_id": attempt.client_order_id,
            "extended_hours": False,
            "limit_price": sells[0]["limit_price"],
            "qty": str(quantity),
            "side": "sell",
            "symbol": SYMBOL,
            "time_in_force": "day",
            "type": "limit",
        }
        assert attempt.client_order_id.startswith("m087-")
        assert Decimal(sells[0]["limit_price"]) <= Decimal("98.90")
        assert attempt.state is PositionExitState.ACCEPTED
        authorization = rows(
            world.engine_c, "SELECT authorized_by FROM public.position_exit_authorization"
        )
        assert len(authorization) == 1 and authorization[0]["authorized_by"] != "owner"
        ex.fill(attempt.client_order_id, quantity, "98.90")
        stack.tick()
        closed = stack.exit_attempts(intent_id)[-1]
        assert closed.state is PositionExitState.FILLED
        assert closed.closed_position_verified_at is not None
        assert ex.positions == {} and ex.open_orders() == []
        store_c = {
            t: count(world.engine_c, t)
            for t in (
                "position_exit_preview",
                "position_exit_authorization",
                "position_exit_attempt",
                "position_exit_acknowledgement",
                "position_exit_event",
            )
        }
        event_types = sorted(
            {
                r["event_type"]
                for r in rows(world.engine_c, "SELECT event_type FROM public.position_exit_event")
            }
        )
        assert "POSITION_CLOSED_VERIFIED" in event_types
    evidence.record(
        proposal_id=proposal_id,
        exit_attempt_id=attempt.attempt_id,
        exit_client_order_id=attempt.client_order_id,
        wire_post_body=sells[0],
        authorized_by=authorization[0]["authorized_by"],
        state_after_submit=PositionExitState.ACCEPTED,
        final_state=closed.state,
        filled_quantity=closed.filled_quantity,
        filled_avg_price=closed.filled_avg_price,
        closed_position_verified_at=closed.closed_position_verified_at,
        broker_position_after=0,
        store_c_row_counts=store_c,
        store_c_event_types=event_types,
    )


def test_ACC_17b_d3_unfilled_exit_is_repriced_and_replaced_within_bounds(
    world: World, evidence: EvidenceRecorder
) -> None:
    """ACC-17b (NEW CONTROL D3) -- an exit that does not fill is not abandoned and not spammed:
    nothing happens inside the minimum spacing; after it the manager CANCELS the working order,
    waits for the broker to report it canceled, and sends a replacement one concession step
    lower (new client_order_id); at most ONE sell is ever live; the concession is capped; after
    the per-session attempt budget the manager stops and raises NEEDS_ATTENTION with a durable
    EXIT_RETRIES_EXHAUSTED event. An UNCONFIRMED cancel never produces a replacement."""
    from empirical_platform.decision_candidate.position_exit import (
        EXIT_MAX_ATTEMPTS_PER_SESSION,
        EXIT_MAX_CONCESSION_BPS,
        EXIT_REPRICE_MIN_SPACING_SECONDS,
    )

    ex = world.exchange
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        ex.set_quote("98.90", "99.00")
        stack.tick()  # claim + generation 0
        assert len(sell_posts(ex)) == 1
        # inside the minimum spacing: no cancel, no replacement
        world.clock.advance(EXIT_REPRICE_MIN_SPACING_SECONDS - 10)
        inside = outcome_row(stack.tick())
        assert len(sell_posts(ex)) == 1 and ex.count("DELETE", "/v2/orders/") == 0

        # an UNCONFIRMED cancel (broker accepts the DELETE but keeps the order working)
        ex.script_cancel("ignore")
        world.clock.advance(15)
        unconfirmed = outcome_row(stack.tick())
        assert len(sell_posts(ex)) == 1 and len(ex.open_orders()) == 1
        ex.script_cancel("cancel")

        limits = [Decimal(sell_posts(ex)[0]["limit_price"])]
        live_counts = [len(ex.open_orders())]
        outcomes: list[Any] = []
        for _ in range(EXIT_MAX_ATTEMPTS_PER_SESSION + 3):
            world.clock.advance(EXIT_REPRICE_MIN_SPACING_SECONDS + 1)
            outcomes.append(outcome_row(stack.tick()))
            live_counts.append(len([o for o in ex.open_orders() if o.side == "sell"]))
            limits = [Decimal(p["limit_price"]) for p in sell_posts(ex)]
        assert len(sell_posts(ex)) == EXIT_MAX_ATTEMPTS_PER_SESSION
        assert max(live_counts) <= 1, "more than one live SELL at once"
        assert limits == sorted(limits, reverse=True) and len(set(limits)) == len(limits)
        floor = Decimal("98.90") * (1 - Decimal(EXIT_MAX_CONCESSION_BPS) / Decimal(10_000))
        assert min(limits) >= floor.quantize(Decimal("0.01")) - Decimal("0.01")
        client_ids = [p["client_order_id"] for p in sell_posts(ex)]
        assert len(set(client_ids)) == len(client_ids)
        last = outcomes[-1]
        assert any(kind == PlanOutcomeKind.NEEDS_ATTENTION.value for kind, _ in last), last
        exhausted = rows(
            world.engine_c,
            "SELECT count(*) AS n FROM public.position_exit_event "
            "WHERE event_type = 'EXIT_RETRIES_EXHAUSTED'",
        )[0]["n"]
        assert exhausted >= 1
        attempts = stack.exit_attempts(intent_id)
        states = [a.state.value for a in attempts]
        sells_at_end = len(sell_posts(ex))
        world.clock.advance(300)
        stack.tick()
        assert len(sell_posts(ex)) == sells_at_end, "a sell was sent after the budget was spent"
    evidence.record(
        generations_sent=len(client_ids),
        attempt_budget=EXIT_MAX_ATTEMPTS_PER_SESSION,
        limit_prices=limits,
        concession_floor=floor.quantize(Decimal("0.01")),
        sell_client_order_ids=client_ids,
        max_live_sells_at_any_tick=max(live_counts),
        tick_inside_minimum_spacing=inside,
        tick_with_unconfirmed_cancel=unconfirmed,
        final_tick=last,
        exit_attempt_states=states,
        retries_exhausted_events=exhausted,
        sells_sent_after_budget_spent=0,
        cancels_sent=ex.count("DELETE", "/v2/orders/"),
    )


def test_ACC_17c_mandatory_liquidation_exit_is_submitted_and_reconciled(
    world: World, evidence: EvidenceRecorder
) -> None:
    """ACC-17c -- the time-driven exit: at the plan's mandatory-liquidation deadline the manager
    claims MANDATORY_EXIT (no price consulted), sends one SELL, reconciles it tick after tick,
    reprices an unfilled one on the shorter mandatory spacing, and ends verified closed.

    REGRESSION for a real defect this matrix found: the attempt id of a plan-minted
    MANDATORY_EXIT is 63 characters, so the acknowledgement id `XACK-<attempt>-<n>[:64]` and the
    reconciliation-round id `XRND-<attempt>-<n>[:64]` lost their sequence and the SECOND
    acknowledgement / round of that attempt collided with the first on the primary key -- every
    reconcile of a mandatory liquidation raised (and, unhandled, aborted the whole manager tick
    for every other plan too)."""
    ex = world.exchange
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        plan = stack.plan_for(proposal_id)
        assert plan is not None
        before_deadline = outcome_row(stack.tick())
        assert before_deadline[0][0] == PlanOutcomeKind.MONITORING.value
        assert sell_posts(ex) == []
        world.clock.advance((plan.mandatory_exit_deadline - world.clock.now()).total_seconds() + 5)
        claimed = outcome_row(stack.tick())
        assert claimed[0][0] == PlanOutcomeKind.EXIT_CLAIMED.value
        assert "trigger=MANDATORY_EXIT" in claimed[0][1], claimed
        assert len(sell_posts(ex)) == 1
        attempt = stack.exit_attempts(intent_id)[-1]
        assert len(attempt.attempt_id) == 63
        for _ in range(2):  # every further tick appends another acknowledgement and round
            stack.tick()
        assert len(sell_posts(ex)) == 1
        # unfilled past the (shorter, 15 s) mandatory spacing: cancel -> confirm -> replace
        world.clock.advance(16)
        replaced = outcome_row(stack.tick())
        assert any(kind == PlanOutcomeKind.EXIT_SUBMITTED.value for kind, _ in replaced), replaced
        assert len(sell_posts(ex)) == 2 and len(ex.open_orders()) == 1
        generations = stack.exit_attempts(intent_id)
        assert [a.state for a in generations][0] is PositionExitState.CANCELED
        replacement = generations[-1]
        ex.fill(replacement.client_order_id, quantity, "99.85")
        stack.tick()
        closed = stack.exit_attempts(intent_id)[-1]
        assert closed.attempt_id == replacement.attempt_id
        assert closed.state is PositionExitState.FILLED
        assert closed.closed_position_verified_at is not None
        assert len(sell_posts(ex)) == 2 and ex.positions == {}
        ack_ids = [
            r["acknowledgement_id"]
            for r in rows(
                world.engine_c,
                "SELECT acknowledgement_id FROM public.position_exit_acknowledgement "
                "ORDER BY sequence",
            )
        ]
        assert len(ack_ids) >= 4 and len(set(ack_ids)) == len(ack_ids)
        assert all(len(i) <= 64 for i in ack_ids)
        claimed_row = plan_row(world, plan.plan_id)
        assert claimed_row["triggered_exit_kind"] == "MANDATORY_EXIT"
        assert claimed_row["triggered_exit_quote_bid"] is None  # time-only: no quote consulted
    evidence.record(
        mandatory_exit_deadline=plan.mandatory_exit_deadline,
        tick_before_deadline=before_deadline,
        tick_at_deadline=claimed,
        attempt_id=attempt.attempt_id,
        attempt_id_length=len(attempt.attempt_id),
        tick_after_mandatory_spacing=replaced,
        sell_orders_on_wire=2,
        generation_states=[a.state for a in generations],
        final_state=closed.state,
        closed_position_verified_at=closed.closed_position_verified_at,
        acknowledgement_ids=ack_ids,
        acknowledgement_ids_all_distinct=True,
        claimed_plan_row_quote_fields=[
            claimed_row["triggered_exit_quote_bid"],
            claimed_row["triggered_exit_quote_source"],
        ],
    )


def test_ACC_18_duplicate_exit_prevented(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-18 -- there is never a second live exit: (a) repeated manager ticks while an exit
    works send nothing; (b) the Owner's manual exit while the manager's exit is live is refused
    and re-submitting a confirmed manual ticket is an idempotent duplicate; (c) the manager
    refuses to add a second exit on top of a manual one; (d) two manager instances racing the
    same trigger on two real connections produce exactly ONE SELL."""
    ex = world.exchange
    # ---- (a) + (b): manager first, then the Owner tries --------------------------------
    with world.stack() as stack:
        proposal_id, intent_id, quantity = world.enter_position(stack)
        ex.set_quote("98.90", "99.00")
        stack.tick()
        for _ in range(3):
            stack.tick()
        assert len(sell_posts(ex)) == 1
        from empirical_platform.usecases.operator_console import ConsoleRefusalError

        with pytest.raises(ConsoleRefusalError) as manual_review:
            stack.service.exits.review(intent_id)
        assert len(sell_posts(ex)) == 1
        review_refusal = str(manual_review.value)
        live = stack.exit_attempts(intent_id)
        assert len(live) == 1
        index_rows = rows(
            world.engine_c,
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = 'position_exit_attempt' AND indexdef ILIKE '%UNIQUE%'",
        )

    # ---- (c): manual exit first, then the manager ---------------------------------------
    ex.fill(live[0].client_order_id, quantity, "98.90")
    with world.stack() as stack:
        stack.tick()  # verifies the first position closed
    world.exchange.positions.clear()
    with world.stack() as stack:
        ex.set_quote("99.98", "100.00")
        second_proposal, second_intent, second_quantity = world.enter_position(stack)
        sells_before = len(sell_posts(ex))
        review = stack.client.get(f"/exit/review?intent={second_intent}")
        assert review.code == 200, review.body[:300]
        ticket, csrf = stack.ticket_of(review)
        confirmed = stack.client.post(
            "/exit/confirm", {"intent": second_intent, "ticket": ticket, "csrf_token": csrf}
        )
        assert confirmed.code == 303 and len(sell_posts(ex)) == sells_before + 1
        ex.set_quote("98.80", "98.90")  # the stop is now also breached
        manager = outcome_row(stack.tick())
        assert len(sell_posts(ex)) == sells_before + 1, manager
        repeated = stack.client.post(
            "/exit/confirm", {"intent": second_intent, "ticket": ticket, "csrf_token": csrf}
        )
        assert repeated.code == 303 and len(sell_posts(ex)) == sells_before + 1
        manual_sell = sell_posts(ex)[-1]["client_order_id"]
        ex.fill(manual_sell, second_quantity, "98.80")
        stack.refresh()
        stack.tick()
        ex.positions.clear()

    # ---- (d): two managers, two connection pools, one trigger ----------------------------
    ex.set_quote("99.98", "100.00")
    with world.stack() as first, world.stack() as second:
        third_proposal, third_intent, third_quantity = world.enter_position(first)
        ex.set_quote("98.90", "99.00")
        sells_before = len(sell_posts(ex))
        gate = threading.Barrier(2)
        results: list[Any] = []
        errors: list[BaseException] = []

        def run(stack_: Stack) -> None:
            try:
                gate.wait(timeout=10)
                results.append(outcome_row(stack_.tick()))
            except BaseException as error:  # noqa: BLE001 - reported below
                errors.append(error)

        threads = [threading.Thread(target=run, args=(s,)) for s in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        raced = len(sell_posts(ex)) - sells_before
        assert raced == 1, f"{raced} SELL orders reached the wire from two racing managers"
        assert len(first.exit_attempts(third_intent)) == 1
        # The LOSER of the race may surface the database's uniqueness refusal on the shared,
        # deterministic preview id (the database, not the Python, is what makes the second
        # exit impossible). Nothing else may go wrong, and the next tick must be clean.
        loser_errors = [repr(e.__cause__) for e in errors]
        for text_ in loser_errors:
            assert "UniqueViolation" in text_ and "position_exit_" in text_, text_
        assert len(errors) <= 1
        quiet = outcome_row(first.tick())
        assert len(sell_posts(ex)) - sells_before == 1
    evidence.record(
        repeated_ticks_while_exit_live_extra_sells=0,
        manual_review_refused_while_manager_exit_live=review_refusal,
        unique_indexes_on_exit_attempts=[r["indexname"] for r in index_rows],
        manual_first_then_manager={
            "manager_outcome": manager,
            "second_sell_sent": False,
            "repeat_confirm_of_manual_ticket_sent_nothing": True,
        },
        racing_managers={
            "threads": 2,
            "sell_orders_on_wire": raced,
            "winner_outcomes": results,
            "loser_error_if_any": [e[:240] for e in loser_errors],
            "next_tick_after_race": quiet,
        },
    )


# ---------------------------------------------------------------------------------------
# ACC-19 .. ACC-21  rejection, connection loss, restart
# ---------------------------------------------------------------------------------------


def test_ACC_19_broker_rejection_handled(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-19 -- a definitive broker REJECTION is a terminal, recorded outcome, never retried
    behind the Owner's back: an entry the broker refuses ends REJECTED with the broker's answer
    stored, no position, no resend on re-confirm, and the plan manager has nothing to manage;
    an EXIT the broker refuses ends REJECTED and is re-armed as a NEW generation (new
    client_order_id) once the spacing allows -- position still protected, never double-sold."""
    ex = world.exchange
    with world.stack() as stack:
        # ---- entry rejected --------------------------------------------------------------
        ex.script_post(
            "reject",
            status=403,
            body={"code": 40310000, "message": "insufficient buying power"},
        )
        entry_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(entry_id).code == 303
        rejected = stack.entry_attempt(entry_id)
        assert rejected is not None and rejected.state is PaperExecutionState.REJECTED
        assert rejected.terminal_at is not None and rejected.broker_order_id is None
        assert len(buy_posts(ex)) == 1 and ex.positions == {} and ex.open_orders() == []
        again = stack.approve_via_route(entry_id, resume=True)  # the Owner presses it again
        assert again.code == 303 and len(buy_posts(ex)) == 1
        ack = rows(
            world.engine_b,
            "SELECT http_status, broker_status, sanitized_payload "
            "FROM public.paper_broker_acknowledgement WHERE attempt_id = :a",
            a=rejected.attempt_id,
        )
        assert ack and ack[0]["http_status"] == 403
        assert "insufficient buying power" in ack[0]["sanitized_payload"]
        manager_after_rejection = outcome_row(stack.tick())
        assert sell_posts(ex) == []

        # ---- exit rejected, then re-armed ----------------------------------------------------
        proposal_id, intent_id, quantity = world.enter_position(stack)
        ex.set_quote("98.90", "99.00")
        ex.script_post("reject", status=403, body={"code": 40310000, "message": "exit refused"})
        first_tick = outcome_row(stack.tick())
        first_exit = stack.exit_attempts(intent_id)[-1]
        assert first_exit.state is PositionExitState.REJECTED
        assert ex.positions[SYMBOL].qty == quantity  # still held, still to be protected
        world.clock.advance(31)
        second_tick = outcome_row(stack.tick())
        attempts = stack.exit_attempts(intent_id)
        assert len(attempts) == 2 and attempts[1].state is PositionExitState.ACCEPTED
        assert attempts[1].client_order_id != attempts[0].client_order_id
        assert len(sell_posts(ex)) == 2 and len([o for o in ex.open_orders()]) == 1
    evidence.record(
        entry_rejection={
            "attempt_id": rejected.attempt_id,
            "state": rejected.state,
            "failure_code": rejected.failure_code,
            "broker_http_status_recorded": ack[0]["http_status"],
            "broker_message_recorded": "insufficient buying power",
            "buy_orders_on_wire": 1,
            "resend_on_second_confirm": False,
            "manager_outcome": manager_after_rejection,
        },
        exit_rejection={
            "first_attempt": first_exit.attempt_id,
            "first_state": first_exit.state,
            "first_failure_code": first_exit.failure_code,
            "tick_after_rejection": first_tick,
            "tick_after_spacing": second_tick,
            "replacement_attempt": attempts[1].attempt_id,
            "replacement_state": attempts[1].state,
            "distinct_client_order_ids": True,
            "sell_orders_on_wire": len(sell_posts(ex)),
            "live_sells": 1,
        },
    )


def test_ACC_20_connection_loss_handled_without_resend(
    world: World, evidence: EvidenceRecorder
) -> None:
    """ACC-20 -- the connection drops AFTER the request left but before any answer arrived (the
    order exists at the broker): the attempt becomes SUBMISSION_UNKNOWN (never REJECTED, never
    resent); reconciliation by client_order_id binds the real order; one more confirm is a
    duplicate. Same for an exit SELL. And a connection that drops BEFORE the broker recorded
    anything is equally never resent: it stays SUBMISSION_UNKNOWN through the first
    reconciliations and is closed as NOT_FOUND_AT_BROKER only once the bounded absence policy
    (consecutive not-found rounds AND a broker-clock waiting interval) is satisfied."""
    ex = world.exchange
    with world.stack() as stack:
        # ---- entry: answer lost, order exists ------------------------------------------------
        ex.script_post("drop_after_record")
        entry_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(entry_id).code == 303
        unknown = stack.entry_attempt(entry_id)
        assert unknown is not None and unknown.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert unknown.failure_code == "AMBIGUOUS" and unknown.broker_order_id is None
        assert len(buy_posts(ex)) == 1
        duplicate = stack.approve_via_route(entry_id, resume=True)
        assert duplicate.code == 303 and len(buy_posts(ex)) == 1
        stack.refresh()
        found = stack.entry_attempt(entry_id)
        assert found is not None and found.state is PaperExecutionState.PAPER_ACCEPTED
        assert found.broker_order_id == ex.order_by_client_id(unknown.client_order_id).id  # type: ignore[union-attr]
        assert len(buy_posts(ex)) == 1
        ex.fill(found.client_order_id, 4, "100.00")
        stack.refresh()
        intent = stack.repositories.intents.for_proposal(entry_id)
        assert intent is not None
        intent_id = intent.intent_governance_id

        # ---- exit: answer lost, order exists ---------------------------------------------------
        ex.set_quote("98.90", "99.00")
        ex.script_post("drop_after_record")
        claim_tick = outcome_row(stack.tick())
        lost = stack.exit_attempts(intent_id)[-1]
        # The same poll that lost the answer already reconciled the attempt by client_order_id
        # (the manager always reconciles a claimed trigger in the same tick); what survives is
        # the durable record that the outcome WAS unknown.
        assert lost.failure_code == "AMBIGUOUS" and "RemoteDisconnected" in (
            lost.failure_detail or ""
        )
        unknown_events = [
            r["event_type"]
            for r in rows(world.engine_c, "SELECT event_type FROM public.position_exit_event")
            if "UNKNOWN" in r["event_type"]
        ]
        assert unknown_events, "the unknown outcome left no durable event"
        assert lost.state is PositionExitState.ACCEPTED and len(sell_posts(ex)) == 1
        reconcile_tick = outcome_row(stack.tick())
        recovered = stack.exit_attempts(intent_id)[-1]
        assert recovered.attempt_id == lost.attempt_id and len(sell_posts(ex)) == 1
        ex.fill(recovered.client_order_id, 4, "98.90")
        stack.tick()
        assert stack.exit_attempts(intent_id)[-1].closed_position_verified_at is not None

    # ---- entry: the connection died before the broker recorded anything -----------------------
    with world.stack() as stack:
        ex.script_post("drop_before_record")
        lonely_id = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(lonely_id).code == 303
        posts_before = len(buy_posts(ex))
        never = stack.entry_attempt(lonely_id)
        assert never is not None and never.state is PaperExecutionState.SUBMISSION_UNKNOWN
        reconcile_trace: list[str] = []
        for _ in range(4):
            world.clock.advance(60)
            stack.refresh()
            current = stack.entry_attempt(lonely_id)
            assert current is not None
            reconcile_trace.append(current.state.value)
        assert reconcile_trace[0] == "SUBMISSION_UNKNOWN", reconcile_trace  # one 404 proves nothing
        still = stack.entry_attempt(lonely_id)
        assert still is not None and ex.order_by_client_id(never.client_order_id) is None
        assert len(buy_posts(ex)) == posts_before, "the lost request was re-sent"
        resumed = stack.approve_via_route(lonely_id, resume=True)
        assert resumed.code == 303 and len(buy_posts(ex)) == posts_before
        # reads failing before the send are a fail-closed refusal: no claim, no order
        outage_id = stack.prepare().proposal.proposal_governance_id
        ex.fail_paths["/v2/account"] = 503
        rows_before = count(world.engine_b, "paper_execution_attempt")
        refused = stack.approve_via_route(outage_id)
        ex.fail_paths.clear()
        assert refused.code >= 400 and len(buy_posts(ex)) == posts_before
        assert count(world.engine_b, "paper_execution_attempt") == rows_before
        assert stack.entry_attempt(outage_id) is None
    evidence.record(
        entry_answer_lost={
            "state_after_loss": unknown.state,
            "failure_code": unknown.failure_code,
            "buy_posts": 1,
            "state_after_reconcile_by_client_order_id": found.state,
            "bound_broker_order_id": found.broker_order_id,
            "duplicate_confirm_sent_nothing": True,
        },
        exit_answer_lost={
            "failure_code_recorded": lost.failure_code,
            "failure_detail_recorded": lost.failure_detail,
            "unknown_outcome_events": unknown_events,
            "tick_that_lost_and_reconciled_it": claim_tick,
            "tick_that_reconciled": reconcile_tick,
            "state_after_reconcile": recovered.state,
            "sell_posts": 1,
            "closed_position_verified": True,
        },
        entry_never_delivered={
            "state_after_each_reconcile_a_minute_apart": reconcile_trace,
            "final_state": still.state,
            "failure_code": still.failure_code,
            "broker_has_order": False,
            "resends": 0,
        },
        broker_read_outage_before_send={
            "http_status_of_refusal": refused.code,
            "attempt_rows_added": 0,
            "buy_posts_added": 0,
        },
    )


def test_ACC_21_restart_recovery(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-21 -- every component is REBUILT from the database mid-flow (the production
    composition is exited and entered again: new connections, new repositories, new clients,
    new service, new manager) and the flow continues without a duplicate order:
      1. restart with an entry in doubt (SUBMISSION_UNKNOWN)      -> reconciled, then filled;
      2. process dies right after the exit trigger is claimed and
         BEFORE the SELL is sent                                  -> the next process resumes the
         same deterministic identities and sends exactly one SELL;
      3. restart with the SELL working                             -> filled and verified closed."""
    from empirical_platform.usecases import position_plan_manager as manager_module

    ex = world.exchange
    # ---- 1. entry in doubt across a restart ------------------------------------------------
    with world.stack() as before:
        ex.script_post("drop_after_record")
        proposal_id = before.prepare().proposal.proposal_governance_id
        assert before.approve_via_route(proposal_id).code == 303
        doubtful = before.entry_attempt(proposal_id)
        assert doubtful is not None and doubtful.state is PaperExecutionState.SUBMISSION_UNKNOWN
        first_manager_id = id(before.manager)
        digest_before = {
            t: evidence.digest(world.engine_b, t)
            for t in (
                "trade_proposal",
                "approved_order_intent",
                "paper_execution_attempt",
                "approved_plan",
            )
        }
    with world.stack() as after:  # a completely new composition: only Postgres carries over
        assert id(after.manager) != first_manager_id
        digest_after = {
            t: evidence.digest(world.engine_b, t)
            for t in (
                "trade_proposal",
                "approved_order_intent",
                "paper_execution_attempt",
                "approved_plan",
            )
        }
        assert digest_after == digest_before, "restarting changed durable state"
        assert len(buy_posts(ex)) == 1
        after.refresh()
        accepted = after.entry_attempt(proposal_id)
        assert accepted is not None and accepted.state is PaperExecutionState.PAPER_ACCEPTED
        ex.fill(accepted.client_order_id, 4, "100.00")
        after.refresh()
        assert after.entry_attempt(proposal_id).state is PaperExecutionState.FILLED  # type: ignore[union-attr]
        intent = after.repositories.intents.for_proposal(proposal_id)
        assert intent is not None
        intent_id = intent.intent_governance_id
        plan_before_crash = after.plan_for(proposal_id)
        assert plan_before_crash is not None and plan_before_crash.triggered_exit_kind is None

        # ---- 2. the process dies between the durable claim and the SELL -------------------------
        ex.set_quote("98.90", "99.00")
        real_submit = manager_module.SubmitAuthorizedPositionExitHandler.handle

        def killed(self: Any, command: Any) -> Any:
            raise RuntimeError("process killed before the SELL left")

        world.monkeypatch.setattr(
            manager_module.SubmitAuthorizedPositionExitHandler, "handle", killed
        )
        with pytest.raises(RuntimeError, match="process killed"):
            after.tick()
        world.monkeypatch.setattr(
            manager_module.SubmitAuthorizedPositionExitHandler, "handle", real_submit
        )
        assert sell_posts(ex) == []
        claimed_row = plan_row(world, plan_before_crash.plan_id)
        assert claimed_row["triggered_exit_kind"] == "STOP"  # durable, though nothing was sent
        previews_before = count(world.engine_c, "position_exit_preview")
    with world.stack() as resumed:
        outcomes = outcome_row(resumed.tick())
        assert len(sell_posts(ex)) == 1, outcomes
        working = resumed.exit_attempts(intent_id)[-1]
        assert working.state is PositionExitState.ACCEPTED
        assert working.attempt_id == f"XAT-plan-{plan_before_crash.plan_id}-STOP"
        assert count(world.engine_c, "position_exit_preview") == previews_before
        # ---- 3. restart with the SELL working ----------------------------------------------------
    ex.fill(working.client_order_id, 4, "98.90")
    with world.stack() as last:
        last.tick()
        done = last.exit_attempts(intent_id)[-1]
        assert done.state is PositionExitState.FILLED and done.closed_position_verified_at
        assert len(sell_posts(ex)) == 1 and len(buy_posts(ex)) == 1 and ex.positions == {}
    evidence.record(
        restarts=3,
        components_rebuilt_each_time=[
            "persistence services (Store A/B/C)",
            "repositories",
            "AlpacaPaperClient + AlpacaPaperMarketDataClient",
            "OperatorConsoleService + PositionExitConsole",
            "PositionPlanManager",
            "WSGI application",
        ],
        durable_state_identical_across_first_restart=digest_after,
        entry_state_before_restart=doubtful.state,
        entry_state_after_restart_reconcile=accepted.state,
        claim_survived_crash={
            "triggered_exit_kind": claimed_row["triggered_exit_kind"],
            "sells_on_wire_at_crash": 0,
        },
        resumed_tick=outcomes,
        resumed_attempt_id=working.attempt_id,
        final_exit_state=done.state,
        buy_orders_on_wire=len(buy_posts(ex)),
        sell_orders_on_wire=len(sell_posts(ex)),
    )


# ---------------------------------------------------------------------------------------
# ACC-22 .. ACC-24  kill switch, audit evidence, final reconciliation
# ---------------------------------------------------------------------------------------


def run_full_lifecycle(world: World, stack: Stack) -> dict[str, Any]:
    """prepare -> Owner approval -> partial fill -> full fill -> STOP -> unfilled exit ->
    cancel/replace (D3) -> exit fill -> position verified closed. Every step through the
    production routes/handlers; only the exchange's fills are scripted."""
    ex = world.exchange
    proposal_id = stack.prepare().proposal.proposal_governance_id
    assert stack.approve_via_route(proposal_id).code == 303
    entry = stack.entry_attempt(proposal_id)
    assert entry is not None
    ex.fill(entry.client_order_id, 1, "100.00")
    stack.refresh()
    ex.fill(entry.client_order_id, 3, "100.40")  # volume-weighted average 100.30
    stack.refresh()
    intent = stack.repositories.intents.for_proposal(proposal_id)
    assert intent is not None
    intent_id = intent.intent_governance_id
    ex.set_quote("98.90", "99.00")
    stack.tick()  # STOP claimed, generation 0 sent (and left unfilled)
    world.clock.advance(31)
    stack.tick()  # cancel confirmed by the broker, generation 1 (one concession step lower)
    replacement = stack.exit_attempts(intent_id)[-1]
    ex.fill(replacement.client_order_id, 4, "98.80")
    stack.tick()  # reconcile the fill, verify the broker position at zero
    ex.set_quote("99.98", "100.00")
    return {
        "proposal_id": proposal_id,
        "intent_id": intent_id,
        "entry_client_order_id": entry.client_order_id,
        "exit_attempt_ids": [a.attempt_id for a in stack.exit_attempts(intent_id)],
    }


def test_ACC_22_kill_switch_enforced(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-22 -- the Owner's kill switch, engaged through the real Safety route, stops every NEW
    entry (the approval is refused before anything is decided or sent) and does NOT stop a
    position-reducing exit: neither the automatic STOP exit nor the Owner's own manual exit.
    Releasing it restores entries."""
    ex = world.exchange
    with world.stack() as stack:
        held = stack.prepare().proposal.proposal_governance_id
        blocked = stack.prepare().proposal.proposal_governance_id
        assert stack.approve_via_route(held).code == 303
        held_attempt = stack.entry_attempt(held)
        assert held_attempt is not None
        ex.fill(held_attempt.client_order_id, 4, "100.00")
        stack.refresh()
        held_intent = stack.repositories.intents.for_proposal(held)
        assert held_intent is not None

        csrf = stack.client.csrf()
        engaged_reply = stack.client.post(
            "/safety/kill-switch",
            {"action": "engage", "reason": "ACC-22 drill", "csrf_token": csrf},
        )
        assert engaged_reply.code == 303
        assert stack.repositories.kill_switch.is_engaged() is True
        engaged_row = rows(world.engine_b, "SELECT * FROM public.paper_execution_kill_switch")

        # ENTRIES REFUSED
        buys_before = len(buy_posts(ex))
        refusal = approve_refused(stack, blocked)
        assert "kill switch" in refusal.lower(), refusal
        assert len(buy_posts(ex)) == buys_before
        assert stack.repositories.intents.for_proposal(blocked) is None
        assert stack.entry_attempt(blocked) is None

        # AUTOMATIC EXIT STILL GOES
        ex.set_quote("98.90", "99.00")
        outcomes = outcome_row(stack.tick())
        assert any(kind == "EXIT_CLAIMED" for kind, _ in outcomes), outcomes
        automatic = stack.exit_attempts(held_intent.intent_governance_id)[-1]
        assert len(sell_posts(ex)) == 1
        ex.fill(automatic.client_order_id, 4, "98.90")
        stack.tick()
        assert stack.exit_attempts(held_intent.intent_governance_id)[-1].closed_position_verified_at
        assert ex.positions == {}

        # RELEASE restores entries
        released = stack.client.post(
            "/safety/kill-switch",
            {"action": "release", "reason": "ACC-22 drill over", "csrf_token": csrf},
        )
        assert released.code == 303 and stack.repositories.kill_switch.is_engaged() is False
        ex.set_quote("99.98", "100.00")
        assert stack.approve_via_route(blocked).code == 303
        resumed = stack.entry_attempt(blocked)
        assert resumed is not None and resumed.state is PaperExecutionState.PAPER_ACCEPTED
        ex.fill(resumed.client_order_id, 4, "100.00")
        stack.refresh()
        second_intent = stack.repositories.intents.for_proposal(blocked)
        assert second_intent is not None

        # MANUAL EXIT STILL GOES (kill switch engaged again, the Owner closes by hand)
        stack.client.post(
            "/safety/kill-switch",
            {"action": "engage", "reason": "ACC-22 drill again", "csrf_token": csrf},
        )
        assert stack.repositories.kill_switch.is_engaged() is True
        sells_before = len(sell_posts(ex))
        review = stack.client.get(f"/exit/review?intent={second_intent.intent_governance_id}")
        assert review.code == 200, page_text(review.body)[:300]
        ticket, form_csrf = stack.ticket_of(review)
        confirm = stack.client.post(
            "/exit/confirm",
            {
                "intent": second_intent.intent_governance_id,
                "ticket": ticket,
                "csrf_token": form_csrf,
            },
        )
        assert confirm.code == 303 and len(sell_posts(ex)) == sells_before + 1
        manual = stack.exit_attempts(second_intent.intent_governance_id)[-1]
        ex.fill(manual.client_order_id, 4, "99.90")
        stack.refresh()
        stack.tick()
        closed_manual = stack.exit_attempts(second_intent.intent_governance_id)[-1]
        assert closed_manual.state is PositionExitState.FILLED
        stack.client.post(
            "/safety/kill-switch",
            {"action": "release", "reason": "ACC-22 over", "csrf_token": csrf},
        )
    evidence.record(
        engage_http_status=engaged_reply.code,
        kill_switch_table_after_engage=[
            {k: str(v) for k, v in r.items() if k != "reason"} for r in engaged_row
        ],
        entry_refusal=refusal[:240],
        buy_orders_added_while_engaged=0,
        decision_or_intent_created_while_engaged=False,
        automatic_exit_while_engaged={
            "tick": outcomes,
            "attempt": automatic.attempt_id,
            "sell_orders": 1,
            "closed_verified": True,
        },
        entry_after_release={"state": resumed.state, "client_order_id": resumed.client_order_id},
        manual_exit_while_engaged={
            "attempt": manual.attempt_id,
            "final_state": closed_manual.state,
        },
        kill_switch_events=count(world.engine_b, "paper_execution_kill_switch"),
    )


def test_ACC_23_audit_evidence_preserved(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-23 -- after a full lifecycle the audit trail exists in BOTH stores (events, attempt
    rows, broker acknowledgements, reconciliation rounds, previews, authorizations, plan), the
    database REFUSES to rewrite or delete it, and no credential or secret appears anywhere in
    it, in the pages the Owner sees, or in what this test records."""
    ex = world.exchange
    with world.stack() as stack:
        lifecycle = run_full_lifecycle(world, stack)
        trail = {
            "store_b": {
                t: count(world.engine_b, t)
                for t in (
                    "trade_proposal",
                    "trade_approval_decision",
                    "approved_order_intent",
                    "paper_submission_preview",
                    "paper_execution_authorization",
                    "paper_execution_attempt",
                    "paper_broker_acknowledgement",
                    "paper_execution_event",
                    "paper_reconciliation_round",
                    "approved_plan",
                )
            },
            "store_c": {
                t: count(world.engine_c, t)
                for t in (
                    "position_exit_preview",
                    "position_exit_authorization",
                    "position_exit_attempt",
                    "position_exit_acknowledgement",
                    "position_exit_event",
                    "position_exit_reconciliation_round",
                )
            },
        }
        assert all(n >= 1 for n in trail["store_b"].values()), trail
        assert all(n >= 1 for n in trail["store_c"].values()), trail
        entry_events = [
            r["event_type"]
            for r in rows(
                world.engine_b,
                "SELECT event_type FROM public.paper_execution_event ORDER BY occurred_at, 1",
            )
        ]
        exit_events = [
            r["event_type"]
            for r in rows(
                world.engine_c,
                "SELECT event_type FROM public.position_exit_event ORDER BY occurred_at, 1",
            )
        ]
        assert "POSITION_CLOSED_VERIFIED" in exit_events

        # the database refuses to rewrite or delete any of it
        attacks: dict[str, str] = {}
        b, c = world.engine_b, world.engine_c
        for label, engine, table, statement in (
            (
                "entry_attempt_update",
                b,
                "paper_execution_attempt",
                "UPDATE public.paper_execution_attempt SET state = 'CANCELED'",
            ),
            (
                "entry_event_update",
                b,
                "paper_execution_event",
                "UPDATE public.paper_execution_event SET event_type = 'FORGED'",
            ),
            (
                "entry_event_delete",
                b,
                "paper_execution_event",
                "DELETE FROM public.paper_execution_event",
            ),
            (
                "entry_ack_update",
                b,
                "paper_broker_acknowledgement",
                "UPDATE public.paper_broker_acknowledgement SET http_status = 200",
            ),
            (
                "entry_ack_delete",
                b,
                "paper_broker_acknowledgement",
                "DELETE FROM public.paper_broker_acknowledgement",
            ),
            ("plan_delete", b, "approved_plan", "DELETE FROM public.approved_plan"),
            (
                "exit_event_update",
                c,
                "position_exit_event",
                "UPDATE public.position_exit_event SET event_type = 'FORGED'",
            ),
            (
                "exit_event_delete",
                c,
                "position_exit_event",
                "DELETE FROM public.position_exit_event",
            ),
            (
                "exit_attempt_update",
                c,
                "position_exit_attempt",
                "UPDATE public.position_exit_attempt SET state = 'CANCELED'",
            ),
            (
                "exit_ack_delete",
                c,
                "position_exit_acknowledgement",
                "DELETE FROM public.position_exit_acknowledgement",
            ),
        ):
            digest_before = evidence.digest(engine, table)
            with pytest.raises(DBAPIError) as refused:
                with engine.begin() as connection:
                    connection.execute(text(statement))
            assert evidence.digest(engine, table) == digest_before, label
            attacks[label] = str(refused.value.orig).splitlines()[0][:160]

        # no credential anywhere: every table of both stores, the Owner's pages, the wire logs
        needles = (_CI_PLACEHOLDER_A, _CI_PLACEHOLDER_B, "APCA-API-KEY-ID", "APCA-API-SECRET-KEY")
        scanned_tables = 0
        for engine in (world.engine_b, world.engine_c):
            for table in [
                r["tablename"]
                for r in rows(
                    engine,
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
                )
            ]:
                with engine.connect() as connection:
                    dump = "\n".join(
                        r[0]
                        for r in connection.execute(
                            text(f'SELECT t::text FROM public."{table}" t')  # noqa: S608
                        )
                    )
                scanned_tables += 1
                for needle in needles:
                    assert needle not in dump, f"{needle!r} found in {table}"
        pages = [
            stack.client.get(path).body
            for path in (
                "/today",
                "/active",
                "/history",
                "/safety",
                f"/execution?intent={lifecycle['intent_id']}",
            )
        ]
        for body in pages:
            assert not any(needle in body for needle in needles)
        assert not any(_CI_PLACEHOLDER_B in p or _CI_PLACEHOLDER_B in b for _, p, b in ex.requests)
    assert not any(needle in repr(evidence.facts) for needle in needles)
    evidence.record(
        lifecycle=lifecycle,
        audit_row_counts=trail,
        entry_event_sequence=entry_events,
        exit_event_sequence=exit_events,
        rewrite_and_delete_attempts_refused_by_database=attacks,
        tables_scanned_for_credentials=scanned_tables,
        pages_scanned_for_credentials=len(pages),
        credential_found_anywhere=False,
        digests={
            "paper_execution_attempt": evidence.digest(world.engine_b, "paper_execution_attempt"),
            "paper_execution_event": evidence.digest(world.engine_b, "paper_execution_event"),
            "position_exit_attempt": evidence.digest(world.engine_c, "position_exit_attempt"),
            "position_exit_event": evidence.digest(world.engine_c, "position_exit_event"),
        },
    )


def test_ACC_24_final_state_reconciled(world: World, evidence: EvidenceRecorder) -> None:
    """ACC-24 -- after the lifecycle the three truths agree: the BROKER is flat (no position,
    no working order), the DATABASE has only terminal attempts and a verified-closed position,
    and the COUNTERS (orders today, positions held, exposure, realized result) match what
    actually crossed the wire. Further reconciliation and manager ticks change nothing, and a
    fresh Prepare reads those counters back as 1 order / 0 positions."""
    from empirical_platform.decision_candidate.paper_portfolio_limits import (
        ledger_counts_order,
        read_portfolio_evidence,
        trading_day_bounds,
    )

    ex = world.exchange
    with world.stack() as stack:
        lifecycle = run_full_lifecycle(world, stack)
        intent_id = lifecycle["intent_id"]
        broker = stack.backend._broker  # noqa: SLF001

        # 1. broker flat, read through the production client
        assert broker.fetch_all_positions() == () and broker.fetch_all_open_orders() == ()
        assert broker.fetch_position(SYMBOL) is None and ex.positions == {}
        assert ex.open_orders() == []

        # 2. database: every attempt terminal, position verified closed
        non_terminal_entries = rows(
            world.engine_b,
            "SELECT count(*) AS n FROM public.paper_execution_attempt "
            "WHERE state NOT IN ('FILLED','CANCELED','REJECTED','EXPIRED')",
        )[0]["n"]
        non_terminal_exits = rows(
            world.engine_c,
            "SELECT count(*) AS n FROM public.position_exit_attempt "
            "WHERE state NOT IN ('FILLED','CANCELED','REJECTED','EXPIRED')",
        )[0]["n"]
        assert non_terminal_entries == 0 and non_terminal_exits == 0
        entry = stack.entry_attempt(lifecycle["proposal_id"])
        assert entry is not None and entry.state is PaperExecutionState.FILLED
        exits = stack.exit_attempts(intent_id)
        states = [a.state.value for a in exits]
        assert states == ["CANCELED", "FILLED"], states
        assert exits[-1].closed_position_verified_at is not None
        plan = stack.plan_for(lifecycle["proposal_id"])
        assert plan is not None and plan.triggered_exit_kind is not None
        assert plan.triggered_exit_kind.value == "STOP"

        # 3. counters agree with the wire
        day_start, day_end = trading_day_bounds(world.clock.now())
        ledger = stack.repositories.attempts.entry_ledger(day_start=day_start, day_end=day_end)
        orders_today = sum(1 for row in ledger if ledger_counts_order(row))
        assert orders_today == len(buy_posts(ex)) == 1
        assert len(exits) == len(sell_posts(ex)) == 2
        evidence_now = read_portfolio_evidence(
            account_payload=broker.fetch_account()[1],
            positions=broker.fetch_all_positions(),
            open_orders=broker.fetch_all_open_orders(),
        )
        exposure = sum((abs(p.market_value) for p in evidence_now.positions), Decimal(0)) + sum(
            (w.notional for w in evidence_now.working_buys), Decimal(0)
        )
        assert exposure == 0 and evidence_now.positions == () and evidence_now.working_buys == ()
        realized = stack.service.exits.realized(entry, intent_id)
        expected_pnl = (Decimal("98.80") - Decimal("100.30")) * 4
        assert realized is not None
        assert realized.realized_pnl == expected_pnl and realized.quantity == 4

        # 4. a second look changes nothing
        before = {
            "b": evidence.digest(world.engine_b, "paper_execution_attempt"),
            "c": evidence.digest(world.engine_c, "position_exit_attempt"),
            "plan": evidence.digest(world.engine_b, "approved_plan"),
        }
        wire_before = len(ex.requests)
        stack.refresh()
        stack.service.exits.refresh()
        quiet = outcome_row(stack.tick())
        after = {
            "b": evidence.digest(world.engine_b, "paper_execution_attempt"),
            "c": evidence.digest(world.engine_c, "position_exit_attempt"),
            "plan": evidence.digest(world.engine_b, "approved_plan"),
        }
        assert after == before
        assert len(buy_posts(ex)) == 1 and len(sell_posts(ex)) == 2
        assert [m for m, _, _ in ex.requests[wire_before:] if m in ("POST", "DELETE")] == []

        # 5. the next Prepare reads the same counters back
        next_candidate = stack.prepare()
        readback = {
            c.check_id: c.detail
            for c in next_candidate.proposal.risk_checks
            if c.check_id
            in {"no_existing_position", "no_open_order", "position_count", "daily_order_count"}
        }
        assert readback["daily_order_count"] == "1 orders today"
        assert readback["position_count"] == "0/2 positions"
    evidence.record(
        lifecycle=lifecycle,
        broker_flat={"positions": 0, "open_orders": 0},
        entry_attempt={
            "state": entry.state,
            "filled": entry.filled_quantity,
            "avg": entry.filled_avg_price,
        },
        exit_attempt_states=states,
        closed_position_verified_at=exits[-1].closed_position_verified_at,
        non_terminal_attempts={"entry": non_terminal_entries, "exit": non_terminal_exits},
        plan_trigger=plan.triggered_exit_kind,
        counters={
            "buy_orders_on_wire": len(buy_posts(ex)),
            "entry_ledger_orders_today": orders_today,
            "sell_orders_on_wire": len(sell_posts(ex)),
            "exit_attempt_rows": len(exits),
            "exposure": exposure,
        },
        realized_result={
            "quantity": realized.quantity,
            "entry_avg": realized.entry_avg_fill_price,
            "exit_avg": realized.exit_avg_fill_price,
            "realized_pnl": realized.realized_pnl,
        },
        expected_realized_pnl=expected_pnl,
        idempotent_second_look={"digests_before": before, "digests_after": after, "tick": quiet},
        next_prepare_readback=readback,
    )
