"""MILESTONE-066 independent statistical evidence verification.

This module does NOT import `build_statistical_evidence_report`,
`_percentile_bootstrap_interval`, `_mean`, `_median`, `_classify`, or any
other production statistical helper from
`empirical_platform.decision_candidate.statistical_evidence`. It reads raw
trade rows directly from PostgreSQL via `sqlalchemy`/raw SQL, independently
recomputes sample counts, mean/median R-multiple, one bootstrap percentile
confidence interval (own `random.Random` loop, own percentile-index
arithmetic), and one excluding-best-trade sensitivity view, then compares
the results against a real report produced by the real production usecase
against a fixture study built within this test module itself (mirroring
the self-contained `study_seeded` fixture pattern used by
`test_m066_statistical_evidence_lifecycle.py`, rather than depending on
out-of-band manually-seeded data that a sibling test's schema-drop
teardown could invalidate).

Requires the same `m063-dev-pg` PostgreSQL container (port 55466) used for
this milestone's other real acceptance evidence. Skipped automatically if
PostgreSQL integration tests are not opted into.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from random import Random
from typing import cast

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.entrypoints.run_statistical_evidence_analysis import (
    run_run_statistical_evidence_analysis,
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
_REPORT_GOVERNANCE_ID = "STATEV-6699"
_STUDY_GOVERNANCE_ID = "SURV-6698"
_QUANT4 = Decimal("0.0001")


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
        application_name="empirical-platform-m066-independent-verification-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANT4, rounding=ROUND_HALF_UP)


def _independent_bootstrap_mean_interval(
    values: list[Decimal], *, resample_count: int, seed: int, confidence_level: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """Independently-authored percentile bootstrap for the mean --
    separate loop, separate percentile-index arithmetic, from scratch."""
    rng = Random(seed)  # noqa: S311 - statistical resampling, not cryptographic
    n = len(values)
    point = _quantize(sum(values, Decimal("0")) / n)
    means: list[Decimal] = []
    for _ in range(resample_count):
        total = Decimal("0")
        for _i in range(n):
            total += values[rng.randrange(n)]
        means.append(_quantize(total / n))
    means.sort()
    tail = (Decimal("1") - confidence_level) / 2
    lower_index = int((tail * (resample_count - 1)).to_integral_value(rounding=ROUND_HALF_UP))
    upper_index = resample_count - 1 - lower_index
    return means[lower_index], point, means[upper_index]


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
        stress_study_governance_id="ROBUST-6698",
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        expected_dataset_sha256=_EXPECTED_DATASET_SHA256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(_MEMBERSHIP_MANIFEST_PATH),
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=6698,
        stress_backtest_run_governance_id_base=7698,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    run_run_statistical_evidence_analysis(
        report_governance_id=_REPORT_GOVERNANCE_ID,
        source_study_governance_id=_STUDY_GOVERNANCE_ID,
        source_study_runtime_id=str(study.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    return upgraded_schema


def test_independent_recomputation_matches_persisted_report(report_seeded: Engine) -> None:
    engine = report_seeded
    with engine.connect() as conn:
        report_row = (
            conn.execute(
                text(
                    "SELECT runtime_id, trade_sample_size, window_sample_size, "
                    "mean_r_per_trade, median_r_per_trade, net_pnl "
                    "FROM statistical_evidence_report WHERE governance_id = :gid"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .one()
        )
        policy_row = (
            conn.execute(
                text(
                    "SELECT bootstrap_resample_count, bootstrap_seed, bootstrap_confidence_level "
                    "FROM statistical_evidence_report WHERE governance_id = :gid"
                ),
                {"gid": _REPORT_GOVERNANCE_ID},
            )
            .mappings()
            .one()
        )
        persisted_interval = (
            conn.execute(
                text(
                    "SELECT lower_bound, point_estimate, upper_bound "
                    "FROM statistical_evidence_bootstrap_interval "
                    "WHERE report_runtime_id = :rid AND metric_name = 'mean_r_per_trade'"
                ),
                {"rid": str(report_row["runtime_id"])},
            )
            .mappings()
            .one()
        )
        persisted_sensitivity = (
            conn.execute(
                text(
                    "SELECT net_pnl, sample_size FROM statistical_evidence_sensitivity "
                    "WHERE report_runtime_id = :rid AND label = 'EXCLUDING_BEST_TRADE'"
                ),
                {"rid": str(report_row["runtime_id"])},
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

        trades: list[dict[str, object]] = []
        for run_id in run_ids:
            rows = (
                conn.execute(
                    text(
                        "SELECT r_multiple, net_pnl FROM historical_backtest_trade "
                        "WHERE backtest_run_runtime_id = :rid AND outcome != 'NO_ENTRY'"
                    ),
                    {"rid": run_id},
                )
                .mappings()
                .all()
            )
            trades.extend(dict(row) for row in rows)

    # --- 1. Independent sample-size recomputation ---
    assert len(trades) == int(report_row["trade_sample_size"])
    assert len(run_ids) == int(report_row["window_sample_size"])

    r_values = [cast(Decimal, t["r_multiple"]) for t in trades if t["r_multiple"] is not None]

    # --- 2. Independent mean/median recomputation ---
    independent_mean = _quantize(sum(r_values, Decimal("0")) / len(r_values))
    sorted_r = sorted(r_values)
    mid = len(sorted_r) // 2
    if len(sorted_r) % 2 == 0:
        independent_median = _quantize((sorted_r[mid - 1] + sorted_r[mid]) / 2)
    else:
        independent_median = _quantize(sorted_r[mid])
    assert independent_mean == cast(Decimal, report_row["mean_r_per_trade"])
    assert independent_median == cast(Decimal, report_row["median_r_per_trade"])

    # --- 3. Independent net_pnl recomputation ---
    independent_net_pnl = _quantize(
        sum((cast(Decimal, t["net_pnl"]) for t in trades), Decimal("0"))
    )
    assert independent_net_pnl == cast(Decimal, report_row["net_pnl"])

    # --- 4. Independent excluding-best-trade sensitivity recomputation ---
    best_trade = max(trades, key=lambda t: cast(Decimal, t["net_pnl"]))
    remaining = [t for t in trades if t is not best_trade]
    independent_excluding_best_net_pnl = _quantize(
        sum((cast(Decimal, t["net_pnl"]) for t in remaining), Decimal("0"))
    )
    assert len(remaining) == int(persisted_sensitivity["sample_size"])
    assert independent_excluding_best_net_pnl == cast(Decimal, persisted_sensitivity["net_pnl"])

    # --- 5. Independent bootstrap interval recomputation (same seed) ---
    independent_lower, independent_point, independent_upper = _independent_bootstrap_mean_interval(
        r_values,
        resample_count=int(policy_row["bootstrap_resample_count"]),
        seed=int(policy_row["bootstrap_seed"]),
        confidence_level=Decimal(policy_row["bootstrap_confidence_level"]),
    )
    assert independent_point == Decimal(persisted_interval["point_estimate"])
    assert independent_lower == Decimal(persisted_interval["lower_bound"])
    assert independent_upper == Decimal(persisted_interval["upper_bound"])
