from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
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


def _seed_valid_aggregate_chain(conn: sa.Connection) -> dict[str, str]:
    """Insert one valid row into every M022 table; returns the identifiers used."""
    campaign_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    evidence_package_id = str(uuid.uuid4())
    review_id = str(uuid.uuid4())

    conn.execute(
        text(
            "INSERT INTO campaign "
            "(runtime_id, governance_id, scope_statement, lifecycle_state, version, "
            "next_transition_sequence) "
            "VALUES (:runtime_id, :governance_id, 'scope', 'DRAFT', 0, 1)"
        ),
        {"runtime_id": campaign_id, "governance_id": f"campaign-{campaign_id}"},
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
            "governance_id": f"run-{run_id}",
            "campaign_id": f"campaign-{campaign_id}",
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
            "governance_id": f"evidence-{evidence_package_id}",
            "run_id": f"run-{run_id}",
        },
    )
    conn.execute(
        text(
            "INSERT INTO evidence_package_criterion_result "
            "(evidence_package_runtime_id, position, criterion_id, recorded_at, "
            "result_label) "
            "VALUES (:evidence_package_runtime_id, 0, 'criterion-1', now(), 'PASS')"
        ),
        {"evidence_package_runtime_id": evidence_package_id},
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
            "governance_id": f"review-{review_id}",
            "target_evidence_package_id": f"evidence-{evidence_package_id}",
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
        "run_id": run_id,
        "evidence_package_id": evidence_package_id,
        "review_id": review_id,
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


# --- Upgrade: structural verification ---------------------------------------


def test_upgrade_creates_all_twelve_tables(upgraded_schema: Engine) -> None:
    inspector = inspect(upgraded_schema)
    assert set(_ALL_TABLES_CREATION_ORDER) <= set(inspector.get_table_names())


def test_upgrade_campaign_table_structure(upgraded_schema: Engine) -> None:
    inspector = inspect(upgraded_schema)
    columns = {c["name"]: c for c in inspector.get_columns("campaign")}
    assert isinstance(columns["runtime_id"]["type"], postgresql.UUID)
    assert columns["runtime_id"]["nullable"] is False
    assert columns["version"]["nullable"] is False
    assert columns["next_transition_sequence"]["nullable"] is False

    pk = inspector.get_pk_constraint("campaign")
    assert pk["constrained_columns"] == ["runtime_id"]
    assert pk["name"] == "pk_campaign"

    uqs = {u["name"]: u["column_names"] for u in inspector.get_unique_constraints("campaign")}
    assert uqs["uq_campaign_governance_id"] == ["governance_id"]

    checks = {c["name"] for c in inspector.get_check_constraints("campaign")}
    assert checks == {
        "ck_campaign_version_non_negative",
        "ck_campaign_next_transition_sequence_positive",
        "ck_campaign_lifecycle_state_valid",
    }


def test_upgrade_foreign_key_names_including_truncated_ones(upgraded_schema: Engine) -> None:
    inspector = inspect(upgraded_schema)

    run_fks = inspector.get_foreign_keys("run")
    assert run_fks[0]["name"] == "fk_run_campaign_id_campaign"
    assert run_fks[0]["constrained_columns"] == ["campaign_id"]
    assert run_fks[0]["referred_table"] == "campaign"
    assert run_fks[0]["referred_columns"] == ["governance_id"]

    campaign_transition_fks = inspector.get_foreign_keys("campaign_transition")
    assert campaign_transition_fks[0]["name"] == (
        "fk_campaign_transition_campaign_runtime_id_campaign"
    )

    # These three FK names exceed PostgreSQL's 63-byte identifier limit before
    # truncation; SQLAlchemy's naming_convention truncates them deterministically
    # with a stable hash suffix. Exact names captured from a real applied migration.
    artifact_fks = inspector.get_foreign_keys("evidence_package_artifact_reference")
    assert artifact_fks[0]["name"] == (
        "fk_evidence_package_artifact_reference_evidence_package_4209"
    )
    criterion_fks = inspector.get_foreign_keys("evidence_package_criterion_result")
    assert criterion_fks[0]["name"] == (
        "fk_evidence_package_criterion_result_evidence_package_r_5363"
    )
    evidence_transition_fks = inspector.get_foreign_keys("evidence_package_transition")
    assert evidence_transition_fks[0]["name"] == (
        "fk_evidence_package_transition_evidence_package_runtime_7780"
    )
    for fk_name in (
        artifact_fks[0]["name"],
        criterion_fks[0]["name"],
        evidence_transition_fks[0]["name"],
    ):
        assert len(fk_name) <= 63


def test_upgrade_run_manifest_partial_unique_index(upgraded_schema: Engine) -> None:
    inspector = inspect(upgraded_schema)
    indexes = {i["name"]: i for i in inspector.get_indexes("run_manifest")}
    partial = indexes["ix_run_manifest_manifest_id_partial_unique"]
    assert partial["unique"] is True
    assert partial["column_names"] == ["run_runtime_id", "manifest_id"]


# --- Constraint behavior: rejections ----------------------------------------


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


def test_invalid_lifecycle_state_is_rejected(upgraded_schema: Engine) -> None:
    _expect_integrity_error(
        upgraded_schema,
        "INSERT INTO campaign (runtime_id, governance_id, scope_statement, "
        "lifecycle_state, version, next_transition_sequence) "
        "VALUES (:id, :gid, 'scope', 'NOT_A_REAL_STATE', 0, 1)",
        {"id": str(uuid.uuid4()), "gid": f"campaign-{uuid.uuid4()}"},
    )


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
