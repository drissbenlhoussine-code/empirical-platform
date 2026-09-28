"""MILESTONE-086 -- Operator Console application services.

THE PRODUCT LAYER OVER M057-M085. Nothing here decides whether a trade may be proposed,
approved, issued, authorized, sent, reconciled or stopped: those decisions belong to the
MILESTONE-084 and MILESTONE-085 handlers and repositories this module calls. What this
module adds is the operator's view of them -- today's opportunities, the exact terms an
Owner confirms, active executions with their timelines, the history, the safety page --
and the operator's actions, each of which is a request to an existing usecase and never a
write to an execution table.

THE TWO-STAGE DECISION. APPROVE opens a confirmation carrying the exact immutable terms
and a signed ticket bound to the proposal's identity, version and content fingerprint.
CONFIRM APPROVAL re-reads the authoritative proposal and refuses when it changed, expired,
was decided already, or when the execution stop is engaged; only then does it run the
existing chain: paper-bound decision -> paper-bound intent -> submission preview -> human
authorization (bound to the preview's fingerprint, which must match the terms shown) ->
dispatch through the M085 handler. Every identifier the chain writes is DERIVED from the
proposal's identity, so a duplicate request (refresh, second tab, retry) cannot create a
second decision, intent, authorization or attempt: it finds the existing rows and reports
them. REJECT is one confirmation, for the same reasons.

THE CAPABILITY FIREWALL. The console's execution capability is chosen by the composition
root, never by a request. `refuse_requested_environment` is called on every state-changing
action with whatever the browser sent; any `environment` value at all -- SIMULATION
included -- is refused, because the browser has no say. PAPER and LIVE are displayed as
locked and not authorized; no code path in this module can construct a broker.

HUMAN LANGUAGE. Technical failures are translated (`describe_failure`) and every message
states one of two safety-critical facts: NOTHING WAS SENT, or OUTCOME UNKNOWN -- DO NOT
RETRY. The console never shows FILLED, or any state, that the durable record does not hold.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from empirical_platform.decision_candidate.operator_trading_configuration import (
    KillSwitchState,
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionEvent,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    BrokerAcknowledgementRepository,
    ExecutionAttemptRepository,
    ExecutionAuthorizationRepository,
    ExecutionKillSwitchRepository,
    PaperAccountSnapshotRepository,
    PaperBrokerPort,
    PaperExecutionEventRepository,
    PaperMarketDataPort,
    ReconciliationRoundRepository,
    SubmissionPreviewRepository,
    TimeBasisRepository,
)
from empirical_platform.decision_candidate.product_repositories import (
    ApprovalDecisionRepository,
    ApprovedOrderIntentRepository,
    EvaluationContextRepository,
    OperatorTradingConfigurationRepository,
    TradeProposalRepository,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
    OperatorAction,
)
from empirical_platform.decision_candidate.trade_proposal import (
    ProposalStatus,
    RiskCheckOutcome,
    TradeProposal,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.paper_time import (
    PaperTimeSource,
    PaperTimeUncertainError,
    SystemPaperTimeSource,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    CancelPaperOrderCommand,
    CancelPaperOrderHandler,
    DecidePaperBoundTradeProposalCommand,
    DecidePaperBoundTradeProposalHandler,
    IssuePaperBoundOrderIntentCommand,
    IssuePaperBoundOrderIntentHandler,
    PaperExecutionRefusedError,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
    SetExecutionKillSwitchCommand,
    SetExecutionKillSwitchHandler,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)

if TYPE_CHECKING:  # the exit console imports this module's vocabulary; no import cycle at runtime
    from empirical_platform.usecases.operator_console_exits import (
        ExitSummary,
        PositionExitConsole,
    )

__all__ = [
    "ActionOutcome",
    "CapabilityRefusedError",
    "CapabilityStatus",
    "ConfirmationTicket",
    "ConfirmationView",
    "ConsoleRefusalError",
    "ConsoleRepositories",
    "ExecutionCapability",
    "ExecutionSummary",
    "HistoryEntry",
    "HumanState",
    "OPEN_POSITION_EXIT_STATUS",
    "OperatorConsoleService",
    "OpportunityCard",
    "RuleRow",
    "SafetyView",
    "Signer",
    "TermsView",
    "TimelineStep",
    "TodayView",
    "describe_failure",
    "human_state_for_attempt",
    "position_is_open",
    "refuse_requested_environment",
]

NOT_AVAILABLE = "Not available"

#: How long a confirmation page stays actionable. A ticket older than this is refused
#: and the Owner is asked to open the opportunity again.
CONFIRMATION_TICKET_MAX_AGE = timedelta(minutes=15)

#: Longest human authorization the console grants, in seconds. The configured approval
#: expiry is respected when shorter; the intent expiry always bounds it in M085.
MAXIMUM_AUTHORIZATION_VALIDITY_SECONDS = 900

#: States the durable record can only hold once the broker accepted the order.
_ACCEPTED_OR_BEYOND: frozenset[PaperExecutionState] = frozenset(
    {
        PaperExecutionState.PAPER_ACCEPTED,
        PaperExecutionState.PARTIALLY_FILLED,
        PaperExecutionState.FILLED,
        PaperExecutionState.CANCEL_REQUESTED,
        PaperExecutionState.CANCELED,
        PaperExecutionState.EXPIRED,
    }
)

#: The console's non-terminal execution states: the ones the refresh reconciles.
_RECONCILABLE_STATES: frozenset[PaperExecutionState] = frozenset(
    {
        PaperExecutionState.SUBMISSION_IN_PROGRESS,
        PaperExecutionState.PAPER_SUBMITTED,
        PaperExecutionState.PAPER_ACCEPTED,
        PaperExecutionState.PARTIALLY_FILLED,
        PaperExecutionState.CANCEL_REQUESTED,
        PaperExecutionState.SUBMISSION_UNKNOWN,
    }
)


# ---------------------------------------------------------------------------
# Capability firewall
# ---------------------------------------------------------------------------


class ExecutionCapability(StrEnum):
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    capability: ExecutionCapability
    enabled: bool
    label: str
    note: str


#: The only table of capabilities. SIMULATION is the only enabled one in this milestone;
#: nothing reads this table from a request.
CAPABILITIES: tuple[CapabilityStatus, ...] = (
    CapabilityStatus(
        ExecutionCapability.SIMULATION,
        True,
        "Simulation",
        "Deterministic simulated broker and market data. No order can reach any venue.",
    ),
    CapabilityStatus(
        ExecutionCapability.PAPER,
        False,
        "Paper — Locked pending M085 Paper Acceptance",
        "Paper execution locked — acceptance pending. A separate Owner gate is required.",
    ),
    CapabilityStatus(
        ExecutionCapability.LIVE,
        False,
        "Live — Not authorized",
        "No live execution exists in this product.",
    ),
)


class CapabilityRefusedError(PermissionError):
    """A request tried to choose an execution environment. The browser has no say."""


def refuse_requested_environment(requested: Mapping[str, object] | None) -> None:
    """Fail closed when a request carries any environment or capability selection.

    Called with the form (or query) mapping of every state-changing action. The presence
    of `environment`, `capability`, `mode` or `venue` -- with ANY value, SIMULATION
    included -- is refused: the composition root decided the capability before the first
    request arrived, and a hostile or tampered browser cannot move it.
    """
    if not requested:
        return
    for key in ("environment", "capability", "mode", "venue"):
        if key in requested:
            raise CapabilityRefusedError(
                "This console cannot select an execution environment from the browser. "
                "The request was refused and nothing was done."
            )


# ---------------------------------------------------------------------------
# Human vocabulary
# ---------------------------------------------------------------------------


class HumanState(StrEnum):
    NEEDS_DECISION = "Needs decision"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    BLOCKED = "Blocked"
    SUBMITTED = "Submitted"
    ACCEPTED = "Accepted"
    PARTIALLY_FILLED = "Partially filled"
    FILLED = "Filled"
    CANCEL_REQUESTED = "Cancel requested"
    CANCELLED = "Cancelled"
    NEEDS_ATTENTION = "Needs attention"


_ATTEMPT_STATES: Mapping[PaperExecutionState, HumanState] = {
    PaperExecutionState.NOT_DISPATCHED: HumanState.APPROVED,
    PaperExecutionState.AUTHORIZATION_PENDING: HumanState.APPROVED,
    PaperExecutionState.AUTHORIZED: HumanState.APPROVED,
    PaperExecutionState.DISPATCH_CLAIMED: HumanState.SUBMITTED,
    PaperExecutionState.SUBMISSION_IN_PROGRESS: HumanState.SUBMITTED,
    PaperExecutionState.PAPER_SUBMITTED: HumanState.SUBMITTED,
    PaperExecutionState.PAPER_ACCEPTED: HumanState.ACCEPTED,
    PaperExecutionState.PARTIALLY_FILLED: HumanState.PARTIALLY_FILLED,
    PaperExecutionState.FILLED: HumanState.FILLED,
    PaperExecutionState.CANCEL_REQUESTED: HumanState.CANCEL_REQUESTED,
    PaperExecutionState.CANCELED: HumanState.CANCELLED,
    PaperExecutionState.REJECTED: HumanState.REJECTED,
    PaperExecutionState.EXPIRED: HumanState.EXPIRED,
    PaperExecutionState.SUBMISSION_UNKNOWN: HumanState.NEEDS_ATTENTION,
}


#: The exit status shown when NO exit path is composed (the M086 console without M087).
OPEN_POSITION_EXIT_STATUS = "Open position — exit locked pending M087."
#: The exit status shown by the M087 console for a position that can be reviewed for closing.
OPEN_POSITION_REVIEWABLE_STATUS = (
    "Open position — review the exit to close it. Nothing is sent without your confirmation."
)


def position_is_open(attempt: ExecutionAttempt) -> bool:
    """A filled or partially filled BUY whose shares are held: an open position.

    Derived from the durable attempt only. FILLED stays FILLED in M085; this is the
    console's reading of it until an exit path exists (M086-REV-EXIT-01).
    """
    return (
        attempt.state in {PaperExecutionState.FILLED, PaperExecutionState.PARTIALLY_FILLED}
        and attempt.filled_quantity is not None
        and attempt.filled_quantity > 0
    )


def human_state_for_attempt(attempt: ExecutionAttempt) -> HumanState:
    """The operator's word for an execution attempt. UNKNOWN is 'Needs attention', never a guess."""
    if attempt.state is PaperExecutionState.REJECTED and attempt.failure_code == "NOT_SENT":
        return HumanState.BLOCKED
    return _ATTEMPT_STATES[attempt.state]


