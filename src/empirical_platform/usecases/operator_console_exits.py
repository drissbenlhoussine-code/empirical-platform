"""MILESTONE-087 -- the Operator Console's exit services: review, confirm, follow, close.

THE OPERATOR'S VIEW OF A POSITION EXIT, over the M087 handlers. Nothing here decides
whether a position may be closed: `AssessPositionExitHandler` and the exit handlers do, and
this module asks them and renders their answers. Every action is a request to a handler and
never a write to an exit table.

THE TWO-STAGE EXIT. "Review exit" freezes a preview (what the Owner is shown: verified
holding, exit quantity, SELL TO CLOSE, order type, limit price, account, environment,
entry average fill, current price evidence, fingerprint, mandatory liquidation deadline,
authorization expiry) and a signed ticket bound to the preview's version and fingerprint.
"CONFIRM EXIT" re-reads everything -- position, entry, attribution, kill switch, preview,
ticket, expiry -- through the handlers and refuses anything changed; only then does it
authorize and submit, with identifiers DERIVED from the entry intent and preview version so
a duplicate click, a second tab, a refresh or a restart can never create a second SELL.

POSITION CLOSED IS SHOWN ONLY WHEN VERIFIED: a filled exit whose broker position was
verified at zero by reconciliation. Until then the exit is "in progress".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.approved_plan_repositories import ApprovedPlanRepository
from empirical_platform.decision_candidate.external_position_closure_repositories import (
    ExternalPositionClosureRepository,
    NullExternalPositionClosureRepository,
)
from empirical_platform.decision_candidate.paper_execution import ExecutionAttempt
from empirical_platform.decision_candidate.paper_execution_repositories import (
    ExecutionAttemptRepository,
    ExecutionKillSwitchRepository,
    PaperMarketDataPort,
)
from empirical_platform.decision_candidate.position_exit import (
    MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS,
    POSITION_CLOSED_VERIFIED_EVENT_TYPE,
    POSITION_NOT_ZERO_AFTER_FILL_EVENT_TYPE,
    PositionExitAttempt,
    PositionExitEvent,
    PositionExitState,
    RealizedResult,
    is_overdue_recovery_authorization,
    realized_result,
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
from empirical_platform.decision_candidate.trade_approval import ApprovedOrderIntent
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource, PaperTimeUncertainError
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.operator_console import (
    NOT_AVAILABLE,
    ActionOutcome,
    ConfirmationTicket,
    ConsoleRefusalError,
    HumanState,
    Signer,
    TimelineStep,
    position_is_open,
)
from empirical_platform.usecases.position_exit import (
    POSITION_NEEDS_ATTENTION,
    AssessPositionExitHandler,
    AuthorizeOverduePositionRecoveryCommand,
    AuthorizeOverduePositionRecoveryHandler,
    AuthorizePositionExitCommand,
    AuthorizePositionExitHandler,
    CancelPositionExitCommand,
    CancelPositionExitHandler,
    GrantOverduePositionRecoveryApprovalCommand,
    GrantOverduePositionRecoveryApprovalHandler,
    PositionAssessment,
    PositionExitRefusedError,
    PreviewPositionExitCommand,
    PreviewPositionExitHandler,
    ReconcilePositionExitCommand,
    ReconcilePositionExitHandler,
    SubmitAuthorizedPositionExitCommand,
    SubmitAuthorizedPositionExitHandler,
)

__all__ = [
    "CATEGORY_EXIT_IN_PROGRESS",
    "CATEGORY_EXPIRED_UNSUBMITTED",
    "CATEGORY_EXTERNALLY_CLOSED",
    "CATEGORY_NEEDS_ATTENTION",
    "CATEGORY_OPEN_POSITION",
    "CATEGORY_POSITION_CLOSED",
    "CATEGORY_WORKING_ENTRY",
    "DEADLINE_MISSED_TRUTH",
    "EXIT_ACTION",
    "ExitRepositories",
    "ExitReviewView",
    "ExitSummary",
    "NullExternalPositionClosureRepository",
    "PositionExitConsole",
    "blocked_exit_alert",
    "deadline_status",
    "human_state_for_exit",
]

EXIT_ACTION = "EXIT"
CATEGORY_WORKING_ENTRY = "Working entry order"
CATEGORY_OPEN_POSITION = "Open position"
CATEGORY_EXIT_IN_PROGRESS = "Exit in progress"
CATEGORY_NEEDS_ATTENTION = "Needs attention"
CATEGORY_POSITION_CLOSED = "Position closed"
#: RELEASE v1 EXTERNAL POSITION CLOSURE VISIBILITY FIX. A durable `ExternalPositionClosure`
#: exists for this entry: its position was closed OUTSIDE this platform's own exit pipeline
#: (an Owner's manual broker-dashboard sale), independently of whether a `PositionExitAttempt`
#: was ever dispatched for it (usually none was -- that is exactly why this category exists).
#: Distinct from `CATEGORY_POSITION_CLOSED`, which means a platform-dispatched exit was
#: VERIFIED closed: callers must not conflate the two, since only the latter has a
#: `PositionExitAttempt` to show realized P&L for.
CATEGORY_EXTERNALLY_CLOSED = "Closed externally"
#: RELEASE v1 EXTERNAL POSITION CLOSURE VISIBILITY FIX. Zero entry attempts were ever
#: dispatched for this intent AND its `ApprovedOrderIntent.expires_at` has already passed:
#: this was never a live working order and never will be one. Distinct from
#: `CATEGORY_WORKING_ENTRY`, which means a fresh, still-live intent may yet be dispatched.
CATEGORY_EXPIRED_UNSUBMITTED = "Expired — never submitted"
DEADLINE_MISSED_TRUTH = "Position remains open — Owner action was not completed."
_DEADLINE_MISSED_EVENT = "LIQUIDATION_DEADLINE_PASSED_POSITION_OPEN"
_URGENCY_WINDOW = timedelta(minutes=30)

_EXIT_WORDS: dict[PositionExitState, HumanState] = {
    PositionExitState.DISPATCH_CLAIMED: HumanState.SUBMITTED,
    PositionExitState.SUBMISSION_IN_PROGRESS: HumanState.SUBMITTED,
    PositionExitState.SUBMITTED: HumanState.SUBMITTED,
    PositionExitState.ACCEPTED: HumanState.ACCEPTED,
    PositionExitState.PARTIALLY_FILLED: HumanState.PARTIALLY_FILLED,
    PositionExitState.FILLED: HumanState.FILLED,
    PositionExitState.CANCEL_REQUESTED: HumanState.CANCEL_REQUESTED,
    PositionExitState.CANCELED: HumanState.CANCELLED,
    PositionExitState.REJECTED: HumanState.REJECTED,
    PositionExitState.EXPIRED: HumanState.EXPIRED,
    PositionExitState.SUBMISSION_UNKNOWN: HumanState.NEEDS_ATTENTION,
}

_RECONCILABLE = frozenset(
    {
        PositionExitState.SUBMISSION_IN_PROGRESS,
        PositionExitState.SUBMITTED,
        PositionExitState.ACCEPTED,
        PositionExitState.PARTIALLY_FILLED,
        PositionExitState.CANCEL_REQUESTED,
        PositionExitState.SUBMISSION_UNKNOWN,
    }
)


def human_state_for_exit(attempt: PositionExitAttempt) -> HumanState:
    if attempt.state is PositionExitState.REJECTED and attempt.failure_code == "NOT_SENT":
        return HumanState.BLOCKED
    return _EXIT_WORDS[attempt.state]


def _money(value: Decimal | None) -> str:
    return NOT_AVAILABLE if value is None else f"{value:,.2f}"


def _broker_noun(environment: str) -> str:
    """MILESTONE-089. The broker described in operator-facing text, never hardcoded.

    Mirrors `usecases.operator_console.OperatorConsoleService._broker_noun`: the same wording
    for the same two environments, so an Owner reading either console sees the same phrase.
    """
    return "simulated broker" if environment == "SIMULATION" else "Alpaca paper endpoint"


def _account_noun(environment: str) -> str:
    return "Simulation account" if environment == "SIMULATION" else "Alpaca Paper account"


def _closed_round_trip_label(environment: str) -> str:
    return "simulation" if environment == "SIMULATION" else "Alpaca Paper"


def _quantity(value: Decimal | int | None) -> str:
    if value is None:
        return NOT_AVAILABLE
    decimal = Decimal(value)
    return (
        str(decimal.quantize(Decimal(1)))
        if decimal == decimal.to_integral_value()
        else str(decimal.normalize())
    )


def deadline_status(
    *, deadline: datetime, now: datetime, position_open: bool, position_closed: bool
) -> tuple[str, str]:
    """(tone, sentence) for the mandatory liquidation deadline. Never executes anything.

    MILESTONE-089 FIX: `deadline` is a timezone-aware instant that may carry ANY offset
    (`operator_timezone`, e.g. Europe/Helsinki) -- `strftime` prints whatever wall-clock hour
    that offset holds, so appending the literal "UTC" without first converting was a
    mislabeling bug (a 15:45 local reading shown as "15:45 UTC" when the instant is actually
    12:45 UTC). `.astimezone(UTC)` here matches `entrypoints._operator_console_html._when`'s
    own conversion exactly, so the banner and the terms table always name the same instant.
    The comparisons below (`now >= deadline`, `deadline - now`) are untouched: datetime
    comparison and subtraction are already timezone-correct regardless of display formatting.
    """
    when = deadline.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if position_closed:
        return "info", f"Position closed. Mandatory liquidation deadline was {when}."
    if not position_open:
        return "info", f"Mandatory liquidation deadline {when}."
    if now >= deadline:
        return "danger", f"{DEADLINE_MISSED_TRUTH} Deadline was {when}. No exit is sent by itself."
    if deadline - now <= _URGENCY_WINDOW:
        minutes = max(1, int((deadline - now).total_seconds() // 60))
        return (
            "warn",
            f"Mandatory liquidation deadline in about {minutes} minute(s) ({when}). The Owner "
            "must review and confirm the exit; nothing closes by itself.",
        )
    return "info", f"Mandatory liquidation deadline {when}. Only the Owner can close the position."


def blocked_exit_alert(
    *, deadline_tone: str, assessment_refusals: tuple[str, ...], position_open: bool
) -> str | None:
    """An explicit, visible escalation for the one gap RELEASE v1's own incident review
    found in the existing visibility: `deadline_status` already warns as the mandatory
    liquidation deadline nears (`deadline_tone` "warn") or shouts once it has passed
    ("danger"), and `AssessPositionExitHandler.handle(...).refusals` already says WHY the
    automatic manager cannot act -- but nothing today says BOTH at once. An Owner who sees
    only the deadline banner's "review and confirm the exit" has no way to know a manual
    confirm would ALSO be refused for the identical reason the automatic manager is stuck
    on (the live incident: a competing-entry attribution refusal silently stalled the
    automatic MANDATORY_EXIT with no owner-visible status at all).

    Returns `None` whenever there is nothing to escalate: the position is not open, no
    refusal is on record for it, or the deadline is not yet inside its own urgency window
    (`deadline_tone` is still "info"). Pure and read-only -- it never executes anything,
    never authorizes anything, and never drops or paraphrases a refusal: the exact refusal
    text `AssessPositionExitHandler` already produced is always included verbatim.
    """
    if not position_open or not assessment_refusals or deadline_tone == "info":
        return None
    when = "already past" if deadline_tone == "danger" else "approaching"
    reason = "; ".join(assessment_refusals)
    return (
        f"The mandatory liquidation deadline is {when}, and the automatic exit cannot act "
        f"on this position right now: {reason}. A manual confirm will be refused for the "
        "same reason until this is resolved -- Owner review of the underlying block is "
        "required."
    )


@dataclass(frozen=True, slots=True)
class ExitRepositories:
    previews: PositionExitPreviewRepository
    authorizations: PositionExitAuthorizationRepository
    attempts: PositionExitAttemptRepository
    acknowledgements: PositionExitAcknowledgementRepository
    rounds: PositionExitRoundRepository
    events: PositionExitEventRepository


@dataclass(frozen=True, slots=True)
class ExitSummary:
    attempt_id: str
    state: HumanState
    raw_state: str
    quantity: str
    filled_quantity: str
    filled_avg_price: str
    limit_price: str
    broker_order_id: str
    claimed_at: datetime | None
    submitted_at: datetime | None
    terminal_at: datetime | None
    position_closed: bool
    closed_verified_at: datetime | None
    outcome_known: bool
    can_cancel: bool
    pending_reason: str | None
    warnings: tuple[str, ...]
    timeline: tuple[TimelineStep, ...]
    realized: RealizedResult | None
    result_text: str


@dataclass(frozen=True, slots=True)
class ExitReviewView:
    intent_id: str
    preview_id: str
    preview_version: int
    symbol: str
    current_holding: str
    exit_quantity: str
    side: str
    order_type: str
    limit_price: str
    account: str
    environment: str
    entry_avg_fill_price: str
    current_bid: str
    current_ask: str
    quote_captured_at: datetime | None
    #: MILESTONE-089 Phase 5: the broker position evidence timestamp -- when
    #: `broker_position_quantity` (the current-holding figure above) was read, distinct from
    #: `quote_captured_at` (the price evidence timestamp).
    position_captured_at: datetime
    #: MILESTONE-089 Phase 5: the exact deterministic client order id this exit would submit
    #: under, safely derivable and shown before final confirmation because it is DERIVED from
    #: already-persisted identity (`derive_exit_client_order_id`), never a value this submits
    #: early or that could be replayed to create a second order.
    client_order_id: str
    fingerprint_short: str
    liquidation_deadline: datetime
    deadline_tone: str
    deadline_note: str
    authorization_expires_at: datetime
    ticket: str
    kill_switch_engaged: bool
    full_close_warning: str


class PositionExitConsole:
    """Review, confirm, follow and verify exits, over the M087 handlers."""

    def __init__(
        self,
        *,
        exits: ExitRepositories,
        intents: ApprovedOrderIntentRepository,
        entry_attempts: ExecutionAttemptRepository,
        external_closures: ExternalPositionClosureRepository,
        configurations: OperatorTradingConfigurationRepository,
        kill_switch: ExecutionKillSwitchRepository,
        broker: ExitBrokerPort,
        market_data: PaperMarketDataPort,
        signer: Signer,
        time_source: PaperTimeSource,
        clock: Callable[[], datetime],
        environment: str,
        #: RELEASE v1 RECOVERY HARDENING. Read-only here: the ORIGINAL Owner-approved plan,
        #: consulted ONLY by `confirm_overdue_recovery` to prove a fresh recovery approval id
        #: is not the original `owner_approval_id` replayed. Never written to by this console.
        #: `None` for a capability with no full-plan-approval concept at all (SIMULATION);
        #: `confirm_overdue_recovery` refuses cleanly rather than requiring every composition
        #: to wire up a plan repository it otherwise has no use for.
        plans: ApprovedPlanRepository | None = None,
        operator_identity: str = "owner",
        recovery_mode: bool = False,
    ) -> None:
        self._x = exits
        self._intents = intents
        self._entries = entry_attempts
        self._external_closures = external_closures
        self._configurations = configurations
        self._kill_switch = kill_switch
        self._broker = broker
        self._market_data = market_data
        self._signer = signer
        self._time = time_source
        self._clock = clock
        self._environment = environment
        self._plans = plans
        self._operator = operator_identity
        #: RELEASE v1 RECOVERY HARDENING. When set, `confirm` refuses before touching any
        #: state: a fail-closed, read-only startup mode must dispatch nothing, automatically
        #: or manually, while still leaving `review`/`assess`/`refresh`/`summary` (Paper
        #: review, broker reconciliation and safety visibility) fully working. See
        #: `entrypoints.operator_console --recovery-mode`.
        self._recovery_mode = recovery_mode

    # -- reads -------------------------------------------------------------------------

    def assess(self, intent_id: str) -> PositionAssessment:
        return AssessPositionExitHandler(
            intents=self._intents,
            entry_attempts=self._entries,
            exit_attempts=self._x.attempts,
            external_closures=self._external_closures,
            broker=self._broker,
        ).handle(intent_id, at=self._clock())

    def latest_exit(self, intent_id: str) -> PositionExitAttempt | None:
        active = self._x.attempts.active_for_entry(intent_id)
        if active is not None:
            return active
        exits = self._x.attempts.for_entry(intent_id)
        return exits[-1] if exits else None

    def position_closed(self, intent_id: str) -> bool:
        active = self._x.attempts.active_for_entry(intent_id)
        return active is not None and active.position_closed

    def category(
        self,
        intent: ApprovedOrderIntent,
        entry: ExecutionAttempt | None,
        exit_attempt: PositionExitAttempt | None,
        *,
        now: datetime | None = None,
    ) -> str:
        """RELEASE v1 EXTERNAL POSITION CLOSURE VISIBILITY FIX. Consults
        `ExternalPositionClosureRepository` FIRST, regardless of whether a platform
        `PositionExitAttempt` exists at all -- an externally-closed entry usually has NONE
        (that is exactly the incident this closes: the Oct 9 entry showed as "Open position"
        because its only evidence of closure was never a `PositionExitAttempt`). Also
        distinguishes a genuinely still-live, not-yet-submitted intent from one that expired
        with zero entry attempts and will never be dispatched -- neither may ever display as
        "Open position" or "Working entry order".
        """
        if self._external_closures.for_entry(intent.intent_governance_id) is not None:
            return CATEGORY_EXTERNALLY_CLOSED
        if exit_attempt is not None and exit_attempt.position_closed:
            return CATEGORY_POSITION_CLOSED
        if exit_attempt is not None and exit_attempt.state not in {
            PositionExitState.CANCELED,
            PositionExitState.REJECTED,
            PositionExitState.EXPIRED,
        }:
            if not exit_attempt.outcome_is_known:
                return CATEGORY_NEEDS_ATTENTION
            return CATEGORY_EXIT_IN_PROGRESS
        if entry is None:
            moment = now if now is not None else self._clock()
            if intent.submission_state.value == "NOT_SUBMITTED" and moment >= intent.expires_at:
                return CATEGORY_EXPIRED_UNSUBMITTED
            return CATEGORY_WORKING_ENTRY
        if not entry.outcome_is_known:
            return CATEGORY_NEEDS_ATTENTION
        if entry.state.value == "FILLED" and position_is_open(entry):
            return CATEGORY_OPEN_POSITION
        if entry.state.value == "CANCELED" and position_is_open_after_cancel(entry):
            return CATEGORY_OPEN_POSITION
        return CATEGORY_WORKING_ENTRY

    def realized(self, entry: ExecutionAttempt | None, intent_id: str) -> RealizedResult | None:
        if entry is None:
            return None
        return realized_result(
            entry_avg_fill_price=entry.filled_avg_price,
            exit_attempt=self._x.attempts.active_for_entry(intent_id),
        )

    def summary(
        self, intent: ApprovedOrderIntent, entry: ExecutionAttempt | None, now: datetime
    ) -> ExitSummary | None:
        attempt = self.latest_exit(intent.intent_governance_id)
        if attempt is None:
            return None
        events = self._x.events.for_entry(intent.intent_governance_id)
        preview = None
        authorization = self._x.authorizations.get(attempt.authorization_id)
        if authorization is not None:
            preview = self._x.previews.get(authorization.preview_id)
        state = human_state_for_exit(attempt)
        warnings: list[str] = []
        pending: str | None = None
        if attempt.state is PositionExitState.SUBMISSION_UNKNOWN:
            pending = (
                "Outcome unknown — do not retry. The console keeps asking the broker about this "
                "exact exit order; it will never be sent again."
            )
        elif attempt.state in {PositionExitState.SUBMITTED, PositionExitState.ACCEPTED}:
            pending = "Waiting for the broker to fill the exit."
        elif attempt.state is PositionExitState.PARTIALLY_FILLED:
            pending = (
                "Partially filled; the rest is still working. The position is reduced, not closed."
            )
        elif attempt.state is PositionExitState.CANCEL_REQUESTED:
            pending = "Cancel requested; a request is not a cancellation."
        elif attempt.fully_filled and not attempt.position_closed:
            pending = (
                "Exit filled; waiting for reconciliation to verify the broker position at zero "
                "before the position is called closed."
            )
        elif attempt.state in {PositionExitState.CANCELED, PositionExitState.REJECTED}:
            pending = (
                "The exit did not close the position; it remains open and can be reviewed again."
            )
        for event in events:
            if event.attempt_id != attempt.attempt_id:
                continue
            if event.event_type == POSITION_NOT_ZERO_AFTER_FILL_EVENT_TYPE:
                warnings.append(
                    "The exit filled but the broker still holds shares; the position is NOT "
                    "closed. " + POSITION_NEEDS_ATTENTION
                )
            elif event.event_type in {
                "EXIT_IDENTITY_COLLISION_MISMATCH",
                "EXIT_IDENTITY_OBSERVED_NOT_ATTRIBUTED",
                "EXIT_RECONCILE_NOT_FOUND_KNOWN_ORDER",
                "EXIT_POSITION_VERIFICATION_FAILED",
            }:
                warnings.append(event.detail)
        realized = (
            None
            if entry is None
            else realized_result(entry_avg_fill_price=entry.filled_avg_price, exit_attempt=attempt)
        )
        label = _closed_round_trip_label(self._environment)
        if realized is not None:
            sign = "+" if realized.realized_pnl >= 0 else "−"
            result_text = (
                f"Closed round trip ({label}): {realized.quantity} @ "
                f"{_money(realized.entry_avg_fill_price)} → "
                f"{_money(realized.exit_avg_fill_price)}; "
                f"realized {sign}{_money(abs(realized.realized_pnl))} USD"
            )
        elif attempt.position_closed:
            result_text = (
                f"Position closed ({label}); realized result not computable from the record"
            )
        else:
            result_text = NOT_AVAILABLE
        reviewed_at = None if preview is None else preview.created_at
        confirmed_at = None if authorization is None else authorization.authorized_at
        accepted = (
            attempt.state
            in {
                PositionExitState.ACCEPTED,
                PositionExitState.PARTIALLY_FILLED,
                PositionExitState.FILLED,
                PositionExitState.CANCEL_REQUESTED,
                PositionExitState.CANCELED,
                PositionExitState.EXPIRED,
            }
            or attempt.acknowledged_at is not None
        )
        steps = [
            TimelineStep("Open position", None, True, f"entry {intent.intent_governance_id}"),
            TimelineStep("Exit reviewed", reviewed_at, preview is not None, ""),
            TimelineStep("Owner confirmed", confirmed_at, authorization is not None, ""),
            TimelineStep(
                "Exit submitted",
                attempt.submitted_at,
                attempt.submitted_at is not None and attempt.failure_code != "NOT_SENT",
                attempt.broker_order_id or "",
            ),
            TimelineStep("Accepted", attempt.acknowledged_at if accepted else None, accepted, ""),
        ]
        if attempt.is_terminal:
            label = {
                PositionExitState.FILLED: "Filled",
                PositionExitState.CANCELED: "Cancelled",
                PositionExitState.REJECTED: "Rejected"
                if attempt.failure_code != "NOT_SENT"
                else "Blocked",
                PositionExitState.EXPIRED: "Expired",
            }[attempt.state]
            steps.append(TimelineStep(label, attempt.terminal_at, True, attempt.failure_code or ""))
        elif attempt.state is PositionExitState.SUBMISSION_UNKNOWN:
            steps.append(TimelineStep("Needs attention", None, True, "outcome UNKNOWN"))
        else:
            steps.append(TimelineStep("Filled / Cancelled / Needs attention", None, False, ""))
        steps.append(
            TimelineStep(
                "Position closed",
                attempt.closed_position_verified_at,
                attempt.position_closed,
                "verified: broker position 0" if attempt.position_closed else "",
            )
        )
        return ExitSummary(
            attempt_id=attempt.attempt_id,
            state=state,
            raw_state=attempt.state.value,
            quantity=_quantity(attempt.quantity),
            filled_quantity=_quantity(attempt.filled_quantity),
            filled_avg_price=_money(attempt.filled_avg_price),
            limit_price=NOT_AVAILABLE if preview is None else _money(preview.request.limit_price),
            broker_order_id=attempt.broker_order_id or NOT_AVAILABLE,
            claimed_at=attempt.claimed_at,
            submitted_at=attempt.submitted_at,
            terminal_at=attempt.terminal_at,
            position_closed=attempt.position_closed,
            closed_verified_at=attempt.closed_position_verified_at,
            outcome_known=attempt.outcome_is_known,
            can_cancel=attempt.state
            in {
                PositionExitState.SUBMITTED,
                PositionExitState.ACCEPTED,
                PositionExitState.PARTIALLY_FILLED,
            },
            pending_reason=pending,
            warnings=tuple(dict.fromkeys(warnings)),
            timeline=tuple(steps),
            realized=realized,
            result_text=result_text,
        )

    # -- review -----------------------------------------------------------------------

    def review(self, intent_id: str) -> ExitReviewView:
        now = self._clock()
        intent = self._intents.get(intent_id)
        if intent is None:
            raise NotFoundError(f"no approved order intent {intent_id!r} exists")
        version = self._x.previews.next_version_for_entry(intent_id)
        try:
            preview = PreviewPositionExitHandler(
                intents=self._intents,
                entry_attempts=self._entries,
                exit_attempts=self._x.attempts,
                external_closures=self._external_closures,
                previews=self._x.previews,
                events=self._x.events,
                broker=self._broker,
                market_data=self._market_data,
                configurations=self._configurations,
                environment=self._environment,
                time_source=self._time,
            ).handle(
                PreviewPositionExitCommand(
                    entry_intent_governance_id=intent_id,
                    preview_id=f"XPV-{intent_id}-{version}",
                    created_at=now,
                )
            )
        except PositionExitRefusedError as error:
            raise ConsoleRefusalError(
                "Position requires operator attention", f"{error} Nothing was sent."
            ) from error
        deadline = preview.liquidation_deadline
        expires = now + timedelta(seconds=MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS)
        if now < deadline:
            expires = min(expires, deadline)
        tone, note = deadline_status(
            deadline=deadline, now=now, position_open=True, position_closed=False
        )
        ticket = ConfirmationTicket(
            action=EXIT_ACTION,
            proposal_id=intent_id,
            proposal_version=preview.preview_version,
            fingerprint=preview.request_fingerprint,
            issued_at=now,
        )
        entry = preview.position
        return ExitReviewView(
            intent_id=intent_id,
            preview_id=preview.preview_id,
            preview_version=preview.preview_version,
            symbol=preview.request.symbol,
            current_holding=_quantity(entry.broker_position_quantity),
            exit_quantity=_quantity(preview.request.quantity),
            side="SELL TO CLOSE",
            order_type=preview.request.order_type.value,
            limit_price=_money(preview.request.limit_price),
            account=f"{_account_noun(self._environment)} ({preview.account_reference[:16]}…)",
            environment=preview.environment,
            entry_avg_fill_price=_money(entry.entry_avg_fill_price),
            current_bid=_money(preview.quote_bid),
            current_ask=_money(preview.quote_ask),
            quote_captured_at=preview.quote_captured_at,
            position_captured_at=entry.captured_at,
            client_order_id=preview.request.client_order_id,
            fingerprint_short=preview.request_fingerprint[:12],
            liquidation_deadline=deadline,
            deadline_tone=tone,
            deadline_note=note,
            authorization_expires_at=expires,
            ticket=ticket.encode(self._signer),
            kill_switch_engaged=self._kill_switch.is_engaged(),
            full_close_warning=(
                "Confirming will close the WHOLE attributable position in "
                f"{preview.request.symbol} ({_quantity(preview.request.quantity)} shares) -- a "
                "full close, not a partial reduction. This is SELL TO CLOSE only: it cannot "
                "open or increase a short position."
            ),
        )

    # -- confirm ----------------------------------------------------------------------

    def confirm(self, intent_id: str, token: str) -> ActionOutcome:
        if self._recovery_mode:
            raise ConsoleRefusalError(
                "Recovery mode active",
                "This console was started in read-only recovery mode: Paper review, broker "
                "reconciliation and safety visibility all work, but no exit may be confirmed "
                "or sent -- automatically or manually. Nothing was sent. Restart without "
                "--recovery-mode, with the Owner present, to resume exits.",
            )
        now = self._clock()
        ticket = ConfirmationTicket.decode(token, signer=self._signer, now=now)
        if ticket.action != EXIT_ACTION or ticket.proposal_id != intent_id:
            raise ConsoleRefusalError(
                "Out of date",
                "This confirmation did not come from a current exit review of this console. "
                "Nothing was sent. Review the exit again.",
            )
        existing = self._x.attempts.active_for_entry(intent_id)
        if existing is not None:
            return self._outcome(existing, duplicate=True)
        preview = self._x.previews.get(f"XPV-{intent_id}-{ticket.proposal_version}")
        if preview is None or preview.request_fingerprint != ticket.fingerprint:
            raise ConsoleRefusalError(
                "Terms changed",
                "The exit terms shown are no longer the current ones. Nothing was sent. Review "
                "the exit again.",
            )
        # RELEASE v1: the kill switch blocks new entries only; a position-reducing exit is
        # never blocked by it. See `docs/operations/kill-switch.md`.
        authorization = self._x.authorizations.latest_for_entry(intent_id)
        if (
            authorization is None
            or authorization.preview_id != preview.preview_id
            or authorization.is_consumed
            or authorization.is_expired_at(now)
        ):
            try:
                AuthorizePositionExitHandler(
                    previews=self._x.previews,
                    authorizations=self._x.authorizations,
                    events=self._x.events,
                    broker=self._broker,
                    kill_switch=self._kill_switch,
                    time_source=self._time,
                ).handle(
                    AuthorizePositionExitCommand(
                        authorization_id=f"XAU-{intent_id}-{preview.preview_version}",
                        preview_id=preview.preview_id,
                        expected_request_fingerprint=preview.request_fingerprint,
                        authorized_by=self._operator,
                        authorized_at=now,
                    )
                )
            except (PositionExitRefusedError, PaperTimeUncertainError) as error:
                # `PaperTimeUncertainError` (paper_time.py) is a sibling `ValueError`
                # subclass, not a `PositionExitRefusedError` -- `AuthorizePositionExitHandler`
                # raises it directly on an uncertain broker-clock reading. Mirrors the SAME
                # catch `position_plan_manager.PositionPlanManager._attempt_exit` already
                # uses for the automatic path, so a transient clock disagreement produces a
                # clear "review again" refusal here too, never an uncaught exception.
                raise ConsoleRefusalError("Exit refused", f"{error}. Nothing was sent.") from error
        try:
            result = SubmitAuthorizedPositionExitHandler(
                intents=self._intents,
                entry_attempts=self._entries,
                previews=self._x.previews,
                authorizations=self._x.authorizations,
                attempts=self._x.attempts,
                external_closures=self._external_closures,
                acknowledgements=self._x.acknowledgements,
                events=self._x.events,
                broker=self._broker,
                configurations=self._configurations,
                kill_switch=self._kill_switch,
                time_source=self._time,
            ).handle(
                SubmitAuthorizedPositionExitCommand(
                    entry_intent_governance_id=intent_id,
                    attempt_id=f"XAT-{intent_id}-{preview.preview_version}",
                    at=self._clock(),
                )
            )
        except (PositionExitRefusedError, PaperTimeUncertainError) as error:
            raise ConsoleRefusalError("Exit refused", f"{error}. Nothing was sent.") from error
        # Not dispatched because another request won the claim: report THAT exit, create nothing.
        lost_race = not result.dispatched and result.attempt.attempt_id != (
            f"XAT-{intent_id}-{preview.preview_version}"
        )
        return self._outcome(result.attempt, duplicate=lost_race)

    # -- overdue-position recovery (RELEASE v1 recovery hardening) ---------------------

    def grant_overdue_recovery_approval(
        self, intent_id: str, recovery_approval_id: str
    ) -> PositionExitEvent:
        """Durably record ONE fresh, explicit Owner decision to recover an overdue
        position -- a SEPARATE, prior step from `confirm_overdue_recovery` (SECURITY GATE,
        RELEASE v1 recovery hardening review): `confirm_overdue_recovery` requires a REAL
        persisted record matching this exact position, not merely a distinct nonempty
        string. No ticket is involved -- this is a decision about the POSITION, not about
        any one preview version, so there is nothing yet to re-confirm against; the
        position, account and quantity are re-verified fresh, right now, against the
        broker, by `GrantOverduePositionRecoveryApprovalHandler` itself.
        """
        plans = self._plans
        if plans is None:
            raise ConsoleRefusalError(
                "Recovery not available",
                "Overdue-position recovery is not available in this capability. Nothing "
                "was recorded.",
            )
        try:
            return GrantOverduePositionRecoveryApprovalHandler(
                intents=self._intents,
                entry_attempts=self._entries,
                exit_attempts=self._x.attempts,
                external_closures=self._external_closures,
                plans=plans,
                broker=self._broker,
                events=self._x.events,
                time_source=self._time,
            ).handle(
                GrantOverduePositionRecoveryApprovalCommand(
                    entry_intent_governance_id=intent_id,
                    recovery_approval_id=recovery_approval_id,
                    granted_at=self._clock(),
                )
            )
        except PositionExitRefusedError as error:
            raise ConsoleRefusalError(
                "Recovery approval refused", f"{error}. Nothing was recorded."
            ) from error

    def confirm_overdue_recovery(
        self, intent_id: str, token: str, recovery_approval_id: str
    ) -> ActionOutcome:
        """The ONE escape hatch for a position whose mandatory deadline has already passed.

        Deliberately a SEPARATE method from `confirm()`, not an extra branch inside it: a
        normal authorization can never again satisfy `exit_authorization_binding_refusal`
        once a position is overdue (see that function's own docstring), so recovering it
        needs its own narrowly scoped authority, requiring `recovery_approval_id` -- a FRESH,
        explicit Owner approval, distinct from the original plan's own `owner_approval_id`,
        which `AuthorizeOverduePositionRecoveryHandler` never reads except to prove the new
        id differs from it, and never rewrites or extends. `confirm()` itself, its normal
        `AuthorizePositionExitHandler` path, and every normal pre-deadline exit are completely
        unaffected by this method's existence.

        Reuses the SAME `review()`-issued ticket `confirm()` does (the ticket proves which
        preview the Owner was shown; it carries no opinion about whether the position is
        overdue), the SAME idempotent-dispatch short-circuit, and the SAME
        `SubmitAuthorizedPositionExitHandler` -- so the fresh broker position/quantity check,
        the no-pending-SELL/no-UNKNOWN check, the fresh-quote check and the exactly-once
        dispatch claim are all identical to a normal exit, unchanged.
        """
        plans = self._plans
        if plans is None:
            raise ConsoleRefusalError(
                "Recovery not available",
                "Overdue-position recovery is not available in this capability. Nothing was sent.",
            )
        now = self._clock()
        ticket = ConfirmationTicket.decode(token, signer=self._signer, now=now)
        if ticket.action != EXIT_ACTION or ticket.proposal_id != intent_id:
            raise ConsoleRefusalError(
                "Out of date",
                "This confirmation did not come from a current exit review of this console. "
                "Nothing was sent. Review the exit again.",
            )
        if not isinstance(recovery_approval_id, str) or not recovery_approval_id.strip():
            raise ConsoleRefusalError(
                "Recovery approval required",
                "Overdue-position recovery requires a fresh, explicit Owner approval id. "
                "Nothing was sent.",
            )
        existing = self._x.attempts.active_for_entry(intent_id)
        if existing is not None:
            return self._outcome(existing, duplicate=True)
        # RELEASE v1 OVERDUE RECOVERY UI: fail-closed outside a regular trading session.
        # Scoped to recovery ONLY (unlike the broader, not-yet-merged fix that gates
        # `SubmitAuthorizedPositionExitHandler` itself for every exit) so normal exit and
        # automatic Plan Manager behavior are completely unaffected by this change -- this
        # is an extra refusal that can only ever apply to the recovery escape hatch.
        if not self._broker.fetch_clock().is_open:
            raise ConsoleRefusalError(
                "Market closed",
                "The market is not in a regular trading session; overdue-recovery exits are "
                "not dispatched outside regular hours. Nothing was sent.",
            )
        preview = self._x.previews.get(f"XPV-{intent_id}-{ticket.proposal_version}")
        if preview is None or preview.request_fingerprint != ticket.fingerprint:
            raise ConsoleRefusalError(
                "Terms changed",
                "The exit terms shown are no longer the current ones. Nothing was sent. Review "
                "the exit again.",
            )
        authorization = self._x.authorizations.latest_for_entry(intent_id)
        if (
            authorization is None
            or authorization.preview_id != preview.preview_id
            or authorization.is_consumed
            or authorization.is_expired_at(now)
            or not is_overdue_recovery_authorization(authorization)
        ):
            try:
                AuthorizeOverduePositionRecoveryHandler(
                    previews=self._x.previews,
                    authorizations=self._x.authorizations,
                    events=self._x.events,
                    plans=plans,
                    broker=self._broker,
                    time_source=self._time,
                ).handle(
                    AuthorizeOverduePositionRecoveryCommand(
                        authorization_id=f"XAU-RECOVERY-{intent_id}-{preview.preview_version}",
                        preview_id=preview.preview_id,
                        expected_request_fingerprint=preview.request_fingerprint,
                        recovery_approval_id=recovery_approval_id,
                        authorized_at=now,
                    )
                )
            except PositionExitRefusedError as error:
                raise ConsoleRefusalError("Exit refused", f"{error}. Nothing was sent.") from error
        try:
            result = SubmitAuthorizedPositionExitHandler(
                intents=self._intents,
                entry_attempts=self._entries,
                previews=self._x.previews,
                authorizations=self._x.authorizations,
                attempts=self._x.attempts,
                external_closures=self._external_closures,
                acknowledgements=self._x.acknowledgements,
                events=self._x.events,
                broker=self._broker,
                configurations=self._configurations,
                kill_switch=self._kill_switch,
                time_source=self._time,
            ).handle(
                SubmitAuthorizedPositionExitCommand(
                    entry_intent_governance_id=intent_id,
                    attempt_id=f"XAT-{intent_id}-{preview.preview_version}",
                    at=self._clock(),
                )
            )
        except PositionExitRefusedError as error:
            raise ConsoleRefusalError("Exit refused", f"{error}. Nothing was sent.") from error
        lost_race = not result.dispatched and result.attempt.attempt_id != (
            f"XAT-{intent_id}-{preview.preview_version}"
        )
        return self._outcome(result.attempt, duplicate=lost_race)

    def _outcome(self, attempt: PositionExitAttempt, *, duplicate: bool) -> ActionOutcome:
        state = human_state_for_exit(attempt)
        prefix = "Already confirmed. " if duplicate else ""
        broker = _broker_noun(self._environment)
        if state is HumanState.NEEDS_ATTENTION:
            return ActionOutcome(
                False,
                "Outcome unknown — do not retry",
                prefix + f"The exit may have reached the {broker} and no answer proves what "
                "happened. The console keeps checking the same exit order; it will never be "
                "sent again.",
                "unknown",
                intent_id=attempt.entry_intent_governance_id,
                state=state,
            )
        if state is HumanState.BLOCKED:
            return ActionOutcome(
                False,
                "Nothing was sent",
                prefix + f"The exit was blocked before anything left: {attempt.failure_detail}",
                "nothing_sent",
                intent_id=attempt.entry_intent_governance_id,
                state=state,
            )
        if state is HumanState.REJECTED:
            return ActionOutcome(
                False,
                "Exit rejected by the broker",
                prefix + f"The {broker} refused the exit ({attempt.failure_code}). The position "
                "remains open.",
                "sent",
                intent_id=attempt.entry_intent_governance_id,
                state=state,
            )
        if attempt.position_closed:
            return ActionOutcome(
                True,
                "Position closed",
                prefix + "The exit filled and the broker position was verified at zero.",
                "sent",
                intent_id=attempt.entry_intent_governance_id,
                state=state,
            )
        return ActionOutcome(
            True,
            "Exit confirmed and sent" if not duplicate else "Already confirmed",
            prefix + f"The SELL TO CLOSE was sent to the {broker} and is {state.value.lower()}. "
            "The position is closed only once the fill is verified.",
            "sent",
            intent_id=attempt.entry_intent_governance_id,
            state=state,
        )

    # -- cancel, refresh ---------------------------------------------------------------

    def cancel(self, attempt_id: str) -> ActionOutcome:
        attempt = self._x.attempts.get(attempt_id)
        if attempt is None:
            raise NotFoundError(f"no exit {attempt_id!r} exists")
        try:
            moved = CancelPositionExitHandler(
                attempts=self._x.attempts,
                acknowledgements=self._x.acknowledgements,
                events=self._x.events,
                broker=self._broker,
            ).handle(CancelPositionExitCommand(attempt_id=attempt_id, at=self._clock()))
        except PositionExitRefusedError as error:
            raise ConsoleRefusalError("Cannot cancel", f"{error}. Nothing was done.") from error
        return ActionOutcome(
            True,
            "Exit cancel requested",
            "A cancellation was requested for the exit order. A request is not a cancellation: "
            f"the exit may still fill. Current state: {human_state_for_exit(moved).value.lower()}.",
            "sent",
            intent_id=attempt.entry_intent_governance_id,
            state=human_state_for_exit(moved),
        )

    def refresh(self) -> tuple[str, ...]:
        """Reconcile every open exit and every filled-but-unverified exit; record deadline truth."""
        refreshed: list[str] = []
        now = self._clock()
        for attempt in self._x.attempts.list_recent(500):
            if attempt.state not in _RECONCILABLE and not (
                attempt.fully_filled and not attempt.position_closed
            ):
                continue
            try:
                ReconcilePositionExitHandler(
                    attempts=self._x.attempts,
                    acknowledgements=self._x.acknowledgements,
                    events=self._x.events,
                    rounds=self._x.rounds,
                    authorizations=self._x.authorizations,
                    previews=self._x.previews,
                    broker=self._broker,
                    time_source=self._time,
                ).handle(ReconcilePositionExitCommand(attempt_id=attempt.attempt_id, at=now))
            except Exception:  # noqa: BLE001, S112 - the handler recorded a FAILED round durably
                continue
            refreshed.append(attempt.attempt_id)
        self._record_missed_deadlines(now)
        return tuple(refreshed)

    def _record_missed_deadlines(self, now: datetime) -> None:
        """The truth, durably: a position still open past its deadline, recorded once."""
        for entry in self._entries.list_recent(500):
            if not position_is_open(entry) and not position_is_open_after_cancel(entry):
                continue
            intent = self._intents.get(entry.intent_governance_id)
            if intent is None or now < intent.mandatory_liquidation_at:
                continue
            active = self._x.attempts.active_for_entry(entry.intent_governance_id)
            if active is not None and active.position_closed:
                continue
            events = self._x.events.for_entry(entry.intent_governance_id)
            if any(e.event_type == _DEADLINE_MISSED_EVENT for e in events):
                continue
            self._x.events.append(
                PositionExitEvent(
                    event_id=f"XEV-DEADLINE-{entry.attempt_id}"[:64],
                    entry_intent_governance_id=entry.intent_governance_id,
                    attempt_id=None,
                    event_type=_DEADLINE_MISSED_EVENT,
                    occurred_at=now,
                    detail=(
                        f"{DEADLINE_MISSED_TRUTH} deadline "
                        f"{intent.mandatory_liquidation_at.isoformat()}; no exit was sent by itself"
                    )[:500],
                )
            )

    def deadline_missed_recorded(self, intent_id: str) -> bool:
        return any(
            e.event_type == _DEADLINE_MISSED_EVENT for e in self._x.events.for_entry(intent_id)
        )

    def closed_verified_event(self, intent_id: str) -> PositionExitEvent | None:
        for event in self._x.events.for_entry(intent_id):
            if event.event_type == POSITION_CLOSED_VERIFIED_EVENT_TYPE:
                return event
        return None


def position_is_open_after_cancel(entry: ExecutionAttempt) -> bool:
    """A cancelled entry that had filled shares before the cancel: a stable open position."""
    return (
        entry.state.value == "CANCELED"
        and entry.filled_quantity is not None
        and entry.filled_quantity > 0
    )
