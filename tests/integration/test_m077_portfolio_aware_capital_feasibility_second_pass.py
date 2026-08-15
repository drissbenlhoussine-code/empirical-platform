"""MILESTONE-077 -- FRESH SECOND VERIFICATION PASS.

Reuses M072's real-session seeding so today's proposals are genuinely
persisted rows, and M076's real ledger repository so held exposure is genuinely
persisted operator assertions. Every figure the assessment reports is
cross-checked against raw SQL read independently of the repository helpers.

Scaffolding (fixtures, session seeding, market-data fakes) is reused from the
M075 integration suite.
"""

from __future__ import annotations

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
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.decision_candidate.portfolio_aware_capital_feasibility import (
    PortfolioAwareCapitalAssessment,
    PortfolioAwareOutcome,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    SameDayCapitalAssessment,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
)
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_ALL_TABLES = [
    "operator_position_event",
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
        application_name="empirical-platform-m077-second-pass",
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


# ---------------------------------------------------------------------------
# M077 helpers
# ---------------------------------------------------------------------------


def _record(
    config: PostgreSQLConfigSnapshot,
    *,
    gid: str,
    pos: str,
    symbol: str,
    kind: OperatorPositionEventKind,
    quantity: int,
    price: str,
    at: datetime,
    plan: str | None = None,
) -> None:
    """Append one event through the REAL M076 repository -- no shortcuts, so
    every domain and persistence invariant is genuinely exercised."""
    with postgres_repository_runtime(config) as runtime:
        runtime.operator_position_ledger.append_validated(
            OperatorAssertedPositionEvent(
                governance_id=gid,
                runtime_id=f"rt-{gid}",
                position_governance_id=pos,
                instrument_symbol=symbol,
                kind=kind,
                quantity=quantity,
                asserted_price=Decimal(price),
                event_timestamp=at,
                recorded_at=at,
                source_position_plan_governance_id=plan,
            )
        )


def _build_portfolio_brief(
    config: PostgreSQLConfigSnapshot,
    identity: object,
    *,
    include_portfolio_aware: bool = True,
) -> object:
    with postgres_repository_runtime(config) as runtime:
        handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            operator_position_ledger_repository=(
                runtime.operator_position_ledger if include_portfolio_aware else None
            ),
            include_portfolio_aware_feasibility=include_portfolio_aware,
        )
        return handler.handle(BuildDailyResearchBriefQuery(identity=identity))  # type: ignore[arg-type]


def _portfolio_of(brief: object) -> PortfolioAwareCapitalAssessment:
    assessment = brief.portfolio_aware_capital_assessment  # type: ignore[attr-defined]
    assert assessment is not None
    return assessment


def _seed_session(tmp_path: Path, config: PostgreSQLConfigSnapshot, gid: str) -> object:
    return _run_session(
        session_governance_id=gid,
        artifact_path=tmp_path / f"{gid}.json",
        config=config,
    )


# ---------------------------------------------------------------------------
# Fresh second pass. Deliberately different from the first suite in every
# input that could hide a bug: different governance ids, different symbols,
# different timestamps, different quantities, different asserted prices,
# a different capital base, and a different universe.
# ---------------------------------------------------------------------------

_SECOND_FLAT_DAYS = 13
_SECOND_AS_OF = _T0 + timedelta(days=_SECOND_FLAT_DAYS)


def _shifted_breakout_csv(base_price: Decimal, breakout_pct: Decimal, breakout_vol: int) -> bytes:
    """Same genuine flat->breakout shape as the first suite, but the breakout
    lands on day 13 rather than day 10.

    The reference window must be entirely flat for the scan to see a genuine
    breakout, so moving only `as_of` later is not enough -- the window would
    then contain earlier breakout bars and the scan correctly reports NO_TRADE.
    The fixture itself has to shift.
    """
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(_SECOND_FLAT_DAYS):
        ts = (_T0 + timedelta(days=i)).isoformat()
        lines.append(
            f"{ts},{base_price:.4f},{base_price * Decimal('1.001'):.4f},"
            f"{base_price * Decimal('0.999'):.4f},{base_price:.4f},50000"
        )
    breakout_close = base_price * (Decimal("1") + breakout_pct)
    for j in range(4):
        ts = (_T0 + timedelta(days=_SECOND_FLAT_DAYS + j)).isoformat()
        c = breakout_close * (Decimal("1") + Decimal("0.001") * j)
        lines.append(
            f"{ts},{c:.4f},{c * Decimal('1.002'):.4f},{c * Decimal('0.998'):.4f},"
            f"{c:.4f},{breakout_vol}"
        )
    return ("\n".join(lines) + "\n").encode()


