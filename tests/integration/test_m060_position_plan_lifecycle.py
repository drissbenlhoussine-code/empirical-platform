"""MILESTONE-060 real-PostgreSQL end-to-end acceptance test for deterministic
position sizing and capital exposure gating."""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionPlanRejectionReason,
    PositionPlanStatus,
    PositionSizingContext,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints.build_position_plan import run_build_position_plan
from empirical_platform.entrypoints.build_trade_plan import run_build_trade_plan
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.get_position_plan import run_get_position_plan
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
from empirical_platform.identifiers.types import PositionPlanId, TradePlanId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
)
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)
from empirical_platform.usecases.build_position_plan import (
    BuildPositionPlanCommand,
    BuildPositionPlanHandler,
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

_ALL_TABLES = [
    "position_plan",
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
        application_name="empirical-platform-m060-test",
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
    config = _config()
    campaign_id = f"CAMP-96{suffix}0"
    run_id = f"RUN-96{suffix}0"
    run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M060 position-plan seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"9600000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    run_create_run(
        run_governance_id=run_id,
        campaign_governance_id=campaign_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"9600000{suffix}-0000-4000-8000-000000000002"]
        ),
        config=config,
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id=evidence_package_id,
        run_governance_id=run_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"9600000{suffix}-0000-4000-8000-000000000003"]
        ),
        config=config,
    )
    return str(ep_identity.runtime_id)


def _candidate_lookup(
    config: PostgreSQLConfigSnapshot, evidence_package_id: str
) -> dict[str, tuple[str, str]]:
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


def _independent_quantity(
    *,
    entry_price: Decimal,
    risk_per_unit: Decimal,
    equity: Decimal,
    risk_percent: Decimal,
) -> dict[str, Decimal | int]:
    allowed_risk_amount = equity * risk_percent
    maximum_notional = equity * DEFAULT_SIZING_POLICY.maximum_notional_percent
    risk_based_quantity = int(
        (allowed_risk_amount / risk_per_unit).to_integral_value(rounding=ROUND_FLOOR)
    )
    capital_based_quantity = int(
        (maximum_notional / entry_price).to_integral_value(rounding=ROUND_FLOOR)
    )
    quantity = min(risk_based_quantity, capital_based_quantity)
    if risk_based_quantity <= 0 or capital_based_quantity <= 0:
        quantity = 0
    return {
        "allowed_risk_amount": allowed_risk_amount,
        "maximum_notional": maximum_notional,
        "risk_based_quantity": risk_based_quantity,
        "capital_based_quantity": capital_based_quantity,
        "quantity": quantity,
        "position_notional": Decimal(quantity) * entry_price,
        "actual_risk": Decimal(quantity) * risk_per_unit,
    }


