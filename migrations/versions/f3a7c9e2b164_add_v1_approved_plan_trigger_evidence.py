"""RELEASE v1 FORENSIC AUDIT FOLLOW-UP. Persist the quote evidence behind a price-based
exit-trigger claim.

WHY. The 2026-10-20 forensic audit of entry INT-PRP-089-PAPER-20261020T145108Z found that
`PositionPlanManager._evaluate_unclaimed` (`usecases/position_plan_manager.py`) claims a
STOP/TARGET trigger using only a bare bid `Decimal` (`_bid_as_decimal`), discarding the
quote's `ask`, `captured_at` and `source` before `evaluate_exit_trigger` ever sees them, and
`claim_exit_trigger` persists only `triggered_exit_kind`/`triggered_exit_at` -- no record of
the bid/ask/quote-timestamp/feed that actually drove an irreversible SELL_TO_CLOSE decision.
In that incident the trigger was CONFIRMED legitimate (a genuine, several-seconds-stable
IEX-venue bid of 335.72 against a stop of 338.40, while the consolidated tape never traded
below 339.85), but reconstructing that required pulling Alpaca's historical quotes endpoint
after the fact -- nothing in this database recorded it. This migration closes that gap with
PURELY ADDITIVE evidence columns; it changes no trigger behavior, weakens no check, and does
not touch `stop_price`/`target_price` or any existing row's existing semantics.

WHAT IS ADDED. Four nullable columns on `approved_plan`, populated (when available) by the
SAME conditional `UPDATE ... WHERE triggered_exit_kind IS NULL` that already claims the
trigger (`PostgresApprovedPlanRepository.claim_exit_trigger`):
  - `triggered_exit_quote_bid`    -- the bid (if any) that drove a STOP/TARGET claim
  - `triggered_exit_quote_ask`    -- the ask captured alongside it
  - `triggered_exit_quote_captured_at` -- the quote's OWN exchange timestamp
  - `triggered_exit_quote_source` -- e.g. "alpaca-iex", so a future reader knows which feed

NOT REQUIRED, DELIBERATELY. A STOP/TARGET claim is NOT required to carry quote evidence --
only the automatic manager's real production path (`PositionPlanManager._evaluate_unclaimed`)
populates it, going forward. Making it mandatory would reject every existing direct
`claim_exit_trigger(kind=STOP/TARGET, ...)` call that has no quote in scope (restart-recovery
resumption, concurrency-race tests, legacy-row tests), which is a BEHAVIOR change this
forensic-audit PR must not make. The one invariant enforced is narrower: the four columns
are all-or-nothing (never partially set), and MANDATORY_EXIT -- which fires on time alone and
never consults a quote -- may never carry any of them, mirroring `evaluate_exit_trigger`'s
own branches.

THE GUARD. `approved_plan_guard_update` (b9f2c4d6a8e1) is replaced (CREATE OR REPLACE,
same function name, same trigger) to additionally: (a) allow the four new columns to move
from NULL only in the SAME UPDATE that sets `triggered_exit_kind`/`triggered_exit_at` for
the first time, (b) refuse any later change to them once set (append-only, matching
`triggered_exit_kind` itself), and (c) require quote evidence to be all-or-nothing and
refuse it outright for a MANDATORY_EXIT claim. Every pre-existing invariant this function
already enforced is unchanged.

Revision ID: f3a7c9e2b164
Revises: 83e15e6bfae4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f3a7c9e2b164"
down_revision: str | None = "83e15e6bfae4"
branch_labels: None = None
depends_on: None = None

_TABLE = "approved_plan"

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

    -- FORENSIC AUDIT FOLLOW-UP (f3a7c9e2b164): the four quote-evidence columns are
    -- all-or-nothing, and only STOP/TARGET (price-based) claims may carry them --
    -- MANDATORY_EXIT fires on time alone and never consults a quote, mirroring
    -- `evaluate_exit_trigger`'s own branches.
    IF (NEW.triggered_exit_quote_bid IS NULL) <> (NEW.triggered_exit_quote_ask IS NULL)
        OR (NEW.triggered_exit_quote_bid IS NULL) <> (NEW.triggered_exit_quote_captured_at IS NULL)
        OR (NEW.triggered_exit_quote_bid IS NULL) <> (NEW.triggered_exit_quote_source IS NULL)
    THEN
        RAISE EXCEPTION
            'approved_plan % quote evidence columns must be set, or unset, together',
            OLD.plan_id;
    END IF;

    IF NEW.triggered_exit_kind = 'MANDATORY_EXIT' AND NEW.triggered_exit_quote_bid IS NOT NULL THEN
        RAISE EXCEPTION
            'approved_plan % a MANDATORY_EXIT claim never consults a quote', OLD.plan_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_PRIOR_GUARD_UPDATE_FUNCTION = """
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


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("triggered_exit_quote_bid", sa.Numeric(20, 8), nullable=True))
    op.add_column(_TABLE, sa.Column("triggered_exit_quote_ask", sa.Numeric(20, 8), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column("triggered_exit_quote_captured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        _TABLE, sa.Column("triggered_exit_quote_source", sa.String(length=32), nullable=True)
    )
    op.create_check_constraint(
        "ck_approved_plan_trigger_quote_paired",
        _TABLE,
        "(triggered_exit_quote_bid IS NULL) = (triggered_exit_quote_ask IS NULL) "
        "AND (triggered_exit_quote_bid IS NULL) = (triggered_exit_quote_captured_at IS NULL) "
        "AND (triggered_exit_quote_bid IS NULL) = (triggered_exit_quote_source IS NULL)",
    )
    op.create_check_constraint(
        "ck_approved_plan_trigger_quote_not_mandatory_exit",
        _TABLE,
        "triggered_exit_kind IS DISTINCT FROM 'MANDATORY_EXIT' OR triggered_exit_quote_bid IS NULL",
    )
    op.execute(_GUARD_UPDATE_FUNCTION)


def downgrade() -> None:
    op.execute(_PRIOR_GUARD_UPDATE_FUNCTION)
    op.drop_constraint("ck_approved_plan_trigger_quote_not_mandatory_exit", _TABLE, type_="check")
    op.drop_constraint("ck_approved_plan_trigger_quote_paired", _TABLE, type_="check")
    op.drop_column(_TABLE, "triggered_exit_quote_source")
    op.drop_column(_TABLE, "triggered_exit_quote_captured_at")
    op.drop_column(_TABLE, "triggered_exit_quote_ask")
    op.drop_column(_TABLE, "triggered_exit_quote_bid")
