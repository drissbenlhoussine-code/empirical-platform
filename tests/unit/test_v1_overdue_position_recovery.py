"""RELEASE v1 RECOVERY HARDENING -- the OVERDUE_POSITION_RECOVERY authorization path.

INCIDENT: a real AAPL PAPER position's mandatory liquidation deadline (2026-10-09 19:45
UTC) passed with the position still open. The normal manual "Review exit" / "CONFIRM
EXIT" path refused every attempt with "this exit is not authorized: the exit
authorization outlives the mandatory liquidation deadline" -- ROOT CAUSE:
`exit_authorization_binding_refusal` (decision_candidate/position_exit.py) refuses any
authorization whose `expires_at` exceeds `preview.liquidation_deadline`, unconditionally.
Once the deadline has already passed, EVERY possible authorization's `expires_at` is, by
construction, strictly later than `authorized_at`, which is itself already later than the
deadline -- so the rule becomes permanently unsatisfiable for an overdue position, by any
path, manual or automatic, forever. (`AuthorizePositionExitHandler`'s own clamp has the
identical gap: `if authorized_at < preview.liquidation_deadline: expires_at =
min(expires_at, preview.liquidation_deadline)` is simply skipped once overdue.)

A SECOND, independent defect was found investigating this, and is FIXED here IN
ISOLATION (own section below): `derive_system_identity` (decision_candidate/
approved_plan.py), used as `authorized_by` for every AUTOMATIC exit authorization,
concatenated `plan_id` and `owner_approval_id` in the open. For this exact incident's
real governance ids the result was 110 characters -- `authorized_by` is capped at 64 by
`PositionExitAuthorization.__post_init__`'s own `_require_identifier`, so the automatic
path would ALSO have raised `ValueError` the moment it tried to save an authorization,
independent of the deadline bug above. It now hashes rather than concatenates.

THE FIX, PROVEN HERE. An explicit, narrowly-scoped `OVERDUE_POSITION_RECOVERY`
authorization path, SPLIT INTO TWO STEPS (SECURITY GATE, second review pass):

1. `PositionExitConsole.grant_overdue_recovery_approval` --
   `GrantOverduePositionRecoveryApprovalHandler`. The ONE place a `recovery_approval_id`
   string becomes a REAL, durable, independently
   queryable Owner decision: re-verifies the position is overdue, an approved plan
   exists, the new id is genuinely distinct from the original `owner_approval_id`
   (never rewritten or extended), and the position is currently eligible to close
   (fresh broker re-verification) -- THEN records an event carrying the exact symbol,
   quantity and account this approval covers.
2. `PositionExitConsole.confirm_overdue_recovery` -- `AuthorizeOverduePositionRecoveryHandler`.
   Refuses outright unless a PERSISTED grant exists matching ALL of the CURRENT
   preview's symbol, quantity and account -- a distinct nonempty string alone is never
   sufficient. Identifiable ONLY by a dedicated `authorized_by` prefix
   (`derive_overdue_recovery_identity`), so `exit_authorization_binding_refusal`'s
   ORIGINAL, UNCHANGED rule keeps applying byte-for-byte to every normal, pre-deadline
   authorization (proven directly below). `AuthorizePositionExitHandler` (the shared
   NORMAL path, manual and automatic alike) now refuses outright if ever asked to mint
   an authorization carrying that reserved prefix -- the forgery question, closed
   structurally, not by convention of what today's callers happen to pass.

Every other safeguard is shared with a normal exit, unchanged: the SAME
`SubmitAuthorizedPositionExitHandler` re-verifies the broker position, the quote and the
account fresh at submit time, and the SAME `claim_dispatch` exactly-once primitive
prevents a duplicate SELL.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans, FakeExternalPositionClosures

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    derive_system_identity,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.decision_candidate.position_exit import (
    OVERDUE_RECOVERY_AUTHORIZATION_VALIDITY_SECONDS,
    OVERDUE_RECOVERY_AUTHORIZED_BY_PREFIX,
    PositionExitAuthorization,
    derive_overdue_recovery_identity,
    exit_authorization_binding_refusal,
    is_overdue_recovery_authorization,
)
from empirical_platform.usecases.operator_console import ConsoleRefusalError
from empirical_platform.usecases.operator_console_exits import PositionExitConsole
from empirical_platform.usecases.position_exit import (
    AuthorizePositionExitCommand,
    AuthorizePositionExitHandler,
    PositionExitRefusedError,
)
from empirical_platform.usecases.position_plan_manager import (
    PlanOutcomeKind,
    PositionPlanManager,
)

#: The real incident's own owner_approval_id, for realism: NOT shortened for the test.
_ORIGINAL_OWNER_APPROVAL_ID = "DEC-PRP-089-PAPER-20261009T172613Z"
_REALISTIC_RECOVERY_APPROVAL_ID = "RECOVERY-APPROVAL-2026-10-12T17-30-00Z-OWNER-VERBAL"


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


def _advance_past_deadline(world: World, intent: str, *, margin_seconds: int = 30) -> None:
    """Move the simulated clock to strictly after the entry's own mandatory deadline."""
    entry_intent = world.repositories.intents.get(intent)
    assert entry_intent is not None
    overdue_by = (entry_intent.mandatory_liquidation_at - world.clock.utc).total_seconds()
    world.clock.advance(overdue_by + margin_seconds)


