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
    #: RELEASE v1: a durable `ExternalPositionClosure` record exists for this entry (the
    #: position was closed outside this platform's own exit pipeline -- see
    #: `usecases.record_external_position_closure`). The manager will never evaluate a
    #: trigger, claim one, or attempt Preview/Authorize/Submit for this plan again.
    EXTERNALLY_CLOSED = "EXTERNALLY_CLOSED"


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
    ) -> None:
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
        claimed = self._plans.claim_exit_trigger(plan.plan_id, kind=trigger, claimed_at=now)
        if claimed is None:
            return PlanEvaluationOutcome(
                plan.plan_id,
                plan.entry_intent_governance_id,
                PlanOutcomeKind.EXIT_ALREADY_CLAIMED,
                "another evaluation already claimed this plan's exit trigger",
            )
        return self._attempt_exit(claimed, now=now, just_claimed=True)

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
        closure = self._external_closures.for_entry(plan.entry_intent_governance_id)
        if closure is not None:
            return self._externally_closed_outcome(plan, closure)
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
                    attempt_id=_attempt_id(plan, kind),
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
                self._manager.evaluate_once(now=self._now())
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
