"""MILESTONE-057 real-PostgreSQL end-to-end acceptance test for the first
trading-intelligence vertical slice: Market Observation -> Strategy
Evaluation -> Trading Decision Evidence.

Drives the real `evaluate_trading_observation` / `get_decision_candidate`
production entrypoints against one real, migrated PostgreSQL database,
using the synthetic, clearly-labeled fixtures in
tests/fixtures/m057_market_data/ (see the README there). Proves:

- a positive `LONG_CANDIDATE` evaluation, persisted, retrieved, and
  independently verified via direct SQL that bypasses the repository
  read path;
- a valid `NO_TRADE` evaluation, equally first-class and persisted;
- deterministic replay: the same window + strategy + configuration
  produces byte-for-byte identical measurements and decision on a second,
  independently-identified evaluation;
- the Phase-10 core-integration design: the resulting DecisionCandidate's
  governance_id is recorded as a separate ArtifactReference on its target
  EvidencePackage via the already-frozen M040 entrypoint, exactly as
  documented in usecases/evaluate_trading_observation.py's own docstring;
- the look-ahead-bias regression probe: an evaluation bar carrying an
  extreme high/volume must never contaminate the reference-window
  statistics it is being compared against.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as every prior milestone's own PostgreSQL integration tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.strategy import TradingDecision
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.evaluate_trading_observation import (
    run_evaluate_trading_observation,
)
from empirical_platform.entrypoints.get_decision_candidate import run_get_decision_candidate
from empirical_platform.entrypoints.record_evidence_package_artifact_reference import (
    run_record_evidence_package_artifact_reference,
)
from empirical_platform.entrypoints.start_evidence_package_collection import (
    run_start_evidence_package_collection,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "m057_market_data"
_LONG_CANDIDATE_FIXTURE = str(_FIXTURES_DIR / "synthetic_aapl_1min_long_candidate.json")
_NO_TRADE_FIXTURE = str(_FIXTURES_DIR / "synthetic_aapl_1min_no_trade.json")
_LOOKAHEAD_PROBE_FIXTURE = str(_FIXTURES_DIR / "synthetic_aapl_1min_lookahead_probe.json")

_ALL_TABLES = [
    "decision_candidate",
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
        application_name="empirical-platform-m057-test",
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


def _seed_evidence_package(*, suffix: str, evidence_package_id: str) -> str:
    """Seed a real Campaign -> Run -> EvidencePackage chain through the
    frozen entrypoints, returning the EvidencePackage's runtime_id."""
    config = _config()
    campaign_id = f"CAMP-70{suffix}0"
    run_id = f"RUN-70{suffix}0"
    run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M057 trading evaluation seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"7000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    run_create_run(
        run_governance_id=run_id,
        campaign_governance_id=campaign_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"7000000{suffix}-0000-4000-8000-000000000002"]
        ),
        config=config,
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id=evidence_package_id,
        run_governance_id=run_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"7000000{suffix}-0000-4000-8000-000000000003"]
        ),
        config=config,
    )
    return str(ep_identity.runtime_id)