def _mandatory_exit_plan(
    world: World,
    intent: str,
    *,
    plan_id: str = "PLAN-1",
    owner_approval_id: str = _ORIGINAL_OWNER_APPROVAL_ID,
) -> ApprovedPlan:
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


def _console(world: World, plans: FakeApprovedPlans | None) -> PositionExitConsole:
    return PositionExitConsole(
        exits=world.exits,
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        configurations=world.repositories.configurations,
        kill_switch=world.repositories.kill_switch,
        broker=world.broker,
        market_data=world.market_data,
        signer=world.signer,
        time_source=world.clock,
        clock=world.clock,
        environment="PAPER",
        plans=plans,
    )


def _manager(world: World, plans: FakeApprovedPlans) -> PositionPlanManager:
    return PositionPlanManager(
        plans=plans,
        external_closures=FakeExternalPositionClosures(),
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
        environment="PAPER",
        time_source=world.clock,
    )


# ---------------------------------------------------------------------------
# The precondition this fix exists for: the normal path is unsatisfiable once overdue
# ---------------------------------------------------------------------------


def test_normal_confirm_still_refuses_once_overdue_message_unchanged(world: World) -> None:
    """Regression precondition. This refusal is EXPECTED and UNCHANGED (requirement: keep
    normal pre-deadline checks unchanged) -- it is exactly why the recovery path exists."""
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    console = _console(world, FakeApprovedPlans())
    view = console.review(intent)

    with pytest.raises(ConsoleRefusalError, match="outlives the mandatory liquidation deadline"):
        console.confirm(intent, view.ticket)

    assert world.exits.attempts.for_entry(intent) == (), "nothing was sent"


# ---------------------------------------------------------------------------
# The happy path: grant, then confirm
# ---------------------------------------------------------------------------


def test_overdue_recovery_confirms_exactly_one_sell_and_closes_the_position(
    world: World,
) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)

    grant = console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL-2026-10-12")
    assert grant.entry_intent_governance_id == intent

    view = console.review(intent)
    outcome = console.confirm_overdue_recovery(intent, view.ticket, "RECOVERY-APPROVAL-2026-10-12")

    assert outcome.ok, outcome.message
    assert outcome.sent == "sent", outcome.message
    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.authorization_id.startswith("XAU-RECOVERY-")
    authorization = world.exits.authorizations.get(attempt.authorization_id)
    assert authorization is not None
    assert is_overdue_recovery_authorization(authorization)
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1, "exactly one SELL_TO_CLOSE, never a duplicate"

    # Verify broker fill and position zero, per the recovery mission's own requirement.
    for _ in range(3):
        world.clock.advance(5)
        world.service.refresh_executions()
    (attempt_after_reconcile,) = world.exits.attempts.for_entry(intent)
    assert attempt_after_reconcile.position_closed, "broker position must verify at zero"
    position = world.broker.fetch_position("AAPL")
    assert position is None or int(position.quantity) == 0

    # The original plan's own approval is untouched -- never rewritten or extended.
    plan = plans.for_entry(intent)
    assert plan is not None
    assert plan.owner_approval_id == _ORIGINAL_OWNER_APPROVAL_ID


