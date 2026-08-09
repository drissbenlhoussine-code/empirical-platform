"""MILESTONE-059 real-PostgreSQL end-to-end acceptance test for the
risk-gated trade plan: is a ranked LONG_CANDIDATE actually a trade worth
taking?

Drives the real `build_trade_plan` / `get_trade_plan` production
entrypoints against one real, migrated PostgreSQL database, reusing the
M058 `run_trading_opportunity_scan` production entrypoint and the existing
M058 six-instrument fixture (see tests/fixtures/m058_market_scan/README.md
for hand-computed expected results) plus one small, purpose-built M059
boundary fixture (tests/fixtures/m059_trade_plan/README.md). Proves:

- a real APPROVED_PLAN (AAPL -- notably the *worst-ranked* (#4) of the four
  LONG_CANDIDATE instruments in the M058 scan);
- a real REJECTED_PLAN due to invalid target geometry, produced by the
  *highest-ranked* (#1) instrument (AMZN) -- the single clearest proof that
  a high ranking score does not mean an approved trade;
- a real REJECTED_PLAN due to reward/risk below the policy minimum (NVDA);
- a real REJECTED_PLAN due to an invalid (NO_TRADE) source (MSFT);
- a boundary-exact APPROVED_PLAN and a just-below REJECTED_PLAN at the
  policy's own minimum reward/risk ratio;
- hostile source-integrity rejection: a claimed scan/candidate pairing
  that does not actually belong together;
- duplicate plan identity raises AggregateAlreadyExists;
- each plan is persisted and independently retrievable, and linked to its
  target EvidencePackage via its own ArtifactReference.

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
from empirical_platform.entrypoints.build_trade_plan import run_build_trade_plan
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.get_trade_plan import run_get_trade_plan
from empirical_platform.entrypoints.record_evidence_package_artifact_reference import (
    run_record_evidence_package_artifact_reference,
)
from empirical_platform.entrypoints.run_trading_opportunity_scan import (
    run_run_trading_opportunity_scan,
)
from empirical_platform.entrypoints.start_evidence_package_collection import (
    run_start_evidence_package_collection,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateNotFound
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)
from empirical_platform.usecases.build_trade_plan import (
    DEFAULT_RISK_POLICY,
    BuildTradePlanCommand,
    BuildTradePlanHandler,
    TradePlan,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_M058_UNIVERSE_FIXTURE = str(
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "m058_market_scan"
    / "synthetic_6instrument_scan_universe.json"
)
_M059_BOUNDARY_FIXTURE = str(
    _REPO_ROOT / "tests" / "fixtures" / "m059_trade_plan" / "synthetic_boundary_ratio_universe.json"
)
_M059_SECOND_SCAN_FIXTURE = str(
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "m059_trade_plan"
    / "synthetic_6instrument_scan_universe_second_scan.json"
)

_ALL_TABLES = [
    "trade_plan",
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
        application_name="empirical-platform-m059-test",
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
    campaign_id = f"CAMP-90{suffix}0"
    run_id = f"RUN-90{suffix}0"
    run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M059 trade-plan seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"9000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    run_create_run(
        run_governance_id=run_id,
        campaign_governance_id=campaign_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"9000000{suffix}-0000-4000-8000-000000000002"]
        ),
        config=config,
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id=evidence_package_id,
        run_governance_id=run_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"9000000{suffix}-0000-4000-8000-000000000003"]
        ),
        config=config,
    )
    return str(ep_identity.runtime_id)


def _candidate_lookup(
    config: PostgreSQLConfigSnapshot, evidence_package_id: str
) -> dict[str, tuple[str, str]]:
    """Return {instrument_symbol: (governance_id, runtime_id)} for every
    DecisionCandidate targeting `evidence_package_id`."""
    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT instrument_symbol, governance_id, runtime_id "
                        "FROM decision_candidate "
                        "WHERE target_evidence_package_governance_id = :ep"
                    ),
                    {"ep": evidence_package_id},
                )
                .mappings()
                .all()
            )
        return {
            row["instrument_symbol"]: (row["governance_id"], str(row["runtime_id"])) for row in rows
        }
    finally:
        engine.dispose()


def test_full_trade_plan_lifecycle_approved_and_rejected(clean_tables: Engine) -> None:
    """A real caller scans the M058 six-instrument universe, then builds
    trade plans for four of the resulting candidates -- proving a real
    APPROVED_PLAN, a real REJECTED_PLAN from the *highest-ranked*
    candidate (invalid target geometry), a real REJECTED_PLAN from a
    below-threshold candidate, and a real REJECTED_PLAN from a NO_TRADE
    source -- each persisted, retrievable, and linked to evidence."""
    config = _config()
    ep_runtime_id = _seed_evidence_package(suffix="1", evidence_package_id="EVID-9001")

    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9001",
        target_evidence_package_governance_id="EVID-9001",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"91000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9001")

    def _build(symbol: str, plan_id: str, n: int) -> TradePlan:
        gov_id, runtime_id = candidates[symbol]
        return run_build_trade_plan(
            plan_governance_id=plan_id,
            source_scan_governance_id="SCAN-9001",
            source_scan_runtime_id=str(scan.identity.runtime_id),
            source_decision_candidate_governance_id=gov_id,
            source_decision_candidate_runtime_id=runtime_id,
            target_evidence_package_governance_id="EVID-9001",
            identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [f"9200000{n}-0000-4000-8000-000000000001"]
            ),
            config=config,
        )

    approved = _build("AAPL", "PLAN-9001", 1)
    rejected_target = _build("AMZN", "PLAN-9002", 2)
    rejected_ratio = _build("NVDA", "PLAN-9003", 3)
    rejected_source = _build("MSFT", "PLAN-9004", 4)

    assert approved.status.value == "APPROVED_PLAN"
    assert approved.reasons == ()
    assert approved.geometry is not None
    assert approved.geometry.reward_risk_ratio == Decimal("2.35")

    assert rejected_target.status.value == "REJECTED_PLAN"
    assert [r.value for r in rejected_target.reasons] == ["INVALID_TARGET_GEOMETRY"]
    assert rejected_target.geometry is None

    assert rejected_ratio.status.value == "REJECTED_PLAN"
    assert [r.value for r in rejected_ratio.reasons] == ["REWARD_RISK_BELOW_MINIMUM"]
    assert rejected_ratio.geometry is not None
    assert rejected_ratio.geometry.reward_risk_ratio == Decimal("0.34")

    assert rejected_source.status.value == "REJECTED_PLAN"
    assert [r.value for r in rejected_source.reasons] == ["SOURCE_NOT_LONG_CANDIDATE"]
    assert rejected_source.geometry is None

    # Independent retrieval matches the in-process result.
    retrieved = run_get_trade_plan(
        plan_governance_id="PLAN-9001",
        plan_runtime_id=str(approved.identity.runtime_id),
        config=config,
    )
    assert retrieved.status == approved.status
    assert retrieved.geometry is not None
    assert retrieved.geometry.reward_risk_ratio == approved.geometry.reward_risk_ratio

    # Each plan (approved and rejected) is linked to evidence via its own
    # ArtifactReference -- a rejected plan is as auditable as an approved one.
    run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-9001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=0,
        actor="trade-plan-operator",
        occurred_at=scan.evaluation_cutoff,
        config=config,
    )
    for position, plan_id in enumerate(
        ["PLAN-9001", "PLAN-9002", "PLAN-9003", "PLAN-9004"], start=1
    ):
        run_record_evidence_package_artifact_reference(
            evidence_package_governance_id="EVID-9001",
            evidence_package_runtime_id=ep_runtime_id,
            expected_persisted_version=position,
            value=f"trade-plan:{plan_id}",
            config=config,
        )

    engine = sa.create_engine(config.sqlalchemy_url())
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT instrument_symbol, status, reasons FROM trade_plan "
                    "WHERE target_evidence_package_governance_id = :ep ORDER BY instrument_symbol"
                ),
                {"ep": "EVID-9001"},
            )
            .mappings()
            .all()
        )
        artifact_rows = (
            conn.execute(
                text(
                    "SELECT value FROM evidence_package_artifact_reference "
                    "WHERE evidence_package_runtime_id = :ep ORDER BY position"
                ),
                {"ep": ep_runtime_id},
            )
            .mappings()
            .all()
        )
    engine.dispose()

    rows_by_symbol = {row["instrument_symbol"]: row for row in rows}
    assert rows_by_symbol["AAPL"]["status"] == "APPROVED_PLAN"
    assert rows_by_symbol["AAPL"]["reasons"] == []
    assert rows_by_symbol["AMZN"]["status"] == "REJECTED_PLAN"
    assert rows_by_symbol["AMZN"]["reasons"] == ["INVALID_TARGET_GEOMETRY"]
    assert rows_by_symbol["NVDA"]["status"] == "REJECTED_PLAN"
    assert rows_by_symbol["NVDA"]["reasons"] == ["REWARD_RISK_BELOW_MINIMUM"]
    assert rows_by_symbol["MSFT"]["status"] == "REJECTED_PLAN"
    assert rows_by_symbol["MSFT"]["reasons"] == ["SOURCE_NOT_LONG_CANDIDATE"]
    assert len(artifact_rows) == 4
    assert {row["value"] for row in artifact_rows} == {
        "trade-plan:PLAN-9001",
        "trade-plan:PLAN-9002",
        "trade-plan:PLAN-9003",
        "trade-plan:PLAN-9004",
    }


def test_boundary_reward_risk_ratio_exact_and_just_below(clean_tables: Engine) -> None:
    """A purpose-built instrument at the policy's exact minimum R:R must be
    APPROVED (inclusive `>=`); one cent higher (lower R:R) must be
    REJECTED."""
    config = _config()
    _seed_evidence_package(suffix="2", evidence_package_id="EVID-9002")

    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9002",
        target_evidence_package_governance_id="EVID-9002",
        universe_file=_M059_BOUNDARY_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"94000001-0000-4000-8000-00000000000{n}" for n in range(6)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9002")

    exact_gov, exact_runtime = candidates["BNDA"]
    below_gov, below_runtime = candidates["BNDB"]

    exact_plan = run_build_trade_plan(
        plan_governance_id="PLAN-9201",
        source_scan_governance_id="SCAN-9002",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=exact_gov,
        source_decision_candidate_runtime_id=exact_runtime,
        target_evidence_package_governance_id="EVID-9002",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["95000001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    below_plan = run_build_trade_plan(
        plan_governance_id="PLAN-9202",
        source_scan_governance_id="SCAN-9002",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=below_gov,
        source_decision_candidate_runtime_id=below_runtime,
        target_evidence_package_governance_id="EVID-9002",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["95000002-0000-4000-8000-000000000001"]
        ),
        config=config,
    )

    assert exact_plan.geometry is not None
    assert exact_plan.geometry.reward_risk_ratio == Decimal("2.0")
    assert exact_plan.status.value == "APPROVED_PLAN"

    assert below_plan.geometry is not None
    assert below_plan.geometry.reward_risk_ratio < Decimal("2.0")
    assert below_plan.status.value == "REJECTED_PLAN"
    assert [r.value for r in below_plan.reasons] == ["REWARD_RISK_BELOW_MINIMUM"]


def test_hostile_mismatched_scan_and_candidate_is_rejected(clean_tables: Engine) -> None:
    """A candidate that genuinely exists but was never evaluated as part of
    the claimed scan must be rejected with PROVENANCE_MISMATCH -- never
    silently approved or silently treated as belonging."""
    config = _config()
    _seed_evidence_package(suffix="3", evidence_package_id="EVID-9003")
    _seed_evidence_package(suffix="4", evidence_package_id="EVID-9004")

    scan_a = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9003",
        target_evidence_package_governance_id="EVID-9003",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"96000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    # A second, independent scan produces its own, genuinely different
    # DecisionCandidate for the same instrument set (identical bars, but a
    # distinct DecisionCandidate governance-id namespace so it does not
    # collide with scan A's own candidates).
    run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9004",
        target_evidence_package_governance_id="EVID-9004",
        universe_file=_M059_SECOND_SCAN_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"97000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    scan_b_candidates = _candidate_lookup(config, "EVID-9004")
    other_gov, other_runtime = scan_b_candidates["AAPL"]

    plan = run_build_trade_plan(
        plan_governance_id="PLAN-9301",
        source_scan_governance_id="SCAN-9003",  # scan A
        source_scan_runtime_id=str(scan_a.identity.runtime_id),
        source_decision_candidate_governance_id=other_gov,  # candidate from scan B
        source_decision_candidate_runtime_id=other_runtime,
        target_evidence_package_governance_id="EVID-9003",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["98000001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )

    assert plan.status.value == "REJECTED_PLAN"
    assert [r.value for r in plan.reasons] == ["PROVENANCE_MISMATCH"]
    assert plan.geometry is None


def test_duplicate_plan_identity_raises_aggregate_already_exists(clean_tables: Engine) -> None:
    """Attempting to build a second plan under the same identity must raise
    `AggregateAlreadyExists`, never silently overwrite."""
    config = _config()
    _seed_evidence_package(suffix="5", evidence_package_id="EVID-9005")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9005",
        target_evidence_package_governance_id="EVID-9005",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"99000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9005")
    aapl_gov, aapl_runtime = candidates["AAPL"]

    with postgres_repository_runtime(config) as runtime:
        handler = BuildTradePlanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
        )
        command = BuildTradePlanCommand(
            identity=DomainIdentity(
                governance_id=TradePlanId("PLAN-9401"),
                runtime_id=RuntimeIdentifier("a1000001-0000-4000-8000-000000000001"),
            ),
            source_scan_identity=scan.identity,
            source_decision_candidate_identity=DomainIdentity(
                governance_id=DecisionCandidateId(aapl_gov),
                runtime_id=RuntimeIdentifier(aapl_runtime),
            ),
            target_evidence_package_id=EvidencePackageId("EVID-9005"),
            policy=DEFAULT_RISK_POLICY,
        )
        handler.handle(command)
        with pytest.raises(Exception, match="already exists"):
            handler.handle(command)


def test_missing_source_scan_raises_aggregate_not_found(clean_tables: Engine) -> None:
    """A `source_scan_identity` that was never persisted must propagate
    `AggregateNotFound` untouched -- no swallowed exception, no silent
    fallback plan."""
    config = _config()
    _seed_evidence_package(suffix="6", evidence_package_id="EVID-9006")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9006",
        target_evidence_package_governance_id="EVID-9006",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"a0000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9006")
    aapl_gov, aapl_runtime = candidates["AAPL"]

    with postgres_repository_runtime(config) as runtime:
        handler = BuildTradePlanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
        )
        command = BuildTradePlanCommand(
            identity=DomainIdentity(
                governance_id=TradePlanId("PLAN-9501"),
                runtime_id=RuntimeIdentifier("a2000001-0000-4000-8000-000000000001"),
            ),
            source_scan_identity=DomainIdentity(
                governance_id=TradingOpportunityScanId("SCAN-9999"),  # never persisted
                runtime_id=RuntimeIdentifier("a3000001-0000-4000-8000-000000000001"),
            ),
            source_decision_candidate_identity=DomainIdentity(
                governance_id=DecisionCandidateId(aapl_gov),
                runtime_id=RuntimeIdentifier(aapl_runtime),
            ),
            target_evidence_package_id=EvidencePackageId("EVID-9006"),
            policy=DEFAULT_RISK_POLICY,
        )
        with pytest.raises(AggregateNotFound):
            handler.handle(command)
    assert str(scan.identity.governance_id) == "SCAN-9006"  # scan A itself is untouched


def test_missing_source_decision_candidate_raises_aggregate_not_found(
    clean_tables: Engine,
) -> None:
    """A `source_decision_candidate_identity` that was never persisted must
    propagate `AggregateNotFound` untouched."""
    config = _config()
    _seed_evidence_package(suffix="7", evidence_package_id="EVID-9007")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9007",
        target_evidence_package_governance_id="EVID-9007",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"a4000001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )

    with postgres_repository_runtime(config) as runtime:
        handler = BuildTradePlanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
        )
        command = BuildTradePlanCommand(
            identity=DomainIdentity(
                governance_id=TradePlanId("PLAN-9601"),
                runtime_id=RuntimeIdentifier("a5000001-0000-4000-8000-000000000001"),
            ),
            source_scan_identity=scan.identity,
            source_decision_candidate_identity=DomainIdentity(
                governance_id=DecisionCandidateId("DCAND-9999"),  # never persisted
                runtime_id=RuntimeIdentifier("a6000001-0000-4000-8000-000000000001"),
            ),
            target_evidence_package_id=EvidencePackageId("EVID-9007"),
            policy=DEFAULT_RISK_POLICY,
        )
        with pytest.raises(AggregateNotFound):
            handler.handle(command)


def test_reward_risk_ratio_precision_survives_storage_rounding(clean_tables: Engine) -> None:
    """The `below` boundary case has a genuinely repeating-decimal ratio
    (1.33/0.68 = 1.9558823529411764...); confirm it round-trips through
    NUMERIC(30, 15) storage without corrupting the APPROVED/REJECTED
    decision, and that retrieval matches the in-memory value once rounded
    to the column's own precision."""
    config = _config()
    _seed_evidence_package(suffix="8", evidence_package_id="EVID-9008")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9008",
        target_evidence_package_governance_id="EVID-9008",
        universe_file=_M059_BOUNDARY_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"a7000001-0000-4000-8000-00000000000{n}" for n in range(6)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9008")
    below_gov, below_runtime = candidates["BNDB"]

    plan = run_build_trade_plan(
        plan_governance_id="PLAN-9701",
        source_scan_governance_id="SCAN-9008",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=below_gov,
        source_decision_candidate_runtime_id=below_runtime,
        target_evidence_package_governance_id="EVID-9008",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["a8000001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    assert plan.geometry is not None
    in_memory_ratio = plan.geometry.reward_risk_ratio
    assert str(in_memory_ratio).startswith("1.95588235294117")

    retrieved = run_get_trade_plan(
        plan_governance_id="PLAN-9701",
        plan_runtime_id=str(plan.identity.runtime_id),
        config=config,
    )
    assert retrieved.geometry is not None
    quantum = Decimal("1.000000000000000")
    assert retrieved.geometry.reward_risk_ratio == in_memory_ratio.quantize(quantum)
    assert retrieved.status == plan.status
    assert plan.status.value == "REJECTED_PLAN"
