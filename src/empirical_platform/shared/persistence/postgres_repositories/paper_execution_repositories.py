"""MILESTONE-085 persistence for paper execution.

SEVEN REPOSITORIES AND ONE RUNTIME, ONE MODULE. They share one row-reading
discipline and one set of fail-closed converters, and every one of them serves a
single flow: preview, authorize, claim, submit, reconcile, cancel, audit.

FAIL CLOSED ON READ. Nothing here coerces a persisted value into the type it
should have had. A stored value of the wrong type means something outside this
milestone's enforcement boundary wrote the row -- DDL authority, a disabled
trigger, a superuser -- and the read path is exactly where that must be noticed
rather than papered over with `str(value)` or `int(value)`. This is the
MILESTONE-083 AUD-001 lesson, applied to rows that decide whether an order-shaped
request leaves this process.

EVERY SQL STATEMENT HERE IS A LITERAL CONSTANT. None is built by interpolating a
column list, even though that would be shorter. Interpolated SQL is what `ruff`'s
S608 reports, and MILESTONE-084's equivalent module carries ZERO suppressions --
so writing the columns out is the difference between adding twenty-one `noqa`
lines to this milestone's suppression budget and adding none. The statements are
also then greppable: a reader looking for what writes `paper_execution_attempt`
finds the whole statement rather than a format string.

`claim_dispatch` IS THE ONE PLACE EXACTLY-ONCE IS DECIDED. It consumes the
authorization and inserts the attempt inside ONE `unit_of_work()`, which is one
real transaction. The UPDATE is conditional on `consumed_at IS NULL`, so two
concurrent workers cannot both win it; the loser reads the persisted winner and
is handed that instead of an error, because a duplicate dispatch request must end
up reconciling the real order rather than creating a second one.

WHY THE RUNTIME IS ITS OWN CLASS. `PostgresRepositoryRuntime` is a MILESTONE-084
production file and MILESTONE-085 must not modify it.
`PostgresPaperExecutionRuntime` composes over the SAME caller-owned
`PostgresPersistenceService`, so both runtimes share one connection pool and one
transaction discipline without this milestone editing a byte of M084's
composition.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    TERMINAL_PAPER_STATES,
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionEvent,
    PaperExecutionState,
    PaperOrderRequest,
    SubmissionPreview,
)
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = [
    "PaperDispatchClaim",
    "PostgresBrokerAcknowledgementRepository",
    "PostgresExecutionAttemptRepository",
    "PostgresExecutionAuthorizationRepository",
    "PostgresExecutionKillSwitchRepository",
    "PostgresPaperAccountSnapshotRepository",
    "PostgresPaperExecutionEventRepository",
    "PostgresPaperExecutionRuntime",
    "PostgresSubmissionPreviewRepository",
]

_OPERATION = "m085.row_mapping"
_KILL_SWITCH_SCOPE = "GLOBAL"


def _fail(field: str, value: object, expected: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted MILESTONE-085 value {field} is {type(value).__name__}, not {expected}; "
            "refusing to coerce a malformed stored value"
        ),
        layer="persistence",
        operation=_OPERATION,
        context={"field": field, "actual_type": type(value).__name__},
    )


def _str(row: Mapping[str, Any], field: str) -> str:
    value = row[field]
    if not isinstance(value, str):
        raise _fail(field, value, "str")
    return value


def _optional_str(row: Mapping[str, Any], field: str) -> str | None:
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise _fail(field, value, "str or NULL")
    return value


def _int(row: Mapping[str, Any], field: str) -> int:
    value = row[field]
    # bool is an int subclass; a boolean in a numeric column is a malformed row,
    # so it is refused before the int check rather than passing through it.
    if isinstance(value, bool):
        raise _fail(field, value, "int")
    if not isinstance(value, int):
        raise _fail(field, value, "int")
    return value


def _bool(row: Mapping[str, Any], field: str) -> bool:
    value = row[field]
    if not isinstance(value, bool):
        raise _fail(field, value, "bool")
    return value


def _decimal(row: Mapping[str, Any], field: str) -> Decimal:
    value = row[field]
    if not isinstance(value, Decimal):
        raise _fail(field, value, "Decimal")
    return value


def _optional_decimal(row: Mapping[str, Any], field: str) -> Decimal | None:
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise _fail(field, value, "Decimal or NULL")
    return value


def _instant(row: Mapping[str, Any], field: str) -> datetime:
    value = row[field]
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _fail(field, value, "timezone-aware datetime")
    return value


def _optional_instant(row: Mapping[str, Any], field: str) -> datetime | None:
    if row[field] is None:
        return None
    return _instant(row, field)


def _member[EnumT: StrEnum](row: Mapping[str, Any], field: str, enum: type[EnumT]) -> EnumT:
    """Read a closed enumeration, refusing any value outside it.

    A stored value the enum does not name is not mapped onto a default or onto
    None. An unknown state is not a known one, and guessing which known one it
    meant is how a REJECTED attempt would come back as something else.
    """
    raw = _str(row, field)
    try:
        return enum(raw)
    except ValueError as error:
        raise FoundationError(
            category=FoundationErrorCategory.PERSISTENCE,
            message=(
                f"persisted MILESTONE-085 value {field} is {raw!r}, which is not a "
                f"member of {enum.__name__}; refusing to map it onto a known member"
            ),
            layer="persistence",
            operation=_OPERATION,
            context={"field": field, "stored_value": raw, "enum": enum.__name__},
        ) from error


def _refusals(row: Mapping[str, Any], field: str) -> tuple[str, ...]:
    """Read the stored refusal list, refusing anything that is not a JSON array.

    Stored as JSON rather than as a delimited string so that a refusal reason
    containing the delimiter cannot split into two reasons, or two into one.
    """
    raw = _str(row, field)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _fail(field, raw, "a JSON array of strings") from error
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise _fail(field, parsed, "a JSON array of strings")
    return tuple(parsed)


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

_KILL_SWITCH_LATEST = (
    "SELECT kill_switch_id, scope, version, engaged, changed_by, changed_at, reason "
    "FROM public.paper_execution_kill_switch "
    "WHERE scope = :scope ORDER BY version DESC LIMIT 1"
)

_KILL_SWITCH_INSERT = (
    "INSERT INTO public.paper_execution_kill_switch "
    "(kill_switch_id, scope, version, engaged, changed_by, changed_at, reason) "
    "VALUES (:kill_switch_id, :scope, :version, :engaged, :changed_by, :changed_at, :reason)"
)


class PostgresExecutionKillSwitchRepository:
    """The execution stop. Versioned, append-only, and read fresh every time."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def is_engaged(self) -> bool:
        """The latest version's state, or False when the switch has never moved.

        Never cached. A dispatch reads this immediately before the network call,
        so a value read minutes earlier would be exactly the wrong thing to
        trust.
        """
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_KILL_SWITCH_LATEST, {"scope": _KILL_SWITCH_SCOPE}))
        if not rows:
            return False
        return _bool(rows[0], "engaged")

    def engage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        return self._set(engaged=True, changed_by=changed_by, changed_at=changed_at, reason=reason)

    def disengage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        return self._set(engaged=False, changed_by=changed_by, changed_at=changed_at, reason=reason)

    def _set(self, *, engaged: bool, changed_by: str, changed_at: datetime, reason: str) -> bool:
        """Write a new version, or nothing when the switch is already there.

        Recording a change that did not happen would be worse than recording
        nothing: a reader would conclude somebody acted when nobody did.
        """
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_KILL_SWITCH_LATEST, {"scope": _KILL_SWITCH_SCOPE}))
            current = _bool(rows[0], "engaged") if rows else False
            if current == engaged:
                return False
            version = (_int(rows[0], "version") + 1) if rows else 1
            work.execute(
                _KILL_SWITCH_INSERT,
                {
                    "kill_switch_id": f"paper-kill-switch-v{version}",
                    "scope": _KILL_SWITCH_SCOPE,
                    "version": version,
                    "engaged": engaged,
                    "changed_by": changed_by,
                    "changed_at": changed_at,
                    "reason": reason,
                },
            )
        return True