# ---------------------------------------------------------------------------
# Confirm requires a REAL persisted grant -- a distinct nonempty string is NOT sufficient
# ---------------------------------------------------------------------------


def test_overdue_recovery_confirm_refuses_without_a_prior_grant(world: World) -> None:
    """A caller who never went through `grant_overdue_recovery_approval` at all -- just
    handing `confirm_overdue_recovery` a distinct, nonempty, never-used-before string --
    must be refused. This is the SECURITY GATE's own central claim, proven directly."""
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)
    view = console.review(intent)

    with pytest.raises(ConsoleRefusalError, match="no persisted Owner recovery approval"):
        console.confirm_overdue_recovery(intent, view.ticket, "NEVER-GRANTED-APPROVAL-ID")

    assert world.exits.attempts.for_entry(intent) == ()


def test_overdue_recovery_confirm_refuses_a_grant_for_a_different_approval_id(
    world: World,
) -> None:
    """A real, persisted grant exists -- but `confirm_overdue_recovery` is handed a
    DIFFERENT id string. Still refused: the ids, not just "a grant exists", must match."""
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)

    console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL-GRANTED")
    view = console.review(intent)

    with pytest.raises(ConsoleRefusalError, match="no persisted Owner recovery approval"):
        console.confirm_overdue_recovery(intent, view.ticket, "A-DIFFERENT-STRING-ENTIRELY")

    assert world.exits.attempts.for_entry(intent) == ()


# ---------------------------------------------------------------------------
# Narrow scope: never a shortcut for a position that is not yet overdue
# ---------------------------------------------------------------------------


def test_overdue_recovery_grant_refuses_when_not_yet_overdue(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)

    with pytest.raises(ConsoleRefusalError, match="not overdue"):
        console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL-EARLY")


