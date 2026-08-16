"""MILESTONE-082 operator event receipt attestation schema.

ADDITIVE ONLY. No existing table is altered and NO ROW IS BACKFILLED.

The table is created EMPTY on purpose. M076 already holds events created before
M082, and manufacturing a receipt for them -- from `recorded_at`, from
`event_timestamp`, or from the migration's own run time -- would fabricate
knowledge history. Absence of a receipt is an honest state and stays absent.

`ON DELETE RESTRICT`, never CASCADE: M076 is append-only, but if a row were ever
removed the receipt evidence must not silently vanish with it.

The trigger makes receipts DATABASE-ENFORCED immutable against UPDATE and
DELETE, not merely append-only by application convention. A superuser can still
drop the trigger; that limit is stated in the design rather than hidden.

Revision ID: d9a2f5c81b73
Revises: b7e1c4a95d38
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d9a2f5c81b73"
down_revision: str | None = "b7e1c4a95d38"
branch_labels: None = None
depends_on: None = None

_TIMESTAMPTZ = sa.DateTime(timezone=True)

_IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION operator_event_receipt_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'operator_event_receipt is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql
"""

_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER operator_event_receipt_immutable_trigger
BEFORE UPDATE OR DELETE ON operator_event_receipt
FOR EACH ROW EXECUTE FUNCTION operator_event_receipt_immutable()
"""


def upgrade() -> None:
    op.create_table(
        "operator_event_receipt",
        sa.Column("receipt_governance_id", sa.String(length=64), primary_key=True),
        # Exactly one receipt per event. The UNIQUE constraint is what makes
        # retry idempotent structurally rather than by convention, and what
        # resolves two concurrent attesters for the same event.
        sa.Column("event_governance_id", sa.String(length=64), nullable=False),
        # The attestation instant. Assigned by the application host clock AFTER
        # the event was read back as committed, so it is an UPPER BOUND WITNESS
        # on the event's commit time -- never the commit time itself.
        sa.Column("system_received_at", _TIMESTAMPTZ, nullable=False),
        # Recorded strings describing the pathway. Neither is an authority in
        # itself; both exist so a reader can tell what produced the receipt.
        sa.Column("attested_by", sa.String(length=64), nullable=False),
        sa.Column("attester_version", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("event_governance_id", name="uq_operator_event_receipt_event"),
        sa.ForeignKeyConstraint(
            ["event_governance_id"],
            ["operator_position_event.governance_id"],
            name="fk_operator_event_receipt_event",
            ondelete="RESTRICT",
        ),
    )
    # The single query path: everything attested by a cutoff.
    op.create_index(
        "ix_operator_event_receipt_received_at",
        "operator_event_receipt",
        ["system_received_at"],
    )
    op.execute(_IMMUTABILITY_FUNCTION)
    op.execute(_IMMUTABILITY_TRIGGER)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS operator_event_receipt_immutable_trigger ON operator_event_receipt"
    )
    op.drop_index("ix_operator_event_receipt_received_at", table_name="operator_event_receipt")
    op.drop_table("operator_event_receipt")
    op.execute("DROP FUNCTION IF EXISTS operator_event_receipt_immutable()")
