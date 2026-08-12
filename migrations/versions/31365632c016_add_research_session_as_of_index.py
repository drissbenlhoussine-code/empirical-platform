"""add research_session as_of index

Revision ID: 31365632c016
Revises: 3b44e3d71f52
Create Date: 2026-08-12 21:00:00.000000

MILESTONE-071: adds one index, `ix_research_session_as_of`, on
`research_session (as_of)`, to support the new session-history query
pattern (`list_recent`/`find_most_recent_prior`, both ordered by
`as_of DESC`) introduced this milestone -- a standard ascending B-tree
index is scanned efficiently in either direction by PostgreSQL, so no
descending-specific index is required. Purely additive: no column,
table, or constraint is added, dropped, or altered. This is the only
DDL change in MILESTONE-071 -- both new repository read methods are
otherwise plain `SELECT` statements against the already-frozen M070
`research_session`/`research_session_decision` tables.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31365632c016"
down_revision: str | None = "3b44e3d71f52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the as_of index used by session-history queries."""
    op.create_index(
        "ix_research_session_as_of",
        "research_session",
        ["as_of"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the as_of index."""
    op.drop_index("ix_research_session_as_of", table_name="research_session")
