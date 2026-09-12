"""MILESTONE-085 commands and queries for paper execution.

EVERY HANDLER IS ONE STEP. There is no handler that previews, authorizes and
submits in one call, because a human decision sits between the first and the
second and a convenience method spanning it would be an authorization nobody
gave. `SubmitAuthorizedPaperOrderHandler` will not create an authorization, and
`AuthorizePaperSubmissionHandler` will not send anything.

THE EVIDENCE IS REFRESHED AT DISPATCH, NOT REUSED FROM THE PREVIEW. Submission
re-reads the account, the asset, the clock, the quote, the existing position and
the kill switch, then RECOMPUTES the request fingerprint and requires the
authorization to still match it. If anything material changed after the human
looked, the fingerprint differs and the dispatch is refused. Reusing the
preview's own numbers would make the freshness checks decorative.

THE ORDER OF THE LAST THREE STEPS IS THE DESIGN. Check the kill switch, claim the
dispatch in the database, and only then touch the network. Claiming after the
network call would mean an order could exist at the broker with nothing
persisted to prove it; checking the kill switch before the refresh would leave a
window where it was engaged and the dispatch proceeded anyway.

AN UNMAPPED BROKER STATUS IS NOT A KNOWN ONE. `_BROKER_STATUS_TO_STATE` is
closed. A status Alpaca returns that is not in it does NOT become the nearest
guess: the acknowledgement is recorded, the raw status is stored, and the state
does not move. An operator then sees a real status they must decide about, which
is better than the product silently deciding that `calculated` means `filled`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from empirical_platform.decision_candidate.paper_execution import (
    MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS,
    MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS,
    PAPER_ENDPOINT_HOST,
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionEvent,
    PaperExecutionState,
    SubmissionPreview,
    authorize_submission,
    build_submission_preview,
    request_fingerprint,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    BrokerAcknowledgementRepository,
    BrokerOrderView,
    ExecutionAttemptRepository,
    ExecutionAuthorizationRepository,
    ExecutionKillSwitchRepository,
    PaperAccountSnapshotRepository,
    PaperBrokerPort,
    PaperExecutionEventRepository,
    PaperMarketDataPort,
    SubmissionPreviewRepository,
)
from empirical_platform.decision_candidate.product_repositories import (
    ApprovedOrderIntentRepository,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
    BrokerResponseInvalidError,
)
from empirical_platform.shared.brokerage.paper_time import (
    PaperTimeSource,
    PaperTimeUncertainError,
    PaperTimeWindow,
    SystemPaperTimeSource,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError

#: Re-exported for `entrypoints`, which may import `usecases` but not
#: `decision_candidate` (see the MILESTONE-083 REV-005 note in
#: `tools/check_architecture.py`). The types travel through here so the
#: architecture allowlist stays exactly as it was.
__all__ = [
    "AuthorizePaperSubmissionCommand",
    "AuthorizePaperSubmissionHandler",
    "CancelPaperOrderCommand",
    "CancelPaperOrderHandler",
    "InspectPaperAccountCommand",
    "InspectPaperAccountHandler",
    "ListPaperExecutionsHandler",
    "ListPaperExecutionsQuery",
    "ExecutionAttempt",
    "ExecutionAuthorization",
    "PaperAccountSnapshot",
    "PaperExecutionState",
    "SubmissionPreview",
    "PaperEvidence",
    "PaperExecutionRefusedError",
    "PaperExecutionStatus",
    "PaperExecutionStatusHandler",
    "PaperExecutionStatusQuery",
    "PaperSubmissionResult",
    "PreviewPaperSubmissionCommand",
    "PreviewPaperSubmissionHandler",
    "ReconcilePaperOrderCommand",
    "ReconcilePaperOrderHandler",
    "SetExecutionKillSwitchCommand",
    "SetExecutionKillSwitchHandler",
    "ShowPaperExecutionHandler",
    "ShowPaperExecutionQuery",
    "SubmitAuthorizedPaperOrderCommand",
    "SubmitAuthorizedPaperOrderHandler",
    "VerifyPaperEnvironmentHandler",
    "VerifyPaperEnvironmentQuery",
    "VerifyPaperEnvironmentResult",
]


class PaperExecutionRefusedError(ValueError):
    """An operator request this product will not perform, with the reason.

    Subclasses `ValueError` so that `entrypoints._operator_cli.operator_command`
    renders it as a refusal rather than a traceback -- the same shape M084 uses,
    reused rather than reinvented.
    """


#: Alpaca order status -> M085 state. CLOSED on purpose: see the module
#: docstring. Statuses absent here are real Alpaca statuses that this milestone
#: deliberately does not map, because none of them has an obviously correct
#: destination and guessing would be worse than reporting.
_BROKER_STATUS_TO_STATE = MappingProxyType(
    {
        "new": PaperExecutionState.PAPER_ACCEPTED,
        "accepted": PaperExecutionState.PAPER_ACCEPTED,
        "pending_new": PaperExecutionState.PAPER_ACCEPTED,
        "accepted_for_bidding": PaperExecutionState.PAPER_ACCEPTED,
        "held": PaperExecutionState.PAPER_ACCEPTED,
        "partially_filled": PaperExecutionState.PARTIALLY_FILLED,
        "filled": PaperExecutionState.FILLED,
        "canceled": PaperExecutionState.CANCELED,
        "expired": PaperExecutionState.EXPIRED,
        "rejected": PaperExecutionState.REJECTED,
        "suspended": PaperExecutionState.REJECTED,
        "pending_cancel": PaperExecutionState.CANCEL_REQUESTED,
    }
)


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _account_reference(account_id: str) -> str:
    """A stable, non-reversible reference to the broker's account identifier.

    The product must prove that an authorization and a dispatch concern the same
    account. It does not need to store a real account number to do that, and
    storing one would put a customer identifier into every audit row.
    """
    import hashlib

    return "ref:" + hashlib.sha256(f"m085/{account_id}".encode()).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class PaperEvidence:
    """Everything read from the broker in one gathering pass."""

    account: PaperAccountSnapshot
    market_is_open: bool
    market_next_open: datetime | None
    market_next_close: datetime | None
    quote_bid: Decimal | None
    quote_ask: Decimal | None
    quote_captured_at: datetime | None
    quote_source: str
    asset_tradable: bool
    asset_status: str
    asset_class: str
    asset_exchange: str
    asset_fractionable: bool
    existing_position_quantity: int
    kill_switch_engaged: bool


def _read_account_snapshot(
    *, broker: PaperBrokerPort, snapshot_id: str, captured_at: datetime
) -> PaperAccountSnapshot:
    """Read the account and reduce it to what this product stores.

    Only the fields below are kept. The rest of Alpaca's account payload -- and it
    is large -- is deliberately dropped rather than persisted, because none of it
    is needed to decide whether this order may be sent, and unnecessary personal
    or financial detail should not be sitting in an audit table.
    """
    status, payload = broker.fetch_account()
    if status != 200:
        raise PaperExecutionRefusedError(f"the paper account could not be read (HTTP {status})")

    def text(field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise BrokerResponseInvalidError(f"the account field {field!r} is missing or empty")
        return value

    def flag(field: str) -> bool:
        value = payload.get(field)
        if not isinstance(value, bool):
            raise BrokerResponseInvalidError(f"the account field {field!r} is not a boolean")
        return value

    def money(field: str) -> Decimal:
        value = payload.get(field)
        if not isinstance(value, str):
            raise BrokerResponseInvalidError(f"the account field {field!r} is not a decimal string")
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise BrokerResponseInvalidError(
                f"the account field {field!r} is not a valid decimal"
            ) from error

    return PaperAccountSnapshot(
        snapshot_id=snapshot_id,
        environment=PaperEnvironment.PAPER,
        endpoint_host=broker.endpoint_host,
        account_reference=_account_reference(text("id")),
        account_status=text("status"),
        currency=text("currency"),
        buying_power=money("buying_power"),
        cash=money("cash"),
        equity=money("equity"),
        multiplier=text("multiplier"),
        shorting_enabled=flag("shorting_enabled"),
        trading_blocked=flag("trading_blocked"),
        transfers_blocked=flag("transfers_blocked"),
        account_blocked=flag("account_blocked"),
        trade_suspended_by_user=flag("trade_suspended_by_user"),
        captured_at=captured_at,
    )


def _gather(
    *,
    broker: PaperBrokerPort,
    market_data: PaperMarketDataPort,
    kill_switch: ExecutionKillSwitchRepository,
    symbol: str,
    snapshot_id: str,
    at: datetime,
    timing: PaperTimeWindow,
) -> PaperEvidence:
    """One pass over every external fact a dispatch decision depends on.

    Shared by preview and submission so that the two cannot disagree about what
    "the evidence" means. The kill switch is read LAST, closest to the decision.
    """
    account = _read_account_snapshot(broker=broker, snapshot_id=snapshot_id, captured_at=at)
    account = replace(account, captured_at=timing.now())
    clock_requested_at = timing.now()
    clock = broker.fetch_clock()
    timing.verify_broker(clock.timestamp, clock_requested_at)
    asset = broker.fetch_asset(symbol)
    position = broker.fetch_position(symbol)
    quote = market_data.fetch_quote(symbol)
    return PaperEvidence(
        account=account,
        market_is_open=clock.is_open,
        market_next_open=clock.next_open,
        market_next_close=clock.next_close,
        quote_bid=_decimal_or_none(None if quote is None else quote.bid),
        quote_ask=_decimal_or_none(None if quote is None else quote.ask),
        quote_captured_at=None if quote is None else quote.captured_at,
        quote_source="absent" if quote is None else quote.source,
        asset_tradable=asset.tradable,
        asset_status=asset.status,
        asset_class=asset.asset_class,
        asset_exchange=asset.exchange,
        asset_fractionable=asset.fractionable,
        existing_position_quantity=0 if position is None else position.quantity,
        kill_switch_engaged=kill_switch.is_engaged(),
    )


# ---------------------------------------------------------------------------
# Verify the environment
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifyPaperEnvironmentQuery:
    pass


@dataclass(frozen=True, slots=True)
class VerifyPaperEnvironmentResult:
    endpoint_host: str
    is_the_pinned_paper_host: bool
    account_reachable: bool
    account_status: str
    account_reference: str
    market_data_host: str


class VerifyPaperEnvironmentHandler:
    """Read-only: is this really the paper environment, and does it answer?"""

    __slots__ = ("_broker", "_market_data")

    def __init__(self, *, broker: PaperBrokerPort, market_data: PaperMarketDataPort) -> None:
        self._broker = broker
        self._market_data = market_data

    def handle(self, query: VerifyPaperEnvironmentQuery) -> VerifyPaperEnvironmentResult:
        del query
        status, payload = self._broker.fetch_account()
        account_id = payload.get("id")
        account_status = payload.get("status")
        return VerifyPaperEnvironmentResult(
            endpoint_host=self._broker.endpoint_host,
            is_the_pinned_paper_host=self._broker.endpoint_host == PAPER_ENDPOINT_HOST,
            account_reachable=status == 200,
            account_status=account_status if isinstance(account_status, str) else "unknown",
            account_reference=(
                _account_reference(account_id) if isinstance(account_id, str) else "unknown"
            ),
            market_data_host=self._market_data.endpoint_host,
        )


# ---------------------------------------------------------------------------
# Inspect and store an account snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InspectPaperAccountCommand:
    snapshot_id: str
    captured_at: datetime


class InspectPaperAccountHandler:
    __slots__ = ("_broker", "_snapshots")

    def __init__(
        self, *, broker: PaperBrokerPort, snapshots: PaperAccountSnapshotRepository
    ) -> None:
        self._broker = broker
        self._snapshots = snapshots

    def handle(self, command: InspectPaperAccountCommand) -> PaperAccountSnapshot:
        snapshot = _read_account_snapshot(
            broker=self._broker,
            snapshot_id=command.snapshot_id,
            captured_at=command.captured_at,
        )
        return self._snapshots.save(snapshot)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreviewPaperSubmissionCommand:
    intent_governance_id: str
    preview_id: str
    account_snapshot_id: str
    approved_watchlist: frozenset[str]
    maximum_notional: Decimal
    quote_maximum_age_seconds: int
    created_at: datetime


class PreviewPaperSubmissionHandler:
    """Freeze exactly what a human will be shown, refusals included."""

    __slots__ = (
        "_intents",
        "_snapshots",
        "_previews",
        "_events",
        "_broker",
        "_market_data",
        "_kill_switch",
        "_time_source",
    )

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        snapshots: PaperAccountSnapshotRepository,
        previews: SubmissionPreviewRepository,
        events: PaperExecutionEventRepository,
        broker: PaperBrokerPort,
        market_data: PaperMarketDataPort,
        kill_switch: ExecutionKillSwitchRepository,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._intents = intents
        self._snapshots = snapshots
        self._previews = previews
        self._events = events
        self._broker = broker
        self._market_data = market_data
        self._kill_switch = kill_switch
        self._time_source = time_source or SystemPaperTimeSource()

    def handle(self, command: PreviewPaperSubmissionCommand) -> SubmissionPreview:
        intent = self._intents.get(command.intent_governance_id)
        if intent is None:
            raise NotFoundError(f"no approved order intent {command.intent_governance_id!r} exists")

        timing = PaperTimeWindow(self._time_source)
        evidence = _gather(
            broker=self._broker,
            market_data=self._market_data,
            kill_switch=self._kill_switch,
            symbol=intent.symbol,
            snapshot_id=command.account_snapshot_id,
            at=command.created_at,
            timing=timing,
        )
        self._snapshots.save(evidence.account)

        version = self._previews.next_version_for_intent(intent.intent_governance_id)
        evaluated_at = timing.now()
        preview = build_submission_preview(
            preview_id=command.preview_id,
            intent=intent,
            account=evidence.account,
            preview_version=version,
            market_is_open=evidence.market_is_open,
            market_next_open=evidence.market_next_open,
            market_next_close=evidence.market_next_close,
            quote_bid=evidence.quote_bid,
            quote_ask=evidence.quote_ask,
            quote_captured_at=evidence.quote_captured_at,
            quote_source=evidence.quote_source,
            asset_tradable=evidence.asset_tradable,
            asset_status=evidence.asset_status,
            asset_class=evidence.asset_class,
            asset_exchange=evidence.asset_exchange,
            asset_fractionable=evidence.asset_fractionable,
            approved_watchlist=command.approved_watchlist,
            maximum_notional=command.maximum_notional,
            quote_maximum_age_seconds=command.quote_maximum_age_seconds,
            existing_position_quantity=evidence.existing_position_quantity,
            execution_kill_switch_engaged=evidence.kill_switch_engaged,
            created_at=evaluated_at,
        )
        stored = self._previews.save(preview)
        self._events.append(
            PaperExecutionEvent(
                event_id=f"EVT-{stored.preview_id}-PREVIEW",
                intent_governance_id=stored.intent_governance_id,
                attempt_id=None,
                event_type="PREVIEW_CREATED",
                occurred_at=evaluated_at,
                detail=(
                    f"v{stored.preview_version} authorizable={stored.is_authorizable} "
                    f"refusals={len(stored.refusals)}"
                )[:500],
            )
        )
        return stored


# ---------------------------------------------------------------------------
# Authorize
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthorizePaperSubmissionCommand:
    authorization_id: str
    preview_id: str
    #: The fingerprint the OPERATOR read off the preview and typed back. Required
    #: so that authorizing is an act about one exact order rather than about
    #: whatever the latest preview happens to be.
    expected_request_fingerprint: str
    authorized_by: str
    authorized_at: datetime
    validity_seconds: int


class AuthorizePaperSubmissionHandler:
    """One human act becomes one narrow, expiring, single-use permission."""

    __slots__ = ("_previews", "_authorizations", "_events")

    def __init__(
        self,
        *,
        previews: SubmissionPreviewRepository,
        authorizations: ExecutionAuthorizationRepository,
        events: PaperExecutionEventRepository,
    ) -> None:
        self._previews = previews
        self._authorizations = authorizations
        self._events = events

    def handle(self, command: AuthorizePaperSubmissionCommand) -> ExecutionAuthorization:
        preview = self._previews.get(command.preview_id)
        if preview is None:
            raise NotFoundError(f"no submission preview {command.preview_id!r} exists")
        if preview.request_fingerprint != command.expected_request_fingerprint:
            # The operator is authorizing something other than what they read.
            raise PaperExecutionRefusedError(
                "the fingerprint given does not match this preview's request fingerprint; "
                "re-read the preview and authorize the order it actually describes"
            )
        if not preview.is_authorizable:
            raise PaperExecutionRefusedError(
                "this preview cannot be authorized: " + "; ".join(preview.refusals)
            )

        authorization = authorize_submission(
            authorization_id=command.authorization_id,
            preview=preview,
            authorized_by=command.authorized_by,
            authorized_at=command.authorized_at,
            validity_seconds=command.validity_seconds,
        )
        stored = self._authorizations.save(authorization)
        self._events.append(
            PaperExecutionEvent(
                event_id=f"EVT-{stored.authorization_id}-AUTH",
                intent_governance_id=stored.intent_governance_id,
                attempt_id=None,
                event_type="AUTHORIZATION_GRANTED",
                occurred_at=command.authorized_at,
                detail=f"by={stored.authorized_by} expires_at={stored.expires_at.isoformat()}"[
                    :500
                ],
            )
        )
        return stored


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SubmitAuthorizedPaperOrderCommand:
    intent_governance_id: str
    attempt_id: str
    account_snapshot_id: str
    approved_watchlist: frozenset[str]
    maximum_notional: Decimal
    quote_maximum_age_seconds: int
    at: datetime


@dataclass(frozen=True, slots=True)
class PaperSubmissionResult:
    attempt: ExecutionAttempt
    #: False when this call found a dispatch already claimed and made NO network
    #: request. The persisted winner is returned in `attempt`.
    dispatched: bool
    http_status: int | None
    broker_status: str | None
    note: str


class SubmitAuthorizedPaperOrderHandler:
    """Send the one authorized order, once, and record whatever happened."""

    __slots__ = (
        "_intents",
        "_previews",
        "_authorizations",
        "_attempts",
        "_acknowledgements",
        "_events",
        "_snapshots",
        "_broker",
        "_market_data",
        "_kill_switch",
        "_time_source",
    )

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        previews: SubmissionPreviewRepository,
        authorizations: ExecutionAuthorizationRepository,
        attempts: ExecutionAttemptRepository,
        acknowledgements: BrokerAcknowledgementRepository,
        events: PaperExecutionEventRepository,
        snapshots: PaperAccountSnapshotRepository,
        broker: PaperBrokerPort,
        market_data: PaperMarketDataPort,
        kill_switch: ExecutionKillSwitchRepository,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._intents = intents
        self._previews = previews
        self._authorizations = authorizations
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._snapshots = snapshots
        self._broker = broker
        self._market_data = market_data
        self._kill_switch = kill_switch
        self._time_source = time_source or SystemPaperTimeSource()

    def handle(self, command: SubmitAuthorizedPaperOrderCommand) -> PaperSubmissionResult:
        intent = self._intents.get(command.intent_governance_id)
        if intent is None:
            raise NotFoundError(f"no approved order intent {command.intent_governance_id!r} exists")

        existing = self._attempts.for_intent(command.intent_governance_id)
        if existing is not None:
            # A dispatch already happened. No network request, no second order.
            return PaperSubmissionResult(
                attempt=existing,
                dispatched=False,
                http_status=None,
                broker_status=existing.broker_status,
                note=(
                    "this intent has already been dispatched; reconcile the existing "
                    f"attempt {existing.attempt_id} instead of sending again"
                ),
            )

        authorization = self._authorizations.latest_for_intent(command.intent_governance_id)
        if authorization is None:
            raise PaperExecutionRefusedError(
                "no human authorization exists for this intent; nothing may be dispatched"
            )

        # THE KILL SWITCH IS READ FIRST, and the evidence refreshed after it, so
        # that a switch engaged during the refresh still blocks the dispatch.
        if self._kill_switch.is_engaged():
            raise PaperExecutionRefusedError(
                "the execution kill switch is engaged; no order may be dispatched"
            )

        timing = PaperTimeWindow(self._time_source)
        evidence = _gather(
            broker=self._broker,
            market_data=self._market_data,
            kill_switch=self._kill_switch,
            symbol=intent.symbol,
            snapshot_id=command.account_snapshot_id,
            at=command.at,
            timing=timing,
        )
        if evidence.kill_switch_engaged:
            raise PaperExecutionRefusedError(
                "the execution kill switch was engaged while the dispatch was being prepared"
            )
        self._snapshots.save(evidence.account)

        # REBUILT from fresh evidence. Every refusal a preview would have raised
        # is re-raised here against the numbers that are true NOW.
        evaluated_at = timing.now()
        fresh = build_submission_preview(
            preview_id=f"{command.attempt_id}-RECHECK",
            intent=intent,
            account=evidence.account,
            preview_version=1,
            market_is_open=evidence.market_is_open,
            market_next_open=evidence.market_next_open,
            market_next_close=evidence.market_next_close,
            quote_bid=evidence.quote_bid,
            quote_ask=evidence.quote_ask,
            quote_captured_at=evidence.quote_captured_at,
            quote_source=evidence.quote_source,
            asset_tradable=evidence.asset_tradable,
            asset_status=evidence.asset_status,
            asset_class=evidence.asset_class,
            asset_exchange=evidence.asset_exchange,
            asset_fractionable=evidence.asset_fractionable,
            approved_watchlist=command.approved_watchlist,
            maximum_notional=command.maximum_notional,
            quote_maximum_age_seconds=command.quote_maximum_age_seconds,
            existing_position_quantity=evidence.existing_position_quantity,
            execution_kill_switch_engaged=evidence.kill_switch_engaged,
            created_at=evaluated_at,
        )
        if not fresh.is_authorizable:
            raise PaperExecutionRefusedError(
                "conditions changed since the preview and this order is no longer "
                "dispatchable: " + "; ".join(fresh.refusals)
            )

        fingerprint_now = request_fingerprint(
            order=fresh.order,
            account_reference=evidence.account.account_reference,
            endpoint_host=self._broker.endpoint_host,
            intent_governance_id=intent.intent_governance_id,
            approved_fingerprint=intent.approved_fingerprint,
        )
        refusal = authorization.refusal_against(
            request_fingerprint_now=fingerprint_now,
            account_reference_now=evidence.account.account_reference,
            instant=timing.now(),
        )
        if refusal is not None:
            raise PaperExecutionRefusedError(f"this dispatch is not authorized: {refusal}")

        # CLAIM BEFORE THE NETWORK. Everything above is a check; this is the
        # commitment, and it happens while nothing has been sent.
        claim = self._attempts.claim_dispatch(
            attempt_id=command.attempt_id,
            authorization=authorization,
            request_fingerprint_now=fingerprint_now,
            account_reference_now=evidence.account.account_reference,
            claimed_at=timing.now(),
            claim_clock=timing.now,
        )
        if not claim.won:
            return PaperSubmissionResult(
                attempt=claim.attempt,
                dispatched=False,
                http_status=None,
                broker_status=claim.attempt.broker_status,
                note=(
                    "another worker had already claimed this dispatch; no request was "
                    "sent and the persisted attempt is returned"
                ),
            )

        attempt = self._attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PaperExecutionState.SUBMISSION_IN_PROGRESS,
            at=timing.last_safe_at,
        )

        def before_send() -> None:
            # The transport invokes this AFTER connect, immediately before HTTP send.
            # Read the kill switch before sampling time: a DB wait must age evidence.
            try:
                if self._kill_switch.is_engaged():
                    raise PaperExecutionRefusedError("the execution kill switch is engaged")
                instant = timing.now()
                refusal = authorization.refusal_against(
                    request_fingerprint_now=fingerprint_now,
                    account_reference_now=evidence.account.account_reference,
                    instant=instant,
                )
                if refusal is not None or instant < authorization.authorized_at:
                    raise PaperExecutionRefusedError(refusal or "authorization is future-dated")
                if instant >= intent.expires_at or instant >= intent.mandatory_liquidation_at:
                    raise PaperExecutionRefusedError(
                        "the approved intent or liquidation deadline expired"
                    )
                if (
                    not evidence.market_is_open
                    or evidence.market_next_close is None
                    or instant >= evidence.market_next_close
                ):
                    raise PaperExecutionRefusedError("the regular market session is closed")
                quote_at = evidence.quote_captured_at
                if (
                    quote_at is None
                    or not 0
                    <= (instant - quote_at).total_seconds()
                    <= command.quote_maximum_age_seconds
                ):
                    raise PaperExecutionRefusedError(
                        "quote freshness cannot be established before send"
                    )
            except (PaperExecutionRefusedError, PaperTimeUncertainError) as error:
                raise BrokerNotSentError(str(error)) from error

        return self._dispatch(
            attempt=attempt,
            order=fresh.order,
            intent_id=intent.intent_governance_id,
            at=timing.last_safe_at,
            before_send=before_send,
            timing=timing,
        )

    def _dispatch(
        self,
        *,
        attempt: ExecutionAttempt,
        order: object,
        intent_id: str,
        at: datetime,
        before_send: Callable[[], None],
        timing: PaperTimeWindow,
    ) -> PaperSubmissionResult:
        from empirical_platform.decision_candidate.paper_execution import PaperOrderRequest

        assert isinstance(order, PaperOrderRequest)
        try:
            status, view, sanitized = self._broker.submit_order(order, before_send=before_send)
        except BrokerNotSentError as error:
            at = timing.last_safe_at
            # DEFINITELY not sent. Safe to close without reconciliation, because
            # there is nothing at the broker to reconcile against.
            final = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PaperExecutionState.REJECTED,
                at=at,
                failure_code="NOT_SENT",
                failure_detail=str(error)[:500],
            )
            self._record_event(intent_id, attempt.attempt_id, "DISPATCH_NOT_SENT", str(error), at)
            return PaperSubmissionResult(
                attempt=final,
                dispatched=False,
                http_status=None,
                broker_status=None,
                note="the request never reached the broker; no order exists",
            )
        except BrokerAmbiguousDispatchError as error:
            at = timing.last_safe_at
            # MAY have been delivered. This must never become a second order.
            final = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PaperExecutionState.SUBMISSION_UNKNOWN,
                at=at,
                failure_code="AMBIGUOUS",
                failure_detail=str(error)[:500],
            )
            self._record_event(
                intent_id, attempt.attempt_id, "DISPATCH_OUTCOME_UNKNOWN", str(error), at
            )
            return PaperSubmissionResult(
                attempt=final,
                dispatched=True,
                http_status=None,
                broker_status=None,
                note=(
                    "the outcome is UNKNOWN: the request may have been delivered. Reconcile "
                    "using the same client_order_id; do not send again"
                ),
            )

        at = timing.last_safe_at
        sequence = self._acknowledgements.next_sequence(attempt.attempt_id)
        self._acknowledgements.append(
            BrokerAcknowledgement(
                acknowledgement_id=f"ACK-{attempt.attempt_id}-{sequence}",
                attempt_id=attempt.attempt_id,
                sequence=sequence,
                kind="SUBMIT",
                observed_at=at,
                http_status=status,
                broker_order_id=None if view is None else view.broker_order_id,
                broker_status=None if view is None else view.status,
                client_order_id_echo=None if view is None else view.client_order_id,
                payload_digest=self._digest(sanitized),
                sanitized_payload=sanitized[:8192],
            )
        )

        if view is None:
            final = self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=PaperExecutionState.REJECTED,
                at=at,
                failure_code=f"HTTP_{status}",
                failure_detail=sanitized[:500],
            )
            self._record_event(
                intent_id, attempt.attempt_id, "DISPATCH_REFUSED_BY_BROKER", f"HTTP {status}", at
            )
            return PaperSubmissionResult(
                attempt=final,
                dispatched=True,
                http_status=status,
                broker_status=None,
                note=f"the broker refused the order with HTTP {status}",
            )

        submitted = self._attempts.transition(
            attempt_id=attempt.attempt_id,
            target=PaperExecutionState.PAPER_SUBMITTED,
            at=at,
            broker_order_id=view.broker_order_id,
            broker_status=view.status,
            filled_quantity=view.filled_quantity,
            filled_avg_price=view.filled_avg_price,
        )
        final = self._apply_broker_status(attempt_id=submitted.attempt_id, view=view, at=at)
        self._record_event(
            intent_id,
            attempt.attempt_id,
            "PAPER_ORDER_SUBMITTED",
            f"broker_status={view.status} broker_order_id={view.broker_order_id}",
            at,
        )
        return PaperSubmissionResult(
            attempt=final,
            dispatched=True,
            http_status=status,
            broker_status=view.status,
            note="the paper broker acknowledged the order",
        )

    def _apply_broker_status(
        self, *, attempt_id: str, view: BrokerOrderView, at: datetime
    ) -> ExecutionAttempt:
        """Map a broker status onto a state, or leave the state alone.

        An unmapped status is recorded and reported, never guessed at. See the
        module docstring.
        """
        target = _BROKER_STATUS_TO_STATE.get(view.status)
        current = self._attempts.get(attempt_id)
        if current is None:
            raise NotFoundError(f"no paper execution attempt {attempt_id!r} exists")
        if target is None or target is current.state:
            return self._attempts.transition(
                attempt_id=attempt_id,
                target=current.state,
                at=at,
                broker_order_id=view.broker_order_id,
                broker_status=view.status,
                filled_quantity=view.filled_quantity,
                filled_avg_price=view.filled_avg_price,
            )
        return self._attempts.transition(
            attempt_id=attempt_id,
            target=target,
            at=at,
            broker_order_id=view.broker_order_id,
            broker_status=view.status,
            filled_quantity=view.filled_quantity,
            filled_avg_price=view.filled_avg_price,
        )

    def _record_event(
        self, intent_id: str, attempt_id: str, event_type: str, detail: str, at: datetime
    ) -> None:
        self._events.append(
            PaperExecutionEvent(
                event_id=f"EVT-{attempt_id}-{event_type}"[:64],
                intent_governance_id=intent_id,
                attempt_id=attempt_id,
                event_type=event_type,
                occurred_at=at,
                detail=detail[:500],
            )
        )

    @staticmethod
    def _digest(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReconcilePaperOrderCommand:
    intent_governance_id: str
    at: datetime


class ReconcilePaperOrderHandler:
    """Ask the broker about the SAME client_order_id, and record the answer."""

    __slots__ = ("_attempts", "_acknowledgements", "_events", "_broker")

    def __init__(
        self,
        *,
        attempts: ExecutionAttemptRepository,
        acknowledgements: BrokerAcknowledgementRepository,
        events: PaperExecutionEventRepository,
        broker: PaperBrokerPort,
    ) -> None:
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._broker = broker

    def handle(self, command: ReconcilePaperOrderCommand) -> ExecutionAttempt:
        attempt = self._attempts.for_intent(command.intent_governance_id)
        if attempt is None:
            raise NotFoundError(
                f"no dispatch attempt exists for intent {command.intent_governance_id!r}"
            )
        if attempt.is_terminal:
            return attempt

        status, view, sanitized = self._broker.fetch_order_by_client_order_id(
            attempt.client_order_id
        )
        sequence = self._acknowledgements.next_sequence(attempt.attempt_id)
        self._acknowledgements.append(
            BrokerAcknowledgement(
                acknowledgement_id=f"ACK-{attempt.attempt_id}-{sequence}",
                attempt_id=attempt.attempt_id,
                sequence=sequence,
                kind="RECONCILE",
                observed_at=command.at,
                http_status=status,
                broker_order_id=None if view is None else view.broker_order_id,
                broker_status=None if view is None else view.status,
                client_order_id_echo=None if view is None else view.client_order_id,
                payload_digest=SubmitAuthorizedPaperOrderHandler._digest(sanitized),
                sanitized_payload=sanitized[:8192],
            )
        )

        if view is None:
            return self._handle_absence(attempt=attempt, status=status, at=command.at)

        target = _BROKER_STATUS_TO_STATE.get(view.status)
        if target is None or target is attempt.state:
            return self._attempts.transition(
                attempt_id=attempt.attempt_id,
                target=attempt.state,
                at=command.at,
                broker_order_id=view.broker_order_id,
                broker_status=view.status,
                filled_quantity=view.filled_quantity,
                filled_avg_price=view.filled_avg_price,
            )
        self._events.append(
            PaperExecutionEvent(
                event_id=f"EVT-{attempt.attempt_id}-RECON-{sequence}"[:64],
                intent_governance_id=attempt.intent_governance_id,
                attempt_id=attempt.attempt_id,
                event_type="RECONCILED",
                occurred_at=command.at,
                detail=f"{attempt.state.value}->{target.value} broker_status={view.status}"[:500],
            )
        )
        return self._attempts.transition(
            attempt_id=attempt.attempt_id,
            target=target,
            at=command.at,
            broker_order_id=view.broker_order_id,
            broker_status=view.status,
            filled_quantity=view.filled_quantity,
            filled_avg_price=view.filled_avg_price,
        )

    def _handle_absence(
        self, *, attempt: ExecutionAttempt, status: int, at: datetime
    ) -> ExecutionAttempt:
        """The broker does not know this order. That is not proof it never did.

        A 404 immediately after an ambiguous dispatch may simply mean the request
        is still in flight. The bounded policy in
        `RECONCILIATION_UNKNOWN_POLICY` decides, using the number of consecutive
        not-found observations and the time since the dispatch -- never the first
        answer alone.
        """
        if status != 404:
            self._events.append(
                PaperExecutionEvent(
                    event_id=f"EVT-{attempt.attempt_id}-RECON-ERR"[:64],
                    intent_governance_id=attempt.intent_governance_id,
                    attempt_id=attempt.attempt_id,
                    event_type="RECONCILE_UNUSABLE_ANSWER",
                    occurred_at=at,
                    detail=f"HTTP {status}"[:500],
                )
            )
            return attempt

        observations = [
            acknowledgement
            for acknowledgement in self._acknowledgements.for_attempt(attempt.attempt_id)
            if acknowledgement.kind == "RECONCILE" and acknowledgement.http_status == 404
        ]
        elapsed = (at - (attempt.submitted_at or attempt.claimed_at)).total_seconds()
        enough_observations = len(observations) >= MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS
        enough_time = elapsed >= MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS
        if not (enough_observations and enough_time):
            self._events.append(
                PaperExecutionEvent(
                    event_id=f"EVT-{attempt.attempt_id}-RECON-404-{len(observations)}"[:64],
                    intent_governance_id=attempt.intent_governance_id,
                    attempt_id=attempt.attempt_id,
                    event_type="RECONCILE_NOT_FOUND_INSUFFICIENT",
                    occurred_at=at,
                    detail=(
                        f"observations={len(observations)} elapsed={int(elapsed)}s; "
                        "policy not yet satisfied, state unchanged"
                    )[:500],
                )
            )
            return attempt

        self._events.append(
            PaperExecutionEvent(
                event_id=f"EVT-{attempt.attempt_id}-RECON-RESOLVED"[:64],
                intent_governance_id=attempt.intent_governance_id,
                attempt_id=attempt.attempt_id,
                event_type="RECONCILE_RESOLVED_NOT_FOUND",
                occurred_at=at,
                detail=(
                    f"observations={len(observations)} elapsed={int(elapsed)}s; "
                    "bounded policy satisfied"
                )[:500],
            )
        )
        return self._attempts.transition(
            attempt_id=attempt.attempt_id,
            target=PaperExecutionState.REJECTED,
            at=at,
            failure_code="NOT_FOUND_AT_BROKER",
            failure_detail=(
                "the broker reported no such client_order_id across "
                f"{len(observations)} observations over {int(elapsed)}s"
            ),
        )


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CancelPaperOrderCommand:
    intent_governance_id: str
    at: datetime


class CancelPaperOrderHandler:
    __slots__ = ("_attempts", "_acknowledgements", "_events", "_broker")

    def __init__(
        self,
        *,
        attempts: ExecutionAttemptRepository,
        acknowledgements: BrokerAcknowledgementRepository,
        events: PaperExecutionEventRepository,
        broker: PaperBrokerPort,
    ) -> None:
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._broker = broker

    def handle(self, command: CancelPaperOrderCommand) -> ExecutionAttempt:
        attempt = self._attempts.for_intent(command.intent_governance_id)
        if attempt is None:
            raise NotFoundError(
                f"no dispatch attempt exists for intent {command.intent_governance_id!r}"
            )
        if attempt.is_terminal:
            raise PaperExecutionRefusedError(
                f"the attempt is already terminal in state {attempt.state.value}"
            )
        if attempt.broker_order_id is None:
            raise PaperExecutionRefusedError(
                "this attempt has no broker order id, so there is nothing to cancel; "
                "reconcile it first"
            )

        status, sanitized = self._broker.cancel_order(attempt.broker_order_id)
        sequence = self._acknowledgements.next_sequence(attempt.attempt_id)
        self._acknowledgements.append(
            BrokerAcknowledgement(
                acknowledgement_id=f"ACK-{attempt.attempt_id}-{sequence}",
                attempt_id=attempt.attempt_id,
                sequence=sequence,
                kind="CANCEL",
                observed_at=command.at,
                http_status=status,
                broker_order_id=attempt.broker_order_id,
                broker_status=None,
                client_order_id_echo=attempt.client_order_id,
                payload_digest=SubmitAuthorizedPaperOrderHandler._digest(sanitized),
                sanitized_payload=sanitized[:8192],
            )
        )
        self._events.append(
            PaperExecutionEvent(
                event_id=f"EVT-{attempt.attempt_id}-CANCEL-{sequence}"[:64],
                intent_governance_id=attempt.intent_governance_id,
                attempt_id=attempt.attempt_id,
                event_type="CANCEL_REQUESTED",
                occurred_at=command.at,
                detail=f"HTTP {status}"[:500],
            )
        )
        if status not in {200, 204}:
            # The cancel was refused. The order is whatever it was; saying
            # otherwise would be inventing an outcome.
            return attempt
        # CANCEL_REQUESTED, not CANCELED. Asking to cancel is not a cancellation:
        # the request races the venue and can lose to a fill, so only
        # reconciliation may declare the terminal state.
        return self._attempts.transition(
            attempt_id=attempt.attempt_id,
            target=PaperExecutionState.CANCEL_REQUESTED,
            at=command.at,
        )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ShowPaperExecutionQuery:
    intent_governance_id: str


@dataclass(frozen=True, slots=True)
class PaperExecutionStatus:
    intent_governance_id: str
    state: PaperExecutionState
    attempt: ExecutionAttempt | None
    authorization: ExecutionAuthorization | None
    preview: SubmissionPreview | None
    acknowledgements: tuple[BrokerAcknowledgement, ...]
    events: tuple[PaperExecutionEvent, ...]


class ShowPaperExecutionHandler:
    """The whole chain behind one intent, in one answer.

    TAKES THE INTENT REPOSITORY ONLY TO REFUSE AN UNKNOWN ONE. Without it, an
    intent that does not exist has no attempt, no authorization and no preview,
    which `_overall_state` reads as NOT_DISPATCHED -- so a mistyped identifier
    produced the reassuring answer "this has not been dispatched" about something
    that was never there. The installed-wheel walkthrough found that: step 30
    expected a refusal and got exit 0. An operator asking about the wrong
    identifier must be told so.
    """

    __slots__ = (
        "_intents",
        "_attempts",
        "_authorizations",
        "_previews",
        "_acknowledgements",
        "_events",
    )

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        attempts: ExecutionAttemptRepository,
        authorizations: ExecutionAuthorizationRepository,
        previews: SubmissionPreviewRepository,
        acknowledgements: BrokerAcknowledgementRepository,
        events: PaperExecutionEventRepository,
    ) -> None:
        self._intents = intents
        self._attempts = attempts
        self._authorizations = authorizations
        self._previews = previews
        self._acknowledgements = acknowledgements
        self._events = events

    def handle(self, query: ShowPaperExecutionQuery) -> PaperExecutionStatus:
        if self._intents.get(query.intent_governance_id) is None:
            raise NotFoundError(f"no approved order intent {query.intent_governance_id!r} exists")
        attempt = self._attempts.for_intent(query.intent_governance_id)
        authorization = self._authorizations.latest_for_intent(query.intent_governance_id)
        preview = self._previews.latest_for_intent(query.intent_governance_id)
        return PaperExecutionStatus(
            intent_governance_id=query.intent_governance_id,
            state=_overall_state(attempt=attempt, authorization=authorization, preview=preview),
            attempt=attempt,
            authorization=authorization,
            preview=preview,
            acknowledgements=(
                () if attempt is None else self._acknowledgements.for_attempt(attempt.attempt_id)
            ),
            events=self._events.for_intent(query.intent_governance_id),
        )


def _overall_state(
    *,
    attempt: ExecutionAttempt | None,
    authorization: ExecutionAuthorization | None,
    preview: SubmissionPreview | None,
) -> PaperExecutionState:
    """Where one intent stands, including the states no attempt row can hold.

    NOT_DISPATCHED, AUTHORIZATION_PENDING and AUTHORIZED describe an intent that
    has no attempt yet, so they are derived here rather than stored -- a row
    claiming one of them would contradict its own existence.
    """
    if attempt is not None:
        return attempt.state
    if authorization is not None and not authorization.is_consumed:
        return PaperExecutionState.AUTHORIZED
    if preview is not None:
        return PaperExecutionState.AUTHORIZATION_PENDING
    return PaperExecutionState.NOT_DISPATCHED


@dataclass(frozen=True, slots=True)
class ListPaperExecutionsQuery:
    limit: int


class ListPaperExecutionsHandler:
    __slots__ = ("_attempts",)

    def __init__(self, *, attempts: ExecutionAttemptRepository) -> None:
        self._attempts = attempts

    def handle(self, query: ListPaperExecutionsQuery) -> tuple[ExecutionAttempt, ...]:
        return self._attempts.list_recent(query.limit)


@dataclass(frozen=True, slots=True)
class PaperExecutionStatusQuery:
    intent_governance_id: str


class PaperExecutionStatusHandler:
    """Just the state, for an operator who wants one word.

    Refuses an unknown intent for the same reason as
    `ShowPaperExecutionHandler`: NOT_DISPATCHED about a nonexistent intent is a
    confident answer to a question nobody asked.
    """

    __slots__ = ("_intents", "_attempts", "_authorizations", "_previews")

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        attempts: ExecutionAttemptRepository,
        authorizations: ExecutionAuthorizationRepository,
        previews: SubmissionPreviewRepository,
    ) -> None:
        self._intents = intents
        self._attempts = attempts
        self._authorizations = authorizations
        self._previews = previews

    def handle(self, query: PaperExecutionStatusQuery) -> PaperExecutionState:
        if self._intents.get(query.intent_governance_id) is None:
            raise NotFoundError(f"no approved order intent {query.intent_governance_id!r} exists")
        return _overall_state(
            attempt=self._attempts.for_intent(query.intent_governance_id),
            authorization=self._authorizations.latest_for_intent(query.intent_governance_id),
            preview=self._previews.latest_for_intent(query.intent_governance_id),
        )


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SetExecutionKillSwitchCommand:
    engaged: bool
    changed_by: str
    changed_at: datetime
    reason: str


class SetExecutionKillSwitchHandler:
    __slots__ = ("_kill_switch",)

    def __init__(self, *, kill_switch: ExecutionKillSwitchRepository) -> None:
        self._kill_switch = kill_switch

    def handle(self, command: SetExecutionKillSwitchCommand) -> bool:
        """Returns whether this call changed anything."""
        if command.engaged:
            return self._kill_switch.engage(
                changed_by=command.changed_by,
                changed_at=command.changed_at,
                reason=command.reason,
            )
        return self._kill_switch.disengage(
            changed_by=command.changed_by,
            changed_at=command.changed_at,
            reason=command.reason,
        )