def describe_failure(error: BaseException) -> tuple[str, str]:
    """Translate a technical failure into (title, message) an operator can act on.

    Every message says which of the two safety-critical facts holds: nothing was sent, or
    the outcome is unknown and must not be retried.
    """
    if isinstance(error, PaperTimeUncertainError):
        return (
            "Execution blocked",
            "Execution blocked because the timing evidence is not reliable enough. "
            "No order was sent.",
        )
    if isinstance(error, BrokerNotSentError):
        return (
            "Nothing was sent",
            f"The request never reached the broker. Nothing was sent. ({error})",
        )
    if isinstance(error, BrokerAmbiguousDispatchError):
        return (
            "Outcome unknown — do not retry",
            "The request may have reached the broker and no answer proves what happened. "
            "The console will keep checking the same order; do not send it again.",
        )
    if isinstance(error, CapabilityRefusedError):
        return ("Refused", str(error))
    if isinstance(error, ConsoleRefusalError):
        return (error.title, error.message)
    if isinstance(error, NotFoundError):
        return ("Not found", "This item no longer exists. Nothing was done.")
    if isinstance(error, PaperExecutionRefusedError):
        return ("Execution blocked", f"Execution blocked: {error}. No order was sent.")
    if isinstance(error, ValueError):
        return ("Refused", f"The request was refused: {error}. Nothing was sent.")
    return (
        "Could not be recorded",
        "The action could not be recorded safely. Nothing was executed.",
    )


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


def _money(value: Decimal | None) -> str:
    if value is None:
        return NOT_AVAILABLE
    return f"{value:,.2f}"


def _quantity(value: Decimal | int | None) -> str:
    """Whole shares read as whole numbers; a fractional record keeps its digits."""
    if value is None:
        return NOT_AVAILABLE
    decimal = Decimal(value)
    return (
        str(decimal.quantize(Decimal(1)))
        if decimal == decimal.to_integral_value()
        else str(decimal.normalize())
    )


@dataclass(frozen=True, slots=True)
class TermsView:
    """The exact immutable order terms, as the Owner sees them."""

    symbol: str
    side: str
    quantity: int
    order_type: str
    limit_price: str
    time_in_force: str
    extended_hours: str
    currency: str
    notional: str
    fingerprint_short: str


@dataclass(frozen=True, slots=True)
class OpportunityCard:
    proposal_id: str
    proposal_version: int
    symbol: str
    terms: TermsView
    maximum_capital: str
    stop_price: str
    target_price: str
    risk_amount: str
    risk_percent: str
    reason: str
    evidence: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    state: HumanState
    decision_available: bool
    blocked_note: str | None
    attention_note: str | None
    intent_id: str | None
    execution: ExecutionSummary | None
    scenario: str | None

    def state_is_settled(self) -> bool:
        """Whether this card has nothing left for the operator to see on Today."""
        if self.execution is not None:
            return self.execution.is_terminal
        return self.state in {HumanState.REJECTED, HumanState.EXPIRED, HumanState.BLOCKED}


@dataclass(frozen=True, slots=True)
class TimelineStep:
    label: str
    at: datetime | None
    reached: bool
    note: str


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    intent_id: str
    proposal_id: str
    symbol: str
    state: HumanState
    raw_state: str
    terms: TermsView
    decision_by: str
    decided_at: datetime | None
    broker_order_id: str
    claimed_at: datetime | None
    submitted_at: datetime | None
    acknowledged_at: datetime | None
    terminal_at: datetime | None
    filled_quantity: str
    filled_avg_price: str
    pending_reason: str | None
    reconciliation: str
    warnings: tuple[str, ...]
    timeline: tuple[TimelineStep, ...]
    is_terminal: bool
    outcome_known: bool
    can_cancel: bool
    execution_kind: str
    #: A FILLED (or partially filled) BUY entry is an OPEN POSITION until an exit closes it.
    #: Without the M087 exit console the exit is shown as locked (M086-REV-EXIT-01); with it,
    #: the position can be reviewed for closing. The M085 state itself is never changed.
    position_open: bool
    exit_status: str
    #: MILESTONE-087. Which of the four Active-trades groups this row belongs to, the exit (if
    #: any) with its own timeline, whether "Review exit" is offered, the mandatory liquidation
    #: deadline and its status, and whether the position is VERIFIED closed.
    category: str = "Working entry order"
    exit: ExitSummary | None = None
    can_review_exit: bool = False
    liquidation_deadline: datetime | None = None
    deadline_tone: str = "info"
    deadline_note: str = ""
    position_closed: bool = False


@dataclass(frozen=True, slots=True)
class TodayView:
    session_date: str
    generated_at: datetime
    system_status: str
    market_status: str
    kill_switch_engaged: bool
    capability: CapabilityStatus
    opportunities: tuple[OpportunityCard, ...]
    needs_action_count: int
    active_positions_count: int
    active_executions_count: int
    #: MILESTONE-088. How many of `opportunities` are still open (not settled): the
    #: genuinely current/actionable count. `len(opportunities)` also counts settled,
    #: historical cards shown today for evidence -- e.g. a completed, canceled Paper
    #: acceptance run -- which is not an opportunity awaiting anything. Never wider than
    #: `len(opportunities)` and never counts a settled card.
    open_opportunities_count: int


