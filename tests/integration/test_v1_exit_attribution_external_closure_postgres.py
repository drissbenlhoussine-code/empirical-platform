"""RELEASE v1 EXTERNAL POSITION CLOSURE ATTRIBUTION FIX -- proven over REAL PostgreSQL,
Store B (= Store A) AND Store C, through `PositionPlanManager.evaluate_once()` exactly as the
live deployment runs it.

THE INCIDENT, REPRODUCED. An entry filled and later externally closed (a broker-dashboard
SELL this platform never dispatched), with ZERO `PositionExitAttempt` rows, wrongly counted
as a "competing" holder for a brand-new, later entry in the SAME symbol --
`AssessPositionExitHandler._competitors()` never consulted `ExternalPositionClosureRepository`.
`exit_eligibility` then refused the new entry's exit with "...attribution is ambiguous", so the
automatic `PositionPlanManager` could never dispatch its own MANDATORY_EXIT, silently, with
NOT_ELIGIBLE never surfaced anywhere.

Reuses `test_m089_paper_exit_postgres.py`'s own `_Clock` helper and `_filled_entry_attempt`'s
own real-chain shape
(copied locally as `_filled_entry`, parametrized by `PaperAccountSnapshot` id -- the original
hardcodes one id and this suite needs two real filled entries in one world), and
`test_v1_record_external_position_closure.py`'s pattern of staging a broker order directly in
the `SimulationStore` to model a sale this platform never dispatched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    CHAIN_AT,
    EVALUATED_AT,
    a_basis_at,
    a_configuration,
    a_context,
    a_proposal,
    build_engine,
    config,
    truncate_all,
)
from tests.integration._m089_support import build_engine_c, store_c_config, truncate_all_c
from tests.integration.test_m089_paper_exit_postgres import _Clock
from tests.unit._m085_fakes import a_provenance

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, derive_system_identity
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    authorize_submission,
    build_submission_preview,
    execution_policy_from_configuration,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovedOrderIntent,
    OperatorAction,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.brokerage.paper_time import BoundedInstant
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedMarketData,
    SimulatedOrder,
    SimulatedPaperBroker,
    SimulationStore,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.approved_plan_repositories import (  # noqa: E501
    PostgresApprovedPlanRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.external_position_closure_repositories import (  # noqa: E501
    PostgresExternalPositionClosureRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    PostgresPositionExitRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.operator_console_exits import ExitRepositories, PositionExitConsole
from empirical_platform.usecases.position_exit import AssessPositionExitHandler
from empirical_platform.usecases.position_plan_manager import PlanOutcomeKind, PositionPlanManager
from empirical_platform.usecases.record_external_position_closure import (
    RecordExternalPositionClosureCommand,
    RecordExternalPositionClosureHandler,
)

pytestmark = pytest.mark.integration

_OCT9 = "INT-PRP-089-PAPER-20261009T172613Z"
_OCT16 = "INT-PRP-089-PAPER-20261016T153856Z"


@pytest.fixture(scope="module")
def engine_b() -> Iterator[Engine]:
    """Store A/B at the REPOSITORY HEAD, NOT `test_m089_paper_exit_postgres.py`'s own
    `engine_b` (pinned to the earlier M085 head, which has neither the `approved_plan` table
    nor the later `v1_entry_risk_guard` trigger this suite's entries must satisfy too)."""
    yield from build_engine("head")


@pytest.fixture(scope="module")
def engine_c() -> Iterator[Engine]:
    """Store C: its own `build_engine_c()`, not imported as a fixture object from
    `test_m089_paper_exit_postgres.py` (a cross-module `@pytest.fixture` import that a lint
    auto-fix can mistake for an unused name and silently strip)."""
    yield from build_engine_c()


def _governed_configuration(configuration_id: str) -> OperatorTradingConfiguration:
    """A configuration carrying an explicit v2 risk contract -- the `v1_entry_risk_guard`
    trigger (migration `c6e2a4f8b901`, stacked before the repository head this suite's
    `engine_b` now builds) refuses any `trade_proposal`/`approved_order_intent` insert under
    a configuration without one. Mirrors `test_v1_risk_contract_postgres.py`'s own recipe."""
    return replace(
        a_configuration(configuration_governance_id=configuration_id),
        risk_contract_version=2,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=Decimal("50.00"),
    )


def _approved_intent(
    runtime: PostgresRepositoryRuntime,
    *,
    intent_id: str,
    proposal_id: str,
    context_id: str,
    watermark_id: str,
    configuration_id: str,
) -> tuple[ApprovedOrderIntent, object]:
    """`_m085_support.an_approved_intent`'s own real M084 chain, with a v2-risk-governed
    configuration (see `_governed_configuration`) instead of that helper's plain one, which
    the `v1_entry_risk_guard` trigger on this suite's head-pinned `engine_b` would refuse.
    Returns `(intent, configuration)`: the preview built from this intent must be priced by
    THIS SAME configuration's own v2-aware execution policy, never the legacy `a_policy()`."""
    configuration = _governed_configuration(configuration_id)
    runtime.operator_trading_configurations.save(configuration)
    context = a_context(runtime, configuration, context_id=context_id, watermark_id=watermark_id)
    runtime.evaluation_contexts.save(context)
    proposal = a_proposal(configuration, context, proposal_id=proposal_id)
    runtime.trade_proposals.save(proposal)
    decision = record_operator_decision(
        proposal=proposal,
        decision_governance_id=f"DEC-{proposal_id}",
        action=OperatorAction.APPROVE,
        operator_identity="owner",
        decided_at=EVALUATED_AT + timedelta(seconds=10),
        approval_expiry_seconds=configuration.approval_expiry_seconds,
    )
    runtime.approval_decisions.record(decision)
    approved = runtime.trade_proposals.set_status(
        proposal.proposal_governance_id, ProposalStatus.APPROVED
    )
    intent = build_approved_order_intent(
        intent_governance_id=intent_id,
        proposal=approved,
        decision=decision,
        created_at=EVALUATED_AT + timedelta(seconds=20),
        idempotency_key=f"IDEM-{intent_id}",
    )
    return runtime.approved_order_intents.issue(intent), configuration


def _filled_entry(
    paper: PostgresPaperExecutionRuntime,
    store: SimulationStore,
    *,
    intent_id: str,
    proposal_id: str,
    context_id: str,
    watermark_id: str,
    configuration_id: str,
    snapshot_id: str,
    filled_avg_price: str = "200.00",
) -> tuple[str, str, Decimal, Decimal]:
    """`test_m089_paper_exit_postgres._filled_entry_attempt`'s own real-chain shape, with the
    `PaperAccountSnapshot` id parametrized: that helper hardcodes `SNP-089-0001`, which
    collides (the snapshot table is append-only) the SECOND time it is called within the
    SAME world -- this test needs TWO real filled entries sharing one Store B/broker world.
    """
    with postgres_repository_runtime(config("v1-exit-attribution-chain")) as m084:
        intent, configuration = _approved_intent(
            m084,
            intent_id=intent_id,
            proposal_id=proposal_id,
            context_id=context_id,
            watermark_id=watermark_id,
            configuration_id=configuration_id,
        )
    account = paper.paper_account_snapshots.save(
        PaperAccountSnapshot(
            snapshot_id=snapshot_id,
            environment=PaperEnvironment.PAPER,
            endpoint_host=PAPER_ENDPOINT_HOST,
            account_reference="ref:v1-exit-attribution-account",
            account_status="ACTIVE",
            currency="USD",
            buying_power=Decimal("100000"),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            multiplier="4",
            shorting_enabled=True,
            trading_blocked=False,
            transfers_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            captured_at=CHAIN_AT,
        )
    )
    preview = build_submission_preview(
        preview_id=f"PVW-{intent_id}",
        intent=intent,
        account=account,
        preview_version=paper.submission_previews.next_version_for_intent(
            intent.intent_governance_id
        ),
        market_is_open=True,
        market_next_open=None,
        market_next_close=CHAIN_AT + timedelta(hours=3),
        quote_bid=Decimal("199.95"),
        quote_ask=Decimal("200.10"),
        quote_captured_at=CHAIN_AT - timedelta(seconds=5),
        quote_source="alpaca-iex",
        asset_tradable=True,
        asset_status="active",
        asset_class="us_equity",
        asset_exchange="NASDAQ",
        asset_fractionable=True,
        policy=execution_policy_from_configuration(configuration),
        existing_position_quantity=0,
        execution_kill_switch_engaged=False,
        created_at=CHAIN_AT,
        broker_now=BoundedInstant(earliest=CHAIN_AT, latest=CHAIN_AT),
        m084_provenance=a_provenance(intent),
    )
    paper.submission_previews.save(preview)
    authorization: ExecutionAuthorization = authorize_submission(
        authorization_id=f"AUT-{intent_id}",
        preview=preview,
        authorized_by="owner",
        authorized_at=CHAIN_AT,
        validity_seconds=60,
        time_basis=a_basis_at(CHAIN_AT),
    )
    paper.execution_authorizations.save(authorization)
    claim = paper.execution_attempts.claim_dispatch(
        attempt_id=f"ATT-{intent_id}",
        authorization=authorization,
        request_fingerprint_now=authorization.request_fingerprint,
        account_reference_now=authorization.account_reference,
        broker_clock=lambda: BoundedInstant(earliest=CHAIN_AT, latest=CHAIN_AT),
        claimed_at=CHAIN_AT,
    )
    assert claim.won
    paper.execution_attempts.transition(
        attempt_id=claim.attempt.attempt_id,
        target=PaperExecutionState.SUBMISSION_IN_PROGRESS,
        at=CHAIN_AT,
    )
    paper.execution_attempts.transition(
        attempt_id=claim.attempt.attempt_id,
        target=PaperExecutionState.PAPER_SUBMITTED,
        at=CHAIN_AT,
        broker_order_id=f"SIM-{intent_id}",
        broker_status="new",
    )
    filled = paper.execution_attempts.transition(
        attempt_id=claim.attempt.attempt_id,
        target=PaperExecutionState.FILLED,
        at=CHAIN_AT,
        broker_order_id=f"SIM-{intent_id}",
        broker_status="filled",
        filled_quantity=str(intent.quantity),
        filled_avg_price=filled_avg_price,
    )
    assert filled.state is PaperExecutionState.FILLED
    assert filled.filled_quantity is not None and filled.filled_quantity == Decimal(intent.quantity)
    store.add_position(intent.symbol, intent.quantity)
    return (
        intent.intent_governance_id,
        intent.symbol,
        filled.filled_quantity,
        filled.filled_avg_price,
    )


@pytest.fixture
def world(engine_b: Engine, engine_c: Engine, tmp_path: Path) -> Iterator[dict[str, object]]:
    """The SAME dual-store world `test_m089_paper_exit_postgres.py` builds, extended with
    `ApprovedPlanRepository` (Store A/B, the `approved_plan` table M090 added on the same
    database) and `ExternalPositionClosureRepository` (Store C, the RELEASE v1 table)."""
    truncate_all(engine_b)
    # `truncate_all` only knows M084/M085 tables (it predates `approved_plan`): truncate it
    # explicitly, or a plan from an earlier test in this module-scoped engine would leak into
    # the next and be evaluated against an entry that no longer exists.
    with engine_b.begin() as connection:
        connection.execute(text("TRUNCATE public.approved_plan"))
    truncate_all_c(engine_c)
    store_b_service = PostgresPersistenceService(config("v1-exit-attribution-store-b"))
    store_b_service.initialize()
    store_c_service = PostgresPersistenceService(store_c_config("v1-exit-attribution-store-c"))
    store_c_service.initialize()
    paper = PostgresPaperExecutionRuntime(store_b_service)
    exit_runtime = PostgresPositionExitRuntime(store_c_service)
    store_b_m084 = PostgresRepositoryRuntime(store_b_service)
    intents = store_b_m084.approved_order_intents
    configurations = store_b_m084.operator_trading_configurations
    plans = PostgresApprovedPlanRepository(store_b_service)
    external_closures = PostgresExternalPositionClosureRepository(store_c_service)
    store = SimulationStore(tmp_path / "broker.json")
    store.stage(scenarios={}, quotes={"AAPL": ("199.95", "200.10")})
    clock = _Clock(CHAIN_AT)
    broker = SimulatedPaperBroker(store, clock=clock)
    market_data = SimulatedMarketData(store, clock=clock)
    try:
        yield {
            "paper": paper,
            "exits": exit_runtime,
            "intents": intents,
            "configurations": configurations,
            "plans": plans,
            "external_closures": external_closures,
            "broker": broker,
            "market_data": market_data,
            "store": store,
            "clock": clock,
        }
    finally:
        store_c_service.close()
        store_b_service.close()


def _manager(world: dict[str, object]) -> PositionPlanManager:
    exits: PostgresPositionExitRuntime = world["exits"]  # type: ignore[assignment]
    return PositionPlanManager(
        plans=world["plans"],  # type: ignore[arg-type]
        external_closures=world["external_closures"],  # type: ignore[arg-type]
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=world["paper"].execution_attempts,  # type: ignore[attr-defined]
        exit_attempts=exits.attempts,
        previews=exits.previews,
        authorizations=exits.authorizations,
        acknowledgements=exits.acknowledgements,
        events=exits.events,
        rounds=exits.rounds,
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        environment="PAPER",
        time_source=world["clock"],  # type: ignore[arg-type]
    )


def _assess(world: dict[str, object], entry_intent_governance_id: str, *, at: datetime) -> object:
    return AssessPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=world["paper"].execution_attempts,  # type: ignore[attr-defined]
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        external_closures=world["external_closures"],  # type: ignore[arg-type]
        broker=world["broker"],  # type: ignore[arg-type]
    ).handle(entry_intent_governance_id, at=at)


