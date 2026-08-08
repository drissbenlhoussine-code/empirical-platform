"""create m057 decision_candidate schema

Revision ID: a1c93f7e2b04
Revises: 5b58cdd7751b
Create Date: 2026-08-10 00:00:00.000000

MILESTONE-057: creates the `decision_candidate` table -- the first and only
new table this milestone requires. `DecisionCandidate` is an immutable,
single-insert record (no lifecycle, no `save()`, no optimistic-concurrency
column), so unlike every prior aggregate's schema there is no companion
`*_transition` child table. `target_evidence_package_governance_id`
foreign-keys to `evidence_package.governance_id`, mirroring the existing
`review.target_evidence_package_id` reference shape exactly. Same naming
convention and table-creation discipline as the frozen M022 migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1c93f7e2b04"
down_revision: str | None = "5b58cdd7751b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
_TIMESTAMPTZ = sa.DateTime(timezone=True)
_TEXT_ARRAY_DEFAULT = sa.text("'{}'::text[]")
_NUMERIC = sa.Numeric(precision=18, scale=6)

# Identical naming convention to the frozen M022 migration.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

_BAR_INTERVALS = ("ONE_MINUTE", "FIVE_MINUTE")
_TRADING_DECISIONS = ("LONG_CANDIDATE", "NO_TRADE")


def _enum_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


# Minimal shadow declaration of the M022 `evidence_package` table, needed only
# so SQLAlchemy can resolve the foreign key below within this revision's own
# `MetaData` object -- it is never created or dropped by this migration.
evidence_package = sa.Table(
    "evidence_package",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)

decision_candidate = sa.Table(
    "decision_candidate",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("target_evidence_package_governance_id", sa.Text(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("bar_interval", sa.Text(), nullable=False),
    sa.Column("evaluation_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("strategy_id", sa.Text(), nullable=False),
    sa.Column("strategy_version", sa.Text(), nullable=False),
    sa.Column("reference_window_size", sa.Integer(), nullable=False),
    sa.Column("decision", sa.Text(), nullable=False),
    sa.Column(
        "reasons", postgresql.ARRAY(sa.Text()), nullable=False, server_default=_TEXT_ARRAY_DEFAULT
    ),
    sa.Column("current_close", _NUMERIC, nullable=False),
    sa.Column("current_volume", sa.BigInteger(), nullable=False),
    sa.Column("reference_high", _NUMERIC, nullable=False),
    sa.Column("reference_average_volume", _NUMERIC, nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["target_evidence_package_governance_id"], ["evidence_package.governance_id"]
    ),
    sa.CheckConstraint("reference_window_size >= 1", name="reference_window_size_positive"),
    sa.CheckConstraint("current_volume >= 0", name="current_volume_non_negative"),
    sa.CheckConstraint(f"bar_interval IN ({_enum_sql(_BAR_INTERVALS)})", name="bar_interval_valid"),
    sa.CheckConstraint(f"decision IN ({_enum_sql(_TRADING_DECISIONS)})", name="decision_valid"),
)


def upgrade() -> None:
    """Create the decision_candidate table."""
    bind = op.get_bind()
    decision_candidate.create(bind=bind)


def downgrade() -> None:
    """Drop the decision_candidate table."""
    bind = op.get_bind()
    decision_candidate.drop(bind=bind)
