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

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    evaluate_exit_trigger,
)
from empirical_platform.decision_candidate.approved_plan_repositories import (
    ApprovedPlanRepository,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    ExecutionAttemptRepository,
    PaperMarketDataPort,
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
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource
from empirical_platform.usecases.position_exit import (
    AssessPositionExitHandler,
    AuthorizePositionExitCommand,
    AuthorizePositionExitHandler,
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
    "PlanEvaluationOutcome",
    "PlanManagerThread",
    "PositionPlanManager",
]

_LOG = logging.getLogger("empirical_platform.position_plan_manager")

#: Many evaluation opportunities inside `MANDATORY_EXIT_SAFETY_BUFFER_SECONDS` (120s), so
#: a mandatory exit is not at the mercy of a single poll landing exactly on the deadline.
DEFAULT_POLL_INTERVAL_SECONDS = 15


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


@dataclass(frozen=True, slots=True)
class PlanEvaluationOutcome:
    plan_id: str
    entry_intent_governance_id: str
    kind: PlanOutcomeKind
    detail: str


def _preview_id(plan: ApprovedPlan, kind: ExitTriggerKind) -> str:
    return f"XPV-plan-{plan.plan_id}-{kind.value}"


def _authorization_id(plan: ApprovedPlan, kind: ExitTriggerKind) -> str:
    return f"XAU-plan-{plan.plan_id}-{kind.value}"


def _attempt_id(plan: ApprovedPlan, kind: ExitTriggerKind) -> str:
    return f"XAT-plan-{plan.plan_id}-{kind.value}"


class PositionPlanManager:
    """One poll tick over every durably-tracked approved plan. No broker call of its own;
    everything is delegated to the existing, proven exit-pipeline handlers."""

    __slots__ = (
        "_plans",
        "_assess",
        "_previews",
        "_authorizations",
        "_attempts",
        "_market_data",
        "_preview_handler",
        "_authorize_handler",
        "_submit_handler",
        "_reconcile_handler",
    )

    def __init__(
        self,
        *,
        plans: ApprovedPlanRepository,
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
    ) -> None:
        self._plans = plans
        self._previews = previews
        self._authorizations = authorizations
        self._attempts = exit_attempts
        self._market_data = market_data
        self._assess = AssessPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            exit_attempts=exit_attempts,
            broker=broker,
        )
        self._preview_handler = PreviewPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            exit_attempts=exit_attempts,
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

    def evaluate_once(self, *, now: datetime) -> tuple[PlanEvaluationOutcome, ...]:
        """One poll tick. Safe to call repeatedly, from any process, at any time -- every
        decision it makes is re-derived from durable state, never remembered in RAM."""
        outcomes: list[PlanEvaluationOutcome] = []
        for plan in self._plans.list_unclaimed(500):
            outcomes.append(self._evaluate_unclaimed(plan, now=now))
        for plan in self._list_claimed_unresolved(limit=500):
            outcomes.append(self._resume_claimed(plan, now=now))
        return tuple(outcomes)

    # -- unclaimed plans: decide whether a trigger fires ------------------------------

    def _evaluate_unclaimed(self, plan: ApprovedPlan, *, now: datetime) -> PlanEvaluationOutcome:
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
        claimed = self._plans.claim_exit_trigger(plan.plan_id, kind=trigger, claimed_at=now)
        if claimed is None:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_ALREADY_CLAIMED,
                "another evaluation already claimed this plan's exit trigger",
            )
        return self._attempt_exit(claimed, now=now, just_claimed=True)

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
        attempt = self._attempts.active_for_entry(plan.entry_intent_governance_id)
        if attempt is not None and not attempt.is_terminal:
            reconciled = self._reconcile_handler.handle(
                ReconcilePositionExitCommand(attempt_id=attempt.attempt_id, at=now)
            )
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_RECONCILED,
                f"attempt {reconciled.attempt_id} state={reconciled.state.value}",
            )
        return self._attempt_exit(plan, now=now, just_claimed=False)

    # -- the shared, idempotent Preview -> Authorize -> Submit sequence ---------------

    def _attempt_exit(
        self, plan: ApprovedPlan, *, now: datetime, just_claimed: bool
    ) -> PlanEvaluationOutcome:
        assert plan.triggered_exit_kind is not None
        kind = plan.triggered_exit_kind
        try:
            preview = self._previews.get(_preview_id(plan, kind))
            if preview is None:
                preview = self._preview_handler.handle(
                    PreviewPositionExitCommand(
                        entry_intent_governance_id=plan.entry_intent_governance_id,
                        preview_id=_preview_id(plan, kind),
                        created_at=now,
                    )
                )
            authorization = self._authorizations.get(_authorization_id(plan, kind))
            if authorization is None:
                authorization = self._authorize_handler.handle(
                    AuthorizePositionExitCommand(
                        authorization_id=_authorization_id(plan, kind),
                        preview_id=preview.preview_id,
                        expected_request_fingerprint=preview.request_fingerprint,
                        authorized_by=plan.system_identity,
                        authorized_at=now,
                    )
                )
            result = self._submit_handler.handle(
                SubmitAuthorizedPositionExitCommand(
                    entry_intent_governance_id=plan.entry_intent_governance_id,
                    attempt_id=_attempt_id(plan, kind),
                    at=now,
                )
            )
        except PositionExitRefusedError as error:
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


class PlanManagerThread:
    """Runs `PositionPlanManager.evaluate_once` on a fixed interval, inside THIS process.

    Started alongside the WSGI server in the SAME console process (see
    `entrypoints/_v1_console_composition.py`) -- never a second process -- and stoppable
    for a clean shutdown. Exceptions from one tick are logged and never kill the loop: a
    manager that stops polling after one bad tick is worse than one that keeps trying.
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

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="position-plan-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._manager.evaluate_once(now=self._now())
            except Exception:  # noqa: BLE001 - one bad tick must never stop the loop
                _LOG.exception("position plan manager tick failed")
            self._stop.wait(self._interval)
