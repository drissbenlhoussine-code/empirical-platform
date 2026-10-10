"""MILESTONE-087 commands for human-approved position exits.

EVERY HANDLER IS ONE STEP, as in MILESTONE-085. Assess, preview, authorize, submit,
reconcile and cancel are separate handlers; there is no handler that reviews and sends in
one call, because an explicit human confirmation sits between the review and the send.

THE POSITION IS RE-VERIFIED AT EVERY STEP. Preview judges the position from the entry
record, earlier exits and the broker's own position; authorize requires the preview to be
recent and its fingerprint unchanged; submit re-reads the position and refuses when its
digest differs from the one the human was shown; reconciliation, after a full fill,
verifies the broker position at zero before anything is called closed.

THE ORDER OF THE LAST STEPS IS THE DESIGN (M085). Check the kill switch, claim the dispatch
in the database (consuming the single-use authorization), persist the send boundary, read
the kill switch once more, and only then let the transport send. An ambiguous answer is
`SUBMISSION_UNKNOWN`; nothing here retries a SELL.

M085 CODE IS CALLED, NOT COPIED, where that is safe: the account snapshot reader, the
pure round helpers, the broker error classes. Nothing in M085 is modified.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS,
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionPolicy,
    PaperExecutionState,
    ReconciliationRoundOutcome,
    execution_policy_from_configuration,
    quote_refusal,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    BrokerOrderView,
    ExecutionAttemptRepository,
    ExecutionKillSwitchRepository,
    PaperMarketDataPort,
)
from empirical_platform.decision_candidate.position_exit import (
    BOUND_EXIT_ORDER_STATES,
    EXIT_SEND_BOUNDARY_EVENT_TYPE,
    EXIT_SIDE,
    MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS,
    POSITION_CLOSED_VERIFIED_EVENT_TYPE,
    POSITION_NEEDS_ATTENTION,
    POSITION_NOT_ZERO_AFTER_FILL_EVENT_TYPE,
    PositionExitAttempt,
    PositionExitAuthorization,
    PositionExitEvent,
    PositionExitPreview,
    PositionExitRequest,
    PositionExitState,
    PositionSnapshot,
    derive_exit_client_order_id,
    exit_absence_evaluation,
    exit_attempt_may_have_transmitted,
    exit_authorization_binding_refusal,
    exit_eligibility,
    exit_order_terms_mismatches,
    exit_request_fingerprint,
    exit_send_boundary_binding,
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
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerIdentityExistsError,
    BrokerIdentityUnresolvedError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.paper_time import (
    BoundedInstant,
    PaperTimeSource,
    PaperTimeUncertainError,
    PaperTimeWindow,
    SystemPaperTimeSource,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.paper_execution import _account_reference

__all__ = [
    "MAXIMUM_EXIT_PREVIEW_AGE_SECONDS",
    "AssessPositionExitHandler",
    "AuthorizePositionExitCommand",
    "AuthorizePositionExitHandler",
    "CancelPositionExitCommand",
    "CancelPositionExitHandler",
    "ExitSubmissionResult",
    "POSITION_NEEDS_ATTENTION",
    "PositionAssessment",
    "PositionExitRefusedError",
    "PreviewPositionExitCommand",
    "PreviewPositionExitHandler",
    "ReconcilePositionExitCommand",
    "ReconcilePositionExitHandler",
    "SubmitAuthorizedPositionExitCommand",
    "SubmitAuthorizedPositionExitHandler",
]

#: A review page older than this cannot be authorized: the position must be re-reviewed.
MAXIMUM_EXIT_PREVIEW_AGE_SECONDS = 900

#: Broker order status -> exit state. Closed; an unmapped status is recorded, never guessed.
_BROKER_STATUS_TO_STATE = MappingProxyType(
    {
        "new": PositionExitState.ACCEPTED,
        "accepted": PositionExitState.ACCEPTED,
        "pending_new": PositionExitState.ACCEPTED,
        "held": PositionExitState.ACCEPTED,
        "partially_filled": PositionExitState.PARTIALLY_FILLED,
        "filled": PositionExitState.FILLED,
        "canceled": PositionExitState.CANCELED,
        "expired": PositionExitState.EXPIRED,
        "rejected": PositionExitState.REJECTED,
        "suspended": PositionExitState.REJECTED,
        "pending_cancel": PositionExitState.CANCEL_REQUESTED,
    }
)

_ENTRY_HOLDING_STATES: frozenset[PaperExecutionState] = frozenset(
    {
        PaperExecutionState.FILLED,
        PaperExecutionState.PARTIALLY_FILLED,
        PaperExecutionState.CANCELED,
        PaperExecutionState.CANCEL_REQUESTED,
    }
)


class PositionExitRefusedError(ValueError):
    """An exit this product will not prepare or send, with the reason. Nothing was sent."""


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _event_id(*parts: str) -> str:
    return "XEV-" + _digest("|".join(parts))[:40]


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _account_reference_of(broker: ExitBrokerPort) -> str:
    """The M085 account reference (a digest, never the id) of the broker's account, read now."""
    status, payload = broker.fetch_account()
    if status != 200:
        raise PositionExitRefusedError(f"the account could not be read (HTTP {status})")
    account_id = payload.get("id")
    if not isinstance(account_id, str) or not account_id:
        raise PositionExitRefusedError("the account payload carries no account id")
    return _account_reference(account_id)


def _is_definitive_refusal(status: int, body: str) -> bool:
    """A 403 carrying the documented refusal code, or a 422 that is not an identity collision."""
    try:
        document = json.loads(body) if body else {}
    except json.JSONDecodeError:
        document = {}
    code = document.get("code") if isinstance(document, dict) else None
    if status == 403:
        return True
    return status == 422 and code != 40010001


def _is_identity_collision(status: int, body: str) -> bool:
    try:
        document = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return False
    return status == 422 and isinstance(document, dict) and document.get("code") == 40010001


