"""create m058 trading opportunity scan schema

Revision ID: 8e6693903b41
Revises: a1c93f7e2b04
Create Date: 2026-08-09 00:00:00.000000

MILESTONE-058: creates the `trading_opportunity_scan` and
`trading_opportunity_scan_evaluation` tables. `TradingOpportunityScan`, like
`DecisionCandidate` (M057), is immutable and single-insert -- no `*_transition`
child table. `trading_opportunity_scan_evaluation` is a genuine child table
(one row per instrument evaluated in the scan, in universe order via
`position`), foreign-keying to both its own scan and the already-frozen
`decision_candidate` table by governance_id -- deliberately NOT duplicating
`decision_candidate`'s own measurements/reasons columns; a scan's full
per-instrument explanation is reconstructed by joining back to
`decision_candidate` at read time (see
MILESTONE_058_TRADING_OPPORTUNITY_SCANNER_SCOPE_AND_DESIGN.md Section 8).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8e6693903b41"
down_revision: str | None = "a1c93f7e2b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
_TIMESTAMPTZ = sa.DateTime(timezone=True)

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

# Minimal shadow declarations of the M022/M057 tables this revision's own
# foreign keys reference -- needed only so SQLAlchemy can resolve them within
# this revision's own MetaData object; never created or dropped here.
evidence_package = sa.Table(
    "evidence_package",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)
decision_candidate = sa.Table(
    "decision_candidate",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)

trading_opportunity_scan = sa.Table(
    "trading_opportunity_scan",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("target_evidence_package_governance_id", sa.Text(), nullable=False),
    sa.Column("strategy_id", sa.Text(), nullable=False),
    sa.Column("strategy_version", sa.Text(), nullable=False),
    sa.Column("ranking_model_id", sa.Text(), nullable=False),
    sa.Column("ranking_model_version", sa.Text(), nullable=False),
    sa.Column("evaluation_cutoff", _TIMESTAMPTZ, nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["target_evidence_package_governance_id"], ["evidence_package.governance_id"]
    ),
)

trading_opportunity_scan_evaluation = sa.Table(
    "trading_opportunity_scan_evaluation",
    _METADATA,
    sa.Column("scan_runtime_id", _UUID, nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("decision_candidate_governance_id", sa.Text(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("decision", sa.Text(), nullable=False),
    sa.Column("rank", sa.Integer(), nullable=True),
    sa.Column("score", sa.Numeric(precision=30, scale=15), nullable=True),
    sa.PrimaryKeyConstraint("scan_runtime_id", "position"),
    sa.ForeignKeyConstraint(["scan_runtime_id"], ["trading_opportunity_scan.runtime_id"]),
    sa.ForeignKeyConstraint(
        ["decision_candidate_governance_id"], ["decision_candidate.governance_id"]
    ),
    sa.UniqueConstraint(
        "scan_runtime_id",
        "instrument_symbol",
        name="uq_trading_opportunity_scan_evaluation_instrument",
    ),
    sa.UniqueConstraint(
        "scan_runtime_id",
        "decision_candidate_governance_id",
        name="uq_trading_opportunity_scan_evaluation_decision_candidate",
    ),
    sa.CheckConstraint("position >= 0", name="position_non_negative"),
    sa.CheckConstraint("decision IN ('LONG_CANDIDATE', 'NO_TRADE')", name="decision_valid"),
    sa.CheckConstraint(
        "(decision = 'LONG_CANDIDATE' AND rank IS NOT NULL AND score IS NOT NULL) "
        "OR (decision = 'NO_TRADE' AND rank IS NULL AND score IS NULL)",
        name="rank_score_matches_decision",
    ),
    sa.CheckConstraint("rank IS NULL OR rank >= 1", name="rank_positive"),
)


def upgrade() -> None:
    """Create the trading_opportunity_scan and
    trading_opportunity_scan_evaluation tables."""
    bind = op.get_bind()
    trading_opportunity_scan.create(bind=bind)
    trading_opportunity_scan_evaluation.create(bind=bind)


def downgrade() -> None:
    """Drop the trading_opportunity_scan_evaluation and
    trading_opportunity_scan tables, in dependency order."""
    bind = op.get_bind()
    trading_opportunity_scan_evaluation.drop(bind=bind)
    trading_opportunity_scan.drop(bind=bind)