def _plan(
    *,
    plan_id: str,
    entry_intent_governance_id: str,
    mandatory_liquidation_at: datetime,
    created_at: datetime,
) -> ApprovedPlan:
    owner_approval_id = f"DEC-{entry_intent_governance_id}"
    return ApprovedPlan(
        plan_id=plan_id,
        candidate_id=f"CAND-{plan_id}",
        entry_intent_governance_id=entry_intent_governance_id,
        symbol="AAPL",
        approved_quantity=Decimal("1"),
        stop_price=Decimal("1.00"),
        target_price=Decimal("999999.00"),
        mandatory_liquidation_at=mandatory_liquidation_at,
        owner_approval_id=owner_approval_id,
        system_identity=derive_system_identity(
            plan_id=plan_id, owner_approval_id=owner_approval_id
        ),
        created_at=created_at,
    )


def _externally_close(
    world: dict[str, object], entry_intent_governance_id: str, *, at: datetime
) -> None:
    """Models an Owner's manual broker-dashboard SELL this platform never dispatched: an
    order is staged directly in the `SimulationStore` (bypassing every Preview/Authorize/
    Submit handler), then `RecordExternalPositionClosureHandler` verifies and records it --
    the SAME path `entrypoints.record_external_position_closure` runs in production."""
    assessment = _assess(world, entry_intent_governance_id, at=at)
    quantity = assessment.snapshot.attributable_quantity
    assert quantity is not None
    client_order_id = f"EXTERNAL-SELL-{entry_intent_governance_id}"
    store: SimulationStore = world["store"]  # type: ignore[assignment]
    order = SimulatedOrder(
        broker_order_id=store.next_broker_order_id(),
        client_order_id=client_order_id,
        symbol="AAPL",
        side="sell",
        quantity=str(quantity),
        order_type="market",
        limit_price=None,
        time_in_force="day",
        extended_hours=False,
        status="filled",
        filled_quantity=str(quantity),
        filled_avg_price="229.50",
        scenario="EXIT_FILLED",
        lookups=0,
        cancel_requested=False,
        received_at=at.isoformat(),
    )
    store.put(order)
    store.reduce_position("AAPL", quantity)
    RecordExternalPositionClosureHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=world["paper"].execution_attempts,  # type: ignore[attr-defined]
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        closures=world["external_closures"],  # type: ignore[arg-type]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=world["broker"],  # type: ignore[arg-type]
    ).handle(
        RecordExternalPositionClosureCommand(
            entry_intent_governance_id=entry_intent_governance_id,
            client_order_id=client_order_id,
            recorded_by="owner",
            at=at,
        )
    )