def _configuration_policy(
    configurations: OperatorTradingConfigurationRepository, intent: ApprovedOrderIntent
) -> ExecutionPolicy:
    """The send-time policy of the configuration version that governs this position's entry.

    MILESTONE-089: this is the durable market-data freshness bound
    (`ExecutionPolicy.quote_maximum_age_seconds`, derived from
    `OperatorTradingConfiguration.maximum_market_data_age_seconds`) M085 already built and
    already governs this SAME position's entry -- reused for the exit's own quote-freshness
    gate rather than a new constant. `ApprovedOrderIntent` already names the exact
    configuration version its entry was evaluated under.
    """
    configuration = configurations.get(
        intent.configuration_governance_id, intent.configuration_version
    )
    if configuration is None:
        raise PositionExitRefusedError(
            "the configuration version that governed this position's entry no longer exists; "
            "its quote-freshness policy cannot be established. Nothing was done."
        )
    return execution_policy_from_configuration(configuration)


def _measure_broker_now(broker: ExitBrokerPort, timing: PaperTimeWindow) -> BoundedInstant:
    """One round trip to the broker's clock, bounded (MILESTONE-085's discipline, reused)."""
    sent = timing.read_monotonic()
    clock = broker.fetch_clock()
    timing.observe_broker_clock(clock.timestamp, sent, timing.read_monotonic())
    return timing.broker_now()


# ---------------------------------------------------------------------------
# Assess
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PositionAssessment:
    """What the eligibility rule saw, and what it decided, for one entry's position."""

    entry_intent: ApprovedOrderIntent
    entry_attempt: ExecutionAttempt | None
    existing_exit: PositionExitAttempt | None
    snapshot: PositionSnapshot
    refusals: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return not self.refusals


class AssessPositionExitHandler:
    """Judge whether an entry's position can be closed now. Reads only; writes nothing."""

    __slots__ = ("_intents", "_entry_attempts", "_exit_attempts", "_broker")

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        entry_attempts: ExecutionAttemptRepository,
        exit_attempts: PositionExitAttemptRepository,
        broker: ExitBrokerPort,
    ) -> None:
        self._intents = intents
        self._entry_attempts = entry_attempts
        self._exit_attempts = exit_attempts
        self._broker = broker

    def handle(self, entry_intent_governance_id: str, *, at: datetime) -> PositionAssessment:
        intent = self._intents.get(entry_intent_governance_id)
        if intent is None:
            raise NotFoundError(f"no approved order intent {entry_intent_governance_id!r} exists")
        entry = self._entry_attempts.for_intent(entry_intent_governance_id)
        exits = self._exit_attempts.for_entry(entry_intent_governance_id)
        sold = sum((x.filled_quantity or Decimal(0)) for x in exits)
        existing = self._exit_attempts.active_for_entry(entry_intent_governance_id)
        position = self._broker.fetch_position(intent.symbol)
        snapshot = PositionSnapshot(
            symbol=intent.symbol,
            entry_intent_governance_id=entry_intent_governance_id,
            entry_attempt_id=None if entry is None else entry.attempt_id,
            entry_state=None if entry is None else entry.state.value,
            entry_filled_quantity=None if entry is None else entry.filled_quantity,
            entry_avg_fill_price=None if entry is None else entry.filled_avg_price,
            exits_filled_quantity=Decimal(sold),
            broker_position_quantity=0 if position is None else int(position.quantity),
            competing_entry_attempt_ids=self._competitors(intent, entry),
            captured_at=at,
        )
        return PositionAssessment(
            entry_intent=intent,
            entry_attempt=entry,
            existing_exit=existing,
            snapshot=snapshot,
            refusals=exit_eligibility(snapshot, existing_exit=existing),
        )

    def _competitors(
        self, intent: ApprovedOrderIntent, entry: ExecutionAttempt | None
    ) -> tuple[str, ...]:
        """Other entry attempts in the same symbol still holding shares (not closed by an exit)."""
        found: list[str] = []
        for other in self._entry_attempts.list_recent(500):
            if entry is not None and other.attempt_id == entry.attempt_id:
                continue
            if other.state not in _ENTRY_HOLDING_STATES:
                continue
            if other.filled_quantity is None or other.filled_quantity <= 0:
                continue
            other_intent = self._intents.get(other.intent_governance_id)
            if other_intent is None or other_intent.symbol != intent.symbol:
                continue
            closer = self._exit_attempts.active_for_entry(other.intent_governance_id)
            if closer is not None and closer.position_closed:
                continue
            found.append(other.attempt_id)
        return tuple(sorted(found))


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreviewPositionExitCommand:
    entry_intent_governance_id: str
    preview_id: str
    created_at: datetime