def test_positive_long_candidate_persists_retrieves_and_links_to_evidence(
    clean_tables: Engine,
) -> None:
    """A real caller evaluates a breakout observation end-to-end, the
    resulting LONG_CANDIDATE is persisted and independently retrievable,
    and its governance_id is recorded as a separate ArtifactReference on
    its target EvidencePackage per the M057 Phase-10 design."""
    config = _config()
    ep_runtime_id = _seed_evidence_package(suffix="1", evidence_package_id="EVID-7001")

    candidate = run_evaluate_trading_observation(
        decision_candidate_governance_id="DCAND-7001",
        target_evidence_package_governance_id="EVID-7001",
        bars_file=_LONG_CANDIDATE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["70000001-0000-4000-8000-000000000004"]
        ),
        config=config,
    )
    assert candidate.outcome.decision is TradingDecision.LONG_CANDIDATE
    assert candidate.outcome.measurements.reference_high == Decimal("100.50")
    assert candidate.outcome.measurements.reference_average_volume == Decimal("1012")

    retrieved = run_get_decision_candidate(
        decision_candidate_governance_id="DCAND-7001",
        decision_candidate_runtime_id=str(candidate.identity.runtime_id),
        config=config,
    )
    assert retrieved == candidate

    run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-7001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=0,
        actor="trading-evaluation-operator",
        occurred_at=candidate.evaluation_timestamp,
        config=config,
    )
    run_record_evidence_package_artifact_reference(
        evidence_package_governance_id="EVID-7001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=1,
        value=f"decision-candidate:{candidate.identity.governance_id}",
        config=config,
    )

    engine = sa.create_engine(config.sqlalchemy_url())
    with engine.connect() as conn:
        candidate_row = (
            conn.execute(
                text(
                    "SELECT decision, strategy_id, strategy_version, "
                    "target_evidence_package_governance_id, reference_high, "
                    "reference_average_volume, reasons "
                    "FROM decision_candidate WHERE governance_id = :g"
                ),
                {"g": "DCAND-7001"},
            )
            .mappings()
            .one()
        )
        artifact_row = (
            conn.execute(
                text(
                    "SELECT value FROM evidence_package_artifact_reference "
                    "WHERE evidence_package_runtime_id = :ep"
                ),
                {"ep": ep_runtime_id},
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert candidate_row["decision"] == "LONG_CANDIDATE"
    assert candidate_row["strategy_id"] == "PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION"
    assert candidate_row["strategy_version"] == "1"
    assert candidate_row["target_evidence_package_governance_id"] == "EVID-7001"
    assert candidate_row["reference_high"] == Decimal("100.500000")
    assert candidate_row["reference_average_volume"] == Decimal("1012.000000")
    assert set(candidate_row["reasons"]) == {
        "PRICE_ABOVE_REFERENCE_HIGH",
        "VOLUME_ABOVE_REFERENCE_AVERAGE",
    }
    assert artifact_row["value"] == "decision-candidate:DCAND-7001"


def test_valid_no_trade_is_persisted_as_a_first_class_outcome(clean_tables: Engine) -> None:
    """NO_TRADE is not an exception path: a quiet observation must persist
    just as completely as a positive candidate, with both reason codes
    explaining exactly why no trade was signalled."""
    config = _config()
    _seed_evidence_package(suffix="2", evidence_package_id="EVID-7002")

    candidate = run_evaluate_trading_observation(
        decision_candidate_governance_id="DCAND-7002",
        target_evidence_package_governance_id="EVID-7002",
        bars_file=_NO_TRADE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["70000002-0000-4000-8000-000000000004"]
        ),
        config=config,
    )
    assert candidate.outcome.decision is TradingDecision.NO_TRADE
    assert {reason.value for reason in candidate.outcome.reasons} == {
        "PRICE_NOT_ABOVE_REFERENCE_HIGH",
        "VOLUME_NOT_ABOVE_REFERENCE_AVERAGE",
    }

    retrieved = run_get_decision_candidate(
        decision_candidate_governance_id="DCAND-7002",
        decision_candidate_runtime_id=str(candidate.identity.runtime_id),
        config=config,
    )
    assert retrieved == candidate


def test_deterministic_replay_produces_identical_outcome(clean_tables: Engine) -> None:
    """The same bars, strategy, and configuration must yield byte-for-byte
    identical decision, reasons, and measurements no matter how many times
    -- or under what independent identity -- the evaluation is replayed."""
    config = _config()
    _seed_evidence_package(suffix="3", evidence_package_id="EVID-7003")

    first = run_evaluate_trading_observation(
        decision_candidate_governance_id="DCAND-7031",
        target_evidence_package_governance_id="EVID-7003",
        bars_file=_LONG_CANDIDATE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["70000003-0000-4000-8000-000000000004"]
        ),
        config=config,
    )
    second = run_evaluate_trading_observation(
        decision_candidate_governance_id="DCAND-7032",
        target_evidence_package_governance_id="EVID-7003",
        bars_file=_LONG_CANDIDATE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["70000003-0000-4000-8000-000000000005"]
        ),
        config=config,
    )

    assert first.outcome.decision == second.outcome.decision
    assert first.outcome.reasons == second.outcome.reasons
    assert first.outcome.measurements == second.outcome.measurements
    assert first.evaluation_timestamp == second.evaluation_timestamp


def test_lookahead_probe_reference_statistics_exclude_the_evaluation_bar(
    clean_tables: Engine,
) -> None:
    """Regression guard for look-ahead bias: the evaluation bar in this
    fixture carries an extreme high (200.00) and volume (5000) alongside a
    close (150.00) that only clears the *true* reference high computed
    from the five prior bars (100.50). If a future refactor accidentally
    sliced the reference window from the whole window (including the
    evaluation bar) instead of strictly `reference_bars`, reference_high
    would jump to 200.00, the price condition would flip to False, and
    this test would fail."""
    config = _config()
    _seed_evidence_package(suffix="4", evidence_package_id="EVID-7004")

    candidate = run_evaluate_trading_observation(
        decision_candidate_governance_id="DCAND-7004",
        target_evidence_package_governance_id="EVID-7004",
        bars_file=_LOOKAHEAD_PROBE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["70000004-0000-4000-8000-000000000004"]
        ),
        config=config,
    )

    assert candidate.outcome.decision is TradingDecision.LONG_CANDIDATE
    assert candidate.outcome.measurements.reference_high == Decimal("100.50")
    assert candidate.outcome.measurements.reference_average_volume == Decimal("1012")
    assert candidate.outcome.measurements.current_close == Decimal("150.00")
    assert candidate.outcome.measurements.current_volume == 5000
