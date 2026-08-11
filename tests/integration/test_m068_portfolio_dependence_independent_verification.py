"""MILESTONE-068 independent cross-instrument dependence verification.

This module does NOT import `build_portfolio_dependence_report`,
`build_pairwise_dependence`, `_pearson_correlation`, `_derive_return_series`,
`_dependence_weighted_concentration`, or any other production calculation
helper from `empirical_platform.decision_candidate.portfolio_dependence`.
It reads raw price bars directly from the fixture's own JSON dataset
bundle file (not via `parse_robustness_dataset_bundle_file`) and raw
allocation-decision rows directly from PostgreSQL via `sqlalchemy`/raw
SQL, independently derives simple returns, aligns timestamps, and
computes Pearson correlation with a differently-structured (raw sum-of-
products) formula -- own loop, own algebra, separately authored -- then
compares every figure against the real, already-persisted report
produced by the real production usecase against a fixture chain built
within this test module itself.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.entrypoints.run_portfolio_dependence_evidence import (
    run_run_portfolio_dependence_evidence,
)
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
_STUDY_GOVERNANCE_ID = "SURV-6898"
_PORTFOLIO_GOVERNANCE_ID = "PORT-6898"
_REPORT_GOVERNANCE_ID = "DEPEND-6898"
_LOOKBACK_BAR_COUNT = 20
_MINIMUM_OVERLAP = 10
_QUANT = Decimal("0.0001")


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
        application_name="empirical-platform-m068-independent-verification-test",
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
    with upgraded_schema.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE portfolio_dependence_concurrent_state, "
                "portfolio_dependence_pair, portfolio_dependence_report, "
                "portfolio_capital_sensitivity, portfolio_equity_observation, "
                "portfolio_allocation_decision, portfolio_study, survivorship_window, "
                "survivorship_study, membership_record, universe_authority, "
                "instrument_master, robustness_window, robustness_study, "
                "historical_backtest_trade, historical_backtest_run CASCADE"
            )
        )
    config = _config()
    study = run_run_survivorship_aware_robustness_study(
        study_governance_id=_STUDY_GOVERNANCE_ID,
        stress_study_governance_id="ROBUST-6898",
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        expected_dataset_sha256=_EXPECTED_DATASET_SHA256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(_MEMBERSHIP_MANIFEST_PATH),
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=6898,
        stress_backtest_run_governance_id_base=7898,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    portfolio = run_run_portfolio_historical_evidence(
        report_governance_id=_PORTFOLIO_GOVERNANCE_ID,
        source_study_governance_id=_STUDY_GOVERNANCE_ID,
        source_study_runtime_id=str(study.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    run_run_portfolio_dependence_evidence(
        report_governance_id=_REPORT_GOVERNANCE_ID,
        source_portfolio_study_governance_id=_PORTFOLIO_GOVERNANCE_ID,
        source_portfolio_study_runtime_id=str(portfolio.identity.runtime_id),  # type: ignore[attr-defined]
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        lookback_bar_count=_LOOKBACK_BAR_COUNT,
        minimum_overlapping_observations=_MINIMUM_OVERLAP,
        config=config,
    )
    return upgraded_schema


def _load_raw_bars_by_instrument() -> dict[str, list[tuple[datetime, Decimal]]]:
    """Read closes directly from the fixture's own JSON file -- no
    production parsing/hashing helper involved."""
    raw = json.loads(_DATASET_BUNDLE_PATH.read_text())
    result: dict[str, list[tuple[datetime, Decimal]]] = {}
    for entry in raw["instruments"]:
        bars = sorted(entry["bars"], key=lambda b: b["timestamp"])
        symbol = bars[0]["instrument"]
        result[symbol] = [
            (datetime.fromisoformat(b["timestamp"]), Decimal(b["close"])) for b in bars
        ]
    return result


def _independent_returns(
    bars: list[tuple[datetime, Decimal]], *, as_of: datetime, lookback_bar_count: int
) -> dict[datetime, Decimal]:
    """Own return-derivation loop: bars strictly at/before `as_of`, the
    trailing `lookback_bar_count + 1` of them, one simple return per
    consecutive close pair."""
    eligible = [ts_close for ts_close in bars if ts_close[0] <= as_of]
    windowed = eligible[-(lookback_bar_count + 1) :] if eligible else []
    returns: dict[datetime, Decimal] = {}
    for i in range(1, len(windowed)):
        prev_ts, prev_close = windowed[i - 1]
        ts, close = windowed[i]
        if prev_close != 0:
            returns[ts] = (close - prev_close) / prev_close
    return returns


def _independent_pearson(
    returns_a: dict[datetime, Decimal], returns_b: dict[datetime, Decimal], *, minimum_overlap: int
) -> tuple[Decimal | None, int]:
    """Raw sum-of-products correlation formula -- algebraically
    equivalent to, but structurally different from (no two-pass
    mean/variance loop), the production implementation:
    r = (n*sum_xy - sum_x*sum_y) / sqrt((n*sum_x2 - sum_x^2) * (n*sum_y2 - sum_y^2))
    """
    shared = sorted(set(returns_a) & set(returns_b))
    n = len(shared)
    if n < minimum_overlap:
        return None, n
    sum_x = sum_y = sum_xy = sum_x2 = sum_y2 = Decimal("0")
    for ts in shared:
        x = returns_a[ts]
        y = returns_b[ts]
        sum_x += x
        sum_y += y
        sum_xy += x * y
        sum_x2 += x * x
        sum_y2 += y * y
    denom_x = Decimal(n) * sum_x2 - sum_x * sum_x
    denom_y = Decimal(n) * sum_y2 - sum_y * sum_y
    if denom_x <= 0 or denom_y <= 0:
        return None, n
    numerator = Decimal(n) * sum_xy - sum_x * sum_y
    correlation = numerator / (denom_x.sqrt() * denom_y.sqrt())
    correlation = max(Decimal("-1"), min(Decimal("1"), correlation))
    return correlation.quantize(_QUANT), n


def test_independent_pairwise_correlation_matches_persisted_report(
    report_seeded: Engine,
) -> None:
    engine = report_seeded
    with engine.connect() as conn:
        report_row = (
            conn.execute(
                text(
                    "SELECT runtime_id FROM portfolio_dependence_report WHERE governance_id = :gid"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .one()
        )
        report_runtime_id = str(report_row["runtime_id"])

        allocated_rows = (
            conn.execute(
                text(
                    "SELECT instrument_symbol, entry_timestamp, exit_timestamp "
                    "FROM portfolio_allocation_decision "
                    "WHERE report_runtime_id = (SELECT runtime_id FROM portfolio_study "
                    "WHERE governance_id = :pid) AND decision = 'ALLOCATED'"
                ),
                {"pid": _PORTFOLIO_GOVERNANCE_ID},
            )
            .mappings()
            .all()
        )
        pair_rows = (
            conn.execute(
                text(
                    "SELECT instrument_a, instrument_b, observation_count, correlation, status "
                    "FROM portfolio_dependence_pair WHERE report_runtime_id = :rid"
                ),
                {"rid": report_runtime_id},
            )
            .mappings()
            .all()
        )

    assert len(allocated_rows) > 0
    all_instruments_ever_open = sorted({r["instrument_symbol"] for r in allocated_rows})
    open_instants = sorted({r["entry_timestamp"] for r in allocated_rows})
    final_cutoff = open_instants[-1]

    bars_by_instrument = _load_raw_bars_by_instrument()
    returns_by_symbol = {
        symbol: _independent_returns(
            bars_by_instrument[symbol],
            as_of=final_cutoff,
            lookback_bar_count=_LOOKBACK_BAR_COUNT,
        )
        for symbol in all_instruments_ever_open
        if symbol in bars_by_instrument
    }

    persisted_by_key = {(r["instrument_a"], r["instrument_b"]): r for r in pair_rows}

    checked_defined = 0
    for i, symbol_a in enumerate(all_instruments_ever_open):
        for symbol_b in all_instruments_ever_open[i:]:
            if symbol_a not in returns_by_symbol or symbol_b not in returns_by_symbol:
                continue
            independent_corr, independent_n = _independent_pearson(
                returns_by_symbol[symbol_a],
                returns_by_symbol[symbol_b],
                minimum_overlap=_MINIMUM_OVERLAP,
            )
            persisted = persisted_by_key[(symbol_a, symbol_b)]
            assert independent_n == int(persisted["observation_count"])
            if independent_corr is None:
                assert persisted["correlation"] is None
            else:
                assert persisted["status"] == "DEFINED"
                assert independent_corr == Decimal(persisted["correlation"])
                checked_defined += 1
    # The independent check must have actually exercised at least one
    # genuinely defined pair -- otherwise this test would pass vacuously.
    assert checked_defined > 0


def test_independent_highest_and_lowest_pair_match_persisted_report(
    report_seeded: Engine,
) -> None:
    engine = report_seeded
    with engine.connect() as conn:
        report_row = (
            conn.execute(
                text(
                    "SELECT highest_pair_a, highest_pair_b, highest_pair_correlation, "
                    "lowest_pair_a, lowest_pair_b, lowest_pair_correlation "
                    "FROM portfolio_dependence_report WHERE governance_id = :gid"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .one()
        )
        pair_rows = (
            conn.execute(
                text(
                    "SELECT instrument_a, instrument_b, correlation FROM portfolio_dependence_pair "
                    "WHERE report_runtime_id = "
                    "(SELECT runtime_id FROM portfolio_dependence_report "
                    "WHERE governance_id = :gid) "
                    "AND status = 'DEFINED' AND instrument_a != instrument_b"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .all()
        )

    assert len(pair_rows) > 0
    highest = max(pair_rows, key=lambda r: Decimal(r["correlation"]))
    lowest = min(pair_rows, key=lambda r: Decimal(r["correlation"]))

    assert (highest["instrument_a"], highest["instrument_b"]) == (
        report_row["highest_pair_a"],
        report_row["highest_pair_b"],
    )
    assert Decimal(highest["correlation"]) == Decimal(report_row["highest_pair_correlation"])
    assert (lowest["instrument_a"], lowest["instrument_b"]) == (
        report_row["lowest_pair_a"],
        report_row["lowest_pair_b"],
    )
    assert Decimal(lowest["correlation"]) == Decimal(report_row["lowest_pair_correlation"])


def test_independent_concurrent_state_concentration_matches_persisted_report(
    report_seeded: Engine,
) -> None:
    """Mission Phase 25: independently recompute one concurrent-position
    dependence-aware concentration figure (`w' C w`, own loop) using
    correlations independently derived at that specific state's own
    estimation cutoff, and compare against the persisted value."""
    engine = report_seeded
    with engine.connect() as conn:
        state_rows = (
            conn.execute(
                text(
                    "SELECT state_sequence, as_of_timestamp, open_instruments, weights, "
                    "dependence_aware_concentration "
                    "FROM portfolio_dependence_concurrent_state "
                    "WHERE report_runtime_id = "
                    "(SELECT runtime_id FROM portfolio_dependence_report "
                    "WHERE governance_id = :gid) "
                    "ORDER BY state_sequence"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .all()
        )

    multi_states = [r for r in state_rows if len(r["open_instruments"]) >= 2]
    assert len(multi_states) > 0
    state = max(multi_states, key=lambda r: len(r["open_instruments"]))

    bars_by_instrument = _load_raw_bars_by_instrument()
    as_of = state["as_of_timestamp"]
    open_instruments = list(state["open_instruments"])
    weights = [Decimal(w) for w in state["weights"]]

    returns_by_symbol = {
        symbol: _independent_returns(
            bars_by_instrument[symbol], as_of=as_of, lookback_bar_count=_LOOKBACK_BAR_COUNT
        )
        for symbol in set(open_instruments)
        if symbol in bars_by_instrument
    }

    total = Decimal("0")
    for i, symbol_a in enumerate(open_instruments):
        for j, symbol_b in enumerate(open_instruments):
            if i == j:
                correlation = Decimal("1")
            else:
                corr, _n = _independent_pearson(
                    returns_by_symbol[symbol_a],
                    returns_by_symbol[symbol_b],
                    minimum_overlap=_MINIMUM_OVERLAP,
                )
                # Mirrors the production report's own documented
                # conservative treatment of an undefined pair within this
                # weighting only (never silently assumed independent).
                correlation = corr if corr is not None else Decimal("1")
            total += weights[i] * weights[j] * correlation
    total = max(Decimal("0"), min(Decimal("1"), total)).quantize(_QUANT)

    assert total == Decimal(state["dependence_aware_concentration"])
