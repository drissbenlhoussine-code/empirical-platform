"""create m066 statistical evidence schema

Revision ID: f18a6b3d9e42
Revises: c275f69cee79
Create Date: 2026-08-11 00:00:00.000000

MILESTONE-066: creates `statistical_evidence_report` (one row per post-hoc
statistical evaluation of an already-frozen M064
`SurvivorshipAwareRobustnessStudy`, with upstream authority lineage,
descriptive trade/window evidence, the bootstrap policy that produced it,
drawdown-path evidence, and a conservative sample-breadth classification),
`statistical_evidence_bootstrap_interval` (one row per named bootstrap
confidence interval), and `statistical_evidence_sensitivity` (one row per
diagnostic excluding-best/worst sensitivity view). Purely additive: no
M020-M065 table is dropped, renamed, or altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f18a6b3d9e42"
down_revision: str | None = "c275f69cee79"
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

# Minimal shadow declaration of the frozen M064 predecessor table this
# revision's own foreign key references -- needed only so SQLAlchemy can
# resolve it within this revision's own MetaData object; never created or
# dropped here (mirrors the M064/M065 migrations' own shadow-declaration
# precedent).
survivorship_study = sa.Table(
    "survivorship_study",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
)

statistical_evidence_report = sa.Table(
    "statistical_evidence_report",
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
    sa.Column("trade_sample_size", sa.BigInteger(), nullable=False),
    sa.Column("window_sample_size", sa.BigInteger(), nullable=False),
    sa.Column("winning_trades", sa.BigInteger(), nullable=False),
    sa.Column("losing_trades", sa.BigInteger(), nullable=False),
    sa.Column("win_rate", _RATIO, nullable=True),
    sa.Column("net_pnl", _PRICE, nullable=False),
    sa.Column("total_r", _RATIO, nullable=False),
    sa.Column("mean_r_per_trade", _RATIO, nullable=True),
    sa.Column("median_r_per_trade", _RATIO, nullable=True),
    sa.Column("r_standard_deviation", _RATIO, nullable=True),
    sa.Column("best_trade_r", _RATIO, nullable=True),
    sa.Column("worst_trade_r", _RATIO, nullable=True),
    sa.Column("largest_trade_share_of_positive_pnl", _RATIO, nullable=True),
    sa.Column("profit_factor", _RATIO, nullable=True),
    sa.Column("positive_windows", sa.BigInteger(), nullable=False),
    sa.Column("negative_windows", sa.BigInteger(), nullable=False),
    sa.Column("median_window_net_pnl", _PRICE, nullable=True),
    sa.Column("median_window_total_r", _RATIO, nullable=True),
    sa.Column("bootstrap_policy_id", sa.Text(), nullable=False),
    sa.Column("bootstrap_policy_version", sa.Text(), nullable=False),
    sa.Column("bootstrap_method", sa.Text(), nullable=False),
    sa.Column("bootstrap_resample_count", sa.BigInteger(), nullable=False),
    sa.Column("bootstrap_seed", sa.BigInteger(), nullable=False),
    sa.Column("bootstrap_confidence_level", _RATIO, nullable=False),
    sa.Column("historical_realized_max_drawdown", _PRICE, nullable=False),
    sa.Column("median_resampled_max_drawdown", _PRICE, nullable=False),
    sa.Column("upper_tail_resampled_max_drawdown", _PRICE, nullable=False),
    sa.Column("worst_resampled_max_drawdown", _PRICE, nullable=False),
    sa.Column("classification", sa.Text(), nullable=False),
    sa.Column("limitations", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["source_study_runtime_id"],
        ["survivorship_study.runtime_id"],
    ),
    sa.CheckConstraint("trade_sample_size >= 0", name="trade_sample_size_non_negative"),
    sa.CheckConstraint("window_sample_size >= 0", name="window_sample_size_non_negative"),
    sa.CheckConstraint(
        "classification IN ('INSUFFICIENT_SAMPLE_BREADTH', 'LIMITED_SAMPLE_BREADTH', "
        "'MODERATE_SAMPLE_BREADTH', 'BROADER_HISTORICAL_SAMPLE_BREADTH')",
        name="classification_valid",
    ),
    sa.CheckConstraint(
        "bootstrap_method IN ('PERCENTILE_BOOTSTRAP')", name="bootstrap_method_valid"
    ),
)

statistical_evidence_bootstrap_interval = sa.Table(
    "statistical_evidence_bootstrap_interval",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("metric_name", sa.Text(), nullable=False),
    sa.Column("confidence_level", _RATIO, nullable=False),
    sa.Column("lower_bound", _RATIO, nullable=False),
    sa.Column("point_estimate", _RATIO, nullable=False),
    sa.Column("upper_bound", _RATIO, nullable=False),
    sa.Column("sample_size", sa.BigInteger(), nullable=False),
    sa.Column("resample_count", sa.BigInteger(), nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("method", sa.Text(), nullable=False),
    sa.Column("policy_version", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("report_runtime_id", "metric_name"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["statistical_evidence_report.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("lower_bound <= upper_bound", name="bounds_ordered"),
)

statistical_evidence_sensitivity = sa.Table(
    "statistical_evidence_sensitivity",
    _METADATA,
    sa.Column("report_runtime_id", _UUID, nullable=False),
    sa.Column("label", sa.Text(), nullable=False),
    sa.Column("sample_size", sa.BigInteger(), nullable=False),
    sa.Column("net_pnl", _PRICE, nullable=False),
    sa.Column("total_r", _RATIO, nullable=False),
    sa.Column("mean_r", _RATIO, nullable=True),
    sa.PrimaryKeyConstraint("report_runtime_id", "label"),
    sa.ForeignKeyConstraint(
        ["report_runtime_id"],
        ["statistical_evidence_report.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        "label IN ('CANONICAL', 'EXCLUDING_BEST_TRADE', 'EXCLUDING_WORST_TRADE', "
        "'EXCLUDING_BEST_WINDOW', 'EXCLUDING_WORST_WINDOW')",
        name="label_valid",
    ),
)


def upgrade() -> None:
    """Create the statistical_evidence_report,
    statistical_evidence_bootstrap_interval, and
    statistical_evidence_sensitivity tables."""
    bind = op.get_bind()
    statistical_evidence_report.create(bind=bind)
    statistical_evidence_bootstrap_interval.create(bind=bind)
    statistical_evidence_sensitivity.create(bind=bind)


def downgrade() -> None:
    """Drop the M066 tables in dependency order."""
    bind = op.get_bind()
    statistical_evidence_sensitivity.drop(bind=bind)
    statistical_evidence_bootstrap_interval.drop(bind=bind)
    statistical_evidence_report.drop(bind=bind)