# ---------------------------------------------------------------------------
# Account snapshot
# ---------------------------------------------------------------------------

_ACCOUNT_INSERT = (
    "INSERT INTO public.paper_account_snapshot "
    "(snapshot_id, environment, endpoint_host, account_reference, account_status, currency, "
    "buying_power, cash, equity, multiplier, shorting_enabled, trading_blocked, "
    "transfers_blocked, account_blocked, trade_suspended_by_user, captured_at) "
    "VALUES (:snapshot_id, :environment, :endpoint_host, :account_reference, :account_status, "
    ":currency, :buying_power, :cash, :equity, :multiplier, :shorting_enabled, "
    ":trading_blocked, :transfers_blocked, :account_blocked, :trade_suspended_by_user, "
    ":captured_at) "
    "RETURNING snapshot_id, environment, endpoint_host, account_reference, account_status, "
    "currency, buying_power, cash, equity, multiplier, shorting_enabled, trading_blocked, "
    "transfers_blocked, account_blocked, trade_suspended_by_user, captured_at"
)

_ACCOUNT_SELECT = (
    "SELECT snapshot_id, environment, endpoint_host, account_reference, account_status, "
    "currency, buying_power, cash, equity, multiplier, shorting_enabled, trading_blocked, "
    "transfers_blocked, account_blocked, trade_suspended_by_user, captured_at "
    "FROM public.paper_account_snapshot WHERE snapshot_id = :snapshot_id"
)