@dataclass(frozen=True, slots=True)
class ConfirmationView:
    action: str
    proposal_id: str
    proposal_version: int
    terms: TermsView
    account: str
    environment: str
    proposal_expires_at: datetime
    approval_expires_at: datetime | None
    ticket: str
    kill_switch_engaged: bool


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    proposal_id: str
    symbol: str
    created_at: datetime
    proposal_state: str
    decision: str
    decided_at: datetime | None
    decided_by: str
    execution_kind: str
    execution_outcome: str
    final_state: HumanState
    quantity: str
    price: str
    result: str
    intent_id: str | None
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class RuleRow:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class SafetyView:
    capabilities: tuple[CapabilityStatus, ...]
    active_capability: CapabilityStatus
    execution_kill_switch_engaged: bool
    configuration_kill_switch: str
    configuration_id: str
    configuration_version: str
    rules: tuple[RuleRow, ...]


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    ok: bool
    title: str
    message: str
    #: "nothing_sent" | "sent" | "unknown" | "none": the safety-critical fact.
    sent: str
    proposal_id: str | None = None
    intent_id: str | None = None
    state: HumanState | None = None


class ConsoleRefusalError(Exception):
    """A request the console refuses, with a title and an operator message."""

    def __init__(self, title: str, message: str) -> None:
        super().__init__(message)
        self.title = title
        self.message = message


# ---------------------------------------------------------------------------
# Confirmation tickets
# ---------------------------------------------------------------------------


class Signer(Protocol):
    def sign(self, payload: bytes) -> str: ...