class PreviewPositionExitHandler:
    """Freeze exactly what the Owner is shown on the exit review page.

    Refuses -- and persists nothing -- when the position is not eligible; the refusal
    reasons are the operator's message. When eligible, the request is built from the
    VERIFIED quantity and the current bid, its broker identity is derived, and the preview
    is stored append-only.

    THE QUOTE MUST BE FRESH, ON THE BROKER'S CLOCK (MILESTONE-089). The bid pricing this
    exit is judged by `quote_refusal` -- M085's own quote-quality gate, reused unchanged --
    against `ExecutionPolicy.quote_maximum_age_seconds`, derived from the SAME
    `OperatorTradingConfiguration` version that governed this position's entry
    (`ApprovedOrderIntent.configuration_governance_id`/`configuration_version`). No new
    constant is introduced: this is the one durable freshness bound the codebase already
    has, and it is measured on the broker's clock exactly as the entry side measures it.
    """

    __slots__ = (
        "_assess",
        "_previews",
        "_events",
        "_broker",
        "_market_data",
        "_configurations",
        "_environment",
        "_time",
    )

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        entry_attempts: ExecutionAttemptRepository,
        exit_attempts: PositionExitAttemptRepository,
        previews: PositionExitPreviewRepository,
        events: PositionExitEventRepository,
        broker: ExitBrokerPort,
        market_data: PaperMarketDataPort,
        configurations: OperatorTradingConfigurationRepository,
        environment: str,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._assess = AssessPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            exit_attempts=exit_attempts,
            broker=broker,
        )
        self._previews = previews
        self._events = events
        self._broker = broker
        self._market_data = market_data
        self._configurations = configurations
        self._environment = environment
        self._time = time_source or SystemPaperTimeSource()

    def handle(self, command: PreviewPositionExitCommand) -> PositionExitPreview:
        assessment = self._assess.handle(command.entry_intent_governance_id, at=command.created_at)
        if not assessment.eligible:
            raise PositionExitRefusedError(
                POSITION_NEEDS_ATTENTION + " " + "; ".join(assessment.refusals)
            )
        entry = assessment.entry_attempt
        assert entry is not None  # eligibility guarantees it
        quantity = assessment.snapshot.attributable_quantity
        assert quantity is not None
        account_reference = _account_reference_of(self._broker)
        policy = _configuration_policy(self._configurations, assessment.entry_intent)
        quote = self._market_data.fetch_quote(assessment.entry_intent.symbol)
        bid = _decimal_or_none(None if quote is None else quote.bid)
        ask = _decimal_or_none(None if quote is None else quote.ask)
        timing = PaperTimeWindow(self._time)
        broker_now = _measure_broker_now(self._broker, timing)
        stale = quote_refusal(
            bid=bid,
            ask=ask,
            captured_at=None if quote is None else quote.captured_at,
            policy=policy,
            broker_now=broker_now,
        )
        if stale is not None:
            raise PositionExitRefusedError(
                POSITION_NEEDS_ATTENTION
                + " The quote is not usable to price this exit: "
                + stale
                + ". Nothing was prepared."
            )
        version = self._previews.next_version_for_entry(command.entry_intent_governance_id)
        request = PositionExitRequest(
            symbol=assessment.entry_intent.symbol,
            side=EXIT_SIDE,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=bid,
            time_in_force="DAY",
            extended_hours=False,
            client_order_id=derive_exit_client_order_id(
                entry_intent_governance_id=command.entry_intent_governance_id,
                account_reference=account_reference,
                preview_id=command.preview_id,
            ),
            entry_intent_governance_id=command.entry_intent_governance_id,
            account_reference=account_reference,
            environment=self._environment,
        )
        deadline = assessment.entry_intent.mandatory_liquidation_at
        preview = PositionExitPreview(
            preview_id=command.preview_id,
            entry_intent_governance_id=command.entry_intent_governance_id,
            entry_attempt_id=entry.attempt_id,
            preview_version=version,
            account_reference=account_reference,
            environment=self._environment,
            request=request,
            request_fingerprint=exit_request_fingerprint(
                request=request,
                entry_attempt_id=entry.attempt_id,
                position_digest=assessment.snapshot.digest,
                liquidation_deadline=deadline,
            ),
            position=assessment.snapshot,
            quote_bid=bid,
            quote_ask=ask,
            quote_captured_at=None if quote is None else quote.captured_at,
            quote_source="absent" if quote is None else quote.source,
            liquidation_deadline=deadline,
            created_at=command.created_at,
        )
        saved = self._previews.save(preview)
        self._events.append(
            PositionExitEvent(
                event_id=_event_id(saved.preview_id, "EXIT_REVIEWED"),
                entry_intent_governance_id=saved.entry_intent_governance_id,
                attempt_id=None,
                event_type="EXIT_REVIEWED",
                occurred_at=command.created_at,
                detail=(
                    f"preview {saved.preview_id} v{saved.preview_version}: SELL_TO_CLOSE "
                    f"{saved.request.quantity} {saved.request.symbol} @ {saved.request.limit_price}"
                )[:500],
            )
        )
        return saved


# ---------------------------------------------------------------------------
# Authorize
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthorizePositionExitCommand:
    authorization_id: str
    preview_id: str
    expected_request_fingerprint: str
    authorized_by: str
    authorized_at: datetime
    validity_seconds: int = MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS


