"""MILESTONE-076 operator-asserted position event schema.

One additive table. Append-only: the application never updates or deletes a
row. Every column records what the OPERATOR asserted -- not a broker record and
not a verified fill.

Revision ID: b7e1c4a95d38
Revises: 31365632c016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1c4a95d38"
down_revision: str | None = "31365632c016"
branch_labels: None = None
depends_on: None = None

_TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "operator_position_event",
        sa.Column("runtime_id", sa.String(length=64), primary_key=True),
        sa.Column("governance_id", sa.String(length=64), nullable=False),
        sa.Column("position_governance_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_symbol", sa.String(length=32), nullable=False),
        sa.Column("event_kind", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("asserted_price", sa.Numeric(precision=20, scale=6), nullable=False),
        # Drives the fold. When the operator says it happened.
        sa.Column("event_timestamp", _TIMESTAMPTZ, nullable=False),
        # Audit only. Never affects derived state.
        sa.Column("recorded_at", _TIMESTAMPTZ, nullable=False),
        # Informational lineage: what motivated the assertion. Never a
        # precondition, and never used to derive a position.
        sa.Column("source_position_plan_governance_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.UniqueConstraint("governance_id", name="uq_operator_position_event_governance_id"),
        sa.CheckConstraint(
            "event_kind IN ('OPENED', 'REDUCED', 'CLOSED')",
            name="operator_position_event_kind_valid",
        ),
        sa.CheckConstraint("quantity >= 0", name="operator_position_event_quantity_non_negative"),
        sa.CheckConstraint(
            "(event_kind = 'CLOSED') OR (quantity > 0)",
            name="operator_position_event_open_reduce_quantity_positive",
        ),
        sa.CheckConstraint(
            "asserted_price > 0", name="operator_position_event_asserted_price_positive"
        ),
    )
    # The two real query paths: fold one position key, and list by instrument.
    op.create_index(
        "ix_operator_position_event_position_time",
        "operator_position_event",
        ["position_governance_id", "event_timestamp"],
    )
    op.create_index(
        "ix_operator_position_event_instrument_time",
        "operator_position_event",
        ["instrument_symbol", "event_timestamp"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operator_position_event_instrument_time", table_name="operator_position_event"
    )
    op.drop_index("ix_operator_position_event_position_time", table_name="operator_position_event")
    op.drop_table("operator_position_event")
