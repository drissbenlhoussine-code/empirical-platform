"""MILESTONE-090 Opportunity Engine schema -- Store A, additive, no schema-head guard.

TWO TABLES ON THE SAME DATABASE TRACK A ALREADY USES. `opportunity` and `opportunity_decision`
stack on `e7c1a9d3b5f2` (M087's SIMULATION exit head) in the SAME `migrations/` chain M057-M073
already use -- not a new Store, not Store B/C (M090 never touches Paper credentials or the
`paper_execution_attempt` table). Unlike M085/M087/M089, no `require_exact_m09X_schema_head`
guard is added for this schema: those guards exist because a stale schema sitting next to LIVE
broker credentials is the danger they defend against, and M090 is research/read data with no
broker-write path anywhere in this milestone (see external-review/MILESTONE-090/scope-and-design.md
Section 4).

`opportunity_decision.opportunity_id` is a REAL foreign key into `opportunity.opportunity_id`
(both tables live in this one database) -- unlike M089's Store C, which could not FK across a
physical database boundary, this schema has no such boundary to work around.

THE STATUS TRANSITION TABLE IS ENFORCED IN THE DATABASE, MIRRORING
`decision_candidate.opportunity_engine.ALLOWED_OPPORTUNITY_TRANSITIONS` EXACTLY: CANDIDATE may
become ACTIONABLE, EXPIRED or INVALIDATED; ACTIONABLE may become EXPIRED, INVALIDATED,
OWNER_APPROVED or OWNER_IGNORED; every other status is terminal (no further UPDATE of ANY
column, not just `status`, is permitted once a row reaches one). No column but `status` may
ever change on an `opportunity` row -- identity and evidence are frozen at INSERT.

`opportunity_decision` is append-only (no UPDATE, no DELETE) and carries a UNIQUE constraint on
`opportunity_id`: exactly one Owner decision per opportunity, ever.

Revision ID: a2b4c6d8e0f2
Revises: e7c1a9d3b5f2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a2b4c6d8" + "e0f2"
down_revision: str | None = "e7c1a9d3b5f2"
branch_labels: None = None
depends_on: None = None

_HEX_DIGEST = "~ '^[0-9a-f]{64}$'"

_SESSIONS = "'PREMARKET_RESEARCH', 'REGULAR_SESSION', 'ENTRY_WINDOW_CLOSED', 'MARKET_CLOSED'"
_STATUSES = (
    "'CANDIDATE', 'ACTIONABLE', 'EXPIRED', 'INVALIDATED', 'REJECTED', "
    "'OWNER_APPROVED', 'OWNER_IGNORED'"
)
_TERMINAL_STATUSES = "'EXPIRED', 'INVALIDATED', 'REJECTED', 'OWNER_APPROVED', 'OWNER_IGNORED'"

_OPPORTUNITY = "opportunity"
_DECISION = "opportunity_decision"


def _not_blank(column: str) -> str:
    return f"length(btrim({column})) > 0"


_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION public.m090_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

#: Every column but `status` is frozen at INSERT; `status` may only move along the SAME closed
#: transition table `ALLOWED_OPPORTUNITY_TRANSITIONS` declares in Python. A row already in a
#: terminal status (everything but CANDIDATE/ACTIONABLE) refuses ANY further UPDATE.
_OPPORTUNITY_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.opportunity_guard_update()
RETURNS trigger AS $$
DECLARE
    allowed text[];
BEGIN
    IF OLD.status IN (__TERMINAL__) THEN
        RAISE EXCEPTION
            'opportunity % is terminal in status % and is immutable',
            OLD.opportunity_id, OLD.status;
    END IF;

    IF NEW.opportunity_id IS DISTINCT FROM OLD.opportunity_id
        OR NEW.policy_fingerprint IS DISTINCT FROM OLD.policy_fingerprint
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.generated_at IS DISTINCT FROM OLD.generated_at
        OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
        OR NEW.evidence_as_of IS DISTINCT FROM OLD.evidence_as_of
        OR NEW.session IS DISTINCT FROM OLD.session
        OR NEW.bid IS DISTINCT FROM OLD.bid
        OR NEW.ask IS DISTINCT FROM OLD.ask
        OR NEW.spread_percent IS DISTINCT FROM OLD.spread_percent
        OR NEW.entry_price IS DISTINCT FROM OLD.entry_price
        OR NEW.stop_price IS DISTINCT FROM OLD.stop_price
        OR NEW.target_price IS DISTINCT FROM OLD.target_price
        OR NEW.risk_per_share IS DISTINCT FROM OLD.risk_per_share
        OR NEW.reward_per_share IS DISTINCT FROM OLD.reward_per_share
        OR NEW.reward_risk_ratio IS DISTINCT FROM OLD.reward_risk_ratio
        OR NEW.quantity IS DISTINCT FROM OLD.quantity
        OR NEW.notional IS DISTINCT FROM OLD.notional
        OR NEW.maximum_loss IS DISTINCT FROM OLD.maximum_loss
        OR NEW.mandatory_liquidation_at IS DISTINCT FROM OLD.mandatory_liquidation_at
        OR NEW.structure_model_id IS DISTINCT FROM OLD.structure_model_id
        OR NEW.structure_model_version IS DISTINCT FROM OLD.structure_model_version
        OR NEW.evidence IS DISTINCT FROM OLD.evidence
        OR NEW.quality_score IS DISTINCT FROM OLD.quality_score
        OR NEW.quality_model_id IS DISTINCT FROM OLD.quality_model_id
        OR NEW.quality_model_version IS DISTINCT FROM OLD.quality_model_version
        OR NEW.rejection_reasons IS DISTINCT FROM OLD.rejection_reasons
    THEN
        RAISE EXCEPTION
            'opportunity % identity and evidence are immutable; only status may change',
            OLD.opportunity_id;
    END IF;

    IF NEW.status = OLD.status THEN
        RAISE EXCEPTION
            'opportunity % status must actually change on an UPDATE', OLD.opportunity_id;
    END IF;

    allowed := CASE OLD.status
        WHEN 'CANDIDATE' THEN ARRAY['ACTIONABLE', 'EXPIRED', 'INVALIDATED']
        WHEN 'ACTIONABLE' THEN
            ARRAY['EXPIRED', 'INVALIDATED', 'OWNER_APPROVED', 'OWNER_IGNORED']
        ELSE ARRAY[]::text[]
    END;

    IF NOT (NEW.status = ANY (allowed)) THEN
        RAISE EXCEPTION
            '% -> % is not an allowed opportunity status transition for %',
            OLD.status, NEW.status, OLD.opportunity_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
""".replace("__TERMINAL__", _TERMINAL_STATUSES)

