"""MILESTONE-085 time bases for the acts that WRITE M084's deadlines.

WHY THIS EXISTS. `d4f18a6c2e97` gave the M084 intent a broker time basis measured
when the intent is issued, and translated the intent's deadlines through it. Those
deadlines are not written at issuance. `expires_at` and `mandatory_liquidation_at`
are written when the PROPOSAL is evaluated, and the approval's `expires_at` when the
human DECIDES. Reproduced at `73a2f96`: proposal and approval created with host and
broker agreeing; real broker time moved on an hour while the host clock fell back;
issuance measured its basis then, M084 accepted the already-expired proposal and
approval on the host clock, the issuance basis mapped the proposal expiry an hour
late, and the chain dispatched.

WHAT IS ADDED. One evidence row per act, each measured IN that act:

  paper_proposal_time_basis  -- when a proposal is evaluated. Bound to the exact
                                stored proposal, and `proposal_created_at` must equal
                                the basis host reading (the Paper-bound command hands
                                that reading to M084 as `evaluated_at`).
  paper_decision_time_basis  -- when a human APPROVES. Bound to the exact stored
                                approval, and `decided_at` must equal the basis host
                                reading.

Each is append-only, guarded at insert against the stored M084 row, and never
backfilled: no row is written here, and a proposal or approval created through
M084 alone has none and cannot lead to a dispatch.

MILESTONE-084 IS NOT MODIFIED. `trade_proposal` and `trade_approval_decision` are
READ by the insert guards and gain no column, constraint or trigger.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e61b3f9a4c27"
down_revision: str | None = "d4f18a6c2e97"
branch_labels: str | None = None
depends_on: str | None = None

_PROPOSAL = "paper_proposal_time_basis"
_DECISION = "paper_decision_time_basis"
_PAPER_HOST = "paper-api.alpaca.markets"

_PROPOSAL_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_proposal_time_basis_guard_insert()
RETURNS trigger AS $$
DECLARE
    proposal_row public.trade_proposal;
BEGIN
    SELECT * INTO proposal_row
    FROM public.trade_proposal
    WHERE proposal_governance_id = NEW.proposal_governance_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            '% references trade proposal % which does not exist',
            TG_TABLE_NAME, NEW.proposal_governance_id;
    END IF;

    IF proposal_row.proposal_version IS DISTINCT FROM NEW.proposal_version
        OR proposal_row.content_fingerprint IS DISTINCT FROM NEW.content_fingerprint
        OR proposal_row.created_at IS DISTINCT FROM NEW.proposal_created_at
        OR proposal_row.expires_at IS DISTINCT FROM NEW.proposal_expires_at
        OR proposal_row.mandatory_liquidation_at IS DISTINCT FROM NEW.mandatory_liquidation_at
    THEN
        RAISE EXCEPTION
            'proposal time basis for % does not describe the exact stored proposal',
            NEW.proposal_governance_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_DECISION_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_decision_time_basis_guard_insert()
RETURNS trigger AS $$
DECLARE
    decision_row public.trade_approval_decision;
BEGIN
    SELECT * INTO decision_row
    FROM public.trade_approval_decision
    WHERE decision_governance_id = NEW.decision_governance_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            '% references approval decision % which does not exist',
            TG_TABLE_NAME, NEW.decision_governance_id;
    END IF;

    IF decision_row.action IS DISTINCT FROM 'APPROVE'
        OR decision_row.proposal_governance_id IS DISTINCT FROM NEW.proposal_governance_id
        OR decision_row.proposal_version IS DISTINCT FROM NEW.proposal_version
        OR decision_row.approved_fingerprint IS DISTINCT FROM NEW.approved_fingerprint
        OR decision_row.decided_at IS DISTINCT FROM NEW.decided_at
        OR decision_row.expires_at IS DISTINCT FROM NEW.decision_expires_at
    THEN
        RAISE EXCEPTION
            'decision time basis for % does not describe the exact stored approval',
            NEW.decision_governance_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""


def _basis_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("broker_endpoint_host", sa.String(length=64), nullable=False),
        sa.Column("basis_host_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_host_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_broker_earliest_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_broker_latest_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _basis_constraints(prefix: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            f"broker_endpoint_host = '{_PAPER_HOST}'", name=f"ck_{prefix}_endpoint_host"
        ),
        sa.CheckConstraint(
            "basis_host_requested_at <= basis_host_at", name=f"ck_{prefix}_host_interval"
        ),
        sa.CheckConstraint(
            "basis_broker_earliest_at <= basis_broker_latest_at",
            name=f"ck_{prefix}_broker_interval",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        _PROPOSAL,
        sa.Column("proposal_governance_id", sa.String(length=64), primary_key=True),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("proposal_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposal_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mandatory_liquidation_at", sa.DateTime(timezone=True), nullable=False),
        *_basis_columns(),
        *_basis_constraints("paper_proposal_time_basis"),
        sa.CheckConstraint(
            "content_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_paper_proposal_time_basis_fingerprint",
        ),
        # THE EVALUATION BINDING. The basis is measured first and its host reading
        # IS the proposal's `created_at`; a basis measured later cannot equal it.
        sa.CheckConstraint(
            "proposal_created_at = basis_host_at",
            name="ck_paper_proposal_time_basis_bound_to_evaluation",
        ),
        sa.CheckConstraint(
            "proposal_expires_at > proposal_created_at",
            name="ck_paper_proposal_time_basis_expiry_follows",
        ),
    )
    op.create_table(
        _DECISION,
        sa.Column("decision_governance_id", sa.String(length=64), primary_key=True),
        sa.Column("proposal_governance_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("approved_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_expires_at", sa.DateTime(timezone=True), nullable=False),
        *_basis_columns(),
        *_basis_constraints("paper_decision_time_basis"),
        sa.CheckConstraint(
            "approved_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_paper_decision_time_basis_fingerprint",
        ),
        # THE DECISION BINDING. The human's decision instant IS the basis host reading.
        sa.CheckConstraint(
            "decided_at = basis_host_at",
            name="ck_paper_decision_time_basis_bound_to_decision",
        ),
        sa.CheckConstraint(
            "decision_expires_at > decided_at",
            name="ck_paper_decision_time_basis_expiry_follows",
        ),
    )
    op.execute(_PROPOSAL_INSERT_FUNCTION)
    op.execute(
        "CREATE TRIGGER paper_proposal_time_basis_guard_insert_trigger "
        "BEFORE INSERT ON public.paper_proposal_time_basis "
        "FOR EACH ROW EXECUTE FUNCTION public.paper_execution_proposal_time_basis_guard_insert()"
    )
    op.execute(
        "CREATE TRIGGER paper_proposal_time_basis_append_only_trigger "
        "BEFORE UPDATE OR DELETE ON public.paper_proposal_time_basis "
        "FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()"
    )
    op.execute(_DECISION_INSERT_FUNCTION)
    op.execute(
        "CREATE TRIGGER paper_decision_time_basis_guard_insert_trigger "
        "BEFORE INSERT ON public.paper_decision_time_basis "
        "FOR EACH ROW EXECUTE FUNCTION public.paper_execution_decision_time_basis_guard_insert()"
    )
    op.execute(
        "CREATE TRIGGER paper_decision_time_basis_append_only_trigger "
        "BEFORE UPDATE OR DELETE ON public.paper_decision_time_basis "
        "FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()"
    )


def downgrade() -> None:
    for table in (_DECISION, _PROPOSAL):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only_trigger ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_guard_insert_trigger ON public.{table}")
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_decision_time_basis_guard_insert()")
    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_proposal_time_basis_guard_insert()")
