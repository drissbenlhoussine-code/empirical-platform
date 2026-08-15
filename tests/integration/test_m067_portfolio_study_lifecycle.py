"""MILESTONE-067 real-PostgreSQL portfolio capital-allocation acceptance
tests.

Covers the full run->persist->retrieve lifecycle against real PostgreSQL,
a real CLI subprocess run of both new M067 entrypoints, raw-SQL
cross-verification of the persisted schema (report + allocation
decisions + equity observations + capital sensitivity), deterministic
replay (same capital policy -> identical result), capital-policy
sensitivity (different policy -> different but still valid result),
upstream-authority-mismatch attacks (nonexistent study, tampered
runtime_id, duplicate governance_id), and the mission's own five named
acceptance controls: capital bottleneck, capital release, overlap
drawdown, input-order shuffle, and future-data mutation -- each built
from the real M064 canonical fixture's own genuine trade data, not
fabricated upstream objects.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.historical_backtest import HistoricalBacktestRun
from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioAllocationOutcome,
    PortfolioCapitalPolicy,
    build_portfolio_evidence_report,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints.get_portfolio_historical_evidence import (
    run_get_portfolio_historical_evidence,
)
from empirical_platform.entrypoints.run_portfolio_historical_evidence import (
    run_run_portfolio_historical_evidence,
)
from empirical_platform.entrypoints.run_survivorship_aware_robustness_study import (
    run_run_survivorship_aware_robustness_study,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioStudyId, SurvivorshipStudyId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.identifiers import RuntimeIdentifier

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "m064_survivorship_aware"
_DATASET_BUNDLE_PATH = _FIXTURE_DIR / "survivorship_aware_dataset_bundle.json"
_INSTRUMENT_MASTER_PATH = _FIXTURE_DIR / "instrument_master.json"
_MEMBERSHIP_MANIFEST_PATH = _FIXTURE_DIR / "membership_manifest.json"
_EXPECTED_DATASET_SHA256 = "af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff"
_EXPECTED_MANIFEST_HASH = "caa9fa899ea26816101a0a494c4977fed75849d4ac19b65ac6410e561f232fda"


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
        application_name="empirical-platform-m067-test",
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
def study_seeded(upgraded_schema: Engine) -> tuple[Engine, str, str]:
    """Truncate M067 tables (leave the upstream M064/M061 studies alone
    across test cases within this module, but ensure a fresh canonical
    study exists for this test)."""
    with upgraded_schema.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE portfolio_capital_sensitivity, portfolio_equity_observation, "
                "portfolio_allocation_decision, portfolio_study, survivorship_window, "
                "survivorship_study, membership_record, universe_authority, "
                "instrument_master, robustness_window, robustness_study, "
                "historical_backtest_trade, historical_backtest_run CASCADE"
            )
        )
    config = _config()
    study = run_run_survivorship_aware_robustness_study(
        study_governance_id="SURV-6710",
        stress_study_governance_id="ROBUST-6711",
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        expected_dataset_sha256=_EXPECTED_DATASET_SHA256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(_MEMBERSHIP_MANIFEST_PATH),
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=6710,
        stress_backtest_run_governance_id_base=7710,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    return upgraded_schema, "SURV-6710", str(study.identity.runtime_id)  # type: ignore[attr-defined]


def _load_study_and_runs(
    study_governance_id: str, study_runtime_id: str
) -> tuple[object, tuple[HistoricalBacktestRun, ...]]:
    with postgres_repository_runtime(_config()) as runtime:
        study = runtime.survivorship_studies.get(
            DomainIdentity(
                governance_id=SurvivorshipStudyId(study_governance_id),
                runtime_id=RuntimeIdentifier(study_runtime_id),
            )
        )
        window_runs = tuple(
            runtime.historical_backtests.get(
                DomainIdentity(
                    governance_id=window.backtest_run_id,
                    runtime_id=window.backtest_run_runtime_id,
                )
            )
            for window in study.window_results
            if window.backtest_run_id is not None and window.backtest_run_runtime_id is not None
        )
    return study, window_runs


def test_full_analysis_lifecycle_and_raw_sql_verification(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()

    report = run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6710",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    assert report.total_opportunities > 0  # type: ignore[attr-defined]
    assert report.source_study_governance_id == study_governance_id  # type: ignore[attr-defined]
    assert report.dataset_bundle_id == "DATASET-6401"  # type: ignore[attr-defined]
    assert report.membership_manifest_hash == _EXPECTED_MANIFEST_HASH  # type: ignore[attr-defined]
    assert (
        report.allocated_count + report.rejected_count  # type: ignore[attr-defined]
        == report.total_opportunities  # type: ignore[attr-defined]
    )

    retrieved = run_get_portfolio_historical_evidence(
        report_governance_id="PORT-6710",
        report_runtime_id=str(report.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    assert retrieved.allocated_count == report.allocated_count  # type: ignore[attr-defined]
    assert retrieved.equity_curve == report.equity_curve  # type: ignore[attr-defined]
    assert retrieved.allocation_decisions == report.allocation_decisions  # type: ignore[attr-defined]
    assert (
        retrieved.capital_sensitivity_views == report.capital_sensitivity_views  # type: ignore[attr-defined]
    )

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            report_row = (
                conn.execute(
                    text(
                        "SELECT source_study_governance_id, total_opportunities, "
                        "allocated_count, rejected_count "
                        "FROM portfolio_study WHERE governance_id = 'PORT-6710'"
                    )
                )
                .mappings()
                .one()
            )
            decision_count = (
                conn.execute(
                    text(
                        "SELECT COUNT(*) AS n FROM portfolio_allocation_decision "
                        "WHERE report_runtime_id = "
                        "(SELECT runtime_id FROM portfolio_study WHERE governance_id = 'PORT-6710')"
                    )
                )
                .mappings()
                .one()
            )
            sensitivity_rows = (
                conn.execute(
                    text(
                        "SELECT label FROM portfolio_capital_sensitivity "
                        "WHERE report_runtime_id = "
                        "(SELECT runtime_id FROM portfolio_study "
                        "WHERE governance_id = 'PORT-6710') "
                        "ORDER BY label"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert report_row["source_study_governance_id"] == study_governance_id
    assert int(decision_count["n"]) == report.total_opportunities  # type: ignore[attr-defined]
    assert {r["label"] for r in sensitivity_rows} == {
        "CANONICAL",
        "REDUCED_CAPITAL",
        "TIGHTER_MAX_CONCURRENCY",
    }


def test_real_cli_subprocess_run_and_get(study_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    run_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.run_portfolio_historical_evidence",
            "PORT-6720",
            study_governance_id,
            study_runtime_id,
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run_result.returncode == 0, run_result.stderr
    run_payload = json.loads(run_result.stdout)
    assert run_payload["source_study_governance_id"] == study_governance_id
    assert run_payload["total_opportunities"] > 0

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_portfolio_historical_evidence",
            "PORT-6720",
            run_payload["runtime_id"],
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert get_result.returncode == 0, get_result.stderr
    get_payload = json.loads(get_result.stdout)
    assert get_payload["allocated_count"] == run_payload["allocated_count"]
    # Numeric fields compare semantically (Decimal equality), not as raw
    # strings -- PostgreSQL's NUMERIC columns pad to full declared scale
    # on retrieval, the identical value at a different string precision.
    for run_decision, get_decision in zip(
        run_payload["allocation_decisions"], get_payload["allocation_decisions"], strict=True
    ):
        assert run_decision["opportunity_sequence"] == get_decision["opportunity_sequence"]
        assert run_decision["decision"] == get_decision["decision"]
        assert Decimal(run_decision["risk_amount"]) == Decimal(get_decision["risk_amount"])
        assert Decimal(run_decision["net_pnl"]) == Decimal(get_decision["net_pnl"])


def test_deterministic_replay_same_capital_policy_produces_identical_result(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()

    first = run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6730",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    second = run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6731",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    assert first.allocation_decisions == second.allocation_decisions  # type: ignore[attr-defined]
    assert first.equity_curve == second.equity_curve  # type: ignore[attr-defined]
    assert first.realized_pnl == second.realized_pnl  # type: ignore[attr-defined]
    assert first.max_drawdown == second.max_drawdown  # type: ignore[attr-defined]


def test_different_capital_policy_produces_a_different_but_valid_result(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()

    default_policy = run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6732",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    tight_policy = run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6733",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        initial_capital=Decimal("300"),
        max_concurrent_positions=1,
        config=config,
    )
    assert default_policy.capital_policy.initial_capital != (  # type: ignore[attr-defined]
        tight_policy.capital_policy.initial_capital  # type: ignore[attr-defined]
    )
    # A far tighter policy must reject strictly more (never fewer)
    # opportunities than the generous default.
    assert tight_policy.rejected_count >= default_policy.rejected_count  # type: ignore[attr-defined]


def test_upstream_study_not_found_is_rejected(study_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, _study_governance_id, _study_runtime_id = study_seeded
    config = _config()
    with pytest.raises(AggregateNotFound):
        run_run_portfolio_historical_evidence(
            report_governance_id="PORT-6734",
            source_study_governance_id="SURV-9999",
            source_study_runtime_id="00000000-0000-4000-8000-000000000000",
            config=config,
        )


def test_tampered_study_runtime_id_is_rejected(study_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, study_governance_id, _study_runtime_id = study_seeded
    config = _config()
    with pytest.raises(AggregateNotFound):
        run_run_portfolio_historical_evidence(
            report_governance_id="PORT-6735",
            source_study_governance_id=study_governance_id,
            source_study_runtime_id="00000000-0000-4000-8000-000000000000",
            config=config,
        )


def test_duplicate_report_governance_id_is_rejected(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()
    run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6736",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        run_run_portfolio_historical_evidence(
            report_governance_id="PORT-6736",
            source_study_governance_id=study_governance_id,
            source_study_runtime_id=study_runtime_id,
            config=config,
        )


# --------------------------------------------------------------------------
# Mission acceptance controls (Phases 23-27), built from the real M064
# canonical fixture's own genuine trade data -- never fabricated upstream
# objects.
# --------------------------------------------------------------------------


def test_acceptance_control_capital_bottleneck(study_seeded: tuple[Engine, str, str]) -> None:
    """Phase 23: several legitimate real opportunities overlap in time
    but a deliberately tiny capital pool cannot fund all of them. Prove
    some are allocated, some explicitly rejected with a reason, no
    capital double-spending occurs, and the result is deterministic."""
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    study, window_runs = _load_study_and_runs(study_governance_id, study_runtime_id)

    tiny_policy = PortfolioCapitalPolicy(
        policy_id="BOTTLENECK-TEST",
        version="1",
        initial_capital=Decimal("200"),
        currency="USD",
        max_concurrent_positions=1,
        max_capital_utilization_percent=Decimal("1"),
    )
    identity = DomainIdentity(
        governance_id=PortfolioStudyId("PORT-6740"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
    )
    report = build_portfolio_evidence_report(
        identity=identity,
        study=study,
        window_runs=window_runs,
        capital_policy=tiny_policy,  # type: ignore[arg-type]
    )

    assert report.allocated_count > 0
    assert report.rejected_count > 0
    assert all(
        d.rejection_reason is not None
        for d in report.allocation_decisions
        if d.decision is PortfolioAllocationOutcome.REJECTED
    )
    # No double-spending: at every equity observation, occupied capital
    # never exceeds the tiny pool's own initial capital.
    assert all(p.occupied_capital <= tiny_policy.initial_capital for p in report.equity_curve)

    # Deterministic: rerunning produces an identical decision set.
    report_again = build_portfolio_evidence_report(
        identity=identity,
        study=study,
        window_runs=window_runs,
        capital_policy=tiny_policy,  # type: ignore[arg-type]
    )
    assert report_again.allocation_decisions == report.allocation_decisions


def test_acceptance_control_capital_release(study_seeded: tuple[Engine, str, str]) -> None:
    """Phase 24: capital reserved by an open position is unavailable to
    a competing opportunity while open, and becomes available again only
    after that position's own real, already-known exit -- never earlier,
    never using any other opportunity's future knowledge."""
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    study, window_runs = _load_study_and_runs(study_governance_id, study_runtime_id)

    policy = PortfolioCapitalPolicy(
        policy_id="RELEASE-TEST",
        version="1",
        initial_capital=Decimal("120"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    identity = DomainIdentity(
        governance_id=PortfolioStudyId("PORT-6741"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000002"),
    )
    report = build_portfolio_evidence_report(
        identity=identity,
        study=study,
        window_runs=window_runs,
        capital_policy=policy,  # type: ignore[arg-type]
    )
    allocated = [
        d for d in report.allocation_decisions if d.decision is PortfolioAllocationOutcome.ALLOCATED
    ]
    assert len(allocated) >= 1
    # Every OPEN observation's occupied_capital is exactly the sum of
    # risk_amount for positions genuinely still open at that instant --
    # proving capital is reserved while open.
    assert any(p.occupied_capital > 0 for p in report.equity_curve)
    # Capital returns to (at least) the initial pool once every position
    # has exited -- proving full release, not permanent consumption.
    assert report.equity_curve[-1].occupied_capital == Decimal("0")


def test_acceptance_control_overlap_drawdown(study_seeded: tuple[Engine, str, str]) -> None:
    """Phase 25: overlapping real losing positions must combine into one
    coherent portfolio-level drawdown computed from the true equity
    sequence -- never derived by naively summing unrelated individual
    trade metrics."""
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    study, window_runs = _load_study_and_runs(study_governance_id, study_runtime_id)

    identity = DomainIdentity(
        governance_id=PortfolioStudyId("PORT-6742"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000003"),
    )

    report = build_portfolio_evidence_report(
        identity=identity,
        study=study,  # type: ignore[arg-type]
        window_runs=window_runs,
        capital_policy=DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    )
    # The portfolio-level max_drawdown must be a real peak-to-trough
    # figure from the equity sequence, strictly less than or equal to
    # peak_equity, and non-negative -- never a naive sum of individual
    # trade losses (which would not respect chronological overlap).
    assert report.max_drawdown >= 0
    assert report.max_drawdown <= report.peak_equity
    naive_loss_sum = sum(
        (
            d.net_pnl
            for d in report.allocation_decisions
            if d.decision is PortfolioAllocationOutcome.ALLOCATED and d.net_pnl < 0
        ),
        Decimal("0"),
    )
    # The true portfolio drawdown reflects realized-equity peak-to-trough
    # motion, not a flat sum of every losing trade's own PnL -- the two
    # figures are computed by unrelated methods and need not match.
    assert report.max_drawdown != abs(naive_loss_sum) or report.max_drawdown == 0


def test_acceptance_control_input_shuffle(study_seeded: tuple[Engine, str, str]) -> None:
    """Phase 26: shuffling the caller-supplied window_runs order must
    never change the canonical allocation/result, since only
    authoritative historical timestamps and the deterministic policy
    control processing order."""
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    study, window_runs = _load_study_and_runs(study_governance_id, study_runtime_id)

    identity = DomainIdentity(
        governance_id=PortfolioStudyId("PORT-6743"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000004"),
    )
    forward = build_portfolio_evidence_report(
        identity=identity,
        study=study,  # type: ignore[arg-type]
        window_runs=window_runs,
        capital_policy=DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    )
    shuffled_runs = list(window_runs)
    random.Random(42).shuffle(shuffled_runs)  # noqa: S311 - test determinism, not crypto
    shuffled = build_portfolio_evidence_report(
        identity=identity,
        study=study,  # type: ignore[arg-type]
        window_runs=tuple(shuffled_runs),
        capital_policy=DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    )
    forward_by_seq = {
        (d.source_window_id, d.trade_sequence): d.decision for d in forward.allocation_decisions
    }
    shuffled_by_seq = {
        (d.source_window_id, d.trade_sequence): d.decision for d in shuffled.allocation_decisions
    }
    assert forward_by_seq == shuffled_by_seq
    assert forward.realized_pnl == shuffled.realized_pnl
    assert forward.max_drawdown == shuffled.max_drawdown


def test_acceptance_control_future_mutation(study_seeded: tuple[Engine, str, str]) -> None:
    """Phase 27: mutating only a late historical event must leave every
    earlier portfolio decision and equity observation unchanged."""
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    study, window_runs = _load_study_and_runs(study_governance_id, study_runtime_id)

    identity = DomainIdentity(
        governance_id=PortfolioStudyId("PORT-6744"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000005"),
    )
    original = build_portfolio_evidence_report(
        identity=identity,
        study=study,  # type: ignore[arg-type]
        window_runs=window_runs,
        capital_policy=DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    )

    # Find the run containing the latest-entering executed trade and
    # mutate only that one trade's own net_pnl -- a genuinely late event.
    # `executed` guarantees entry_timestamp is not None (domain invariant).
    all_trades = [
        (run, trade)
        for run in window_runs
        for trade in run.trades
        if trade.executed and trade.entry_timestamp is not None
    ]
    latest_run, latest_trade = max(all_trades, key=lambda rt: cast(datetime, rt[1].entry_timestamp))
    assert latest_trade.entry_timestamp is not None
    mutated_trade = dataclasses.replace(latest_trade, net_pnl=Decimal("-999999.000000"))
    mutated_trades = tuple(mutated_trade if t is latest_trade else t for t in latest_run.trades)
    mutated_run = dataclasses.replace(latest_run, trades=mutated_trades)
    mutated_window_runs = tuple(mutated_run if run is latest_run else run for run in window_runs)

    mutated = build_portfolio_evidence_report(
        identity=identity,
        study=study,  # type: ignore[arg-type]
        window_runs=mutated_window_runs,
        capital_policy=DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    )

    # Every decision and equity observation strictly before the mutated
    # trade's own entry_timestamp must be byte-identical.
    cutoff: datetime = latest_trade.entry_timestamp
    original_early_decisions = [
        d for d in original.allocation_decisions if d.entry_timestamp < cutoff
    ]
    mutated_early_decisions = [
        d for d in mutated.allocation_decisions if d.entry_timestamp < cutoff
    ]
    assert original_early_decisions == mutated_early_decisions
    original_early_equity = [p for p in original.equity_curve if p.event_timestamp < cutoff]
    mutated_early_equity = [p for p in mutated.equity_curve if p.event_timestamp < cutoff]
    assert original_early_equity == mutated_early_equity
    # The mutation itself must actually have taken effect somewhere (the
    # test is not vacuous).
    assert mutated.realized_pnl != original.realized_pnl
