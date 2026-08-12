"""create m070 research session schema

Revision ID: 83d5dbd9ec54
Revises: c4d8f6a29b17
Create Date: 2026-08-12 00:00:00.000000

MILESTONE-070: creates `research_session` (one row per one-command daily
research session orchestration run, binding its own dataset authority,
governance chain, and terminal outcome), `research_session_stage` (the
ordered stage manifest), and `research_session_decision` (one row per
ranked candidate the session evaluated). Purely additive: no M020-M069
table is dropped, renamed, or altered. Deliberately references frozen
authorities (dataset_snapshot, trading_opportunity_scan, decision_candidate,
trade_plan, position_plan, historical_backtest_run, campaign, run,
evidence_package) rather than copying their own content.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "83d5dbd9ec54"
down_revision: str | None = "c4d8f6a29b17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

# Minimal shadow declarations of frozen predecessor tables this
# revision's own foreign keys reference -- needed only so SQLAlchemy can
# resolve them within this revision's own MetaData object; never created
# or dropped here (mirrors the M064-M069 migrations' own shadow
# -declaration precedent).
campaign = sa.Table(
    "campaign",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)
run = sa.Table(
    "run",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)
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
    sa.Column("governance_id", sa.Text(), nullable=False),
)
position_plan = sa.Table(
    "position_plan",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)
historical_backtest_run = sa.Table(
    "historical_backtest_run",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)
dataset_snapshot = sa.Table(
    "dataset_snapshot",
    _METADATA,
    sa.Column("dataset_id", sa.Text(), nullable=False),
    sa.Column("dataset_version", sa.Text(), nullable=False),
)

research_session = sa.Table(
    "research_session",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
    sa.Column("requested_universe", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("data_source", sa.Text(), nullable=False),
    sa.Column("dataset_id", sa.Text(), nullable=True),
    sa.Column("dataset_version", sa.Text(), nullable=True),
    sa.Column("dataset_sha256", sa.Text(), nullable=True),
    sa.Column("strategy_id", sa.Text(), nullable=True),
    sa.Column("strategy_version", sa.Text(), nullable=True),
    sa.Column("ranking_model_id", sa.Text(), nullable=True),
    sa.Column("ranking_model_version", sa.Text(), nullable=True),
    sa.Column("risk_policy_id", sa.Text(), nullable=True),
    sa.Column("risk_policy_version", sa.Text(), nullable=True),
    sa.Column("sizing_policy_id", sa.Text(), nullable=True),
    sa.Column("sizing_policy_version", sa.Text(), nullable=True),
    sa.Column("campaign_governance_id", sa.Text(), nullable=False),
    sa.Column("run_governance_id", sa.Text(), nullable=False),
    sa.Column("evidence_package_governance_id", sa.Text(), nullable=False),
    sa.Column("scan_governance_id", sa.Text(), nullable=True),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("failed_stage", sa.Text(), nullable=True),
    sa.Column("failure_type", sa.Text(), nullable=True),
    sa.Column("failure_message", sa.Text(), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("candidate_count", sa.BigInteger(), nullable=False),
    sa.Column("accepted_trade_plan_count", sa.BigInteger(), nullable=False),
    sa.Column("rejected_trade_plan_count", sa.BigInteger(), nullable=False),
    sa.Column("position_plan_count", sa.BigInteger(), nullable=False),
    sa.Column("backtest_run_governance_id", sa.Text(), nullable=True),
    sa.Column("backtest_evaluated_opportunity_count", sa.BigInteger(), nullable=True),
    sa.Column("backtest_executed_trade_count", sa.BigInteger(), nullable=True),
    sa.Column("limitations", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(
        ["dataset_id", "dataset_version"],
        ["dataset_snapshot.dataset_id", "dataset_snapshot.dataset_version"],
    ),
    sa.ForeignKeyConstraint(["campaign_governance_id"], ["campaign.governance_id"]),
    sa.ForeignKeyConstraint(["run_governance_id"], ["run.governance_id"]),
    sa.ForeignKeyConstraint(["evidence_package_governance_id"], ["evidence_package.governance_id"]),
    sa.ForeignKeyConstraint(["scan_governance_id"], ["trading_opportunity_scan.governance_id"]),
    sa.ForeignKeyConstraint(
        ["backtest_run_governance_id"], ["historical_backtest_run.governance_id"]
    ),
    sa.CheckConstraint(
        "status IN ('COMPLETED', 'FAILED')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "(status = 'COMPLETED' AND failed_stage IS NULL AND failure_type IS NULL "
        "AND failure_message IS NULL AND completed_at IS NOT NULL) OR "
        "(status = 'FAILED' AND failed_stage IS NOT NULL AND failure_type IS NOT NULL "
        "AND failure_message IS NOT NULL)",
        name="status_failure_metadata_consistent",
    ),
    sa.CheckConstraint("candidate_count >= 0", name="candidate_count_non_negative"),
    sa.CheckConstraint(
        "accepted_trade_plan_count >= 0 AND rejected_trade_plan_count >= 0",
        name="trade_plan_counts_non_negative",
    ),
    sa.CheckConstraint("position_plan_count >= 0", name="position_plan_count_non_negative"),
    sa.CheckConstraint(
        "position_plan_count <= accepted_trade_plan_count",
        name="position_plan_count_bounded",
    ),
)

research_session_stage = sa.Table(
    "research_session_stage",
    _METADATA,
    sa.Column("session_runtime_id", _UUID, nullable=False),
    sa.Column("stage_sequence", sa.BigInteger(), nullable=False),
    sa.Column("stage_name", sa.Text(), nullable=False),
    sa.Column("stage_version", sa.Text(), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("input_authority", sa.Text(), nullable=False),
    sa.Column("output_identity", sa.Text(), nullable=True),
    sa.Column("error_type", sa.Text(), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint("session_runtime_id", "stage_sequence"),
    sa.ForeignKeyConstraint(
        ["session_runtime_id"],
        ["research_session.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("stage_sequence >= 1", name="stage_sequence_positive"),
    sa.CheckConstraint(
        "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')",
        name="stage_status_valid",
    ),
)

research_session_decision = sa.Table(
    "research_session_decision",
    _METADATA,
    sa.Column("session_runtime_id", _UUID, nullable=False),
    sa.Column("decision_sequence", sa.BigInteger(), nullable=False),
    sa.Column("rank", sa.BigInteger(), nullable=True),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("decision_candidate_governance_id", sa.Text(), nullable=False),
    sa.Column("scan_decision", sa.Text(), nullable=False),
    sa.Column("trade_plan_governance_id", sa.Text(), nullable=True),
    sa.Column("trade_plan_decision", sa.Text(), nullable=True),
    sa.Column("position_plan_governance_id", sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint("session_runtime_id", "decision_sequence"),
    sa.ForeignKeyConstraint(
        ["session_runtime_id"],
        ["research_session.runtime_id"],
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["decision_candidate_governance_id"], ["decision_candidate.governance_id"]
    ),
    sa.ForeignKeyConstraint(["trade_plan_governance_id"], ["trade_plan.governance_id"]),
    sa.ForeignKeyConstraint(["position_plan_governance_id"], ["position_plan.governance_id"]),
    sa.CheckConstraint("decision_sequence >= 1", name="decision_sequence_positive"),
    sa.CheckConstraint("rank IS NULL OR rank >= 1", name="rank_positive_when_set"),
)


def upgrade() -> None:
    """Create the research_session, research_session_stage, and
    research_session_decision tables."""
    bind = op.get_bind()
    research_session.create(bind=bind)
    research_session_stage.create(bind=bind)
    research_session_decision.create(bind=bind)


def downgrade() -> None:
    """Drop the M070 tables in dependency order."""
    bind = op.get_bind()
    research_session_decision.drop(bind=bind)
    research_session_stage.drop(bind=bind)
    research_session.drop(bind=bind)
