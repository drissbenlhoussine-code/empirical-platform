"""RELEASE v1 persistence for `ApprovedPlan`.

ONE REPOSITORY, ONE ATOMIC CLAIM, THE M085 DISCIPLINE: every SQL statement is a literal
constant, every persisted value is read fail-closed (a wrong type is refused, never
coerced), and `claim_exit_trigger` is a single conditional `UPDATE ... WHERE
triggered_exit_kind IS NULL ... RETURNING`, mirroring `claim_dispatch`'s own exactly-once
discipline exactly. The database ALSO enforces this independently (the migration's
`approved_plan_guard_update` trigger refuses a second claim even against a caller who
bypassed this repository), the same belt-and-suspenders pattern M090's
`opportunity_guard_update` already uses.

THE SCHEMA HEAD. `require_exact_v1_approved_plan_schema_head` mirrors
`require_exact_m087_schema_head`: this table feeds the automatic exit manager's decision
to submit a real (Paper) SELL_TO_CLOSE unattended, which is the same class of danger those
guards exist for (see the migration's own docstring for why this is NOT treated like
M090's guard-free research schema).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind
from empirical_platform.decision_candidate.approved_plan_repositories import (
    ApprovedPlanAlreadyExistsError,
)
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = [
    "V1_APPROVED_PLAN_SCHEMA_HEAD",
    "ApprovedPlanAlreadyExistsError",
    "ApprovedPlanSchemaHeadError",
    "PostgresApprovedPlanRepository",
    "require_exact_v1_approved_plan_schema_head",
]

_OPERATION = "v1.approved_plan.row_mapping"

#: The ONE schema revision this code was written against: additive on the M090 head
#: `a2b4c6d8e0f2`, in the SAME `migrations/` chain (Store A).
V1_APPROVED_PLAN_SCHEMA_HEAD = "b9f2c4d6" + "a8e1"
_SCHEMA_HEAD_SELECT = "SELECT version_num FROM public.alembic_version"


class ApprovedPlanSchemaHeadError(ValueError):
    """The database is not at exactly the v1 approved-plan schema head this code requires."""


def require_exact_v1_approved_plan_schema_head(service: PostgresPersistenceService) -> str:
    try:
        with service.unit_of_work() as work:
            rows = list(work.execute(_SCHEMA_HEAD_SELECT))
    except Exception as error:
        raise ApprovedPlanSchemaHeadError(
            "the database schema revision could not be read; refusing to run the automatic "
            f"exit manager against an unverified schema ({type(error).__name__})"
        ) from error
    revisions = sorted(str(row.get("version_num")) for row in rows)
    if revisions != [V1_APPROVED_PLAN_SCHEMA_HEAD]:
        raise ApprovedPlanSchemaHeadError(
            f"the database is at schema revision(s) {revisions or ['<none>']}, not exactly "
            f"{V1_APPROVED_PLAN_SCHEMA_HEAD}; refusing to let the automatic exit manager run "
            "against a schema whose guards this code was not written for"
        )
    return V1_APPROVED_PLAN_SCHEMA_HEAD


def _fail(field: str, value: object, expected: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted approved_plan value {field} is {type(value).__name__}, not {expected}; "
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


def _optional_instant(row: Mapping[str, Any], field: str) -> datetime | None:
    return None if row[field] is None else _instant(row, field)


def _trigger_kind(row: Mapping[str, Any]) -> ExitTriggerKind | None:
    raw = _optional_str(row, "triggered_exit_kind")
    if raw is None:
        return None
    try:
        return ExitTriggerKind(raw)
    except ValueError as error:
        raise _fail("triggered_exit_kind", raw, "a valid ExitTriggerKind") from error


def _row_to_plan(row: Mapping[str, Any]) -> ApprovedPlan:
    return ApprovedPlan(
        plan_id=_str(row, "plan_id"),
        candidate_id=_str(row, "candidate_id"),
        entry_intent_governance_id=_str(row, "entry_intent_governance_id"),
        symbol=_str(row, "symbol"),
        approved_quantity=_decimal(row, "approved_quantity"),
        stop_price=_decimal(row, "stop_price"),
        target_price=_decimal(row, "target_price"),
        mandatory_liquidation_at=_instant(row, "mandatory_liquidation_at"),
        owner_approval_id=_str(row, "owner_approval_id"),
        system_identity=_str(row, "system_identity"),
        created_at=_instant(row, "created_at"),
        triggered_exit_kind=_trigger_kind(row),
        triggered_exit_at=_optional_instant(row, "triggered_exit_at"),
    )


#: Every statement below spells out its own column list as a literal, never built by
#: interpolating a shared variable -- the M085 discipline (see module docstring): `ruff`'s
#: S608 exists to catch exactly the shortcut of concatenating a column-list variable into
#: SQL text, and this module carries zero suppressions for it.
_RETURNING_COLUMNS = (
    "RETURNING plan_id, candidate_id, entry_intent_governance_id, symbol, "
    "approved_quantity, stop_price, target_price, mandatory_liquidation_at, "
    "owner_approval_id, system_identity, created_at, triggered_exit_kind, triggered_exit_at"
)

_INSERT = (
    "INSERT INTO public.approved_plan (plan_id, candidate_id, entry_intent_governance_id, "
    "symbol, approved_quantity, stop_price, target_price, mandatory_liquidation_at, "
    "owner_approval_id, system_identity, created_at, triggered_exit_kind, triggered_exit_at) "
    "VALUES (:plan_id, :candidate_id, :entry_intent_governance_id, :symbol, "
    ":approved_quantity, :stop_price, :target_price, :mandatory_liquidation_at, "
    ":owner_approval_id, :system_identity, :created_at, NULL, NULL) " + _RETURNING_COLUMNS
)

_BY_ID = (
    "SELECT plan_id, candidate_id, entry_intent_governance_id, symbol, approved_quantity, "
    "stop_price, target_price, mandatory_liquidation_at, owner_approval_id, system_identity, "
    "created_at, triggered_exit_kind, triggered_exit_at "
    "FROM public.approved_plan WHERE plan_id = :plan_id"
)

_BY_ENTRY = (
    "SELECT plan_id, candidate_id, entry_intent_governance_id, symbol, approved_quantity, "
    "stop_price, target_price, mandatory_liquidation_at, owner_approval_id, system_identity, "
    "created_at, triggered_exit_kind, triggered_exit_at "
    "FROM public.approved_plan WHERE entry_intent_governance_id = :entry_intent_governance_id"
)

_UNCLAIMED = (
    "SELECT plan_id, candidate_id, entry_intent_governance_id, symbol, approved_quantity, "
    "stop_price, target_price, mandatory_liquidation_at, owner_approval_id, system_identity, "
    "created_at, triggered_exit_kind, triggered_exit_at FROM public.approved_plan "
    "WHERE triggered_exit_kind IS NULL ORDER BY created_at ASC LIMIT :limit"
)

_CLAIMED = (
    "SELECT plan_id, candidate_id, entry_intent_governance_id, symbol, approved_quantity, "
    "stop_price, target_price, mandatory_liquidation_at, owner_approval_id, system_identity, "
    "created_at, triggered_exit_kind, triggered_exit_at FROM public.approved_plan "
    "WHERE triggered_exit_kind IS NOT NULL ORDER BY triggered_exit_at ASC LIMIT :limit"
)

_CLAIM = (
    "UPDATE public.approved_plan "
    "SET triggered_exit_kind = :kind, triggered_exit_at = :claimed_at "
    "WHERE plan_id = :plan_id AND triggered_exit_kind IS NULL " + _RETURNING_COLUMNS
)


class PostgresApprovedPlanRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, plan: ApprovedPlan) -> ApprovedPlan:
        if plan.is_claimed:
            raise ValueError("save() only accepts a brand-new, unclaimed plan")
        try:
            with self._service.unit_of_work() as work:
                rows = work.execute(
                    _INSERT,
                    {
                        "plan_id": plan.plan_id,
                        "candidate_id": plan.candidate_id,
                        "entry_intent_governance_id": plan.entry_intent_governance_id,
                        "symbol": plan.symbol,
                        "approved_quantity": plan.approved_quantity,
                        "stop_price": plan.stop_price,
                        "target_price": plan.target_price,
                        "mandatory_liquidation_at": plan.mandatory_liquidation_at,
                        "owner_approval_id": plan.owner_approval_id,
                        "system_identity": plan.system_identity,
                        "created_at": plan.created_at,
                    },
                )
        except Exception as error:
            cause = error.__cause__
            if isinstance(cause, IntegrityError) and (
                "uq_approved_plan" in str(cause) or "approved_plan_pkey" in str(cause)
            ):
                raise ApprovedPlanAlreadyExistsError(
                    f"a plan already exists for plan_id={plan.plan_id!r} or "
                    f"entry_intent_governance_id={plan.entry_intent_governance_id!r}"
                ) from error
            raise
        return _row_to_plan(rows[0])

    def get(self, plan_id: str) -> ApprovedPlan | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_BY_ID, {"plan_id": plan_id}))
        return _row_to_plan(rows[0]) if rows else None

    def for_entry(self, entry_intent_governance_id: str) -> ApprovedPlan | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(_BY_ENTRY, {"entry_intent_governance_id": entry_intent_governance_id})
            )
        return _row_to_plan(rows[0]) if rows else None

    def list_unclaimed(self, limit: int) -> tuple[ApprovedPlan, ...]:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_UNCLAIMED, {"limit": limit}))
        return tuple(_row_to_plan(row) for row in rows)

    def list_claimed(self, limit: int) -> tuple[ApprovedPlan, ...]:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_CLAIMED, {"limit": limit}))
        return tuple(_row_to_plan(row) for row in rows)

    def claim_exit_trigger(
        self, plan_id: str, *, kind: ExitTriggerKind, claimed_at: datetime
    ) -> ApprovedPlan | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    _CLAIM, {"plan_id": plan_id, "kind": kind.value, "claimed_at": claimed_at}
                )
            )
        return _row_to_plan(rows[0]) if rows else None
