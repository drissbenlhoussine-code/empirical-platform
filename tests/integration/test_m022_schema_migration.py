from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

_ALL_TABLES_CREATION_ORDER = [
    "campaign",
    "campaign_transition",
    "run",
    "run_manifest",
    "run_transition",
    "evidence_package",
    "evidence_package_criterion_result",
    "evidence_package_artifact_reference",
    "evidence_package_transition",
    "review",
    "review_finding",
    "review_transition",
]

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

# Exact structural specification of every table, captured from a real applied
# migration and cross-checked against MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN.md
# Sections 7-10 and 12.2-12.5. Column type names are the class names SQLAlchemy's
# reflection reports for a real PostgreSQL connection (not the migration's own
# construction-time types), so this spec is a genuinely independent check.
_TRANSITION_COLUMNS: dict[str, tuple[str, bool]] = {
    "sequence": ("INTEGER", False),
    "from_state": ("TEXT", True),
    "to_state": ("TEXT", False),
    "version": ("INTEGER", False),
    "actor": ("TEXT", False),
    "occurred_at": ("TIMESTAMP", False),
    "identity_governance_id": ("TEXT", True),
    "identity_runtime_id": ("UUID", True),
    "correlation_id": ("TEXT", True),
    "reason": ("TEXT", True),
}


def _transition_checks(table: str) -> set[str]:
    return {
        f"ck_{table}_sequence_positive",
        f"ck_{table}_version_non_negative",
        f"ck_{table}_from_state_valid",
        f"ck_{table}_to_state_valid",
    }