class AuthorizePositionExitHandler:
    """Record one human's explicit permission for exactly one exit preview. Sends nothing."""

    __slots__ = ("_previews", "_authorizations", "_events", "_broker", "_kill_switch", "_time")

    def __init__(
        self,
        *,
        previews: PositionExitPreviewRepository,
        authorizations: PositionExitAuthorizationRepository,
        events: PositionExitEventRepository,
        broker: ExitBrokerPort,
        kill_switch: ExecutionKillSwitchRepository,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._previews = previews
        self._authorizations = authorizations
        self._events = events
        self._broker = broker
        self._kill_switch = kill_switch
        self._time = time_source or SystemPaperTimeSource()

    def handle(self, command: AuthorizePositionExitCommand) -> PositionExitAuthorization:
        preview = self._previews.get(command.preview_id)
        if preview is None:
            raise NotFoundError(f"no exit preview {command.preview_id!r} exists")
        if preview.request_fingerprint != command.expected_request_fingerprint:
            raise PositionExitRefusedError(
                "the exit review shown does not match the stored preview; nothing was authorized"
            )
        age = (command.authorized_at - preview.created_at).total_seconds()
        if age < 0 or age > MAXIMUM_EXIT_PREVIEW_AGE_SECONDS:
            raise PositionExitRefusedError(
                "the exit review page is too old; open the review again to see current terms"
            )
        # RELEASE v1: the kill switch blocks NEW ENTRIES only (see `paper_execution.py`); it
        # must never trap an already-open position, so a position-reducing exit authorization
        # is never refused for the kill switch being engaged. See `docs/operations/kill-switch.md`.
        validity = min(int(command.validity_seconds), MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS)
        if validity <= 0:
            raise PositionExitRefusedError("an exit authorization needs a positive validity")
        timing = PaperTimeWindow(self._time)
        basis = timing.measure_broker_basis(lambda: self._broker.fetch_clock().timestamp)
        authorized_at = command.authorized_at
        if authorized_at > basis.host_at:
            raise PaperTimeUncertainError(
                "the authorization instant is later than this host's reading of the broker "
                "basis; nothing was authorized"
            )
        expires_at = authorized_at + timedelta(seconds=validity)
        if authorized_at < preview.liquidation_deadline:
            expires_at = min(expires_at, preview.liquidation_deadline)
        if expires_at <= authorized_at:
            raise PositionExitRefusedError(
                "the mandatory liquidation deadline leaves no time for an authorization"
            )
        authorization = self._authorizations.save(
            PositionExitAuthorization(
                authorization_id=command.authorization_id,
                entry_intent_governance_id=preview.entry_intent_governance_id,
                preview_id=preview.preview_id,
                preview_version=preview.preview_version,
                request_fingerprint=preview.request_fingerprint,
                preview_binding_fingerprint=preview.binding_fingerprint,
                account_reference=preview.account_reference,
                client_order_id=preview.request.client_order_id,
                symbol=preview.request.symbol,
                quantity=preview.request.quantity,
                authorized_by=command.authorized_by,
                authorized_at=authorized_at,
                expires_at=expires_at,
                basis_host_requested_at=basis.host_requested_at,
                basis_host_at=basis.host_at,
                basis_broker_earliest_at=basis.broker_earliest_at,
                basis_broker_latest_at=basis.broker_latest_at,
                consumed_at=None,
                consumed_by_attempt_id=None,
            )
        )
        self._events.append(
            PositionExitEvent(
                event_id=_event_id(authorization.authorization_id, "EXIT_AUTHORIZED"),
                entry_intent_governance_id=authorization.entry_intent_governance_id,
                attempt_id=None,
                event_type="EXIT_AUTHORIZED",
                occurred_at=authorized_at,
                detail=(
                    f"{authorization.authorized_by} confirmed exit preview {preview.preview_id}; "
                    f"expires {expires_at.isoformat()}"
                )[:500],
            )
        )
        return authorization


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SubmitAuthorizedPositionExitCommand:
    entry_intent_governance_id: str
    attempt_id: str
    at: datetime


@dataclass(frozen=True, slots=True)
class ExitSubmissionResult:
    attempt: PositionExitAttempt
    dispatched: bool
    http_status: int | None
    broker_status: str | None
    note: str


class SubmitAuthorizedPositionExitHandler:
    """Send the one authorized SELL-TO-CLOSE, once, and record whatever happened.

    THE QUOTE'S FRESHNESS IS REVALIDATED HERE TOO (MILESTONE-089). A quote that was fresh
    when the Owner reviewed the exit can go stale by the time they confirm it: this handler
    re-runs `quote_refusal` against the SAME stored `preview.quote_bid`/`quote_ask`/
    `quote_captured_at` the Owner was shown, but against a FRESHLY measured broker clock --
    never a newly fetched quote, and never the authorization's own expiry as a substitute.
    Growing too old between review and confirm refuses the submission; it does not fall back
    to a repriced or silently reauthorized exit.
    """

    __slots__ = (
        "_assess",
        "_previews",
        "_authorizations",
        "_attempts",
        "_acknowledgements",
        "_events",
        "_broker",
        "_configurations",
        "_kill_switch",
        "_time",
    )

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        entry_attempts: ExecutionAttemptRepository,
        previews: PositionExitPreviewRepository,
        authorizations: PositionExitAuthorizationRepository,
        attempts: PositionExitAttemptRepository,
        acknowledgements: PositionExitAcknowledgementRepository,
        events: PositionExitEventRepository,
        broker: ExitBrokerPort,
        configurations: OperatorTradingConfigurationRepository,
        kill_switch: ExecutionKillSwitchRepository,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._assess = AssessPositionExitHandler(
            intents=intents, entry_attempts=entry_attempts, exit_attempts=attempts, broker=broker
        )
        self._previews = previews
        self._authorizations = authorizations
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._broker = broker
        self._configurations = configurations
        self._kill_switch = kill_switch
        self._time = time_source or SystemPaperTimeSource()

    def handle(self, command: SubmitAuthorizedPositionExitCommand) -> ExitSubmissionResult:
        existing = self._attempts.active_for_entry(command.entry_intent_governance_id)
        if existing is not None:
            return ExitSubmissionResult(
                attempt=existing,
                dispatched=False,
                http_status=None,
                broker_status=existing.broker_status,
                note=(
                    "an exit for this position already exists; reconcile the existing attempt "
                    f"{existing.attempt_id} instead of sending again"
                ),
            )
        authorization = self._authorizations.latest_for_entry(command.entry_intent_governance_id)
        if authorization is None or authorization.is_consumed:
            raise PositionExitRefusedError(
                "no unused human exit authorization exists for this position; nothing may be sent"
            )
        preview = self._previews.get(authorization.preview_id)
        if preview is None:
            raise PositionExitRefusedError(
                "the exit authorization names a preview that does not exist; nothing may be sent"
            )
        binding = exit_authorization_binding_refusal(authorization=authorization, preview=preview)
        if binding is not None:
            raise PositionExitRefusedError(f"this exit is not authorized: {binding}")

        # RELEASE v1: the kill switch blocks NEW ENTRIES only. A position-reducing exit
        # (stop, target, mandatory liquidation, or an Owner's manual SELL_TO_CLOSE) is never
        # blocked by it -- the engaged state must never silently trap an open position. See
        # `docs/operations/kill-switch.md`.

        timing = PaperTimeWindow(self._time)
        # The broker clock, so the authorization can be judged on the broker's timeline.
        sent = timing.read_monotonic()
        clock = self._broker.fetch_clock()
        timing.observe_broker_clock(clock.timestamp, sent, timing.read_monotonic())

        # RELEASE v1 RECOVERY HARDENING: a position-reducing exit is still fail-closed outside
        # regular trading hours. `clock.is_open` is the SAME broker-reported regular-session
        # flag `_measure_broker_now`'s caller already paid for above -- no new broker call.
        # This blocks BOTH dispatch paths that reach this one handler alike: a manual Owner
        # confirm (`operator_console_exits.PositionExitConsole.confirm`) and the automatic
        # manager (`position_plan_manager.PositionPlanManager._attempt_exit`), including an
        # overdue mandatory-exit trigger claimed while the market was shut. It never widens
        # anything: every existing refusal/freshness/authorization check below still runs in
        # full once the market is open; this only adds one more gate, never removes one.
        if not clock.is_open:
            raise PositionExitRefusedError(
                POSITION_NEEDS_ATTENTION + " The market is not in a regular trading session; "
                "exits are not dispatched outside regular hours. Nothing was sent; this attempt "
                "will be retried the next time the plan is evaluated."
            )

        # THE POSITION, RE-VERIFIED NOW. Same entry, same quantity, same broker position, no
        # competing lot, no other exit: the digest must be the one the human confirmed.
        assessment = self._assess.handle(command.entry_intent_governance_id, at=timing.now())
        if not assessment.eligible:
            raise PositionExitRefusedError(
                POSITION_NEEDS_ATTENTION
                + " The position changed after it was reviewed: "
                + "; ".join(assessment.refusals)
                + ". Nothing was sent."
            )
        entry = assessment.entry_attempt
        assert entry is not None

        # THE QUOTE, RE-VERIFIED NOW (MILESTONE-089). The SAME evidence the Owner was shown
        # -- never a freshly fetched, differently priced quote -- judged against a broker
        # clock reading taken THIS instant. A quote that was fresh at review and has since
        # aged past the policy limit refuses the send; it is not silently repriced.
        policy = _configuration_policy(self._configurations, assessment.entry_intent)
        stale = quote_refusal(
            bid=preview.quote_bid,
            ask=preview.quote_ask,
            captured_at=preview.quote_captured_at,
            policy=policy,
            broker_now=timing.broker_now(),
        )
        if stale is not None:
            raise PositionExitRefusedError(
                POSITION_NEEDS_ATTENTION + " The quote priced this exit at review is no longer "
                "usable: " + stale + ". Nothing was sent; review the position again for a "
                "fresh quote."
            )

        account_reference = _account_reference_of(self._broker)
        fingerprint_now = exit_request_fingerprint(
            request=preview.request,
            entry_attempt_id=entry.attempt_id,
            position_digest=assessment.snapshot.digest,
            liquidation_deadline=preview.liquidation_deadline,
        )
        refusal = authorization.refusal_against(
            request_fingerprint_now=fingerprint_now,
            account_reference_now=account_reference,
            instant=timing.now(),
            broker_now=timing.broker_now(),
        )
        if refusal is not None:
            raise PositionExitRefusedError(
                f"this exit is not authorized: {refusal}. Nothing was sent; review the position "
                "again"
            )

        # CLAIM BEFORE THE NETWORK: the authorization is consumed and the one attempt exists
        # while nothing has been sent.
        claim = self._attempts.claim_dispatch(
            attempt_id=command.attempt_id,
            authorization=authorization,
            request_fingerprint_now=fingerprint_now,
            account_reference_now=account_reference,
            claimed_at=timing.now(),
            claim_clock=timing.now,
            broker_clock=timing.broker_now,
        )
        if not claim.won:
            return ExitSubmissionResult(
                attempt=claim.attempt,
                dispatched=False,
                http_status=None,
                broker_status=claim.attempt.broker_status,
                note="another worker had already claimed this exit; no request was sent",
            )
        attempt = self._attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PositionExitState.SUBMISSION_IN_PROGRESS,
            at=timing.last_safe_at,
        )
        request = preview.request

        def before_send() -> None:
            try:
                try:
                    lookup_status, existing_order, lookup_body = (
                        self._broker.fetch_order_by_client_order_id(request.client_order_id)
                    )
                except Exception as error:  # noqa: BLE001 - inconclusive, recorded below
                    raise BrokerIdentityUnresolvedError(
                        f"the identity lookup before the send failed ({type(error).__name__}); "
                        "nothing was sent"
                    ) from error
                if existing_order is not None:
                    raise BrokerIdentityExistsError(
                        "the broker already holds an order under this client_order_id; "
                        "nothing was sent",
                        http_status=lookup_status,
                        sanitized_body=lookup_body,
                        request_sent=False,
                    )
                if lookup_status != 404:
                    raise BrokerIdentityUnresolvedError(
                        "the broker could not confirm that this client_order_id is unused "
                        f"(HTTP {lookup_status}); nothing was sent",
                        http_status=lookup_status,
                        sanitized_body=lookup_body,
                    )
                # The send-capable boundary, DURABLY, before the last kill-switch read.
                self._record(
                    attempt,
                    EXIT_SEND_BOUNDARY_EVENT_TYPE,
                    exit_send_boundary_binding(
                        attempt_id=attempt.attempt_id,
                        authorization_id=attempt.authorization_id,
                        request_fingerprint=attempt.request_fingerprint,
                        account_reference=account_reference,
                        client_order_id=request.client_order_id,
                        identity_lookup_status=lookup_status,
                    ),
                    timing.last_safe_at,
                )
                # RELEASE v1: the kill switch does not gate the send boundary either -- see
                # the handler docstring and `docs/operations/kill-switch.md`.
                final = authorization.refusal_against(
                    request_fingerprint_now=fingerprint_now,
                    account_reference_now=account_reference,
                    instant=timing.now(),
                    broker_now=timing.broker_now(),
                )
                if final is not None:
                    raise PositionExitRefusedError(final)
            except (PositionExitRefusedError, PaperTimeUncertainError) as error:
                raise BrokerNotSentError(str(error)) from error

        return self._dispatch(attempt, request, before_send, timing)

    def _dispatch(
        self,
        attempt: PositionExitAttempt,
        request: PositionExitRequest,
        before_send: Callable[[], None],
        timing: PaperTimeWindow,
    ) -> ExitSubmissionResult:
        try:
            status, view, sanitized = self._broker.submit_close_order(
                request, before_send=before_send
            )
        except BrokerNotSentError as error:
            at = timing.last_safe_at
            final = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.REJECTED,
                at=at,
                failure_code="NOT_SENT",
                failure_detail=str(error)[:500],
            )
            self._record(attempt, "EXIT_DISPATCH_NOT_SENT", str(error), at)
            return ExitSubmissionResult(
                final,
                False,
                None,
                None,
                "the exit request never reached the broker; nothing was sent",
            )
        except BrokerIdentityExistsError as error:
            at = timing.last_safe_at
            if error.http_status is not None and error.sanitized_body is not None:
                self._acknowledge(
                    attempt.attempt_id,
                    kind="SUBMIT" if error.request_sent else "RECONCILE",
                    at=at,
                    http_status=error.http_status,
                    view=None,
                    sanitized=error.sanitized_body,
                )
            unknown = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code="IDENTITY_EXISTS_SENT"
                if error.request_sent
                else "IDENTITY_EXISTS_UNSENT",
                failure_detail=str(error)[:500],
            )
            self._record(
                attempt,
                "EXIT_CLIENT_ORDER_ID_COLLISION"
                if error.request_sent
                else "EXIT_IDENTITY_OBSERVED_BEFORE_SEND",
                str(error),
                at,
            )
            return ExitSubmissionResult(
                unknown,
                error.request_sent,
                error.http_status,
                None,
                "an order already exists under this exit identity; it was NOT adopted and nothing "
                "was sent again; an operator must resolve it",
            )
        except BrokerIdentityUnresolvedError as error:
            at = timing.last_safe_at
            unknown = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code="IDENTITY_UNRESOLVED_UNSENT",
                failure_detail=str(error)[:500],
            )
            self._record(attempt, "EXIT_IDENTITY_LOOKUP_INCONCLUSIVE", str(error), at)
            return ExitSubmissionResult(
                unknown,
                False,
                error.http_status,
                None,
                "nothing was sent: the broker could not confirm the exit identity is unused; "
                "the outcome is UNKNOWN until reconciliation asks again",
            )
        except BrokerAmbiguousDispatchError as error:
            at = timing.last_safe_at
            final = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code="AMBIGUOUS",
                failure_detail=str(error)[:500],
            )
            self._record(attempt, "EXIT_DISPATCH_OUTCOME_UNKNOWN", str(error), at)
            return ExitSubmissionResult(
                final,
                True,
                None,
                None,
                "the outcome is UNKNOWN: the exit request may have been delivered. Reconcile "
                "using the same client_order_id; do not send again",
            )
        except Exception as error:  # noqa: BLE001 - after before_send passed, the request may have left
            at = timing.last_safe_at
            final = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code="UNUSABLE_ANSWER",
                failure_detail=f"{type(error).__name__}: {error}"[:500],
            )
            self._record(attempt, "EXIT_DISPATCH_OUTCOME_UNKNOWN", str(error), at)
            return ExitSubmissionResult(
                final, True, None, None, "the outcome is UNKNOWN; reconcile, do not send again"
            )

        at = timing.last_safe_at
        self._acknowledge(
            attempt.attempt_id,
            kind="SUBMIT",
            at=at,
            http_status=status,
            view=view,
            sanitized=sanitized,
        )
        if view is None or status not in {200, 201}:
            if view is None and _is_identity_collision(status, sanitized):
                unknown = self._attempts.transition(
                    attempt_id=attempt.attempt_id,
                    target=PositionExitState.SUBMISSION_UNKNOWN,
                    at=at,
                    failure_code="IDENTITY_EXISTS_SENT",
                    failure_detail=sanitized[:500],
                )
                self._record(attempt, "EXIT_CLIENT_ORDER_ID_COLLISION", f"HTTP {status}", at)
                return ExitSubmissionResult(
                    unknown, True, status, None, "the broker reports an order under this identity"
                )
            if view is None and _is_definitive_refusal(status, sanitized):
                final = self._attempts.transition(
                    attempt_id=attempt.attempt_id,
                    target=PositionExitState.REJECTED,
                    at=at,
                    failure_code=f"HTTP_{status}",
                    failure_detail=sanitized[:500],
                )
                self._record(attempt, "EXIT_REFUSED_BY_BROKER", f"HTTP {status}", at)
                return ExitSubmissionResult(
                    final, True, status, None, f"the broker refused the exit with HTTP {status}"
                )
            uncertain = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code=f"UNCERTAIN_HTTP_{status}"[:32],
                failure_detail=sanitized[:500],
            )
            self._record(attempt, "EXIT_DISPATCH_OUTCOME_UNKNOWN", f"HTTP {status}", at)
            return ExitSubmissionResult(
                uncertain,
                True,
                status,
                None,
                "the outcome is UNKNOWN; reconcile, do not send again",
            )

        mismatches = exit_order_terms_mismatches(expected=request, actual=view)
        if mismatches:
            # The broker echoed an order that is NOT the authorized exit. It is not adopted.
            unknown = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code="TERMS_MISMATCH",
                failure_detail=f"broker echoed different terms: {', '.join(mismatches)}"[:500],
            )
            self._record(
                attempt,
                "EXIT_IDENTITY_COLLISION_MISMATCH",
                f"the broker's answer differs from the authorized exit on: {', '.join(mismatches)}",
                at,
            )
            return ExitSubmissionResult(
                unknown,
                True,
                status,
                view.status,
                "the broker described an order with different terms; it was NOT adopted and an "
                "operator must resolve it",
            )
        submitted = self._attempts.transition(
            attempt_id=attempt.attempt_id,
            target=PositionExitState.SUBMITTED,
            at=at,
            broker_order_id=view.broker_order_id,
            broker_status=view.status,
            filled_quantity=view.filled_quantity,
            filled_avg_price=view.filled_avg_price,
        )
        final = _apply_status(self._attempts, submitted, view, at)
        self._record(
            attempt,
            "EXIT_SUBMITTED",
            f"broker_status={view.status} broker_order_id={view.broker_order_id}",
            at,
        )
        return ExitSubmissionResult(final, True, status, view.status, "the exit was sent")

    def _acknowledge(
        self,
        attempt_id: str,
        *,
        kind: str,
        at: datetime,
        http_status: int,
        view: BrokerOrderView | None,
        sanitized: str,
    ) -> None:
        _acknowledge(self._acknowledgements, attempt_id, kind, at, http_status, view, sanitized)

    def _record(
        self, attempt: PositionExitAttempt, event_type: str, detail: str, at: datetime
    ) -> None:
        self._events.append(
            PositionExitEvent(
                event_id=_event_id(attempt.attempt_id, event_type),
                entry_intent_governance_id=attempt.entry_intent_governance_id,
                attempt_id=attempt.attempt_id,
                event_type=event_type,
                occurred_at=at,
                detail=detail[:500],
            )
        )


