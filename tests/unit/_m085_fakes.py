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
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    TERMINAL_PAPER_STATES,
    BrokerAcknowledgement,
    DecisionTimeBasis,
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionPolicy,
    IntentTimeBasis,
    M084TimeProvenance,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionEvent,
    PaperExecutionState,
    PaperOrderRequest,
    ProposalTimeBasis,
    SubmissionPreview,
    bind_intent_time_basis,
    build_submission_preview,
    execution_policy_from_configuration,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovedOrderIntent,
    SubmissionState,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerIdentityExistsError,
    BrokerIdentityUnresolvedError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, BrokerTimeBasis

_NOW = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)
_DIGEST = "a" * 64
_ACCOUNT_REFERENCE = "ref:0123456789abcdef0123456789abcdef"

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def a_time_basis(
    at: datetime = _NOW,
    *,
    broker_offset: timedelta = timedelta(0),
    round_trip: timedelta = timedelta(0),
) -> BrokerTimeBasis:
    """A measured basis: host readings at `at`, the broker `broker_offset` ahead.

    Zero-width by default because these fakes answer instantly; the width and
    the pairing are exercised against a scripted clock in the handler and time
    suites.
    """
    return BrokerTimeBasis(
        host_requested_at=at - round_trip,
        host_at=at,
        broker_earliest_at=at + broker_offset - round_trip,
        broker_latest_at=at + broker_offset,
    )


def an_intent_time_basis(
    intent: ApprovedOrderIntent | None = None, *, broker_offset: timedelta = timedelta(0)
) -> IntentTimeBasis:
    """The evidence the Paper-bound issuance command would have recorded for `intent`."""
    issued = an_intent() if intent is None else intent
    return bind_intent_time_basis(
        intent=issued,
        time_basis=a_time_basis(issued.created_at, broker_offset=broker_offset),
        broker_endpoint_host=PAPER_ENDPOINT_HOST,
    )


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


def a_configuration(**overrides: object) -> OperatorTradingConfiguration:
    """The configuration version `an_intent()` names: CFG-1 v1, the acceptance limits.

    USD 5 cap, 60 s freshness, 5 % spread, AAPL only, 09:45-15:30 New York. `_NOW` is
    10:00 in New York, inside the window. Corrective pass (D1): these are the ONLY
    source of the send-time limits the handlers apply.
    """
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-1",
        "configuration_version": 1,
        "base_currency": "USD",
        "permitted_markets": ("XNAS",),
        "watchlist": ("AAPL",),
        "prohibited_instruments": ("PENNY",),
        "maximum_deployable_capital": Decimal("10000"),
        "maximum_capital_per_trade": Decimal("5"),
        "maximum_percent_per_trade": Decimal("20"),
        "minimum_cash_reserve": Decimal("1000"),
        "maximum_simultaneous_positions": 3,
        "maximum_daily_loss": Decimal("500"),
        "maximum_daily_order_count": 10,
        "minimum_price": Decimal("1"),
        "maximum_price": Decimal("1000"),
        "minimum_liquidity_shares": 100_000,
        "maximum_spread_percent": Decimal("5"),
        "maximum_estimated_slippage_percent": Decimal("1"),
        "maximum_evidence_age_seconds": 86_400,
        "maximum_market_data_age_seconds": 60,
        "permitted_session": TradingSession.REGULAR,
        "earliest_entry_time": time(9, 45),
        "latest_entry_time": time(15, 30),
        "mandatory_liquidation_time": time(15, 45),
        "operator_timezone": "America/New_York",
        "exchange_calendar_policy": "XNAS-REGULAR-2026",
        "proposal_expiry_seconds": 300,
        "approval_expiry_seconds": 120,
        "default_order_type": OrderType.LIMIT,
        "permitted_order_types": (OrderType.LIMIT,),
        "limit_price_policy": LimitPricePolicy.ASK,
        "stop_loss_percent": Decimal("2"),
        "profit_exit_percent": Decimal("4"),
        "maximum_leverage": Decimal("1"),
        "short_selling_permitted": False,
        "overnight_positions_permitted": False,
        "account_mode": AccountMode.PREPARATION,
        "kill_switch": KillSwitchState.DISENGAGED,
    }
    defaults.update(overrides)
    return OperatorTradingConfiguration(**defaults)  # type: ignore[arg-type]


def a_policy(**overrides: object) -> ExecutionPolicy:
    return execution_policy_from_configuration(a_configuration(**overrides))


