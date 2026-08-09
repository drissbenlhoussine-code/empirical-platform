"""create m060 position plan schema

Revision ID: 73f4a1d89b22
Revises: 256558a33013
Create Date: 2026-08-09 16:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "73f4a1d89b22"
down_revision: str | None = "256558a33013"
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

trade_plan = sa.Table(
    "trade_plan",
    _METADATA,
    sa.Column("governance_id", sa.Text(), nullable=False),
)

position_plan = sa.Table(
    "position_plan",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("source_trade_plan_governance_id", sa.Text(), nullable=False),
    sa.Column("instrument_symbol", sa.Text(), nullable=False),
    sa.Column("policy_id", sa.Text(), nullable=False),
    sa.Column("policy_version", sa.Text(), nullable=False),
    sa.Column("policy_maximum_risk_percent", _RATIO, nullable=False),
    sa.Column("policy_maximum_notional_percent", _RATIO, nullable=False),
    sa.Column("policy_allow_fractional_shares", sa.Boolean(), nullable=False),
    sa.Column("supplied_account_equity", _PRICE, nullable=False),
    sa.Column("supplied_risk_percent", _RATIO, nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column(
        "reasons",
        postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column("entry_price", _PRICE, nullable=True),
    sa.Column("stop_price", _PRICE, nullable=True),
    sa.Column("risk_per_unit", _PRICE, nullable=True),
    sa.Column("allowed_risk_amount", _PRICE, nullable=True),
    sa.Column("maximum_notional", _PRICE, nullable=True),
    sa.Column("risk_based_quantity", sa.BigInteger(), nullable=True),
    sa.Column("capital_based_quantity", sa.BigInteger(), nullable=True),
    sa.Column("quantity", sa.BigInteger(), nullable=True),
    sa.Column("position_notional", _PRICE, nullable=True),
    sa.Column("actual_risk", _PRICE, nullable=True),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(["source_trade_plan_governance_id"], ["trade_plan.governance_id"]),
    sa.CheckConstraint(
        "status IN ('APPROVED_POSITION_PLAN', 'REJECTED_POSITION_PLAN')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "(status = 'APPROVED_POSITION_PLAN' "
        "AND cardinality(reasons) = 0 "
        "AND entry_price IS NOT NULL "
        "AND stop_price IS NOT NULL "
        "AND risk_per_unit IS NOT NULL "
        "AND allowed_risk_amount IS NOT NULL "
        "AND maximum_notional IS NOT NULL "
        "AND risk_based_quantity IS NOT NULL "
        "AND capital_based_quantity IS NOT NULL "
        "AND quantity IS NOT NULL "
        "AND position_notional IS NOT NULL "
        "AND actual_risk IS NOT NULL "
        "AND quantity > 0 "
        "AND actual_risk <= allowed_risk_amount "
        "AND position_notional <= maximum_notional) "
        "OR (status = 'REJECTED_POSITION_PLAN' AND cardinality(reasons) = 1)",
        name="status_sizing_reasons_coherent",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    position_plan.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    position_plan.drop(bind=bind)