def _acknowledge(
    repository: PositionExitAcknowledgementRepository,
    attempt_id: str,
    kind: str,
    at: datetime,
    http_status: int,
    view: BrokerOrderView | None,
    sanitized: str,
) -> int:
    sequence = repository.next_sequence(attempt_id)
    repository.append(
        BrokerAcknowledgement(
            acknowledgement_id=f"XACK-{attempt_id}-{sequence}"[:64],
            attempt_id=attempt_id,
            sequence=sequence,
            kind=kind,
            observed_at=at,
            http_status=http_status,
            broker_order_id=None if view is None else view.broker_order_id,
            broker_status=None if view is None else view.status,
            client_order_id_echo=None if view is None else view.client_order_id,
            payload_digest=_digest(sanitized),
            sanitized_payload=sanitized[:8192],
        )
    )
    return sequence


def _apply_status(
    attempts: PositionExitAttemptRepository,
    attempt: PositionExitAttempt,
    view: BrokerOrderView,
    at: datetime,
) -> PositionExitAttempt:
    target = _BROKER_STATUS_TO_STATE.get(view.status)
    return attempts.transition(
        attempt_id=attempt.attempt_id,
        target=attempt.state if target is None or target is attempt.state else target,
        at=at,
        broker_order_id=view.broker_order_id,
        broker_status=view.status,
        filled_quantity=view.filled_quantity,
        filled_avg_price=view.filled_avg_price,
    )


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReconcilePositionExitCommand:
    attempt_id: str
    at: datetime


