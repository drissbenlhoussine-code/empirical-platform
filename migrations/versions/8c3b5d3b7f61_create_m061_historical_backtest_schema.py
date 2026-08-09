"""create m061 historical backtest schema

Revision ID: 8c3b5d3b7f61
Revises: 73f4a1d89b22
Create Date: 2026-08-09 19:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8c3b5d3b7f61"
down_revision: str | None = "73f4a1d89b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
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

historical_backtest_run = sa.Table(
    "historical_backtest_run",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("dataset_id", sa.Text(), nullable=False),
    sa.Column("dataset_version", sa.Text(), nullable=False),
    sa.Column("dataset_source_kind", sa.Text(), nullable=False),
    sa.Column("dataset_sha256", sa.Text(), nullable=False),
    sa.Column("bar_interval", sa.Text(), nullable=False),
    sa.Column(
        "universe_symbols",
        postgresql.ARRAY(sa.Text()),
        nullable=False,
    ),
    sa.Column("dataset_start_timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("dataset_end_timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("dataset_total_bars", sa.BigInteger(), nullable=False),
    sa.Column("reference_window_size", sa.BigInteger(), nullable=False),
    sa.Column("decision_cadence", sa.Text(), nullable=False),
    sa.Column("strategy_id", sa.Text(), nullable=False),
    sa.Column("strategy_version", sa.Text(), nullable=False),
    sa.Column("ranking_model_id", sa.Text(), nullable=False),
    sa.Column("ranking_model_version", sa.Text(), nullable=False),
    sa.Column("risk_policy_id", sa.Text(), nullable=False),
    sa.Column("risk_policy_version", sa.Text(), nullable=False),
    sa.Column("risk_policy_target_projection_percent", _RATIO, nullable=False),
    sa.Column("risk_policy_minimum_reward_risk_ratio", _RATIO, nullable=False),
    sa.Column("sizing_policy_id", sa.Text(), nullable=False),
    sa.Column("sizing_policy_version", sa.Text(), nullable=False),
    sa.Column("sizing_policy_maximum_risk_percent", _RATIO, nullable=False),
    sa.Column("sizing_policy_maximum_notional_percent", _RATIO, nullable=False),
    sa.Column("sizing_policy_allow_fractional_shares", sa.Boolean(), nullable=False),
    sa.Column("supplied_account_equity", _PRICE, nullable=False),
    sa.Column("supplied_risk_percent", _RATIO, nullable=False),
    sa.Column("execution_assumption_id", sa.Text(), nullable=False),
    sa.Column("execution_assumption_version", sa.Text(), nullable=False),
    sa.Column("outcome_model_id", sa.Text(), nullable=False),
    sa.Column("outcome_model_version", sa.Text(), nullable=False),
    sa.Column("outcome_model_no_overnight", sa.Boolean(), nullable=False),
    sa.Column("cost_model_id", sa.Text(), nullable=False),
    sa.Column("cost_model_version", sa.Text(), nullable=False),
    sa.Column("cost_model_entry_slippage_bps", _RATIO, nullable=False),
    sa.Column("cost_model_exit_slippage_bps", _RATIO, nullable=False),
    sa.Column("cost_model_fixed_commission_per_side", _PRICE, nullable=False),
    sa.Column("ambiguity_policy", sa.Text(), nullable=False),
    sa.Column("holding_horizon_bars", sa.BigInteger(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("product_classification", sa.Text(), nullable=False),
    sa.Column("evaluated_cutoff_count", sa.BigInteger(), nullable=False),
    sa.Column("evaluated_opportunity_count", sa.BigInteger(), nullable=False),
    sa.Column("approved_trade_plan_count", sa.BigInteger(), nullable=False),
    sa.Column("approved_position_plan_count", sa.BigInteger(), nullable=False),
    sa.Column("simulated_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("win_count", sa.BigInteger(), nullable=False),
    sa.Column("loss_count", sa.BigInteger(), nullable=False),
    sa.Column("flat_count", sa.BigInteger(), nullable=False),
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
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.CheckConstraint("status IN ('COMPLETED')", name="status_valid"),
    sa.CheckConstraint(
        "product_classification IN "
        "('VALIDATION_ENGINE_PROVEN_STRATEGY_UNASSESSED', "
        "'VALIDATION_ENGINE_PROVEN_FIXTURE_RESULTS_RECORDED')",
        name="classification_valid",
    ),
    sa.CheckConstraint("ambiguity_policy IN ('STOP_FIRST')", name="ambiguity_policy_valid"),
)

historical_backtest_trade = sa.Table(
    "historical_backtest_trade",
    _METADATA,
    sa.Column("backtest_run_runtime_id", _UUID, nullable=False),
    sa.Column("trade_sequence", sa.BigInteger(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("evaluation_cutoff", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source_scan_reference", sa.Text(), nullable=False),
    sa.Column("source_decision_candidate_reference", sa.Text(), nullable=False),
    sa.Column("source_trade_plan_reference", sa.Text(), nullable=False),
    sa.Column("source_position_plan_reference", sa.Text(), nullable=False),
    sa.Column("scan_rank", sa.BigInteger(), nullable=False),
    sa.Column("ranking_score", _RATIO, nullable=False),
    sa.Column("entry_timestamp", sa.DateTime(timezone=True), nullable=True),
    sa.Column("planned_entry_price", _PRICE, nullable=False),
    sa.Column("simulated_entry_price", _PRICE, nullable=True),
    sa.Column("planned_stop_price", _PRICE, nullable=False),
    sa.Column("planned_target_price", _PRICE, nullable=False),
    sa.Column("exit_timestamp", sa.DateTime(timezone=True), nullable=True),
    sa.Column("exit_price", _PRICE, nullable=True),
    sa.Column("outcome", sa.Text(), nullable=False),
    sa.Column("ambiguity_policy", sa.Text(), nullable=False),
    sa.Column("ambiguity_triggered", sa.Boolean(), nullable=False),
    sa.Column("quantity", sa.BigInteger(), nullable=False),
    sa.Column("gross_pnl", _PRICE, nullable=False),
    sa.Column("transaction_costs", _PRICE, nullable=False),
    sa.Column("net_pnl", _PRICE, nullable=False),
    sa.Column("risk_amount", _PRICE, nullable=False),
    sa.Column("r_multiple", _RATIO, nullable=True),
    sa.Column("holding_bars", sa.BigInteger(), nullable=True),
    sa.PrimaryKeyConstraint("backtest_run_runtime_id", "trade_sequence"),
    sa.ForeignKeyConstraint(
        ["backtest_run_runtime_id"],
        ["historical_backtest_run.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        "outcome IN ('TARGET_HIT', 'STOP_HIT', 'TIME_EXIT', 'NO_ENTRY')",
        name="outcome_valid",
    ),
    sa.CheckConstraint("ambiguity_policy IN ('STOP_FIRST')", name="ambiguity_policy_valid"),
    sa.CheckConstraint(
        "(outcome = 'NO_ENTRY' AND entry_timestamp IS NULL AND simulated_entry_price IS NULL "
        "AND exit_timestamp IS NULL AND exit_price IS NULL AND holding_bars IS NULL "
        "AND gross_pnl = 0 AND transaction_costs = 0 AND net_pnl = 0 AND r_multiple IS NULL) "
        "OR (outcome <> 'NO_ENTRY' AND entry_timestamp IS NOT NULL "
        "AND simulated_entry_price IS NOT NULL AND exit_timestamp IS NOT NULL "
        "AND exit_price IS NOT NULL AND holding_bars IS NOT NULL)",
        name="outcome_shape_valid",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    historical_backtest_run.create(bind=bind)
    historical_backtest_trade.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    historical_backtest_trade.drop(bind=bind)
    historical_backtest_run.drop(bind=bind)