_TABLE_SPECS: dict[str, dict[str, Any]] = {
    "campaign": {
        "columns": {
            "runtime_id": ("UUID", False),
            "governance_id": ("TEXT", False),
            "scope_statement": ("TEXT", False),
            "lifecycle_state": ("TEXT", False),
            "version": ("INTEGER", False),
            "next_transition_sequence": ("INTEGER", False),
        },
        "pk": {"name": "pk_campaign", "columns": ["runtime_id"]},
        "fks": [],
        "uniques": [{"name": "uq_campaign_governance_id", "columns": ["governance_id"]}],
        "checks": {
            "ck_campaign_version_non_negative",
            "ck_campaign_next_transition_sequence_positive",
            "ck_campaign_lifecycle_state_valid",
        },
        "indexes": [],
    },
    "campaign_transition": {
        "columns": {"campaign_runtime_id": ("UUID", False), **_TRANSITION_COLUMNS},
        "pk": {"name": "pk_campaign_transition", "columns": ["campaign_runtime_id", "sequence"]},
        "fks": [
            {
                "name": "fk_campaign_transition_campaign_runtime_id_campaign",
                "columns": ["campaign_runtime_id"],
                "referred_table": "campaign",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [],
        "checks": _transition_checks("campaign_transition"),
        "indexes": [],
    },
    "run": {
        "columns": {
            "runtime_id": ("UUID", False),
            "governance_id": ("TEXT", False),
            "campaign_id": ("TEXT", False),
            "lifecycle_state": ("TEXT", False),
            "version": ("INTEGER", False),
            "next_transition_sequence": ("INTEGER", False),
        },
        "pk": {"name": "pk_run", "columns": ["runtime_id"]},
        "fks": [
            {
                "name": "fk_run_campaign_id_campaign",
                "columns": ["campaign_id"],
                "referred_table": "campaign",
                "referred_columns": ["governance_id"],
            }
        ],
        "uniques": [{"name": "uq_run_governance_id", "columns": ["governance_id"]}],
        "checks": {
            "ck_run_version_non_negative",
            "ck_run_next_transition_sequence_positive",
            "ck_run_lifecycle_state_valid",
        },
        "indexes": [],
    },
    "run_manifest": {
        "columns": {
            "run_runtime_id": ("UUID", False),
            "position": ("INTEGER", False),
            "manifest_id": ("TEXT", True),
            "recorded_at": ("TIMESTAMP", False),
            "source": ("TEXT", False),
            "acquisition_method": ("TEXT", True),
            "normalization_method": ("TEXT", True),
            "notes": ("ARRAY", False),
        },
        "pk": {"name": "pk_run_manifest", "columns": ["run_runtime_id", "position"]},
        "fks": [
            {
                "name": "fk_run_manifest_run_runtime_id_run",
                "columns": ["run_runtime_id"],
                "referred_table": "run",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [],
        "checks": {"ck_run_manifest_position_non_negative"},
        "indexes": [
            {
                "name": "ix_run_manifest_manifest_id_partial_unique",
                "columns": ["run_runtime_id", "manifest_id"],
                "unique": True,
                "has_predicate": True,
            }
        ],
    },
    "run_transition": {
        "columns": {"run_runtime_id": ("UUID", False), **_TRANSITION_COLUMNS},
        "pk": {"name": "pk_run_transition", "columns": ["run_runtime_id", "sequence"]},
        "fks": [
            {
                "name": "fk_run_transition_run_runtime_id_run",
                "columns": ["run_runtime_id"],
                "referred_table": "run",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [],
        "checks": _transition_checks("run_transition"),
        "indexes": [],
    },
    "evidence_package": {
        "columns": {
            "runtime_id": ("UUID", False),
            "governance_id": ("TEXT", False),
            "run_id": ("TEXT", False),
            "lifecycle_state": ("TEXT", False),
            "version": ("INTEGER", False),
            "next_transition_sequence": ("INTEGER", False),
        },
        "pk": {"name": "pk_evidence_package", "columns": ["runtime_id"]},
        "fks": [
            {
                "name": "fk_evidence_package_run_id_run",
                "columns": ["run_id"],
                "referred_table": "run",
                "referred_columns": ["governance_id"],
            }
        ],
        "uniques": [{"name": "uq_evidence_package_governance_id", "columns": ["governance_id"]}],
        "checks": {
            "ck_evidence_package_version_non_negative",
            "ck_evidence_package_next_transition_sequence_positive",
            "ck_evidence_package_lifecycle_state_valid",
        },
        "indexes": [],
    },
    "evidence_package_criterion_result": {
        "columns": {
            "evidence_package_runtime_id": ("UUID", False),
            "position": ("INTEGER", False),
            "criterion_id": ("TEXT", False),
            "recorded_at": ("TIMESTAMP", False),
            "result_label": ("TEXT", False),
            "summary": ("TEXT", True),
            "evidence_references": ("ARRAY", False),
        },
        "pk": {
            "name": "pk_evidence_package_criterion_result",
            "columns": ["evidence_package_runtime_id", "position"],
        },
        "fks": [
            {
                "name": "fk_evidence_package_criterion_result_evidence_package_r_5363",
                "columns": ["evidence_package_runtime_id"],
                "referred_table": "evidence_package",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [
            {
                "name": "uq_evidence_package_criterion_result_evidence_package_r_3ff8",
                "columns": ["evidence_package_runtime_id", "criterion_id"],
            }
        ],
        "checks": {"ck_evidence_package_criterion_result_position_non_negative"},
        "indexes": [],
    },
    "evidence_package_artifact_reference": {
        "columns": {
            "evidence_package_runtime_id": ("UUID", False),
            "position": ("INTEGER", False),
            "value": ("TEXT", False),
        },
        "pk": {
            "name": "pk_evidence_package_artifact_reference",
            "columns": ["evidence_package_runtime_id", "position"],
        },
        "fks": [
            {
                "name": "fk_evidence_package_artifact_reference_evidence_package_4209",
                "columns": ["evidence_package_runtime_id"],
                "referred_table": "evidence_package",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [
            {
                "name": "uq_evidence_package_artifact_reference_evidence_package_35f6",
                "columns": ["evidence_package_runtime_id", "value"],
            }
        ],
        "checks": {"ck_evidence_package_artifact_reference_position_non_negative"},
        "indexes": [],
    },
    "evidence_package_transition": {
        "columns": {"evidence_package_runtime_id": ("UUID", False), **_TRANSITION_COLUMNS},
        "pk": {
            "name": "pk_evidence_package_transition",
            "columns": ["evidence_package_runtime_id", "sequence"],
        },
        "fks": [
            {
                "name": "fk_evidence_package_transition_evidence_package_runtime_7780",
                "columns": ["evidence_package_runtime_id"],
                "referred_table": "evidence_package",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [],
        "checks": _transition_checks("evidence_package_transition"),
        "indexes": [],
    },
    "review": {
        "columns": {
            "runtime_id": ("UUID", False),
            "governance_id": ("TEXT", False),
            "target_evidence_package_id": ("TEXT", False),
            "reviewer_reference": ("TEXT", False),
            "lifecycle_state": ("TEXT", False),
            "disposition": ("TEXT", True),
            "final_disposition_rationale": ("TEXT", True),
            "cancellation_reason": ("TEXT", True),
            "version": ("INTEGER", False),
            "next_transition_sequence": ("INTEGER", False),
        },
        "pk": {"name": "pk_review", "columns": ["runtime_id"]},
        "fks": [
            {
                "name": "fk_review_target_evidence_package_id_evidence_package",
                "columns": ["target_evidence_package_id"],
                "referred_table": "evidence_package",
                "referred_columns": ["governance_id"],
            }
        ],
        "uniques": [{"name": "uq_review_governance_id", "columns": ["governance_id"]}],
        "checks": {
            "ck_review_version_non_negative",
            "ck_review_next_transition_sequence_positive",
            "ck_review_lifecycle_state_valid",
            "ck_review_disposition_valid",
        },
        "indexes": [],
    },
    "review_finding": {
        "columns": {
            "review_runtime_id": ("UUID", False),
            "sequence": ("INTEGER", False),
            "text": ("TEXT", False),
            "rationale": ("TEXT", True),
            "evidence_references": ("ARRAY", False),
        },
        "pk": {"name": "pk_review_finding", "columns": ["review_runtime_id", "sequence"]},
        "fks": [
            {
                "name": "fk_review_finding_review_runtime_id_review",
                "columns": ["review_runtime_id"],
                "referred_table": "review",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [],
        "checks": {"ck_review_finding_sequence_positive"},
        "indexes": [],
    },
    "review_transition": {
        "columns": {"review_runtime_id": ("UUID", False), **_TRANSITION_COLUMNS},
        "pk": {"name": "pk_review_transition", "columns": ["review_runtime_id", "sequence"]},
        "fks": [
            {
                "name": "fk_review_transition_review_runtime_id_review",
                "columns": ["review_runtime_id"],
                "referred_table": "review",
                "referred_columns": ["runtime_id"],
            }
        ],
        "uniques": [],
        "checks": _transition_checks("review_transition"),
        "indexes": [],
    },
}

assert set(_TABLE_SPECS) == set(_ALL_TABLES_CREATION_ORDER)


def _integration_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m022-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _integration_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url())
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="module")
def upgraded_schema(engine: Engine) -> Iterator[Engine]:
    """Apply the M022 migration to a guaranteed-empty database, once per module."""
    _reset_public_schema(engine)
    command.upgrade(_alembic_config(), "head")
    yield engine
    _reset_public_schema(engine)


def _seed_valid_aggregate_chain(
    conn: sa.Connection, *, criterion_id: str = "criterion-1"
) -> dict[str, str]:
    """Insert one valid row into every M022 table; returns identifiers and governance ids used."""
    campaign_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    evidence_package_id = str(uuid.uuid4())
    review_id = str(uuid.uuid4())
    campaign_governance_id = f"campaign-{campaign_id}"
    run_governance_id = f"run-{run_id}"
    evidence_package_governance_id = f"evidence-{evidence_package_id}"
    review_governance_id = f"review-{review_id}"

    conn.execute(
        text(
            "INSERT INTO campaign "
            "(runtime_id, governance_id, scope_statement, lifecycle_state, version, "
            "next_transition_sequence) "
            "VALUES (:runtime_id, :governance_id, 'scope', 'DRAFT', 0, 1)"
        ),
        {"runtime_id": campaign_id, "governance_id": campaign_governance_id},
    )
    conn.execute(
        text(
            "INSERT INTO campaign_transition "
            "(campaign_runtime_id, sequence, from_state, to_state, version, actor, "
            "occurred_at) "
            "VALUES (:campaign_runtime_id, 1, NULL, 'DRAFT', 0, 'tester', now())"
        ),
        {"campaign_runtime_id": campaign_id},
    )
    conn.execute(
        text(
            "INSERT INTO run "
            "(runtime_id, governance_id, campaign_id, lifecycle_state, version, "
            "next_transition_sequence) "
            "VALUES (:runtime_id, :governance_id, :campaign_id, 'CREATED', 0, 1)"
        ),
        {
            "runtime_id": run_id,
            "governance_id": run_governance_id,
            "campaign_id": campaign_governance_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO run_manifest "
            "(run_runtime_id, position, manifest_id, recorded_at, source) "
            "VALUES (:run_runtime_id, 0, :manifest_id, now(), 'acquisition')"
        ),
        {"run_runtime_id": run_id, "manifest_id": f"manifest-{run_id}"},
    )
    conn.execute(
        text(
            "INSERT INTO run_transition "
            "(run_runtime_id, sequence, from_state, to_state, version, actor, occurred_at) "
            "VALUES (:run_runtime_id, 1, NULL, 'CREATED', 0, 'tester', now())"
        ),
        {"run_runtime_id": run_id},
    )
    conn.execute(
        text(
            "INSERT INTO evidence_package "
            "(runtime_id, governance_id, run_id, lifecycle_state, version, "
            "next_transition_sequence) "
            "VALUES (:runtime_id, :governance_id, :run_id, 'INITIALIZED', 0, 1)"
        ),
        {
            "runtime_id": evidence_package_id,
            "governance_id": evidence_package_governance_id,
            "run_id": run_governance_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO evidence_package_criterion_result "
            "(evidence_package_runtime_id, position, criterion_id, recorded_at, "
            "result_label) "
            "VALUES (:evidence_package_runtime_id, 0, :criterion_id, now(), 'PASS')"
        ),
        {"evidence_package_runtime_id": evidence_package_id, "criterion_id": criterion_id},
    )
    conn.execute(
        text(
            "INSERT INTO evidence_package_artifact_reference "
            "(evidence_package_runtime_id, position, value) "
            "VALUES (:evidence_package_runtime_id, 0, 'artifact-a')"
        ),
        {"evidence_package_runtime_id": evidence_package_id},
    )
    conn.execute(
        text(
            "INSERT INTO evidence_package_transition "
            "(evidence_package_runtime_id, sequence, from_state, to_state, version, "
            "actor, occurred_at) "
            "VALUES (:evidence_package_runtime_id, 1, NULL, 'INITIALIZED', 0, 'tester', "
            "now())"
        ),
        {"evidence_package_runtime_id": evidence_package_id},
    )
    conn.execute(
        text(
            "INSERT INTO review "
            "(runtime_id, governance_id, target_evidence_package_id, "
            "reviewer_reference, lifecycle_state, version, next_transition_sequence) "
            "VALUES (:runtime_id, :governance_id, :target_evidence_package_id, "
            "'reviewer-1', 'ASSIGNED', 0, 1)"
        ),
        {
            "runtime_id": review_id,
            "governance_id": review_governance_id,
            "target_evidence_package_id": evidence_package_governance_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO review_finding (review_runtime_id, sequence, text) "
            "VALUES (:review_runtime_id, 1, 'finding text')"
        ),
        {"review_runtime_id": review_id},
    )
    conn.execute(
        text(
            "INSERT INTO review_transition "
            "(review_runtime_id, sequence, from_state, to_state, version, actor, "
            "occurred_at) "
            "VALUES (:review_runtime_id, 1, NULL, 'ASSIGNED', 0, 'tester', now())"
        ),
        {"review_runtime_id": review_id},
    )
    return {
        "campaign_id": campaign_id,
        "campaign_governance_id": campaign_governance_id,
        "run_id": run_id,
        "run_governance_id": run_governance_id,
        "evidence_package_id": evidence_package_id,
        "evidence_package_governance_id": evidence_package_governance_id,
        "review_id": review_id,
        "review_governance_id": review_governance_id,
    }


def _expect_integrity_error(engine: Engine, statement: str, params: dict[str, object]) -> None:
    with engine.connect() as conn:
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(text(statement), params)
        conn.rollback()


# --- Atomicity -------------------------------------------------------------


def test_migration_failure_leaves_no_partial_schema(engine: Engine) -> None:
    """A revision that fails partway through must roll back completely.

    A conflicting ``review`` table is pre-created so the migration fails at
    creation step 10; because PostgreSQL DDL is transactional and Alembic
    wraps each revision in a transaction, tables 1-9 must not survive.
    """
    _reset_public_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE review (conflicting_column INTEGER)"))

    with pytest.raises(sa.exc.ProgrammingError, match="already exists"):
        command.upgrade(_alembic_config(), "head")

    inspector = inspect(engine)
    remaining_tables = set(inspector.get_table_names())
    leaked_tables = remaining_tables & (set(_ALL_TABLES_CREATION_ORDER) - {"review"})
    assert not leaked_tables, f"partial schema survived a failed migration: {leaked_tables}"
    with engine.connect() as conn:
        row_count = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = "
                "'alembic_version'"
            )
        ).scalar_one()
    assert row_count == 0, "alembic_version must not exist after a fully rolled-back migration"

    _reset_public_schema(engine)


# --- Upgrade: exhaustive structural verification -----------------------------


def test_upgrade_creates_all_twelve_tables(upgraded_schema: Engine) -> None:
    inspector = inspect(upgraded_schema)
    assert set(_ALL_TABLES_CREATION_ORDER) <= set(inspector.get_table_names())


@pytest.mark.parametrize("table_name", sorted(_TABLE_SPECS))
def test_table_matches_frozen_structure(upgraded_schema: Engine, table_name: str) -> None:
    """Exact columns, types, nullability, PK/FK/UNIQUE/CHECK names, and indexes.

    Every value asserted here is read back from a real applied migration via
    SQLAlchemy's PostgreSQL reflection, independent of the migration file's own
    construction-time type objects.
    """
    spec = _TABLE_SPECS[table_name]
    inspector = inspect(upgraded_schema)

    columns = {c["name"]: c for c in inspector.get_columns(table_name)}
    assert set(columns) == set(spec["columns"]), (
        f"{table_name}: column set mismatch, got {sorted(columns)}"
    )
    for column_name, (expected_type, expected_nullable) in spec["columns"].items():
        actual = columns[column_name]
        assert type(actual["type"]).__name__ == expected_type, (
            f"{table_name}.{column_name}: expected type {expected_type}, "
            f"got {type(actual['type']).__name__}"
        )
        assert actual["nullable"] is expected_nullable, (
            f"{table_name}.{column_name}: expected nullable={expected_nullable}, "
            f"got {actual['nullable']}"
        )

    pk = inspector.get_pk_constraint(table_name)
    assert pk["name"] == spec["pk"]["name"]
    assert pk["constrained_columns"] == spec["pk"]["columns"]

    actual_fks = {fk["name"]: fk for fk in inspector.get_foreign_keys(table_name)}
    expected_fk_names = {fk["name"] for fk in spec["fks"]}
    assert set(actual_fks) == expected_fk_names, f"{table_name}: FK set mismatch"
    for expected_fk in spec["fks"]:
        actual_fk = actual_fks[expected_fk["name"]]
        assert actual_fk["constrained_columns"] == expected_fk["columns"]
        assert actual_fk["referred_table"] == expected_fk["referred_table"]
        assert actual_fk["referred_columns"] == expected_fk["referred_columns"]
        # No ondelete configured anywhere in the frozen design: PostgreSQL's
        # implicit default (NO ACTION) applies, and SQLAlchemy reports no
        # explicit "ondelete" option in that case.
        assert actual_fk["options"].get("ondelete") is None, (
            f"{table_name}.{expected_fk['name']}: expected no explicit ON DELETE action "
            f"(implicit NO ACTION), got {actual_fk['options'].get('ondelete')}"
        )

    actual_uniques = {u["name"]: u for u in inspector.get_unique_constraints(table_name)}
    expected_unique_names = {u["name"] for u in spec["uniques"]}
    assert set(actual_uniques) == expected_unique_names, f"{table_name}: UNIQUE set mismatch"
    for expected_unique in spec["uniques"]:
        assert (
            actual_uniques[expected_unique["name"]]["column_names"] == expected_unique["columns"]
        ), f"{table_name}.{expected_unique['name']}: column order mismatch"

    actual_check_names = {c["name"] for c in inspector.get_check_constraints(table_name)}
    assert actual_check_names == spec["checks"], f"{table_name}: CHECK name set mismatch"

    actual_indexes = {ix["name"]: ix for ix in inspector.get_indexes(table_name)}
    # PostgreSQL implements every UNIQUE constraint via a backing unique index,
    # which SQLAlchemy's reflection reports through get_indexes() in addition to
    # get_unique_constraints() above; the PK's own index is not included here.
    expected_index_names = {ix["name"] for ix in spec["indexes"]} | expected_unique_names
    assert set(actual_indexes) == expected_index_names, f"{table_name}: index set mismatch"
    for expected_index in spec["indexes"]:
        actual_index = actual_indexes[expected_index["name"]]
        assert actual_index["column_names"] == expected_index["columns"]
        assert actual_index["unique"] is expected_index["unique"]
        if expected_index.get("has_predicate"):
            assert actual_index["dialect_options"].get("postgresql_where") is not None


def test_upgrade_evidence_package_unique_constraints_preserve_frozen_column_order(
    upgraded_schema: Engine,
) -> None:
    """Narrow, explicit regression test for the corrected UNIQUE column order.

    The frozen design requires ``UNIQUE (evidence_package_runtime_id, criterion_id)``
    and ``UNIQUE (evidence_package_runtime_id, value)`` -- the owning parent's
    foreign-key column first. An earlier implementation had these reversed.
    """
    inspector = inspect(upgraded_schema)

    criterion_uniques = inspector.get_unique_constraints("evidence_package_criterion_result")
    assert len(criterion_uniques) == 1
    assert criterion_uniques[0]["column_names"] == [
        "evidence_package_runtime_id",
        "criterion_id",
    ]

    artifact_uniques = inspector.get_unique_constraints("evidence_package_artifact_reference")
    assert len(artifact_uniques) == 1
    assert artifact_uniques[0]["column_names"] == ["evidence_package_runtime_id", "value"]


# --- Constraint behavior: numeric/positional rejections ----------------------


def test_campaign_version_below_zero_is_rejected(upgraded_schema: Engine) -> None:
    _expect_integrity_error(
        upgraded_schema,
        "INSERT INTO campaign (runtime_id, governance_id, scope_statement, "
        "lifecycle_state, version, next_transition_sequence) "
        "VALUES (:id, :gid, 'scope', 'DRAFT', -1, 1)",
        {"id": str(uuid.uuid4()), "gid": f"campaign-{uuid.uuid4()}"},
    )


def test_campaign_next_transition_sequence_below_one_is_rejected(upgraded_schema: Engine) -> None:
    _expect_integrity_error(
        upgraded_schema,
        "INSERT INTO campaign (runtime_id, governance_id, scope_statement, "
        "lifecycle_state, version, next_transition_sequence) "
        "VALUES (:id, :gid, 'scope', 'DRAFT', 0, 0)",
        {"id": str(uuid.uuid4()), "gid": f"campaign-{uuid.uuid4()}"},
    )


def test_transition_sequence_below_one_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        campaign_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO campaign (runtime_id, governance_id, scope_statement, "
                "lifecycle_state, version, next_transition_sequence) "
                "VALUES (:id, :gid, 'scope', 'DRAFT', 0, 1)"
            ),
            {"id": campaign_id, "gid": f"campaign-{campaign_id}"},
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO campaign_transition (campaign_runtime_id, sequence, "
                    "from_state, to_state, version, actor, occurred_at) "
                    "VALUES (:cid, 0, NULL, 'DRAFT', 0, 'tester', now())"
                ),
                {"cid": campaign_id},
            )
        conn.rollback()


def test_review_finding_sequence_below_one_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO review_finding (review_runtime_id, sequence, text) "
                    "VALUES (:rid, 0, 'bad finding')"
                ),
                {"rid": ids["review_id"]},
            )
        conn.rollback()


def test_position_below_zero_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO run_manifest (run_runtime_id, position, recorded_at, "
                    "source) VALUES (:rid, -1, now(), 'acquisition')"
                ),
                {"rid": ids["run_id"]},
            )
        conn.rollback()


# --- Constraint behavior: enum-membership rejections -------------------------


def test_invalid_campaign_lifecycle_state_is_rejected(upgraded_schema: Engine) -> None:
    _expect_integrity_error(
        upgraded_schema,
        "INSERT INTO campaign (runtime_id, governance_id, scope_statement, "
        "lifecycle_state, version, next_transition_sequence) "
        "VALUES (:id, :gid, 'scope', 'NOT_A_REAL_STATE', 0, 1)",
        {"id": str(uuid.uuid4()), "gid": f"campaign-{uuid.uuid4()}"},
    )


def test_invalid_run_lifecycle_state_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text("UPDATE run SET lifecycle_state = 'NOT_A_REAL_STATE' WHERE runtime_id = :rid"),
                {"rid": ids["run_id"]},
            )
        conn.rollback()


def test_invalid_evidence_package_lifecycle_state_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "UPDATE evidence_package SET lifecycle_state = 'NOT_A_REAL_STATE' "
                    "WHERE runtime_id = :eid"
                ),
                {"eid": ids["evidence_package_id"]},
            )
        conn.rollback()


def test_invalid_review_lifecycle_state_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "UPDATE review SET lifecycle_state = 'NOT_A_REAL_STATE' WHERE runtime_id = :rid"
                ),
                {"rid": ids["review_id"]},
            )
        conn.rollback()


def test_invalid_review_disposition_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "UPDATE review SET disposition = 'NOT_A_REAL_DISPOSITION' WHERE "
                    "runtime_id = :rid"
                ),
                {"rid": ids["review_id"]},
            )
        conn.rollback()


