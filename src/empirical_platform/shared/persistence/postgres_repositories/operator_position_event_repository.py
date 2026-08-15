"""Concrete PostgreSQL operator-asserted position ledger adapter (MILESTONE-076).

Append-only. This adapter issues exactly one INSERT and two SELECTs; there is no
UPDATE and no DELETE anywhere in it, which is the persistence-level expression of
the ledger being an immutable log of operator assertions.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "OperatorAssertedPositionEvent"
_ROOT_UNIQUE_CONSTRAINTS = {
    "pk_operator_position_event",
    "uq_operator_position_event_governance_id",
    "operator_position_event_pkey",
}


def _row_to_event(row: Mapping[str, Any]) -> OperatorAssertedPositionEvent:
    plan_id = row["source_position_plan_governance_id"]
    note = row["note"]
    return OperatorAssertedPositionEvent(
        governance_id=str(row["governance_id"]),
        runtime_id=str(row["runtime_id"]),
        position_governance_id=str(row["position_governance_id"]),
        instrument_symbol=str(row["instrument_symbol"]),
        kind=OperatorPositionEventKind(str(row["event_kind"])),
        quantity=int(row["quantity"]),
        asserted_price=cast(Decimal, row["asserted_price"]),
        event_timestamp=cast(datetime, row["event_timestamp"]),
        recorded_at=cast(datetime, row["recorded_at"]),
        source_position_plan_governance_id=None if plan_id is None else str(plan_id),
        note=None if note is None else str(note),
    )


class PostgresOperatorPositionLedgerRepository:
    """PostgreSQL-backed append-only operator position ledger."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def append(self, event: OperatorAssertedPositionEvent) -> None:
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    "INSERT INTO operator_position_event "
                    "(runtime_id, governance_id, position_governance_id, "
                    "instrument_symbol, event_kind, quantity, asserted_price, "
                    "event_timestamp, recorded_at, "
                    "source_position_plan_governance_id, note) VALUES "
                    "(:runtime_id, :governance_id, :position_governance_id, "
                    ":instrument_symbol, :event_kind, :quantity, :asserted_price, "
                    ":event_timestamp, :recorded_at, "
                    ":source_position_plan_governance_id, :note)",
                    {
                        "runtime_id": event.runtime_id,
                        "governance_id": event.governance_id,
                        "position_governance_id": event.position_governance_id,
                        "instrument_symbol": event.instrument_symbol,
                        "event_kind": event.kind.value,
                        "quantity": event.quantity,
                        "asserted_price": event.asserted_price,
                        "event_timestamp": event.event_timestamp,
                        "recorded_at": event.recorded_at,
                        "source_position_plan_governance_id": (
                            event.source_position_plan_governance_id
                        ),
                        "note": event.note,
                    },
                )
            except FoundationError as exc:
                constraint = unique_violation_constraint_name(exc)
                if constraint in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=event.governance_id
                    ) from exc
                raise

    def list_all(self) -> tuple[OperatorAssertedPositionEvent, ...]:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT runtime_id, governance_id, position_governance_id, "
                "instrument_symbol, event_kind, quantity, asserted_price, "
                "event_timestamp, recorded_at, source_position_plan_governance_id, note "
                "FROM operator_position_event ORDER BY event_timestamp, governance_id"
            )
            return tuple(_row_to_event(row) for row in rows)

    def list_for_position(
        self, position_governance_id: str
    ) -> tuple[OperatorAssertedPositionEvent, ...]:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT runtime_id, governance_id, position_governance_id, "
                "instrument_symbol, event_kind, quantity, asserted_price, "
                "event_timestamp, recorded_at, source_position_plan_governance_id, note "
                "FROM operator_position_event WHERE position_governance_id = :pid "
                "ORDER BY event_timestamp, governance_id",
                {"pid": position_governance_id},
            )
            return tuple(_row_to_event(row) for row in rows)