#: An opportunity may only be DELETEd never; UPDATE is governed by `opportunity_guard_update`
#: above, so this trigger only needs to refuse DELETE (append-only-on-delete, same as M087's
#: `_refuse_delete_trigger` pattern for a table whose UPDATE has its own dedicated guard).
_OPPORTUNITY_DECISION_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.opportunity_decision_guard_insert()
RETURNS trigger AS $$
DECLARE
    opportunity_row public.opportunity;
BEGIN
    SELECT * INTO opportunity_row FROM public.opportunity WHERE opportunity_id = NEW.opportunity_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'opportunity decision % names opportunity % which does not exist',
            NEW.decision_id, NEW.opportunity_id;
    END IF;
    IF opportunity_row.status NOT IN ('OWNER_APPROVED', 'OWNER_IGNORED') THEN
        RAISE EXCEPTION
            'opportunity decision % names opportunity % in status %; a decision may only be '
            'recorded once the opportunity itself reflects OWNER_APPROVED or OWNER_IGNORED',
            NEW.decision_id, NEW.opportunity_id, opportunity_row.status;
    END IF;
    IF (NEW.action = 'APPROVE' AND opportunity_row.status <> 'OWNER_APPROVED')
        OR (NEW.action = 'IGNORE' AND opportunity_row.status <> 'OWNER_IGNORED')
    THEN
        RAISE EXCEPTION
            'opportunity decision % action % does not match opportunity % status %',
            NEW.decision_id, NEW.action, NEW.opportunity_id, opportunity_row.status;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""