def test_overdue_recovery_confirm_refuses_when_not_yet_overdue_even_with_a_valid_grant(
    world: World,
) -> None:
    """A grant can never be issued before the deadline (proven above); this proves the
    AUTHORIZE step's own, independent copy of the same narrow gate also holds, in case a
    grant is ever somehow back-dated or forged directly in storage (defense in depth)."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)
    view = console.review(intent)

    with pytest.raises(ConsoleRefusalError, match="not overdue"):
        console.confirm_overdue_recovery(intent, view.ticket, "RECOVERY-APPROVAL-EARLY")

    assert world.exits.attempts.for_entry(intent) == ()


# ---------------------------------------------------------------------------
# The fresh Owner approval must be fresh: never the original, replayed or extended
# ---------------------------------------------------------------------------


def test_overdue_recovery_grant_refuses_when_the_approval_id_replays_the_original(
    world: World,
) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)

    with pytest.raises(ConsoleRefusalError, match="distinct from"):
        console.grant_overdue_recovery_approval(intent, _ORIGINAL_OWNER_APPROVAL_ID)


def test_overdue_recovery_grant_refuses_a_blank_approval_id(world: World) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)

    with pytest.raises(ConsoleRefusalError, match="fresh, explicit Owner approval"):
        console.grant_overdue_recovery_approval(intent, "   ")


def test_overdue_recovery_grant_refuses_without_an_approved_plan(world: World) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    console = _console(world, FakeApprovedPlans())

    with pytest.raises(ConsoleRefusalError, match="no approved plan exists"):
        console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL")


# ---------------------------------------------------------------------------
# Idempotency: no duplicate SELL, whether retried deliberately or by a second click
# ---------------------------------------------------------------------------


def test_overdue_recovery_is_idempotent_no_duplicate_sell(world: World) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)
    console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL-FIRST")
    view = console.review(intent)

    first = console.confirm_overdue_recovery(intent, view.ticket, "RECOVERY-APPROVAL-FIRST")
    assert first.ok, first.message

    # A second click (same page, same ticket, same approval id): the console's own
    # active-attempt short-circuit fires before any new authorization is even considered.
    second = console.confirm_overdue_recovery(intent, view.ticket, "RECOVERY-APPROVAL-FIRST")

    assert "Already confirmed" in second.message
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1, "the second attempt must never create a second SELL"
    assert len(world.exits.attempts.for_entry(intent)) == 1


# ---------------------------------------------------------------------------
# Never available where there is no full-plan-approval concept at all (e.g. SIMULATION)
# ---------------------------------------------------------------------------


def test_overdue_recovery_grant_is_refused_when_no_plan_repository_is_wired(
    world: World,
) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    console = _console(world, plans=None)

    with pytest.raises(ConsoleRefusalError, match="not available"):
        console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL")


def test_overdue_recovery_confirm_is_refused_when_no_plan_repository_is_wired(
    world: World,
) -> None:
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    console = _console(world, plans=None)
    view = console.review(intent)

    with pytest.raises(ConsoleRefusalError, match="not available"):
        console.confirm_overdue_recovery(intent, view.ticket, "RECOVERY-APPROVAL")

    assert world.exits.attempts.for_entry(intent) == ()


# ---------------------------------------------------------------------------
# The forgery question: closed structurally, at the ONE shared normal-authorize entry point
# ---------------------------------------------------------------------------


def test_normal_authorize_refuses_the_overdue_recovery_identity_prefix_outright(
    world: World,
) -> None:
    """Neither a manual confirm nor the automatic manager can ever smuggle the recovery
    identity prefix through the NORMAL authorize path -- proven directly against the
    handler both paths share, bypassing the console entirely."""
    intent = _open_position(world)
    console = _console(world, FakeApprovedPlans())
    view = console.review(intent)
    preview = world.exits.previews.get(f"XPV-{intent}-{view.preview_version}")
    assert preview is not None

    forged_authorized_by = derive_overdue_recovery_identity(
        entry_intent_governance_id=intent, recovery_approval_id="ANYTHING"
    )
    handler = AuthorizePositionExitHandler(
        previews=world.exits.previews,
        authorizations=world.exits.authorizations,
        events=world.exits.events,
        broker=world.broker,
        kill_switch=world.repositories.kill_switch,
        time_source=world.clock,
    )

    with pytest.raises(PositionExitRefusedError, match="may not use the overdue-position"):
        handler.handle(
            AuthorizePositionExitCommand(
                authorization_id="XAU-forged-1",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by=forged_authorized_by,
                authorized_at=world.clock.utc,
            )
        )

    assert world.exits.authorizations.get("XAU-forged-1") is None


# ---------------------------------------------------------------------------
# Domain-level: the binding-refusal rule itself, both branches, in isolation
# ---------------------------------------------------------------------------


def test_binding_refusal_normal_pre_deadline_case_is_byte_for_byte_unchanged(
    world: World,
) -> None:
    """A normal (non-recovery) authorization whose `expires_at` outlives the deadline is
    refused with the EXACT original message, regardless of this fix's existence."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    console = _console(world, plans)
    view = console.review(intent)
    preview = world.exits.previews.get(f"XPV-{intent}-{view.preview_version}")
    assert preview is not None

    outlives = PositionExitAuthorization(
        authorization_id="XAU-test-outlives",
        entry_intent_governance_id=preview.entry_intent_governance_id,
        preview_id=preview.preview_id,
        preview_version=preview.preview_version,
        request_fingerprint=preview.request_fingerprint,
        preview_binding_fingerprint=preview.binding_fingerprint,
        account_reference=preview.account_reference,
        client_order_id=preview.request.client_order_id,
        symbol=preview.request.symbol,
        quantity=preview.request.quantity,
        authorized_by="owner",
        authorized_at=preview.liquidation_deadline - timedelta(seconds=10),
        expires_at=preview.liquidation_deadline + timedelta(seconds=10),
        basis_host_requested_at=preview.liquidation_deadline - timedelta(seconds=10),
        basis_host_at=preview.liquidation_deadline - timedelta(seconds=10),
        basis_broker_earliest_at=preview.liquidation_deadline - timedelta(seconds=10),
        basis_broker_latest_at=preview.liquidation_deadline - timedelta(seconds=10),
        consumed_at=None,
        consumed_by_attempt_id=None,
    )

    refusal = exit_authorization_binding_refusal(authorization=outlives, preview=preview)

    assert refusal == "the exit authorization outlives the mandatory liquidation deadline"