@pytest.mark.parametrize(
    ("transition_table", "parent_id_key", "parent_column", "states"),
    [
        (
            "campaign_transition",
            "campaign_id",
            "campaign_runtime_id",
            _CAMPAIGN_LIFECYCLE_STATES,
        ),
        ("run_transition", "run_id", "run_runtime_id", _RUN_LIFECYCLE_STATES),
        (
            "evidence_package_transition",
            "evidence_package_id",
            "evidence_package_runtime_id",
            _EVIDENCE_PACKAGE_LIFECYCLE_STATES,
        ),
        ("review_transition", "review_id", "review_runtime_id", _REVIEW_LIFECYCLE_STATES),
    ],
)
def test_invalid_transition_from_state_is_rejected(
    upgraded_schema: Engine,
    transition_table: str,
    parent_id_key: str,
    parent_column: str,
    states: tuple[str, ...],
) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            # Table/column names come only from the fixed parametrize list above,
            # never from external input; bind params carry all data values.
            conn.execute(
                text(
                    f"INSERT INTO {transition_table} "  # noqa: S608
                    f"({parent_column}, sequence, from_state, to_state, version, actor, "
                    "occurred_at) "
                    f"VALUES (:parent_id, 2, 'NOT_A_REAL_STATE', :valid_state, 0, "
                    "'tester', now())"
                ),
                {"parent_id": ids[parent_id_key], "valid_state": states[0]},
            )
        conn.rollback()


