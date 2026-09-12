"""MILESTONE-085 in-memory fakes and builders, shared by the unit suites.

An underscore-prefixed module rather than a test module, following
`tests/contract/_fakes.py` and `tests/integration/_m085_support.py`: pytest does not
collect it, and a test file importing it is importing a helper rather than reaching
into another test's internals.

THE FAKES ARE DELIBERATELY DUMB -- dictionaries and lists, with no behaviour of
their own -- so that a test which passes cannot be passing because a fake was
clever. The one exception is `FakeAttempts`, which records the ORDER of its
transitions, because the order is part of what the handlers must get right.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionEvent,
    PaperExecutionState,
    PaperOrderRequest,
    SubmissionPreview,
    build_submission_preview,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovedOrderIntent,
    SubmissionState,
)

_NOW = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)
_DIGEST = "a" * 64
_ACCOUNT_REFERENCE = "ref:0123456789abcdef0123456789abcdef"

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def an_intent(**overrides: object) -> ApprovedOrderIntent:
    defaults: dict[str, object] = {
        "intent_governance_id": "INT-1",
        "proposal_governance_id": "PRP-1",
        "proposal_version": 1,
        "approved_fingerprint": _DIGEST,
        "decision_governance_id": "DEC-1",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "order_type": OrderType.LIMIT,
        "limit_price": Decimal("4.00"),
        "currency": "USD",
        "time_in_force": "DAY",
        "mandatory_liquidation_at": _NOW + timedelta(hours=3),
        "account_mode_required": "PREPARATION",
        "idempotency_key": "IDEM-1",
        "configuration_governance_id": "CFG-1",
        "configuration_version": 1,
        "evaluation_context_id": "ECX-1",
        "created_at": _NOW - timedelta(minutes=1),
        "expires_at": _NOW + timedelta(hours=1),
        "submission_state": SubmissionState.NOT_SUBMITTED,
    }
    defaults.update(overrides)
    return ApprovedOrderIntent(**defaults)  # type: ignore[arg-type]


def an_account(**overrides: object) -> PaperAccountSnapshot:
    defaults: dict[str, object] = {
        "snapshot_id": "SNP-1",
        "environment": PaperEnvironment.PAPER,
        "endpoint_host": PAPER_ENDPOINT_HOST,
        "account_reference": _ACCOUNT_REFERENCE,
        "account_status": "ACTIVE",
        "currency": "USD",
        "buying_power": Decimal("100000"),
        "cash": Decimal("100000"),
        "equity": Decimal("100000"),
        "multiplier": "4",
        "shorting_enabled": True,
        "trading_blocked": False,
        "transfers_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "captured_at": _NOW,
    }
    defaults.update(overrides)
    return PaperAccountSnapshot(**defaults)  # type: ignore[arg-type]


def a_preview(**overrides: object) -> SubmissionPreview:
    arguments: dict[str, object] = {
        "preview_id": "PVW-1",
        "intent": an_intent(),
        "account": an_account(),
        "preview_version": 1,
        "market_is_open": True,
        "market_next_open": _NOW + timedelta(hours=20),
        "market_next_close": _NOW + timedelta(hours=2),
        "quote_bid": Decimal("299.63"),
        "quote_ask": Decimal("299.70"),
        "quote_captured_at": _NOW - timedelta(seconds=5),
        "quote_source": "alpaca-iex",
        "asset_tradable": True,
        "asset_status": "active",
        "asset_class": "us_equity",
        "asset_exchange": "NASDAQ",
        "asset_fractionable": True,
        "approved_watchlist": frozenset({"AAPL"}),
        "maximum_notional": Decimal("5"),
        "quote_maximum_age_seconds": 60,
        "existing_position_quantity": 0,
        "execution_kill_switch_engaged": False,
        "created_at": _NOW,
    }
    arguments.update(overrides)
    return build_submission_preview(**arguments)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fakes. Dictionaries and lists, no cleverness.
# ---------------------------------------------------------------------------


class FakeIntents:
    def __init__(self, *intents: ApprovedOrderIntent) -> None:
        self.rows = {intent.intent_governance_id: intent for intent in intents}

    def get(self, intent_governance_id: str) -> ApprovedOrderIntent | None:
        return self.rows.get(intent_governance_id)


class FakeSnapshots:
    def __init__(self) -> None:
        self.rows: dict[str, PaperAccountSnapshot] = {}

    def save(self, snapshot: PaperAccountSnapshot) -> PaperAccountSnapshot:
        self.rows[snapshot.snapshot_id] = snapshot
        return snapshot

    def get(self, snapshot_id: str) -> PaperAccountSnapshot | None:
        return self.rows.get(snapshot_id)


class FakePreviews:
    def __init__(self) -> None:
        self.rows: dict[str, SubmissionPreview] = {}

    def save(self, preview: SubmissionPreview) -> SubmissionPreview:
        self.rows[preview.preview_id] = preview
        return preview

    def get(self, preview_id: str) -> SubmissionPreview | None:
        return self.rows.get(preview_id)

    def latest_for_intent(self, intent_governance_id: str) -> SubmissionPreview | None:
        matches = [
            preview
            for preview in self.rows.values()
            if preview.intent_governance_id == intent_governance_id
        ]
        return max(matches, key=lambda p: p.preview_version) if matches else None

    def next_version_for_intent(self, intent_governance_id: str) -> int:
        latest = self.latest_for_intent(intent_governance_id)
        return 1 if latest is None else latest.preview_version + 1


class FakeAuthorizations:
    def __init__(self) -> None:
        self.rows: dict[str, ExecutionAuthorization] = {}

    def save(self, authorization: ExecutionAuthorization) -> ExecutionAuthorization:
        self.rows[authorization.authorization_id] = authorization
        return authorization

    def get(self, authorization_id: str) -> ExecutionAuthorization | None:
        return self.rows.get(authorization_id)

    def latest_for_intent(self, intent_governance_id: str) -> ExecutionAuthorization | None:
        matches = [
            authorization
            for authorization in self.rows.values()
            if authorization.intent_governance_id == intent_governance_id
        ]
        return max(matches, key=lambda a: a.authorized_at) if matches else None


class FakeClaim:
    def __init__(self, *, won: bool, attempt: ExecutionAttempt) -> None:
        self.won = won
        self.attempt = attempt


class FakeAttempts:
    """Records transitions in order, so a test can assert the SEQUENCE."""

    def __init__(self) -> None:
        self.rows: dict[str, ExecutionAttempt] = {}
        self.transitions: list[tuple[str, PaperExecutionState]] = []
        self.claim_refusal: str | None = None
        self.claim_wins = True

    def claim_dispatch(
        self,
        *,
        attempt_id: str,
        authorization: ExecutionAuthorization,
        request_fingerprint_now: str,
        account_reference_now: str,
        claimed_at: datetime,
        claim_clock: Callable[[], datetime] | None = None,
    ) -> FakeClaim:
        if claim_clock is not None:
            claimed_at = claim_clock()
        refusal = authorization.refusal_against(
            request_fingerprint_now=request_fingerprint_now,
            account_reference_now=account_reference_now,
            instant=claimed_at,
        )
        if refusal is not None:
            raise ValueError(f"this dispatch is not authorized: {refusal}")
        attempt = ExecutionAttempt(
            attempt_id=attempt_id,
            intent_governance_id=authorization.intent_governance_id,
            authorization_id=authorization.authorization_id,
            client_order_id=authorization.client_order_id,
            request_fingerprint=authorization.request_fingerprint,
            state=PaperExecutionState.DISPATCH_CLAIMED,
            claimed_at=claimed_at,
            submitted_at=None,
            acknowledged_at=None,
            terminal_at=None,
            broker_order_id=None,
            broker_status=None,
            filled_quantity=None,
            filled_avg_price=None,
            failure_code=None,
            failure_detail=None,
        )
        self.rows[attempt_id] = attempt
        return FakeClaim(won=self.claim_wins, attempt=attempt)

    def get(self, attempt_id: str) -> ExecutionAttempt | None:
        return self.rows.get(attempt_id)

    def for_intent(self, intent_governance_id: str) -> ExecutionAttempt | None:
        for attempt in self.rows.values():
            if attempt.intent_governance_id == intent_governance_id:
                return attempt
        return None

    def by_client_order_id(self, client_order_id: str) -> ExecutionAttempt | None:
        for attempt in self.rows.values():
            if attempt.client_order_id == client_order_id:
                return attempt
        return None

    def transition(
        self,
        *,
        attempt_id: str,
        target: PaperExecutionState,
        at: datetime,
        broker_order_id: str | None = None,
        broker_status: str | None = None,
        filled_quantity: str | None = None,
        filled_avg_price: str | None = None,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> ExecutionAttempt:
        current = self.rows[attempt_id]
        self.transitions.append((attempt_id, target))
        terminal = target in {
            PaperExecutionState.FILLED,
            PaperExecutionState.CANCELED,
            PaperExecutionState.REJECTED,
            PaperExecutionState.EXPIRED,
        }
        updated = replace(
            current,
            state=target,
            submitted_at=(
                at if target is PaperExecutionState.SUBMISSION_IN_PROGRESS else current.submitted_at
            ),
            terminal_at=at if terminal else None,
            broker_order_id=broker_order_id or current.broker_order_id,
            broker_status=broker_status or current.broker_status,
            filled_quantity=(
                Decimal(filled_quantity) if filled_quantity else current.filled_quantity
            ),
            filled_avg_price=(
                Decimal(filled_avg_price) if filled_avg_price else current.filled_avg_price
            ),
            failure_code=failure_code or current.failure_code,
            failure_detail=failure_detail or current.failure_detail,
        )
        self.rows[attempt_id] = updated
        return updated

    def list_recent(self, limit: int) -> tuple[ExecutionAttempt, ...]:
        return tuple(list(self.rows.values())[:limit])


class FakeAcknowledgements:
    def __init__(self) -> None:
        self.rows: list[BrokerAcknowledgement] = []

    def append(self, acknowledgement: BrokerAcknowledgement) -> BrokerAcknowledgement:
        self.rows.append(acknowledgement)
        return acknowledgement

    def for_attempt(self, attempt_id: str) -> tuple[BrokerAcknowledgement, ...]:
        return tuple(row for row in self.rows if row.attempt_id == attempt_id)

    def next_sequence(self, attempt_id: str) -> int:
        return len(self.for_attempt(attempt_id)) + 1


class FakeEvents:
    def __init__(self) -> None:
        self.rows: list[PaperExecutionEvent] = []

    def append(self, event: PaperExecutionEvent) -> PaperExecutionEvent:
        self.rows.append(event)
        return event

    def for_intent(self, intent_governance_id: str) -> tuple[PaperExecutionEvent, ...]:
        return tuple(row for row in self.rows if row.intent_governance_id == intent_governance_id)


class FakeKillSwitch:
    def __init__(self, *, engaged: bool = False) -> None:
        self.engaged = engaged
        self.reads = 0

    def is_engaged(self) -> bool:
        self.reads += 1
        return self.engaged

    def engage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        del changed_by, changed_at, reason
        if self.engaged:
            return False
        self.engaged = True
        return True

    def disengage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        del changed_by, changed_at, reason
        if not self.engaged:
            return False
        self.engaged = False
        return True


class FakeView:
    def __init__(self, **fields: object) -> None:
        defaults: dict[str, object] = {
            "broker_order_id": "broker-1",
            "client_order_id": "m085-x",
            "status": "accepted",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": "1",
            "order_type": "limit",
            "filled_quantity": "0",
            "filled_avg_price": None,
        }
        defaults.update(fields)
        for name, value in defaults.items():
            setattr(self, name, value)


class FakeClock:
    is_open = True
    timestamp = _NOW
    next_open = _NOW + timedelta(hours=20)
    next_close = _NOW + timedelta(hours=2)


class FakeAsset:
    symbol = "AAPL"
    status = "active"
    tradable = True
    asset_class = "us_equity"
    exchange = "NASDAQ"
    fractionable = True


class FakeQuote:
    symbol = "AAPL"
    bid = "299.63"
    ask = "299.70"
    captured_at = _NOW - timedelta(seconds=5)
    source = "alpaca-iex"


#: Distinguishes "the caller said nothing" from "the caller said None". Several
#: fakes must be able to answer with None, so None cannot double as the default.
_UNSET = object()


class FakeBroker:
    """A broker that answers, and records what it was asked.

    Every knob is an explicitly typed attribute rather than an untyped kwargs bag,
    so a test that misspells one fails at the attribute instead of silently
    configuring nothing -- which is the failure mode a `**behaviour` dict has.
    They are plain attributes as well as constructor arguments because several
    tests must change the broker's answers AFTER an authorization was created
    from its earlier ones.
    """

    endpoint_host = PAPER_ENDPOINT_HOST

    def __init__(
        self,
        *,
        account_status_code: int = 200,
        account_overrides: dict[str, object] | None = None,
        position: object | None = None,
        submit_raises: BaseException | None = None,
        submit_status: int = 200,
        submit_view: object | None = _UNSET,
        submit_fields: dict[str, object] | None = None,
        submit_body: str = "{}",
        lookup_status: int = 200,
        lookup_view: object | None = _UNSET,
        lookup_fields: dict[str, object] | None = None,
        lookup_body: str = "{}",
        cancel_status: int = 204,
    ) -> None:
        self.account_status_code = account_status_code
        self.account_overrides: dict[str, object] = account_overrides or {}
        self.position = position
        self.submit_raises = submit_raises
        self.submit_status = submit_status
        self.submit_view = submit_view
        self.submit_fields: dict[str, object] = submit_fields or {}
        self.submit_body = submit_body
        self.lookup_status = lookup_status
        self.lookup_view = lookup_view
        self.lookup_fields: dict[str, object] = lookup_fields or {}
        self.lookup_body = lookup_body
        self.cancel_status = cancel_status
        self.submitted: list[object] = []
        self.cancelled: list[str] = []
        self.lookups: list[str] = []

    def fetch_account(self) -> tuple[int, dict[str, object]]:
        if self.account_status_code != 200:
            return self.account_status_code, {}
        payload: dict[str, object] = {
            "id": "real-account-id",
            "status": "ACTIVE",
            "currency": "USD",
            "buying_power": "100000",
            "cash": "100000",
            "equity": "100000",
            "multiplier": "4",
            "shorting_enabled": True,
            "trading_blocked": False,
            "transfers_blocked": False,
            "account_blocked": False,
            "trade_suspended_by_user": False,
        }
        payload.update(self.account_overrides)
        return 200, payload

    def fetch_clock(self) -> FakeClock:
        clock = FakeClock()
        clock.timestamp = datetime.now(UTC)
        return clock

    def fetch_asset(self, symbol: str) -> FakeAsset:
        del symbol
        return FakeAsset()

    def fetch_position(self, symbol: str) -> object | None:
        del symbol
        return self.position

    def submit_order(
        self, order: PaperOrderRequest, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, object | None, str]:
        if before_send is not None:
            before_send()
        self.submitted.append(order)
        if self.submit_raises is not None:
            raise self.submit_raises
        # The view ECHOES the client_order_id that was sent, because the real
        # adapter has already refused any answer that does not. A fake free to
        # answer about a different order would test the handler against a
        # response the adapter cannot deliver.
        view: object | None
        if self.submit_view is not _UNSET:
            view = self.submit_view
        elif self.submit_status >= 400:
            view = None
        else:
            fields: dict[str, object] = {"client_order_id": order.client_order_id}
            fields.update(self.submit_fields)
            view = FakeView(**fields)
        return self.submit_status, view, self.submit_body

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, object | None, str]:
        self.lookups.append(client_order_id)
        view: object | None
        if self.lookup_view is not _UNSET:
            view = self.lookup_view
        elif self.lookup_status >= 400:
            view = None
        else:
            fields: dict[str, object] = {"client_order_id": client_order_id}
            fields.update(self.lookup_fields)
            view = FakeView(**fields)
        return self.lookup_status, view, self.lookup_body

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]:
        self.cancelled.append(broker_order_id)
        return self.cancel_status, "{}"


class FakeMarketData:
    endpoint_host = "data.alpaca.markets"

    def __init__(self, *, quote: object | None = _UNSET) -> None:  # type: ignore[assignment]
        # A sentinel, not None: `quote=None` must mean "the feed returned nothing",
        # which is a case under test. Defaulting None to a quote would have made
        # test_an_absent_quote_refuses_on_freshness pass against a present quote.
        self._quote = FakeQuote() if quote is _UNSET else quote

    def fetch_quote(self, symbol: str) -> object | None:
        del symbol
        return self._quote