class FakeConfigurations:
    """Versioned configurations keyed by (id, version). Append-only, like the real store."""

    def __init__(self, *configurations: OperatorTradingConfiguration) -> None:
        self.rows = {
            (row.configuration_governance_id, row.configuration_version): row
            for row in (configurations or (a_configuration(),))
        }
        self.reads = 0

    def save(self, configuration: OperatorTradingConfiguration) -> OperatorTradingConfiguration:
        key = (configuration.configuration_governance_id, configuration.configuration_version)
        if key in self.rows:
            raise ValueError("configuration versions are never edited")
        self.rows[key] = configuration
        return configuration

    def get(
        self, configuration_governance_id: str, configuration_version: int
    ) -> OperatorTradingConfiguration | None:
        self.reads += 1
        return self.rows.get((configuration_governance_id, configuration_version))

    def latest(self, configuration_governance_id: str) -> OperatorTradingConfiguration | None:
        versions = [row for key, row in self.rows.items() if key[0] == configuration_governance_id]
        return max(versions, key=lambda row: row.configuration_version) if versions else None


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
        "policy": a_policy(),
        "existing_position_quantity": 0,
        "execution_kill_switch_engaged": False,
        "created_at": _NOW,
        "broker_now": BoundedInstant(earliest=_NOW, latest=_NOW),
    }
    arguments.update(overrides)
    if "m084_provenance" not in overrides:
        # Evidence for whichever intent the preview is about, so overriding the
        # intent cannot silently turn a test into a mismatched-evidence refusal.
        arguments["m084_provenance"] = a_provenance(arguments["intent"])  # type: ignore[arg-type]
    return build_submission_preview(**arguments)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fakes. Dictionaries and lists, no cleverness.
# ---------------------------------------------------------------------------


class FakeIntents:
    def __init__(self, *intents: ApprovedOrderIntent) -> None:
        self.rows = {intent.intent_governance_id: intent for intent in intents}

    def get(self, intent_governance_id: str) -> ApprovedOrderIntent | None:
        return self.rows.get(intent_governance_id)


class FakeTimeBases:
    """Three dictionaries, one per act that records a basis."""

    def __init__(
        self,
        *intents: IntentTimeBasis,
        proposals: tuple[ProposalTimeBasis, ...] = (),
        decisions: tuple[DecisionTimeBasis, ...] = (),
    ) -> None:
        self.intents = {row.intent_governance_id: row for row in intents}
        self.proposals = {
            (row.proposal_governance_id, row.proposal_version): row for row in proposals
        }
        self.decisions = {row.decision_governance_id: row for row in decisions}

    def record_proposal(self, evidence: ProposalTimeBasis) -> ProposalTimeBasis:
        key = (evidence.proposal_governance_id, evidence.proposal_version)
        if key in self.proposals:
            raise ValueError("a proposal-time basis is recorded once per proposal")
        self.proposals[key] = evidence
        return evidence

    def proposal(
        self, proposal_governance_id: str, proposal_version: int
    ) -> ProposalTimeBasis | None:
        return self.proposals.get((proposal_governance_id, proposal_version))

    def record_decision(self, evidence: DecisionTimeBasis) -> DecisionTimeBasis:
        if evidence.decision_governance_id in self.decisions:
            raise ValueError("a decision-time basis is recorded once per decision")
        self.decisions[evidence.decision_governance_id] = evidence
        return evidence

    def decision(self, decision_governance_id: str) -> DecisionTimeBasis | None:
        return self.decisions.get(decision_governance_id)

    def record_intent(self, evidence: IntentTimeBasis) -> IntentTimeBasis:
        if evidence.intent_governance_id in self.intents:
            raise ValueError("an intent-time basis is recorded once per intent")
        self.intents[evidence.intent_governance_id] = evidence
        return evidence

    def intent(self, intent_governance_id: str) -> IntentTimeBasis | None:
        return self.intents.get(intent_governance_id)


