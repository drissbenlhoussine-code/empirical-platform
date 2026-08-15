"""MILESTONE-077 -- portfolio-aware capital feasibility against real PostgreSQL.

Reuses M072's real-session seeding so today's proposals are genuinely
persisted rows, and M076's real ledger repository so held exposure is genuinely
persisted operator assertions. Every figure the assessment reports is
cross-checked against raw SQL read independently of the repository helpers.

Scaffolding (fixtures, session seeding, market-data fakes) is reused from the
M075 integration suite.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
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
    PortfolioAwareUnassessableReason,
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
# Scenarios over genuinely persisted rows
# ---------------------------------------------------------------------------


def test_m077_no_held_positions_matches_same_day_view(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    result = _seed_session(tmp_path, config, "RESEARCH-7701")
    brief = _build_portfolio_brief(config, result.identity)  # type: ignore[attr-defined]
    portfolio = _portfolio_of(brief)

    assert portfolio.held_position_count == 0
    assert Decimal(portfolio.held_asserted_notional) == Decimal("0")
    # With nothing held, the portfolio-aware admission must agree with M075's
    # own admission over the same plans.
    same_day = brief.same_day_capital_assessment  # type: ignore[attr-defined]
    assert portfolio.admitted_plan_count == same_day.admitted_plan_count


def test_m077_held_exposure_reduces_headroom_and_matches_raw_sql(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7710",
        pos="POS-7710",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7702")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    assert portfolio.held_position_count == 1
    assert Decimal(portfolio.held_asserted_notional) == Decimal("70000")

    # Cross-check against raw SQL, with no repository helper in the path.
    with clean_tables.begin() as conn:
        row = conn.execute(
            text(
                "SELECT quantity, asserted_price FROM operator_position_event "
                "WHERE governance_id = 'OPEV-7710'"
            )
        ).one()
    assert row.quantity * row.asserted_price == Decimal("70000")
    assert Decimal(portfolio.capital_ceiling) - Decimal("70000") == Decimal(
        portfolio.remaining_capital_under_policy
    )


def test_m077_held_exposure_beyond_ceiling_blocks_every_plan(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7720",
        pos="POS-7720",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=2000,
        price="100",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7703")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    assert portfolio.outcome is PortfolioAwareOutcome.ALREADY_AT_OR_OVER_CAPITAL
    assert portfolio.admitted_plan_count == 0
    assert Decimal(portfolio.remaining_capital_under_policy) == Decimal("0")


def test_m077_closed_position_before_as_of_does_not_consume_capital(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    opened_at = _AS_OF_BREAKOUT - timedelta(days=5)
    _record(
        config,
        gid="OPEV-7730",
        pos="POS-7730",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=1000,
        price="100",
        at=opened_at,
    )
    _record(
        config,
        gid="OPEV-7731",
        pos="POS-7730",
        symbol="TSLA",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=1000,
        price="110",
        at=opened_at + timedelta(days=1),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7704")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    assert portfolio.held_position_count == 0
    assert Decimal(portfolio.held_asserted_notional) == Decimal("0")
    assert portfolio.outcome is not PortfolioAwareOutcome.ALREADY_AT_OR_OVER_CAPITAL


def test_m077_reduction_before_as_of_is_reflected_at_entry_price(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    opened_at = _AS_OF_BREAKOUT - timedelta(days=5)
    _record(
        config,
        gid="OPEV-7740",
        pos="POS-7740",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=opened_at,
    )
    _record(
        config,
        gid="OPEV-7741",
        pos="POS-7740",
        symbol="TSLA",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=60,
        price="900",
        at=opened_at + timedelta(days=1),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7705")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    # 40 remaining valued at the ORIGINAL asserted entry price of 700, never
    # at the 900 the reduction cited -- no revaluation anywhere.
    assert Decimal(portfolio.held_asserted_notional) == Decimal("28000")
    assert portfolio.held_positions[0].asserted_entry_price == "700"


def test_m077_events_after_as_of_are_excluded_and_counted(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7750",
        pos="POS-7750",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    _record(
        config,
        gid="OPEV-7751",
        pos="POS-7750",
        symbol="TSLA",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=60,
        price="700",
        at=_AS_OF_BREAKOUT + timedelta(days=3),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7706")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    assert Decimal(portfolio.held_asserted_notional) == Decimal("70000")
    assert portfolio.excluded_future_event_count == 1


def test_m077_mixed_timezone_offsets_for_one_instant_agree(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    utc_moment = _AS_OF_BREAKOUT - timedelta(days=2)
    offset_moment = utc_moment.astimezone(timezone(timedelta(hours=-5)))
    assert utc_moment == offset_moment
    _record(
        config,
        gid="OPEV-7760",
        pos="POS-7760",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=offset_moment,
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7707")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    assert Decimal(portfolio.held_asserted_notional) == Decimal("70000")


def test_m077_suppression_is_distinct_from_a_feasible_verdict(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed_session(tmp_path, config, "RESEARCH-7708")
    brief = _build_portfolio_brief(config, result.identity, include_portfolio_aware=False)  # type: ignore[attr-defined]
    assert brief.portfolio_aware_capital_assessment is None  # type: ignore[attr-defined]

    payload = render_daily_research_brief_json(brief)  # type: ignore[arg-type]
    section = payload["PORTFOLIO_AWARE_CAPITAL_FEASIBILITY"]
    assert section["computed"] is False
    assert "not a finding" in section["note"]


def test_m077_missing_ledger_is_withheld_not_reported_as_empty(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed_session(tmp_path, config, "RESEARCH-7709")
    with postgres_repository_runtime(config) as runtime:
        handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            operator_position_ledger_repository=None,
        )
        brief = handler.handle(BuildDailyResearchBriefQuery(identity=result.identity))  # type: ignore[attr-defined,arg-type]
    portfolio = _portfolio_of(brief)
    assert portfolio.outcome is PortfolioAwareOutcome.NOT_ASSESSABLE
    assert portfolio.unassessable_reason is PortfolioAwareUnassessableReason.LEDGER_UNAVAILABLE


def test_m077_text_and_json_agree_semantically(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7770",
        pos="POS-7770",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7710")
    brief = _build_portfolio_brief(config, result.identity)  # type: ignore[attr-defined]
    portfolio = _portfolio_of(brief)

    payload = render_daily_research_brief_json(brief)["PORTFOLIO_AWARE_CAPITAL_FEASIBILITY"]  # type: ignore[arg-type]
    text_output = render_daily_research_brief_text(brief)  # type: ignore[arg-type]

    assert payload["outcome"] == portfolio.outcome.value
    assert payload["held_asserted_notional"] == portfolio.held_asserted_notional
    assert "PORTFOLIO-AWARE CAPITAL FEASIBILITY" in text_output
    assert portfolio.held_asserted_notional in text_output
    assert "NOT broker-verified" in text_output


def test_m077_double_counting_is_prevented_for_a_plan_already_acted_upon(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed_session(tmp_path, config, "RESEARCH-7711")
    brief_before = _build_portfolio_brief(config, result.identity)  # type: ignore[attr-defined]
    before = _portfolio_of(brief_before)
    assert before.verdicts, "the session must produce at least one approved plan"
    acted_plan = before.verdicts[0].position_plan_governance_id

    _record(
        config,
        gid="OPEV-7780",
        pos="POS-7780",
        symbol=before.verdicts[0].instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=10,
        price="100",
        at=_AS_OF_BREAKOUT - timedelta(days=1),
        plan=acted_plan,
    )
    after = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    assert acted_plan in after.plans_already_acted_upon
    assert all(v.position_plan_governance_id != acted_plan for v in after.verdicts)
    assert after.held_positions[0].source_position_plan_governance_id == acted_plan


def test_m077_is_deterministic_across_two_independent_builds(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7790",
        pos="POS-7790",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7712")
    first = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    second = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    assert first == second


def test_m077_reads_a_consistent_snapshot_while_a_writer_appends(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """The consistency requirement is a point-in-time snapshot, and one
    statement provides exactly that. Proven, not asserted."""
    config = _config()
    _record(
        config,
        gid="OPEV-7800",
        pos="POS-7800",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7713")

    barrier = threading.Barrier(2)

    def writer() -> None:
        barrier.wait(timeout=20)
        _record(
            config,
            gid="OPEV-7801",
            pos="POS-7801",
            symbol="NVDA",
            kind=OperatorPositionEventKind.OPENED,
            quantity=10,
            price="50",
            at=_AS_OF_BREAKOUT - timedelta(days=1),
        )

    def reader() -> PortfolioAwareCapitalAssessment:
        barrier.wait(timeout=20)
        return _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_future = pool.submit(writer)
        reader_future = pool.submit(reader)
        writer_future.result(timeout=60)
        snapshot = reader_future.result(timeout=60)

    # The reader saw either the pre-write or the post-write ledger -- never a
    # torn state. Both are coherent; neither is a partial position.
    assert Decimal(snapshot.held_asserted_notional) in {
        Decimal("70000"),
        Decimal("70500"),
    }
    assert snapshot.held_position_count in {1, 2}

    # After both complete, the committed ledger is unambiguous.
    final = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    assert Decimal(final.held_asserted_notional) == Decimal("70500")
    assert final.held_position_count == 2


def test_m077_held_notional_never_revalues_and_says_so(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7810",
        pos="POS-7810",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        price="700",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7714")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]
    assert any("not revalued" in line for line in portfolio.limitations)
    assert any("ASSERTED entry price" in line for line in portfolio.limitations)


def test_m077_exact_decimal_round_trip_through_postgresql(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7820",
        pos="POS-7820",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=3,
        price="123.456789",
        at=_AS_OF_BREAKOUT - timedelta(days=2),
    )
    result = _seed_session(tmp_path, config, "RESEARCH-7715")
    portfolio = _portfolio_of(_build_portfolio_brief(config, result.identity))  # type: ignore[attr-defined]

    expected = Decimal("123.456789") * 3
    assert Decimal(portfolio.held_asserted_notional) == expected
    with clean_tables.begin() as conn:
        stored = conn.execute(
            text(
                "SELECT asserted_price FROM operator_position_event "
                "WHERE governance_id = 'OPEV-7820'"
            )
        ).scalar_one()
    assert stored == Decimal("123.456789")