class ReconcilePositionExitHandler:
    """Ask the broker about the SAME exit identity, record the answer, verify the position."""

    __slots__ = (
        "_attempts",
        "_acknowledgements",
        "_events",
        "_rounds",
        "_authorizations",
        "_previews",
        "_broker",
        "_time",
    )

    def __init__(
        self,
        *,
        attempts: PositionExitAttemptRepository,
        acknowledgements: PositionExitAcknowledgementRepository,
        events: PositionExitEventRepository,
        rounds: PositionExitRoundRepository,
        authorizations: PositionExitAuthorizationRepository,
        previews: PositionExitPreviewRepository,
        broker: ExitBrokerPort,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._rounds = rounds
        self._authorizations = authorizations
        self._previews = previews
        self._broker = broker
        self._time = time_source or SystemPaperTimeSource()

    def handle(self, command: ReconcilePositionExitCommand) -> PositionExitAttempt:
        attempt = self._attempts.get(command.attempt_id)
        if attempt is None:
            raise NotFoundError(f"no exit attempt {command.attempt_id!r} exists")
        if attempt.is_terminal:
            return self._verify_closed(attempt, command.at)
        if attempt.state is PositionExitState.SUBMISSION_IN_PROGRESS:
            started = attempt.submitted_at or attempt.claimed_at
            if (command.at - started).total_seconds() < MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS:
                return attempt
        authorization = self._authorizations.get(attempt.authorization_id)
        if authorization is None:
            self._event(
                attempt, "EXIT_RECONCILE_ROUND_NOT_BEGUN", "authorization missing", command.at
            )
            return attempt
        round_ = self._rounds.begin(
            attempt=attempt,
            account_reference=authorization.account_reference,
            started_at=command.at,
        )
        window = PaperTimeWindow(self._time)
        try:
            sent = window.read_monotonic()
            clock = self._broker.fetch_clock()
            sample = window.observe_broker_clock(clock.timestamp, sent, window.read_monotonic())
            status, view, sanitized = self._broker.fetch_order_by_client_order_id(
                attempt.client_order_id
            )
        except Exception as error:
            self._rounds.complete(
                round_.round_id,
                outcome=ReconciliationRoundOutcome.FAILED,
                completed_at=command.at,
                detail=f"the round's network work raised {type(error).__name__}",
            )
            self._event(
                attempt,
                "EXIT_RECONCILE_LOOKUP_FAILED",
                f"the reconciliation lookup raised {type(error).__name__}",
                command.at,
                suffix=round_.round_id,
            )
            raise
        sequence = _acknowledge(
            self._acknowledgements,
            attempt.attempt_id,
            "RECONCILE",
            command.at,
            status,
            view,
            sanitized,
        )
        outcome = (
            ReconciliationRoundOutcome.FOUND
            if view is not None
            else ReconciliationRoundOutcome.NOT_FOUND
            if status == 404
            else ReconciliationRoundOutcome.UNUSABLE
        )
        self._rounds.complete(
            round_.round_id,
            outcome=outcome,
            completed_at=command.at,
            acknowledgement_sequence=sequence,
            broker_earliest_at=sample.earliest,
            broker_latest_at=sample.latest,
        )
        if view is None:
            return self._absence(attempt, status, command.at, sequence)

        preview = self._previews.get(authorization.preview_id)
        held = f"broker_order_id={view.broker_order_id} status={view.status}"
        mismatches: tuple[str, ...] = ("authorization",)
        if preview is not None:
            mismatches = exit_order_terms_mismatches(
                expected=preview.request, actual=view, bound_broker_order_id=attempt.broker_order_id
            )
        if mismatches:
            self._event(
                attempt,
                "EXIT_IDENTITY_COLLISION_MISMATCH",
                f"the broker's order under this identity differs on: {', '.join(mismatches)} "
                f"({held})",
                command.at,
                suffix=str(sequence),
            )
            return attempt
        if attempt.state in {
            PositionExitState.SUBMISSION_IN_PROGRESS,
            PositionExitState.SUBMISSION_UNKNOWN,
        }:
            if not exit_attempt_may_have_transmitted(
                attempt, self._events.for_entry(attempt.entry_intent_governance_id)
            ):
                self._event(
                    attempt,
                    "EXIT_IDENTITY_OBSERVED_NOT_ATTRIBUTED",
                    f"an order with the authorized terms exists under this identity ({held}); "
                    "this attempt did not transmit a request that could have created it; an "
                    "operator must resolve it",
                    command.at,
                    suffix=str(sequence),
                )
                return attempt
            attempt = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PositionExitState.SUBMITTED,
                at=command.at,
                broker_order_id=view.broker_order_id,
                broker_status=view.status,
                filled_quantity=view.filled_quantity,
                filled_avg_price=view.filled_avg_price,
            )
        target = _BROKER_STATUS_TO_STATE.get(view.status)
        if target is not None and target is not attempt.state:
            self._event(
                attempt,
                "EXIT_RECONCILED",
                f"{attempt.state.value}->{target.value} broker_status={view.status}",
                command.at,
                suffix=str(sequence),
            )
        updated = _apply_status(self._attempts, attempt, view, command.at)
        return self._verify_closed(updated, command.at)

    def _verify_closed(self, attempt: PositionExitAttempt, at: datetime) -> PositionExitAttempt:
        """After a full fill: the position is closed only when the broker holds zero."""
        if not attempt.fully_filled or attempt.closed_position_verified_at is not None:
            return attempt
        try:
            position = self._broker.fetch_position(attempt.symbol)
        except Exception as error:  # noqa: BLE001 - recorded; verification simply has not happened
            self._event(
                attempt,
                "EXIT_POSITION_VERIFICATION_FAILED",
                f"the position lookup raised {type(error).__name__}",
                at,
                suffix=at.isoformat(),
            )
            return attempt
        quantity = 0 if position is None else int(position.quantity)
        if quantity == 0:
            verified = self._attempts.mark_position_closed(
                attempt_id=attempt.attempt_id, verified_at=at
            )
            self._event(
                verified,
                POSITION_CLOSED_VERIFIED_EVENT_TYPE,
                f"the broker position in {attempt.symbol} was verified at zero after the exit "
                f"filled {attempt.filled_quantity} of {attempt.quantity}",
                at,
            )
            return verified
        self._event(
            attempt,
            POSITION_NOT_ZERO_AFTER_FILL_EVENT_TYPE,
            f"the exit filled {attempt.filled_quantity} but the broker still holds {quantity} "
            f"{attempt.symbol}; the position is NOT closed and needs operator attention",
            at,
            suffix=at.isoformat(),
        )
        return attempt

    def _absence(
        self, attempt: PositionExitAttempt, status: int, at: datetime, sequence: int
    ) -> PositionExitAttempt:
        if status != 404:
            self._event(
                attempt,
                "EXIT_RECONCILE_UNUSABLE_ANSWER",
                f"HTTP {status}",
                at,
                suffix=str(sequence),
            )
            return attempt
        acknowledgements = self._acknowledgements.for_attempt(attempt.attempt_id)
        events = self._events.for_entry(attempt.entry_intent_governance_id)
        if attempt.state in BOUND_EXIT_ORDER_STATES:
            self._event(
                attempt,
                "EXIT_RECONCILE_NOT_FOUND_KNOWN_ORDER",
                f"the broker reported no order under this identity but {attempt.state.value} "
                f"with broker_order_id={attempt.broker_order_id} is on record; absence revokes "
                "nothing; an operator must establish what the broker holds",
                at,
                suffix=str(sequence),
            )
            return attempt
        if attempt.state is PositionExitState.SUBMISSION_IN_PROGRESS:
            self._event(
                attempt,
                "EXIT_RECONCILE_NOT_FOUND_DISPATCH_MAY_BE_LIVE",
                "the attempt is still SUBMISSION_IN_PROGRESS; absence proves nothing",
                at,
                suffix=str(sequence),
            )
            return attempt
        rounds = self._rounds.for_attempt(attempt.attempt_id)
        evaluation = exit_absence_evaluation(
            state=attempt.state,
            broker_order_id=attempt.broker_order_id,
            acknowledgements=acknowledgements,
            events=events,
            rounds=rounds,
        )
        if not evaluation.resolvable:
            self._event(
                attempt,
                "EXIT_RECONCILE_NOT_FOUND_INSUFFICIENT",
                f"rounds={evaluation.rounds_version[0]} "
                f"consecutive_not_found={evaluation.consecutive_not_found} "
                f"waiting_lower_bound={evaluation.waiting_lower_bound_seconds}; "
                f"{evaluation.reason}; state unchanged",
                at,
                suffix=str(sequence),
            )
            return attempt
        resolved = self._rounds.resolve_not_found(
            attempt_id=attempt.attempt_id,
            expected_version=evaluation.rounds_version,
            at=at,
            failure_code="NOT_FOUND_AT_BROKER",
            failure_detail=(
                "the broker reported no such exit client_order_id across "
                f"{evaluation.consecutive_not_found} consecutive completed rounds; waiting lower "
                f"bound {int(evaluation.waiting_lower_bound_seconds or 0)}s on the broker clock"
            ),
        )
        if resolved is None:
            self._event(
                attempt,
                "EXIT_RECONCILE_RESOLUTION_REVALIDATION_FAILED",
                "the absence decision did not hold on fresh rows; state unchanged",
                at,
                suffix=str(sequence),
            )
            return self._attempts.get(attempt.attempt_id) or attempt
        self._event(
            resolved,
            "EXIT_RECONCILE_RESOLVED_NOT_FOUND",
            "bounded policy satisfied and re-validated atomically; the exit was never received "
            "and the position remains open",
            at,
        )
        return resolved

    def _event(
        self,
        attempt: PositionExitAttempt,
        event_type: str,
        detail: str,
        at: datetime,
        *,
        suffix: str = "",
    ) -> None:
        self._events.append(
            PositionExitEvent(
                event_id=_event_id(attempt.attempt_id, event_type, suffix),
                entry_intent_governance_id=attempt.entry_intent_governance_id,
                attempt_id=attempt.attempt_id,
                event_type=event_type,
                occurred_at=at,
                detail=detail[:500],
            )
        )


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CancelPositionExitCommand:
    attempt_id: str
    at: datetime