def _row_to_account(row: Mapping[str, Any]) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        snapshot_id=_str(row, "snapshot_id"),
        environment=_member(row, "environment", PaperEnvironment),
        endpoint_host=_str(row, "endpoint_host"),
        account_reference=_str(row, "account_reference"),
        account_status=_str(row, "account_status"),
        currency=_str(row, "currency"),
        buying_power=_decimal(row, "buying_power"),
        cash=_decimal(row, "cash"),
        equity=_decimal(row, "equity"),
        multiplier=_str(row, "multiplier"),
        shorting_enabled=_bool(row, "shorting_enabled"),
        trading_blocked=_bool(row, "trading_blocked"),
        transfers_blocked=_bool(row, "transfers_blocked"),
        account_blocked=_bool(row, "account_blocked"),
        trade_suspended_by_user=_bool(row, "trade_suspended_by_user"),
        captured_at=_instant(row, "captured_at"),
    )


class PostgresPaperAccountSnapshotRepository:
    """Append-only store of what the paper account said, when it said it."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, snapshot: PaperAccountSnapshot) -> PaperAccountSnapshot:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _ACCOUNT_INSERT,
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "environment": snapshot.environment.value,
                    "endpoint_host": snapshot.endpoint_host,
                    "account_reference": snapshot.account_reference,
                    "account_status": snapshot.account_status,
                    "currency": snapshot.currency,
                    "buying_power": snapshot.buying_power,
                    "cash": snapshot.cash,
                    "equity": snapshot.equity,
                    "multiplier": snapshot.multiplier,
                    "shorting_enabled": snapshot.shorting_enabled,
                    "trading_blocked": snapshot.trading_blocked,
                    "transfers_blocked": snapshot.transfers_blocked,
                    "account_blocked": snapshot.account_blocked,
                    "trade_suspended_by_user": snapshot.trade_suspended_by_user,
                    "captured_at": snapshot.captured_at,
                },
            )
        return _row_to_account(rows[0])

    def get(self, snapshot_id: str) -> PaperAccountSnapshot | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_ACCOUNT_SELECT, {"snapshot_id": snapshot_id}))
        return _row_to_account(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Submission preview
# ---------------------------------------------------------------------------

_PREVIEW_INSERT = (
    "INSERT INTO public.paper_submission_preview "
    "(preview_id, intent_governance_id, preview_version, account_snapshot_id, "
    "account_reference, symbol, side, quantity, order_type, limit_price, time_in_force, "
    "extended_hours, client_order_id, request_fingerprint, approved_fingerprint, "
    "market_is_open, market_next_open, market_next_close, quote_bid, quote_ask, "
    "quote_captured_at, quote_source, asset_tradable, asset_status, asset_class, "
    "asset_exchange, asset_fractionable, refusals, created_at) "
    "VALUES (:preview_id, :intent_governance_id, :preview_version, :account_snapshot_id, "
    ":account_reference, :symbol, :side, :quantity, :order_type, :limit_price, "
    ":time_in_force, :extended_hours, :client_order_id, :request_fingerprint, "
    ":approved_fingerprint, :market_is_open, :market_next_open, :market_next_close, "
    ":quote_bid, :quote_ask, :quote_captured_at, :quote_source, :asset_tradable, "
    ":asset_status, :asset_class, :asset_exchange, :asset_fractionable, :refusals, "
    ":created_at) "
    "RETURNING preview_id, intent_governance_id, preview_version, account_snapshot_id, "
    "account_reference, symbol, side, quantity, order_type, limit_price, time_in_force, "
    "extended_hours, client_order_id, request_fingerprint, approved_fingerprint, "
    "market_is_open, market_next_open, market_next_close, quote_bid, quote_ask, "
    "quote_captured_at, quote_source, asset_tradable, asset_status, asset_class, "
    "asset_exchange, asset_fractionable, refusals, created_at"
)

_PREVIEW_SELECT_BY_ID = (
    "SELECT preview_id, intent_governance_id, preview_version, account_snapshot_id, "
    "account_reference, symbol, side, quantity, order_type, limit_price, time_in_force, "
    "extended_hours, client_order_id, request_fingerprint, approved_fingerprint, "
    "market_is_open, market_next_open, market_next_close, quote_bid, quote_ask, "
    "quote_captured_at, quote_source, asset_tradable, asset_status, asset_class, "
    "asset_exchange, asset_fractionable, refusals, created_at "
    "FROM public.paper_submission_preview WHERE preview_id = :preview_id"
)

_PREVIEW_SELECT_LATEST = (
    "SELECT preview_id, intent_governance_id, preview_version, account_snapshot_id, "
    "account_reference, symbol, side, quantity, order_type, limit_price, time_in_force, "
    "extended_hours, client_order_id, request_fingerprint, approved_fingerprint, "
    "market_is_open, market_next_open, market_next_close, quote_bid, quote_ask, "
    "quote_captured_at, quote_source, asset_tradable, asset_status, asset_class, "
    "asset_exchange, asset_fractionable, refusals, created_at "
    "FROM public.paper_submission_preview WHERE intent_governance_id = :intent "
    "ORDER BY preview_version DESC LIMIT 1"
)

_PREVIEW_MAX_VERSION = (
    "SELECT COALESCE(MAX(preview_version), 0) AS highest "
    "FROM public.paper_submission_preview WHERE intent_governance_id = :intent"
)


def _row_to_preview(row: Mapping[str, Any]) -> SubmissionPreview:
    return SubmissionPreview(
        preview_id=_str(row, "preview_id"),
        intent_governance_id=_str(row, "intent_governance_id"),
        preview_version=_int(row, "preview_version"),
        account_snapshot_id=_str(row, "account_snapshot_id"),
        account_reference=_str(row, "account_reference"),
        order=PaperOrderRequest(
            symbol=_str(row, "symbol"),
            side=_str(row, "side"),
            quantity=_int(row, "quantity"),
            order_type=_member(row, "order_type", OrderType),
            limit_price=_optional_decimal(row, "limit_price"),
            time_in_force=_str(row, "time_in_force"),
            extended_hours=_bool(row, "extended_hours"),
            client_order_id=_str(row, "client_order_id"),
        ),
        request_fingerprint=_str(row, "request_fingerprint"),
        approved_fingerprint=_str(row, "approved_fingerprint"),
        market_is_open=_bool(row, "market_is_open"),
        market_next_open=_optional_instant(row, "market_next_open"),
        market_next_close=_optional_instant(row, "market_next_close"),
        quote_bid=_optional_decimal(row, "quote_bid"),
        quote_ask=_optional_decimal(row, "quote_ask"),
        quote_captured_at=_optional_instant(row, "quote_captured_at"),
        quote_source=_str(row, "quote_source"),
        asset_tradable=_bool(row, "asset_tradable"),
        asset_status=_str(row, "asset_status"),
        asset_class=_str(row, "asset_class"),
        asset_exchange=_str(row, "asset_exchange"),
        asset_fractionable=_bool(row, "asset_fractionable"),
        refusals=_refusals(row, "refusals"),
        created_at=_instant(row, "created_at"),
    )


class PostgresSubmissionPreviewRepository:
    """Append-only store of exactly what a human was shown."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, preview: SubmissionPreview) -> SubmissionPreview:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _PREVIEW_INSERT,
                {
                    "preview_id": preview.preview_id,
                    "intent_governance_id": preview.intent_governance_id,
                    "preview_version": preview.preview_version,
                    "account_snapshot_id": preview.account_snapshot_id,
                    "account_reference": preview.account_reference,
                    "symbol": preview.order.symbol,
                    "side": preview.order.side,
                    "quantity": preview.order.quantity,
                    "order_type": preview.order.order_type.value,
                    "limit_price": preview.order.limit_price,
                    "time_in_force": preview.order.time_in_force,
                    "extended_hours": preview.order.extended_hours,
                    "client_order_id": preview.order.client_order_id,
                    "request_fingerprint": preview.request_fingerprint,
                    "approved_fingerprint": preview.approved_fingerprint,
                    "market_is_open": preview.market_is_open,
                    "market_next_open": preview.market_next_open,
                    "market_next_close": preview.market_next_close,
                    "quote_bid": preview.quote_bid,
                    "quote_ask": preview.quote_ask,
                    "quote_captured_at": preview.quote_captured_at,
                    "quote_source": preview.quote_source,
                    "asset_tradable": preview.asset_tradable,
                    "asset_status": preview.asset_status,
                    "asset_class": preview.asset_class,
                    "asset_exchange": preview.asset_exchange,
                    "asset_fractionable": preview.asset_fractionable,
                    "refusals": json.dumps(list(preview.refusals)),
                    "created_at": preview.created_at,
                },
            )
        return _row_to_preview(rows[0])

    def get(self, preview_id: str) -> SubmissionPreview | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_PREVIEW_SELECT_BY_ID, {"preview_id": preview_id}))
        return _row_to_preview(rows[0]) if rows else None

    def latest_for_intent(self, intent_governance_id: str) -> SubmissionPreview | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_PREVIEW_SELECT_LATEST, {"intent": intent_governance_id}))
        return _row_to_preview(rows[0]) if rows else None

    def next_version_for_intent(self, intent_governance_id: str) -> int:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_PREVIEW_MAX_VERSION, {"intent": intent_governance_id}))
        return _int(rows[0], "highest") + 1


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

