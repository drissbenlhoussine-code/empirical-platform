"""widen decision_candidate bar_interval check for M069 ONE_DAY

Revision ID: 3b44e3d71f52
Revises: 83d5dbd9ec54
Create Date: 2026-08-12 00:30:00.000000

MILESTONE-070. MILESTONE-069 added `BarInterval.ONE_DAY` to the frozen
Python enum (a deliberate, disclosed, purely additive change -- see the
M069 final report) but never updated the one place that value is also
enumerated at the database level: the M057 `decision_candidate` table's
own `ck_decision_candidate_bar_interval_valid` CHECK constraint, which
still only allowed `'ONE_MINUTE'`/`'FIVE_MINUTE'`. M070 is the first
capability to actually persist a `decision_candidate` row built from
real, daily-granularity M069 data, and its own integration testing
surfaced the gap directly (a `CheckViolation` on the very first scan
attempt). This migration closes it: purely additive (widens an existing
constraint to include one already-frozen value; drops no data, alters no
other column, changes no other table).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b44e3d71f52"
down_revision: str | None = "83d5dbd9ec54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONSTRAINT_SQL = "bar_interval IN ('ONE_MINUTE', 'FIVE_MINUTE')"
_NEW_CONSTRAINT_SQL = "bar_interval IN ('ONE_MINUTE', 'FIVE_MINUTE', 'ONE_DAY')"


def upgrade() -> None:
    """Widen decision_candidate's own bar_interval CHECK constraint to
    also allow 'ONE_DAY', matching the M069 Python-level enum."""
    op.drop_constraint(
        "ck_decision_candidate_bar_interval_valid", "decision_candidate", type_="check"
    )
    op.create_check_constraint(
        "ck_decision_candidate_bar_interval_valid", "decision_candidate", _NEW_CONSTRAINT_SQL
    )


def downgrade() -> None:
    """Restore the original, narrower bar_interval CHECK constraint."""
    op.drop_constraint(
        "ck_decision_candidate_bar_interval_valid", "decision_candidate", type_="check"
    )
    op.create_check_constraint(
        "ck_decision_candidate_bar_interval_valid", "decision_candidate", _OLD_CONSTRAINT_SQL
    )
