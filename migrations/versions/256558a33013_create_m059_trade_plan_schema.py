"""create m059 trade plan schema

Revision ID: 256558a33013
Revises: 8e6693903b41
Create Date: 2026-08-10 00:00:00.000000

MILESTONE-059: creates the `trade_plan` table. `TradePlan`, like
`DecisionCandidate` (M057) and `TradingOpportunityScan` (M058), is immutable
and single-insert -- no `*_transition` child table. Geometry columns
(entry/stop/target/risk/reward/reward_risk_ratio) are nullable: NULL for
`SOURCE_NOT_LONG_CANDIDATE`/`INVALID_STOP_GEOMETRY`/`INVALID_TARGET_GEOMETRY`
rejections (no valid geometry could be computed), populated for
`REWARD_RISK_BELOW_MINIMUM` rejections (valid geometry, just below the
policy threshold -- preserved for audit) and for every `APPROVED_PLAN`.
Foreign-keys to `trading_opportunity_scan`, `decision_candidate`, and
`evidence_package` by governance_id, mirroring the existing M057/M058
convention exactly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "256558a33013"
down_revision: str | None = "8e6693903b41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
_TIMESTAMPTZ = sa.DateTime(timezone=True)
_PRICE = sa.Numeric(precision=18, scale=6)
_RATIO = sa.Numeric(precision=30, scale=15)

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

# Minimal shadow declarations of the M022/M057/M058 tables this revision's
# own foreign keys reference -- needed only so SQLAlchemy can resolve them
# within this revision's own MetaData object; never created or dropped here.
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
    sa.Column("governance_id", sa.Text(), nullable=False),
)

trade_plan = sa.Table(
    "trade_plan",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("source_scan_governance_id", sa.Text(), nullable=False),
    sa.Column("source_decision_candidate_governance_id", sa.Text(), nullable=False),
    sa.Column("target_evidence_package_governance_id", sa.Text(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("evaluation_cutoff", _TIMESTAMPTZ, nullable=False),
    sa.Column("strategy_id", sa.Text(), nullable=False),
    sa.Column("strategy_version", sa.Text(), nullable=False),
    sa.Column("ranking_model_id", sa.Text(), nullable=False),
    sa.Column("ranking_model_version", sa.Text(), nullable=False),
    sa.Column("policy_id", sa.Text(), nullable=False),
    sa.Column("policy_version", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column(
        "reasons",
        postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column("entry_price", _PRICE, nullable=True),
    sa.Column("stop_price", _PRICE, nullable=True),
    sa.Column("target_price", _PRICE, nullable=True),
    sa.Column("risk_per_unit", _PRICE, nullable=True),
    sa.Column("reward_per_unit", _PRICE, nullable=True),
    sa.Column("reward_risk_ratio", _RATIO, nullable=True),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["source_scan_governance_id"], ["trading_opportunity_scan.governance_id"]
    ),
    sa.ForeignKeyConstraint(
        ["source_decision_candidate_governance_id"], ["decision_candidate.governance_id"]
    ),
    sa.ForeignKeyConstraint(
        ["target_evidence_package_governance_id"], ["evidence_package.governance_id"]
    ),
    sa.CheckConstraint("status IN ('APPROVED_PLAN', 'REJECTED_PLAN')", name="status_valid"),
    sa.CheckConstraint(
        "(status = 'APPROVED_PLAN' AND cardinality(reasons) = 0 "
        "AND entry_price IS NOT NULL AND stop_price IS NOT NULL AND target_price IS NOT NULL "
        "AND risk_per_unit IS NOT NULL AND reward_per_unit IS NOT NULL "
        "AND reward_risk_ratio IS NOT NULL) "
        "OR (status = 'REJECTED_PLAN' AND cardinality(reasons) = 1)",
        name="status_geometry_reasons_coherent",
    ),
)


def upgrade() -> None:
    """Create the trade_plan table."""
    bind = op.get_bind()
    trade_plan.create(bind=bind)


def downgrade() -> None:
    """Drop the trade_plan table."""
    bind = op.get_bind()
    trade_plan.drop(bind=bind)
