"""RELEASE v1 -- Release Blocker 4: automatic management of an Owner-approved plan.

WHAT THIS IS. The one new piece of automation this release adds: given a durable
`ApprovedPlan`, watch broker/market truth and, when the stop, target, or mandatory-
liquidation condition the Owner already approved is reached, submit the SAME bounded
SELL_TO_CLOSE a human would -- through the SAME `AuthorizePositionExitHandler` /
`SubmitAuthorizedPositionExitHandler` chain `operator_console_exits.py` uses for a manual
exit, with `authorized_by` set to the plan's own `system_identity`
(`approved_plan.derive_system_identity`). Nothing here calls the broker directly, submits
a BUY, widens a stop, moves a target, or increases quantity -- see
`tests/architecture/test_v1_position_plan_manager_boundaries.py` for the static proof.

WHY THIS IS SAFE TO RUN UNATTENDED (restart/crash-recovery). Every durable fact this
manager depends on lives in Postgres, never in-process memory alone:

  1. The trigger decision is pure (`approved_plan.evaluate_exit_trigger`) and re-derivable
     from the plan's own frozen terms plus a fresh quote -- nothing about "which trigger
     fired" is remembered only in RAM.
  2. The RIGHT to act on a trigger is claimed durably and atomically
     (`ApprovedPlanRepository.claim_exit_trigger`, `UPDATE ... WHERE triggered_exit_kind
     IS NULL`), before any Preview/Authorize/Submit call. A process that dies the instant
     after winning the claim leaves `triggered_exit_kind` set in Postgres; the NEXT process
     to poll this plan sees it as "claimed, not yet resolved" and resumes the SAME
     Preview-> Authorize-> Submit sequence with the SAME deterministic identities
     (`_preview_id`, `_authorization_id`, `_attempt_id`, all derived from `(plan_id, kind)`
     -- never random), which is safe to call again at ANY point because the existing exit
     pipeline is itself idempotent at every one of those steps: `exit_eligibility` refuses
     a second preview while an attempt is in flight or filled-unverified,
     `PositionExitAttemptRepository.claim_dispatch` allows at most one active attempt per
     position, and `SubmitAuthorizedPositionExitHandler.handle`'s own first check
     (`active_for_entry`) is itself a no-op "already sent" branch, not a resend.
  3. An attempt stuck in a non-terminal state (including `SUBMISSION_UNKNOWN`) is advanced
     by calling the EXISTING `ReconcilePositionExitHandler` against the SAME attempt
     identity -- never a new SELL, never a guess.

This gives every restart boundary the release mission lists (waiting for entry, after
fill, monitoring, immediately before claim, after claim/before broker ack, UNKNOWN, after
fill/before zero-verification) the same answer: re-poll from Postgres and continue: see
`tests/unit/test_v1_position_plan_manager.py`'s restart-recovery cases, which simulate
exactly these boundaries by constructing a fresh manager instance mid-sequence.

ONE PROCESS, ONE BACKGROUND LOOP, NO SECOND BINARY. `run_forever`/`PlanManagerThread` are
started INSIDE the same console process as the WSGI server (see
`entrypoints/_v1_console_composition.py`), never a second console instance, matching the
release mission's "one console instance" requirement.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    derive_system_identity,
    evaluate_exit_trigger,
)
from empirical_platform.decision_candidate.approved_plan_repositories import (
    ApprovedPlanRepository,
)
from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
)
from empirical_platform.decision_candidate.external_position_closure_repositories import (
    ExternalPositionClosureRepository,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    ExecutionAttemptRepository,
    ExecutionKillSwitchRepository,
    PaperMarketDataPort,
)
from empirical_platform.decision_candidate.position_exit import (
    PositionExitAttempt,
    PositionExitEvent,
    PositionExitState,
)
from empirical_platform.decision_candidate.position_exit_repositories import (
    ExitBrokerPort,
    PositionExitAcknowledgementRepository,
    PositionExitAttemptRepository,
    PositionExitAuthorizationRepository,
    PositionExitEventRepository,
    PositionExitPreviewRepository,
    PositionExitRoundRepository,
)
from empirical_platform.decision_candidate.product_repositories import (
    ApprovedOrderIntentRepository,
    OperatorTradingConfigurationRepository,
)
from empirical_platform.shared.brokerage.paper_time import (
    PaperTimeSource,
    PaperTimeUncertainError,
)
from empirical_platform.usecases.position_exit import (
    AssessPositionExitHandler,
    AuthorizePositionExitCommand,
    AuthorizePositionExitHandler,
    CancelPositionExitCommand,
    CancelPositionExitHandler,
    PositionExitRefusedError,
    PreviewPositionExitCommand,
    PreviewPositionExitHandler,
    ReconcilePositionExitCommand,
    ReconcilePositionExitHandler,
    SubmitAuthorizedPositionExitCommand,
    SubmitAuthorizedPositionExitHandler,
)

__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "ApprovedPlanRepository",
    "ExternalPositionClosureRepository",
    "ManagerHeartbeat",
    "ManagerStatus",
    "ManagerStatusView",
    "ManagerThreadHandle",
    "PlanEvaluationOutcome",
    "PlanManagerThread",
    "PositionPlanManager",
    "manager_liveness_alert",
    "manager_status",
    "manager_status_detail",
]

_LOG = logging.getLogger("empirical_platform.position_plan_manager")

#: Many evaluation opportunities inside `MANDATORY_EXIT_SAFETY_BUFFER_SECONDS` (120s), so
#: a mandatory exit is not at the mercy of a single poll landing exactly on the deadline.
DEFAULT_POLL_INTERVAL_SECONDS = 15

#: EXIT SIGNAL QUALITY GATE (2026-10-21 hardening, FORENSIC AUDIT follow-up). The 2026-10-20
#: early-STOP incident: an IEX bid of 335.72 claimed a STOP against stop_price=338.40 while
#: the SAME feed's ask stayed anchored at ~340.11-340.52 throughout -- the bid was a thin,
#: flickering single-venue print, not a genuine move. Retrieving Alpaca's own historical IEX
#: quote ticks for the 15 seconds preceding that claim shows why a single snapshot is not
#: enough evidence: of 664 ticks in that window, only 360 (54%) crossed stop_price -- a coin
#: flip. A comparable window around a GENUINE, sustained move crosses at ~100%, because real
#: price deterioration persists tick to tick; it does not oscillate back to the old level.
#:
#: This is deliberately NOT a new price or spread threshold: it reuses the EXACT comparison
#: `evaluate_exit_trigger` already makes (`bid <= stop_price` / `bid >= target_price`), just
#: requires it to hold across a short recent window of independent IEX prints, not only the
#: single latest one. It is also deliberately separate from, and does not duplicate, the
#: EXISTING M085 freshness/spread gate (`paper_execution.quote_refusal`, reused unchanged by
#: `PreviewPositionExitHandler`/`SubmitAuthorizedPositionExitHandler`) -- that gate already
#: protects EXECUTION quality at preview/submit time using a LATER quote; it ran against a
#: calmer, later snapshot during the actual incident and so never refused, because the
#: problem was never execution quality -- it was trusting the single snapshot that claimed
#: the trigger in the first place. See `docs/operations/exit-signal-quality-gate.md`.
EXIT_QUOTE_CORROBORATION_WINDOW_SECONDS = DEFAULT_POLL_INTERVAL_SECONDS

#: Below this many independent ticks in the lookback window, agreement cannot be assessed
#: at all (a market can be too thin to produce enough prints in 15s). The gate then falls
#: back to trusting the single latest quote exactly as it did before this hardening -- it
#: fails OPEN toward the pre-existing, Owner-accepted behavior, never toward silently
#: blocking a protective exit the Owner is relying on. This is a deliberate policy choice,
#: not an oversight: see the PR description's "residual risks" for the alternative
#: considered and rejected (refusing to claim at all when data is thin).
EXIT_QUOTE_CORROBORATION_MINIMUM_SAMPLE = 5

#: Evidence-grounded (see the constant above this one), not invented: 90% is comfortably
#: separated from both the incident's 54% and a genuine move's ~100%, with margin for a
#: single stray tick in either direction.
EXIT_QUOTE_CORROBORATION_MINIMUM_FRACTION = Decimal("0.90")

# ---------------------------------------------------------------------------------------------
# M100 D3 -- the bounded exit state machine. OPERATIONAL bounds, not financial thresholds: they
# say how long to wait and how many times to try, never what price or size is acceptable. Every
# re-arm is priced by the SAME preview handler as the first attempt (fresh bid, same freshness
# and spread gates, LIMIT/DAY only) -- there is no market order and no discretionary repricing.
# They are pending Owner approval (see docs/operations/m100-exit-state-machine.md).
# ---------------------------------------------------------------------------------------------

#: Total exit attempts per plan: the first dispatch plus (N-1) re-arms. When they are spent and
#: the position is still open, the plan is escalated -- never retried again.
EXIT_MAXIMUM_ATTEMPTS = 3

#: How long a working (ACCEPTED / PARTIALLY_FILLED) exit may rest at the broker before it is
#: cancelled so it can be re-armed at the current bid.
EXIT_WORKING_REST_SECONDS = 90

#: Cancel-for-reprice is only attempted while at least this long remains before the close. Closer
#: than that, a cancel could leave NO working exit when the session ends, so the resting order is
#: left in place instead.
EXIT_MINIMUM_SECONDS_TO_CLOSE_FOR_REPRICE = 300

#: A cancel the broker has not confirmed within this long is an unresolved risk.
EXIT_CANCEL_CONFIRMATION_SECONDS = 120

#: A position with NO working exit (terminal, unfilled) that cannot be re-armed for this long is
#: an unresolved risk. Shorter gaps are ordinary transient refusals (stale quote, spread).
EXIT_UNPROTECTED_ESCALATION_SECONDS = 120

_ESCALATION_ACTOR = "plan-manager"

#: The ONLY broker statuses on which the manager will cancel a resting exit. Any other vocabulary
#: (a status this product has never mapped, or none at all) is an unexpected broker response:
#: nothing is cancelled or replaced on the strength of it.
_CANCELLABLE_BROKER_STATUSES = frozenset(
    {"new", "accepted", "pending_new", "held", "partially_filled"}
)


class PlanOutcomeKind(StrEnum):
    MONITORING = "MONITORING"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NO_QUOTE = "NO_QUOTE"
    EXIT_CLAIMED = "EXIT_CLAIMED"
    EXIT_ALREADY_CLAIMED = "EXIT_ALREADY_CLAIMED"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    EXIT_ALREADY_IN_PROGRESS = "EXIT_ALREADY_IN_PROGRESS"
    EXIT_RECONCILED = "EXIT_RECONCILED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    #: EXIT SIGNAL QUALITY GATE (2026-10-21): a STOP/TARGET candidate's own single quote
    #: snapshot is NOT corroborated by its short recent quote history (see
    #: `EXIT_QUOTE_CORROBORATION_MINIMUM_FRACTION`). The plan is left unclaimed -- this is
    #: a `MONITORING`-family outcome, re-evaluated fresh next tick, never a terminal state.
    #: `MANDATORY_EXIT` never produces this: it is time-only and never consults a quote.
    TRIGGER_EVIDENCE_UNCERTAIN = "TRIGGER_EVIDENCE_UNCERTAIN"
    #: RELEASE v1: a durable `ExternalPositionClosure` record exists for this entry (the
    #: position was closed outside this platform's own exit pipeline -- see
    #: `usecases.record_external_position_closure`). The manager will never evaluate a
    #: trigger, claim one, or attempt Preview/Authorize/Submit for this plan again.
    EXTERNALLY_CLOSED = "EXTERNALLY_CLOSED"
    #: M100 D3: the working exit rested too long; a cancel was REQUESTED (not assumed).
    EXIT_CANCEL_REQUESTED = "EXIT_CANCEL_REQUESTED"
    #: M100 D3: a previous attempt is confirmed terminal and unfilled; a new generation was sent.
    EXIT_REARMED = "EXIT_REARMED"
    #: M100 D3: the market is closed; nothing is sent until it opens (and the gap is visible).
    EXIT_WAITING_FOR_MARKET = "EXIT_WAITING_FOR_MARKET"
    #: M100 D3: an exit cannot safely complete. Durable event written, entries blocked, Owner
    #: must act. The position stays visible as "Needs attention" until it is closed.
    EXIT_UNRESOLVED_RISK = "EXIT_UNRESOLVED_RISK"


@dataclass(frozen=True, slots=True)
class PlanEvaluationOutcome:
    plan_id: str
    entry_intent_governance_id: str
    kind: PlanOutcomeKind
    detail: str


def _generation_suffix(plan: ApprovedPlan, kind: ExitTriggerKind, generation: int) -> str:
    """Identity material for re-arm generations (>= 1).

    A digest, not a concatenation: the base identifiers are already close to the 64-character
    identifier limit, so a readable suffix could overflow it. Deterministic, so a restart, a
    second worker and a reconciliation all derive the SAME identity for the same generation.
    """
    return hashlib.sha256(f"{plan.plan_id}|{kind.value}|{generation}".encode()).hexdigest()[:40]


def _preview_id(plan: ApprovedPlan, kind: ExitTriggerKind, generation: int = 0) -> str:
    if generation:
        return f"XPV-{_generation_suffix(plan, kind, generation)}"
    return f"XPV-plan-{plan.plan_id}-{kind.value}"


def _authorization_id(plan: ApprovedPlan, kind: ExitTriggerKind, generation: int = 0) -> str:
    if generation:
        return f"XAU-{_generation_suffix(plan, kind, generation)}"
    return f"XAU-plan-{plan.plan_id}-{kind.value}"


def _attempt_id(plan: ApprovedPlan, kind: ExitTriggerKind, generation: int = 0) -> str:
    if generation:
        return f"XAT-{_generation_suffix(plan, kind, generation)}"
    return f"XAT-plan-{plan.plan_id}-{kind.value}"


class PositionPlanManager:
    """One poll tick over every durably-tracked approved plan. No broker call of its own;
    everything is delegated to the existing, proven exit-pipeline handlers."""

    __slots__ = (
        "_plans",
        "_external_closures",
        "_assess",
        "_previews",
        "_authorizations",
        "_attempts",
        "_market_data",
        "_preview_handler",
        "_authorize_handler",
        "_submit_handler",
        "_reconcile_handler",
        "_cancel_handler",
        "_events",
        "_broker",
        "_entry_kill_switch",
    )

    def __init__(
        self,
        *,
        plans: ApprovedPlanRepository,
        external_closures: ExternalPositionClosureRepository,
        intents: ApprovedOrderIntentRepository,
        entry_attempts: ExecutionAttemptRepository,
        exit_attempts: PositionExitAttemptRepository,
        previews: PositionExitPreviewRepository,
        authorizations: PositionExitAuthorizationRepository,
        acknowledgements: PositionExitAcknowledgementRepository,
        events: PositionExitEventRepository,
        rounds: PositionExitRoundRepository,
        broker: ExitBrokerPort,
        market_data: PaperMarketDataPort,
        configurations: OperatorTradingConfigurationRepository,
        environment: str,
        time_source: PaperTimeSource | None = None,
        entry_kill_switch: ExecutionKillSwitchRepository | None = None,
    ) -> None:
        self._events = events
        self._broker = broker
        #: M100 D3: engaged ONLY to stop new ENTRIES when an exit cannot safely complete. It is
        #: never given to the exit handlers (exits ignore the kill switch), so engaging it can
        #: never block a position-reducing order.
        self._entry_kill_switch = entry_kill_switch
        self._plans = plans
        self._external_closures = external_closures
        self._previews = previews
        self._authorizations = authorizations
        self._attempts = exit_attempts
        self._market_data = market_data
        self._assess = AssessPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            exit_attempts=exit_attempts,
            external_closures=external_closures,
            broker=broker,
        )
        self._preview_handler = PreviewPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            exit_attempts=exit_attempts,
            external_closures=external_closures,
            previews=previews,
            events=events,
            broker=broker,
            market_data=market_data,
            configurations=configurations,
            environment=environment,
            time_source=time_source,
        )
        self._authorize_handler = AuthorizePositionExitHandler(
            previews=previews,
            authorizations=authorizations,
            events=events,
            broker=broker,
            kill_switch=_NeverEngagedKillSwitch(),
            time_source=time_source,
        )
        self._submit_handler = SubmitAuthorizedPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            previews=previews,
            authorizations=authorizations,
            attempts=exit_attempts,
            external_closures=external_closures,
            acknowledgements=acknowledgements,
            events=events,
            broker=broker,
            configurations=configurations,
            kill_switch=_NeverEngagedKillSwitch(),
            time_source=time_source,
        )
        self._reconcile_handler = ReconcilePositionExitHandler(
            attempts=exit_attempts,
            acknowledgements=acknowledgements,
            events=events,
            rounds=rounds,
            authorizations=authorizations,
            previews=previews,
            broker=broker,
            time_source=time_source,
        )
        self._cancel_handler = CancelPositionExitHandler(
            attempts=exit_attempts,
            acknowledgements=acknowledgements,
            events=events,
            broker=broker,
        )

    def evaluate_once(self, *, now: datetime) -> tuple[PlanEvaluationOutcome, ...]:
        """One poll tick. Safe to call repeatedly, from any process, at any time -- every
        decision it makes is re-derived from durable state, never remembered in RAM."""
        outcomes: list[PlanEvaluationOutcome] = []
        for plan in self._plans.list_unclaimed(500):
            outcomes.append(self._guarded(plan, self._evaluate_unclaimed, now))
        for plan in self._list_claimed_unresolved(limit=500):
            outcomes.append(self._guarded(plan, self._resume_claimed, now))
        return tuple(outcomes)

    @staticmethod
    def _guarded(
        plan: ApprovedPlan,
        step: Callable[..., PlanEvaluationOutcome],
        now: datetime,
    ) -> PlanEvaluationOutcome:
        """M100 D3: one plan's broker outage or unexpected response must not abort the tick for
        every other plan. The failure becomes a visible NEEDS_ATTENTION outcome and nothing is
        cancelled, replaced or re-armed on its strength; the next tick tries again."""
        try:
            return step(plan, now=now)
        except Exception as error:  # noqa: BLE001 - isolate per plan, report, retry next tick
            _LOG.warning("plan %s tick failed: %s: %s", plan.plan_id, type(error).__name__, error)
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.NEEDS_ATTENTION,
                f"{type(error).__name__}: {error}; no exit action was taken on this tick",
            )

    # -- unclaimed plans: decide whether a trigger fires ------------------------------

    def _evaluate_unclaimed(self, plan: ApprovedPlan, *, now: datetime) -> PlanEvaluationOutcome:
        closure = self._external_closures.for_entry(plan.entry_intent_governance_id)
        if closure is not None:
            return self._externally_closed_outcome(plan, closure)
        assessment = self._assess.handle(plan.entry_intent_governance_id, at=now)
        if not assessment.eligible:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.NOT_ELIGIBLE,
                "; ".join(assessment.refusals),
            )
        quote = self._market_data.fetch_quote(plan.symbol)
        last_price = _bid_as_decimal(quote)
        if last_price is None:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.NO_QUOTE,
                "no usable bid is available to evaluate the stop/target condition",
            )
        trigger = evaluate_exit_trigger(plan, last_price=last_price, now=now)
        if trigger is None:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.MONITORING,
                f"last_price={last_price} stop={plan.stop_price} target={plan.target_price}",
            )
        # FORENSIC AUDIT FOLLOW-UP (2026-10-20 early-STOP incident): persist the exact
        # quote that drove a price-based (STOP/TARGET) claim -- bid, ask, the quote's OWN
        # timestamp, and its feed/source -- so a future incident is reconstructible from
        # this row alone. MANDATORY_EXIT fires on time alone and never consults a quote.
        is_price_trigger = trigger in (ExitTriggerKind.STOP, ExitTriggerKind.TARGET)
        if is_price_trigger:
            corroborated, detail = self._corroborate_price_trigger(trigger, plan=plan, now=now)
            if not corroborated:
                # ADVERSARIAL REVIEW FOLLOW-UP (PR #41, 2026-10-21): `evaluate_exit_trigger`
                # prioritizes a price trigger over MANDATORY_EXIT even when the deadline has
                # ALSO already passed (its own docstring: STOP/TARGET is "the more urgent
                # risk-bounding fact") -- so it never even evaluated the deadline branch once
                # it returned `trigger` here. Before this check, an uncertain price trigger
                # therefore left the plan completely unclaimed on a tick where MANDATORY_EXIT
                # was independently and unconditionally due -- the exact "poor-quality quote
                # silently prevents timely mandatory exit" case the mission forbids. Re-check
                # the deadline directly: it needs no quote and is immune to this gate.
                if now >= plan.mandatory_exit_deadline:
                    trigger = ExitTriggerKind.MANDATORY_EXIT
                    is_price_trigger = False
                else:
                    return PlanEvaluationOutcome(
                        plan.plan_id,
                        plan.entry_intent_governance_id,
                        PlanOutcomeKind.TRIGGER_EVIDENCE_UNCERTAIN,
                        f"trigger={trigger.value} candidate last_price={last_price} "
                        f"stop={plan.stop_price} target={plan.target_price}: {detail}; not "
                        "claimed, re-evaluating next tick -- MANDATORY_EXIT is unaffected and "
                        "remains independently time-driven",
                    )
        claimed = self._plans.claim_exit_trigger(
            plan.plan_id,
            kind=trigger,
            claimed_at=now,
            quote_bid=last_price if is_price_trigger else None,
            quote_ask=_ask_as_decimal(quote) if is_price_trigger else None,
            quote_captured_at=getattr(quote, "captured_at", None) if is_price_trigger else None,
            quote_source=getattr(quote, "source", None) if is_price_trigger else None,
        )
        if claimed is None:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_ALREADY_CLAIMED,
                "another evaluation already claimed this plan's exit trigger",
            )
        return self._attempt_exit(claimed, now=now, just_claimed=True)

    def _corroborate_price_trigger(
        self, kind: ExitTriggerKind, *, plan: ApprovedPlan, now: datetime
    ) -> tuple[bool, str]:
        """EXIT SIGNAL QUALITY GATE: does a short recent window of independent IEX quote
        ticks agree with the single latest one that produced `kind`? Re-fetches fresh from
        the broker every call (see `fetch_recent_quotes`) -- nothing here is remembered in
        RAM between ticks, matching every other durability property this manager has.

        ADVERSARIAL REVIEW FOLLOW-UP (PR #41, 2026-10-21): a `fetch_recent_quotes` failure
        (network error, timeout, malformed response the adapter could not swallow itself)
        must fail OPEN exactly like an empty/thin result does -- not propagate and abort
        the ENTIRE tick (every other plan `evaluate_once` was about to evaluate too) over a
        failure in a check that is, by this gate's own design, allowed to be unavailable.
        """
        try:
            recent = self._market_data.fetch_recent_quotes(
                plan.symbol,
                start=now - timedelta(seconds=EXIT_QUOTE_CORROBORATION_WINDOW_SECONDS),
                end=now,
            )
        except Exception as error:  # noqa: BLE001 - a corroboration failure must fail OPEN
            _LOG.warning(
                "plan %s: fetch_recent_quotes failed (%s: %s); falling back to trusting "
                "the single latest quote",
                plan.plan_id,
                type(error).__name__,
                error,
            )
            return True, f"fetch_recent_quotes raised {type(error).__name__}: {error}"
        return _price_trigger_corroboration(kind, plan=plan, recent=recent)

    def _externally_closed_outcome(
        self, plan: ApprovedPlan, closure: ExternalPositionClosure
    ) -> PlanEvaluationOutcome:
        return PlanEvaluationOutcome(
            plan.plan_id,
            plan.entry_intent_governance_id,
            PlanOutcomeKind.EXTERNALLY_CLOSED,
            f"closed externally under broker order {closure.client_order_id!r} "
            f"(recorded by {closure.recorded_by!r} at {closure.recorded_at.isoformat()}); "
            "the automatic manager will not evaluate or act on this plan again",
        )

    # -- claimed plans: resume dispatch/reconciliation ---------------------------------

    def _list_claimed_unresolved(self, *, limit: int) -> tuple[ApprovedPlan, ...]:
        claimed = self._plans.list_claimed(limit)
        unresolved = []
        for plan in claimed:
            attempt = self._attempts.active_for_entry(plan.entry_intent_governance_id)
            if attempt is None or not attempt.position_closed:
                unresolved.append(plan)
        return tuple(unresolved)

    def _resume_claimed(self, plan: ApprovedPlan, *, now: datetime) -> PlanEvaluationOutcome:
        """M100 D3: drive a claimed plan's exit through a bounded, fail-closed state machine.

        Every decision is re-derived from DURABLE state (the plan's attempt history and the
        broker), so a restart, a second worker or a crashed tick resumes exactly here. The rules:

        * Broker truth first: a non-terminal attempt is reconciled before anything else, and an
          order is never treated as cancelled or filled until the broker says so.
        * Uncertain attempts (unknown, claimed, in progress) are only reconciled -- never
          cancelled, replaced or duplicated.
        * A working exit that has rested too long is CANCEL-REQUESTED once; the next ticks
          reconcile; only a broker-confirmed CANCELED/EXPIRED/REJECTED attempt can be re-armed,
          so two exit orders can never be live together and the position cannot be oversold.
        * Re-arms are bounded (`EXIT_MAXIMUM_ATTEMPTS`) and priced by the ordinary preview.
        * Anything that cannot safely complete is ESCALATED: a durable event, a visible
          NEEDS_ATTENTION state, and the entry kill switch -- never silence.
        """
        closure = self._external_closures.for_entry(plan.entry_intent_governance_id)
        if closure is not None:
            return self._externally_closed_outcome(plan, closure)
        history = self._attempts.for_entry(plan.entry_intent_governance_id)
        if not history:
            return self._attempt_exit(plan, now=now, just_claimed=False)
        latest = history[-1]
        if not latest.is_terminal:
            return self._supervise_working(plan, latest, len(history), now=now)
        if latest.state is PositionExitState.FILLED:
            # Verify the broker position is flat (the reconcile of a terminal FILLED attempt does
            # exactly that and nothing else).
            verified = self._reconcile_handler.handle(
                ReconcilePositionExitCommand(attempt_id=latest.attempt_id, at=now)
            )
            if verified.position_closed:
                return PlanEvaluationOutcome(
                    plan.plan_id,
                    plan.entry_intent_governance_id,
                    PlanOutcomeKind.EXIT_RECONCILED,
                    f"attempt {verified.attempt_id} state=FILLED position verified closed",
                )
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_ALREADY_IN_PROGRESS,
                f"attempt {verified.attempt_id} filled; the broker position is not yet verified "
                "flat",
            )
        return self._rearm_or_escalate(plan, latest, len(history), now=now)

    def _supervise_working(
        self, plan: ApprovedPlan, attempt: PositionExitAttempt, attempts_made: int, *, now: datetime
    ) -> PlanEvaluationOutcome:
        reconciled = self._reconcile_handler.handle(
            ReconcilePositionExitCommand(attempt_id=attempt.attempt_id, at=now)
        )

        def reconciled_outcome(note: str) -> PlanEvaluationOutcome:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_RECONCILED,
                f"attempt {reconciled.attempt_id} state={reconciled.state.value}{note}",
            )

        state = reconciled.state
        if reconciled.is_terminal:
            return reconciled_outcome("; decided on the next tick")
        if state in (
            PositionExitState.SUBMISSION_UNKNOWN,
            PositionExitState.DISPATCH_CLAIMED,
            PositionExitState.SUBMISSION_IN_PROGRESS,
        ):
            # Never cancel, replace or duplicate an order whose existence is not established.
            return reconciled_outcome("; outcome not established, reconciling only")
        if state is PositionExitState.CANCEL_REQUESTED:
            requested_at = self._cancel_requested_at(reconciled)
            if (
                requested_at is not None
                and (now - requested_at).total_seconds() > EXIT_CANCEL_CONFIRMATION_SECONDS
            ):
                return self._escalate(
                    plan,
                    reconciled,
                    now=now,
                    key="cancel-unconfirmed",
                    reason=(
                        f"the broker has not confirmed the cancel of exit {reconciled.attempt_id} "
                        f"within {EXIT_CANCEL_CONFIRMATION_SECONDS}s; the order may still be live"
                    ),
                )
            return reconciled_outcome("; awaiting broker confirmation of the cancel")

        rest_started = (
            reconciled.acknowledged_at or reconciled.submitted_at or reconciled.claimed_at
        )
        resting = (now - rest_started).total_seconds()
        if resting < EXIT_WORKING_REST_SECONDS:
            return reconciled_outcome(f"; resting {int(resting)}s")
        if reconciled.broker_status not in _CANCELLABLE_BROKER_STATUSES:
            return self._escalate(
                plan,
                reconciled,
                now=now,
                key="final-attempt-resting",
                reason=(
                    f"the broker reports exit {reconciled.attempt_id} as "
                    f"{reconciled.broker_status!r}, which this product does not recognise as "
                    "a working order; nothing was cancelled or replaced"
                ),
            )
        if attempts_made >= EXIT_MAXIMUM_ATTEMPTS:
            # The last allowed attempt is still working: it is still real protection, so it is
            # left alone -- but an operator must know it has not filled.
            return self._escalate(
                plan,
                reconciled,
                now=now,
                key="unrecognised-status",
                reason=(
                    f"the final allowed exit attempt {reconciled.attempt_id} has rested "
                    f"{int(resting)}s without filling"
                ),
            )
        if not self._can_reprice_safely(now):
            return reconciled_outcome("; not repriced (market closed, closing, or clock unknown)")
        cancelled = self._cancel_handler.handle(
            CancelPositionExitCommand(attempt_id=reconciled.attempt_id, at=now)
        )
        return PlanEvaluationOutcome(
            plan.plan_id,
            plan.entry_intent_governance_id,
            PlanOutcomeKind.EXIT_CANCEL_REQUESTED,
            f"attempt {cancelled.attempt_id} state={cancelled.state.value}; a cancel was "
            "requested after resting too long -- the replacement waits for the broker to "
            "confirm it",
        )

    def _rearm_or_escalate(
        self, plan: ApprovedPlan, latest: PositionExitAttempt, attempts_made: int, *, now: datetime
    ) -> PlanEvaluationOutcome:
        unprotected = (now - (latest.terminal_at or latest.claimed_at)).total_seconds()
        assessment = self._assess.handle(plan.entry_intent_governance_id, at=now)
        if not assessment.eligible:
            # The position no longer matches what this plan can safely sell (closed or resized
            # outside this platform, attribution ambiguous, ...). Selling anyway could oversell.
            return self._escalate(
                plan,
                latest,
                now=now,
                key="position-not-reexitable",
                reason="the position cannot be safely re-exited: " + "; ".join(assessment.refusals),
            )
        if attempts_made >= EXIT_MAXIMUM_ATTEMPTS:
            return self._escalate(
                plan,
                latest,
                now=now,
                key="attempts-spent",
                reason=(
                    f"{attempts_made} exit attempts were spent (last: {latest.state.value}) and "
                    "the position is still open"
                ),
            )
        if not self._market_is_open(now):
            if unprotected > EXIT_UNPROTECTED_ESCALATION_SECONDS:
                return self._escalate(
                    plan,
                    latest,
                    now=now,
                    key="market-closed",
                    reason=(
                        f"exit {latest.attempt_id} ended {latest.state.value} with the position "
                        "still open and the market is closed (or its state is unknown)"
                    ),
                )
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_WAITING_FOR_MARKET,
                f"exit {latest.attempt_id} ended {latest.state.value}; waiting for the market",
            )
        outcome = self._attempt_exit(plan, now=now, just_claimed=False, generation=attempts_made)
        if outcome.kind is PlanOutcomeKind.NEEDS_ATTENTION:
            if unprotected > EXIT_UNPROTECTED_ESCALATION_SECONDS:
                return self._escalate(
                    plan,
                    latest,
                    now=now,
                    key="refused-while-unprotected",
                    reason=(
                        f"no exit has been working for {int(unprotected)}s and a new one was "
                        f"refused: {outcome.detail}"
                    ),
                )
            return outcome
        return PlanEvaluationOutcome(
            plan.plan_id,
            plan.entry_intent_governance_id,
            PlanOutcomeKind.EXIT_REARMED,
            f"generation {attempts_made} after {latest.attempt_id} ({latest.state.value}): "
            + outcome.detail,
        )

    # -- helpers for the exit state machine ------------------------------------------------

    def _market_is_open(self, now: datetime) -> bool:
        """True only on a positive, readable broker answer. Anything else is "not open"."""
        del now
        try:
            return bool(self._broker.fetch_clock().is_open)
        except Exception:  # noqa: BLE001 - an unreadable clock is not permission to act
            return False

    def _can_reprice_safely(self, now: datetime) -> bool:
        try:
            clock = self._broker.fetch_clock()
        except Exception:  # noqa: BLE001 - unknown is not safe
            return False
        if not clock.is_open or clock.next_close is None:
            return False
        remaining = (clock.next_close - now).total_seconds()
        return remaining >= EXIT_MINIMUM_SECONDS_TO_CLOSE_FOR_REPRICE

    def _cancel_requested_at(self, attempt: PositionExitAttempt) -> datetime | None:
        requested = [
            event.occurred_at
            for event in self._events.for_entry(attempt.entry_intent_governance_id)
            if event.attempt_id == attempt.attempt_id
            and event.event_type == "EXIT_CANCEL_REQUESTED"
        ]
        return max(requested) if requested else None

    def _escalate(
        self,
        plan: ApprovedPlan,
        attempt: PositionExitAttempt,
        *,
        now: datetime,
        key: str,
        reason: str,
    ) -> PlanEvaluationOutcome:
        """Make an unresolved exit risk durable, visible and entry-blocking.

        Idempotent per (plan, attempt, ``key``): the key names the KIND of risk, so a reason
        that embeds a changing number (seconds rested) is recorded once, not once per tick.
        """
        digest = hashlib.sha256(f"{plan.plan_id}|{attempt.attempt_id}|{key}".encode()).hexdigest()
        event_id = f"XEV-risk-{digest[:40]}"
        known = {e.event_id for e in self._events.for_entry(plan.entry_intent_governance_id)}
        if event_id not in known:
            self._events.append(
                PositionExitEvent(
                    event_id=event_id,
                    entry_intent_governance_id=plan.entry_intent_governance_id,
                    attempt_id=attempt.attempt_id,
                    event_type="EXIT_UNRESOLVED_RISK",
                    occurred_at=now,
                    detail=reason[:500],
                )
            )
        blocked = "entries not blocked"
        if self._entry_kill_switch is not None:
            try:
                self._entry_kill_switch.engage(
                    changed_by=_ESCALATION_ACTOR,
                    changed_at=now,
                    reason=f"unresolved exit risk for plan {plan.plan_id}"[:500],
                )
                blocked = "new entries blocked (kill switch engaged)"
            except Exception as error:  # noqa: BLE001 - never let escalation itself raise
                blocked = f"FAILED to block new entries ({type(error).__name__})"
                _LOG.error(
                    "plan %s: could not engage the entry kill switch: %s", plan.plan_id, error
                )
        _LOG.warning("plan %s UNRESOLVED EXIT RISK: %s; %s", plan.plan_id, reason, blocked)
        return PlanEvaluationOutcome(
            plan.plan_id,
            plan.entry_intent_governance_id,
            PlanOutcomeKind.EXIT_UNRESOLVED_RISK,
            f"{reason}; {blocked}; the Owner must act",
        )

    # -- the shared, idempotent Preview -> Authorize -> Submit sequence ---------------

    def _attempt_exit(
        self, plan: ApprovedPlan, *, now: datetime, just_claimed: bool, generation: int = 0
    ) -> PlanEvaluationOutcome:
        assert plan.triggered_exit_kind is not None
        kind = plan.triggered_exit_kind
        try:
            preview = self._previews.get(_preview_id(plan, kind, generation))
            if preview is None:
                preview = self._preview_handler.handle(
                    PreviewPositionExitCommand(
                        entry_intent_governance_id=plan.entry_intent_governance_id,
                        preview_id=_preview_id(plan, kind, generation),
                        created_at=now,
                    )
                )
            authorization = self._authorizations.get(_authorization_id(plan, kind, generation))
            if authorization is None:
                authorization = self._authorize_handler.handle(
                    AuthorizePositionExitCommand(
                        authorization_id=_authorization_id(plan, kind, generation),
                        preview_id=preview.preview_id,
                        expected_request_fingerprint=preview.request_fingerprint,
                        # RELEASE v1 LEGACY APPROVED PLAN IDENTITY COMPATIBILITY: derived
                        # fresh, never `plan.system_identity` directly. A legacy plan's OWN
                        # stored identity is still the oversized pre-rewrite string (the
                        # original 64-character authorized_by overflow); deriving fresh is a
                        # no-op for every current-format plan (its stored value already
                        # equals this) and the fix for a legacy one.
                        authorized_by=derive_system_identity(
                            plan_id=plan.plan_id, owner_approval_id=plan.owner_approval_id
                        ),
                        authorized_at=now,
                    )
                )
            result = self._submit_handler.handle(
                SubmitAuthorizedPositionExitCommand(
                    entry_intent_governance_id=plan.entry_intent_governance_id,
                    attempt_id=_attempt_id(plan, kind, generation),
                    at=now,
                )
            )
        except (PositionExitRefusedError, PaperTimeUncertainError) as error:
            # `PaperTimeUncertainError` (paper_time.py) is a sibling `ValueError` subclass,
            # not a `PositionExitRefusedError` -- `AuthorizePositionExitHandler` and
            # `SubmitAuthorizedPositionExitHandler` both raise it directly when a fresh
            # broker-clock reading disagrees with the instant this tick was handed. Left
            # out of this except clause, it escaped to `PlanManagerThread._run`'s blanket
            # `except Exception` instead, which only logs and keeps the thread alive --
            # the claimed trigger was never resolved to NEEDS_ATTENTION, so every later
            # tick repeated the identical failure forever with no owner-visible status.
            # `SubmitAuthorizedPositionExitHandler.handle` already treats the two
            # exceptions as one refusal vocabulary (position_exit.py); this mirrors that.
            message = str(error)
            if (
                "already in progress" in message
                or "already closed" in message
                or ("not yet verified" in message)
            ):
                return PlanEvaluationOutcome(
                    plan.plan_id,
                    plan.entry_intent_governance_id,
                    PlanOutcomeKind.EXIT_ALREADY_IN_PROGRESS,
                    message,
                )
            _LOG.warning("plan %s exit attempt needs attention: %s", plan.plan_id, message)
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.NEEDS_ATTENTION,
                message,
            )
        kind_label = (
            PlanOutcomeKind.EXIT_CLAIMED if just_claimed else PlanOutcomeKind.EXIT_SUBMITTED
        )
        detail = (
            f"trigger={kind.value} attempt={result.attempt.attempt_id} "
            f"dispatched={result.dispatched}"
        )
        return PlanEvaluationOutcome(
            plan.plan_id, plan.entry_intent_governance_id, kind_label, detail
        )


def _bid_as_decimal(quote: object) -> Decimal | None:
    bid = getattr(quote, "bid", None)
    if bid is None:
        return None
    try:
        return Decimal(str(bid))
    except InvalidOperation:
        return None


def _ask_as_decimal(quote: object) -> Decimal | None:
    """FORENSIC AUDIT FOLLOW-UP: the ask alongside the bid `evaluate_exit_trigger` actually
    used, persisted purely as evidence -- never consulted by the trigger decision itself,
    which (unchanged) depends only on the bid (see `evaluate_exit_trigger`)."""
    ask = getattr(quote, "ask", None)
    if ask is None:
        return None
    try:
        return Decimal(str(ask))
    except InvalidOperation:
        return None


def _price_trigger_corroboration(
    kind: ExitTriggerKind, *, plan: ApprovedPlan, recent: Sequence[object]
) -> tuple[bool, str]:
    """EXIT SIGNAL QUALITY GATE, pure and re-derivable: does `recent` -- independent IEX
    quote ticks from the seconds just before `now` -- agree with the single latest tick
    that produced a STOP/TARGET candidate `kind`? See
    `EXIT_QUOTE_CORROBORATION_MINIMUM_FRACTION`'s own docstring for the evidence behind
    this design and why it is not a new price or spread threshold.

    `detail` is always returned, corroborated or not, so the EXACT evidence behind every
    decision -- sample size and agreement fraction, or the thin-sample fallback -- is
    available to log/persist (Phase 3 requirement: "record the actual evidence used").
    """
    sample = [bid for q in recent if (bid := _bid_as_decimal(q)) is not None]
    if len(sample) < EXIT_QUOTE_CORROBORATION_MINIMUM_SAMPLE:
        return (
            True,
            f"sample_size={len(sample)} below the minimum of "
            f"{EXIT_QUOTE_CORROBORATION_MINIMUM_SAMPLE} to assess agreement; falling back "
            "to trusting the single latest quote (pre-hardening behavior)",
        )
    if kind is ExitTriggerKind.STOP:
        agreeing = sum(1 for bid in sample if bid <= plan.stop_price)
    elif kind is ExitTriggerKind.TARGET:
        agreeing = sum(1 for bid in sample if bid >= plan.target_price)
    else:
        raise ValueError(
            f"{kind!r} is not a price-based trigger; MANDATORY_EXIT never reaches here"
        )
    fraction = Decimal(agreeing) / Decimal(len(sample))
    rounded = fraction.quantize(Decimal("0.01"))
    detail = f"sample_size={len(sample)} agreeing={agreeing} fraction={rounded}"
    return fraction >= EXIT_QUOTE_CORROBORATION_MINIMUM_FRACTION, detail


class _NeverEngagedKillSwitch:
    """RELEASE v1: the kill switch never blocks a position-reducing exit (see
    `docs/operations/kill-switch.md`). `AuthorizePositionExitHandler`/
    `SubmitAuthorizedPositionExitHandler` no longer read their `kill_switch` dependency at
    all (see `usecases/position_exit.py`), but this manager still supplies a well-typed,
    always-disengaged stand-in rather than `None`, so a future change to those handlers
    that DID read it again would fail loudly in tests instead of silently reading `None`."""

    __slots__ = ()

    def is_engaged(self) -> bool:
        return False

    def engage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        raise NotImplementedError("the automatic manager never engages the kill switch")

    def disengage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        raise NotImplementedError("the automatic manager never disengages the kill switch")


@dataclass(frozen=True, slots=True)
class ManagerHeartbeat:
    """A point-in-time snapshot of `PlanManagerThread`'s own liveness -- RELEASE v1 SAFETY
    ALERT ADDITION. Safe to read from any thread (`PlanManagerThread.heartbeat()` copies it
    out under a lock; this object itself is immutable once returned).

    `last_tick_at`/`last_tick_error` are set after EVERY tick ATTEMPT, successful or not --
    `last_tick_at` is `None` only before the thread has completed its first tick at all,
    distinct from a tick that ran and failed (which still advances `last_tick_at`, with
    `last_tick_error` naming what went wrong). `ticks_completed` counts attempts, not
    successes, so a manager wedged on the SAME failing tick forever is still visibly
    advancing this counter (it is `last_tick_error`, not a stalled counter, that reveals
    that case) while a manager that has stopped running entirely leaves BOTH frozen.
    """

    started_at: datetime
    last_tick_at: datetime | None
    last_tick_error: str | None
    ticks_completed: int


def manager_liveness_alert(
    heartbeat: ManagerHeartbeat | None,
    *,
    now: datetime,
    has_open_positions: bool,
    max_staleness_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS * 4,
) -> str | None:
    """RELEASE v1 SAFETY ALERT: "background manager failure or stopped manager while a
    position is open" (the one gap the Phase 4 safety-alert review found with no existing
    coverage -- every other required alert category was already produced by
    `blocked_exit_alert`, `deadline_status`, `ExitSummary.pending_reason`,
    `PositionExitConsole.category`, or `PlanOutcomeKind`).

    Pure and read-only: never executes anything, never starts or stops the manager, never
    drops or paraphrases the recorded tick error. Returns `None` whenever there is nothing
    to escalate: no heartbeat object at all (this capability composed no automatic manager
    -- e.g. `--recovery-mode`, or a console with no exit path -- which is a DIFFERENT,
    already-visible state this alert must never duplicate or contradict), no open position
    depends on the manager right now, or the manager is both ticking recently AND its most
    recent tick did not fail.
    """
    if heartbeat is None or not has_open_positions:
        return None
    reference = heartbeat.last_tick_at or heartbeat.started_at
    staleness = (now - reference).total_seconds()
    if staleness > max_staleness_seconds:
        since = "its first tick" if heartbeat.last_tick_at is None else "its last completed tick"
        return (
            f"The automatic position manager has not completed a tick in {int(staleness)}s "
            f"since {since} (expected at least every {DEFAULT_POLL_INTERVAL_SECONDS}s) while "
            "a position depends on it. STOP/TARGET/MANDATORY_EXIT will not be dispatched "
            "automatically until it resumes -- review the console process and /safety."
        )
    if heartbeat.last_tick_error is not None:
        return (
            "The automatic position manager's most recent tick failed while a position is "
            f"open: {heartbeat.last_tick_error}. It will keep retrying on its own schedule, "
            "but review /safety if this repeats."
        )
    return None


class PlanManagerThread:
    """Runs `PositionPlanManager.evaluate_once` on a fixed interval, inside THIS process.

    Started alongside the WSGI server in the SAME console process (see
    `entrypoints/_v1_console_composition.py`) -- never a second process -- and stoppable
    for a clean shutdown. Exceptions from one tick are logged and never kill the loop: a
    manager that stops polling after one bad tick is worse than one that keeps trying.

    RELEASE v1 SAFETY ALERT ADDITION: `heartbeat()` exposes a `ManagerHeartbeat` snapshot
    for `manager_liveness_alert` (or any other read-only caller) to detect a stalled or
    silently-dead thread -- see that function's own docstring. Guarded by `self._lock`
    because it is written from `_run` (the background thread) and read from whatever
    thread serves a console request; the GIL alone would make a single attribute write
    safe, but a lock makes the read-modify-write of `ticks_completed` unambiguous too.
    """

    def __init__(
        self,
        manager: PositionPlanManager,
        *,
        now: Callable[[], datetime],
        interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._manager = manager
        self._now = now
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._heartbeat: ManagerHeartbeat | None = None

    def heartbeat(self) -> ManagerHeartbeat | None:
        """`None` before `start()` has ever been called. Thereafter, always set -- the
        FIRST tick's own attempt sets it before `_run`'s loop can wait on anything, so
        there is no window where the thread is running but this returns `None`."""
        with self._lock:
            return self._heartbeat

    def start(self) -> None:
        if self._thread is not None:
            return
        with self._lock:
            self._heartbeat = ManagerHeartbeat(
                started_at=self._now(), last_tick_at=None, last_tick_error=None, ticks_completed=0
            )
        self._thread = threading.Thread(target=self._run, name="position-plan-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 5)

    def _run(self) -> None:
        while not self._stop.is_set():
            error: str | None = None
            try:
                outcomes = self._manager.evaluate_once(now=self._now())
                # EXIT SIGNAL QUALITY GATE / Phase 3 observability requirement (2026-10-21):
                # the 2026-10-20 incident's own trigger evidence (the exact bid that claimed
                # it) was never logged anywhere -- `evaluate_once`'s return value used to be
                # discarded here entirely. Every outcome is now logged, routine ones at INFO
                # and anything requiring attention at WARNING, so a future incident is
                # reconstructible from the process log even before touching Postgres.
                for outcome in outcomes:
                    level = (
                        logging.WARNING
                        if outcome.kind
                        in (
                            PlanOutcomeKind.NEEDS_ATTENTION,
                            PlanOutcomeKind.TRIGGER_EVIDENCE_UNCERTAIN,
                            PlanOutcomeKind.EXIT_UNRESOLVED_RISK,
                        )
                        else logging.INFO
                    )
                    _LOG.log(
                        level,
                        "plan %s [%s] %s: %s",
                        outcome.plan_id,
                        outcome.entry_intent_governance_id,
                        outcome.kind.value,
                        outcome.detail,
                    )
            except Exception as exc:  # noqa: BLE001 - one bad tick must never stop the loop
                _LOG.exception("position plan manager tick failed")
                error = f"{type(exc).__name__}: {exc}"
            with self._lock:
                previous = self._heartbeat
                self._heartbeat = ManagerHeartbeat(
                    started_at=previous.started_at if previous is not None else self._now(),
                    last_tick_at=self._now(),
                    last_tick_error=error,
                    ticks_completed=(previous.ticks_completed if previous is not None else 0) + 1,
                )
            self._stop.wait(self._interval)


class ManagerThreadHandle:
    """RELEASE v1 SAFETY VISIBILITY. A late-bound, mutable reference to this process's
    `PlanManagerThread` -- read-only from every caller's point of view.

    WHY THIS EXISTS. `PaperConsoleBackend` (`entrypoints._paper_position_exit_composition`)
    is an immutable (`frozen=True`) dataclass built BEFORE the real `PlanManagerThread` is
    constructed: the thread is only started inside `entrypoints.operator_console.main`'s
    `_serve_with_reconciler`, after the backend (and every HTTP route closed over it) already
    exists. A frozen dataclass cannot grow a new attribute later, so the composition hands
    out this ONE mutable box instead -- `operator_console.py` sets `.thread` once the real
    thread starts; the `/safety` route reads `.heartbeat()` on every request, always getting
    the CURRENT thread's live state, never a stale snapshot captured at startup.

    `.thread` is `None` until the owning process actually starts a `PlanManagerThread` (never
    true for `--recovery-mode`, which builds no `PositionPlanManager` at all -- see
    `_paper_position_exit_composition.paper_operator_console_with_exit_runtime`) -- this is
    exactly the "automatic management is supposed to exist, but nothing has started it"
    evidence `manager_status`'s `STOPPED` state reads. A console capability with NO
    plan-manager concept at all (SIMULATION, or plain PAPER without the exit path) never
    constructs one of these at all -- `PaperConsoleBackend._manager_thread_handle` stays
    `None` there, which `manager_status` reads as `manager_supported=False` -> `UNKNOWN`.
    """

    __slots__ = ("thread",)

    def __init__(self) -> None:
        self.thread: PlanManagerThread | None = None

    def heartbeat(self) -> ManagerHeartbeat | None:
        return None if self.thread is None else self.thread.heartbeat()


class ManagerStatus(StrEnum):
    """RELEASE v1 SAFETY VISIBILITY: the Owner-facing truth-state for `/safety`'s automatic
    position manager field. Exactly five states, deliberately -- see `manager_status`'s own
    docstring for why each one is truthful and when it applies. `UNKNOWN` is the fallback
    whenever the evidence does not clearly support one of the other four; this field must
    NEVER read `HEALTHY` without positive, fresh, error-free tick evidence."""

    RECOVERY_MODE = "RECOVERY_MODE"
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    STOPPED = "STOPPED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ManagerStatusView:
    """What `/safety` renders: the state plus the plain-language, actionable text for it.
    See `manager_status`/`manager_status_detail` -- this is just their paired output, built
    once per request so the route and the HTML layer agree on exactly one `now`."""

    status: ManagerStatus
    detail: str


def manager_status(
    heartbeat: ManagerHeartbeat | None,
    *,
    now: datetime,
    recovery_mode: bool,
    manager_supported: bool,
    max_staleness_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS * 4,
) -> ManagerStatus:
    """RELEASE v1 SAFETY VISIBILITY: the pure classification behind `/safety`'s manager-status
    field (see `ManagerStatus`). Reads ONLY the real `ManagerHeartbeat` the evaluation loop
    itself maintains (`PlanManagerThread._run`) -- never "the HTTP server answered this
    request" or "the process is alive", neither of which says anything about whether the
    BACKGROUND loop is still ticking.

    Precedence, each one answering a different question the Owner needs kept apart:

    1. `recovery_mode` -> `RECOVERY_MODE`. Checked FIRST and unconditionally: a deliberate,
       read-only `--recovery-mode` startup never builds a `PositionPlanManager` at all (see
       `paper_operator_console_with_exit_runtime`'s own docstring), so `heartbeat` is always
       `None` here anyway -- but this state must never be confused with a REAL failure
       (`STOPPED`), which is exactly why it is checked ahead of, not folded into, the
       no-heartbeat case below.
    2. `not manager_supported` -> `UNKNOWN`. This capability's composition has no plan-manager
       concept at all (SIMULATION, or plain PAPER without the exit path -- see
       `ManagerThreadHandle`'s own docstring) or cannot safely expose one. There is nothing to
       assert here, positive or negative -- not "stopped" (nothing was ever supposed to run),
       just genuinely unknown to this page.
    3. `heartbeat is None` -> `STOPPED`. Supported and not in recovery mode, yet no heartbeat
       object exists at all: `PlanManagerThread.start()` was never called (or the thread
       object itself is gone). Per `PlanManagerThread.heartbeat`'s own docstring, ONCE
       `start()` runs, a heartbeat is set before the background thread can do anything else --
       so `None` here can only mean the thread never started, never "it ticked and then
       disappeared" (that is `STALE`, below).
    4. A heartbeat exists but is stale (`last_tick_at`, or `started_at` if it has never
       ticked, is older than `max_staleness_seconds`) OR its most recent tick recorded an
       error -> `STALE`. Both are folded into the SAME state (there is no sixth name for
       "ticking, but the last tick just failed"): a fresh heartbeat with a recorded error is
       not stale BY TIMESTAMP, but it is equally not evidence of a working manager, and
       requirement 7 forbids ever reporting `HEALTHY` without full, no-error evidence.
       `manager_status_detail` tells the two cases apart in its own wording.
    5. Otherwise (a heartbeat exists, is fresh, and its last tick did not error) -> `HEALTHY`.
       The ONLY state this function will return without a stale-or-erroring heartbeat check
       having already passed -- the "never HEALTHY without evidence" rule in one sentence.
    """
    if recovery_mode:
        return ManagerStatus.RECOVERY_MODE
    if not manager_supported:
        return ManagerStatus.UNKNOWN
    if heartbeat is None:
        return ManagerStatus.STOPPED
    reference = heartbeat.last_tick_at or heartbeat.started_at
    staleness = (now - reference).total_seconds()
    if staleness > max_staleness_seconds or heartbeat.last_tick_error is not None:
        return ManagerStatus.STALE
    return ManagerStatus.HEALTHY


def manager_status_detail(
    status: ManagerStatus,
    heartbeat: ManagerHeartbeat | None,
    *,
    now: datetime,
    max_staleness_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS * 4,
) -> str:
    """Plain-language, actionable text for `ManagerStatus` -- same tone and pattern as
    `operator_console_exits.blocked_exit_alert` and the `--recovery-mode` startup banner
    (`entrypoints.operator_console.main`): say what is actually true, say plainly that
    nothing is failing silently, and never alarm for the intentional `RECOVERY_MODE` case.
    """
    if status is ManagerStatus.RECOVERY_MODE:
        return (
            "This console was started with --recovery-mode: a deliberate, read-only, "
            "fail-closed startup. The automatic position manager was never built -- not "
            "failed, not stopped, simply not started on purpose. No exit, automatic or "
            "manual, can be confirmed or sent while this holds. Restart without "
            "--recovery-mode, with the Owner present, to resume automatic management."
        )
    if status is ManagerStatus.UNKNOWN:
        return (
            "This console's composition does not expose automatic-manager status -- either "
            "it has no plan-manager concept at all, or the wiring to read one safely is not "
            "in place. This is not a claim that management is healthy; it is a gap in what "
            "this page can currently prove, and should be treated as unproven, not fine."
        )
    if status is ManagerStatus.STOPPED:
        return (
            "This console expects an automatic position manager, but none has ever started "
            "ticking -- no heartbeat exists at all. STOP/TARGET/MANDATORY_EXIT will not be "
            "dispatched automatically until it does. This is not a silent failure: restart "
            "the console process, with the Owner present, to resume automatic management."
        )
    assert heartbeat is not None  # STALE and HEALTHY both require real heartbeat evidence
    if status is ManagerStatus.STALE:
        reference = heartbeat.last_tick_at or heartbeat.started_at
        staleness = int((now - reference).total_seconds())
        if staleness > max_staleness_seconds:
            since = (
                "its first tick" if heartbeat.last_tick_at is None else "its last completed tick"
            )
            return (
                f"The automatic position manager has not completed a tick in {staleness}s "
                f"since {since} (expected at least every {DEFAULT_POLL_INTERVAL_SECONDS}s). It "
                "may have hung or crashed without exiting. STOP/TARGET/MANDATORY_EXIT will not "
                "be dispatched automatically until it resumes -- review the console process."
            )
        assert heartbeat.last_tick_error is not None  # the only other way into STALE
        return (
            "The automatic position manager's most recent tick failed: "
            f"{heartbeat.last_tick_error}. It is still running and will keep retrying on its "
            "own schedule, but review this if it repeats."
        )
    ticks_ago = int((now - (heartbeat.last_tick_at or heartbeat.started_at)).total_seconds())
    return (
        f"The automatic position manager is running: {heartbeat.ticks_completed} tick(s) "
        f"completed, most recently {ticks_ago}s ago, with no error."
    )
