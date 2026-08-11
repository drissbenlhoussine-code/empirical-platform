"""MILESTONE-067 independent portfolio capital-allocation verification.

This module does NOT import `build_portfolio_evidence_report`,
`_simulate_capital_allocation`, `_pool_opportunities`,
`_build_event_timeline`, `_max_drawdown_from_equity_curve`, or any other
production calculation helper from
`empirical_platform.decision_candidate.portfolio_study`. It reads raw
trade rows directly from PostgreSQL via `sqlalchemy`/raw SQL and
independently replays the same well-specified, deterministic
capital-allocation event ordering (own loop, own priority/tie-break
logic, separately authored) to recompute: total opportunity count,
allocated/rejected counts, ending capital, realized PnL, peak occupied
capital, maximum concurrent positions, and portfolio maximum drawdown --
then compares every figure against the real, already-persisted report
produced by the real production usecase against a fixture study built
within this test module itself (self-contained, mirroring the
established `study_seeded`/`report_seeded` pattern used across this
milestone's other PostgreSQL acceptance tests).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.entrypoints.run_portfolio_historical_evidence import (
    run_run_portfolio_historical_evidence,
)
from empirical_platform.entrypoints.run_survivorship_aware_robustness_study import (
    run_run_survivorship_aware_robustness_study,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "m064_survivorship_aware"
_DATASET_BUNDLE_PATH = _FIXTURE_DIR / "survivorship_aware_dataset_bundle.json"
_INSTRUMENT_MASTER_PATH = _FIXTURE_DIR / "instrument_master.json"
_MEMBERSHIP_MANIFEST_PATH = _FIXTURE_DIR / "membership_manifest.json"
_EXPECTED_DATASET_SHA256 = "af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff"
_EXPECTED_MANIFEST_HASH = "caa9fa899ea26816101a0a494c4977fed75849d4ac19b65ac6410e561f232fda"
_REPORT_GOVERNANCE_ID = "PORT-6799"
_STUDY_GOVERNANCE_ID = "SURV-6798"
_QUANT = Decimal("0.000001")


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
        application_name="empirical-platform-m067-independent-verification-test",
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
def report_seeded(upgraded_schema: Engine) -> Engine:
    config = _config()
    study = run_run_survivorship_aware_robustness_study(
        study_governance_id=_STUDY_GOVERNANCE_ID,
        stress_study_governance_id="ROBUST-6798",
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        expected_dataset_sha256=_EXPECTED_DATASET_SHA256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(_MEMBERSHIP_MANIFEST_PATH),
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=6798,
        stress_backtest_run_governance_id_base=7798,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    run_run_portfolio_historical_evidence(
        report_governance_id=_REPORT_GOVERNANCE_ID,
        source_study_governance_id=_STUDY_GOVERNANCE_ID,
        source_study_runtime_id=str(study.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    return upgraded_schema


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _independent_replay(
    opportunities: list[dict[str, object]], initial_capital: Decimal, max_concurrent: int
) -> tuple[int, int, Decimal, Decimal, Decimal, int, Decimal]:
    """Separately-authored event-driven replay: own priority scheme
    (closes before opens at the same instant, except a zero-duration
    opportunity's own self-close which follows its own open; opens
    ordered by ascending scan_rank), own loop, no shared code with the
    production `_simulate_capital_allocation`."""
    events: list[tuple[object, int, object, object, int, str]] = []
    for i, opp in enumerate(opportunities):
        entry = opp["entry_timestamp"]
        exit_ = opp["exit_timestamp"]
        close_priority = 2 if exit_ == entry else 0
        events.append((entry, 1, opp["scan_rank"], opp["instrument_symbol"], i, "OPEN"))
        events.append(
            (exit_, close_priority, opp["scan_rank"], opp["instrument_symbol"], i, "CLOSE")
        )
    events.sort(key=lambda e: (e[0], e[1], e[2], e[3], e[4]))

    available = initial_capital
    occupied = Decimal("0")
    open_count = 0
    realized_pnl = Decimal("0")
    allocated = 0
    rejected = 0
    open_risk: dict[int, Decimal] = {}
    peak_occupied = Decimal("0")
    max_concurrent_observed = 0
    equity = initial_capital
    peak_equity = initial_capital
    max_drawdown = Decimal("0")
    allocated_flags: dict[int, bool] = {}

    for _timestamp, _priority, _rank, _symbol, idx, kind in events:
        opp = opportunities[idx]
        risk = _quantize(cast(Decimal, opp["risk_amount"]))
        if kind == "OPEN":
            if available >= risk and open_count < max_concurrent:
                available -= risk
                occupied += risk
                open_count += 1
                open_risk[idx] = risk
                allocated_flags[idx] = True
                allocated += 1
                peak_occupied = max(peak_occupied, occupied)
                max_concurrent_observed = max(max_concurrent_observed, open_count)
            else:
                allocated_flags[idx] = False
                rejected += 1
        else:
            if not allocated_flags.get(idx, False):
                continue
            reserved = open_risk.pop(idx)
            pnl = _quantize(cast(Decimal, opp["net_pnl"]))
            available += reserved + pnl
            occupied -= reserved
            open_count -= 1
            realized_pnl += pnl
            equity = _quantize(initial_capital + realized_pnl)
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)

    ending_capital = _quantize(initial_capital + realized_pnl)
    return (
        allocated,
        rejected,
        ending_capital,
        _quantize(realized_pnl),
        peak_occupied,
        max_concurrent_observed,
        max_drawdown,
    )


def test_independent_recomputation_matches_persisted_report(report_seeded: Engine) -> None:
    engine = report_seeded
    with engine.connect() as conn:
        report_row = (
            conn.execute(
                text(
                    "SELECT runtime_id, total_opportunities, allocated_count, "
                    "rejected_count, ending_capital, realized_pnl, "
                    "peak_occupied_capital, max_concurrent_positions_observed, "
                    "max_drawdown, initial_capital, max_concurrent_positions "
                    "FROM portfolio_study WHERE governance_id = :gid"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .one()
        )

        window_rows = (
            conn.execute(
                text(
                    "SELECT backtest_run_runtime_id FROM survivorship_window "
                    "WHERE study_runtime_id = (SELECT runtime_id FROM survivorship_study "
                    "WHERE governance_id = :sid) AND backtest_run_runtime_id IS NOT NULL"
                ),
                {"sid": _STUDY_GOVERNANCE_ID},
            )
            .mappings()
            .all()
        )
        run_ids = [str(r["backtest_run_runtime_id"]) for r in window_rows]

        opportunities: list[dict[str, object]] = []
        for run_id in run_ids:
            rows = (
                conn.execute(
                    text(
                        "SELECT entry_timestamp, exit_timestamp, risk_amount, net_pnl, "
                        "scan_rank, instrument_symbol "
                        "FROM historical_backtest_trade "
                        "WHERE backtest_run_runtime_id = :rid AND outcome != 'NO_ENTRY'"
                    ),
                    {"rid": run_id},
                )
                .mappings()
                .all()
            )
            opportunities.extend(dict(row) for row in rows)

    assert len(opportunities) == int(report_row["total_opportunities"])

    allocated, rejected, ending_capital, realized_pnl, peak_occupied, max_concurrent, max_dd = (
        _independent_replay(
            opportunities,
            initial_capital=Decimal(report_row["initial_capital"]),
            max_concurrent=int(report_row["max_concurrent_positions"]),
        )
    )

    assert allocated == int(report_row["allocated_count"])
    assert rejected == int(report_row["rejected_count"])
    assert ending_capital == Decimal(report_row["ending_capital"])
    assert realized_pnl == Decimal(report_row["realized_pnl"])
    assert peak_occupied == Decimal(report_row["peak_occupied_capital"])
    assert max_concurrent == int(report_row["max_concurrent_positions_observed"])
    assert max_dd == Decimal(report_row["max_drawdown"])
