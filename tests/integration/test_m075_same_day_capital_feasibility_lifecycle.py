"""MILESTONE-075 -- same-day capital feasibility against real PostgreSQL.

Reuses M072's own real-session seeding so the assessment is exercised over
genuinely persisted rows, then cross-checks every notional it used against
raw SQL read independently of the repository helpers.

Superseded header from MILESTONE-072 real-PostgreSQL daily research brief acceptance tests.

Covers a genuine day-over-day product demo (two real sessions against
real PostgreSQL, the later session's brief making the change visible in
human-readable text -- not raw JSON), raw-SQL cross-verification of risk
evidence, no-prior-session/day-1 semantics, a FAILED-session warning,
and the real installed `empirical-platform-daily-brief` CLI subprocess
(default-latest-session selection, explicit selection, `--json`).
Mirrors the established M070/M071 offline-acceptance pattern
(`FakeMarketDataSource` + real PostgreSQL, zero network dependency).
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioRejectionReason,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    SameDayCapitalAssessment,
    SameDayCapitalOutcome,
    SameDayPositionRequest,
    assess_same_day_capital_feasibility,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
)
from empirical_platform.usecases.daily_research_brief_io import (
    render_daily_research_brief_json,
    render_daily_research_brief_text,
)
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_ALL_TABLES = [
    "research_session_decision",
    "research_session_stage",
    "research_session",
    "historical_backtest_trade",
    "historical_backtest_run",
    "position_plan",
    "trade_plan",
    "trading_opportunity_scan_evaluation",
    "trading_opportunity_scan",
    "decision_candidate",
    "dataset_snapshot_source_file",
    "dataset_snapshot",
    "instrument_master",
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


def _postgres_enabled() -> bool:
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
        application_name="empirical-platform-m072-test",
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
    if not _postgres_enabled():
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


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _breakout_csv(base_price: Decimal, breakout_pct: Decimal, breakout_vol: int) -> bytes:
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(10):
        ts = (_T0 + timedelta(days=i)).isoformat()
        lines.append(
            f"{ts},{base_price:.4f},{base_price * Decimal('1.001'):.4f},"
            f"{base_price * Decimal('0.999'):.4f},{base_price:.4f},50000"
        )
    breakout_close = base_price * (Decimal("1") + breakout_pct)
    for j in range(6):
        ts = (_T0 + timedelta(days=10 + j)).isoformat()
        c = breakout_close * (Decimal("1") + Decimal("0.001") * j)
        high = c * Decimal("1.002")
        low = c * Decimal("0.998")
        lines.append(f"{ts},{c:.4f},{high:.4f},{low:.4f},{c:.4f},{breakout_vol}")
    return ("\n".join(lines) + "\n").encode()


# The frozen M059 risk gate requires reward:risk >= 2.0, with
# target = reference_high * 1.02 (a fixed 2% projection, deliberately
# NOT a multiple of risk_per_unit -- see trade_plan.py's own
# compute_target_price docstring) and stop = reference_high. Working
# the inequality backwards: entry must land within roughly +0.67% of
# reference_high for the resulting geometry to clear the 2:1 minimum.
# A breakout_pct much larger than that (an earlier draft used 10%)
# pushes the target below the entry price entirely -- a genuine
# INVALID_TARGET_GEOMETRY rejection, confirmed by direct smoke-testing
# against a real container, not assumed. 0.4%/0.5% keep both
# instruments' entries close enough to the reference high to clear the
# gate on real math, not a hand-tuned pass.
_FIXTURES = {
    "AAPL": _breakout_csv(Decimal("100"), Decimal("0.004"), 500000),
    "MSFT": _breakout_csv(Decimal("400"), Decimal("0.005"), 400000),
}
# Same genuine flat->breakout fixture design as M071's own integration
# tests: days 0-9 are flat (NO_TRADE), day 10 is the first genuine
# breakout bar whose own reference window (days 6-9) is still entirely
# flat -- a real, unforced day-over-day state transition, not a
# fabricated difference between hand-authored fixtures.
_AS_OF_FLAT = _T0 + timedelta(days=5)
_AS_OF_BREAKOUT = _T0 + timedelta(days=10)


def _run_session(
    *,
    session_governance_id: str,
    artifact_path: Path,
    config: PostgreSQLConfigSnapshot,
    universe: tuple[str, ...] = ("AAPL", "MSFT"),
    fixtures: dict[str, bytes] | None = None,
    as_of: datetime = _AS_OF_BREAKOUT,
    lookback_days: int = 20,
    reference_window_size: int = 4,
) -> object:
    clock = _FixedClock(as_of)
    source = FakeMarketDataSource(fixtures if fixtures is not None else _FIXTURES, clock=clock)
    generator = UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = RunDailyResearchSessionHandler(
            campaign_repository=runtime.campaigns,
            run_repository=runtime.runs,
            evidence_package_repository=runtime.evidence_packages,
            dataset_snapshot_repository=runtime.dataset_snapshots,
            instrument_master_repository=runtime.instrument_masters,
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            historical_backtest_repository=runtime.historical_backtests,
            research_session_repository=runtime.research_sessions,
            clock=clock,
            runtime_identifier_generator=generator,
        )
        return handler.handle(
            build_run_daily_research_session_command(
                session_governance_id=session_governance_id,
                as_of=as_of,
                universe=universe,
                lookback_days=lookback_days,
                artifact_path=str(artifact_path),
                account_equity=Decimal("100000"),
                risk_percent=Decimal("0.01"),
                source=source,
                runtime_identifier_generator=generator,
                reference_window_size=reference_window_size,
            )
        )


def _build_brief(config: PostgreSQLConfigSnapshot, identity: object) -> object:
    with postgres_repository_runtime(config) as runtime:
        handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
        )
        return handler.handle(BuildDailyResearchBriefQuery(identity=identity))  # type: ignore[arg-type]


def _assessment_of(brief: object) -> SameDayCapitalAssessment:
    assessment = brief.same_day_capital_assessment  # type: ignore[attr-defined]
    assert assessment is not None
    return assessment


def test_m075_assessment_is_computed_over_really_persisted_position_plans(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """End-to-end: a real session through the real handler, and every notional
    the assessment used is cross-checked against raw SQL."""
    config = _config()
    result = _run_session(
        session_governance_id="RESEARCH-7501",
        artifact_path=tmp_path / "m075.json",
        config=config,
    )
    brief = _build_brief(config, result.identity)  # type: ignore[attr-defined]
    assessment = _assessment_of(brief)

    assert assessment.outcome in (
        SameDayCapitalOutcome.FITS_WITHIN_CAPITAL,
        SameDayCapitalOutcome.EXCEEDS_CAPITAL,
        SameDayCapitalOutcome.NO_APPROVED_POSITION_PLANS,
    )
    assert assessment.unassessable_reason is None

    with clean_tables.begin() as conn:
        rows = list(
            conn.execute(
                text(
                    "SELECT governance_id, supplied_account_equity, quantity, "
                    "position_notional FROM position_plan "
                    "WHERE status = 'APPROVED_POSITION_PLAN' ORDER BY governance_id"
                )
            ).mappings()
        )

    assert len(rows) == assessment.requested_plan_count + assessment.excluded_plan_count
    by_id = {str(r["governance_id"]): r for r in rows}
    for verdict in assessment.verdicts:
        row = by_id[verdict.position_plan_governance_id]
        assert Decimal(verdict.position_notional) == Decimal(str(row["position_notional"]))
        assert verdict.quantity == int(row["quantity"])
    if rows:
        assert Decimal(assessment.capital_base) == min(
            Decimal(str(r["supplied_account_equity"])) for r in rows
        )


def test_m075_exceeds_capital_is_reachable_from_real_persisted_rows(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Drive the EXCEEDS branch from genuinely persisted position plans by
    tightening only the capital policy -- the rows are real, unmodified."""
    config = _config()
    result = _run_session(
        session_governance_id="RESEARCH-7502",
        artifact_path=tmp_path / "m075b.json",
        config=config,
    )
    brief = _build_brief(config, result.identity)  # type: ignore[attr-defined]
    baseline = _assessment_of(brief)
    if baseline.requested_plan_count == 0:
        pytest.skip("this fixture produced no approved position plans")

    with clean_tables.begin() as conn:
        rows = list(
            conn.execute(
                text(
                    "SELECT governance_id, instrument_symbol, supplied_account_equity, "
                    "quantity, position_notional, actual_risk FROM position_plan "
                    "WHERE status = 'APPROVED_POSITION_PLAN' ORDER BY governance_id"
                )
            ).mappings()
        )
    requests = tuple(
        SameDayPositionRequest(
            rank=index,
            instrument_symbol=str(row["instrument_symbol"]),
            position_plan_governance_id=str(row["governance_id"]),
            quantity=int(row["quantity"]),
            position_notional=Decimal(str(row["position_notional"])),
            actual_risk=Decimal(str(row["actual_risk"])),
            supplied_account_equity=Decimal(str(row["supplied_account_equity"])),
        )
        for index, row in enumerate(rows, start=1)
    )
    total = sum((r.position_notional for r in requests), Decimal("0"))
    # A ceiling one cent below the real total must make the real set infeasible.
    tightened = dataclasses.replace(
        DEFAULT_PORTFOLIO_CAPITAL_POLICY,
        initial_capital=total - Decimal("0.01"),
        max_capital_utilization_percent=Decimal("1"),
    )
    tightened_requests = tuple(
        dataclasses.replace(r, supplied_account_equity=tightened.initial_capital) for r in requests
    )
    result_tight = assess_same_day_capital_feasibility(
        requests=tightened_requests, session_is_completed=True, template_policy=tightened
    )
    assert result_tight.outcome is SameDayCapitalOutcome.EXCEEDS_CAPITAL
    assert result_tight.admitted_plan_count < result_tight.requested_plan_count
    assert any(
        v.rejection_reason is PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED
        for v in result_tight.verdicts
        if not v.fits
    )


