"""RELEASE v1 -- external position closure: Store C, additive on the M089 head.

WHY. A position can be closed by a human directly on the broker's own dashboard, outside
this platform's own Preview -> Authorize -> Submit chain (see
`external-review/INCIDENT-2026-10-14-aapl-overdue-recovery/evidence.md`). Nothing in the
existing M089 schema records that outside fact durably, so the automatic Plan Manager
retries a trigger forever for a position that can never be closed through its own pipeline.
This migration adds exactly one new, independent table -- it does not alter, rename, or add
a column to any M089 table, and it does not touch `approved_plan` (Store B) at all. See
`decision_candidate/external_position_closure.py` for the domain object this table backs,
and `usecases/record_external_position_closure.py` for the one handler that may write to it
(after verifying the evidence against a live broker read -- never on the caller's word
alone).

APPEND-ONLY, AT MOST ONE PER ENTRY. The same `m089_append_only()` trigger function the first
M089 migration defined is reused unchanged (it is generic, not table-specific) to refuse any
UPDATE or DELETE. `uq_external_position_closure_entry` is the exactly-once primitive --
mirroring `approved_plan`'s own `claim_exit_trigger` and `position_exit_attempt`'s
one-active-exit index elsewhere in this codebase -- so at most one closure record can ever
exist per entry, even against a caller who raced the handler's own `for_entry` check.

Revision ID: d4e9c2a7f183
Revises: f083b6c29d17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d4e9c2a7" + "f183"
down_revision: str | None = "f083b6c2" + "9d17"
branch_labels: None = None
depends_on: None = None

_TABLE = "external_position_closure"


def _not_blank(column: str) -> str:
    return f"length(btrim({column})) > 0"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("closure_id", sa.String(length=64), primary_key=True),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("filled_avg_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("recorded_by", sa.String(length=64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "entry_intent_governance_id", name="uq_external_position_closure_entry"
        ),
        sa.CheckConstraint(
            _not_blank("closure_id"), name="ck_external_position_closure_id_present"
        ),
        sa.CheckConstraint(
            "closure_id = 'XEC-' || entry_intent_governance_id",
            name="ck_external_position_closure_id_derived",
        ),
        sa.CheckConstraint(
            _not_blank("broker_order_id"),
            name="ck_external_position_closure_broker_order_id_present",
        ),
        sa.CheckConstraint(
            _not_blank("client_order_id"),
            name="ck_external_position_closure_client_order_id_present",
        ),
        sa.CheckConstraint(
            _not_blank("recorded_by"), name="ck_external_position_closure_recorded_by_present"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_external_position_closure_quantity_positive"),
        sa.CheckConstraint(
            "filled_avg_price > 0", name="ck_external_position_closure_price_positive"
        ),
    )
    # No separate index: `uq_external_position_closure_entry` above already gives Postgres
    # a unique btree on `entry_intent_governance_id`, which is the only lookup this table
    # ever needs (`for_entry`).
    op.execute(
        f"CREATE TRIGGER {_TABLE}_append_only_trigger "
        f"BEFORE UPDATE OR DELETE ON public.{_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.m089_append_only()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TABLE}_append_only_trigger ON public.{_TABLE}")
    op.drop_table(_TABLE)