_AUTHORIZATION_INSERT = (
    "INSERT INTO public.paper_execution_authorization "
    "(authorization_id, intent_governance_id, preview_id, preview_version, "
    "request_fingerprint, account_reference, client_order_id, authorized_by, authorized_at, "
    "expires_at, consumed_at, consumed_by_attempt_id) "
    "VALUES (:authorization_id, :intent_governance_id, :preview_id, :preview_version, "
    ":request_fingerprint, :account_reference, :client_order_id, :authorized_by, "
    ":authorized_at, :expires_at, :consumed_at, :consumed_by_attempt_id) "
    "RETURNING authorization_id, intent_governance_id, preview_id, preview_version, "
    "request_fingerprint, account_reference, client_order_id, authorized_by, authorized_at, "
    "expires_at, consumed_at, consumed_by_attempt_id"
)

_AUTHORIZATION_SELECT_BY_ID = (
    "SELECT authorization_id, intent_governance_id, preview_id, preview_version, "
    "request_fingerprint, account_reference, client_order_id, authorized_by, authorized_at, "
    "expires_at, consumed_at, consumed_by_attempt_id "
    "FROM public.paper_execution_authorization WHERE authorization_id = :authorization_id"
)

_AUTHORIZATION_SELECT_LATEST = (
    "SELECT authorization_id, intent_governance_id, preview_id, preview_version, "
    "request_fingerprint, account_reference, client_order_id, authorized_by, authorized_at, "
    "expires_at, consumed_at, consumed_by_attempt_id "
    "FROM public.paper_execution_authorization WHERE intent_governance_id = :intent "
    "ORDER BY authorized_at DESC, authorization_id DESC LIMIT 1"
)

