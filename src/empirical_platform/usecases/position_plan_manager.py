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
    PaperMarketDataPort,
)
from empirical_platform.decision_candidate.position_exit import (
    EXIT_CANCEL_EVENT_TYPES,
    EXIT_MAX_ATTEMPTS_PER_SESSION,
    EXIT_MAX_CANCEL_REQUESTS_PER_ATTEMPT,
    EXIT_MAX_EXPIRED_SESSIONS,
    EXIT_REPRICE_MIN_SPACING_MANDATORY_SECONDS,
    EXIT_REPRICE_MIN_SPACING_SECONDS,
    EXIT_RETRIES_EXHAUSTED_EVENT_TYPE,
    EXIT_UNRESOLVED_ALERT_SECONDS,
    POSITION_NEEDS_ATTENTION,
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
from empirical_platform.usecases.entry_remainder_protection import (
    EntryRemainderProtector,
    EntryRemainderStatus,
    entry_remainder_applies,
)
from empirical_platform.usecases.position_exit import (
    MAXIMUM_EXIT_PREVIEW_AGE_SECONDS,
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
    "PLAN_EVALUATION_ERROR_EVENT_TYPE",
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


class PlanOutcomeKind(StrEnum):
    MONITORING = "MONITORING"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NO_QUOTE = "NO_QUOTE"
    EXIT_CLAIMED = "EXIT_CLAIMED"
    EXIT_ALREADY_CLAIMED = "EXIT_ALREADY_CLAIMED"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    EXIT_ALREADY_IN_PROGRESS = "EXIT_ALREADY_IN_PROGRESS"
    EXIT_RECONCILED = "EXIT_RECONCILED"
    #: RELIABLE EXIT MANAGEMENT: a previous exit generation ended unfilled (or is live) and
    #: the next send/replace is deliberately waiting for the next regular session.
    EXIT_WAITING_FOR_MARKET = "EXIT_WAITING_FOR_MARKET"
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
    #: PARTIAL ENTRY PROTECTION: the entry is partially filled and its remainder is being
    #: cancelled (see `usecases.entry_remainder_protection`). Exit management for the filled
    #: shares starts the tick the broker reports the entry terminal.
    ENTRY_REMAINDER_CANCEL_REQUESTED = "ENTRY_REMAINDER_CANCEL_REQUESTED"


@dataclass(frozen=True, slots=True)
class PlanEvaluationOutcome:
    plan_id: str
    entry_intent_governance_id: str
    kind: PlanOutcomeKind
    detail: str


#: Durable event recorded (at most once per plan, error type and hour) when evaluating a plan
#: raised unexpectedly.
PLAN_EVALUATION_ERROR_EVENT_TYPE = "PLAN_EVALUATION_ERROR"

#: Generation slots a plan can ever use (abandoned stale slots included). A hard bound.
_MAX_PLAN_SLOTS = 64

_INACTIVE_STATES: frozenset[PositionExitState] = frozenset(
    {PositionExitState.CANCELED, PositionExitState.REJECTED, PositionExitState.EXPIRED}
)
#: States in which the outcome of a send is not yet known: reconcile, never resend.
_UNRESOLVED_STATES: frozenset[PositionExitState] = frozenset(
    {
        PositionExitState.DISPATCH_CLAIMED,
        PositionExitState.SUBMISSION_IN_PROGRESS,
        PositionExitState.SUBMISSION_UNKNOWN,
    }
)

_MARKET_CLOSED_DETAIL = (
    POSITION_NEEDS_ATTENTION
    + " The market is not in a regular trading session; exits are not dispatched outside "
    "regular hours. Nothing was sent; this attempt will be retried the next time the plan is "
    "evaluated."
)


def _spacing_seconds(kind: ExitTriggerKind) -> int:
    return (
        EXIT_REPRICE_MIN_SPACING_MANDATORY_SECONDS
        if kind is ExitTriggerKind.MANDATORY_EXIT
        else EXIT_REPRICE_MIN_SPACING_SECONDS
    )


def _slot_token(plan: ApprovedPlan, kind: ExitTriggerKind, slot: int) -> str:
    material = f"{plan.plan_id}|{kind.value}|{slot}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:36]


# Slot 0 keeps the ORIGINAL ids (every already-claimed plan resumes unchanged); slot g >= 1 is
# a digest, so the id can never overflow the 64-character identifier limit.
def _preview_id(plan: ApprovedPlan, kind: ExitTriggerKind, slot: int = 0) -> str:
    if slot == 0:
        return f"XPV-plan-{plan.plan_id}-{kind.value}"
    return f"XPV-pg{slot}-{_slot_token(plan, kind, slot)}"


def _authorization_id(plan: ApprovedPlan, kind: ExitTriggerKind, slot: int = 0) -> str:
    if slot == 0:
        return f"XAU-plan-{plan.plan_id}-{kind.value}"
    return f"XAU-pg{slot}-{_slot_token(plan, kind, slot)}"


def _attempt_id(plan: ApprovedPlan, kind: ExitTriggerKind, slot: int = 0) -> str:
    if slot == 0:
        return f"XAT-plan-{plan.plan_id}-{kind.value}"
    return f"XAT-pg{slot}-{_slot_token(plan, kind, slot)}"


def _slot_of(plan: ApprovedPlan, kind: ExitTriggerKind, attempt_id: str) -> int | None:
    for slot in range(_MAX_PLAN_SLOTS):
        if _attempt_id(plan, kind, slot) == attempt_id:
            return slot
    return None


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
        "_events",
        "_broker",
        "_market_data",
        "_preview_handler",
        "_authorize_handler",
        "_submit_handler",
        "_reconcile_handler",
        "_cancel_handler",
        "_entry_protector",
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
        entry_remainder_protector: EntryRemainderProtector | None = None,
    ) -> None:
        #: PARTIAL ENTRY PROTECTION. `None` disables it (a composition with no Store B entry
        #: repositories); every production composition passes one.
        self._entry_protector = entry_remainder_protector
        self._plans = plans
        self._external_closures = external_closures
        self._previews = previews
        self._authorizations = authorizations
        self._attempts = exit_attempts
        self._events = events
        self._broker = broker
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
            outcomes.append(self._isolated(plan, now, self._evaluate_unclaimed))
        for plan in self._list_claimed_unresolved(limit=500):
            outcomes.append(self._isolated(plan, now, self._resume_claimed))
        return tuple(outcomes)

    def _isolated(
        self,
        plan: ApprovedPlan,
        now: datetime,
        evaluate: Callable[..., PlanEvaluationOutcome],
    ) -> PlanEvaluationOutcome:
        """PLAN ISOLATION. One plan's unexpected exception (a lost uniqueness race, a broker
        error, a bad row) becomes a NEEDS_ATTENTION outcome for THAT plan, a durable event
        and a log line -- and the loop moves on, so it can never starve the other plans.
        `KeyboardInterrupt`/`SystemExit` are `BaseException`s and are deliberately NOT caught."""
        try:
            return evaluate(plan, now=now)
        except Exception as error:  # noqa: BLE001 - isolation is the point
            name = type(error).__name__
            if error.__cause__ is not None:
                name = f"{name} (caused by {type(error.__cause__).__name__})"
            message = str(error)[:200]
            _LOG.warning("plan %s evaluation raised %s: %s", plan.plan_id, name, message)
            detail = (
                f"{PLAN_EVALUATION_ERROR_EVENT_TYPE}: evaluating this plan raised {name}; it "
                "is retried on the next tick and every other plan was still evaluated"
            )
            try:
                self._record_event(
                    plan,
                    None,
                    PLAN_EVALUATION_ERROR_EVENT_TYPE,
                    f"{detail}: {message}",
                    now,
                    suffix=f"{name}|{now:%Y%m%dT%H}",
                    once=True,
                )
            except Exception as record_error:  # noqa: BLE001 - the log line above stands
                _LOG.warning(
                    "plan %s: the error event could not be recorded (%s)",
                    plan.plan_id,
                    type(record_error).__name__,
                )
            return self._outcome(plan, PlanOutcomeKind.NEEDS_ATTENTION, f"{detail}: {message}")

    # -- unclaimed plans: decide whether a trigger fires ------------------------------

    def _evaluate_unclaimed(self, plan: ApprovedPlan, *, now: datetime) -> PlanEvaluationOutcome:
        closure = self._external_closures.for_entry(plan.entry_intent_governance_id)
        if closure is not None:
            return self._externally_closed_outcome(plan, closure)
        assessment = self._assess.handle(plan.entry_intent_governance_id, at=now)
        if (
            not assessment.eligible
            and self._entry_protector is not None
            and assessment.entry_attempt is not None
            and entry_remainder_applies(assessment.entry_attempt)
        ):
            # PARTIAL ENTRY PROTECTION: the filled shares have no exit until the entry is
            # final, so cancel the remainder (bounded) and continue normally once it is.
            step = self._entry_protector.step(
                assessment.entry_attempt, now=now, urgent_reason=self._entry_urgency(plan, now=now)
            )
            if step.status is EntryRemainderStatus.CANCEL_REQUESTED:
                return self._outcome(
                    plan, PlanOutcomeKind.ENTRY_REMAINDER_CANCEL_REQUESTED, step.detail
                )
            if step.status is EntryRemainderStatus.NEEDS_ATTENTION:
                return self._outcome(plan, PlanOutcomeKind.NEEDS_ATTENTION, step.detail)
            if step.status is EntryRemainderStatus.WAITING:
                return self._outcome(plan, PlanOutcomeKind.NOT_ELIGIBLE, step.detail)
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

    def _entry_urgency(self, plan: ApprovedPlan, *, now: datetime) -> str | None:
        """Why a partial entry's remainder must be cancelled NOW: a STOP/TARGET condition is
        met on the current bid, or the mandatory-liquidation deadline has arrived. Pure of
        side effects; a missing quote simply means no price trigger is evidenced."""
        if now >= plan.mandatory_exit_deadline:
            return "the mandatory-liquidation deadline has arrived"
        try:
            last_price = _bid_as_decimal(self._market_data.fetch_quote(plan.symbol))
        except Exception:  # noqa: BLE001 - no quote => no price trigger evidenced
            return None
        if last_price is None:
            return None
        trigger = evaluate_exit_trigger(plan, last_price=last_price, now=now)
        if trigger is None:
            return None
        return f"a {trigger.value} condition is met (bid {last_price})"

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
            try:
                attempt = self._attempts.active_for_entry(plan.entry_intent_governance_id)
            except Exception:  # noqa: BLE001 - unreadable => treat as unresolved; resume isolates
                unresolved.append(plan)
                continue
            if attempt is None or not attempt.position_closed:
                unresolved.append(plan)
        return tuple(unresolved)

    def _resume_claimed(self, plan: ApprovedPlan, *, now: datetime) -> PlanEvaluationOutcome:
        closure = self._external_closures.for_entry(plan.entry_intent_governance_id)
        if closure is not None:
            return self._externally_closed_outcome(plan, closure)
        attempt = self._attempts.active_for_entry(plan.entry_intent_governance_id)
        if attempt is not None:
            # ALWAYS reconcile first, by the attempt's own deterministic client_order_id: no
            # decision below (cancel, replace, alert) is ever taken on stale local state.
            reconciled = self._reconcile_handler.handle(
                ReconcilePositionExitCommand(attempt_id=attempt.attempt_id, at=now)
            )
            if reconciled.state not in _INACTIVE_STATES:
                return self._manage_live(plan, reconciled, now=now)
        return self._rearm(plan, now=now)

    # -- RELIABLE EXIT MANAGEMENT: bounded cancel -> confirm -> new generation -------------
    #
    # STATE MACHINE (every transition re-derived from durable rows each tick):
    #
    #   (no attempt) --send g0--> LIVE --fills--> FILLED --verify zero--> closed
    #   LIVE (SUBMITTED/ACCEPTED/PARTIALLY_FILLED), unfilled for >= spacing, budget left,
    #        market open --cancel--> CANCEL_REQUESTED --broker reports canceled--> CANCELED
    #   CANCELED / EXPIRED / REJECTED (broker-confirmed terminal) --new generation g+1, a new
    #        preview/authorization/attempt/client_order_id, remaining quantity only--> LIVE
    #   SUBMISSION_UNKNOWN / IN_PROGRESS / CLAIMED: reconcile by client_order_id only; NEVER
    #        a resend; loud alert after EXIT_UNRESOLVED_ALERT_SECONDS
    #   budget spent (EXIT_MAX_ATTEMPTS_PER_SESSION, or EXIT_MAX_EXPIRED_SESSIONS) --> loud
    #        NEEDS_ATTENTION (+ durable EXIT_RETRIES_EXHAUSTED event); no further sends
    #
    # AT MOST ONE LIVE SELL: a new generation is sent only when `active_for_entry` is None,
    # i.e. every earlier attempt is CANCELED/REJECTED/EXPIRED as REPORTED BY THE BROKER for
    # that very order; the database additionally refuses a second active attempt per entry.

    def _manage_live(
        self, plan: ApprovedPlan, attempt: PositionExitAttempt, *, now: datetime
    ) -> PlanEvaluationOutcome:
        base = f"attempt {attempt.attempt_id} state={attempt.state.value}"
        if attempt.is_terminal:  # FILLED (verified or awaiting verification)
            return self._outcome(plan, PlanOutcomeKind.EXIT_RECONCILED, base)
        kind = plan.triggered_exit_kind
        assert kind is not None
        if _slot_of(plan, kind, attempt.attempt_id) is None:
            # Not an attempt this plan minted (an Owner's manual exit): reconcile only.
            return self._outcome(plan, PlanOutcomeKind.EXIT_RECONCILED, base)
        age = (now - attempt.claimed_at).total_seconds()
        if attempt.state in _UNRESOLVED_STATES:
            if age >= EXIT_UNRESOLVED_ALERT_SECONDS:
                return self._outcome(
                    plan,
                    PlanOutcomeKind.NEEDS_ATTENTION,
                    f"{base} has been unresolved for {int(age)}s; it is reconciled by "
                    "client_order_id every tick and is NEVER re-sent automatically",
                )
            return self._outcome(plan, PlanOutcomeKind.EXIT_RECONCILED, base)
        if age < _spacing_seconds(kind):
            return self._outcome(plan, PlanOutcomeKind.EXIT_RECONCILED, base)
        return self._cancel_step(plan, attempt, now=now, base=base)

    def _cancel_step(
        self, plan: ApprovedPlan, attempt: PositionExitAttempt, *, now: datetime, base: str
    ) -> PlanEvaluationOutcome:
        kind = plan.triggered_exit_kind
        assert kind is not None
        session, expired = self._session_view(plan, kind)
        if len(session) >= EXIT_MAX_ATTEMPTS_PER_SESSION:
            return self._exhausted(plan, session, expired, now=now, live=attempt)
        if self._market_is_open() is not True:
            return self._outcome(
                plan,
                PlanOutcomeKind.EXIT_WAITING_FOR_MARKET,
                f"{base}: not repriced while the market is not confirmed open",
            )
        events = self._events.for_entry(plan.entry_intent_governance_id)
        cancels = [
            e
            for e in events
            if e.attempt_id == attempt.attempt_id and e.event_type in EXIT_CANCEL_EVENT_TYPES
        ]
        if len(cancels) >= EXIT_MAX_CANCEL_REQUESTS_PER_ATTEMPT:
            return self._outcome(
                plan,
                PlanOutcomeKind.NEEDS_ATTENTION,
                f"{base}: {len(cancels)} cancel requests were not confirmed by the broker; "
                "no replacement is sent while this order may still be live",
            )
        if cancels:
            last_cancel = max(e.occurred_at for e in cancels)
            if (now - last_cancel).total_seconds() < _spacing_seconds(kind):
                return self._outcome(
                    plan, PlanOutcomeKind.EXIT_RECONCILED, f"{base}: cancel pending"
                )
        try:
            self._cancel_handler.handle(CancelPositionExitCommand(attempt.attempt_id, at=now))
        except PositionExitRefusedError as error:
            return self._outcome(plan, PlanOutcomeKind.NEEDS_ATTENTION, f"{base}: {error}")
        except Exception as error:  # noqa: BLE001 - cancel acknowledgement unknown
            # The DELETE may or may not have reached the broker. State is NOT advanced; the
            # attempt is reconciled by client_order_id next tick and no replacement is sent.
            self._record_event(
                plan,
                attempt,
                "EXIT_CANCEL_ERROR",
                f"cancel request raised {type(error).__name__}; outcome unknown",
                now,
                suffix=now.isoformat(),
            )
            return self._outcome(
                plan,
                PlanOutcomeKind.NEEDS_ATTENTION,
                f"{base}: cancel acknowledgement unknown ({type(error).__name__}); reconciling "
                "by client_order_id, no replacement until the broker reports it terminal",
            )
        # Observe the result NOW (still by client_order_id): an order that fills while the
        # cancel is in flight is FILLED here, and then no replacement exists to send.
        after = self._reconcile_handler.handle(
            ReconcilePositionExitCommand(attempt_id=attempt.attempt_id, at=now)
        )
        if after.state in _INACTIVE_STATES:
            return self._rearm(plan, now=now)
        return self._outcome(
            plan,
            PlanOutcomeKind.EXIT_RECONCILED,
            f"attempt {after.attempt_id} state={after.state.value}: cancel requested; the "
            "replacement waits until the broker reports this order terminal",
        )

    def _rearm(self, plan: ApprovedPlan, *, now: datetime) -> PlanEvaluationOutcome:
        """No live attempt exists (none yet, or every one broker-confirmed CANCELED /
        REJECTED / EXPIRED): send the next generation if the bounded budget allows."""
        kind = plan.triggered_exit_kind
        assert kind is not None
        session, expired = self._session_view(plan, kind)
        if len(session) >= EXIT_MAX_ATTEMPTS_PER_SESSION or expired >= EXIT_MAX_EXPIRED_SESSIONS:
            return self._exhausted(plan, session, expired, now=now, live=None)
        if session and (now - session[-1].claimed_at).total_seconds() < _spacing_seconds(kind):
            return self._outcome(
                plan,
                PlanOutcomeKind.EXIT_RECONCILED,
                f"attempt {session[-1].attempt_id} ended {session[-1].state.value}; the next "
                "generation waits for the minimum spacing",
            )
        if (session or expired) and self._market_is_open() is not True:
            return self._outcome(
                plan,
                PlanOutcomeKind.EXIT_WAITING_FOR_MARKET,
                "the previous exit ended without closing the position; the next generation is "
                "armed for the next regular session",
            )
        return self._attempt_exit(plan, now=now, just_claimed=False, generation=len(session))

    def _session_view(
        self, plan: ApprovedPlan, kind: ExitTriggerKind
    ) -> tuple[list[PositionExitAttempt], int]:
        """This plan's attempts in the CURRENT session (after the last EXPIRED one) and the
        number of sessions that already expired. Derived from durable rows only."""
        ours = [
            a
            for a in self._attempts.for_entry(plan.entry_intent_governance_id)
            if _slot_of(plan, kind, a.attempt_id) is not None
        ]
        expired = sum(1 for a in ours if a.state is PositionExitState.EXPIRED)
        last_expired = max(
            (i for i, a in enumerate(ours) if a.state is PositionExitState.EXPIRED), default=-1
        )
        return ours[last_expired + 1 :], expired

    def _exhausted(
        self,
        plan: ApprovedPlan,
        session: Sequence[PositionExitAttempt],
        expired: int,
        *,
        now: datetime,
        live: PositionExitAttempt | None,
    ) -> PlanEvaluationOutcome:
        detail = (
            f"{EXIT_RETRIES_EXHAUSTED_EVENT_TYPE}: {len(session)} exit attempt(s) this session "
            f"and {expired} expired session(s) did not close the position; no further orders "
            "are sent automatically"
            + (
                f". The last order ({live.attempt_id}, {live.state.value}) is left working at "
                "the broker and is still reconciled every tick"
                if live is not None
                else ""
            )
            + ". The Owner must close or review this position."
        )
        self._record_event(
            plan,
            None,
            EXIT_RETRIES_EXHAUSTED_EVENT_TYPE,
            detail,
            now,
            suffix=f"{len(session)}|{expired}",
            once=True,
        )
        return self._outcome(plan, PlanOutcomeKind.NEEDS_ATTENTION, detail)

    def _market_is_open(self) -> bool | None:
        try:
            return bool(self._broker.fetch_clock().is_open)
        except Exception:  # noqa: BLE001 - an unreadable clock is "not confirmed open"
            return None

    def _select_slot(self, plan: ApprovedPlan, kind: ExitTriggerKind, now: datetime) -> int | None:
        """The generation slot to (re)use. Slot ids are deterministic in `(plan, kind, slot)`.
        A slot whose attempt exists is spent; one whose preview/authorization went stale
        without ever being used is ABANDONED (a fresh one is minted); otherwise it is
        resumed, so a crash between Preview, Authorize and Submit never mints a duplicate."""
        for slot in range(_MAX_PLAN_SLOTS):
            if self._attempts.get(_attempt_id(plan, kind, slot)) is not None:
                continue
            preview = self._previews.get(_preview_id(plan, kind, slot))
            if preview is None:
                return slot
            if (now - preview.created_at).total_seconds() > MAXIMUM_EXIT_PREVIEW_AGE_SECONDS:
                continue
            authorization = self._authorizations.get(_authorization_id(plan, kind, slot))
            if authorization is None:
                return slot
            if authorization.is_consumed or now >= authorization.expires_at:
                continue
            # P2-5: the submit handler spends the entry's LATEST authorization, not this
            # slot's. If a later one exists (e.g. an Owner's manual exit authorized after
            # this slot was pre-minted) and is itself unusable, resuming this slot would be
            # refused ("no unused human exit authorization exists") on every tick until this
            # authorization expires (<= 300 s) -- a stall that must not touch a mandatory
            # exit. Abandon the slot instead; the next one is minted fresh (its authorization
            # becomes the latest). A usable later authorization keeps the old behaviour.
            latest = self._authorizations.latest_for_entry(plan.entry_intent_governance_id)
            if (
                latest is not None
                and latest.authorization_id != authorization.authorization_id
                and (latest.is_consumed or now >= latest.expires_at)
            ):
                continue
            return slot
        return None

    def _record_event(
        self,
        plan: ApprovedPlan,
        attempt: PositionExitAttempt | None,
        event_type: str,
        detail: str,
        at: datetime,
        *,
        suffix: str = "",
        once: bool = False,
    ) -> None:
        digest = hashlib.sha256(
            "|".join(
                (plan.plan_id, attempt.attempt_id if attempt else "-", event_type, suffix)
            ).encode("utf-8")
        ).hexdigest()
        event_id = f"XEV-{digest[:40]}"
        if once and any(
            e.event_id == event_id for e in self._events.for_entry(plan.entry_intent_governance_id)
        ):
            return
        self._events.append(
            PositionExitEvent(
                event_id=event_id,
                entry_intent_governance_id=plan.entry_intent_governance_id,
                attempt_id=None if attempt is None else attempt.attempt_id,
                event_type=event_type,
                occurred_at=at,
                detail=detail[:500],
            )
        )

    @staticmethod
    def _outcome(plan: ApprovedPlan, kind: PlanOutcomeKind, detail: str) -> PlanEvaluationOutcome:
        return PlanEvaluationOutcome(plan.plan_id, plan.entry_intent_governance_id, kind, detail)

    # -- the shared, idempotent Preview -> Authorize -> Submit sequence ---------------

    def _attempt_exit(
        self, plan: ApprovedPlan, *, now: datetime, just_claimed: bool, generation: int = 0
    ) -> PlanEvaluationOutcome:
        assert plan.triggered_exit_kind is not None
        kind = plan.triggered_exit_kind
        # The regular-hours gate (also enforced inside the submit handler, unchanged) is
        # checked FIRST so a shut market never mints a preview/authorization that would
        # only expire unused.
        market = self._market_is_open()
        if market is not True:
            return self._outcome(
                plan,
                PlanOutcomeKind.NEEDS_ATTENTION,
                _MARKET_CLOSED_DETAIL
                if market is False
                else POSITION_NEEDS_ATTENTION
                + " The broker clock could not be read; nothing was sent and this attempt "
                "will be retried the next time the plan is evaluated.",
            )
        slot = self._select_slot(plan, kind, now)
        if slot is None:
            return self._outcome(
                plan,
                PlanOutcomeKind.NEEDS_ATTENTION,
                "every exit generation slot for this plan is spent or stale; nothing was sent",
            )
        try:
            preview = self._previews.get(_preview_id(plan, kind, slot))
            if preview is None:
                preview = self._preview_handler.handle(
                    PreviewPositionExitCommand(
                        entry_intent_governance_id=plan.entry_intent_governance_id,
                        preview_id=_preview_id(plan, kind, slot),
                        created_at=now,
                        reprice_generation=generation,
                    )
                )
            authorization = self._authorizations.get(_authorization_id(plan, kind, slot))
            if authorization is None:
                authorization = self._authorize_handler.handle(
                    AuthorizePositionExitCommand(
                        authorization_id=_authorization_id(plan, kind, slot),
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
                    attempt_id=_attempt_id(plan, kind, slot),
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
            f"generation={generation} dispatched={result.dispatched}"
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