@pytest.mark.parametrize(
    ("transition_table", "parent_id_key", "parent_column"),
    [
        ("campaign_transition", "campaign_id", "campaign_runtime_id"),
        ("run_transition", "run_id", "run_runtime_id"),
        ("evidence_package_transition", "evidence_package_id", "evidence_package_runtime_id"),
        ("review_transition", "review_id", "review_runtime_id"),
    ],
)
def test_invalid_transition_to_state_is_rejected(
    upgraded_schema: Engine,
    transition_table: str,
    parent_id_key: str,
    parent_column: str,
) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            # Table/column names come only from the fixed parametrize list above,
            # never from external input; bind params carry all data values.
            conn.execute(
                text(
                    f"INSERT INTO {transition_table} "  # noqa: S608
                    f"({parent_column}, sequence, from_state, to_state, version, actor, "
                    "occurred_at) "
                    f"VALUES (:parent_id, 2, NULL, 'NOT_A_REAL_STATE', 0, 'tester', now())"
                ),
                {"parent_id": ids[parent_id_key]},
            )
        conn.rollback()


# --- Constraint behavior: uniqueness rejections ------------------------------


def test_duplicate_campaign_governance_id_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO campaign (runtime_id, governance_id, scope_statement, "
                    "lifecycle_state, version, next_transition_sequence) "
                    "VALUES (:id, :gid, 'scope', 'DRAFT', 0, 1)"
                ),
                {"id": str(uuid.uuid4()), "gid": ids["campaign_governance_id"]},
            )
        conn.rollback()


