"""RELEASE v1 persistence for `ExternalPositionClosure` -- Store C.

THE M085 DISCIPLINE, UNCHANGED: every SQL statement is a literal constant, and every
persisted value is read fail-closed (a wrong type is refused, never coerced). The table's
own UNIQUE constraint on `entry_intent_governance_id` is the exactly-once primitive here --
mirroring `ApprovedPlanRepository`/`PositionExitAttemptRepository` elsewhere in this
codebase -- so a concurrent caller can never persist two closure records for one entry even
if it raced `RecordExternalPositionClosureHandler`'s own `for_entry` check.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError

from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
)
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = [
    "ExternalPositionClosureAlreadyExistsError",
    "PostgresExternalPositionClosureRepository",
]

_OPERATION = "v1.external_position_closure.row_mapping"


class ExternalPositionClosureAlreadyExistsError(ValueError):
    """`save` was asked to insert a second closure record for an entry that already has one."""


def _fail(field: str, value: object, expected: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted external_position_closure value {field} is {type(value).__name__}, "
            f"not {expected}; refusing to coerce a malformed stored value"
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


def _decimal(row: Mapping[str, Any], field: str) -> Decimal:
    value = row[field]
    if not isinstance(value, Decimal):
        raise _fail(field, value, "Decimal")
    return value


def _instant(row: Mapping[str, Any], field: str) -> datetime:
    value = row[field]
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _fail(field, value, "timezone-aware datetime")
    return value


def _row_to_closure(row: Mapping[str, Any]) -> ExternalPositionClosure:
    return ExternalPositionClosure(
        closure_id=_str(row, "closure_id"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        symbol=_str(row, "symbol"),
        quantity=row["quantity"],
        broker_order_id=_str(row, "broker_order_id"),
        client_order_id=_str(row, "client_order_id"),
        filled_avg_price=_decimal(row, "filled_avg_price"),
        recorded_by=_str(row, "recorded_by"),
        recorded_at=_instant(row, "recorded_at"),
    )


#: Every statement below spells out its own column list as a literal, never built by
#: interpolating a shared variable -- the M085 discipline (see `approved_plan_repositories.
#: py`'s own module docstring): `ruff`'s S608 exists to catch exactly the shortcut of
#: concatenating a column-list variable into SQL text, and this module carries zero
#: suppressions for it.
_INSERT = (
    "INSERT INTO public.external_position_closure (closure_id, entry_intent_governance_id, "
    "symbol, quantity, broker_order_id, client_order_id, filled_avg_price, recorded_by, "
    "recorded_at) VALUES (:closure_id, :entry_intent_governance_id, :symbol, :quantity, "
    ":broker_order_id, :client_order_id, :filled_avg_price, :recorded_by, :recorded_at) "
    "RETURNING closure_id, entry_intent_governance_id, symbol, quantity, broker_order_id, "
    "client_order_id, filled_avg_price, recorded_by, recorded_at"
)

_BY_ENTRY = (
    "SELECT closure_id, entry_intent_governance_id, symbol, quantity, broker_order_id, "
    "client_order_id, filled_avg_price, recorded_by, recorded_at "
    "FROM public.external_position_closure "
    "WHERE entry_intent_governance_id = :entry_intent_governance_id"
)


class PostgresExternalPositionClosureRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, closure: ExternalPositionClosure) -> ExternalPositionClosure:
        try:
            with self._service.unit_of_work() as work:
                rows = work.execute(
                    _INSERT,
                    {
                        "closure_id": closure.closure_id,
                        "entry_intent_governance_id": closure.entry_intent_governance_id,
                        "symbol": closure.symbol,
                        "quantity": closure.quantity,
                        "broker_order_id": closure.broker_order_id,
                        "client_order_id": closure.client_order_id,
                        "filled_avg_price": closure.filled_avg_price,
                        "recorded_by": closure.recorded_by,
                        "recorded_at": closure.recorded_at,
                    },
                )
        except Exception as error:
            cause = error.__cause__
            if isinstance(cause, IntegrityError) and (
                "uq_external_position_closure_entry" in str(cause)
                or "external_position_closure_pkey" in str(cause)
            ):
                raise ExternalPositionClosureAlreadyExistsError(
                    "an external closure already exists for entry_intent_governance_id="
                    f"{closure.entry_intent_governance_id!r}"
                ) from error
            raise
        return _row_to_closure(rows[0])

    def for_entry(self, entry_intent_governance_id: str) -> ExternalPositionClosure | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(_BY_ENTRY, {"entry_intent_governance_id": entry_intent_governance_id})
            )
        return _row_to_closure(rows[0]) if rows else None