#: The exactly-once statement. `consumed_at IS NULL` is the entire race
#: mechanism: the second worker updates zero rows and gets nothing back.
_AUTHORIZATION_CONSUME = (
    "UPDATE public.paper_execution_authorization "
    "SET consumed_at = :claimed_at, consumed_by_attempt_id = :attempt_id "
    "WHERE authorization_id = :authorization_id AND consumed_at IS NULL "
    "RETURNING authorization_id, intent_governance_id, preview_id, preview_version, "
    "request_fingerprint, account_reference, client_order_id, authorized_by, authorized_at, "
    "expires_at, consumed_at, consumed_by_attempt_id"
)


def _row_to_authorization(row: Mapping[str, Any]) -> ExecutionAuthorization:
    return ExecutionAuthorization(
        authorization_id=_str(row, "authorization_id"),
        intent_governance_id=_str(row, "intent_governance_id"),
        preview_id=_str(row, "preview_id"),
        preview_version=_int(row, "preview_version"),
        request_fingerprint=_str(row, "request_fingerprint"),
        account_reference=_str(row, "account_reference"),
        client_order_id=_str(row, "client_order_id"),
        authorized_by=_str(row, "authorized_by"),
        authorized_at=_instant(row, "authorized_at"),
        expires_at=_instant(row, "expires_at"),
        consumed_at=_optional_instant(row, "consumed_at"),
        consumed_by_attempt_id=_optional_str(row, "consumed_by_attempt_id"),
    )


