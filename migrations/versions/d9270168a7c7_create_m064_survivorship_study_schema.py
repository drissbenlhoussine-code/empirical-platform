"""create m064 survivorship study schema

Revision ID: d9270168a7c7
Revises: 63e46fdef1c7
Create Date: 2026-08-10 00:00:00.000000

MILESTONE-064: creates `instrument_master` (stable cross-time instrument
identity), `universe_authority` (versioned universe identity),
`membership_record` (immutable effective-dated membership facts),
`survivorship_study` (one row per survivorship-aware robustness study, with
an embedded `CURRENT_UNIVERSE_BIAS_STRESS` diagnostic summary referencing a
genuine, separately persisted M063 `robustness_study` row), and
`survivorship_window` (N child rows, one per declared window, carrying its
own eligible/evaluated/missing-data-excluded instrument-id snapshot).
Purely additive: no M020-M063 table is dropped, renamed, or altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d9270168a7c7"
down_revision: str | None = "63e46fdef1c7"
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

# Minimal shadow declarations of frozen predecessor tables this revision's
# own foreign keys reference -- needed only so SQLAlchemy can resolve them
# within this revision's own MetaData object; never created or dropped
# here (mirrors the M063 migration's own shadow-declaration precedent).
historical_backtest_run = sa.Table(
    "historical_backtest_run",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
)

robustness_study = sa.Table(
    "robustness_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
)

instrument_master = sa.Table(
    "instrument_master",
    _METADATA,
    sa.Column("instrument_id", sa.Text(), nullable=False),
    sa.Column("canonical_symbol", sa.Text(), nullable=False),
    sa.Column("instrument_type", sa.Text(), nullable=False),
    sa.Column("exchange_or_venue", sa.Text(), nullable=True),
    sa.Column("external_identifier", sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint("instrument_id"),
    sa.UniqueConstraint("canonical_symbol"),
    sa.CheckConstraint("instrument_type IN ('EQUITY', 'ETF')", name="instrument_type_valid"),
)

universe_authority = sa.Table(
    "universe_authority",
    _METADATA,
    sa.Column("universe_id", sa.Text(), nullable=False),
    sa.Column("universe_version", sa.Text(), nullable=False),
    sa.Column("source_kind", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("universe_id", "universe_version"),
)

membership_record = sa.Table(
    "membership_record",
    _METADATA,
    sa.Column("universe_id", sa.Text(), nullable=False),
    sa.Column("universe_version", sa.Text(), nullable=False),
    sa.Column("instrument_id", sa.Text(), nullable=False),
    sa.Column("effective_from", _TIMESTAMPTZ, nullable=False),
    sa.Column("effective_to", _TIMESTAMPTZ, nullable=True),
    sa.Column("membership_status", sa.Text(), nullable=False),
    sa.Column("source_kind", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("universe_id", "universe_version", "instrument_id", "effective_from"),
    sa.ForeignKeyConstraint(
        ["universe_id", "universe_version"],
        ["universe_authority.universe_id", "universe_authority.universe_version"],
    ),
    sa.ForeignKeyConstraint(["instrument_id"], ["instrument_master.instrument_id"]),
    sa.CheckConstraint(
        "membership_status IN ('ACTIVE', 'INACTIVE', 'DELISTED_LIKE', 'INACTIVE_LIKE')",
        name="membership_status_valid",
    ),
    sa.CheckConstraint(
        "effective_to IS NULL OR effective_to > effective_from", name="effective_range_valid"
    ),
)

survivorship_study = sa.Table(
    "survivorship_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_id", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_version", sa.Text(), nullable=False),
    sa.Column("dataset_bundle_sha256", sa.Text(), nullable=False),
    sa.Column("dataset_source_kind", sa.Text(), nullable=False),
    sa.Column("universe_id", sa.Text(), nullable=False),
    sa.Column("universe_version", sa.Text(), nullable=False),
    sa.Column("universe_membership_model", sa.Text(), nullable=False),
    sa.Column("membership_manifest_hash", sa.Text(), nullable=False),
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
    sa.Column("regime_policy_id", sa.Text(), nullable=False),
    sa.Column("regime_policy_version", sa.Text(), nullable=False),
    sa.Column("corporate_action_handling", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("classification", sa.Text(), nullable=False),
    sa.Column("window_count", sa.BigInteger(), nullable=False),
    sa.Column("total_evaluated_cutoff_count", sa.BigInteger(), nullable=False),
    sa.Column("total_simulated_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("total_executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("positive_net_pnl_window_count", sa.BigInteger(), nullable=False),
    sa.Column("negative_net_pnl_window_count", sa.BigInteger(), nullable=False),
    sa.Column("positive_total_r_window_count", sa.BigInteger(), nullable=False),
    sa.Column("negative_total_r_window_count", sa.BigInteger(), nullable=False),
    sa.Column("median_window_net_pnl", _PRICE, nullable=False),
    sa.Column("median_window_total_r", _RATIO, nullable=False),
    sa.Column("best_window_by_net_pnl_id", sa.Text(), nullable=False),
    sa.Column("best_window_by_net_pnl_value", _PRICE, nullable=False),
    sa.Column("worst_window_by_net_pnl_id", sa.Text(), nullable=False),
    sa.Column("worst_window_by_net_pnl_value", _PRICE, nullable=False),
    sa.Column("best_window_by_total_r_id", sa.Text(), nullable=False),
    sa.Column("best_window_by_total_r_value", _RATIO, nullable=False),
    sa.Column("worst_window_by_total_r_id", sa.Text(), nullable=False),
    sa.Column("worst_window_by_total_r_value", _RATIO, nullable=False),
    sa.Column("all_window_net_pnl_total", _PRICE, nullable=False),
    sa.Column("all_window_total_r_total", _RATIO, nullable=False),
    sa.Column("excluding_best_window_net_pnl_total", _PRICE, nullable=False),
    sa.Column("excluding_best_window_total_r_total", _RATIO, nullable=False),
    sa.Column("largest_positive_window_share_of_positive_pnl", _RATIO, nullable=True),
    sa.Column("largest_negative_window_share_of_absolute_negative_pnl", _RATIO, nullable=True),
    sa.Column("stress_study_governance_id", sa.Text(), nullable=False),
    sa.Column("stress_comparison", sa.Text(), nullable=False),
    sa.Column("stress_full_universe_size", sa.BigInteger(), nullable=False),
    sa.Column("stress_canonical_total_executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("stress_total_executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("stress_canonical_net_pnl_total", _PRICE, nullable=False),
    sa.Column("stress_net_pnl_total", _PRICE, nullable=False),
    sa.Column("stress_canonical_total_r_total", _RATIO, nullable=False),
    sa.Column("stress_total_r_total", _RATIO, nullable=False),
    sa.Column("stress_canonical_best_window_by_net_pnl_id", sa.Text(), nullable=False),
    sa.Column("stress_canonical_best_window_by_net_pnl_value", _PRICE, nullable=False),
    sa.Column("stress_best_window_by_net_pnl_id", sa.Text(), nullable=False),
    sa.Column("stress_best_window_by_net_pnl_value", _PRICE, nullable=False),
    sa.Column("stress_canonical_worst_window_by_net_pnl_id", sa.Text(), nullable=False),
    sa.Column("stress_canonical_worst_window_by_net_pnl_value", _PRICE, nullable=False),
    sa.Column("stress_worst_window_by_net_pnl_id", sa.Text(), nullable=False),
    sa.Column("stress_worst_window_by_net_pnl_value", _PRICE, nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["universe_id", "universe_version"],
        ["universe_authority.universe_id", "universe_authority.universe_version"],
    ),
    sa.ForeignKeyConstraint(["stress_study_governance_id"], ["robustness_study.governance_id"]),
    sa.CheckConstraint("status IN ('STUDY_COMPLETED')", name="status_valid"),
    sa.CheckConstraint(
        "classification IN ('INSUFFICIENT_SAMPLE', "
        "'SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN')",
        name="classification_valid",
    ),
    sa.CheckConstraint(
        "stress_comparison IN ('CURRENT_UNIVERSE_BIAS_STRESS_IDENTICAL', "
        "'CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS')",
        name="stress_comparison_valid",
    ),
    sa.CheckConstraint("window_count >= 1", name="window_count_positive"),
)

survivorship_window = sa.Table(
    "survivorship_window",
    _METADATA,
    sa.Column("study_runtime_id", _UUID, nullable=False),
    sa.Column("window_id", sa.Text(), nullable=False),
    sa.Column("sequence_index", sa.BigInteger(), nullable=False),
    sa.Column("data_start_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("data_end_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("scoring_start_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("scoring_end_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("eligible_instrument_ids", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("evaluated_instrument_ids", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("missing_data_excluded_instrument_ids", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("backtest_run_governance_id", sa.Text(), nullable=True),
    sa.Column("backtest_run_runtime_id", _UUID, nullable=True),
    sa.Column("regime_label", sa.Text(), nullable=False),
    sa.Column("realized_volatility", _RATIO, nullable=False),
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
    sa.PrimaryKeyConstraint("study_runtime_id", "window_id"),
    sa.UniqueConstraint("study_runtime_id", "sequence_index"),
    sa.ForeignKeyConstraint(
        ["study_runtime_id"], ["survivorship_study.runtime_id"], ondelete="CASCADE"
    ),
    sa.ForeignKeyConstraint(
        ["backtest_run_governance_id"], ["historical_backtest_run.governance_id"]
    ),
    sa.ForeignKeyConstraint(["backtest_run_runtime_id"], ["historical_backtest_run.runtime_id"]),
    sa.CheckConstraint(
        "regime_label IN ('LOW_VOLATILITY', 'NORMAL_VOLATILITY', 'HIGH_VOLATILITY')",
        name="regime_label_valid",
    ),
    sa.CheckConstraint(
        "scoring_start_timestamp >= data_start_timestamp "
        "AND scoring_end_timestamp <= data_end_timestamp "
        "AND scoring_start_timestamp <= scoring_end_timestamp",
        name="boundaries_coherent",
    ),
    sa.CheckConstraint(
        "(backtest_run_governance_id IS NULL) = (backtest_run_runtime_id IS NULL)",
        name="backtest_run_reference_coherent",
    ),
)


def upgrade() -> None:
    """Create the instrument_master, universe_authority, membership_record,
    survivorship_study, and survivorship_window tables."""
    bind = op.get_bind()
    instrument_master.create(bind=bind)
    universe_authority.create(bind=bind)
    membership_record.create(bind=bind)
    survivorship_study.create(bind=bind)
    survivorship_window.create(bind=bind)


def downgrade() -> None:
    """Drop the M064 tables in dependency order."""
    bind = op.get_bind()
    survivorship_window.drop(bind=bind)
    survivorship_study.drop(bind=bind)
    membership_record.drop(bind=bind)
    universe_authority.drop(bind=bind)
    instrument_master.drop(bind=bind)
