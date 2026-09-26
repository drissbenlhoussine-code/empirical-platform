"""MILESTONE-085 durable reconciliation rounds (Q-2 / Q-4).

WHY THIS EXISTS. The publication review of `832b20b` reproduced two gaps in the bounded
not-found policy, on PostgreSQL through the production handlers:

  Q-2  a reconciliation lookup that raised, whose failure event could not be persisted
       either, left NOTHING behind -- no acknowledgement, no event, no sequence gap -- so the
       404 answers on either side of it read as consecutive after a restart;
  Q-4  the failure event was ordered against acknowledgements by wall-clock timestamps from
       different hosts, so a lagging reconciler's failure sorted before the run and was
       ignored, and the 60-second minimum was measured on the reconciler's own wall clock.

WHAT IS ADDED.

  paper_reconciliation_round   one row per reconciliation ROUND, written BEFORE the network
                               call. Its identity is the attempt plus an allocated per-attempt
                               sequence (UNIQUE), its context the attempt's authorization,
                               client_order_id and the authorized account. It starts INCOMPLETE
                               (outcome NULL) and is completed exactly once with the outcome of
                               that exact round -- NOT_FOUND, FOUND, UNUSABLE or FAILED -- the
                               acknowledgement sequence it produced, if any, and the broker
                               clock interval sampled during the round. A round that is never
                               completed stays visible as unfinished work; it is not an
                               acknowledgement and no HTTP status is fabricated for it.

GUARDS. The insert guard binds the row to its attempt (the attempt must exist and the
authorization_id and client_order_id must be the attempt's) and refuses a row inserted already
complete. The update guard permits exactly one change -- outcome NULL -> outcome set -- and
freezes every identity column and every completed row. Deletion is refused by the milestone's
append-only function. The per-attempt sequence is UNIQUE, so two writers racing for the same
position cannot both succeed; the repository additionally serialises allocation by locking the
attempt row.

NOT BACKFILLED. Rounds are not invented for attempts reconciled before this revision; their
acknowledgements remain as evidence but do not count as rounds. MILESTONE-083 and MILESTONE-084
tables gain no column, constraint or trigger.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3c9e14f26"
down_revision: str | None = "9c4b2e7d5a18"
branch_labels: str | None = None
depends_on: str | None = None

_ROUND = "paper_reconciliation_round"
_OUTCOMES = "'NOT_FOUND', 'FOUND', 'UNUSABLE', 'FAILED'"


def _not_blank(column: str) -> str:
    return f"length(btrim({column})) > 0"


_ROUND_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_reconciliation_round_guard_insert()
RETURNS trigger AS $$
DECLARE
    attempt_row public.paper_execution_attempt;
BEGIN
    SELECT * INTO attempt_row
    FROM public.paper_execution_attempt
    WHERE attempt_id = NEW.attempt_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'reconciliation round % names attempt % which does not exist',
            NEW.round_id, NEW.attempt_id;
    END IF;

    -- The round is bound to the attempt's own identity and authorization.
    IF attempt_row.intent_governance_id IS DISTINCT FROM NEW.intent_governance_id
        OR attempt_row.authorization_id IS DISTINCT FROM NEW.authorization_id
        OR attempt_row.client_order_id IS DISTINCT FROM NEW.client_order_id
    THEN
        RAISE EXCEPTION
            'reconciliation round % does not describe attempt %',
            NEW.round_id, NEW.attempt_id;
    END IF;

    -- A round begins INCOMPLETE. Completion is the one update this table permits.
    IF NEW.outcome IS NOT NULL OR NEW.completed_at IS NOT NULL
        OR NEW.acknowledgement_sequence IS NOT NULL
        OR NEW.broker_earliest_at IS NOT NULL OR NEW.broker_latest_at IS NOT NULL
    THEN
        RAISE EXCEPTION
            'reconciliation round % must begin incomplete',
            NEW.round_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_ROUND_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_reconciliation_round_guard_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.round_id IS DISTINCT FROM OLD.round_id
        OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
        OR NEW.intent_governance_id IS DISTINCT FROM OLD.intent_governance_id
        OR NEW.authorization_id IS DISTINCT FROM OLD.authorization_id
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id
        OR NEW.account_reference IS DISTINCT FROM OLD.account_reference
        OR NEW.sequence IS DISTINCT FROM OLD.sequence
        OR NEW.started_at IS DISTINCT FROM OLD.started_at
    THEN
        RAISE EXCEPTION
            'reconciliation round % identity is immutable',
            OLD.round_id;
    END IF;

    -- Completed exactly once: a completed round is the record of what that round found.
    IF OLD.outcome IS NOT NULL THEN
        RAISE EXCEPTION
            'reconciliation round % is complete (%) and is immutable',
            OLD.round_id, OLD.outcome;
    END IF;

    IF NEW.outcome IS NULL OR NEW.completed_at IS NULL THEN
        RAISE EXCEPTION
            'reconciliation round % may only be updated to a completed outcome',
            OLD.round_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""


def upgrade() -> None:
    op.create_table(
        _ROUND,
        sa.Column("round_id", sa.String(length=64), primary_key=True),
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("authorization_id", sa.String(length=64), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("account_reference", sa.String(length=96), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_sequence", sa.Integer(), nullable=True),
        sa.Column("broker_earliest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broker_latest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["paper_execution_attempt.attempt_id"],
            name="fk_paper_reconciliation_round_attempt",
        ),
        sa.UniqueConstraint(
            "attempt_id", "sequence", name="uq_paper_reconciliation_round_attempt_sequence"
        ),
        sa.CheckConstraint(_not_blank("round_id"), name="ck_paper_reconciliation_round_id_present"),
        sa.CheckConstraint(
            _not_blank("account_reference"),
            name="ck_paper_reconciliation_round_account_present",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_paper_reconciliation_round_sequence_positive"),
        sa.CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_OUTCOMES})",
            name="ck_paper_reconciliation_round_outcome",
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (completed_at IS NULL)",
            name="ck_paper_reconciliation_round_completion_pairs",
        ),
        sa.CheckConstraint(
            "(broker_earliest_at IS NULL) = (broker_latest_at IS NULL)",
            name="ck_paper_reconciliation_round_broker_interval_pairs",
        ),
        sa.CheckConstraint(
            "broker_latest_at IS NULL OR broker_latest_at >= broker_earliest_at",
            name="ck_paper_reconciliation_round_broker_interval_ordered",
        ),
        sa.CheckConstraint(
            "acknowledgement_sequence IS NULL OR acknowledgement_sequence >= 1",
            name="ck_paper_reconciliation_round_ack_sequence_positive",
        ),
    )
    op.create_index("ix_paper_reconciliation_round_attempt", _ROUND, ["attempt_id", "sequence"])
    op.execute(_ROUND_INSERT_FUNCTION)
    op.execute(
        f"CREATE TRIGGER {_ROUND}_guard_insert_trigger "
        f"AFTER INSERT ON public.{_ROUND} "
        "FOR EACH ROW EXECUTE FUNCTION public.paper_reconciliation_round_guard_insert()"
    )
    op.execute(_ROUND_UPDATE_FUNCTION)
    op.execute(
        f"CREATE TRIGGER {_ROUND}_guard_update_trigger "
        f"BEFORE UPDATE ON public.{_ROUND} "
        "FOR EACH ROW EXECUTE FUNCTION public.paper_reconciliation_round_guard_update()"
    )
    op.execute(
        f"CREATE TRIGGER {_ROUND}_append_only_trigger "
        f"BEFORE DELETE ON public.{_ROUND} "
        "FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_ROUND}_append_only_trigger ON public.{_ROUND}")
    op.execute(f"DROP TRIGGER IF EXISTS {_ROUND}_guard_update_trigger ON public.{_ROUND}")
    op.execute("DROP FUNCTION IF EXISTS public.paper_reconciliation_round_guard_update()")
    op.execute(f"DROP TRIGGER IF EXISTS {_ROUND}_guard_insert_trigger ON public.{_ROUND}")
    op.execute("DROP FUNCTION IF EXISTS public.paper_reconciliation_round_guard_insert()")
    op.drop_index("ix_paper_reconciliation_round_attempt", table_name=_ROUND)
    op.drop_table(_ROUND)
