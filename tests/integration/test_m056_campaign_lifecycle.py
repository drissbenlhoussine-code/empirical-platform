"""MILESTONE-056 real-PostgreSQL end-to-end acceptance test for the Campaign
Lifecycle vertical slice.

Proves the WHOLE new capability, not merely every entrypoint independently:
before this milestone, a Campaign could be created, retrieved, and
cancelled, but no real caller could drive it through its complete forward
business lifecycle. This test drives a real Campaign through every legal
forward transition -- revise scope (DRAFT) -> prepare for authorization ->
record authorization -> activate -> suspend -> resume -> complete -- against
one real, migrated PostgreSQL database, independently verified via direct
SQL read-back that bypasses the repository read path, including proof that
the revised scope statement (Campaign-owned data) survives every subsequent
transition unchanged. Also proves the already-frozen M047/M051
`cancel_campaign` capability as this milestone's negative path, from a
legitimate ACTIVE state, without rebuilding or exhaustively re-testing it.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as every prior milestone's own PostgreSQL integration tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.entrypoints.activate_campaign import run_activate_campaign
from empirical_platform.entrypoints.cancel_campaign import run_cancel_campaign
from empirical_platform.entrypoints.complete_campaign import run_complete_campaign
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.get_campaign import run_get_campaign
from empirical_platform.entrypoints.prepare_campaign_for_authorization import (
    run_prepare_campaign_for_authorization,
)
from empirical_platform.entrypoints.record_campaign_authorization import (
    run_record_campaign_authorization,
)
from empirical_platform.entrypoints.resume_campaign import run_resume_campaign
from empirical_platform.entrypoints.revise_campaign_scope_statement import (
    run_revise_campaign_scope_statement,
)
from empirical_platform.entrypoints.suspend_campaign import run_suspend_campaign
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALL_TABLES = [
    "review_transition",
    "review_finding",
    "review",
    "evidence_package_transition",
    "evidence_package_artifact_reference",
    "evidence_package_criterion_result",
    "evidence_package",
    "run_transition",
    "run_manifest",
    "run",
    "campaign_transition",
    "campaign",
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
        application_name="empirical-platform-m056-test",
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
    _reset_public_schema(engine)
    alembic_command.upgrade(_alembic_config(), "head")
    yield engine
    _reset_public_schema(engine)


@pytest.fixture
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


def _seed_campaign(*, suffix: str, campaign_id: str) -> str:
    """Seed a real Campaign through the frozen M050-M052 entrypoints,
    returning its runtime_id."""
    identity = run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M056 lifecycle seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"1000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    return str(identity.runtime_id)


def test_full_campaign_lifecycle_from_draft_to_completed(clean_tables: Engine) -> None:
    """Drives the entire M056 capability end-to-end against real PostgreSQL,
    proving the platform can genuinely take a Campaign through its complete
    legal forward lifecycle -- not merely that each individual entrypoint
    works in isolation -- with Campaign-owned data (the scope statement)
    verified to survive every subsequent transition."""
    campaign_runtime_id = _seed_campaign(suffix="1", campaign_id="CAMP-0001")

    revise_result = run_revise_campaign_scope_statement(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=0,
        scope_statement="a revised, more precise scope statement",
        config=_config(),
    )
    assert revise_result.persisted_version.value == 1

    prepare_result = run_prepare_campaign_for_authorization(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=1,
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    assert prepare_result.persisted_version.value == 2

    authorize_result = run_record_campaign_authorization(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=2,
        reason="authorization approved",
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 5, 0, tzinfo=UTC),
        config=_config(),
    )
    assert authorize_result.persisted_version.value == 3

    activate_result = run_activate_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=3,
        reason="starting execution",
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 10, 0, tzinfo=UTC),
        config=_config(),
    )
    assert activate_result.persisted_version.value == 4

    suspend_result = run_suspend_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=4,
        reason="pausing for external review",
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 15, 0, tzinfo=UTC),
        config=_config(),
    )
    assert suspend_result.persisted_version.value == 5

    resume_result = run_resume_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=5,
        reason="resuming execution",
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 20, 0, tzinfo=UTC),
        config=_config(),
    )
    assert resume_result.persisted_version.value == 6

    complete_result = run_complete_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=6,
        reason="objectives met",
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 25, 0, tzinfo=UTC),
        config=_config(),
    )
    assert complete_result.persisted_version.value == 7

    snapshot = run_get_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=campaign_runtime_id,
        config=_config(),
    )
    assert snapshot.state.value == "COMPLETED"
    assert str(snapshot.scope_statement) == "a revised, more precise scope statement"

    # Independent verification via direct SQL, bypassing the repository
    # read path entirely.
    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        campaign_row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, scope_statement, version FROM campaign "
                    "WHERE governance_id = :g"
                ),
                {"g": "CAMP-0001"},
            )
            .mappings()
            .one()
        )
        transition_rows = (
            conn.execute(
                text(
                    "SELECT from_state, to_state FROM campaign_transition "
                    "WHERE campaign_runtime_id = :r ORDER BY sequence"
                ),
                {"r": campaign_runtime_id},
            )
            .mappings()
            .all()
        )
    engine.dispose()

    assert campaign_row["lifecycle_state"] == "COMPLETED"
    assert campaign_row["scope_statement"] == "a revised, more precise scope statement"
    assert campaign_row["version"] == 7
    assert [(r["from_state"], r["to_state"]) for r in transition_rows] == [
        ("DRAFT", "READY_FOR_AUTHORIZATION"),
        ("READY_FOR_AUTHORIZATION", "AUTHORIZED"),
        ("AUTHORIZED", "ACTIVE"),
        ("ACTIVE", "SUSPENDED"),
        ("SUSPENDED", "ACTIVE"),
        ("ACTIVE", "COMPLETED"),
    ]


def test_cancel_campaign_from_active_state_is_the_negative_path(clean_tables: Engine) -> None:
    """Integrates the already-frozen M047/M051 `cancel_campaign` capability
    into this milestone's own acceptance picture as the negative path, from
    a real, legitimately ACTIVE Campaign -- not rebuilt, not exhaustively
    re-tested, just proven once as part of the real workflow."""
    campaign_runtime_id = _seed_campaign(suffix="2", campaign_id="CAMP-0002")
    run_prepare_campaign_for_authorization(
        campaign_governance_id="CAMP-0002",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=0,
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    run_record_campaign_authorization(
        campaign_governance_id="CAMP-0002",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=1,
        reason="authorized",
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 5, 0, tzinfo=UTC),
        config=_config(),
    )
    run_activate_campaign(
        campaign_governance_id="CAMP-0002",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=2,
        reason="starting execution",
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 10, 0, tzinfo=UTC),
        config=_config(),
    )

    cancel_result = run_cancel_campaign(
        campaign_governance_id="CAMP-0002",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=3,
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 15, 0, tzinfo=UTC),
        reason="scope no longer viable",
        config=_config(),
    )
    assert cancel_result.persisted_version.value == 4

    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT lifecycle_state, version FROM campaign WHERE governance_id = :g"),
                {"g": "CAMP-0002"},
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert row["lifecycle_state"] == "CANCELLED"
    assert row["version"] == 4


def test_revise_scope_statement_outside_draft_raises_value_error(clean_tables: Engine) -> None:
    """New failure mode this slice's composition genuinely exercises: the
    scope statement cannot be revised once a Campaign has left DRAFT."""
    campaign_runtime_id = _seed_campaign(suffix="3", campaign_id="CAMP-0003")
    run_prepare_campaign_for_authorization(
        campaign_governance_id="CAMP-0003",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=0,
        actor="operator-gamma",
        occurred_at=datetime(2026, 8, 8, 10, 0, 0, tzinfo=UTC),
        config=_config(),
    )

    with pytest.raises(ValueError, match="may be revised only while DRAFT"):
        run_revise_campaign_scope_statement(
            campaign_governance_id="CAMP-0003",
            campaign_runtime_id=campaign_runtime_id,
            expected_persisted_version=1,
            scope_statement="should never persist",
            config=_config(),
        )


def test_default_config_resolves_from_environment(
    monkeypatch: pytest.MonkeyPatch, clean_tables: Engine
) -> None:
    """Proves the production default path -- omitting `config` -- really
    resolves through `resolve_foundation_config()` against this same
    disposable database for the reused MILESTONE-053
    `_composition.postgres_repository_runtime()` helper."""
    config = _config()
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", config.host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", str(config.port))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", config.database)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", config.user)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", config.password.get_secret_value())

    campaign_runtime_id = _seed_campaign(suffix="4", campaign_id="CAMP-0004")
    prepare_result = run_prepare_campaign_for_authorization(
        campaign_governance_id="CAMP-0004",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=0,
        actor="operator-delta",
        occurred_at=datetime(2026, 8, 8, 11, 0, 0, tzinfo=UTC),
    )

    assert prepare_result.persisted_version.value == 1
