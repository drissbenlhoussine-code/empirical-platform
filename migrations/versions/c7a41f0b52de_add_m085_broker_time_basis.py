"""MILESTONE-085 broker time basis for execution authorizations.

WHY THIS EXISTS. `paper_execution_authorization.expires_at` is an absolute UTC
instant written by the approving host's wall clock. Operation-local monotonic
time protects it only while that process runs. Once the process exits, a host
clock that steps BACKWARD makes the stored expiry look further away, and the
dispatching process has no memory with which to notice. That was reproduced
deterministically: with an hour-long backward step between approval and
dispatch, a 300-second permission still dispatched.

WHAT IS ADDED. Two readings taken at the SAME moment the human authorized --
this host's clock, and the earliest instant the broker's clock could then have
been showing. Their difference is a measured, conservative host-to-broker
mapping. Nothing is recomputed or reinterpreted from it later; it is only ever
used to place a stored host deadline on the broker's timeline, in the direction
that makes the deadline sooner.

NULLABLE, DELIBERATELY. A row written before this basis existed has none. Such a
row is not silently trusted and not silently reinterpreted: the domain refuses to
map it, and the dispatch path refuses it. Backfilling a plausible value would be
manufacturing the very evidence this column exists to carry.

MILESTONE-083 and MILESTONE-084 tables are untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c7a41f0b52de"
down_revision: str | None = "b1e9d47c30a5"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "paper_execution_authorization"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("basis_host_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("basis_broker_earliest_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The two readings are meaningless apart: one without the other cannot express
    # a mapping, so the database refuses the half-written pair outright.
    op.create_check_constraint(
        "ck_paper_execution_authorization_basis_pair",
        _TABLE,
        "(basis_host_at IS NULL) = (basis_broker_earliest_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_paper_execution_authorization_basis_pair", _TABLE, type_="check")
    op.drop_column(_TABLE, "basis_broker_earliest_at")
    op.drop_column(_TABLE, "basis_host_at")
