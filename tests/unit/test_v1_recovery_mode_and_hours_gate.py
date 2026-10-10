"""V1 RELEASE -- FINAL SAFE RECOVERY HARDENING.

The deployment investigation into the real overdue AAPL exit found three remaining safety
gaps in the just-merged exit path (PR #28), none of them fixed by that PR:

1. `--capability paper-exit` always started `PlanManagerThread` with ZERO delay. There was
   no way to restart the console, for ANY reason -- including just to pick up a bug fix --
   without also re-arming the automatic manager against an already-claimed, overdue
   trigger. `--recovery-mode` (`entrypoints.operator_console`, composed by
   `_paper_position_exit_composition.paper_operator_console_with_exit_runtime`) is a
   fail-closed, read-only startup: both Stores open and every read works (`review`,
   `assess`, `refresh`, `/safety`), but `PositionPlanManager` is never built at all and
   `PositionExitConsole.confirm` refuses before touching anything.

2. `PositionExitConsole.confirm` caught `PositionExitRefusedError` but not
   `PaperTimeUncertainError` at either of its two call sites (Authorize, Submit) -- the SAME
   gap `position_plan_manager.PositionPlanManager._attempt_exit` had before PR #28. A manual
   confirm during the identical clock disagreement crashed into the generic 500 handler
   instead of a clear, recoverable refusal.

3. `SubmitAuthorizedPositionExitHandler.handle` had no regular-trading-hours gate. An exit
   -- manual OR automatic -- could be dispatched while the market was shut. The handler
   already reads `broker.fetch_clock().is_open` for the broker-timeline measurement it needs
   regardless; this pins that SAME, already-fetched flag as a fail-closed gate shared by
   both dispatch paths that call this one handler, so an overdue mandatory exit claimed
   while the market is shut cannot dispatch before the next regular session.

Every test below uses the SAME in-memory `World`/`simulation_world` harness the rest of the
M086-089/v1 exit suite already uses (`test_v1_exit_authorize_time_uncertain_repro.py`,
`test_m089_exit_quote_freshness.py`) -- no new fakes, no real network, no real Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import TestClock, World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    derive_system_identity,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.usecases.operator_console import ConsoleRefusalError
from empirical_platform.usecases.operator_console_exits import PositionExitConsole
from empirical_platform.usecases.position_plan_manager import PlanOutcomeKind, PositionPlanManager


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _intent(world: World, symbol: str) -> str:
    return f"INT-{world.proposal_id(symbol)}"


def _open_position(world: World, symbol: str = "AAPL") -> str:
    world.load_day((symbol,))
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    outcome = world.service.confirm_approval(proposal, view.ticket)
    assert outcome.sent == "sent", outcome.message
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    intent = _intent(world, symbol)
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.FILLED
    return intent


def _manager(world: World, plans: FakeApprovedPlans) -> PositionPlanManager:
    return PositionPlanManager(
        plans=plans,
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        exit_attempts=world.exits.attempts,
        previews=world.exits.previews,
        authorizations=world.exits.authorizations,
        acknowledgements=world.exits.acknowledgements,
        events=world.exits.events,
        rounds=world.exits.rounds,
        broker=world.broker,
        market_data=world.market_data,
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
    )


def _mandatory_exit_plan(world: World, intent: str) -> ApprovedPlan:
    owner_approval_id = "OWN-1"
    plan_id = "PLAN-1"
    return ApprovedPlan(
        plan_id=plan_id,
        candidate_id="CAND-1",
        entry_intent_governance_id=intent,
        symbol="AAPL",
        approved_quantity=Decimal("8"),
        stop_price=Decimal("200"),
        target_price=Decimal("999"),
        mandatory_liquidation_at=world.clock.utc,
        owner_approval_id=owner_approval_id,
        system_identity=derive_system_identity(
            plan_id=plan_id, owner_approval_id=owner_approval_id
        ),
        created_at=world.clock.utc,
    )


# ---------------------------------------------------------------------------
# 3. The regular-trading-hours gate on SubmitAuthorizedPositionExitHandler
# ---------------------------------------------------------------------------


def test_an_overdue_mandatory_exit_does_not_dispatch_while_the_market_is_shut(
    world: World,
) -> None:
    intent = _open_position(world)
    world.store.set_market_open(False)
    plans = FakeApprovedPlans()
    plan = plans.save(_mandatory_exit_plan(world, intent))
    manager = _manager(world, plans)

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert "regular trading session" in outcomes[0].detail
    assert world.exits.attempts.for_entry(intent) == (), "nothing was dispatched"
    assert [o for o in world.store.orders() if o.side == "sell"] == []
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is not None, (
        "the trigger remains claimed durably -- the next tick resumes the SAME plan rather "
        "than losing the claim because the market happened to be shut"
    )


def test_the_same_claimed_plan_dispatches_exactly_once_the_market_opens(world: World) -> None:
    intent = _open_position(world)
    world.store.set_market_open(False)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    manager = _manager(world, plans)

    first = manager.evaluate_once(now=world.clock.utc)
    assert first[0].kind is PlanOutcomeKind.NEEDS_ATTENTION

    world.store.set_market_open(True)
    world.clock.advance(15)
    second = manager.evaluate_once(now=world.clock.utc)

    assert second[0].kind is PlanOutcomeKind.EXIT_SUBMITTED
    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.authorization_id.startswith("XAU-plan-")
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1, "exactly one SELL_TO_CLOSE, never a duplicate"


def test_manual_confirm_is_also_refused_while_the_market_is_shut(world: World) -> None:
    """The gate lives in the ONE shared `SubmitAuthorizedPositionExitHandler`, so a manual
    Owner confirm is refused by the SAME check as the automatic manager -- never a separate,
    possibly-forgotten copy of the rule."""
    intent = _open_position(world)
    assert world.service.exits is not None
    review = world.service.exits.review(intent)
    world.store.set_market_open(False)

    with pytest.raises(ConsoleRefusalError, match="not dispatched outside regular hours"):
        world.service.exits.confirm(intent, review.ticket)

    assert world.exits.attempts.for_entry(intent) == ()


def test_a_normal_exit_still_dispatches_during_regular_hours(world: World) -> None:
    """Regression pin: the new gate changes nothing about the existing, fully-open-market
    round trip -- `test_m089_exit_quote_freshness.py`'s own regression case, repeated here
    next to the new gate it must not interact with."""
    intent = _open_position(world)
    assert world.service.exits is not None
    review = world.service.exits.review(intent)
    outcome = world.service.exits.confirm(intent, review.ticket)
    assert outcome.ok is True
    for _ in range(3):
        world.clock.advance(5)
        world.service.exits.refresh()
    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.position_closed
    assert world.store.position("AAPL") == 0


# ---------------------------------------------------------------------------
# 2. `confirm` handles `PaperTimeUncertainError` as a clear refusal, not a crash
# ---------------------------------------------------------------------------


@dataclass
class _LaggingTimeSource:
    """The SAME clock as `inner`, but every `read()` reports a timestamp `lag_seconds`
    BEHIND it -- modelling the real-world gap between the Owner's click (stamped by
    `clock()`, read directly) and `AuthorizePositionExitHandler`'s own fresh sample taken a
    moment later, when the two readings of "now" disagree by more than nothing."""

    inner: TestClock
    lag_seconds: float

    def read(self) -> PaperTimeReading:
        reading = self.inner.read()
        lagged = reading.utc - timedelta(seconds=self.lag_seconds)
        return PaperTimeReading(lagged, reading.monotonic)


def test_manual_confirm_during_a_clock_disagreement_is_a_clear_refusal_not_a_crash(
    world: World,
) -> None:
    intent = _open_position(world)
    assert world.service.exits is not None
    review = world.service.exits.review(intent)

    lagging_console = PositionExitConsole(
        exits=world.exits,
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        configurations=world.repositories.configurations,
        kill_switch=world.repositories.kill_switch,
        broker=world.broker,
        market_data=world.market_data,
        signer=world.signer,
        time_source=_LaggingTimeSource(world.clock, lag_seconds=5),
        clock=world.clock,
        environment="SIMULATION",
    )

    with pytest.raises(ConsoleRefusalError, match="later than this host's reading"):
        lagging_console.confirm(intent, review.ticket)

    assert world.exits.attempts.for_entry(intent) == (), "nothing was dispatched"
    assert world.exits.authorizations.latest_for_entry(intent) is None, (
        "no authorization was recorded either -- the refusal happened before anything "
        "durable was written"
    )


# ---------------------------------------------------------------------------
# 1. `--recovery-mode`: a fail-closed, read-only startup
# ---------------------------------------------------------------------------


def test_recovery_mode_confirm_refuses_before_touching_anything_review_still_works(
    world: World,
) -> None:
    intent = _open_position(world)
    recovered = world.restart(recovery_mode=True)
    assert recovered.service.exits is not None

    # Visibility is fully preserved: review, assess and reconciliation all still work.
    review = recovered.service.exits.review(intent)
    assert review.side == "SELL TO CLOSE"
    assert recovered.service.exits.assess(intent).eligible
    recovered.service.exits.refresh()  # must not raise

    with pytest.raises(ConsoleRefusalError, match="read-only recovery mode"):
        recovered.service.exits.confirm(intent, review.ticket)

    assert recovered.exits.attempts.for_entry(intent) == (), "nothing was dispatched"


def test_recovery_mode_refuses_even_when_an_authorization_already_exists(world: World) -> None:
    """Fail-closed means fail-closed regardless of how far a PRIOR process got: an unconsumed
    authorization left over from an earlier confirm that authorized successfully but could
    not submit (here, because the market closed in between) is NOT consumed, resumed or
    retried by a recovery-mode confirm -- it refuses before touching it at all."""
    intent = _open_position(world)
    assert world.service.exits is not None
    review = world.service.exits.review(intent)
    world.store.set_market_open(False)
    with pytest.raises(ConsoleRefusalError, match="not dispatched outside regular hours"):
        world.service.exits.confirm(intent, review.ticket)
    authorization = world.exits.authorizations.latest_for_entry(intent)
    assert authorization is not None and not authorization.is_consumed

    recovered = world.restart(recovery_mode=True)
    assert recovered.service.exits is not None
    with pytest.raises(ConsoleRefusalError, match="read-only recovery mode"):
        recovered.service.exits.confirm(intent, review.ticket)
    assert recovered.exits.attempts.for_entry(intent) == ()
    assert recovered.exits.authorizations.latest_for_entry(intent) == authorization, (
        "the dangling authorization is untouched -- still there, still unconsumed"
    )


def test_restart_into_and_out_of_recovery_mode_preserves_evidence_and_dispatches_once(
    world: World,
) -> None:
    """Durable evidence survives a recovery-mode restart: the SAME claimed plan and preview
    are read back unchanged, and a later NORMAL tick (market open, no recovery mode) resumes
    and completes the SAME exit exactly once -- never a second SELL because recovery mode
    was in between."""
    intent = _open_position(world)
    world.store.set_market_open(False)
    plans = FakeApprovedPlans()
    plan = plans.save(_mandatory_exit_plan(world, intent))
    manager = _manager(world, plans)

    first = manager.evaluate_once(now=world.clock.utc)
    assert first[0].kind is PlanOutcomeKind.NEEDS_ATTENTION
    preview_version = world.exits.previews.next_version_for_entry(intent)

    # "Restart" into recovery mode: read-only, nothing lost, nothing dispatched.
    recovered = world.restart(recovery_mode=True)
    assert recovered.service.exits is not None
    assert recovered.service.exits.assess(intent).eligible
    assert world.exits.previews.next_version_for_entry(intent) == preview_version, (
        "recovery mode made no write of its own"
    )
    reclaimed = plans.get(plan.plan_id)
    assert reclaimed is not None and reclaimed.triggered_exit_kind is not None

    # Market opens; a later tick on the SAME durable claim resumes and completes it once.
    world.store.set_market_open(True)
    world.clock.advance(15)
    second = manager.evaluate_once(now=world.clock.utc)[0]
    assert second.kind is PlanOutcomeKind.EXIT_SUBMITTED
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1, "exactly one SELL_TO_CLOSE across the whole recovery sequence"