def test_binding_refusal_recovery_kind_requires_authorized_at_after_deadline(
    world: World,
) -> None:
    """Defense in depth: even a hand-crafted row carrying the recovery prefix is refused
    unless it was genuinely granted after the deadline -- the handler's own gate is not the
    only thing standing between a forged row and acceptance."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    console = _console(world, plans)
    view = console.review(intent)
    preview = world.exits.previews.get(f"XPV-{intent}-{view.preview_version}")
    assert preview is not None

    early_recovery = PositionExitAuthorization(
        authorization_id="XAU-RECOVERY-test-early",
        entry_intent_governance_id=preview.entry_intent_governance_id,
        preview_id=preview.preview_id,
        preview_version=preview.preview_version,
        request_fingerprint=preview.request_fingerprint,
        preview_binding_fingerprint=preview.binding_fingerprint,
        account_reference=preview.account_reference,
        client_order_id=preview.request.client_order_id,
        symbol=preview.request.symbol,
        quantity=preview.request.quantity,
        authorized_by=derive_overdue_recovery_identity(
            entry_intent_governance_id=preview.entry_intent_governance_id,
            recovery_approval_id="RECOVERY-APPROVAL",
        ),
        authorized_at=preview.liquidation_deadline - timedelta(seconds=10),
        expires_at=preview.liquidation_deadline + timedelta(seconds=10),
        basis_host_requested_at=preview.liquidation_deadline - timedelta(seconds=10),
        basis_host_at=preview.liquidation_deadline - timedelta(seconds=10),
        basis_broker_earliest_at=preview.liquidation_deadline - timedelta(seconds=10),
        basis_broker_latest_at=preview.liquidation_deadline - timedelta(seconds=10),
        consumed_at=None,
        consumed_by_attempt_id=None,
    )

    refusal = exit_authorization_binding_refusal(authorization=early_recovery, preview=preview)

    assert refusal is not None and "not actually overdue" in refusal

    late_recovery = replace(
        early_recovery,
        authorization_id="XAU-RECOVERY-test-late",
        authorized_at=preview.liquidation_deadline + timedelta(seconds=10),
        expires_at=preview.liquidation_deadline + timedelta(seconds=130),
        basis_host_requested_at=preview.liquidation_deadline + timedelta(seconds=10),
        basis_host_at=preview.liquidation_deadline + timedelta(seconds=10),
        basis_broker_earliest_at=preview.liquidation_deadline + timedelta(seconds=10),
        basis_broker_latest_at=preview.liquidation_deadline + timedelta(seconds=10),
    )
    assert exit_authorization_binding_refusal(authorization=late_recovery, preview=preview) is None


# ---------------------------------------------------------------------------
# The identity must never overflow the 64-character authorized_by limit
# ---------------------------------------------------------------------------


def test_derive_overdue_recovery_identity_stays_short_for_realistic_governance_ids() -> None:
    """The SAME class of defect independently found in `derive_system_identity` (110
    characters for this real incident's own ids, against a 64-character limit) must not
    recur here: hash rather than concatenate."""
    identity = derive_overdue_recovery_identity(
        entry_intent_governance_id="INT-PRP-089-PAPER-20261009T172613Z",
        recovery_approval_id=_REALISTIC_RECOVERY_APPROVAL_ID,
    )
    assert len(identity) <= 64
    assert identity.startswith(OVERDUE_RECOVERY_AUTHORIZED_BY_PREFIX)


def test_derive_system_identity_isolated_fix_stays_short_for_the_real_incidents_own_ids() -> None:
    """The independent 64-character overflow defect, fixed in isolation: these are the
    REAL incident's own `plan_id`/`owner_approval_id` (the OLD concatenated form was 110
    characters)."""
    identity = derive_system_identity(
        plan_id="PLAN-INT-PRP-089-PAPER-20261009T172613Z",
        owner_approval_id=_ORIGINAL_OWNER_APPROVAL_ID,
    )
    assert len(identity) <= 64


def test_overdue_recovery_authorization_expiry_is_short_and_capped(world: World) -> None:
    """`OVERDUE_RECOVERY_AUTHORIZATION_VALIDITY_SECONDS` is enforced even if a caller asked
    for something longer; the (already-passed) deadline is never used to clamp it."""
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    console = _console(world, plans)
    console.grant_overdue_recovery_approval(intent, "RECOVERY-APPROVAL")
    view = console.review(intent)

    console.confirm_overdue_recovery(intent, view.ticket, "RECOVERY-APPROVAL")

    (attempt,) = world.exits.attempts.for_entry(intent)
    authorization = world.exits.authorizations.get(attempt.authorization_id)
    assert authorization is not None
    granted_window = (authorization.expires_at - authorization.authorized_at).total_seconds()
    assert granted_window <= OVERDUE_RECOVERY_AUTHORIZATION_VALIDITY_SECONDS


# ---------------------------------------------------------------------------
# Realistic production ids, end to end: manual recovery AND automatic dispatch
# ---------------------------------------------------------------------------


def test_manual_overdue_recovery_end_to_end_with_realistic_production_ids(
    world: World,
) -> None:
    """The full grant -> confirm flow, using the REAL incident's own governance id shapes
    throughout (not the short synthetic ids most other tests use)."""
    intent = _open_position(world)
    _advance_past_deadline(world, intent)
    plans = FakeApprovedPlans()
    plans.save(
        _mandatory_exit_plan(
            world,
            intent,
            plan_id="PLAN-INT-PRP-089-PAPER-20261009T172613Z",
            owner_approval_id=_ORIGINAL_OWNER_APPROVAL_ID,
        )
    )
    console = _console(world, plans)

    console.grant_overdue_recovery_approval(intent, _REALISTIC_RECOVERY_APPROVAL_ID)
    view = console.review(intent)
    outcome = console.confirm_overdue_recovery(intent, view.ticket, _REALISTIC_RECOVERY_APPROVAL_ID)

    assert outcome.ok, outcome.message
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1


def test_automatic_mandatory_exit_dispatch_end_to_end_with_realistic_production_ids(
    world: World,
) -> None:
    """Proves the ISOLATED `derive_system_identity` fix: before it, the automatic manager
    would raise `ValueError` the instant it tried to save an authorization whose
    `authorized_by` (`plan.system_identity`) exceeded 64 characters for ids this long.
    Uses the real incident's own `plan_id`/`owner_approval_id`/`entry_intent_governance_id`
    shapes, within the mandatory deadline (NOT the overdue-recovery path -- this is the
    ordinary automatic dispatch the real incident never reached)."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(
        _mandatory_exit_plan(
            world,
            intent,
            plan_id="PLAN-INT-PRP-089-PAPER-20261009T172613Z",
            owner_approval_id=_ORIGINAL_OWNER_APPROVAL_ID,
        )
    )
    assert len(plan.system_identity) <= 64, "the isolated fix must hold for this plan"
    manager = _manager(world, plans)

    # `now` exactly matches the clock the broker itself reads (no artificial disagreement
    # -- that is a SEPARATE, already-fixed concern, PR #28, not what this test proves).
    outcomes = manager.evaluate_once(now=world.clock.utc)

    # A brand-new claim that dispatches within the SAME tick reports EXIT_CLAIMED with
    # "dispatched=True" in its detail (EXIT_SUBMITTED is for RESUMING an already-claimed
    # plan on a later tick -- see `test_v1_exit_authorize_time_uncertain_repro.py`).
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    assert "dispatched=True" in outcomes[0].detail
    (attempt,) = world.exits.attempts.for_entry(intent)
    authorization = world.exits.authorizations.get(attempt.authorization_id)
    assert authorization is not None
    assert authorization.authorized_by == plan.system_identity
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1, "exactly one SELL_TO_CLOSE, never a duplicate"