def _create_opportunity_table() -> None:
    op.create_table(
        _OPPORTUNITY,
        sa.Column("opportunity_id", sa.String(length=64), primary_key=True),
        sa.Column("policy_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=12), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session", sa.String(length=32), nullable=False),
        sa.Column("bid", sa.Numeric(20, 8), nullable=True),
        sa.Column("ask", sa.Numeric(20, 8), nullable=True),
        sa.Column("spread_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("stop_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("target_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("risk_per_share", sa.Numeric(20, 8), nullable=True),
        sa.Column("reward_per_share", sa.Numeric(20, 8), nullable=True),
        sa.Column("reward_risk_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("quantity", sa.BigInteger(), nullable=True),
        sa.Column("notional", sa.Numeric(20, 8), nullable=True),
        sa.Column("maximum_loss", sa.Numeric(20, 8), nullable=True),
        sa.Column("mandatory_liquidation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("structure_model_id", sa.String(length=96), nullable=False),
        sa.Column("structure_model_version", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("quality_model_id", sa.String(length=96), nullable=False),
        sa.Column("quality_model_version", sa.String(length=16), nullable=False),
        sa.Column("rejection_reasons", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(_not_blank("opportunity_id"), name="ck_opportunity_id_present"),
        sa.CheckConstraint(
            f"symbol = upper(symbol) AND {_not_blank('symbol')}", name="ck_opportunity_symbol_upper"
        ),
        sa.CheckConstraint(
            f"policy_fingerprint {_HEX_DIGEST}", name="ck_opportunity_policy_fingerprint"
        ),
        sa.CheckConstraint("expires_at > generated_at", name="ck_opportunity_expiry_follows"),
        sa.CheckConstraint(f"session IN ({_SESSIONS})", name="ck_opportunity_session"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_opportunity_status"),
        # THE ACTIONABLE INVARIANT AT THE DATABASE BOUNDARY, mirroring
        # `TradingOpportunity.__post_init__` exactly: an ACTIONABLE row carries no rejection
        # reason, a whole positive quantity, and a stop strictly below its entry.
        sa.CheckConstraint(
            "status <> 'ACTIONABLE' OR (entry_price IS NOT NULL AND stop_price IS NOT NULL "
            "AND target_price IS NOT NULL AND quantity IS NOT NULL "
            "AND mandatory_liquidation_at IS NOT NULL AND rejection_reasons = '[]')",
            name="ck_opportunity_actionable_fields_present",
        ),
        sa.CheckConstraint(
            "status <> 'ACTIONABLE' OR stop_price < entry_price",
            name="ck_opportunity_actionable_stop_below_entry",
        ),
        sa.CheckConstraint(
            "status <> 'ACTIONABLE' OR quantity >= 1", name="ck_opportunity_actionable_quantity"
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR rejection_reasons <> '[]'",
            name="ck_opportunity_rejected_has_reason",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity >= 0", name="ck_opportunity_quantity_non_negative"
        ),
    )
    op.create_index(f"ix_{_OPPORTUNITY}_symbol_generated", _OPPORTUNITY, ["symbol", "generated_at"])
    op.create_index(
        f"ix_{_OPPORTUNITY}_generated_desc", _OPPORTUNITY, [sa.text("generated_at DESC")]
    )


def _create_opportunity_decision_table() -> None:
    op.create_table(
        _DECISION,
        sa.Column("decision_id", sa.String(length=64), primary_key=True),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            [f"{_OPPORTUNITY}.opportunity_id"],
            name="fk_opportunity_decision_opportunity",
        ),
        sa.UniqueConstraint("opportunity_id", name="uq_opportunity_decision_one_per_opportunity"),
        sa.CheckConstraint(_not_blank("decision_id"), name="ck_opportunity_decision_id_present"),
        sa.CheckConstraint(_not_blank("decided_by"), name="ck_opportunity_decision_actor_present"),
        sa.CheckConstraint(
            "action IN ('APPROVE', 'IGNORE')", name="ck_opportunity_decision_action"
        ),
    )


def _trigger(name: str, timing: str, table: str, function: str) -> str:
    return (
        f"CREATE TRIGGER {name} {timing} ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{function}()"
    )


def upgrade() -> None:
    op.execute(_APPEND_ONLY_FUNCTION)
    _create_opportunity_table()
    _create_opportunity_decision_table()

    op.execute(_OPPORTUNITY_UPDATE_FUNCTION)
    op.execute(
        _trigger(
            f"{_OPPORTUNITY}_guard_update_trigger",
            "BEFORE UPDATE",
            _OPPORTUNITY,
            "opportunity_guard_update",
        )
    )
    op.execute(
        _trigger(
            f"{_OPPORTUNITY}_refuse_delete_trigger",
            "BEFORE DELETE",
            _OPPORTUNITY,
            "m090_append_only",
        )
    )

    op.execute(_OPPORTUNITY_DECISION_INSERT_FUNCTION)
    op.execute(
        _trigger(
            f"{_DECISION}_guard_insert_trigger",
            "BEFORE INSERT",
            _DECISION,
            "opportunity_decision_guard_insert",
        )
    )
    op.execute(
        _trigger(
            f"{_DECISION}_append_only_trigger",
            "BEFORE UPDATE OR DELETE",
            _DECISION,
            "m090_append_only",
        )
    )


def downgrade() -> None:
    for trigger, table in (
        (f"{_DECISION}_append_only_trigger", _DECISION),
        (f"{_DECISION}_guard_insert_trigger", _DECISION),
        (f"{_OPPORTUNITY}_refuse_delete_trigger", _OPPORTUNITY),
        (f"{_OPPORTUNITY}_guard_update_trigger", _OPPORTUNITY),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON public.{table}")
    op.drop_table(_DECISION)
    op.drop_table(_OPPORTUNITY)
    for function in (
        "opportunity_decision_guard_insert",
        "opportunity_guard_update",
        "m090_append_only",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS public.{function}()")