class PostgresExecutionAuthorizationRepository:
    """Append-only store of human permissions, with consumption the one mutation."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, authorization: ExecutionAuthorization) -> ExecutionAuthorization:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _AUTHORIZATION_INSERT,
                {
                    "authorization_id": authorization.authorization_id,
                    "intent_governance_id": authorization.intent_governance_id,
                    "preview_id": authorization.preview_id,
                    "preview_version": authorization.preview_version,
                    "request_fingerprint": authorization.request_fingerprint,
                    "account_reference": authorization.account_reference,
                    "client_order_id": authorization.client_order_id,
                    "authorized_by": authorization.authorized_by,
                    "authorized_at": authorization.authorized_at,
                    "expires_at": authorization.expires_at,
                    "consumed_at": authorization.consumed_at,
                    "consumed_by_attempt_id": authorization.consumed_by_attempt_id,
                },
            )
        return _row_to_authorization(rows[0])

    def get(self, authorization_id: str) -> ExecutionAuthorization | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(_AUTHORIZATION_SELECT_BY_ID, {"authorization_id": authorization_id})
            )
        return _row_to_authorization(rows[0]) if rows else None

    def latest_for_intent(self, intent_governance_id: str) -> ExecutionAuthorization | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(_AUTHORIZATION_SELECT_LATEST, {"intent": intent_governance_id})
            )
        return _row_to_authorization(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------

_ATTEMPT_INSERT = (
    "INSERT INTO public.paper_execution_attempt "
    "(attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail) "
    "VALUES (:attempt_id, :intent_governance_id, :authorization_id, :client_order_id, "
    ":request_fingerprint, :state, :claimed_at, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
    "NULL, NULL) "
    "RETURNING attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail"
)

_ATTEMPT_SELECT_BY_ID = (
    "SELECT attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail FROM public.paper_execution_attempt WHERE attempt_id = :key"
)

_ATTEMPT_SELECT_BY_INTENT = (
    "SELECT attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail FROM public.paper_execution_attempt WHERE intent_governance_id = :key"
)

_ATTEMPT_SELECT_BY_CLIENT_ORDER_ID = (
    "SELECT attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail FROM public.paper_execution_attempt WHERE client_order_id = :key"
)

_ATTEMPT_SELECT_RECENT = (
    "SELECT attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail FROM public.paper_execution_attempt "
    "ORDER BY claimed_at DESC, attempt_id DESC LIMIT :limit"
)

#: COALESCE on every broker column so that a later observation never blanks an
#: earlier one. `terminal_at` is set outright, because it must be present exactly
#: when the state is terminal and the database CHECK enforces that pairing.
_ATTEMPT_TRANSITION = (
    "UPDATE public.paper_execution_attempt SET "
    "state = :state, "
    "submitted_at = COALESCE(:submitted_at, submitted_at), "
    "acknowledged_at = COALESCE(:acknowledged_at, acknowledged_at), "
    "terminal_at = :terminal_at, "
    "broker_order_id = COALESCE(:broker_order_id, broker_order_id), "
    "broker_status = COALESCE(:broker_status, broker_status), "
    "filled_quantity = COALESCE(CAST(:filled_quantity AS numeric), filled_quantity), "
    "filled_avg_price = COALESCE(CAST(:filled_avg_price AS numeric), filled_avg_price), "
    "failure_code = COALESCE(:failure_code, failure_code), "
    "failure_detail = COALESCE(:failure_detail, failure_detail) "
    "WHERE attempt_id = :attempt_id "
    "RETURNING attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, submitted_at, acknowledged_at, terminal_at, "
    "broker_order_id, broker_status, filled_quantity, filled_avg_price, failure_code, "
    "failure_detail"
)


def _row_to_attempt(row: Mapping[str, Any]) -> ExecutionAttempt:
    return ExecutionAttempt(
        attempt_id=_str(row, "attempt_id"),
        intent_governance_id=_str(row, "intent_governance_id"),
        authorization_id=_str(row, "authorization_id"),
        client_order_id=_str(row, "client_order_id"),
        request_fingerprint=_str(row, "request_fingerprint"),
        state=_member(row, "state", PaperExecutionState),
        claimed_at=_instant(row, "claimed_at"),
        submitted_at=_optional_instant(row, "submitted_at"),
        acknowledged_at=_optional_instant(row, "acknowledged_at"),
        terminal_at=_optional_instant(row, "terminal_at"),
        broker_order_id=_optional_str(row, "broker_order_id"),
        broker_status=_optional_str(row, "broker_status"),
        filled_quantity=_optional_decimal(row, "filled_quantity"),
        filled_avg_price=_optional_decimal(row, "filled_avg_price"),
        failure_code=_optional_str(row, "failure_code"),
        failure_detail=_optional_str(row, "failure_detail"),
    )


class PaperDispatchClaim:
    """Who won the race to dispatch one intent, and the attempt that resulted."""

    __slots__ = ("_won", "_attempt")

    def __init__(self, *, won: bool, attempt: ExecutionAttempt) -> None:
        self._won = won
        self._attempt = attempt

    @property
    def won(self) -> bool:
        return self._won

    @property
    def attempt(self) -> ExecutionAttempt:
        return self._attempt

    def __repr__(self) -> str:
        return f"PaperDispatchClaim(won={self._won}, attempt_id={self._attempt.attempt_id!r})"


class PostgresExecutionAttemptRepository:
    """The dispatch lineage. One attempt per intent, ever, decided here."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def claim_dispatch(
        self,
        *,
        attempt_id: str,
        authorization: ExecutionAuthorization,
        request_fingerprint_now: str,
        account_reference_now: str,
        claimed_at: datetime,
    ) -> PaperDispatchClaim:
        """Consume the authorization and create the one attempt, atomically.

        The application refusal below is the legible one. The database refuses
        every part of it again -- the conditional UPDATE, the consumption
        trigger, the insert guard and three UNIQUE constraints -- so a caller who
        never came through here still cannot produce a second dispatch.
        """
        refusal = authorization.refusal_against(
            request_fingerprint_now=request_fingerprint_now,
            account_reference_now=account_reference_now,
            instant=claimed_at,
        )
        if refusal is not None:
            raise ValueError(f"this dispatch is not authorized: {refusal}")

        with self._service.unit_of_work() as work:
            claimed = list(
                work.execute(
                    _AUTHORIZATION_CONSUME,
                    {
                        "claimed_at": claimed_at,
                        "attempt_id": attempt_id,
                        "authorization_id": authorization.authorization_id,
                    },
                )
            )
            if not claimed:
                # Lost, or already spent. Hand back the persisted winner so the
                # caller reconciles the real order instead of creating another.
                existing = list(
                    work.execute(
                        _ATTEMPT_SELECT_BY_INTENT,
                        {"key": authorization.intent_governance_id},
                    )
                )
                if not existing:
                    raise ValueError(
                        "the authorization is already consumed but no attempt exists for it; "
                        "refusing to dispatch rather than guessing what happened"
                    )
                return PaperDispatchClaim(won=False, attempt=_row_to_attempt(existing[0]))

            rows = work.execute(
                _ATTEMPT_INSERT,
                {
                    "attempt_id": attempt_id,
                    "intent_governance_id": authorization.intent_governance_id,
                    "authorization_id": authorization.authorization_id,
                    "client_order_id": authorization.client_order_id,
                    "request_fingerprint": authorization.request_fingerprint,
                    "state": PaperExecutionState.DISPATCH_CLAIMED.value,
                    "claimed_at": claimed_at,
                },
            )
        return PaperDispatchClaim(won=True, attempt=_row_to_attempt(rows[0]))

    def get(self, attempt_id: str) -> ExecutionAttempt | None:
        return self._one(_ATTEMPT_SELECT_BY_ID, attempt_id)

    def for_intent(self, intent_governance_id: str) -> ExecutionAttempt | None:
        return self._one(_ATTEMPT_SELECT_BY_INTENT, intent_governance_id)

    def by_client_order_id(self, client_order_id: str) -> ExecutionAttempt | None:
        return self._one(_ATTEMPT_SELECT_BY_CLIENT_ORDER_ID, client_order_id)

    def _one(self, statement: str, key: str) -> ExecutionAttempt | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(statement, {"key": key}))
        return _row_to_attempt(rows[0]) if rows else None

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
        """Move one attempt along the closed table, letting the trigger decide.

        Deliberately does NOT re-check the edge in Python. The database trigger
        is the authority here, and holding the table in a third place would be a
        third thing that can drift. An illegal edge surfaces as a translated
        persistence error naming both states.
        """
        if not isinstance(target, PaperExecutionState):
            raise ValueError("target must be a PaperExecutionState")
        acknowledged_states = {
            PaperExecutionState.PAPER_SUBMITTED,
            PaperExecutionState.PAPER_ACCEPTED,
            PaperExecutionState.PARTIALLY_FILLED,
        }
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _ATTEMPT_TRANSITION,
                {
                    "attempt_id": attempt_id,
                    "state": target.value,
                    "submitted_at": (
                        at if target is PaperExecutionState.SUBMISSION_IN_PROGRESS else None
                    ),
                    "acknowledged_at": at if target in acknowledged_states else None,
                    "terminal_at": at if target in TERMINAL_PAPER_STATES else None,
                    "broker_order_id": broker_order_id,
                    "broker_status": broker_status,
                    "filled_quantity": filled_quantity,
                    "filled_avg_price": filled_avg_price,
                    "failure_code": failure_code,
                    "failure_detail": failure_detail,
                },
            )
        if not rows:
            raise ValueError(f"no paper execution attempt {attempt_id!r} exists")
        return _row_to_attempt(rows[0])

    def list_recent(self, limit: int) -> tuple[ExecutionAttempt, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive int")
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(
                _ATTEMPT_SELECT_RECENT, {"limit": limit}
            )
        return tuple(_row_to_attempt(row) for row in rows)


# ---------------------------------------------------------------------------
# Broker acknowledgements
# ---------------------------------------------------------------------------

_ACKNOWLEDGEMENT_INSERT = (
    "INSERT INTO public.paper_broker_acknowledgement "
    "(acknowledgement_id, attempt_id, sequence, kind, observed_at, http_status, "
    "broker_order_id, broker_status, client_order_id_echo, payload_digest, sanitized_payload) "
    "VALUES (:acknowledgement_id, :attempt_id, :sequence, :kind, :observed_at, :http_status, "
    ":broker_order_id, :broker_status, :client_order_id_echo, :payload_digest, "
    ":sanitized_payload) "
    "RETURNING acknowledgement_id, attempt_id, sequence, kind, observed_at, http_status, "
    "broker_order_id, broker_status, client_order_id_echo, payload_digest, sanitized_payload"
)

_ACKNOWLEDGEMENT_SELECT = (
    "SELECT acknowledgement_id, attempt_id, sequence, kind, observed_at, http_status, "
    "broker_order_id, broker_status, client_order_id_echo, payload_digest, sanitized_payload "
    "FROM public.paper_broker_acknowledgement WHERE attempt_id = :attempt_id "
    "ORDER BY sequence ASC"
)

_ACKNOWLEDGEMENT_MAX_SEQUENCE = (
    "SELECT COALESCE(MAX(sequence), 0) AS highest "
    "FROM public.paper_broker_acknowledgement WHERE attempt_id = :attempt_id"
)


def _row_to_acknowledgement(row: Mapping[str, Any]) -> BrokerAcknowledgement:
    return BrokerAcknowledgement(
        acknowledgement_id=_str(row, "acknowledgement_id"),
        attempt_id=_str(row, "attempt_id"),
        sequence=_int(row, "sequence"),
        kind=_str(row, "kind"),
        observed_at=_instant(row, "observed_at"),
        http_status=_int(row, "http_status"),
        broker_order_id=_optional_str(row, "broker_order_id"),
        broker_status=_optional_str(row, "broker_status"),
        client_order_id_echo=_optional_str(row, "client_order_id_echo"),
        payload_digest=_str(row, "payload_digest"),
        sanitized_payload=_str(row, "sanitized_payload"),
    )


class PostgresBrokerAcknowledgementRepository:
    """Append-only record of what the broker said, in the order it said it."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def append(self, acknowledgement: BrokerAcknowledgement) -> BrokerAcknowledgement:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _ACKNOWLEDGEMENT_INSERT,
                {
                    "acknowledgement_id": acknowledgement.acknowledgement_id,
                    "attempt_id": acknowledgement.attempt_id,
                    "sequence": acknowledgement.sequence,
                    "kind": acknowledgement.kind,
                    "observed_at": acknowledgement.observed_at,
                    "http_status": acknowledgement.http_status,
                    "broker_order_id": acknowledgement.broker_order_id,
                    "broker_status": acknowledgement.broker_status,
                    "client_order_id_echo": acknowledgement.client_order_id_echo,
                    "payload_digest": acknowledgement.payload_digest,
                    "sanitized_payload": acknowledgement.sanitized_payload,
                },
            )
        return _row_to_acknowledgement(rows[0])

    def for_attempt(self, attempt_id: str) -> tuple[BrokerAcknowledgement, ...]:
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(
                _ACKNOWLEDGEMENT_SELECT, {"attempt_id": attempt_id}
            )
        return tuple(_row_to_acknowledgement(row) for row in rows)

    def next_sequence(self, attempt_id: str) -> int:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_ACKNOWLEDGEMENT_MAX_SEQUENCE, {"attempt_id": attempt_id}))
        return _int(rows[0], "highest") + 1


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------

_EVENT_INSERT = (
    "INSERT INTO public.paper_execution_event "
    "(event_id, intent_governance_id, attempt_id, event_type, occurred_at, detail) "
    "VALUES (:event_id, :intent_governance_id, :attempt_id, :event_type, :occurred_at, :detail) "
    "RETURNING event_id, intent_governance_id, attempt_id, event_type, occurred_at, detail"
)

_EVENT_SELECT = (
    "SELECT event_id, intent_governance_id, attempt_id, event_type, occurred_at, detail "
    "FROM public.paper_execution_event WHERE intent_governance_id = :intent "
    "ORDER BY occurred_at ASC, event_id ASC"
)


def _row_to_event(row: Mapping[str, Any]) -> PaperExecutionEvent:
    return PaperExecutionEvent(
        event_id=_str(row, "event_id"),
        intent_governance_id=_str(row, "intent_governance_id"),
        attempt_id=_optional_str(row, "attempt_id"),
        event_type=_str(row, "event_type"),
        occurred_at=_instant(row, "occurred_at"),
        detail=_str(row, "detail"),
    )


class PostgresPaperExecutionEventRepository:
    """Append-only audit trail. Never the source of state."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def append(self, event: PaperExecutionEvent) -> PaperExecutionEvent:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _EVENT_INSERT,
                {
                    "event_id": event.event_id,
                    "intent_governance_id": event.intent_governance_id,
                    "attempt_id": event.attempt_id,
                    "event_type": event.event_type,
                    "occurred_at": event.occurred_at,
                    "detail": event.detail,
                },
            )
        return _row_to_event(rows[0])

    def for_intent(self, intent_governance_id: str) -> tuple[PaperExecutionEvent, ...]:
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(
                _EVENT_SELECT, {"intent": intent_governance_id}
            )
        return tuple(_row_to_event(row) for row in rows)


