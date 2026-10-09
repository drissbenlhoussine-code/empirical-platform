"""RELEASE v1 Approved Plan schema -- Store A, additive, same database as M090.

ONE TABLE, ONE ATOMIC CLAIM. `approved_plan` is the durable record of the Owner's single
full-plan approval: frozen entry + exit terms, plus the ONE deliberate mutation the row
ever undergoes -- `triggered_exit_kind`/`triggered_exit_at`, claimed exactly once by the
automatic `PositionPlanManager` (see `decision_candidate/approved_plan.py` and
`shared/persistence/postgres_repositories/approved_plan_repositories.py`).

WHY A SCHEMA-HEAD GUARD, UNLIKE M090. M090's own migration explains why IT skips a
`require_exact_m09X_schema_head` guard: that schema is read-only research data with no
broker-write path. `approved_plan` is the opposite -- it is the one row the automatic
exit manager reads to decide whether to submit a real (Paper) SELL_TO_CLOSE unattended,
which is exactly the class of danger M085/M087/M089's guards exist for. This migration
therefore DOES add `require_exact_v1_approved_plan_schema_head`
(`approved_plan_repositories.py`), consistent with that stated rationale rather than
M090's.

THE GUARD AT THE DATABASE BOUNDARY, mirroring `ApprovedPlan.__post_init__` and
`evaluate_exit_trigger`'s invariants exactly: `stop_price < target_price` (long-only, full
close only), positive quantity/prices, and `system_identity` is the deterministic
`system:approved-plan:<plan_id>:owner-approval:<owner_approval_id>` format -- never a
freeform string, checked by a regex CHECK constraint mirroring
`approved_plan.derive_system_identity` byte for byte.

THE CLAIM-ONCE TRIGGER. Every column but `triggered_exit_kind`/`triggered_exit_at` is
frozen at INSERT (an UPDATE of any other column is refused). Those two columns may move
from NULL to a value exactly once; an UPDATE that tries to change an already-set
`triggered_exit_kind`, or that sets one of the pair without the other, is refused. This is
the database's own copy of the application-level atomic
`UPDATE ... WHERE triggered_exit_kind IS NULL` the repository already performs -- belt and
suspenders, the same discipline `opportunity_guard_update` already uses for M090.

Revision ID: b9f2c4d6a8e1
Revises: a2b4c6d8e0f2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b9f2c4d6" + "a8e1"
down_revision: str | None = "a2b4c6d8e0f2"
branch_labels: None = None
depends_on: None = None

_TABLE = "approved_plan"
_HEX_DIGEST = "~ '^[0-9a-f]{64}$'"
_TRIGGER_KINDS = "'STOP', 'TARGET', 'MANDATORY_EXIT'"


def _not_blank(column: str) -> str:
    return f"length(btrim({column})) > 0"


_GUARD_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.approved_plan_guard_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.plan_id IS DISTINCT FROM OLD.plan_id
        OR NEW.candidate_id IS DISTINCT FROM OLD.candidate_id
        OR NEW.entry_intent_governance_id IS DISTINCT FROM OLD.entry_intent_governance_id
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.approved_quantity IS DISTINCT FROM OLD.approved_quantity
        OR NEW.stop_price IS DISTINCT FROM OLD.stop_price
        OR NEW.target_price IS DISTINCT FROM OLD.target_price
        OR NEW.mandatory_liquidation_at IS DISTINCT FROM OLD.mandatory_liquidation_at
        OR NEW.owner_approval_id IS DISTINCT FROM OLD.owner_approval_id
        OR NEW.system_identity IS DISTINCT FROM OLD.system_identity
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION
            'approved_plan % identity and terms are immutable; only the one exit-trigger '
            'claim may change', OLD.plan_id;
    END IF;

    IF OLD.triggered_exit_kind IS NOT NULL THEN
        RAISE EXCEPTION
            'approved_plan % already claimed (%); a second claim is refused',
            OLD.plan_id, OLD.triggered_exit_kind;
    END IF;

    IF (NEW.triggered_exit_kind IS NULL) <> (NEW.triggered_exit_at IS NULL) THEN
        RAISE EXCEPTION
            'approved_plan % triggered_exit_kind and triggered_exit_at must be set, or '
            'unset, together', OLD.plan_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_REFUSE_DELETE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.approved_plan_refuse_delete()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'approved_plan % is append-only; DELETE is not permitted', OLD.plan_id;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("plan_id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("stop_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("target_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("mandatory_liquidation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_approval_id", sa.String(length=64), nullable=False),
        sa.Column("system_identity", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_exit_kind", sa.String(length=32), nullable=True),
        sa.Column("triggered_exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_not_blank("plan_id"), name="ck_approved_plan_id_present"),
        sa.CheckConstraint(_not_blank("candidate_id"), name="ck_approved_plan_candidate_present"),
        sa.CheckConstraint(
            _not_blank("entry_intent_governance_id"), name="ck_approved_plan_entry_present"
        ),
        sa.CheckConstraint(
            f"symbol = upper(symbol) AND {_not_blank('symbol')}",
            name="ck_approved_plan_symbol_upper",
        ),
        sa.CheckConstraint("approved_quantity > 0", name="ck_approved_plan_quantity_positive"),
        sa.CheckConstraint(
            "stop_price > 0 AND target_price > 0", name="ck_approved_plan_prices_positive"
        ),
        sa.CheckConstraint("stop_price < target_price", name="ck_approved_plan_stop_below_target"),
        sa.CheckConstraint(
            _not_blank("owner_approval_id"), name="ck_approved_plan_owner_approval_present"
        ),
        sa.CheckConstraint(
            # NOTE: `\:` escapes a literal colon so SQLAlchemy's textual-SQL compiler does not
            # mistake `:approved`/`:owner` for a bind parameter (it silently rendered them as
            # NULL the first time this was written, which a local-Postgres smoke test caught
            # before this ever reached CI).
            r"system_identity = 'system\:approved-plan:' || plan_id || '\:owner-approval:' "
            "|| owner_approval_id",
            name="ck_approved_plan_system_identity_derived",
        ),
        sa.CheckConstraint(
            f"triggered_exit_kind IS NULL OR triggered_exit_kind IN ({_TRIGGER_KINDS})",
            name="ck_approved_plan_trigger_kind",
        ),
        sa.CheckConstraint(
            "(triggered_exit_kind IS NULL) = (triggered_exit_at IS NULL)",
            name="ck_approved_plan_trigger_pair",
        ),
        sa.UniqueConstraint("entry_intent_governance_id", name="uq_approved_plan_one_per_entry"),
    )
    op.create_index(
        "ix_approved_plan_unclaimed",
        _TABLE,
        ["created_at"],
        postgresql_where=sa.text("triggered_exit_kind IS NULL"),
    )
    op.create_index(
        "ix_approved_plan_claimed",
        _TABLE,
        ["triggered_exit_at"],
        postgresql_where=sa.text("triggered_exit_kind IS NOT NULL"),
    )
    op.execute(_GUARD_UPDATE_FUNCTION)
    op.execute(_REFUSE_DELETE_FUNCTION)
    op.execute(
        f"CREATE TRIGGER trg_{_TABLE}_guard_update BEFORE UPDATE ON public.{_TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION public.approved_plan_guard_update()"
    )
    op.execute(
        f"CREATE TRIGGER trg_{_TABLE}_refuse_delete BEFORE DELETE ON public.{_TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION public.approved_plan_refuse_delete()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{_TABLE}_refuse_delete ON public.{_TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS trg_{_TABLE}_guard_update ON public.{_TABLE}")
    op.execute("DROP FUNCTION IF EXISTS public.approved_plan_refuse_delete()")
    op.execute("DROP FUNCTION IF EXISTS public.approved_plan_guard_update()")
    op.drop_index("ix_approved_plan_claimed", table_name=_TABLE)
    op.drop_index("ix_approved_plan_unclaimed", table_name=_TABLE)
    op.drop_table(_TABLE)