def test_duplicate_run_governance_id_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO run (runtime_id, governance_id, campaign_id, "
                    "lifecycle_state, version, next_transition_sequence) "
                    "VALUES (:id, :gid, :campaign_id, 'CREATED', 0, 1)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "gid": ids["run_governance_id"],
                    "campaign_id": ids["campaign_governance_id"],
                },
            )
        conn.rollback()


def test_duplicate_evidence_package_governance_id_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO evidence_package (runtime_id, governance_id, run_id, "
                    "lifecycle_state, version, next_transition_sequence) "
                    "VALUES (:id, :gid, :run_id, 'INITIALIZED', 0, 1)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "gid": ids["evidence_package_governance_id"],
                    "run_id": ids["run_governance_id"],
                },
            )
        conn.rollback()


def test_duplicate_review_governance_id_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO review (runtime_id, governance_id, "
                    "target_evidence_package_id, reviewer_reference, lifecycle_state, "
                    "version, next_transition_sequence) "
                    "VALUES (:id, :gid, :target_id, 'reviewer-1', 'ASSIGNED', 0, 1)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "gid": ids["review_governance_id"],
                    "target_id": ids["evidence_package_governance_id"],
                },
            )
        conn.rollback()


def test_duplicate_criterion_id_within_same_package_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn, criterion_id="criterion-1")
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO evidence_package_criterion_result "
                    "(evidence_package_runtime_id, position, criterion_id, recorded_at, "
                    "result_label) "
                    "VALUES (:eid, 1, 'criterion-1', now(), 'PASS')"
                ),
                {"eid": ids["evidence_package_id"]},
            )
        conn.rollback()


