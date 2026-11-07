"""RELEASE v1 RECOVERY HARDENING SECURITY GATE (isolated fix). Drop the obsolete
`system_identity` CHECK constraint.

Revision ID: 83e15e6bfae4
Revises: c6e2a4f8b901

WHY. `ck_approved_plan_system_identity_derived` (b9f2c4d6a8e1) mirrored
`approved_plan.derive_system_identity`'s OLD format byte for byte:
`system_identity = 'system:approved-plan:' || plan_id || ':owner-approval:' ||
owner_approval_id`. That Python function concatenated `plan_id` and `owner_approval_id`
in the open, which could -- and for a real incident's own governance ids DID (110
characters) -- exceed the 64-character limit `PositionExitAuthorization.authorized_by`
enforces, independent of any deadline logic: the automatic manager would raise
`ValueError` the instant it tried to save the resulting authorization. The Python
function now hashes rather than concatenates (same module, same release); this
database-level mirror of its OLD representation can no longer match ANY value the
function produces and must be dropped, or no future `ApprovedPlan` could ever be
inserted again.

WHAT STILL ENFORCES THE INVARIANT. `ApprovedPlan.__post_init__`
(`decision_candidate/approved_plan.py`) recomputes `derive_system_identity(plan_id=...,
owner_approval_id=...)` and refuses construction if `system_identity` does not match
EXACTLY -- on EVERY construction, before an `ApprovedPlan` instance can ever reach a
repository's `save()`. This was always the primary enforcement; the database CHECK was
redundant defense in depth mirroring it. Replicating the new hash-based format at the
database layer would require a cryptographic digest function Postgres does not provide
without the `pgcrypto` extension, which nothing else in this schema depends on -- adding
it now, for redundant enforcement an unconditional Python-level check already provides
unconditionally, is a larger and riskier change than this fix calls for. No other
`approved_plan` CHECK constraint is touched.

ALL OTHER INVARIANTS THIS MIGRATION DOES NOT TOUCH: plan_id/candidate_id/entry present,
symbol uppercase, quantity positive, prices positive, stop below target, owner_approval_id
present, trigger-kind/trigger-pair, the one-plan-per-entry unique constraint, and the
claim-once trigger from b9f2c4d6a8e1. The historical deadline
(`mandatory_liquidation_at`) and the original Owner approval (`owner_approval_id`) are
untouched by this or any other change in this release.
"""

from alembic import op

revision: str = "83e15e6bfae4"
down_revision: str | None = "c6e2a4f8b901"
branch_labels = None
depends_on = None

_TABLE = "approved_plan"
_CONSTRAINT = "ck_approved_plan_system_identity_derived"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")


def downgrade() -> None:
    raise RuntimeError(
        "re-adding the obsolete system_identity CHECK constraint is prohibited; it would "
        "reject every system_identity the current derive_system_identity produces"
    )