def test_m075_suppression_is_distinct_from_a_feasible_verdict(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _run_session(
        session_governance_id="RESEARCH-7503",
        artifact_path=tmp_path / "m075c.json",
        config=config,
    )
    with postgres_repository_runtime(config) as runtime:
        handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            include_capital_feasibility=False,
        )
        brief = handler.handle(BuildDailyResearchBriefQuery(identity=result.identity))  # type: ignore[attr-defined,arg-type]

    assert brief.same_day_capital_assessment is None
    payload = render_daily_research_brief_json(brief)
    section = payload["SAME_DAY_CAPITAL_FEASIBILITY"]
    assert isinstance(section, dict)
    assert section["computed"] is False
    assert section["outcome"] is None
    rendered = render_daily_research_brief_text(brief)
    assert "SAME-DAY CAPITAL FEASIBILITY" in rendered
    assert "not computed for this brief" in rendered


def test_m075_assessment_is_deterministic_across_two_independent_builds(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _run_session(
        session_governance_id="RESEARCH-7504",
        artifact_path=tmp_path / "m075d.json",
        config=config,
    )
    first = _assessment_of(_build_brief(config, result.identity))  # type: ignore[attr-defined]
    second = _assessment_of(_build_brief(config, result.identity))  # type: ignore[attr-defined]
    assert first == second
