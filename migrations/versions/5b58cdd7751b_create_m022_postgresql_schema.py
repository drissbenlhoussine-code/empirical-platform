"""create m022 postgresql schema

Revision ID: 5b58cdd7751b
Revises:
Create Date: 2026-07-26 12:42:39.878511

MILESTONE-022: creates the twelve tables specified by
MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN.md (Version 1.1), in the
exact object creation order frozen by that design's Section 12.5, using the
frozen SQLAlchemy-recommended ``naming_convention`` attached to a local
``MetaData`` object exactly as Section 12.5 specifies. Primary key, foreign
key, and unique constraint names are left to the convention to derive (and,
where a derived name would exceed PostgreSQL's 63-byte identifier limit, to
truncate deterministically via SQLAlchemy's standard hashing behavior); every
CHECK constraint is given the explicit short qualifier name Section 12.5
mandates. No column, table, or constraint beyond what that design specifies
is created here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5b58cdd7751b"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)
_TIMESTAMPTZ = sa.DateTime(timezone=True)
_TEXT_ARRAY_DEFAULT = sa.text("'{}'::text[]")

# Frozen by MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN.md Section 12.5.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}

_METADATA = sa.MetaData(naming_convention=NAMING_CONVENTION)

_CAMPAIGN_LIFECYCLE_STATES = (
    "DRAFT",
    "READY_FOR_AUTHORIZATION",
    "AUTHORIZED",
    "ACTIVE",
    "SUSPENDED",
    "COMPLETED",
    "CANCELLED",
)
_RUN_LIFECYCLE_STATES = (
    "CREATED",
    "AUTHORIZED",
    "ACQUIRING",
    "NORMALIZING",
    "VALIDATING",
    "EXECUTION_COMPLETED",
    "FAILED",
    "CANCELLED",
)
_EVIDENCE_PACKAGE_LIFECYCLE_STATES = ("INITIALIZED", "COLLECTING", "SEALED", "INVALIDATED")
_REVIEW_LIFECYCLE_STATES = ("ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED")
_REVIEW_DISPOSITIONS = ("ACCEPTED", "REJECTED", "CHANGES_REQUESTED", "INCONCLUSIVE")


def _enum_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _transition_columns() -> list[sa.Column]:
    """Shared column shape for every `*_transition` child table."""
    return [
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("occurred_at", _TIMESTAMPTZ, nullable=False),
        sa.Column("identity_governance_id", sa.Text(), nullable=True),
        sa.Column("identity_runtime_id", _UUID, nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    ]


def _transition_constraints(table_name: str, states: tuple[str, ...]) -> list[sa.CheckConstraint]:
    enum_sql = _enum_sql(states)
    return [
        sa.CheckConstraint("sequence >= 1", name="sequence_positive"),
        sa.CheckConstraint("version >= 0", name="version_non_negative"),
        sa.CheckConstraint(
            f"from_state IS NULL OR from_state IN ({enum_sql})", name="from_state_valid"
        ),
        sa.CheckConstraint(f"to_state IN ({enum_sql})", name="to_state_valid"),
    ]


# 1. campaign
campaign = sa.Table(
    "campaign",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("scope_statement", sa.Text(), nullable=False),
    sa.Column("lifecycle_state", sa.Text(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("next_transition_sequence", sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.CheckConstraint("version >= 0", name="version_non_negative"),
    sa.CheckConstraint("next_transition_sequence >= 1", name="next_transition_sequence_positive"),
    sa.CheckConstraint(
        f"lifecycle_state IN ({_enum_sql(_CAMPAIGN_LIFECYCLE_STATES)})",
        name="lifecycle_state_valid",
    ),
)

# 2. campaign_transition
campaign_transition = sa.Table(
    "campaign_transition",
    _METADATA,
    sa.Column("campaign_runtime_id", _UUID, nullable=False),
    *_transition_columns(),
    sa.PrimaryKeyConstraint("campaign_runtime_id", "sequence"),
    sa.ForeignKeyConstraint(["campaign_runtime_id"], ["campaign.runtime_id"]),
    *_transition_constraints("campaign_transition", _CAMPAIGN_LIFECYCLE_STATES),
)

# 3. run
run = sa.Table(
    "run",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("campaign_id", sa.Text(), nullable=False),
    sa.Column("lifecycle_state", sa.Text(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("next_transition_sequence", sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(["campaign_id"], ["campaign.governance_id"]),
    sa.CheckConstraint("version >= 0", name="version_non_negative"),
    sa.CheckConstraint("next_transition_sequence >= 1", name="next_transition_sequence_positive"),
    sa.CheckConstraint(
        f"lifecycle_state IN ({_enum_sql(_RUN_LIFECYCLE_STATES)})",
        name="lifecycle_state_valid",
    ),
)

# 4. run_manifest
run_manifest = sa.Table(
    "run_manifest",
    _METADATA,
    sa.Column("run_runtime_id", _UUID, nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("manifest_id", sa.Text(), nullable=True),
    sa.Column("recorded_at", _TIMESTAMPTZ, nullable=False),
    sa.Column("source", sa.Text(), nullable=False),
    sa.Column("acquisition_method", sa.Text(), nullable=True),
    sa.Column("normalization_method", sa.Text(), nullable=True),
    sa.Column(
        "notes", postgresql.ARRAY(sa.Text()), nullable=False, server_default=_TEXT_ARRAY_DEFAULT
    ),
    sa.PrimaryKeyConstraint("run_runtime_id", "position"),
    sa.ForeignKeyConstraint(["run_runtime_id"], ["run.runtime_id"]),
    sa.CheckConstraint("position >= 0", name="position_non_negative"),
)
_run_manifest_manifest_id_index = sa.Index(
    "ix_run_manifest_manifest_id_partial_unique",
    run_manifest.c.run_runtime_id,
    run_manifest.c.manifest_id,
    unique=True,
    postgresql_where=sa.text("manifest_id IS NOT NULL"),
)

# 5. run_transition
run_transition = sa.Table(
    "run_transition",
    _METADATA,
    sa.Column("run_runtime_id", _UUID, nullable=False),
    *_transition_columns(),
    sa.PrimaryKeyConstraint("run_runtime_id", "sequence"),
    sa.ForeignKeyConstraint(["run_runtime_id"], ["run.runtime_id"]),
    *_transition_constraints("run_transition", _RUN_LIFECYCLE_STATES),
)

# 6. evidence_package
evidence_package = sa.Table(
    "evidence_package",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("run_id", sa.Text(), nullable=False),
    sa.Column("lifecycle_state", sa.Text(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("next_transition_sequence", sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(["run_id"], ["run.governance_id"]),
    sa.CheckConstraint("version >= 0", name="version_non_negative"),
    sa.CheckConstraint("next_transition_sequence >= 1", name="next_transition_sequence_positive"),
    sa.CheckConstraint(
        f"lifecycle_state IN ({_enum_sql(_EVIDENCE_PACKAGE_LIFECYCLE_STATES)})",
        name="lifecycle_state_valid",
    ),
)

# 7. evidence_package_criterion_result
evidence_package_criterion_result = sa.Table(
    "evidence_package_criterion_result",
    _METADATA,
    sa.Column("evidence_package_runtime_id", _UUID, nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("criterion_id", sa.Text(), nullable=False),
    sa.Column("recorded_at", _TIMESTAMPTZ, nullable=False),
    sa.Column("result_label", sa.Text(), nullable=False),
    sa.Column("summary", sa.Text(), nullable=True),
    sa.Column(
        "evidence_references",
        postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default=_TEXT_ARRAY_DEFAULT,
    ),
    sa.PrimaryKeyConstraint("evidence_package_runtime_id", "position"),
    sa.ForeignKeyConstraint(["evidence_package_runtime_id"], ["evidence_package.runtime_id"]),
    sa.UniqueConstraint("criterion_id", "evidence_package_runtime_id"),
    sa.CheckConstraint("position >= 0", name="position_non_negative"),
)

# 8. evidence_package_artifact_reference
evidence_package_artifact_reference = sa.Table(
    "evidence_package_artifact_reference",
    _METADATA,
    sa.Column("evidence_package_runtime_id", _UUID, nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("value", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("evidence_package_runtime_id", "position"),
    sa.ForeignKeyConstraint(["evidence_package_runtime_id"], ["evidence_package.runtime_id"]),
    sa.UniqueConstraint("value", "evidence_package_runtime_id"),
    sa.CheckConstraint("position >= 0", name="position_non_negative"),
)

# 9. evidence_package_transition
evidence_package_transition = sa.Table(
    "evidence_package_transition",
    _METADATA,
    sa.Column("evidence_package_runtime_id", _UUID, nullable=False),
    *_transition_columns(),
    sa.PrimaryKeyConstraint("evidence_package_runtime_id", "sequence"),
    sa.ForeignKeyConstraint(["evidence_package_runtime_id"], ["evidence_package.runtime_id"]),
    *_transition_constraints("evidence_package_transition", _EVIDENCE_PACKAGE_LIFECYCLE_STATES),
)

# 10. review
review = sa.Table(
    "review",
    _METADATA,
    sa.Column("runtime_id", _UUID, nullable=False),
    sa.Column("governance_id", sa.Text(), nullable=False),
    sa.Column("target_evidence_package_id", sa.Text(), nullable=False),
    sa.Column("reviewer_reference", sa.Text(), nullable=False),
    sa.Column("lifecycle_state", sa.Text(), nullable=False),
    sa.Column("disposition", sa.Text(), nullable=True),
    sa.Column("final_disposition_rationale", sa.Text(), nullable=True),
    sa.Column("cancellation_reason", sa.Text(), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("next_transition_sequence", sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint("runtime_id"),
    sa.UniqueConstraint("governance_id"),
    sa.ForeignKeyConstraint(["target_evidence_package_id"], ["evidence_package.governance_id"]),
    sa.CheckConstraint("version >= 0", name="version_non_negative"),
    sa.CheckConstraint("next_transition_sequence >= 1", name="next_transition_sequence_positive"),
    sa.CheckConstraint(
        f"lifecycle_state IN ({_enum_sql(_REVIEW_LIFECYCLE_STATES)})",
        name="lifecycle_state_valid",
    ),
    sa.CheckConstraint(
        f"disposition IS NULL OR disposition IN ({_enum_sql(_REVIEW_DISPOSITIONS)})",
        name="disposition_valid",
    ),
)

# 11. review_finding
review_finding = sa.Table(
    "review_finding",
    _METADATA,
    sa.Column("review_runtime_id", _UUID, nullable=False),
    sa.Column("sequence", sa.Integer(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("rationale", sa.Text(), nullable=True),
    sa.Column(
        "evidence_references",
        postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default=_TEXT_ARRAY_DEFAULT,
    ),
    sa.PrimaryKeyConstraint("review_runtime_id", "sequence"),
    sa.ForeignKeyConstraint(["review_runtime_id"], ["review.runtime_id"]),
    sa.CheckConstraint("sequence >= 1", name="sequence_positive"),
)

# 12. review_transition
review_transition = sa.Table(
    "review_transition",
    _METADATA,
    sa.Column("review_runtime_id", _UUID, nullable=False),
    *_transition_columns(),
    sa.PrimaryKeyConstraint("review_runtime_id", "sequence"),
    sa.ForeignKeyConstraint(["review_runtime_id"], ["review.runtime_id"]),
    *_transition_constraints("review_transition", _REVIEW_LIFECYCLE_STATES),
)

# Exact object creation order frozen by Design Section 12.5.
_TABLES_IN_CREATION_ORDER = [
    campaign,
    campaign_transition,
    run,
    run_manifest,
    run_transition,
    evidence_package,
    evidence_package_criterion_result,
    evidence_package_artifact_reference,
    evidence_package_transition,
    review,
    review_finding,
    review_transition,
]


def upgrade() -> None:
    """Create all twelve MILESTONE-022 tables in frozen dependency order.

    The partial-unique index on ``run_manifest`` is attached to that table's
    definition above, so ``run_manifest.create()`` emits it automatically as
    part of that table's own DDL; it must not be created again explicitly.
    """
    bind = op.get_bind()
    for table in _TABLES_IN_CREATION_ORDER:
        table.create(bind=bind)


def downgrade() -> None:
    """Drop all twelve MILESTONE-022 tables in the exact reverse of creation order."""
    bind = op.get_bind()
    _run_manifest_manifest_id_index.drop(bind=bind)
    for table in reversed(_TABLES_IN_CREATION_ORDER):
        table.drop(bind=bind)