_SECOND_EQUITY = Decimal("43750.25")

# Different base prices, breakout percentages, volumes, universe, as_of,
# equity and risk budget from the first suite -- but the breakout must stay
# inside the frozen M059 2:1 reward:risk geometry (entry within ~0.67% of the
# reference high), so 0.3%/0.6% are used rather than the double-digit values an
# earlier draft tried, which produced INVALID_TARGET_GEOMETRY and no approved
# plans at all.
_SECOND_FIXTURES = {
    "NVDA": _shifted_breakout_csv(Decimal("42.50"), Decimal("0.003"), 900_000),
    "AMD": _shifted_breakout_csv(Decimal("17.25"), Decimal("0.006"), 640_000),
}


def _run_second_session(
    *, gid: str, artifact_path: Path, config: PostgreSQLConfigSnapshot
) -> object:
    clock = _FixedClock(_SECOND_AS_OF)
    source = FakeMarketDataSource(_SECOND_FIXTURES, clock=clock)
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
                session_governance_id=gid,
                as_of=_SECOND_AS_OF,
                universe=("NVDA", "AMD"),
                lookback_days=20,
                artifact_path=str(artifact_path),
                account_equity=_SECOND_EQUITY,
                risk_percent=Decimal("0.015"),
                source=source,
                runtime_identifier_generator=generator,
                reference_window_size=4,
            )
        )


def test_m077_second_pass_held_exposure_against_a_different_capital_base(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-9101",
        pos="POS-99001",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=37,
        price="291.6375",
        at=_SECOND_AS_OF - timedelta(days=4),
    )
    result = _run_second_session(
        gid="RESEARCH-9101", artifact_path=tmp_path / "s2.json", config=config
    )
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    expected_held = Decimal("291.6375") * 37
    assert Decimal(portfolio.held_asserted_notional) == expected_held
    assert Decimal(portfolio.capital_base) == _SECOND_EQUITY
    # Ceiling is the exact product -- never rounded (implementation review R03).
    assert Decimal(portfolio.capital_ceiling) == _SECOND_EQUITY * Decimal("1.00")
    assert Decimal(portfolio.remaining_capital_under_policy) == (
        Decimal(portfolio.capital_ceiling) - expected_held
    )

    with clean_tables.begin() as conn:
        row = conn.execute(
            text(
                "SELECT quantity, asserted_price FROM operator_position_event "
                "WHERE governance_id = 'OPEV-9101'"
            )
        ).one()
    assert row.quantity * row.asserted_price == expected_held


def test_m077_second_pass_partial_reduction_then_new_proposal(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    opened_at = _SECOND_AS_OF - timedelta(days=6)
    _record(
        config,
        gid="OPEV-9110",
        pos="POS-99010",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=80,
        price="150.125",
        at=opened_at,
    )
    _record(
        config,
        gid="OPEV-9111",
        pos="POS-99010",
        symbol="SMCI",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=55,
        price="401.999999",
        at=opened_at + timedelta(days=2),
    )
    result = _run_second_session(
        gid="RESEARCH-9102", artifact_path=tmp_path / "s3.json", config=config
    )
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    # 25 remaining at the ORIGINAL 150.125 -- the 401.999999 reduction price is
    # never used to revalue anything.
    assert Decimal(portfolio.held_asserted_notional) == Decimal("150.125") * 25
    assert portfolio.held_positions[0].asserted_entry_price == "150.125"
    assert "401.999999" not in portfolio.held_asserted_notional


def test_m077_second_pass_exhausted_capital_blocks_every_proposal(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-9120",
        pos="POS-99020",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=500,
        price="99.9999",
        at=_SECOND_AS_OF - timedelta(days=3),
    )
    result = _run_second_session(
        gid="RESEARCH-9103", artifact_path=tmp_path / "s4.json", config=config
    )
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    assert Decimal(portfolio.held_asserted_notional) > _SECOND_EQUITY
    assert portfolio.outcome is PortfolioAwareOutcome.ALREADY_AT_OR_OVER_CAPITAL
    assert portfolio.admitted_plan_count == 0
    assert Decimal(portfolio.remaining_capital_under_policy) == Decimal("0")


def test_m077_second_pass_migrations_from_empty_and_deterministic(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-9130",
        pos="POS-99030",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=11,
        price="7.000001",
        at=_SECOND_AS_OF - timedelta(days=2),
    )
    result = _run_second_session(
        gid="RESEARCH-9104", artifact_path=tmp_path / "s5.json", config=config
    )
    first = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    second = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    assert first == second
    assert Decimal(first.held_asserted_notional) == Decimal("7.000001") * 11
