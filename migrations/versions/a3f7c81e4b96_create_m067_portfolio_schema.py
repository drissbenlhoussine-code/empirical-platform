"""create m067 portfolio schema

Revision ID: a3f7c81e4b96
Revises: f18a6b3d9e42
Create Date: 2026-08-11 00:00:00.000000

MILESTONE-067: creates `portfolio_study` (one row per post-hoc portfolio
capital-allocation evaluation of an already-frozen M064
`SurvivorshipAwareRobustnessStudy`, with upstream authority lineage, the
capital policy that produced it, allocation/rejection counts, and
equity/drawdown/exposure summary evidence), `portfolio_allocation_decision`
(one row per candidate historical trade opportunity -- allocated or
rejected, with reason), `portfolio_equity_observation` (one row per
portfolio equity checkpoint), and `portfolio_capital_sensitivity` (one row
per predeclared capital-sensitivity scenario). Purely additive: no
M020-M066 table is dropped, renamed, or altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3f7c81e4b96"
down_revision: str | None = "f18a6b3d9e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
_PRICE = sa.Numeric(precision=18, scale=6)
_RATIO = sa.Numeric(precision=30, scale=15)
_TIMESTAMP = sa.DateTime(timezone=True)

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

# Minimal shadow declaration of the frozen M064 predecessor table this
# revision's own foreign key references -- needed only so SQLAlchemy can
# resolve it within this revision's own MetaData object; never created or
# dropped here (mirrors the M065/M066 migrations' own shadow-declaration
# precedent).
survivorship_study = sa.Table(
    "survivorship_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
)

portfolio_study = sa.Table(
    "portfolio_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("source_study_governance_id", sa.Text(), nullable=False),
    sa.Column("source_study_runtime_id", _UUID, nullable=False),
    sa.Column("dataset_bundle_id", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_version", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_sha256", sa.Text(), nullable=False),
    sa.Column("dataset_source_kind", sa.Text(), nullable=False),
    sa.Column("universe_id", sa.Text(), nullable=False),
    sa.Column("universe_version", sa.Text(), nullable=False),
    sa.Column("membership_manifest_hash", sa.Text(), nullable=False),
    sa.Column("strategy_id", sa.Text(), nullable=False),
    sa.Column("strategy_version", sa.Text(), nullable=False),
    sa.Column("ranking_model_id", sa.Text(), nullable=False),
    sa.Column("ranking_model_version", sa.Text(), nullable=False),
    sa.Column("risk_policy_id", sa.Text(), nullable=False),
    sa.Column("risk_policy_version", sa.Text(), nullable=False),
    sa.Column("sizing_policy_id", sa.Text(), nullable=False),
    sa.Column("sizing_policy_version", sa.Text(), nullable=False),
    sa.Column("capital_policy_id", sa.Text(), nullable=False),
    sa.Column("capital_policy_version", sa.Text(), nullable=False),
    sa.Column("initial_capital", _PRICE, nullable=False),
    sa.Column("currency", sa.Text(), nullable=False),
    sa.Column("max_concurrent_positions", sa.BigInteger(), nullable=False),
    sa.Column("max_capital_utilization_percent", _RATIO, nullable=False),
    sa.Column("total_opportunities", sa.BigInteger(), nullable=False),
    sa.Column("allocated_count", sa.BigInteger(), nullable=False),
    sa.Column("rejected_count", sa.BigInteger(), nullable=False),
    sa.Column("rejected_insufficient_capital_count", sa.BigInteger(), nullable=False),
    sa.Column("rejected_max_concurrent_count", sa.BigInteger(), nullable=False),
    sa.Column("rejected_max_utilization_count", sa.BigInteger(), nullable=False),
    sa.Column("ending_capital", _PRICE, nullable=False),
    sa.Column("realized_pnl", _PRICE, nullable=False),
    sa.Column("portfolio_return_percent", _RATIO, nullable=False),
    sa.Column("peak_equity", _PRICE, nullable=False),
    sa.Column("max_drawdown", _PRICE, nullable=False),
    sa.Column("max_drawdown_percent", _RATIO, nullable=True),
    sa.Column("max_concurrent_positions_observed", sa.BigInteger(), nullable=False),
    sa.Column("average_concurrent_positions", _RATIO, nullable=True),
    sa.Column("peak_occupied_capital", _PRICE, nullable=False),
    sa.Column("peak_capital_utilization_percent", _RATIO, nullable=True),
    sa.Column("largest_instrument_positive_contribution_symbol", sa.Text(), nullable=True),
    sa.Column("largest_instrument_positive_contribution_amount", _PRICE, nullable=True),
    sa.Column("largest_instrument_negative_contribution_symbol", sa.Text(), nullable=True),
    sa.Column("largest_instrument_negative_contribution_amount", _PRICE, nullable=True),
    sa.Column("largest_position_contribution_trade_sequence", sa.BigInteger(), nullable=True),
    sa.Column("largest_position_contribution_amount", _PRICE, nullable=True),
    sa.Column("largest_window_contribution_window_id", sa.Text(), nullable=True),
    sa.Column("largest_window_contribution_amount", _PRICE, nullable=True),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["source_study_runtime_id"],
        ["survivorship_study.runtime_id"],
    ),
    sa.CheckConstraint("total_opportunities >= 0", name="total_opportunities_non_negative"),
    sa.CheckConstraint(
        "allocated_count + rejected_count = total_opportunities",
        name="allocation_counts_reconcile",
    ),
    sa.CheckConstraint("initial_capital > 0", name="initial_capital_positive"),
    sa.CheckConstraint(
        "max_concurrent_positions >= 1", name="max_concurrent_positions_at_least_one"
    ),
    sa.CheckConstraint(
        "max_capital_utilization_percent > 0 AND max_capital_utilization_percent <= 1",
        name="max_capital_utilization_percent_valid_range",
    ),
)

portfolio_allocation_decision = sa.Table(
    "portfolio_allocation_decision",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("opportunity_sequence", sa.BigInteger(), nullable=False),
    sa.Column("source_window_id", sa.Text(), nullable=False),
    sa.Column("trade_sequence", sa.BigInteger(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("scan_rank", sa.BigInteger(), nullable=False),
    sa.Column("entry_timestamp", _TIMESTAMP, nullable=False),
    sa.Column("exit_timestamp", _TIMESTAMP, nullable=False),
    sa.Column("risk_amount", _PRICE, nullable=False),
    sa.Column("net_pnl", _PRICE, nullable=False),
    sa.Column("decision", sa.Text(), nullable=False),
    sa.Column("rejection_reason", sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint("report_runtime_id", "opportunity_sequence"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["portfolio_study.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("risk_amount > 0", name="risk_amount_positive"),
    sa.CheckConstraint("decision IN ('ALLOCATED', 'REJECTED')", name="decision_valid"),
    sa.CheckConstraint(
        "rejection_reason IS NULL OR rejection_reason IN "
        "('INSUFFICIENT_AVAILABLE_CAPITAL', 'MAX_CONCURRENT_POSITIONS', "
        "'MAX_CAPITAL_UTILIZATION_EXCEEDED')",
        name="rejection_reason_valid",
    ),
    sa.CheckConstraint(
        "(decision = 'ALLOCATED' AND rejection_reason IS NULL) OR "
        "(decision = 'REJECTED' AND rejection_reason IS NOT NULL)",
        name="decision_reason_coherent",
    ),
)

portfolio_equity_observation = sa.Table(
    "portfolio_equity_observation",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("sequence_index", sa.BigInteger(), nullable=False),
    sa.Column("event_timestamp", _TIMESTAMP, nullable=False),
    sa.Column("event_kind", sa.Text(), nullable=False),
    sa.Column("equity", _PRICE, nullable=False),
    sa.Column("occupied_capital", _PRICE, nullable=False),
    sa.Column("available_capital", _PRICE, nullable=False),
    sa.Column("open_position_count", sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint("report_runtime_id", "sequence_index"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["portfolio_study.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("event_kind IN ('OPEN', 'CLOSE')", name="event_kind_valid"),
    sa.CheckConstraint("occupied_capital >= 0", name="occupied_capital_non_negative"),
    sa.CheckConstraint("open_position_count >= 0", name="open_position_count_non_negative"),
)

portfolio_capital_sensitivity = sa.Table(
    "portfolio_capital_sensitivity",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("label", sa.Text(), nullable=False),
    sa.Column("capital_policy_id", sa.Text(), nullable=False),
    sa.Column("initial_capital", _PRICE, nullable=False),
    sa.Column("max_concurrent_positions", sa.BigInteger(), nullable=False),
    sa.Column("allocated_count", sa.BigInteger(), nullable=False),
    sa.Column("rejected_count", sa.BigInteger(), nullable=False),
    sa.Column("ending_capital", _PRICE, nullable=False),
    sa.Column("realized_pnl", _PRICE, nullable=False),
    sa.Column("max_drawdown", _PRICE, nullable=False),
    sa.PrimaryKeyConstraint("report_runtime_id", "label"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["portfolio_study.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        "label IN ('CANONICAL', 'REDUCED_CAPITAL', 'TIGHTER_MAX_CONCURRENCY')",
        name="label_valid",
    ),
)


def upgrade() -> None:
    """Create the portfolio_study, portfolio_allocation_decision,
    portfolio_equity_observation, and portfolio_capital_sensitivity
    tables."""
    bind = op.get_bind()
    portfolio_study.create(bind=bind)
    portfolio_allocation_decision.create(bind=bind)
    portfolio_equity_observation.create(bind=bind)
    portfolio_capital_sensitivity.create(bind=bind)


def downgrade() -> None:
    """Drop the M067 tables in dependency order."""
    bind = op.get_bind()
    portfolio_capital_sensitivity.drop(bind=bind)
    portfolio_equity_observation.drop(bind=bind)
    portfolio_allocation_decision.drop(bind=bind)
    portfolio_study.drop(bind=bind)