def test_full_position_plan_lifecycle_and_raw_sql_verification(clean_tables: Engine) -> None:
    """Drive M057 -> M058 -> M059 -> M060 through real production entrypoints,
    then verify approved, small-budget, capital-capped, rejected-source, and
    evidence-linkage outcomes independently via raw SQL."""
    config = _config()
    ep_runtime_id = _seed_evidence_package(suffix="1", evidence_package_id="EVID-9601")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9601",
        target_evidence_package_governance_id="EVID-9601",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"96100001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9601")

    aapl_gov, aapl_runtime = candidates["AAPL"]
    msft_gov, msft_runtime = candidates["MSFT"]

    approved_trade_plan = run_build_trade_plan(
        plan_governance_id="PLAN-9601",
        source_scan_governance_id="SCAN-9601",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=aapl_gov,
        source_decision_candidate_runtime_id=aapl_runtime,
        target_evidence_package_governance_id="EVID-9601",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96200001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    rejected_trade_plan = run_build_trade_plan(
        plan_governance_id="PLAN-9602",
        source_scan_governance_id="SCAN-9601",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=msft_gov,
        source_decision_candidate_runtime_id=msft_runtime,
        target_evidence_package_governance_id="EVID-9601",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96200002-0000-4000-8000-000000000001"]
        ),
        config=config,
    )

    assert approved_trade_plan.geometry is not None
    geometry = approved_trade_plan.geometry
    safe_equity = geometry.entry_price * Decimal("100")
    one_share_risk_percent = geometry.risk_per_unit / safe_equity
    approved_position_plan = run_build_position_plan(
        position_plan_governance_id="POS-9601",
        source_trade_plan_governance_id="PLAN-9601",
        source_trade_plan_runtime_id=str(approved_trade_plan.identity.runtime_id),
        account_equity=safe_equity,
        risk_percent=one_share_risk_percent,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96300001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    small_budget_equity = geometry.entry_price * Decimal("4")
    tiny_risk_percent = (geometry.risk_per_unit / small_budget_equity) / Decimal("2")
    small_budget_plan = run_build_position_plan(
        position_plan_governance_id="POS-9602",
        source_trade_plan_governance_id="PLAN-9601",
        source_trade_plan_runtime_id=str(approved_trade_plan.identity.runtime_id),
        account_equity=small_budget_equity,
        risk_percent=tiny_risk_percent,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96300002-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    capital_capped_equity = geometry.entry_price * Decimal("4")
    capital_capped_risk_percent = min(
        DEFAULT_SIZING_POLICY.maximum_risk_percent,
        (geometry.risk_per_unit * Decimal("2")) / capital_capped_equity,
    )
    capital_capped_plan = run_build_position_plan(
        position_plan_governance_id="POS-9603",
        source_trade_plan_governance_id="PLAN-9601",
        source_trade_plan_runtime_id=str(approved_trade_plan.identity.runtime_id),
        account_equity=capital_capped_equity,
        risk_percent=capital_capped_risk_percent,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96300003-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    rejected_source_position_plan = run_build_position_plan(
        position_plan_governance_id="POS-9604",
        source_trade_plan_governance_id="PLAN-9602",
        source_trade_plan_runtime_id=str(rejected_trade_plan.identity.runtime_id),
        account_equity=safe_equity,
        risk_percent=one_share_risk_percent,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96300004-0000-4000-8000-000000000001"]
        ),
        config=config,
    )

    assert approved_position_plan.status is PositionPlanStatus.APPROVED_POSITION_PLAN
    assert approved_position_plan.sizing is not None
    assert approved_position_plan.sizing.quantity == 1

    assert small_budget_plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert small_budget_plan.reasons == (PositionPlanRejectionReason.ZERO_POSITION_SIZE,)

    assert capital_capped_plan.status is PositionPlanStatus.APPROVED_POSITION_PLAN
    assert capital_capped_plan.sizing is not None
    assert capital_capped_plan.sizing.capital_based_quantity == 1
    assert capital_capped_plan.sizing.risk_based_quantity >= 2
    assert capital_capped_plan.sizing.quantity == 1

    assert rejected_source_position_plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert rejected_source_position_plan.reasons == (
        PositionPlanRejectionReason.SOURCE_PLAN_NOT_APPROVED,
    )

    run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-9601",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=0,
        actor="m060-operator",
        occurred_at=approved_trade_plan.evaluation_cutoff,
        config=config,
    )
    run_record_evidence_package_artifact_reference(
        evidence_package_governance_id="EVID-9601",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=1,
        value="trade-plan:PLAN-9601",
        config=config,
    )
    run_record_evidence_package_artifact_reference(
        evidence_package_governance_id="EVID-9601",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=2,
        value="trade-plan:PLAN-9602",
        config=config,
    )
    for expected_version, position_id in enumerate(
        ("POS-9601", "POS-9602", "POS-9603", "POS-9604"),
        start=3,
    ):
        run_record_evidence_package_artifact_reference(
            evidence_package_governance_id="EVID-9601",
            evidence_package_runtime_id=ep_runtime_id,
            expected_persisted_version=expected_version,
            value=f"position-plan:{position_id}",
            config=config,
        )

    retrieved = run_get_position_plan(
        position_plan_governance_id="POS-9603",
        position_plan_runtime_id=str(capital_capped_plan.identity.runtime_id),
        config=config,
    )
    assert retrieved.identity == capital_capped_plan.identity
    assert retrieved.source_trade_plan_id == capital_capped_plan.source_trade_plan_id
    assert retrieved.status == capital_capped_plan.status
    assert retrieved.reasons == capital_capped_plan.reasons
    assert retrieved.sizing == capital_capped_plan.sizing
    assert retrieved.supplied_account_equity == capital_capped_plan.supplied_account_equity
    assert retrieved.supplied_risk_percent == capital_capped_plan.supplied_risk_percent.quantize(
        Decimal("1.000000000000000")
    )

    independent = _independent_quantity(
        entry_price=geometry.entry_price,
        risk_per_unit=geometry.risk_per_unit,
        equity=capital_capped_equity,
        risk_percent=capital_capped_risk_percent,
    )
    assert capital_capped_plan.sizing is not None
    assert capital_capped_plan.sizing.allowed_risk_amount == independent["allowed_risk_amount"]
    assert capital_capped_plan.sizing.maximum_notional == independent["maximum_notional"]
    assert capital_capped_plan.sizing.risk_based_quantity == independent["risk_based_quantity"]
    assert (
        capital_capped_plan.sizing.capital_based_quantity == independent["capital_based_quantity"]
    )
    assert capital_capped_plan.sizing.quantity == independent["quantity"]
    assert capital_capped_plan.sizing.position_notional == independent["position_notional"]
    assert capital_capped_plan.sizing.actual_risk == independent["actual_risk"]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            position_rows = (
                conn.execute(
                    text(
                        "SELECT governance_id, source_trade_plan_governance_id, status, reasons, "
                        "supplied_account_equity, supplied_risk_percent, "
                        "policy_id, policy_version, policy_maximum_risk_percent, "
                        "policy_maximum_notional_percent, quantity, position_notional, "
                        "actual_risk, risk_based_quantity, capital_based_quantity "
                        "FROM position_plan ORDER BY governance_id"
                    )
                )
                .mappings()
                .all()
            )
            artifact_rows = (
                conn.execute(
                    text(
                        "SELECT value FROM evidence_package_artifact_reference "
                        "WHERE evidence_package_runtime_id = :runtime_id ORDER BY position"
                    ),
                    {"runtime_id": ep_runtime_id},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    rows_by_id = {row["governance_id"]: row for row in position_rows}
    assert rows_by_id["POS-9601"]["status"] == "APPROVED_POSITION_PLAN"
    assert rows_by_id["POS-9601"]["quantity"] == 1
    assert rows_by_id["POS-9602"]["reasons"] == ["ZERO_POSITION_SIZE"]
    assert rows_by_id["POS-9603"]["source_trade_plan_governance_id"] == "PLAN-9601"
    assert rows_by_id["POS-9603"]["quantity"] == 1
    assert rows_by_id["POS-9603"]["position_notional"] == independent["position_notional"]
    assert rows_by_id["POS-9603"]["actual_risk"] == independent["actual_risk"]
    assert rows_by_id["POS-9603"]["risk_based_quantity"] == independent["risk_based_quantity"]
    assert rows_by_id["POS-9603"]["capital_based_quantity"] == independent["capital_based_quantity"]
    assert rows_by_id["POS-9604"]["reasons"] == ["SOURCE_PLAN_NOT_APPROVED"]
    assert [row["value"] for row in artifact_rows] == [
        "trade-plan:PLAN-9601",
        "trade-plan:PLAN-9602",
        "position-plan:POS-9601",
        "position-plan:POS-9602",
        "position-plan:POS-9603",
        "position-plan:POS-9604",
    ]


def test_policy_boundary_exact_maximum_risk_percent_is_approved(clean_tables: Engine) -> None:
    config = _config()
    _seed_evidence_package(suffix="2", evidence_package_id="EVID-9602")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9602",
        target_evidence_package_governance_id="EVID-9602",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"96400001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9602")
    aapl_gov, aapl_runtime = candidates["AAPL"]
    trade_plan = run_build_trade_plan(
        plan_governance_id="PLAN-9605",
        source_scan_governance_id="SCAN-9602",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=aapl_gov,
        source_decision_candidate_runtime_id=aapl_runtime,
        target_evidence_package_governance_id="EVID-9602",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96500001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    assert trade_plan.geometry is not None
    plan = run_build_position_plan(
        position_plan_governance_id="POS-9605",
        source_trade_plan_governance_id="PLAN-9605",
        source_trade_plan_runtime_id=str(trade_plan.identity.runtime_id),
        account_equity=trade_plan.geometry.entry_price * Decimal("4"),
        risk_percent=DEFAULT_SIZING_POLICY.maximum_risk_percent,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96600001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    assert plan.status is PositionPlanStatus.APPROVED_POSITION_PLAN
    assert plan.sizing is not None
    assert plan.sizing.position_notional == plan.sizing.maximum_notional


def test_duplicate_position_plan_identity_raises_aggregate_already_exists(
    clean_tables: Engine,
) -> None:
    config = _config()
    _seed_evidence_package(suffix="3", evidence_package_id="EVID-9603")
    scan = run_run_trading_opportunity_scan(
        scan_governance_id="SCAN-9603",
        target_evidence_package_governance_id="EVID-9603",
        universe_file=_M058_UNIVERSE_FIXTURE,
        reference_window_size=5,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"96700001-0000-4000-8000-00000000000{n}" for n in range(10)]
        ),
        config=config,
    )
    candidates = _candidate_lookup(config, "EVID-9603")
    aapl_gov, aapl_runtime = candidates["AAPL"]
    trade_plan = run_build_trade_plan(
        plan_governance_id="PLAN-9606",
        source_scan_governance_id="SCAN-9603",
        source_scan_runtime_id=str(scan.identity.runtime_id),
        source_decision_candidate_governance_id=aapl_gov,
        source_decision_candidate_runtime_id=aapl_runtime,
        target_evidence_package_governance_id="EVID-9603",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["96800001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )

    with postgres_repository_runtime(config) as runtime:
        handler = BuildPositionPlanHandler(
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
        )
        command = BuildPositionPlanCommand(
            identity=DomainIdentity(
                governance_id=PositionPlanId("POS-9606"),
                runtime_id=RuntimeIdentifier("96900001-0000-4000-8000-000000000001"),
            ),
            source_trade_plan_identity=trade_plan.identity,
            sizing_context=PositionSizingContext(
                account_equity=Decimal("10000"),
                risk_percent=Decimal("0.01"),
            ),
        )
        handler.handle(command)
        with pytest.raises(AggregateAlreadyExists):
            handler.handle(command)


def test_missing_source_trade_plan_raises_aggregate_not_found(clean_tables: Engine) -> None:
    config = _config()
    with postgres_repository_runtime(config) as runtime:
        handler = BuildPositionPlanHandler(
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
        )
        command = BuildPositionPlanCommand(
            identity=DomainIdentity(
                governance_id=PositionPlanId("POS-9607"),
                runtime_id=RuntimeIdentifier("97000001-0000-4000-8000-000000000001"),
            ),
            source_trade_plan_identity=DomainIdentity(
                governance_id=TradePlanId("PLAN-9999"),
                runtime_id=RuntimeIdentifier("97100001-0000-4000-8000-000000000001"),
            ),
            sizing_context=PositionSizingContext(
                account_equity=Decimal("10000"),
                risk_percent=Decimal("0.01"),
            ),
        )
        with pytest.raises(AggregateNotFound):
            handler.handle(command)