class CancelPositionExitHandler:
    """Ask the broker to cancel the exit order. A request is not a cancellation."""

    __slots__ = ("_attempts", "_acknowledgements", "_events", "_broker")

    def __init__(
        self,
        *,
        attempts: PositionExitAttemptRepository,
        acknowledgements: PositionExitAcknowledgementRepository,
        events: PositionExitEventRepository,
        broker: ExitBrokerPort,
    ) -> None:
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._broker = broker

    def handle(self, command: CancelPositionExitCommand) -> PositionExitAttempt:
        attempt = self._attempts.get(command.attempt_id)
        if attempt is None:
            raise NotFoundError(f"no exit attempt {command.attempt_id!r} exists")
        if attempt.is_terminal:
            raise PositionExitRefusedError(f"the exit is already {attempt.state.value}")
        if attempt.broker_order_id is None or attempt.state not in BOUND_EXIT_ORDER_STATES:
            raise PositionExitRefusedError(
                "the exit has no acknowledged broker order to cancel; reconcile it first"
            )
        status, body = self._broker.cancel_order(attempt.broker_order_id)
        _acknowledge(
            self._acknowledgements, attempt.attempt_id, "CANCEL", command.at, status, None, body
        )
        if status not in {200, 202, 204}:
            self._events.append(
                PositionExitEvent(
                    event_id=_event_id(attempt.attempt_id, "EXIT_CANCEL_REFUSED", str(status)),
                    entry_intent_governance_id=attempt.entry_intent_governance_id,
                    attempt_id=attempt.attempt_id,
                    event_type="EXIT_CANCEL_REFUSED",
                    occurred_at=command.at,
                    detail=f"HTTP {status}"[:500],
                )
            )
            return attempt
        moved = self._attempts.transition(
            attempt_id=attempt.attempt_id, target=PositionExitState.CANCEL_REQUESTED, at=command.at
        )
        self._events.append(
            PositionExitEvent(
                event_id=_event_id(attempt.attempt_id, "EXIT_CANCEL_REQUESTED"),
                entry_intent_governance_id=attempt.entry_intent_governance_id,
                attempt_id=attempt.attempt_id,
                event_type="EXIT_CANCEL_REQUESTED",
                occurred_at=command.at,
                detail=f"cancel requested for broker_order_id={attempt.broker_order_id}"[:500],
            )
        )
        return moved


def broker_now_for(timing: PaperTimeWindow) -> BoundedInstant:
    """Exposed for tests that want the bounded broker instant a window currently holds."""
    return timing.broker_now()
