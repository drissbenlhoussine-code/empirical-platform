"""create m068 portfolio dependence schema

Revision ID: c4d8f6a29b17
Revises: a3f7c81e4b96
Create Date: 2026-08-11 00:00:00.000000

MILESTONE-068: creates `portfolio_dependence_report` (one row per
post-hoc cross-instrument dependence evaluation of an already-frozen
M067 `PortfolioEvidenceReport`, with upstream authority lineage, the
estimation policy that produced it, pair/concentration summary evidence,
and a conservative dependence classification),
`portfolio_dependence_pair` (one row per canonically-ordered pairwise
historical correlation computation), and
`portfolio_dependence_concurrent_state` (one row per genuinely
concurrent open-exposure snapshot derived from the real M067 event
timeline). Purely additive: no M020-M067 table is dropped, renamed, or
altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4d8f6a29b17"
down_revision: str | None = "a3f7c81e4b96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
_RATIO = sa.Numeric(precision=30, scale=15)

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

# Minimal shadow declaration of the frozen M067 predecessor table this
# revision's own foreign key references -- needed only so SQLAlchemy can
# resolve it within this revision's own MetaData object; never created or
# dropped here (mirrors the M064-M067 migrations' own shadow-declaration
# precedent).
portfolio_study = sa.Table(
    "portfolio_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
)

portfolio_dependence_report = sa.Table(
    "portfolio_dependence_report",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("source_portfolio_study_governance_id", sa.Text(), nullable=False),
    sa.Column("source_portfolio_study_runtime_id", _UUID, nullable=False),
    sa.Column("source_study_governance_id", sa.Text(), nullable=False),
    sa.Column("source_study_runtime_id", _UUID, nullable=False),
    sa.Column("dataset_bundle_id", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_version", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_sha256", sa.Text(), nullable=False),
    sa.Column("dataset_source_kind", sa.Text(), nullable=False),
    sa.Column("capital_policy_id", sa.Text(), nullable=False),
    sa.Column("capital_policy_version", sa.Text(), nullable=False),
    sa.Column("estimation_policy_id", sa.Text(), nullable=False),
    sa.Column("estimation_policy_version", sa.Text(), nullable=False),
    sa.Column("estimation_lookback_bar_count", sa.BigInteger(), nullable=False),
    sa.Column("estimation_minimum_overlapping_observations", sa.BigInteger(), nullable=False),
    sa.Column("instrument_count", sa.BigInteger(), nullable=False),
    sa.Column("pair_count", sa.BigInteger(), nullable=False),
    sa.Column("defined_pair_count", sa.BigInteger(), nullable=False),
    sa.Column("undefined_pair_count", sa.BigInteger(), nullable=False),
    sa.Column("highest_pair_a", sa.Text(), nullable=True),
    sa.Column("highest_pair_b", sa.Text(), nullable=True),
    sa.Column("highest_pair_correlation", _RATIO, nullable=True),
    sa.Column("lowest_pair_a", sa.Text(), nullable=True),
    sa.Column("lowest_pair_b", sa.Text(), nullable=True),
    sa.Column("lowest_pair_correlation", _RATIO, nullable=True),
    sa.Column("concurrent_exposure_state_count", sa.BigInteger(), nullable=False),
    sa.Column("peak_nominal_concentration", _RATIO, nullable=True),
    sa.Column("peak_dependence_aware_concentration", _RATIO, nullable=True),
    sa.Column("correlation_instability_observed", sa.Boolean(), nullable=False),
    sa.Column("max_window_instability_delta", _RATIO, nullable=True),
    sa.Column("stress_canonical_peak_dependence_aware_concentration", _RATIO, nullable=True),
    sa.Column("stress_perfect_correlation_concentration", _RATIO, nullable=True),
    sa.Column("classification", sa.Text(), nullable=False),
    sa.Column("limitations", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["source_portfolio_study_runtime_id"],
        ["portfolio_study.runtime_id"],
    ),
    sa.CheckConstraint("instrument_count >= 0", name="instrument_count_non_negative"),
    sa.CheckConstraint("pair_count >= 0", name="pair_count_non_negative"),
    sa.CheckConstraint(
        "defined_pair_count + undefined_pair_count = pair_count",
        name="pair_count_breakdown_consistent",
    ),
    sa.CheckConstraint(
        "classification IN ('INSUFFICIENT_DEPENDENCE_EVIDENCE', 'LOW_OBSERVED_DEPENDENCE', "
        "'MIXED_OBSERVED_DEPENDENCE', 'HIGH_OBSERVED_DEPENDENCE')",
        name="classification_valid",
    ),
)

portfolio_dependence_pair = sa.Table(
    "portfolio_dependence_pair",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("instrument_a", sa.Text(), nullable=False),
    sa.Column("instrument_b", sa.Text(), nullable=False),
    sa.Column("observation_count", sa.BigInteger(), nullable=False),
    sa.Column("estimation_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("estimation_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("correlation", _RATIO, nullable=True),
    sa.Column("status", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("report_runtime_id", "instrument_a", "instrument_b"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["portfolio_dependence_report.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("instrument_a <= instrument_b", name="canonical_pair_order"),
    sa.CheckConstraint("observation_count >= 0", name="observation_count_non_negative"),
    sa.CheckConstraint(
        "status IN ('DEFINED', 'INSUFFICIENT_OBSERVATIONS', 'UNDEFINED_ZERO_VARIANCE')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "(status = 'DEFINED' AND correlation IS NOT NULL) OR "
        "(status != 'DEFINED' AND correlation IS NULL)",
        name="correlation_status_consistent",
    ),
)

portfolio_dependence_concurrent_state = sa.Table(
    "portfolio_dependence_concurrent_state",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("state_sequence", sa.BigInteger(), nullable=False),
    sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("open_instruments", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("weights", postgresql.ARRAY(_RATIO), nullable=False),
    sa.Column("nominal_concentration", _RATIO, nullable=False),
    sa.Column("dependence_aware_concentration", _RATIO, nullable=True),
    sa.Column("undefined_pair_count", sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint("report_runtime_id", "state_sequence"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["portfolio_dependence_report.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("state_sequence >= 1", name="state_sequence_positive"),
    sa.CheckConstraint("undefined_pair_count >= 0", name="undefined_pair_count_non_negative"),
)


def upgrade() -> None:
    """Create the portfolio_dependence_report,
    portfolio_dependence_pair, and portfolio_dependence_concurrent_state
    tables."""
    bind = op.get_bind()
    portfolio_dependence_report.create(bind=bind)
    portfolio_dependence_pair.create(bind=bind)
    portfolio_dependence_concurrent_state.create(bind=bind)


def downgrade() -> None:
    """Drop the M068 tables in dependency order."""
    bind = op.get_bind()
    portfolio_dependence_concurrent_state.drop(bind=bind)
    portfolio_dependence_pair.drop(bind=bind)
    portfolio_dependence_report.drop(bind=bind)