# ---------------------------------------------------------------------------
# Runtime composition
# ---------------------------------------------------------------------------


class PostgresPaperExecutionRuntime:
    """The seven MILESTONE-085 repositories over one caller-owned service.

    A separate class from `PostgresRepositoryRuntime` on purpose: that file is
    MILESTONE-084 production code and this milestone does not modify it. Both
    compose over the same `PostgresPersistenceService`, so a caller holding one
    service gets both sets of repositories under one transaction discipline.
    """

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    @property
    def execution_kill_switch(self) -> PostgresExecutionKillSwitchRepository:
        return PostgresExecutionKillSwitchRepository(self._service)

    @property
    def paper_account_snapshots(self) -> PostgresPaperAccountSnapshotRepository:
        return PostgresPaperAccountSnapshotRepository(self._service)

    @property
    def submission_previews(self) -> PostgresSubmissionPreviewRepository:
        return PostgresSubmissionPreviewRepository(self._service)

    @property
    def execution_authorizations(self) -> PostgresExecutionAuthorizationRepository:
        return PostgresExecutionAuthorizationRepository(self._service)

    @property
    def execution_attempts(self) -> PostgresExecutionAttemptRepository:
        return PostgresExecutionAttemptRepository(self._service)

    @property
    def broker_acknowledgements(self) -> PostgresBrokerAcknowledgementRepository:
        return PostgresBrokerAcknowledgementRepository(self._service)

    @property
    def paper_execution_events(self) -> PostgresPaperExecutionEventRepository:
        return PostgresPaperExecutionEventRepository(self._service)
