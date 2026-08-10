"""create m065 dataset snapshot schema

Revision ID: c275f69cee79
Revises: d9270168a7c7
Create Date: 2026-08-10 00:00:00.000000

MILESTONE-065: creates `dataset_snapshot` (one row per immutable, versioned
local historical-data import), `dataset_snapshot_source_file` (its own raw
source-file manifest), `corporate_action` (declared split/reverse-split/
symbol-change events), and `corporate_action_semantics_stress` (the
diagnostic comparison between a correctly-adjusted and a naive/raw
interpretation, both run through the unmodified M061
`build_historical_backtest_run()`). Purely additive: no M020-M064 table is
dropped, renamed, or altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c275f69cee79"
down_revision: str | None = "d9270168a7c7"
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

dataset_snapshot = sa.Table(
    "dataset_snapshot",
    _METADATA,
    sa.Column("dataset_id", sa.Text(), nullable=False),
    sa.Column("dataset_version", sa.Text(), nullable=False),
    sa.Column("source_kind", sa.Text(), nullable=False),
    sa.Column("source_name", sa.Text(), nullable=False),
    sa.Column("source_reference", sa.Text(), nullable=False),
    sa.Column("license_note", sa.Text(), nullable=False),
    sa.Column("snapshot_created_at", _TIMESTAMPTZ, nullable=False),
    sa.Column("bar_interval", sa.Text(), nullable=False),
    sa.Column("start_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("end_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("instrument_count", sa.BigInteger(), nullable=False),
    sa.Column("total_row_count", sa.BigInteger(), nullable=False),
    sa.Column("file_count", sa.BigInteger(), nullable=False),
    sa.Column("bundle_sha256", sa.Text(), nullable=False),
    sa.Column("normalized_sha256", sa.Text(), nullable=False),
    sa.Column("price_semantics", sa.Text(), nullable=False),
    sa.Column("corporate_action_semantics", sa.Text(), nullable=False),
    sa.Column("corporate_action_manifest_hash", sa.Text(), nullable=True),
    sa.Column("dividend_handling", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("dataset_id", "dataset_version"),
    sa.CheckConstraint(
        "price_semantics IN ('RAW_UNADJUSTED', 'SPLIT_ADJUSTED', 'TOTAL_RETURN_ADJUSTED')",
        name="price_semantics_valid",
    ),
    sa.CheckConstraint(
        "corporate_action_semantics IN ('NONE_DECLARED', 'SPLIT_AND_SYMBOL_CHANGE_AWARE')",
        name="corporate_action_semantics_valid",
    ),
    sa.CheckConstraint("instrument_count >= 1", name="instrument_count_positive"),
    sa.CheckConstraint("file_count >= 1", name="file_count_positive"),
)

dataset_snapshot_source_file = sa.Table(
    "dataset_snapshot_source_file",
    _METADATA,
    sa.Column("dataset_id", sa.Text(), nullable=False),
    sa.Column("dataset_version", sa.Text(), nullable=False),
    sa.Column("file_name", sa.Text(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("sha256", sa.Text(), nullable=False),
    sa.Column("row_count", sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint("dataset_id", "dataset_version", "file_name"),
    sa.ForeignKeyConstraint(
        ["dataset_id", "dataset_version"],
        ["dataset_snapshot.dataset_id", "dataset_snapshot.dataset_version"],
        ondelete="CASCADE",
    ),
)

corporate_action = sa.Table(
    "corporate_action",
    _METADATA,
    sa.Column("dataset_id", sa.Text(), nullable=False),
    sa.Column("dataset_version", sa.Text(), nullable=False),
    sa.Column("instrument_id", sa.Text(), nullable=False),
    sa.Column("effective_timestamp", _TIMESTAMPTZ, nullable=False),
    sa.Column("action_type", sa.Text(), nullable=False),
    sa.Column("ratio_new_shares", sa.BigInteger(), nullable=True),
    sa.Column("ratio_old_shares", sa.BigInteger(), nullable=True),
    sa.Column("old_symbol", sa.Text(), nullable=True),
    sa.Column("new_symbol", sa.Text(), nullable=True),
    sa.Column("source_kind", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint(
        "dataset_id", "dataset_version", "instrument_id", "effective_timestamp", "action_type"
    ),
    sa.ForeignKeyConstraint(
        ["dataset_id", "dataset_version"],
        ["dataset_snapshot.dataset_id", "dataset_snapshot.dataset_version"],
    ),
    sa.CheckConstraint(
        "action_type IN ('SPLIT', 'REVERSE_SPLIT', 'SYMBOL_CHANGE')", name="action_type_valid"
    ),
    sa.CheckConstraint(
        "(action_type IN ('SPLIT', 'REVERSE_SPLIT') AND ratio_new_shares IS NOT NULL "
        "AND ratio_old_shares IS NOT NULL AND old_symbol IS NULL AND new_symbol IS NULL) OR "
        "(action_type = 'SYMBOL_CHANGE' AND ratio_new_shares IS NULL AND ratio_old_shares IS NULL "
        "AND old_symbol IS NOT NULL AND new_symbol IS NOT NULL)",
        name="action_payload_coherent",
    ),
)

corporate_action_semantics_stress = sa.Table(
    "corporate_action_semantics_stress",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("dataset_id", sa.Text(), nullable=False),
    sa.Column("correct_dataset_version", sa.Text(), nullable=False),
    sa.Column("correct_run_governance_id", sa.Text(), nullable=False),
    sa.Column("naive_dataset_version", sa.Text(), nullable=False),
    sa.Column("naive_run_governance_id", sa.Text(), nullable=False),
    sa.Column("comparison", sa.Text(), nullable=False),
    sa.Column("correct_executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("naive_executed_trade_count", sa.BigInteger(), nullable=False),
    sa.Column("correct_net_pnl_total", _PRICE, nullable=False),
    sa.Column("naive_net_pnl_total", _PRICE, nullable=False),
    sa.Column("correct_total_r_total", _RATIO, nullable=False),
    sa.Column("naive_total_r_total", _RATIO, nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.CheckConstraint(
        "comparison IN ('CORPORATE_ACTION_SEMANTICS_STRESS_IDENTICAL', "
        "'CORPORATE_ACTION_SEMANTICS_STRESS_DIFFERS')",
        name="comparison_valid",
    ),
)


def upgrade() -> None:
    """Create the M065 dataset-snapshot and corporate-action tables."""
    bind = op.get_bind()
    dataset_snapshot.create(bind=bind)
    dataset_snapshot_source_file.create(bind=bind)
    corporate_action.create(bind=bind)
    corporate_action_semantics_stress.create(bind=bind)


def downgrade() -> None:
    """Drop the M065 tables in dependency order."""
    bind = op.get_bind()
    corporate_action_semantics_stress.drop(bind=bind)
    corporate_action.drop(bind=bind)
    dataset_snapshot_source_file.drop(bind=bind)
    dataset_snapshot.drop(bind=bind)