# ---------------------------------------------------------------------------
# The full reproduction, the fix, and restart-recovery idempotence
# ---------------------------------------------------------------------------


def test_the_externally_closed_old_entry_no_longer_blocks_the_automatic_mandatory_exit(
    world: dict[str, object],
) -> None:
    clock: _Clock = world["clock"]  # type: ignore[assignment]
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]

    # Oct 9: entry approved, BUY filled.
    oct9_id, symbol, oct9_qty, _ = _filled_entry(
        paper,
        store,
        intent_id=_OCT9,
        proposal_id="PRP-089-PAPER-20261009T172613Z",
        context_id="ECX-OCT9",
        watermark_id="WM-OCT9",
        configuration_id="CFG-OCT9",
        snapshot_id="SNP-V1-EA-0001",
    )
    assert symbol == "AAPL"

    # Oct 9 entry externally sold and canonically reconciled.
    _externally_close(world, oct9_id, at=clock.at)
    assert store.position("AAPL") == 0

    # Oct 16: a third, NEW entry in the SAME symbol, BUY filled -- a fresh ApprovedPlan.
    oct16_id, _symbol, oct16_qty, _ = _filled_entry(
        paper,
        store,
        intent_id=_OCT16,
        proposal_id="PRP-089-PAPER-20261016T153856Z",
        context_id="ECX-OCT16",
        watermark_id="WM-OCT16",
        configuration_id="CFG-OCT16",
        snapshot_id="SNP-V1-EA-0002",
    )
    assert store.position("AAPL") == int(oct16_qty)

    # BEFORE THE FIX'S OWN SHAPE: without consulting the closure, `_competitors()` would
    # wrongly count the Oct 9 entry (FILLED, same symbol, no platform exit attempt) as a
    # competitor. Proven directly: the SAME assessment the manager and the manual console
    # both call is eligible, and attributes ONLY the Oct 16 entry's own shares.
    direct = _assess(world, oct16_id, at=clock.at)
    assert direct.eligible, direct.refusals
    assert direct.snapshot.competing_entry_attempt_ids == ()
    assert direct.snapshot.attributable_quantity == int(oct16_qty)

    # (a) The manual/direct console path reaches the SAME conclusion as the raw handler.
    console = PositionExitConsole(
        exits=ExitRepositories(
            previews=world["exits"].previews,  # type: ignore[attr-defined]
            authorizations=world["exits"].authorizations,  # type: ignore[attr-defined]
            attempts=world["exits"].attempts,  # type: ignore[attr-defined]
            acknowledgements=world["exits"].acknowledgements,  # type: ignore[attr-defined]
            rounds=world["exits"].rounds,  # type: ignore[attr-defined]
            events=world["exits"].events,  # type: ignore[attr-defined]
        ),
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=paper.execution_attempts,
        external_closures=world["external_closures"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        kill_switch=paper.execution_kill_switch,
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        signer=None,  # type: ignore[arg-type]
        time_source=clock,
        clock=lambda: clock.at,
        environment="PAPER",
    )
    via_console = console.assess(oct16_id)
    assert via_console.eligible
    assert via_console.snapshot.competing_entry_attempt_ids == ()

    # (c) "Overdue recovery": the deadline passes BEFORE the manager ever ticks -- exactly
    # the live incident's own shape. The plan's own deadline mirrors the entry's.
    oct16_intent = world["intents"].get(oct16_id)  # type: ignore[attr-defined]
    assert oct16_intent is not None
    plan = _plan(
        plan_id="PLAN-OCT16",
        entry_intent_governance_id=oct16_id,
        mandatory_liquidation_at=oct16_intent.mandatory_liquidation_at,
        created_at=clock.at,
    )
    world["plans"].save(plan)  # type: ignore[attr-defined]
    clock.advance((oct16_intent.mandatory_liquidation_at - clock.at).total_seconds() - 100)

    # (b) The automatic PositionPlanManager path: ONE tick claims the trigger and dispatches
    # exactly one SELL_TO_CLOSE for the Oct 16 entry only. (`evaluate_once` re-reads
    # `list_claimed_unresolved` AFTER the claim loop in the SAME call, so the newly-claimed
    # plan is also reconciled once, same tick -- both outcomes are asserted here.)
    manager = _manager(world)
    outcomes = manager.evaluate_once(now=clock.at)
    claimed = [o for o in outcomes if o.entry_intent_governance_id == oct16_id]
    assert any(o.kind is PlanOutcomeKind.EXIT_CLAIMED for o in claimed), outcomes
    assert any(o.kind is PlanOutcomeKind.EXIT_RECONCILED for o in claimed), outcomes
    assert not any(o.entry_intent_governance_id == oct9_id for o in outcomes), outcomes

    # Reconcile the fill (the simulated broker's own two-lookup progression: the previous
    # tick's reconcile was the FIRST lookup, still "accepted"; this one is the second).
    clock.advance(1)
    resolved = manager.evaluate_once(now=clock.at)
    reconciled = [o for o in resolved if o.entry_intent_governance_id == oct16_id]
    assert reconciled and reconciled[0].kind is PlanOutcomeKind.EXIT_RECONCILED, resolved

    attempts_for_oct16 = world["exits"].attempts.for_entry(oct16_id)  # type: ignore[attr-defined]
    assert len(attempts_for_oct16) == 1
    final_attempt = attempts_for_oct16[0]
    assert final_attempt.position_closed
    assert final_attempt.symbol == "AAPL"
    assert final_attempt.quantity == int(oct16_qty)
    assert store.position("AAPL") == 0

    # RESTART: a fresh PositionPlanManager instance over the SAME durable Postgres state.
    # Several more ticks, including through the fresh instance, must never dispatch a
    # second SELL: the plan is already resolved (`position_closed`), and the deterministic
    # (plan_id, kind)-derived preview/authorization/attempt identities make any further
    # attempt a pure no-op even if it were re-evaluated.
    restarted = _manager(world)
    for _ in range(3):
        clock.advance(5)
        restarted.evaluate_once(now=clock.at)
    attempts_after_restart = world["exits"].attempts.for_entry(oct16_id)  # type: ignore[attr-defined]
    assert len(attempts_after_restart) == 1
    assert attempts_after_restart[0].attempt_id == final_attempt.attempt_id
    assert store.position("AAPL") == 0

    # Attribution never crossed entries: the Oct 9 entry's own external closure is
    # untouched and still refuses a direct exit of IT unconditionally.
    oct9_direct = _assess(world, oct9_id, at=clock.at)
    assert not oct9_direct.eligible
    assert "closed externally" in oct9_direct.refusals[0]


def test_a_genuinely_still_open_old_entry_still_blocks_the_new_entrys_assessment(
    world: dict[str, object],
) -> None:
    """Regression guard for the REAL protection this fix must never weaken: an old FILLED
    entry in the same symbol, with NO platform exit attempt AND NO external closure, is
    STILL a genuine ambiguous competitor."""
    clock: _Clock = world["clock"]  # type: ignore[assignment]
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]

    old_id, _symbol, _qty, _price = _filled_entry(
        paper,
        store,
        intent_id="INT-OLD-STILL-OPEN",
        proposal_id="PRP-OLD-STILL-OPEN",
        context_id="ECX-OLD-STILL-OPEN",
        watermark_id="WM-OLD-STILL-OPEN",
        configuration_id="CFG-OLD-STILL-OPEN",
        snapshot_id="SNP-V1-EA-0003",
    )
    new_id, _symbol2, _qty2, _price2 = _filled_entry(
        paper,
        store,
        intent_id="INT-NEW-BLOCKED",
        proposal_id="PRP-NEW-BLOCKED",
        context_id="ECX-NEW-BLOCKED",
        watermark_id="WM-NEW-BLOCKED",
        configuration_id="CFG-NEW-BLOCKED",
        snapshot_id="SNP-V1-EA-0004",
    )

    direct = _assess(world, new_id, at=clock.at)
    assert not direct.eligible
    assert direct.snapshot.competing_entry_attempt_ids == (f"ATT-{old_id}",)
    assert any("ambiguous" in r for r in direct.refusals), direct.refusals

    # The SAME conclusion through the manager's own path, via a plan that would otherwise
    # be ready to fire MANDATORY_EXIT.
    new_intent = world["intents"].get(new_id)  # type: ignore[attr-defined]
    assert new_intent is not None
    plan = _plan(
        plan_id="PLAN-NEW-BLOCKED",
        entry_intent_governance_id=new_id,
        mandatory_liquidation_at=new_intent.mandatory_liquidation_at,
        created_at=clock.at,
    )
    world["plans"].save(plan)  # type: ignore[attr-defined]
    clock.advance((new_intent.mandatory_liquidation_at - clock.at).total_seconds() - 100)
    manager = _manager(world)
    outcomes = manager.evaluate_once(now=clock.at)
    matching = [o for o in outcomes if o.entry_intent_governance_id == new_id]
    assert len(matching) == 1
    assert matching[0].kind is PlanOutcomeKind.NOT_ELIGIBLE, matching[0]
    assert "ambiguous" in matching[0].detail
