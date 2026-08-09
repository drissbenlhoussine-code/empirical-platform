"""create m062 validation study schema

Revision ID: a66cb39e7dba
Revises: 8c3b5d3b7f61
Create Date: 2026-08-10 00:00:00.000000

MILESTONE-062: creates `validation_study` (one row per historical
validation study) and `validation_segment` (exactly 3 child rows per
study: DEVELOPMENT_REFERENCE, HOLDOUT_1, HOLDOUT_2), immutable and
single-insert like every non-lifecycle record since M057 -- no
`*_transition` child table. Each `validation_segment` row references its
own, independently persisted M061 `historical_backtest_run` row by
governance_id/runtime_id (the unmodified M061 table, unchanged by this
migration) -- full per-trade detail for every segment remains reachable
through the existing, frozen M061 repository/CLI, never duplicated here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a66cb39e7dba"
down_revision: str | None = "8c3b5d3b7f61"
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

# Minimal shadow declaration of the M061 table this revision's own foreign
# key references -- needed only so SQLAlchemy can resolve it within this
# revision's own MetaData object; never created or dropped here.
historical_backtest_run = sa.Table(
    "historical_backtest_run",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
)

validation_study = sa.Table(
    "validation_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_id", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_version", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_sha256", sa.Text(), nullable=False),
    sa.Column("dataset_source_kind", sa.Text(), nullable=False),
    sa.Column("bar_interval", sa.Text(), nullable=False),
    sa.Column("instrument_universe", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("reference_window_size", sa.BigInteger(), nullable=False),
    sa.Column("strategy_id", sa.Text(), nullable=False),
    sa.Column("strategy_version", sa.Text(), nullable=False),
    sa.Column("ranking_model_id", sa.Text(), nullable=False),
    sa.Column("ranking_model_version", sa.Text(), nullable=False),
    sa.Column("risk_policy_id", sa.Text(), nullable=False),
    sa.Column("risk_policy_version", sa.Text(), nullable=False),
    sa.Column("sizing_policy_id", sa.Text(), nullable=False),
    sa.Column("sizing_policy_version", sa.Text(), nullable=False),
    sa.Column("execution_assumption_id", sa.Text(), nullable=False),
    sa.Column("execution_assumption_version", sa.Text(), nullable=False),
    sa.Column("outcome_model_id", sa.Text(), nullable=False),
    sa.Column("outcome_model_version", sa.Text(), nullable=False),
    sa.Column("cost_model_id", sa.Text(), nullable=False),
    sa.Column("cost_model_version", sa.Text(), nullable=False),
    sa.Column("holding_horizon_bars", sa.BigInteger(), nullable=False),
    sa.Column("supplied_account_equity", _PRICE, nullable=False),
    sa.Column("supplied_risk_percent", _RATIO, nullable=False),
    sa.Column("survivorship_bias_disclosure", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("classification", sa.Text(), nullable=False),
    sa.Column("holdout_1_net_pnl_delta", _PRICE, nullable=False),
    sa.Column("holdout_1_total_r_delta", _RATIO, nullable=False),
    sa.Column("holdout_2_net_pnl_delta", _PRICE, nullable=False),
    sa.Column("holdout_2_total_r_delta", _RATIO, nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.CheckConstraint("status IN ('STUDY_COMPLETED')", name="status_valid"),
    sa.CheckConstraint(
        "classification IN ('HOLDOUT_RESULTS_RECORDED', 'INSUFFICIENT_EVIDENCE')",
        name="classification_valid",
    ),
)

validation_segment = sa.Table(
    "validation_segment",
    _METADATA,
    sa.Column("study_runtime_id", _UUID, nullable=False),
    sa.Column("segment_id", sa.Text(), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.Column("data_start_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("data_end_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("scoring_start_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("scoring_end_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("warmup_bar_count", sa.BigInteger(), nullable=False),
    sa.Column("scoring_bar_count", sa.BigInteger(), nullable=False),
    sa.Column("buffer_bar_count", sa.BigInteger(), nullable=False),
    sa.Column("backtest_run_governance_id", sa.Text(), nullable=False),
    sa.Column("backtest_run_runtime_id", _UUID, nullable=False),
    sa.Column("evaluated_cutoff_count", sa.BigInteger(), nullable=False),
    sa.Column("simulated_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("win_count", sa.BigInteger(), nullable=False),
    sa.Column("loss_count", sa.BigInteger(), nullable=False),
    sa.Column("time_exit_count", sa.BigInteger(), nullable=False),
    sa.Column("no_entry_count", sa.BigInteger(), nullable=False),
    sa.Column("gross_pnl", _PRICE, nullable=False),
    sa.Column("net_pnl", _PRICE, nullable=False),
    sa.Column("average_net_pnl", _PRICE, nullable=True),
    sa.Column("average_r", _RATIO, nullable=True),
    sa.Column("total_r", _RATIO, nullable=False),
    sa.Column("win_rate", _RATIO, nullable=True),
    sa.Column("profit_factor", _RATIO, nullable=True),
    sa.Column("maximum_realized_pnl_drawdown", _PRICE, nullable=True),
    sa.PrimaryKeyConstraint("study_runtime_id", "segment_id"),
    sa.UniqueConstraint("study_runtime_id", "role"),
    sa.ForeignKeyConstraint(
        ["study_runtime_id"], ["validation_study.runtime_id"], ondelete="CASCADE"
    ),
    sa.ForeignKeyConstraint(
        ["backtest_run_governance_id"], ["historical_backtest_run.governance_id"]
    ),
    sa.ForeignKeyConstraint(["backtest_run_runtime_id"], ["historical_backtest_run.runtime_id"]),
    sa.CheckConstraint(
        "role IN ('DEVELOPMENT_REFERENCE', 'HOLDOUT_1', 'HOLDOUT_2')", name="role_valid"
    ),
    sa.CheckConstraint(
        "scoring_start_timestamp >= data_start_timestamp "
        "AND scoring_end_timestamp <= data_end_timestamp "
        "AND scoring_start_timestamp <= scoring_end_timestamp",
        name="boundaries_coherent",
    ),
)


def upgrade() -> None:
    """Create the validation_study and validation_segment tables."""
    bind = op.get_bind()
    validation_study.create(bind=bind)
    validation_segment.create(bind=bind)


def downgrade() -> None:
    """Drop the validation_segment and validation_study tables."""
    bind = op.get_bind()
    validation_segment.drop(bind=bind)
    validation_study.drop(bind=bind)