def test_same_criterion_id_across_different_packages_is_accepted(
    upgraded_schema: Engine,
) -> None:
    with upgraded_schema.connect() as conn:
        first = _seed_valid_aggregate_chain(conn, criterion_id="shared-criterion")
        second = _seed_valid_aggregate_chain(conn, criterion_id="shared-criterion")
        assert first["evidence_package_id"] != second["evidence_package_id"]
        count = conn.execute(
            text(
                "SELECT count(*) FROM evidence_package_criterion_result "
                "WHERE criterion_id = 'shared-criterion'"
            )
        ).scalar_one()
        assert count == 2
        conn.rollback()


def test_duplicate_artifact_reference_position_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO evidence_package_artifact_reference "
                    "(evidence_package_runtime_id, position, value) "
                    "VALUES (:eid, 0, 'artifact-different-value')"
                ),
                {"eid": ids["evidence_package_id"]},
            )
        conn.rollback()


def test_duplicate_artifact_reference_value_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO evidence_package_artifact_reference "
                    "(evidence_package_runtime_id, position, value) "
                    "VALUES (:eid, 1, 'artifact-a')"
                ),
                {"eid": ids["evidence_package_id"]},
            )
        conn.rollback()


def test_duplicate_manifest_id_within_same_run_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO run_manifest (run_runtime_id, position, manifest_id, "
                    "recorded_at, source) "
                    "VALUES (:rid, 1, :manifest_id, now(), 'normalization')"
                ),
                {"rid": ids["run_id"], "manifest_id": f"manifest-{ids['run_id']}"},
            )
        conn.rollback()


