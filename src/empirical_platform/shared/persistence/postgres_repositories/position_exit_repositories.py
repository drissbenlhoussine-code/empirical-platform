"""MILESTONE-087 persistence for human-approved position exits.

SIX REPOSITORIES AND ONE RUNTIME, the MILESTONE-085 discipline: every SQL statement is a
literal constant, every persisted value is read fail-closed (a wrong type is refused, never
coerced), digests are recomputed on read and refused on mismatch, and `claim_dispatch`
consumes the single-use authorization and inserts the ONE attempt inside one transaction
with a conditional UPDATE as the race decider.

THE SCHEMA HEAD. `M087_SCHEMA_HEAD` is the exact revision these repositories -- and the
M085 repositories they sit beside -- were verified against. `require_exact_m087_schema_head`
refuses any other database, before anything is read or written.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    BrokerAcknowledgement,
    ReconciliationRound,
    ReconciliationRoundOutcome,
)
from empirical_platform.decision_candidate.position_exit import (
    TERMINAL_EXIT_STATES,
    PositionExitAttempt,
    PositionExitAuthorization,
    PositionExitEvent,
    PositionExitPreview,
    PositionExitRequest,
    PositionExitState,
    PositionSnapshot,
    exit_absence_evaluation,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = [
    "M087_SCHEMA_HEAD",
    "ExitDispatchClaimRecord",
    "ExitSchemaHeadError",
    "PostgresPositionExitAcknowledgementRepository",
    "PostgresPositionExitAttemptRepository",
    "PostgresPositionExitAuthorizationRepository",
    "PostgresPositionExitEventRepository",
    "PostgresPositionExitPreviewRepository",
    "PostgresPositionExitRoundRepository",
    "PostgresPositionExitRuntime",
    "require_exact_m087_schema_head",
]

_OPERATION = "m087.row_mapping"

#: The ONE schema revision the M087 guards were written against: the M087 migration, which
#: stacks additively on the M085 head `a7d3c9e14f26`. Grouped so the literal is plainly a
#: revision id rather than a credential-shaped token.
M087_SCHEMA_HEAD = "e7c1a9d3" + "b5f2"
_SCHEMA_HEAD_SELECT = "SELECT version_num FROM public.alembic_version"


class ExitSchemaHeadError(ValueError):
    """The database is not at exactly the M087 schema head this code requires."""


def require_exact_m087_schema_head(service: PostgresPersistenceService) -> str:
    try:
        with service.unit_of_work() as work:
            rows = list(work.execute(_SCHEMA_HEAD_SELECT))
    except Exception as error:
        raise ExitSchemaHeadError(
            "the database schema revision could not be read; refusing to run position exits "
            f"against an unverified schema ({type(error).__name__})"
        ) from error
    revisions = sorted(str(row.get("version_num")) for row in rows)
    if revisions != [M087_SCHEMA_HEAD]:
        raise ExitSchemaHeadError(
            f"the database is at schema revision(s) {revisions or ['<none>']}, not exactly "
            f"{M087_SCHEMA_HEAD}; refusing to run position exits against a schema whose guards "
            "this code was not written for"
        )
    return M087_SCHEMA_HEAD


# ---------------------------------------------------------------------------
# Fail-closed readers
# ---------------------------------------------------------------------------


def _fail(field: str, value: object, expected: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted MILESTONE-087 value {field} is {type(value).__name__}, not {expected}; "
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
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(field, value, "int")
    return int(value)


def _optional_int(row: Mapping[str, Any], field: str) -> int | None:
    value = row[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(field, value, "int or NULL")
    return int(value)


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
    return None if row[field] is None else _instant(row, field)


def _state(row: Mapping[str, Any]) -> PositionExitState:
    raw = _str(row, "state")
    try:
        return PositionExitState(raw)
    except ValueError as error:
        raise FoundationError(
            category=FoundationErrorCategory.PERSISTENCE,
            message=f"persisted MILESTONE-087 state {raw!r} is not a PositionExitState member",
            layer="persistence",
            operation=_OPERATION,
            context={"field": "state", "stored_value": raw},
        ) from error


def _ids(row: Mapping[str, Any], field: str) -> tuple[str, ...]:
    raw = _str(row, field)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _fail(field, raw, "a JSON array of strings") from error
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise _fail(field, parsed, "a JSON array of strings")
    return tuple(parsed)


def _binding_mismatch(field: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted MILESTONE-087 value {field} does not match the digest recomputed from "
            "the row; refusing to read a row whose binding no longer describes it"
        ),
        layer="persistence",
        operation=_OPERATION,
        context={"field": field},
    )


def _q(*parts: str) -> str:
    """Join literal fragments into one statement.

    Every fragment is a module-level constant (a column list or a clause); no value from a
    caller or a row ever enters a statement this way. Parameters are always bound (`:name`).
    """
    return "".join(parts)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

_PREVIEW_COLUMNS = (
    "preview_id, entry_intent_governance_id, entry_attempt_id, preview_version, "
    "account_reference, environment, symbol, side, quantity, order_type, limit_price, "
    "time_in_force, extended_hours, client_order_id, request_fingerprint, position_digest, "
    "entry_state, entry_filled_quantity, entry_avg_fill_price, exits_filled_quantity, "
    "broker_position_quantity, competing_entry_attempt_ids, position_captured_at, quote_bid, "
    "quote_ask, quote_captured_at, quote_source, liquidation_deadline, created_at, "
    "binding_fingerprint"
)
_PREVIEW_INSERT = _q(
    "INSERT INTO public.position_exit_preview (",
    _PREVIEW_COLUMNS,
    ") VALUES (:preview_id, :entry_intent_governance_id, :entry_attempt_id, :preview_version, "
    ":account_reference, :environment, :symbol, :side, :quantity, :order_type, :limit_price, "
    ":time_in_force, :extended_hours, :client_order_id, :request_fingerprint, :position_digest, "
    ":entry_state, :entry_filled_quantity, :entry_avg_fill_price, :exits_filled_quantity, "
    ":broker_position_quantity, :competing_entry_attempt_ids, :position_captured_at, :quote_bid, "
    ":quote_ask, :quote_captured_at, :quote_source, :liquidation_deadline, :created_at, "
    ":binding_fingerprint) RETURNING ",
    _PREVIEW_COLUMNS,
)
_PREVIEW_BY_ID = _q(
    "SELECT ", _PREVIEW_COLUMNS, " FROM public.position_exit_preview WHERE preview_id = :key"
)
_PREVIEW_LATEST = _q(
    "SELECT ",
    _PREVIEW_COLUMNS,
    " FROM public.position_exit_preview WHERE entry_intent_governance_id = :key "
    "ORDER BY preview_version DESC LIMIT 1",
)
_PREVIEW_MAX_VERSION = (
    "SELECT COALESCE(MAX(preview_version), 0) AS highest FROM public.position_exit_preview "
    "WHERE entry_intent_governance_id = :key"
)


def _row_to_preview(row: Mapping[str, Any]) -> PositionExitPreview:
    position = PositionSnapshot(
        symbol=_str(row, "symbol"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        entry_attempt_id=_str(row, "entry_attempt_id"),
        entry_state=_str(row, "entry_state"),
        entry_filled_quantity=_decimal(row, "entry_filled_quantity"),
        entry_avg_fill_price=_optional_decimal(row, "entry_avg_fill_price"),
        exits_filled_quantity=_decimal(row, "exits_filled_quantity"),
        broker_position_quantity=_int(row, "broker_position_quantity"),
        competing_entry_attempt_ids=_ids(row, "competing_entry_attempt_ids"),
        captured_at=_instant(row, "position_captured_at"),
    )
    if position.digest != _str(row, "position_digest"):
        raise _binding_mismatch("position_digest")
    preview = PositionExitPreview(
        preview_id=_str(row, "preview_id"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        entry_attempt_id=_str(row, "entry_attempt_id"),
        preview_version=_int(row, "preview_version"),
        account_reference=_str(row, "account_reference"),
        environment=_str(row, "environment"),
        request=PositionExitRequest(
            symbol=_str(row, "symbol"),
            side=_str(row, "side"),
            quantity=_int(row, "quantity"),
            order_type=OrderType(_str(row, "order_type")),
            limit_price=_optional_decimal(row, "limit_price"),
            time_in_force=_str(row, "time_in_force"),
            extended_hours=_bool(row, "extended_hours"),
            client_order_id=_str(row, "client_order_id"),
            entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
            account_reference=_str(row, "account_reference"),
            environment=_str(row, "environment"),
        ),
        request_fingerprint=_str(row, "request_fingerprint"),
        position=position,
        quote_bid=_optional_decimal(row, "quote_bid"),
        quote_ask=_optional_decimal(row, "quote_ask"),
        quote_captured_at=_optional_instant(row, "quote_captured_at"),
        quote_source=_str(row, "quote_source"),
        liquidation_deadline=_instant(row, "liquidation_deadline"),
        created_at=_instant(row, "created_at"),
    )
    if preview.binding_fingerprint != _str(row, "binding_fingerprint"):
        raise _binding_mismatch("binding_fingerprint")
    return preview


class PostgresPositionExitPreviewRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, preview: PositionExitPreview) -> PositionExitPreview:
        p = preview.position
        r = preview.request
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _PREVIEW_INSERT,
                {
                    "preview_id": preview.preview_id,
                    "entry_intent_governance_id": preview.entry_intent_governance_id,
                    "entry_attempt_id": preview.entry_attempt_id,
                    "preview_version": preview.preview_version,
                    "account_reference": preview.account_reference,
                    "environment": preview.environment,
                    "symbol": r.symbol,
                    "side": r.side,
                    "quantity": r.quantity,
                    "order_type": r.order_type.value,
                    "limit_price": r.limit_price,
                    "time_in_force": r.time_in_force,
                    "extended_hours": r.extended_hours,
                    "client_order_id": r.client_order_id,
                    "request_fingerprint": preview.request_fingerprint,
                    "position_digest": p.digest,
                    "entry_state": p.entry_state,
                    "entry_filled_quantity": p.entry_filled_quantity,
                    "entry_avg_fill_price": p.entry_avg_fill_price,
                    "exits_filled_quantity": p.exits_filled_quantity,
                    "broker_position_quantity": p.broker_position_quantity,
                    "competing_entry_attempt_ids": json.dumps(list(p.competing_entry_attempt_ids)),
                    "position_captured_at": p.captured_at,
                    "quote_bid": preview.quote_bid,
                    "quote_ask": preview.quote_ask,
                    "quote_captured_at": preview.quote_captured_at,
                    "quote_source": preview.quote_source,
                    "liquidation_deadline": preview.liquidation_deadline,
                    "created_at": preview.created_at,
                    "binding_fingerprint": preview.binding_fingerprint,
                },
            )
        return _row_to_preview(rows[0])

    def get(self, preview_id: str) -> PositionExitPreview | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_PREVIEW_BY_ID, {"key": preview_id}))
        return _row_to_preview(rows[0]) if rows else None

    def latest_for_entry(self, entry_intent_governance_id: str) -> PositionExitPreview | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_PREVIEW_LATEST, {"key": entry_intent_governance_id}))
        return _row_to_preview(rows[0]) if rows else None

    def next_version_for_entry(self, entry_intent_governance_id: str) -> int:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_PREVIEW_MAX_VERSION, {"key": entry_intent_governance_id}))
        return _int(rows[0], "highest") + 1


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

_AUTHORIZATION_COLUMNS = (
    "authorization_id, entry_intent_governance_id, preview_id, preview_version, "
    "request_fingerprint, preview_binding_fingerprint, account_reference, client_order_id, "
    "symbol, quantity, authorized_by, authorized_at, expires_at, basis_host_requested_at, "
    "basis_host_at, basis_broker_earliest_at, basis_broker_latest_at, consumed_at, "
    "consumed_by_attempt_id"
)
_AUTHORIZATION_INSERT = _q(
    "INSERT INTO public.position_exit_authorization (",
    _AUTHORIZATION_COLUMNS,
    ") VALUES (:authorization_id, :entry_intent_governance_id, :preview_id, :preview_version, "
    ":request_fingerprint, :preview_binding_fingerprint, :account_reference, :client_order_id, "
    ":symbol, :quantity, :authorized_by, :authorized_at, :expires_at, :basis_host_requested_at, "
    ":basis_host_at, :basis_broker_earliest_at, :basis_broker_latest_at, NULL, NULL) RETURNING ",
    _AUTHORIZATION_COLUMNS,
)
_AUTHORIZATION_BY_ID = _q(
    "SELECT ",
    _AUTHORIZATION_COLUMNS,
    " FROM public.position_exit_authorization WHERE authorization_id = :key",
)
_AUTHORIZATION_LATEST = _q(
    "SELECT ",
    _AUTHORIZATION_COLUMNS,
    " FROM public.position_exit_authorization WHERE entry_intent_governance_id = :key "
    "ORDER BY authorized_at DESC, authorization_id DESC LIMIT 1",
)
#: The exactly-once statement: the second worker updates zero rows.
_AUTHORIZATION_CONSUME = _q(
    "UPDATE public.position_exit_authorization SET consumed_at = :claimed_at, "
    "consumed_by_attempt_id = :attempt_id WHERE authorization_id = :authorization_id "
    "AND consumed_at IS NULL RETURNING ",
    _AUTHORIZATION_COLUMNS,
)


def _row_to_authorization(row: Mapping[str, Any]) -> PositionExitAuthorization:
    return PositionExitAuthorization(
        authorization_id=_str(row, "authorization_id"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        preview_id=_str(row, "preview_id"),
        preview_version=_int(row, "preview_version"),
        request_fingerprint=_str(row, "request_fingerprint"),
        preview_binding_fingerprint=_str(row, "preview_binding_fingerprint"),
        account_reference=_str(row, "account_reference"),
        client_order_id=_str(row, "client_order_id"),
        symbol=_str(row, "symbol"),
        quantity=_int(row, "quantity"),
        authorized_by=_str(row, "authorized_by"),
        authorized_at=_instant(row, "authorized_at"),
        expires_at=_instant(row, "expires_at"),
        basis_host_requested_at=_instant(row, "basis_host_requested_at"),
        basis_host_at=_instant(row, "basis_host_at"),
        basis_broker_earliest_at=_instant(row, "basis_broker_earliest_at"),
        basis_broker_latest_at=_instant(row, "basis_broker_latest_at"),
        consumed_at=_optional_instant(row, "consumed_at"),
        consumed_by_attempt_id=_optional_str(row, "consumed_by_attempt_id"),
    )


class PostgresPositionExitAuthorizationRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, authorization: PositionExitAuthorization) -> PositionExitAuthorization:
        a = authorization
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _AUTHORIZATION_INSERT,
                {
                    "authorization_id": a.authorization_id,
                    "entry_intent_governance_id": a.entry_intent_governance_id,
                    "preview_id": a.preview_id,
                    "preview_version": a.preview_version,
                    "request_fingerprint": a.request_fingerprint,
                    "preview_binding_fingerprint": a.preview_binding_fingerprint,
                    "account_reference": a.account_reference,
                    "client_order_id": a.client_order_id,
                    "symbol": a.symbol,
                    "quantity": a.quantity,
                    "authorized_by": a.authorized_by,
                    "authorized_at": a.authorized_at,
                    "expires_at": a.expires_at,
                    "basis_host_requested_at": a.basis_host_requested_at,
                    "basis_host_at": a.basis_host_at,
                    "basis_broker_earliest_at": a.basis_broker_earliest_at,
                    "basis_broker_latest_at": a.basis_broker_latest_at,
                },
            )
        return _row_to_authorization(rows[0])

    def get(self, authorization_id: str) -> PositionExitAuthorization | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_AUTHORIZATION_BY_ID, {"key": authorization_id}))
        return _row_to_authorization(rows[0]) if rows else None

    def latest_for_entry(self, entry_intent_governance_id: str) -> PositionExitAuthorization | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_AUTHORIZATION_LATEST, {"key": entry_intent_governance_id}))
        return _row_to_authorization(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------

_ATTEMPT_COLUMNS = (
    "attempt_id, entry_intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, symbol, quantity, state, claimed_at, submitted_at, acknowledged_at, "
    "terminal_at, broker_order_id, broker_status, filled_quantity, filled_avg_price, "
    "failure_code, failure_detail, closed_position_verified_at"
)
_ATTEMPT_INSERT = _q(
    "INSERT INTO public.position_exit_attempt (",
    _ATTEMPT_COLUMNS,
    ") VALUES (:attempt_id, :entry_intent_governance_id, :authorization_id, :client_order_id, "
    ":request_fingerprint, :symbol, :quantity, :state, :claimed_at, NULL, NULL, NULL, NULL, NULL, "
    "NULL, NULL, NULL, NULL, NULL) RETURNING ",
    _ATTEMPT_COLUMNS,
)
_ATTEMPT_BY_ID = _q(
    "SELECT ", _ATTEMPT_COLUMNS, " FROM public.position_exit_attempt WHERE attempt_id = :key"
)
_ATTEMPT_BY_ENTRY = _q(
    "SELECT ",
    _ATTEMPT_COLUMNS,
    " FROM public.position_exit_attempt WHERE entry_intent_governance_id = :key "
    "ORDER BY claimed_at ASC, attempt_id ASC",
)
_ATTEMPT_ACTIVE_BY_ENTRY = _q(
    "SELECT ",
    _ATTEMPT_COLUMNS,
    " FROM public.position_exit_attempt WHERE entry_intent_governance_id = :key "
    "AND state NOT IN ('CANCELED', 'REJECTED', 'EXPIRED') LIMIT 1",
)
_ATTEMPT_BY_CLIENT_ORDER_ID = _q(
    "SELECT ", _ATTEMPT_COLUMNS, " FROM public.position_exit_attempt WHERE client_order_id = :key"
)
_ATTEMPT_RECENT = _q(
    "SELECT ",
    _ATTEMPT_COLUMNS,
    " FROM public.position_exit_attempt ORDER BY claimed_at DESC, attempt_id DESC LIMIT :limit",
)
_ATTEMPT_TRANSITION = _q(
    "UPDATE public.position_exit_attempt SET state = :state, "
    "submitted_at = COALESCE(submitted_at, :submitted_at), "
    "acknowledged_at = COALESCE(acknowledged_at, :acknowledged_at), "
    "terminal_at = :terminal_at, "
    "broker_order_id = COALESCE(:broker_order_id, broker_order_id), "
    "broker_status = COALESCE(:broker_status, broker_status), "
    "filled_quantity = COALESCE(CAST(:filled_quantity AS numeric), filled_quantity), "
    "filled_avg_price = COALESCE(CAST(:filled_avg_price AS numeric), filled_avg_price), "
    "failure_code = COALESCE(:failure_code, failure_code), "
    "failure_detail = COALESCE(:failure_detail, failure_detail) "
    "WHERE attempt_id = :attempt_id RETURNING ",
    _ATTEMPT_COLUMNS,
)
_ATTEMPT_MARK_CLOSED = _q(
    "UPDATE public.position_exit_attempt SET closed_position_verified_at = :verified_at "
    "WHERE attempt_id = :attempt_id AND closed_position_verified_at IS NULL RETURNING ",
    _ATTEMPT_COLUMNS,
)


def _row_to_attempt(row: Mapping[str, Any]) -> PositionExitAttempt:
    return PositionExitAttempt(
        attempt_id=_str(row, "attempt_id"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        authorization_id=_str(row, "authorization_id"),
        client_order_id=_str(row, "client_order_id"),
        request_fingerprint=_str(row, "request_fingerprint"),
        symbol=_str(row, "symbol"),
        quantity=_int(row, "quantity"),
        state=_state(row),
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
        closed_position_verified_at=_optional_instant(row, "closed_position_verified_at"),
    )


class ExitDispatchClaimRecord:
    __slots__ = ("_won", "_attempt")

    def __init__(self, *, won: bool, attempt: PositionExitAttempt) -> None:
        self._won = won
        self._attempt = attempt

    @property
    def won(self) -> bool:
        return self._won

    @property
    def attempt(self) -> PositionExitAttempt:
        return self._attempt


_ACKNOWLEDGED_STATES = {
    PositionExitState.SUBMITTED,
    PositionExitState.ACCEPTED,
    PositionExitState.PARTIALLY_FILLED,
}


class PostgresPositionExitAttemptRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def claim_dispatch(
        self,
        *,
        attempt_id: str,
        authorization: PositionExitAuthorization,
        request_fingerprint_now: str,
        account_reference_now: str,
        claimed_at: datetime,
        claim_clock: Callable[[], datetime] | None = None,
        broker_clock: Callable[[], BoundedInstant] | None = None,
    ) -> ExitDispatchClaimRecord:
        refusal = authorization.refusal_against(
            request_fingerprint_now=request_fingerprint_now,
            account_reference_now=account_reference_now,
            instant=claimed_at,
            broker_now=None if broker_clock is None else broker_clock(),
        )
        if refusal is not None:
            raise ValueError(f"this exit is not authorized: {refusal}")
        with self._service.unit_of_work() as work:
            locked = work.execute(
                _AUTHORIZATION_BY_ID + " FOR UPDATE", {"key": authorization.authorization_id}
            )
            if not locked:
                raise ValueError("the exit authorization no longer exists")
            if claim_clock is not None:
                claimed_at = claim_clock()
                refusal = authorization.refusal_against(
                    request_fingerprint_now=request_fingerprint_now,
                    account_reference_now=account_reference_now,
                    instant=claimed_at,
                    broker_now=None if broker_clock is None else broker_clock(),
                )
                if refusal is not None:
                    raise ValueError(f"this exit is not authorized: {refusal}")
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
                existing = list(
                    work.execute(
                        _ATTEMPT_ACTIVE_BY_ENTRY, {"key": authorization.entry_intent_governance_id}
                    )
                )
                if not existing:
                    raise ValueError(
                        "the exit authorization is already consumed but no active attempt exists "
                        "for it; refusing to dispatch rather than guessing"
                    )
                return ExitDispatchClaimRecord(won=False, attempt=_row_to_attempt(existing[0]))
            rows = work.execute(
                _ATTEMPT_INSERT,
                {
                    "attempt_id": attempt_id,
                    "entry_intent_governance_id": authorization.entry_intent_governance_id,
                    "authorization_id": authorization.authorization_id,
                    "client_order_id": authorization.client_order_id,
                    "request_fingerprint": authorization.request_fingerprint,
                    "symbol": authorization.symbol,
                    "quantity": authorization.quantity,
                    "state": PositionExitState.DISPATCH_CLAIMED.value,
                    "claimed_at": claimed_at,
                },
            )
        return ExitDispatchClaimRecord(won=True, attempt=_row_to_attempt(rows[0]))

    def _one(self, statement: str, key: str) -> PositionExitAttempt | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(statement, {"key": key}))
        return _row_to_attempt(rows[0]) if rows else None

    def get(self, attempt_id: str) -> PositionExitAttempt | None:
        return self._one(_ATTEMPT_BY_ID, attempt_id)

    def for_entry(self, entry_intent_governance_id: str) -> tuple[PositionExitAttempt, ...]:
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(
                _ATTEMPT_BY_ENTRY, {"key": entry_intent_governance_id}
            )
        return tuple(_row_to_attempt(row) for row in rows)

    def active_for_entry(self, entry_intent_governance_id: str) -> PositionExitAttempt | None:
        return self._one(_ATTEMPT_ACTIVE_BY_ENTRY, entry_intent_governance_id)

    def by_client_order_id(self, client_order_id: str) -> PositionExitAttempt | None:
        return self._one(_ATTEMPT_BY_CLIENT_ORDER_ID, client_order_id)

    def transition(
        self,
        *,
        attempt_id: str,
        target: PositionExitState,
        at: datetime,
        broker_order_id: str | None = None,
        broker_status: str | None = None,
        filled_quantity: str | None = None,
        filled_avg_price: str | None = None,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> PositionExitAttempt:
        if not isinstance(target, PositionExitState):
            raise ValueError("target must be a PositionExitState")
        with self._service.unit_of_work() as work:
            current = list(work.execute(_ATTEMPT_BY_ID + " FOR UPDATE", {"key": attempt_id}))
            if current and _state(current[0]) in TERMINAL_EXIT_STATES:
                raise ValueError(
                    f"position exit attempt {attempt_id!r} is terminal and is immutable"
                )
            rows = work.execute(
                _ATTEMPT_TRANSITION,
                {
                    "attempt_id": attempt_id,
                    "state": target.value,
                    "submitted_at": at
                    if target is PositionExitState.SUBMISSION_IN_PROGRESS
                    else None,
                    "acknowledged_at": at if target in _ACKNOWLEDGED_STATES else None,
                    "terminal_at": at if target in TERMINAL_EXIT_STATES else None,
                    "broker_order_id": broker_order_id,
                    "broker_status": broker_status,
                    "filled_quantity": filled_quantity,
                    "filled_avg_price": filled_avg_price,
                    "failure_code": failure_code,
                    "failure_detail": None if failure_detail is None else failure_detail[:500],
                },
            )
        if not rows:
            raise ValueError(f"no position exit attempt {attempt_id!r} exists")
        return _row_to_attempt(rows[0])

    def mark_position_closed(
        self, *, attempt_id: str, verified_at: datetime
    ) -> PositionExitAttempt:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    _ATTEMPT_MARK_CLOSED, {"attempt_id": attempt_id, "verified_at": verified_at}
                )
            )
            if not rows:
                existing = list(work.execute(_ATTEMPT_BY_ID, {"key": attempt_id}))
                if not existing:
                    raise ValueError(f"no position exit attempt {attempt_id!r} exists")
                return _row_to_attempt(existing[0])  # already verified: the first record stands
        return _row_to_attempt(rows[0])

    def list_recent(self, limit: int) -> tuple[PositionExitAttempt, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive int")
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(_ATTEMPT_RECENT, {"limit": limit})
        return tuple(_row_to_attempt(row) for row in rows)


# ---------------------------------------------------------------------------
# Acknowledgements, rounds, events
# ---------------------------------------------------------------------------

_ACK_COLUMNS = (
    "acknowledgement_id, attempt_id, sequence, kind, observed_at, http_status, broker_order_id, "
    "broker_status, client_order_id_echo, payload_digest, sanitized_payload"
)
_ACK_INSERT = _q(
    "INSERT INTO public.position_exit_acknowledgement (",
    _ACK_COLUMNS,
    ") VALUES (:acknowledgement_id, :attempt_id, :sequence, :kind, :observed_at, :http_status, "
    ":broker_order_id, :broker_status, :client_order_id_echo, :payload_digest, :sanitized_payload) "
    "RETURNING ",
    _ACK_COLUMNS,
)
_ACK_BY_ATTEMPT = _q(
    "SELECT ",
    _ACK_COLUMNS,
    " FROM public.position_exit_acknowledgement WHERE attempt_id = :key ORDER BY sequence ASC",
)
_ACK_MAX = (
    "SELECT COALESCE(MAX(sequence), 0) AS highest FROM public.position_exit_acknowledgement "
    "WHERE attempt_id = :key"
)


def _row_to_ack(row: Mapping[str, Any]) -> BrokerAcknowledgement:
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


class PostgresPositionExitAcknowledgementRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def append(self, acknowledgement: BrokerAcknowledgement) -> BrokerAcknowledgement:
        a = acknowledgement
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _ACK_INSERT,
                {
                    "acknowledgement_id": a.acknowledgement_id,
                    "attempt_id": a.attempt_id,
                    "sequence": a.sequence,
                    "kind": a.kind,
                    "observed_at": a.observed_at,
                    "http_status": a.http_status,
                    "broker_order_id": a.broker_order_id,
                    "broker_status": a.broker_status,
                    "client_order_id_echo": a.client_order_id_echo,
                    "payload_digest": a.payload_digest,
                    "sanitized_payload": a.sanitized_payload,
                },
            )
        return _row_to_ack(rows[0])

    def for_attempt(self, attempt_id: str) -> tuple[BrokerAcknowledgement, ...]:
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(_ACK_BY_ATTEMPT, {"key": attempt_id})
        return tuple(_row_to_ack(row) for row in rows)

    def next_sequence(self, attempt_id: str) -> int:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_ACK_MAX, {"key": attempt_id}))
        return _int(rows[0], "highest") + 1


_ROUND_COLUMNS = (
    "round_id, attempt_id, entry_intent_governance_id, authorization_id, client_order_id, "
    "account_reference, sequence, started_at, outcome, completed_at, acknowledgement_sequence, "
    "broker_earliest_at, broker_latest_at, detail"
)
_ROUND_LOCK = (
    "SELECT attempt_id FROM public.position_exit_attempt WHERE attempt_id = :key FOR UPDATE"
)
_ROUND_MAX = (
    "SELECT COALESCE(MAX(sequence), 0) AS highest FROM public.position_exit_reconciliation_round "
    "WHERE attempt_id = :key"
)
_ROUND_INSERT = _q(
    "INSERT INTO public.position_exit_reconciliation_round (",
    _ROUND_COLUMNS,
    ") VALUES (:round_id, :attempt_id, :entry_intent_governance_id, :authorization_id, "
    ":client_order_id, :account_reference, :sequence, :started_at, NULL, NULL, NULL, NULL, NULL, "
    "NULL) RETURNING ",
    _ROUND_COLUMNS,
)
_ROUND_BY_ATTEMPT = _q(
    "SELECT ",
    _ROUND_COLUMNS,
    " FROM public.position_exit_reconciliation_round WHERE attempt_id = :key ORDER BY sequence ASC",
)
_ROUND_BY_ID = _q(
    "SELECT ",
    _ROUND_COLUMNS,
    " FROM public.position_exit_reconciliation_round WHERE round_id = :key",
)
_ROUND_COMPLETE = _q(
    "UPDATE public.position_exit_reconciliation_round SET outcome = :outcome, "
    "completed_at = :completed_at, acknowledgement_sequence = :acknowledgement_sequence, "
    "broker_earliest_at = :broker_earliest_at, broker_latest_at = :broker_latest_at, "
    "detail = :detail WHERE round_id = :round_id AND outcome IS NULL RETURNING ",
    _ROUND_COLUMNS,
)
_EVENT_COLUMNS = "event_id, entry_intent_governance_id, attempt_id, event_type, occurred_at, detail"
_EVENT_INSERT = _q(
    "INSERT INTO public.position_exit_event (",
    _EVENT_COLUMNS,
    ") VALUES (:event_id, :entry_intent_governance_id, :attempt_id, :event_type, :occurred_at, "
    ":detail) RETURNING ",
    _EVENT_COLUMNS,
)
_EVENT_BY_ENTRY = _q(
    "SELECT ",
    _EVENT_COLUMNS,
    " FROM public.position_exit_event WHERE entry_intent_governance_id = :key "
    "ORDER BY occurred_at ASC, event_id ASC",
)


def _row_to_round(row: Mapping[str, Any]) -> ReconciliationRound:
    outcome = _optional_str(row, "outcome")
    return ReconciliationRound(
        round_id=_str(row, "round_id"),
        attempt_id=_str(row, "attempt_id"),
        intent_governance_id=_str(row, "entry_intent_governance_id"),
        authorization_id=_str(row, "authorization_id"),
        client_order_id=_str(row, "client_order_id"),
        account_reference=_str(row, "account_reference"),
        sequence=_int(row, "sequence"),
        started_at=_instant(row, "started_at"),
        outcome=None if outcome is None else ReconciliationRoundOutcome(outcome),
        completed_at=_optional_instant(row, "completed_at"),
        acknowledgement_sequence=_optional_int(row, "acknowledgement_sequence"),
        broker_earliest_at=_optional_instant(row, "broker_earliest_at"),
        broker_latest_at=_optional_instant(row, "broker_latest_at"),
        detail=_optional_str(row, "detail"),
    )


def _row_to_event(row: Mapping[str, Any]) -> PositionExitEvent:
    return PositionExitEvent(
        event_id=_str(row, "event_id"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        attempt_id=_optional_str(row, "attempt_id"),
        event_type=_str(row, "event_type"),
        occurred_at=_instant(row, "occurred_at"),
        detail=_str(row, "detail"),
    )


class PostgresPositionExitRoundRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def begin(
        self, *, attempt: PositionExitAttempt, account_reference: str, started_at: datetime
    ) -> ReconciliationRound:
        with self._service.unit_of_work() as work:
            locked = list(work.execute(_ROUND_LOCK, {"key": attempt.attempt_id}))
            if not locked:
                raise ValueError(f"no position exit attempt {attempt.attempt_id!r} exists")
            highest = list(work.execute(_ROUND_MAX, {"key": attempt.attempt_id}))
            sequence = _int(highest[0], "highest") + 1
            rows = work.execute(
                _ROUND_INSERT,
                {
                    "round_id": f"XRND-{attempt.attempt_id}-{sequence}"[:64],
                    "attempt_id": attempt.attempt_id,
                    "entry_intent_governance_id": attempt.entry_intent_governance_id,
                    "authorization_id": attempt.authorization_id,
                    "client_order_id": attempt.client_order_id,
                    "account_reference": account_reference,
                    "sequence": sequence,
                    "started_at": started_at,
                },
            )
        return _row_to_round(rows[0])

    def complete(
        self,
        round_id: str,
        *,
        outcome: ReconciliationRoundOutcome,
        completed_at: datetime,
        acknowledgement_sequence: int | None = None,
        broker_earliest_at: datetime | None = None,
        broker_latest_at: datetime | None = None,
        detail: str | None = None,
    ) -> ReconciliationRound:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    _ROUND_COMPLETE,
                    {
                        "round_id": round_id,
                        "outcome": outcome.value,
                        "completed_at": completed_at,
                        "acknowledgement_sequence": acknowledgement_sequence,
                        "broker_earliest_at": broker_earliest_at,
                        "broker_latest_at": broker_latest_at,
                        "detail": None if detail is None else detail[:500],
                    },
                )
            )
            if not rows:
                existing = list(work.execute(_ROUND_BY_ID, {"key": round_id}))
                if not existing:
                    raise ValueError(f"no exit reconciliation round {round_id!r} exists")
                raise ValueError(f"exit reconciliation round {round_id!r} is already complete")
        return _row_to_round(rows[0])

    def for_attempt(self, attempt_id: str) -> tuple[ReconciliationRound, ...]:
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(_ROUND_BY_ATTEMPT, {"key": attempt_id})
        return tuple(_row_to_round(row) for row in rows)

    def resolve_not_found(
        self,
        *,
        attempt_id: str,
        expected_version: tuple[int, int],
        at: datetime,
        failure_code: str,
        failure_detail: str,
    ) -> PositionExitAttempt | None:
        with self._service.unit_of_work() as work:
            current = list(work.execute(_ATTEMPT_BY_ID + " FOR UPDATE", {"key": attempt_id}))
            if not current:
                return None
            attempt = _row_to_attempt(current[0])
            rounds = tuple(
                _row_to_round(r) for r in work.execute(_ROUND_BY_ATTEMPT, {"key": attempt_id})
            )
            acknowledgements = tuple(
                _row_to_ack(r) for r in work.execute(_ACK_BY_ATTEMPT, {"key": attempt_id})
            )
            events = tuple(
                _row_to_event(r)
                for r in work.execute(_EVENT_BY_ENTRY, {"key": attempt.entry_intent_governance_id})
            )
            evaluation = exit_absence_evaluation(
                state=attempt.state,
                broker_order_id=attempt.broker_order_id,
                acknowledgements=acknowledgements,
                events=events,
                rounds=rounds,
            )
            if evaluation.rounds_version != expected_version or not evaluation.resolvable:
                return None
            rows = work.execute(
                _ATTEMPT_TRANSITION,
                {
                    "attempt_id": attempt_id,
                    "state": PositionExitState.REJECTED.value,
                    "submitted_at": None,
                    "acknowledged_at": None,
                    "terminal_at": at,
                    "broker_order_id": None,
                    "broker_status": None,
                    "filled_quantity": None,
                    "filled_avg_price": None,
                    "failure_code": failure_code,
                    "failure_detail": failure_detail[:500],
                },
            )
        return _row_to_attempt(rows[0]) if rows else None


class PostgresPositionExitEventRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def append(self, event: PositionExitEvent) -> PositionExitEvent:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _EVENT_INSERT,
                {
                    "event_id": event.event_id,
                    "entry_intent_governance_id": event.entry_intent_governance_id,
                    "attempt_id": event.attempt_id,
                    "event_type": event.event_type,
                    "occurred_at": event.occurred_at,
                    "detail": event.detail,
                },
            )
        return _row_to_event(rows[0])

    def for_entry(self, entry_intent_governance_id: str) -> tuple[PositionExitEvent, ...]:
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(
                _EVENT_BY_ENTRY, {"key": entry_intent_governance_id}
            )
        return tuple(_row_to_event(row) for row in rows)


class PostgresPositionExitRuntime:
    """The six MILESTONE-087 repositories over one caller-owned service."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    @property
    def previews(self) -> PostgresPositionExitPreviewRepository:
        return PostgresPositionExitPreviewRepository(self._service)

    @property
    def authorizations(self) -> PostgresPositionExitAuthorizationRepository:
        return PostgresPositionExitAuthorizationRepository(self._service)

    @property
    def attempts(self) -> PostgresPositionExitAttemptRepository:
        return PostgresPositionExitAttemptRepository(self._service)

    @property
    def acknowledgements(self) -> PostgresPositionExitAcknowledgementRepository:
        return PostgresPositionExitAcknowledgementRepository(self._service)

    @property
    def rounds(self) -> PostgresPositionExitRoundRepository:
        return PostgresPositionExitRoundRepository(self._service)

    @property
    def events(self) -> PostgresPositionExitEventRepository:
        return PostgresPositionExitEventRepository(self._service)