class HmacSigner:
    """HMAC-SHA256 over a caller-supplied secret. The console gives it a per-process one."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()[:40]


@dataclass(frozen=True, slots=True)
class ConfirmationTicket:
    """What a confirmation page carries back: the exact thing the Owner was shown.

    Bound to the action, the proposal's identity, its version and its content
    fingerprint, and the instant it was issued. Signed by the process, so it cannot be
    forged, edited to another proposal or replayed after a restart.
    """

    action: str
    proposal_id: str
    proposal_version: int
    fingerprint: str
    issued_at: datetime

    def payload(self) -> bytes:
        return "|".join(
            (
                self.action,
                self.proposal_id,
                str(self.proposal_version),
                self.fingerprint,
                str(int(self.issued_at.timestamp())),
            )
        ).encode("utf-8")

    def encode(self, signer: Signer) -> str:
        return self.payload().decode("utf-8") + "|" + signer.sign(self.payload())

    @classmethod
    def decode(cls, token: str, *, signer: Signer, now: datetime) -> ConfirmationTicket:
        parts = token.split("|")
        if len(parts) != 6:
            raise ConsoleRefusalError("Out of date", _STALE_TICKET)
        action, proposal_id, version, fingerprint, issued, signature = parts
        try:
            ticket = cls(
                action=action,
                proposal_id=proposal_id,
                proposal_version=int(version),
                fingerprint=fingerprint,
                issued_at=datetime.fromtimestamp(int(issued), tz=UTC),
            )
        except (ValueError, OverflowError, OSError) as error:
            raise ConsoleRefusalError("Out of date", _STALE_TICKET) from error
        if not hmac.compare_digest(signer.sign(ticket.payload()), signature):
            raise ConsoleRefusalError("Out of date", _STALE_TICKET)
        if (
            now - ticket.issued_at > CONFIRMATION_TICKET_MAX_AGE
            or ticket.issued_at > now + timedelta(minutes=1)
        ):
            raise ConsoleRefusalError(
                "Confirmation expired",
                "This confirmation page is too old. Nothing was done. Open the opportunity "
                "again to see its current terms.",
            )
        return ticket


_STALE_TICKET = (
    "This confirmation did not come from a current page of this console. Nothing was done. "
    "Open the opportunity again."
)


# ---------------------------------------------------------------------------
# Repositories the console needs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConsoleRepositories:
    """Every repository the console reads or asks a usecase to write. Protocol-typed."""

    configurations: OperatorTradingConfigurationRepository
    contexts: EvaluationContextRepository
    proposals: TradeProposalRepository
    decisions: ApprovalDecisionRepository
    intents: ApprovedOrderIntentRepository
    time_bases: TimeBasisRepository
    snapshots: PaperAccountSnapshotRepository
    previews: SubmissionPreviewRepository
    authorizations: ExecutionAuthorizationRepository
    attempts: ExecutionAttemptRepository
    acknowledgements: BrokerAcknowledgementRepository
    events: PaperExecutionEventRepository
    rounds: ReconciliationRoundRepository
    kill_switch: ExecutionKillSwitchRepository


def _now_utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


class OperatorConsoleService:
    """Reads for the four pages and the operator's actions, over the existing usecases."""

    def __init__(
        self,
        *,
        repositories: ConsoleRepositories,
        broker: PaperBrokerPort,
        market_data: PaperMarketDataPort,
        signer: Signer,
        capability: CapabilityStatus = CAPABILITIES[0],
        time_source: PaperTimeSource | None = None,
        clock: Callable[[], datetime] = _now_utc,
        operator_identity: str = "owner",
        staged_scenarios: Callable[[], Mapping[str, str]] | None = None,
        exits: PositionExitConsole | None = None,
    ) -> None:
        # MILESTONE-088: PAPER joins SIMULATION now that M085 Paper Acceptance has completed
        # against the real Alpaca paper endpoint. LIVE has no member here and never will from
        # this check alone -- composing it requires a `CapabilityStatus` this module's own
        # `CAPABILITIES` table never produces with `enabled=True` for LIVE, and no composition
        # root in this repository builds one.
        if not capability.enabled or capability.capability not in (
            ExecutionCapability.SIMULATION,
            ExecutionCapability.PAPER,
        ):
            raise CapabilityRefusedError(
                "the Operator Console can be composed for SIMULATION or PAPER only; LIVE is not "
                "authorized"
            )
        self._r = repositories
        self._broker = broker
        self._market_data = market_data
        self._signer = signer
        self._capability = capability
        self._time_source: PaperTimeSource = time_source or SystemPaperTimeSource()
        self._clock = clock
        self._operator = operator_identity
        self._staged_scenarios = staged_scenarios or (lambda: {})
        #: MILESTONE-087: the exit console, when the composition root wired one. None means
        #: the M086 behaviour exactly: open positions are shown with their exit locked.
        self._exits = exits

    # -- helpers -------------------------------------------------------------------

    @property
    def capability(self) -> CapabilityStatus:
        return self._capability

    @property
    def exits(self) -> PositionExitConsole | None:
        return self._exits

    def _position_closed(self, intent_id: str) -> bool:
        return self._exits is not None and self._exits.position_closed(intent_id)

    def _configuration(self, proposal: TradeProposal) -> OperatorTradingConfiguration | None:
        return self._r.configurations.get(
            proposal.configuration_governance_id, proposal.configuration_version
        )

    def _terms(self, proposal: TradeProposal) -> TermsView:
        ceiling = (
            proposal.limit_price * Decimal(proposal.quantity)
            if proposal.limit_price is not None
            else None
        )
        return TermsView(
            symbol=proposal.symbol,
            side=proposal.side,
            quantity=proposal.quantity,
            order_type=proposal.order_type.value,
            limit_price=_money(proposal.limit_price),
            time_in_force="DAY",
            extended_hours="No",
            currency=proposal.currency,
            notional=_money(ceiling if ceiling is not None else proposal.estimated_notional),
            fingerprint_short=proposal.content_fingerprint[:12],
        )

    def _all_proposals(self) -> tuple[TradeProposal, ...]:
        rows: list[TradeProposal] = []
        for status in ProposalStatus:
            rows.extend(self._r.proposals.list_by_status(status))
        rows.sort(key=lambda p: (p.created_at, p.proposal_governance_id))
        return tuple(rows)

    def _execution_for(
        self, proposal: TradeProposal
    ) -> tuple[ApprovalDecision | None, ApprovedOrderIntent | None, ExecutionAttempt | None]:
        decision = self._r.decisions.for_proposal(proposal.proposal_governance_id)
        intent = self._r.intents.for_proposal(proposal.proposal_governance_id)
        attempt = (
            None if intent is None else self._r.attempts.for_intent(intent.intent_governance_id)
        )
        return decision, intent, attempt

    # -- Today -----------------------------------------------------------------------

    def today(self) -> TodayView:
        now = self._clock()
        engaged = self._r.kill_switch.is_engaged()
        cards = tuple(self._card(p, now, engaged) for p in self._all_proposals())
        today = now.date()
        todays = tuple(c for c in cards if c.created_at.date() == today or not c.state_is_settled())
        active = self.active_trades()
        try:
            market_open = self._broker.fetch_clock().is_open
            source = (
                "the simulation"
                if self._capability.capability is ExecutionCapability.SIMULATION
                else "the Alpaca paper endpoint"
            )
            market = (
                f"Open (as reported by {source})"
                if market_open
                else f"Closed (as reported by {source})"
            )
        except Exception as error:  # noqa: BLE001 - a status page must not fail closed
            market = f"Unknown ({type(error).__name__})"
        positions = sum(
            1
            for c in cards
            if c.execution is not None
            and c.execution.state in {HumanState.FILLED, HumanState.PARTIALLY_FILLED}
            and not c.execution.position_closed
        )
        return TodayView(
            session_date=today.isoformat(),
            generated_at=now,
            system_status=("Execution stopped by the kill switch" if engaged else "Operating"),
            market_status=market,
            kill_switch_engaged=engaged,
            capability=self._capability,
            opportunities=todays,
            needs_action_count=sum(1 for c in todays if c.state is HumanState.NEEDS_DECISION),
            active_positions_count=positions,
            active_executions_count=len(active),
            open_opportunities_count=sum(1 for c in todays if not c.state_is_settled()),
        )

    def opportunity(self, proposal_id: str) -> OpportunityCard:
        proposal = self._r.proposals.get(proposal_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {proposal_id!r} exists")
        return self._card(proposal, self._clock(), self._r.kill_switch.is_engaged())

    def _card(self, proposal: TradeProposal, now: datetime, engaged: bool) -> OpportunityCard:
        decision, intent, attempt = self._execution_for(proposal)
        execution = None if intent is None else self._summary(proposal, decision, intent, attempt)
        state, blocked, attention = self._proposal_state(
            proposal, decision, intent, attempt, now, engaged
        )
        configuration = self._configuration(proposal)
        passed = [c for c in proposal.risk_checks if c.outcome is RiskCheckOutcome.PASSED]
        failed = [c for c in proposal.risk_checks if c.outcome is not RiskCheckOutcome.PASSED]
        context = self._r.contexts.get(proposal.evaluation_context_id)
        strategy = context.strategy_version if context is not None else NOT_AVAILABLE
        scenario = self._staged_scenarios().get(proposal.symbol)
        evidence = tuple(f"{c.check_id}: {c.detail}" for c in proposal.risk_checks[:6])
        risk_amount = (
            (proposal.limit_price - proposal.stop_loss_price) * Decimal(proposal.quantity)
            if proposal.limit_price is not None
            else None
        )
        risk_percent = (
            (risk_amount / proposal.estimated_total_cash_required * Decimal(100))
            if risk_amount is not None and proposal.estimated_total_cash_required > 0
            else None
        )
        return OpportunityCard(
            proposal_id=proposal.proposal_governance_id,
            proposal_version=proposal.proposal_version,
            symbol=proposal.symbol,
            terms=self._terms(proposal),
            maximum_capital=(
                _money(configuration.maximum_capital_per_trade)
                if configuration is not None
                else NOT_AVAILABLE
            ),
            stop_price=_money(proposal.stop_loss_price),
            target_price=_money(proposal.profit_exit_price),
            risk_amount=_money(risk_amount),
            risk_percent=(f"{risk_percent:.2f}%" if risk_percent is not None else NOT_AVAILABLE),
            reason=(
                f"Proposed by strategy {strategy}: {len(passed)} of {len(proposal.risk_checks)} "
                f"risk checks passed" + ("" if not failed else f", {len(failed)} not passed")
            ),
            evidence=evidence,
            created_at=proposal.created_at,
            expires_at=proposal.expires_at,
            state=state,
            decision_available=state is HumanState.NEEDS_DECISION,
            blocked_note=blocked,
            attention_note=attention,
            intent_id=None if intent is None else intent.intent_governance_id,
            execution=execution,
            scenario=scenario,
        )

    def _proposal_state(
        self,
        proposal: TradeProposal,
        decision: ApprovalDecision | None,
        intent: ApprovedOrderIntent | None,
        attempt: ExecutionAttempt | None,
        now: datetime,
        engaged: bool,
    ) -> tuple[HumanState, str | None, str | None]:
        if attempt is not None:
            state = human_state_for_attempt(attempt)
            note = None
            if state is HumanState.NEEDS_ATTENTION:
                note = (
                    "Outcome unknown — do not retry. The order may have reached the broker; "
                    "the console keeps checking the same order."
                )
            elif state is HumanState.BLOCKED:
                note = f"Nothing was sent: {attempt.failure_detail or NOT_AVAILABLE}"
            return state, None, note
        if proposal.status is ProposalStatus.PREPARED:
            if proposal.expired_at(now):
                return HumanState.EXPIRED, None, None
            if engaged:
                return (
                    HumanState.NEEDS_DECISION,
                    "Execution is blocked while the kill switch is engaged. A decision cannot "
                    "be confirmed until it is released.",
                    None,
                )
            return HumanState.NEEDS_DECISION, None, None
        if proposal.status is ProposalStatus.APPROVED:
            if intent is None:
                return (
                    HumanState.APPROVED,
                    None,
                    "Approved, but no order intent was issued. Nothing was sent.",
                )
            return HumanState.APPROVED, None, "Approved; awaiting execution. Nothing was sent yet."
        if proposal.status is ProposalStatus.REJECTED:
            return HumanState.REJECTED, None, None
        if proposal.status is ProposalStatus.CANCELLED:
            return HumanState.REJECTED, None, "Cancelled by the operator."
        if proposal.status is ProposalStatus.INVALIDATED:
            return (
                HumanState.BLOCKED,
                "Invalidated by a configuration change. Nothing was sent.",
                None,
            )
        return HumanState.EXPIRED, None, None

    # -- approve / reject ----------------------------------------------------------

    def prepare_approval(self, proposal_id: str) -> ConfirmationView:
        return self._prepare(proposal_id, OperatorAction.APPROVE.value)

    def prepare_rejection(self, proposal_id: str) -> ConfirmationView:
        return self._prepare(proposal_id, OperatorAction.REJECT.value)

    def _prepare(self, proposal_id: str, action: str) -> ConfirmationView:
        now = self._clock()
        proposal = self._r.proposals.get(proposal_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {proposal_id!r} exists")
        if proposal.status is not ProposalStatus.PREPARED:
            raise ConsoleRefusalError(
                "Already decided",
                f"This opportunity is {proposal.status.value.lower()} and cannot be decided again. "
                "Nothing was done.",
            )
        if proposal.expired_at(now):
            raise ConsoleRefusalError("Expired", "This opportunity has expired. Nothing was done.")
        configuration = self._configuration(proposal)
        approval_expires = (
            now + timedelta(seconds=configuration.approval_expiry_seconds)
            if configuration is not None
            else None
        )
        ticket = ConfirmationTicket(
            action=action,
            proposal_id=proposal.proposal_governance_id,
            proposal_version=proposal.proposal_version,
            fingerprint=proposal.content_fingerprint,
            issued_at=now,
        )
        return ConfirmationView(
            action=action,
            proposal_id=proposal.proposal_governance_id,
            proposal_version=proposal.proposal_version,
            terms=self._terms(proposal),
            account=f"{self._capability.label} account",
            environment=self._capability.capability.value,
            proposal_expires_at=proposal.expires_at,
            approval_expires_at=approval_expires,
            ticket=ticket.encode(self._signer),
            kill_switch_engaged=self._r.kill_switch.is_engaged(),
        )

    def _authoritative(self, ticket: ConfirmationTicket, now: datetime) -> TradeProposal:
        """Re-read the proposal and refuse anything that is not exactly what was shown."""
        proposal = self._r.proposals.get(ticket.proposal_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {ticket.proposal_id!r} exists")
        if (
            proposal.proposal_version != ticket.proposal_version
            or proposal.content_fingerprint != ticket.fingerprint
        ):
            raise ConsoleRefusalError(
                "Terms changed",
                "The opportunity changed after this page was opened, so the terms shown are no "
                "longer the current ones. Nothing was done. Open it again to see the current "
                "terms.",
            )
        if proposal.expired_at(now):
            raise ConsoleRefusalError(
                "Expired", "This opportunity expired before it was confirmed. Nothing was sent."
            )
        return proposal

    def confirm_rejection(self, proposal_id: str, token: str) -> ActionOutcome:
        now = self._clock()
        ticket = ConfirmationTicket.decode(token, signer=self._signer, now=now)
        if ticket.action != OperatorAction.REJECT.value or ticket.proposal_id != proposal_id:
            raise ConsoleRefusalError("Out of date", _STALE_TICKET)
        proposal = self._r.proposals.get(proposal_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {proposal_id!r} exists")
        if proposal.status is ProposalStatus.REJECTED:
            return ActionOutcome(
                True,
                "Already rejected",
                "This opportunity was already rejected. Nothing was sent.",
                "nothing_sent",
                proposal_id=proposal_id,
                state=HumanState.REJECTED,
            )
        self._authoritative(ticket, now)
        DecidePaperBoundTradeProposalHandler(
            configurations=self._r.configurations,
            decisions=self._r.decisions,
            proposals=self._r.proposals,
            time_bases=self._r.time_bases,
            broker=self._broker,
            time_source=self._time_source,
        ).handle(
            DecidePaperBoundTradeProposalCommand(
                proposal_governance_id=proposal_id,
                decision_governance_id=f"DEC-{proposal_id}",
                action=OperatorAction.REJECT,
                operator_identity=self._operator,
            )
        )
        return ActionOutcome(
            True,
            "Rejected",
            "The opportunity was rejected and recorded. Nothing was sent.",
            "nothing_sent",
            proposal_id=proposal_id,
            state=HumanState.REJECTED,
        )

    def confirm_approval(self, proposal_id: str, token: str) -> ActionOutcome:
        """CONFIRM APPROVAL: re-read, refuse stale or blocked, then the existing chain.

        Idempotent by construction: every identifier is derived from the proposal's, so a
        second confirmation resumes at the first step whose row already exists and ends by
        reporting the existing execution.
        """
        now = self._clock()
        ticket = ConfirmationTicket.decode(token, signer=self._signer, now=now)
        if ticket.action != OperatorAction.APPROVE.value or ticket.proposal_id != proposal_id:
            raise ConsoleRefusalError("Out of date", _STALE_TICKET)
        proposal = self._r.proposals.get(proposal_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {proposal_id!r} exists")

        decision = self._r.decisions.for_proposal(proposal_id)
        intent = self._r.intents.for_proposal(proposal_id)
        attempt = (
            None if intent is None else self._r.attempts.for_intent(intent.intent_governance_id)
        )
        if attempt is not None:
            # A duplicate: the execution exists. Report it; create nothing.
            return self._outcome_for_attempt(attempt, intent, duplicate=True)
        if proposal.status is ProposalStatus.REJECTED or (
            decision is not None and decision.action is not OperatorAction.APPROVE
        ):
            raise ConsoleRefusalError(
                "Already rejected", "This opportunity was already rejected. Nothing was sent."
            )
        if self._r.kill_switch.is_engaged():
            raise ConsoleRefusalError(
                "Execution blocked",
                "The kill switch is engaged, so this approval cannot be confirmed. Nothing was "
                "sent. Release the kill switch on the Safety page first.",
            )

        if decision is None:
            proposal = self._authoritative(ticket, now)
            DecidePaperBoundTradeProposalHandler(
                configurations=self._r.configurations,
                decisions=self._r.decisions,
                proposals=self._r.proposals,
                time_bases=self._r.time_bases,
                broker=self._broker,
                time_source=self._time_source,
            ).handle(
                DecidePaperBoundTradeProposalCommand(
                    proposal_governance_id=proposal_id,
                    decision_governance_id=f"DEC-{proposal_id}",
                    action=OperatorAction.APPROVE,
                    operator_identity=self._operator,
                )
            )
        elif (
            decision.proposal_version != ticket.proposal_version
            or decision.approved_fingerprint != ticket.fingerprint
        ):
            raise ConsoleRefusalError(
                "Terms changed",
                "A different version of this opportunity was already decided. Nothing was done.",
            )

        if intent is None:
            intent = (
                IssuePaperBoundOrderIntentHandler(
                    approval_decisions=self._r.decisions,
                    intents=self._r.intents,
                    proposals=self._r.proposals,
                    time_bases=self._r.time_bases,
                    broker=self._broker,
                    time_source=self._time_source,
                )
                .handle(
                    IssuePaperBoundOrderIntentCommand(
                        intent_governance_id=f"INT-{proposal_id}",
                        proposal_governance_id=proposal_id,
                        idempotency_key=f"IDEM-{proposal_id}",
                    )
                )
                .intent
            )

        authorization = self._r.authorizations.latest_for_intent(intent.intent_governance_id)
        if authorization is None or authorization.is_consumed or authorization.expires_at <= now:
            version = self._r.previews.next_version_for_intent(intent.intent_governance_id)
            preview = PreviewPaperSubmissionHandler(
                intents=self._r.intents,
                configurations=self._r.configurations,
                time_bases=self._r.time_bases,
                snapshots=self._r.snapshots,
                previews=self._r.previews,
                events=self._r.events,
                broker=self._broker,
                market_data=self._market_data,
                kill_switch=self._r.kill_switch,
                time_source=self._time_source,
            ).handle(
                PreviewPaperSubmissionCommand(
                    intent_governance_id=intent.intent_governance_id,
                    preview_id=f"PVW-{proposal_id}-{version}",
                    account_snapshot_id=f"SNP-{proposal_id}-{version}",
                    created_at=now,
                )
            )
            shown = self._terms(proposal)
            if (
                preview.order.symbol != shown.symbol
                or preview.order.quantity != shown.quantity
                or preview.order.order_type.value != shown.order_type
                or _money(preview.order.limit_price) != shown.limit_price
                or preview.order.side != shown.side
            ):
                raise ConsoleRefusalError(
                    "Terms changed",
                    "The order the engine would send differs from the terms shown, so it was "
                    "not authorized. Nothing was sent. An operator must review this opportunity.",
                )
            if not preview.is_authorizable:
                return ActionOutcome(
                    False,
                    "Approved, execution blocked",
                    "The approval was recorded but execution is blocked: "
                    + "; ".join(preview.refusals)
                    + ". Nothing was sent.",
                    "nothing_sent",
                    proposal_id=proposal_id,
                    intent_id=intent.intent_governance_id,
                    state=HumanState.APPROVED,
                )
            configuration = self._configuration(proposal)
            validity = MAXIMUM_AUTHORIZATION_VALIDITY_SECONDS
            if configuration is not None:
                validity = min(validity, configuration.approval_expiry_seconds)
            AuthorizePaperSubmissionHandler(
                previews=self._r.previews,
                authorizations=self._r.authorizations,
                events=self._r.events,
                broker=self._broker,
                time_source=self._time_source,
            ).handle(
                AuthorizePaperSubmissionCommand(
                    authorization_id=f"AUT-{proposal_id}-{version}",
                    preview_id=preview.preview_id,
                    expected_request_fingerprint=preview.request_fingerprint,
                    authorized_by=self._operator,
                    authorized_at=now,
                    validity_seconds=validity,
                )
            )

        result = SubmitAuthorizedPaperOrderHandler(
            intents=self._r.intents,
            configurations=self._r.configurations,
            time_bases=self._r.time_bases,
            previews=self._r.previews,
            authorizations=self._r.authorizations,
            attempts=self._r.attempts,
            acknowledgements=self._r.acknowledgements,
            events=self._r.events,
            snapshots=self._r.snapshots,
            broker=self._broker,
            market_data=self._market_data,
            kill_switch=self._r.kill_switch,
            time_source=self._time_source,
        ).handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=intent.intent_governance_id,
                attempt_id=f"ATT-{proposal_id}",
                account_snapshot_id=f"SNP-{proposal_id}-dispatch",
                at=self._clock(),
            )
        )
        return self._outcome_for_attempt(result.attempt, intent, duplicate=False)

    def _broker_noun(self) -> str:
        """MILESTONE-088. The broker described in operator-facing text, never hardcoded."""
        if self._capability.capability is ExecutionCapability.SIMULATION:
            return "simulated broker"
        return "Alpaca paper endpoint"

    def _outcome_for_attempt(
        self, attempt: ExecutionAttempt, intent: ApprovedOrderIntent | None, *, duplicate: bool
    ) -> ActionOutcome:
        state = human_state_for_attempt(attempt)
        intent_id = attempt.intent_governance_id if intent is None else intent.intent_governance_id
        prefix = "Already confirmed. " if duplicate else ""
        broker = self._broker_noun()
        if state is HumanState.NEEDS_ATTENTION:
            return ActionOutcome(
                False,
                "Outcome unknown — do not retry",
                prefix + f"The order may have reached the {broker} and no answer proves what "
                "happened. The console keeps checking the same order; it will never be sent again.",
                "unknown",
                attempt.intent_governance_id,
                intent_id,
                state,
            )
        if state is HumanState.BLOCKED:
            return ActionOutcome(
                False,
                "Nothing was sent",
                prefix + f"Execution was blocked before anything left: {attempt.failure_detail}",
                "nothing_sent",
                attempt.intent_governance_id,
                intent_id,
                state,
            )
        if state is HumanState.REJECTED:
            return ActionOutcome(
                False,
                "Rejected by the broker",
                prefix + f"The {broker} refused the order ({attempt.failure_code}). "
                "No position was opened.",
                "sent",
                attempt.intent_governance_id,
                intent_id,
                state,
            )
        return ActionOutcome(
            True,
            "Approved and sent" if not duplicate else "Already confirmed",
            prefix + f"The order was sent to the {broker} and is {state.value.lower()}.",
            "sent",
            attempt.intent_governance_id,
            intent_id,
            state,
        )

    # -- Active trades -------------------------------------------------------------

    def active_trades(self) -> tuple[ExecutionSummary, ...]:
        rows: list[ExecutionSummary] = []
        for proposal in self._all_proposals():
            decision, intent, attempt = self._execution_for(proposal)
            if intent is None:
                continue
            if attempt is not None and attempt.is_terminal and not position_is_open(attempt):
                # A cancelled entry that had filled shares still holds a position (M087).
                if not (
                    self._exits is not None
                    and attempt.state is PaperExecutionState.CANCELED
                    and attempt.filled_quantity is not None
                    and attempt.filled_quantity > 0
                ):
                    continue
            if self._position_closed(intent.intent_governance_id):
                continue  # a VERIFIED closed position belongs to History, not Active trades
            rows.append(self._summary(proposal, decision, intent, attempt))
        rows.sort(key=lambda s: s.claimed_at or s.decided_at or datetime.min.replace(tzinfo=UTC))
        return tuple(rows)

    def execution(self, intent_id: str) -> ExecutionSummary:
        intent = self._r.intents.get(intent_id)
        if intent is None:
            raise NotFoundError(f"no approved order intent {intent_id!r} exists")
        proposal = self._r.proposals.get(intent.proposal_governance_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {intent.proposal_governance_id!r} exists")
        decision = self._r.decisions.for_proposal(proposal.proposal_governance_id)
        attempt = self._r.attempts.for_intent(intent_id)
        return self._summary(proposal, decision, intent, attempt)

    def _summary(
        self,
        proposal: TradeProposal,
        decision: ApprovalDecision | None,
        intent: ApprovedOrderIntent,
        attempt: ExecutionAttempt | None,
    ) -> ExecutionSummary:
        events = self._r.events.for_intent(intent.intent_governance_id)
        authorization = self._r.authorizations.latest_for_intent(intent.intent_governance_id)
        position_open = attempt is not None and position_is_open(attempt)
        state = human_state_for_attempt(attempt) if attempt is not None else HumanState.APPROVED
        warnings: list[str] = []
        pending: str | None = None
        reconciliation = NOT_AVAILABLE
        if attempt is not None:
            rounds = self._r.rounds.for_attempt(attempt.attempt_id)
            complete = [r for r in rounds if r.is_complete]
            if rounds:
                reconciliation = (
                    f"{len(complete)} of {len(rounds)} reconciliation rounds completed"
                    + (
                        f"; last outcome {complete[-1].outcome.value.lower().replace('_', ' ')}"
                        if complete and complete[-1].outcome is not None
                        else ""
                    )
                )
            else:
                reconciliation = "No reconciliation round yet"
            if attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN:
                pending = (
                    "Outcome unknown — do not retry. The console keeps asking the broker about "
                    "this exact order."
                )
                warnings.append("The broker's answer to the submission was lost.")
            elif attempt.state in {
                PaperExecutionState.PAPER_SUBMITTED,
                PaperExecutionState.PAPER_ACCEPTED,
            }:
                pending = "Waiting for the broker to fill the order."
            elif attempt.state is PaperExecutionState.PARTIALLY_FILLED:
                pending = (
                    "Partially filled; the rest is still working. The filled part is an "
                    "open position."
                )
            elif attempt.state is PaperExecutionState.FILLED and position_open:
                pending = OPEN_POSITION_EXIT_STATUS + " Nothing is sent."
            elif attempt.state is PaperExecutionState.CANCEL_REQUESTED:
                pending = "Cancel requested; a request is not yet a cancellation."
            if attempt.failure_code and attempt.state is not PaperExecutionState.REJECTED:
                warnings.append(f"Recorded condition: {attempt.failure_code}")
            for event in events:
                if event.event_type in {
                    "RECONCILE_NOT_FOUND_KNOWN_ORDER",
                    "RECONCILE_NOT_FOUND_AFTER_OBSERVATION",
                    "RECONCILE_FOUND_ROUND_WITHOUT_OBSERVATION",
                    "RECONCILE_LOOKUP_FAILED",
                    "IDENTITY_OBSERVED_NOT_ATTRIBUTED",
                }:
                    warnings.append(_plain_event(event))
        elif authorization is not None and not authorization.is_consumed:
            pending = "Authorized; the order has not been sent."
        else:
            pending = "Approved; nothing has been sent."

        # MILESTONE-087: the exit, the group and the deadline.
        exit_summary = None
        category = "Working entry order"
        can_review = False
        closed = False
        exit_status = OPEN_POSITION_EXIT_STATUS if position_open else NOT_AVAILABLE
        tone, note = "info", ""
        if self._exits is not None:
            now = self._clock()
            exit_summary = self._exits.summary(intent, attempt, now)
            latest_exit = self._exits.latest_exit(intent.intent_governance_id)
            category = self._exits.category(attempt, latest_exit)
            closed = latest_exit is not None and latest_exit.position_closed
            held = category == "Open position"
            # "Review exit" is offered for every held position; the review page itself shows
            # an engaged kill switch, and the confirmation refuses while it is engaged.
            can_review = held
            if closed:
                exit_status = "Position closed — verified at the broker."
                position_open = False
            elif category == "Exit in progress":
                exit_status = (
                    "Exit in progress — nothing further is sent without your confirmation."
                )
            elif category == "Needs attention" and exit_summary is not None:
                exit_status = "Exit outcome unknown — do not retry."
            elif held:
                exit_status = OPEN_POSITION_REVIEWABLE_STATUS
                position_open = True
            if attempt is not None and attempt.state is PaperExecutionState.FILLED and held:
                pending = OPEN_POSITION_REVIEWABLE_STATUS
            from empirical_platform.usecases.operator_console_exits import deadline_status

            tone, note = deadline_status(
                deadline=intent.mandatory_liquidation_at,
                now=now,
                position_open=held or category == "Exit in progress",
                position_closed=closed,
            )
            if held and now >= intent.mandatory_liquidation_at:
                warnings.append(note)
        return ExecutionSummary(
            intent_id=intent.intent_governance_id,
            proposal_id=proposal.proposal_governance_id,
            symbol=proposal.symbol,
            state=state,
            raw_state=attempt.state.value if attempt is not None else "NOT_DISPATCHED",
            terms=self._terms(proposal),
            decision_by=decision.operator_identity if decision is not None else NOT_AVAILABLE,
            decided_at=decision.decided_at if decision is not None else None,
            broker_order_id=(
                attempt.broker_order_id
                if attempt is not None and attempt.broker_order_id
                else NOT_AVAILABLE
            ),
            claimed_at=attempt.claimed_at if attempt is not None else None,
            submitted_at=attempt.submitted_at if attempt is not None else None,
            acknowledged_at=attempt.acknowledged_at if attempt is not None else None,
            terminal_at=attempt.terminal_at if attempt is not None else None,
            filled_quantity=(
                _quantity(attempt.filled_quantity)
                if attempt is not None and attempt.filled_quantity is not None
                else NOT_AVAILABLE
            ),
            filled_avg_price=(
                _money(attempt.filled_avg_price)
                if attempt is not None and attempt.filled_avg_price is not None
                else NOT_AVAILABLE
            ),
            pending_reason=pending,
            reconciliation=reconciliation,
            warnings=tuple(dict.fromkeys(warnings)),
            timeline=self._timeline(proposal, decision, intent, authorization, attempt, events),
            is_terminal=attempt is not None and attempt.is_terminal,
            outcome_known=attempt is None or attempt.outcome_is_known,
            can_cancel=attempt is not None
            and attempt.state
            in {
                PaperExecutionState.PAPER_SUBMITTED,
                PaperExecutionState.PAPER_ACCEPTED,
                PaperExecutionState.PARTIALLY_FILLED,
            },
            execution_kind=f"{self._capability.label} execution",
            position_open=position_open,
            exit_status=exit_status,
            category=category,
            exit=exit_summary,
            can_review_exit=can_review,
            liquidation_deadline=intent.mandatory_liquidation_at,
            deadline_tone=tone,
            deadline_note=note,
            position_closed=closed,
        )

    def _timeline(
        self,
        proposal: TradeProposal,
        decision: ApprovalDecision | None,
        intent: ApprovedOrderIntent,
        authorization: object | None,
        attempt: ExecutionAttempt | None,
        events: Iterable[PaperExecutionEvent],
    ) -> tuple[TimelineStep, ...]:
        """Only steps the durable record proves; nothing is inferred."""
        steps = [
            TimelineStep("Proposal", proposal.created_at, True, proposal.proposal_governance_id)
        ]
        steps.append(
            TimelineStep(
                "Owner approved",
                decision.decided_at if decision is not None else None,
                decision is not None,
                decision.operator_identity if decision is not None else "",
            )
        )
        steps.append(
            TimelineStep("Intent issued", intent.created_at, True, intent.intent_governance_id)
        )
        authorized_at = getattr(authorization, "authorized_at", None)
        steps.append(
            TimelineStep(
                "Authorized",
                authorized_at if isinstance(authorized_at, datetime) else None,
                authorization is not None,
                "",
            )
        )
        submitted = attempt is not None and attempt.submitted_at is not None
        steps.append(
            TimelineStep(
                "Submitted",
                attempt.submitted_at if attempt is not None else None,
                submitted,
                ""
                if attempt is None or attempt.broker_order_id is None
                else attempt.broker_order_id,
            )
        )
        accepted = attempt is not None and (
            attempt.state in _ACCEPTED_OR_BEYOND or attempt.acknowledged_at is not None
        )
        steps.append(
            TimelineStep(
                "Accepted",
                attempt.acknowledged_at if accepted and attempt is not None else None,
                accepted,
                "",
            )
        )
        if attempt is not None and attempt.is_terminal:
            label = {
                PaperExecutionState.FILLED: "Filled",
                PaperExecutionState.CANCELED: "Cancelled",
                PaperExecutionState.REJECTED: "Rejected"
                if attempt.failure_code != "NOT_SENT"
                else "Blocked",
                PaperExecutionState.EXPIRED: "Expired",
            }[attempt.state]
            steps.append(TimelineStep(label, attempt.terminal_at, True, attempt.failure_code or ""))
        elif attempt is not None and attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN:
            steps.append(TimelineStep("Needs attention", None, True, "outcome UNKNOWN"))
        else:
            steps.append(TimelineStep("Filled / Cancelled / Needs attention", None, False, ""))
        del events
        return tuple(steps)

    # -- History -------------------------------------------------------------------

    def history(
        self,
        *,
        date: str | None = None,
        symbol: str | None = None,
        decision: str | None = None,
        outcome: str | None = None,
    ) -> tuple[HistoryEntry, ...]:
        rows: list[HistoryEntry] = []
        for proposal in self._all_proposals():
            dec, intent, attempt = self._execution_for(proposal)
            if date and proposal.created_at.date().isoformat() != date:
                continue
            if symbol and proposal.symbol != symbol.strip().upper():
                continue
            decision_word = NOT_AVAILABLE
            if dec is not None:
                decision_word = {
                    "APPROVE": "Approved",
                    "REJECT": "Rejected",
                    "CANCEL": "Cancelled",
                }[dec.action.value]
            if decision and decision_word != decision:
                continue
            result_text = NOT_AVAILABLE
            if attempt is not None:
                final = human_state_for_attempt(attempt)
                kind = f"{self._capability.label} execution"
                exec_outcome = final.value
                if self._exits is not None and intent is not None:
                    exit_summary = self._exits.summary(intent, attempt, self._clock())
                    if exit_summary is not None and exit_summary.position_closed:
                        exec_outcome = "Position closed (simulation)"
                        result_text = exit_summary.result_text
                    elif exit_summary is not None:
                        exec_outcome = f"{final.value}; exit {exit_summary.state.value.lower()}"
            elif intent is not None:
                final = HumanState.APPROVED
                kind = "Owner decision"
                exec_outcome = "Not executed"
            elif dec is not None:
                final = (
                    HumanState.REJECTED
                    if dec.action is not OperatorAction.APPROVE
                    else HumanState.APPROVED
                )
                kind = "Owner decision"
                exec_outcome = "Not executed"
            else:
                final = (
                    HumanState.EXPIRED
                    if proposal.status in {ProposalStatus.EXPIRED, ProposalStatus.PREPARED}
                    and proposal.expired_at(self._clock())
                    else HumanState.NEEDS_DECISION
                    if proposal.status is ProposalStatus.PREPARED
                    else HumanState.BLOCKED
                )
                kind = "Model proposal"
                exec_outcome = "No decision"
            if outcome and final.value != outcome:
                continue
            rows.append(
                HistoryEntry(
                    proposal_id=proposal.proposal_governance_id,
                    symbol=proposal.symbol,
                    created_at=proposal.created_at,
                    proposal_state=proposal.status.value.capitalize(),
                    decision=decision_word,
                    decided_at=dec.decided_at if dec is not None else None,
                    decided_by=dec.operator_identity if dec is not None else NOT_AVAILABLE,
                    execution_kind=kind,
                    execution_outcome=exec_outcome,
                    final_state=final,
                    quantity=(
                        _quantity(attempt.filled_quantity)
                        if attempt is not None and attempt.filled_quantity is not None
                        else str(proposal.quantity)
                    ),
                    price=(
                        _money(attempt.filled_avg_price)
                        if attempt is not None and attempt.filled_avg_price is not None
                        else _money(proposal.limit_price)
                    ),
                    result=result_text,
                    intent_id=None if intent is None else intent.intent_governance_id,
                    timestamp=(
                        attempt.terminal_at or attempt.acknowledged_at or attempt.claimed_at
                        if attempt is not None
                        else dec.decided_at
                        if dec is not None
                        else proposal.created_at
                    ),
                )
            )
        rows.sort(key=lambda r: r.timestamp, reverse=True)
        return tuple(rows)

    # -- Safety ----------------------------------------------------------------------

    def safety(self, configuration_governance_id: str) -> SafetyView:
        configuration = self._r.configurations.latest(configuration_governance_id)
        rules: list[RuleRow] = []
        m084_switch = NOT_AVAILABLE
        version = NOT_AVAILABLE
        if configuration is not None:
            version = str(configuration.configuration_version)
            m084_switch = (
                "Engaged" if configuration.kill_switch is KillSwitchState.ENGAGED else "Disengaged"
            )
            rules = [
                RuleRow("Direction", "Long only (BUY); the request type cannot express a sell"),
                RuleRow(
                    "Short selling",
                    "Not permitted" if not configuration.short_selling_permitted else "Permitted",
                ),
                RuleRow(
                    "Whole shares",
                    "Quantities are whole shares; fractional orders cannot be expressed",
                ),
                RuleRow("Leverage", f"Maximum {configuration.maximum_leverage}x"),
                RuleRow(
                    "Overnight positions",
                    "Not permitted"
                    if not configuration.overnight_positions_permitted
                    else "Permitted",
                ),
                RuleRow("Watchlist", ", ".join(configuration.watchlist) or NOT_AVAILABLE),
                RuleRow(
                    "Capital per trade",
                    f"{_money(configuration.maximum_capital_per_trade)} "
                    f"{configuration.base_currency} "
                    f"({configuration.maximum_percent_per_trade}% cap)",
                ),
                RuleRow(
                    "Deployable capital",
                    f"{_money(configuration.maximum_deployable_capital)} "
                    f"{configuration.base_currency}",
                ),
                RuleRow(
                    "Quote freshness", f"{configuration.maximum_market_data_age_seconds} seconds"
                ),
                RuleRow("Spread limit", f"{configuration.maximum_spread_percent}%"),
                RuleRow(
                    "Trading window",
                    f"{configuration.earliest_entry_time:%H:%M}–"
                    f"{configuration.latest_entry_time:%H:%M} "
                    f"{configuration.operator_timezone}, "
                    f"{configuration.permitted_session.value.lower()} session",
                ),
                RuleRow(
                    "Order types", ", ".join(t.value for t in configuration.permitted_order_types)
                ),
                RuleRow("Proposal expiry", f"{configuration.proposal_expiry_seconds} seconds"),
                RuleRow("Approval expiry", f"{configuration.approval_expiry_seconds} seconds"),
            ]
        return SafetyView(
            # MILESTONE-088: CAPABILITIES is the static, milestone-agnostic display table --
            # correct for a SIMULATION-composed console (self._capability already equals
            # CAPABILITIES[0], so this is a no-op there) but stale for a PAPER-composed one,
            # which would otherwise show its OWN capability as "locked" on its own Safety
            # page. The entry matching what THIS service actually composed as is replaced by
            # the true, verified `self._capability`; the other two entries are unaffected.
            capabilities=tuple(
                self._capability if c.capability is self._capability.capability else c
                for c in CAPABILITIES
            ),
            active_capability=self._capability,
            execution_kill_switch_engaged=self._r.kill_switch.is_engaged(),
            configuration_kill_switch=m084_switch,
            configuration_id=configuration_governance_id,
            configuration_version=version,
            rules=tuple(rules),
        )

    def set_kill_switch(self, *, engaged: bool, reason: str) -> ActionOutcome:
        changed = SetExecutionKillSwitchHandler(kill_switch=self._r.kill_switch).handle(
            SetExecutionKillSwitchCommand(
                engaged=engaged,
                changed_by=self._operator,
                changed_at=self._clock(),
                reason=reason.strip()
                or ("engaged from the console" if engaged else "released from the console"),
            )
        )
        if engaged:
            message = (
                "The kill switch is engaged. No new execution can start; existing orders remain "
                "visible and keep being reconciled. Nothing was sent."
            )
        else:
            message = (
                "The kill switch is released. Execution can be confirmed again. Nothing was sent."
            )
        if not changed:
            message = "Already in that state. " + message
        return ActionOutcome(
            True, "Kill switch " + ("engaged" if engaged else "released"), message, "nothing_sent"
        )

    # -- Reconciliation ------------------------------------------------------------

    def refresh_executions(self) -> tuple[str, ...]:
        """Ask the broker about every non-terminal execution through the M085 reconciler.

        Returns the intent ids that were reconciled. A failure of one lookup is recorded
        by the handler itself (a FAILED round) and never stops the others.
        """
        refreshed: list[str] = []
        for attempt in self._r.attempts.list_recent(500):
            if attempt.state not in _RECONCILABLE_STATES:
                continue
            try:
                ReconcilePaperOrderHandler(
                    attempts=self._r.attempts,
                    acknowledgements=self._r.acknowledgements,
                    events=self._r.events,
                    broker=self._broker,
                    authorizations=self._r.authorizations,
                    previews=self._r.previews,
                    rounds=self._r.rounds,
                    time_source=self._time_source,
                ).handle(
                    ReconcilePaperOrderCommand(
                        intent_governance_id=attempt.intent_governance_id, at=self._clock()
                    )
                )
            except Exception:  # noqa: BLE001, S112 - the handler recorded a FAILED round durably
                continue
            refreshed.append(attempt.intent_governance_id)
        if self._exits is not None:
            refreshed.extend(self._exits.refresh())
        return tuple(refreshed)

    def cancel_execution(self, intent_id: str) -> ActionOutcome:
        attempt = self._r.attempts.for_intent(intent_id)
        if attempt is None:
            raise NotFoundError(f"no execution exists for {intent_id!r}")
        if attempt.is_terminal:
            raise ConsoleRefusalError(
                "Already final",
                f"This execution is already {human_state_for_attempt(attempt).value.lower()}. "
                "Nothing was done.",
            )
        result = CancelPaperOrderHandler(
            attempts=self._r.attempts,
            acknowledgements=self._r.acknowledgements,
            events=self._r.events,
            broker=self._broker,
        ).handle(CancelPaperOrderCommand(intent_governance_id=intent_id, at=self._clock()))
        return ActionOutcome(
            True,
            "Cancel requested",
            "A cancellation was requested. A request is not a cancellation: the order may still "
            f"fill. Current state: {human_state_for_attempt(result).value.lower()}.",
            "sent",
            intent_id=intent_id,
            state=human_state_for_attempt(result),
        )


def _plain_event(event: PaperExecutionEvent) -> str:
    words = {
        "RECONCILE_NOT_FOUND_KNOWN_ORDER": (
            "The broker reported no order under this identity although one was accepted; "
            "nothing is revoked, an operator should check with the broker."
        ),
        "RECONCILE_NOT_FOUND_AFTER_OBSERVATION": (
            "The broker reported no order after one had been observed; an operator should check."
        ),
        "RECONCILE_FOUND_ROUND_WITHOUT_OBSERVATION": (
            "A reconciliation found an order whose record was not stored; an operator should check."
        ),
        "RECONCILE_LOOKUP_FAILED": "A reconciliation lookup failed; the console will try again.",
        "IDENTITY_OBSERVED_NOT_ATTRIBUTED": (
            "An order exists under this identity but was not attributed to this attempt; "
            "an operator should check."
        ),
    }
    return words.get(event.event_type, event.event_type.replace("_", " ").lower())