def test_multiple_null_manifest_id_within_same_run_is_accepted(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        conn.execute(
            text(
                "INSERT INTO run_manifest (run_runtime_id, position, manifest_id, "
                "recorded_at, source) "
                "VALUES (:rid, 1, NULL, now(), 'normalization')"
            ),
            {"rid": ids["run_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO run_manifest (run_runtime_id, position, manifest_id, "
                "recorded_at, source) "
                "VALUES (:rid, 2, NULL, now(), 'validation')"
            ),
            {"rid": ids["run_id"]},
        )
        count = conn.execute(
            text(
                "SELECT count(*) FROM run_manifest WHERE run_runtime_id = :rid AND "
                "manifest_id IS NULL"
            ),
            {"rid": ids["run_id"]},
        ).scalar_one()
        assert count == 2
        conn.rollback()


def test_duplicate_owned_row_key_is_rejected(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO run_manifest (run_runtime_id, position, recorded_at, "
                    "source) VALUES (:rid, 0, now(), 'a-different-source')"
                ),
                {"rid": ids["run_id"]},
            )
        conn.rollback()


def test_invalid_parent_reference_is_rejected(upgraded_schema: Engine) -> None:
    _expect_integrity_error(
        upgraded_schema,
        "INSERT INTO campaign_transition (campaign_runtime_id, sequence, from_state, "
        "to_state, version, actor, occurred_at) "
        "VALUES (:cid, 1, NULL, 'DRAFT', 0, 'tester', now())",
        {"cid": str(uuid.uuid4())},
    )


def test_orphan_child_row_is_rejected(upgraded_schema: Engine) -> None:
    _expect_integrity_error(
        upgraded_schema,
        "INSERT INTO review_finding (review_runtime_id, sequence, text) "
        "VALUES (:rid, 1, 'orphan finding')",
        {"rid": str(uuid.uuid4())},
    )


# --- Constraint behavior: acceptance -----------------------------------------


def test_full_valid_aggregate_chain_is_accepted(upgraded_schema: Engine) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        assert (
            conn.execute(
                text("SELECT count(*) FROM campaign WHERE runtime_id = :id"),
                {"id": ids["campaign_id"]},
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM review WHERE runtime_id = :id"),
                {"id": ids["review_id"]},
            ).scalar_one()
            == 1
        )
        conn.rollback()


# --- Ordering ------------------------------------------------------------


def test_artifact_reference_rows_reconstruct_deterministically_by_position(
    upgraded_schema: Engine,
) -> None:
    with upgraded_schema.connect() as conn:
        ids = _seed_valid_aggregate_chain(conn)
        evidence_package_id = ids["evidence_package_id"]
        # position 0/"artifact-a" already inserted by the seed helper; add the rest
        # out of position order to prove position, not insertion order, governs
        # reconstruction.
        conn.execute(
            text(
                "INSERT INTO evidence_package_artifact_reference "
                "(evidence_package_runtime_id, position, value) "
                "VALUES (:eid, 2, 'artifact-c')"
            ),
            {"eid": evidence_package_id},
        )
        conn.execute(
            text(
                "INSERT INTO evidence_package_artifact_reference "
                "(evidence_package_runtime_id, position, value) "
                "VALUES (:eid, 1, 'artifact-b')"
            ),
            {"eid": evidence_package_id},
        )
        rows = conn.execute(
            text(
                "SELECT position, value FROM evidence_package_artifact_reference "
                "WHERE evidence_package_runtime_id = :eid ORDER BY position"
            ),
            {"eid": evidence_package_id},
        ).all()
        assert [(row.position, row.value) for row in rows] == [
            (0, "artifact-a"),
            (1, "artifact-b"),
            (2, "artifact-c"),
        ]
        conn.rollback()


# --- Downgrade ---------------------------------------------------------------


def test_downgrade_removes_all_tables_and_reupgrade_succeeds(engine: Engine) -> None:
    _reset_public_schema(engine)
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    assert set(_ALL_TABLES_CREATION_ORDER) <= set(inspector.get_table_names())

    command.downgrade(cfg, "base")

    inspector = inspect(engine)
    remaining = set(inspector.get_table_names())
    assert not (remaining & set(_ALL_TABLES_CREATION_ORDER))
    with engine.connect() as conn:
        version_rows = conn.execute(text("SELECT * FROM alembic_version")).all()
    assert version_rows == []

    # Re-upgrade must succeed cleanly after a full downgrade.
    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    assert set(_ALL_TABLES_CREATION_ORDER) <= set(inspector.get_table_names())

    _reset_public_schema(engine)