def a_provenance(
    intent: ApprovedOrderIntent | None = None,
    *,
    proposal_offset: timedelta = timedelta(0),
    decision_offset: timedelta = timedelta(0),
    intent_offset: timedelta = timedelta(0),
) -> M084TimeProvenance:
    """Evidence the three Paper-bound commands would have recorded behind `intent`.

    The proposal was evaluated 20 s and approved 10 s before the intent was issued,
    and the approval lasts an hour. Each offset is how far the broker's clock was
    AHEAD of this host's during that act.
    """
    issued = an_intent() if intent is None else intent
    evaluated_at = issued.created_at - timedelta(seconds=20)
    decided_at = issued.created_at - timedelta(seconds=10)
    return M084TimeProvenance(
        proposal=ProposalTimeBasis(
            proposal_governance_id=issued.proposal_governance_id,
            proposal_version=issued.proposal_version,
            content_fingerprint=issued.approved_fingerprint,
            proposal_created_at=evaluated_at,
            proposal_expires_at=issued.expires_at,
            mandatory_liquidation_at=issued.mandatory_liquidation_at,
            broker_endpoint_host=PAPER_ENDPOINT_HOST,
            basis_host_requested_at=evaluated_at,
            basis_host_at=evaluated_at,
            basis_broker_earliest_at=evaluated_at + proposal_offset,
            basis_broker_latest_at=evaluated_at + proposal_offset,
        ),
        decision=DecisionTimeBasis(
            decision_governance_id=issued.decision_governance_id,
            proposal_governance_id=issued.proposal_governance_id,
            proposal_version=issued.proposal_version,
            approved_fingerprint=issued.approved_fingerprint,
            decided_at=decided_at,
            decision_expires_at=decided_at + timedelta(hours=1),
            broker_endpoint_host=PAPER_ENDPOINT_HOST,
            basis_host_requested_at=decided_at,
            basis_host_at=decided_at,
            basis_broker_earliest_at=decided_at + decision_offset,
            basis_broker_latest_at=decided_at + decision_offset,
        ),
        intent=an_intent_time_basis(issued, broker_offset=intent_offset),
    )


def time_bases_for(*provenances: M084TimeProvenance) -> FakeTimeBases:
    return FakeTimeBases(
        *(p.intent for p in provenances if p.intent is not None),
        proposals=tuple(p.proposal for p in provenances if p.proposal is not None),
        decisions=tuple(p.decision for p in provenances if p.decision is not None),
    )


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
        broker_clock: Callable[[], BoundedInstant] | None = None,
    ) -> FakeClaim:
        if claim_clock is not None:
            claimed_at = claim_clock()
        refusal = authorization.refusal_against(
            request_fingerprint_now=request_fingerprint_now,
            account_reference_now=account_reference_now,
            instant=claimed_at,
            broker_now=broker_clock()
            if broker_clock is not None
            else (
                BoundedInstant(earliest=claimed_at, latest=claimed_at)
                if authorization.has_broker_time_basis
                else None
            ),
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
        if current.state in TERMINAL_PAPER_STATES:
            # Mirrors the database update guard (corrective pass, P2): a terminal
            # attempt is immutable, a same-state update included.
            raise ValueError(f"paper execution attempt {attempt_id!r} is terminal and is immutable")
        self.transitions.append((attempt_id, target))
        terminal = target in TERMINAL_PAPER_STATES
        updated = replace(
            current,
            state=target,
            submitted_at=current.submitted_at
            or (at if target is PaperExecutionState.SUBMISSION_IN_PROGRESS else None),
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
            # The fixture intent's limit price (see `an_intent`), so a view that names
            # nothing else describes the authorized order exactly. A test about a
            # mismatched order overrides the field it wants to differ.
            "limit_price": "4.00",
            "time_in_force": "day",
            "extended_hours": False,
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
        self.lookup_sequence: list[tuple[int, object | None, str]] = []
        self.lookup_raises: BaseException | None = None

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
            # As `AlpacaPaperClient._request` does: anything `before_send` raises means
            # nothing was sent, and is reported as a definite not-sent.
            try:
                before_send()
            except (BrokerNotSentError, BrokerIdentityExistsError, BrokerIdentityUnresolvedError):
                raise
            except Exception as error:  # noqa: BLE001 - mirrors the transport
                raise BrokerNotSentError(
                    f"pre-send validation failed: {type(error).__name__}"
                ) from error
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
        if self.lookup_raises is not None:
            raise self.lookup_raises
        if self.lookup_sequence:
            # Scripted answers, consumed in order; the standing knobs answer afterwards.
            # Lets a test say "404 before the send, found after it".
            return self.lookup_sequence.pop(0)
        view: object | None
        if self.lookup_view is not _UNSET:
            view = self.lookup_view
        elif self.lookup_status >= 400:
            view = None
        else:
            # A faithful broker knows only the orders it RECEIVED. Unless a test scripts
            # an answer, an identity nothing was sent under is not found (404), and an
            # identity that was sent echoes exactly the order that carried it. This is
            # what lets the pre-send identity check pass for a fresh dispatch and find
            # the order after a crash, without a test saying either.
            sent = [
                o for o in self.submitted if getattr(o, "client_order_id", None) == client_order_id
            ]
            if not sent:
                return 404, None, '{"code": 40410000, "message": "order not found"}'
            order = sent[-1]
            fields: dict[str, object] = {
                "client_order_id": client_order_id,
                "symbol": order.symbol,
                "side": order.side.lower(),
                "quantity": str(order.quantity),
                "order_type": order.order_type.value.lower(),
                "limit_price": None if order.limit_price is None else str(order.limit_price),
                "time_in_force": order.time_in_force.lower(),
                "extended_hours": order.extended_hours,
            }
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
