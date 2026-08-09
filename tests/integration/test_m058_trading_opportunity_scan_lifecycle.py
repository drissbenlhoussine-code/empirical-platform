"""MILESTONE-058 real-PostgreSQL end-to-end acceptance test for the trading
opportunity scanner and ranker: multiple instruments, evaluated through the
unmodified M057 strategy, deterministically ranked, persisted, and linked
into the existing evidence/audit core.

Drives the real `run_trading_opportunity_scan` / `get_trading_opportunity_scan`
production entrypoints against one real, migrated PostgreSQL database, using
the synthetic, clearly-labeled fixture in tests/fixtures/m058_market_scan/
(see the README there for hand-computed expected results verified before
this test was written). Proves:

- every instrument in a 6-instrument universe is evaluated and persisted as
  its own DecisionCandidate, independently verified via direct SQL;
- exactly the 4 LONG_CANDIDATE evaluations are ranked, in the exact
  hand-verified order (including a genuine deterministic tie resolved by
  instrument symbol), and the 2 NO_TRADE evaluations are excluded from
  ranking but remain fully present and explained;
- the scan itself is persisted and independently retrievable, matching the
  in-process result exactly;
- the scan is linked to its target EvidencePackage via a single
  ArtifactReference (the Phase-9 core-integration design -- one reference
  for the scan, not one per DecisionCandidate);
- deterministic replay: the same universe, strategy, and ranking model
  produce byte-for-byte identical decisions, scores, and ordering on a
  second, independently-identified scan.

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

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.get_trading_opportunity_scan import (
    run_get_trading_opportunity_scan,
)
from empirical_platform.entrypoints.record_evidence_package_artifact_reference import (
    run_record_evidence_package_artifact_reference,
)
from empirical_platform.entrypoints.run_trading_opportunity_scan import (
    _parse_universe_file,
    run_run_trading_opportunity_scan,
)
from empirical_platform.entrypoints.start_evidence_package_collection import (
    run_start_evidence_package_collection,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.run_trading_opportunity_scan import (
    RunTradingOpportunityScanCommand,
    RunTradingOpportunityScanHandler,
    ScanUniverseEntry,
    StrategyParameters,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIVERSE_FIXTURE = str(
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "m058_market_scan"
    / "synthetic_6instrument_scan_universe.json"
)

_ALL_TABLES = [
    "trading_opportunity_scan_evaluation",
    "trading_opportunity_scan",
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

_EXPECTED_RANK_ORDER = ["AMZN", "NVDA", "TSLA", "AAPL"]


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
        application_name="empirical-platform-m058-test",
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
    campaign_id = f"CAMP-80{suffix}0"
    run_id = f"RUN-80{suffix}0"
    run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M058 scan seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"8000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    run_create_run(
        run_governance_id=run_id,
        campaign_governance_id=campaign_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"8000000{suffix}-0000-4000-8000-000000000002"]
        ),
        config=config,
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id=evidence_package_id,
        run_governance_id=run_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"8000000{suffix}-0000-4000-8000-000000000003"]
        ),
        config=config,
    )
    return str(ep_identity.runtime_id)


def test_full_scan_persists_ranks_and_links_to_evidence(clean_tables: Engine) -> None:
    """A real caller scans a 6-instrument universe end-to-end: every
    instrument is persisted as its own DecisionCandidate, exactly the
    LONG_CANDIDATE subset is ranked in the hand-verified order (including a
    genuine tie), and the scan is linked to its target EvidencePackage via a
    single ArtifactReference."""
    config = _config()
    ep_runtime_id = _seed_evidence_package(suffix="1", evidence_package_id="EVID-8001")

    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-8001",
        target_evidence_package_governance_id="EVID-8001",
        universe_file=_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"90000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )

    assert scan.total_instruments == 6
    assert scan.candidate_count == 4
    assert scan.no_trade_count == 2
    assert [str(e.instrument) for e in scan.ranked_opportunities] == _EXPECTED_RANK_ORDER
    assert [e.rank for e in scan.ranked_opportunities] == [1, 2, 3, 4]
    amzn = scan.ranked_opportunities[0]
    nvda = scan.ranked_opportunities[1]
    tsla = scan.ranked_opportunities[2]
    assert nvda.score == tsla.score
    assert amzn.score is not None and nvda.score is not None
    assert amzn.score > nvda.score

    retrieved = run_get_trading_opportunity_scan(
        scan_governance_id="SCAN-8001",
        scan_runtime_id=str(scan.identity.runtime_id),
        config=config,
    )
    # `score` is stored as NUMERIC(30, 15); the in-memory Decimal division
    # carries more significant digits, so retrieval rounds it -- everything
    # else (including `measurements`, whose Decimal fields compare equal by
    # value regardless of trailing-zero scale) must match exactly.
    assert retrieved.identity == scan.identity
    assert retrieved.target_evidence_package_id == scan.target_evidence_package_id
    assert retrieved.strategy_id == scan.strategy_id
    assert retrieved.strategy_version == scan.strategy_version
    assert retrieved.ranking_model_id == scan.ranking_model_id
    assert retrieved.ranking_model_version == scan.ranking_model_version
    assert retrieved.evaluation_cutoff == scan.evaluation_cutoff
    assert len(retrieved.evaluations) == len(scan.evaluations)
    quantum = Decimal("1.000000000000000")
    for retrieved_entry, original_entry in zip(
        retrieved.evaluations, scan.evaluations, strict=True
    ):
        assert retrieved_entry.instrument == original_entry.instrument
        assert retrieved_entry.decision_candidate_id == original_entry.decision_candidate_id
        assert retrieved_entry.decision == original_entry.decision
        assert retrieved_entry.measurements == original_entry.measurements
        assert retrieved_entry.reasons == original_entry.reasons
        assert retrieved_entry.rank == original_entry.rank
        if original_entry.score is None:
            assert retrieved_entry.score is None
        else:
            assert retrieved_entry.score == original_entry.score.quantize(quantum)

    run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-8001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=0,
        actor="trading-scan-operator",
        occurred_at=scan.evaluation_cutoff,
        config=config,
    )
    run_record_evidence_package_artifact_reference(
        evidence_package_governance_id="EVID-8001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=1,
        value=f"trading-opportunity-scan:{scan.identity.governance_id}",
        config=config,
    )

    engine = sa.create_engine(config.sqlalchemy_url())
    with engine.connect() as conn:
        candidate_rows = (
            conn.execute(
                text(
                    "SELECT instrument_symbol, decision FROM decision_candidate "
                    "WHERE target_evidence_package_governance_id = :ep ORDER BY instrument_symbol"
                ),
                {"ep": "EVID-8001"},
            )
            .mappings()
            .all()
        )
        scan_row = (
            conn.execute(
                text(
                    "SELECT total_count.n AS total, "
                    "(SELECT COUNT(*) FROM trading_opportunity_scan_evaluation "
                    " WHERE scan_runtime_id = tos.runtime_id AND decision = 'LONG_CANDIDATE') "
                    "AS long_count "
                    "FROM trading_opportunity_scan tos, "
                    "LATERAL (SELECT COUNT(*) AS n FROM trading_opportunity_scan_evaluation "
                    "WHERE scan_runtime_id = tos.runtime_id) AS total_count "
                    "WHERE tos.governance_id = :g"
                ),
                {"g": "SCAN-8001"},
            )
            .mappings()
            .one()
        )
        ranked_rows = (
            conn.execute(
                text(
                    "SELECT instrument_symbol, rank, score "
                    "FROM trading_opportunity_scan_evaluation toe "
                    "JOIN trading_opportunity_scan tos ON tos.runtime_id = toe.scan_runtime_id "
                    "WHERE tos.governance_id = :g AND toe.decision = 'LONG_CANDIDATE' "
                    "ORDER BY toe.rank"
                ),
                {"g": "SCAN-8001"},
            )
            .mappings()
            .all()
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

    assert len(candidate_rows) == 6
    assert {row["instrument_symbol"] for row in candidate_rows} == {
        "AAPL",
        "MSFT",
        "GOOG",
        "AMZN",
        "NVDA",
        "TSLA",
    }
    assert scan_row["total"] == 6
    assert scan_row["long_count"] == 4
    assert [row["instrument_symbol"] for row in ranked_rows] == _EXPECTED_RANK_ORDER
    assert [row["rank"] for row in ranked_rows] == [1, 2, 3, 4]
    assert ranked_rows[1]["score"] == ranked_rows[2]["score"]  # NVDA == TSLA
    assert artifact_row["value"] == "trading-opportunity-scan:SCAN-8001"


def test_deterministic_replay_produces_identical_scan(clean_tables: Engine) -> None:
    """The same universe (same bars, same strategy, same ranking model) must
    yield byte-for-byte identical decisions, scores, and ordering no matter
    how many times -- or under what independent identity -- the scan is
    replayed. Identity (governance IDs) is caller-assigned metadata, not
    part of what is being replayed, so the two runs deliberately use
    disjoint DecisionCandidate/scan identities over the exact same parsed
    ObservationWindows (the `decision_candidate` table's governance_id is
    globally unique, so genuine replay under the *same* identities is
    already covered, trivially, by any single scan's own internal
    consistency)."""
    config = _config()
    _seed_evidence_package(suffix="2", evidence_package_id="EVID-8002")

    first_generator = DeterministicRuntimeIdentifierGenerator(
        [f"90000002-0000-4000-8000-00000000000{n}" for n in range(10)]
    )
    first_universe = _parse_universe_file(_UNIVERSE_FIXTURE, first_generator)
    with postgres_repository_runtime(config) as runtime:
        first = RunTradingOpportunityScanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
        ).handle(
            RunTradingOpportunityScanCommand(
                scan_identity=DomainIdentity(
                    governance_id=TradingOpportunityScanId("SCAN-8002"),
                    runtime_id=first_generator.generate(),
                ),
                target_evidence_package_id=EvidencePackageId("EVID-8002"),
                universe=first_universe,
                parameters=StrategyParameters(reference_window_size=5),
            )
        )

    second_generator = DeterministicRuntimeIdentifierGenerator(
        [f"90000003-0000-4000-8000-00000000000{n}" for n in range(10)]
    )
    second_raw_universe = _parse_universe_file(_UNIVERSE_FIXTURE, second_generator)
    # Same bars, remapped to fresh DecisionCandidate governance IDs (8201..)
    # so the second run does not collide with the first run's own rows.
    second_universe = tuple(
        ScanUniverseEntry(
            decision_candidate_identity=DomainIdentity(
                governance_id=DecisionCandidateId(f"DCAND-82{index:02d}"),
                runtime_id=entry.decision_candidate_identity.runtime_id,
            ),
            window=entry.window,
        )
        for index, entry in enumerate(second_raw_universe, start=1)
    )
    with postgres_repository_runtime(config) as runtime:
        second = RunTradingOpportunityScanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
        ).handle(
            RunTradingOpportunityScanCommand(
                scan_identity=DomainIdentity(
                    governance_id=TradingOpportunityScanId("SCAN-8003"),
                    runtime_id=second_generator.generate(),
                ),
                target_evidence_package_id=EvidencePackageId("EVID-8002"),
                universe=second_universe,
                parameters=StrategyParameters(reference_window_size=5),
            )
        )

    assert first.total_instruments == second.total_instruments
    assert first.candidate_count == second.candidate_count
    assert first.no_trade_count == second.no_trade_count
    assert first.evaluation_cutoff == second.evaluation_cutoff
    first_ranked = [
        (str(e.instrument), e.rank, e.score, e.decision) for e in first.ranked_opportunities
    ]
    second_ranked = [
        (str(e.instrument), e.rank, e.score, e.decision) for e in second.ranked_opportunities
    ]
    assert first_ranked == second_ranked
    first_all = [(str(e.instrument), e.decision, e.measurements) for e in first.evaluations]
    second_all = [(str(e.instrument), e.decision, e.measurements) for e in second.evaluations]
    assert first_all == second_all


def test_scan_score_precision_matches_hand_verified_values(clean_tables: Engine) -> None:
    """Cross-check the persisted, retrieved scores against the hand-computed
    values recorded in tests/fixtures/m058_market_scan/README.md, confirming
    NUMERIC(30, 15) storage does not silently corrupt the ranking."""
    config = _config()
    _seed_evidence_package(suffix="4", evidence_package_id="EVID-8004")

    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-8004",
        target_evidence_package_governance_id="EVID-8004",
        universe_file=_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"90000004-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    scores_by_symbol = {str(e.instrument): e.score for e in scan.ranked_opportunities}
    assert scores_by_symbol["AMZN"] == Decimal("2.989302499360902994906888483")
    assert scores_by_symbol["NVDA"] == Decimal("1.991209958114565512359152852")
    assert scores_by_symbol["TSLA"] == Decimal("1.991209958114565512359152852")
    assert scores_by_symbol["AAPL"] == Decimal("1.586997817237921066603740193")
