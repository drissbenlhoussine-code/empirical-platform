"""Shared fixtures for the MILESTONE-085 integration suites.

Not a test module: `pytest` collects `test_*.py`, so this is imported rather than
run. It exists because three M085 suites -- database enforcement, concurrency and
the paper lifecycle -- all need the SAME real MILESTONE-084 chain underneath
them: a configuration, an M083 watermark, an evaluation context, a proposal, a
human decision and an approved order intent.

THE CHAIN IS BUILT, NEVER FABRICATED. Every row is produced by the real M084
engine and stored through the real M084 repositories. Inserting a hand-written
`approved_order_intent` row would test M085 against an intent that M084's own
rules might have refused, which is precisely the input contract this milestone
must not get wrong.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.evaluation_context import (
    EvaluationContext,
    build_evaluation_context,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.product_market_inputs import (
    AccountSnapshot,
    DataFeedKind,
    InstrumentMetadata,
    LiquiditySnapshot,
    MarketStatus,
    QuoteSnapshot,
    SessionSnapshot,
    TradingCostEstimate,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovedOrderIntent,
    OperatorAction,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import (
    ProposalStatus,
    TradeProposal,
    evaluate_trade_proposal,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATED_AT = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)

#: The M085 tables, in dependency order for TRUNCATE.
M085_TABLES = (
    "paper_execution_event",
    "paper_broker_acknowledgement",
    "paper_execution_attempt",
    "paper_execution_authorization",
    "paper_submission_preview",
    "paper_account_snapshot",
    "paper_execution_kill_switch",
)

M084_TABLES = (
    "approved_order_intent",
    "trade_approval_decision",
    "trade_proposal_risk_check",
    "trade_proposal",
    "evaluation_context",
    "operator_trading_configuration",
    "evaluation_evidence_watermark",
)


def postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def config(application_name: str = "empirical-platform-m085") -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=8,
        max_overflow=8,
        connection_timeout_seconds=5,
        application_name=application_name,
    )


def alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def build_engine() -> Iterator[Engine]:
    """A database at M085 head, rebuilt from the complete migration history.

    Dropping and recreating `public` rather than truncating means every run
    installs the whole history, so a migration that only works on top of an
    existing schema fails here rather than in production.
    """
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    engine = sa.create_engine(config().sqlalchemy_url())
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(alembic_config(), "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        engine.dispose()


def truncate_all(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join((*M085_TABLES, *M084_TABLES))))


def database_identity(engine: Engine) -> dict[str, str]:
    """Facts that distinguish one real database from another.

    Recorded so that "three clean repetitions" can be shown to have run against
    three genuinely rebuilt schemas rather than three passes over one.
    """
    with engine.begin() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT current_database() AS database, "
                    "(SELECT oid FROM pg_database WHERE datname = current_database()) "
                    "  AS database_oid, "
                    "(SELECT oid FROM pg_namespace WHERE nspname = 'public') AS schema_oid, "
                    "(SELECT oid FROM pg_class WHERE relname = 'paper_execution_attempt') "
                    "  AS attempt_oid"
                )
            )
            .mappings()
            .one()
        )
    return {key: str(value) for key, value in row.items()}


def a_configuration(**overrides: object) -> OperatorTradingConfiguration:
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-085-0001",
        "configuration_version": 1,
        "base_currency": "USD",
        "permitted_markets": ("XNAS",),
        "watchlist": ("AAPL", "MSFT"),
        "prohibited_instruments": ("PENNY",),
        "maximum_deployable_capital": Decimal("10000"),
        "maximum_capital_per_trade": Decimal("2000"),
        "maximum_percent_per_trade": Decimal("20"),
        "minimum_cash_reserve": Decimal("1000"),
        "maximum_simultaneous_positions": 3,
        "maximum_daily_loss": Decimal("500"),
        "maximum_daily_order_count": 10,
        "minimum_price": Decimal("5"),
        "maximum_price": Decimal("1000"),
        "minimum_liquidity_shares": 100_000,
        "maximum_spread_percent": Decimal("1"),
        "maximum_estimated_slippage_percent": Decimal("1"),
        "maximum_evidence_age_seconds": 86_400,
        "maximum_market_data_age_seconds": 60,
        "permitted_session": TradingSession.REGULAR,
        "earliest_entry_time": time(10, 0),
        "latest_entry_time": time(15, 30),
        "mandatory_liquidation_time": time(15, 45),
        "operator_timezone": "Europe/Helsinki",
        "exchange_calendar_policy": "XNAS-REGULAR-2026",
        "proposal_expiry_seconds": 300,
        "approval_expiry_seconds": 120,
        "default_order_type": OrderType.LIMIT,
        "permitted_order_types": (OrderType.LIMIT, OrderType.MARKET),
        "limit_price_policy": LimitPricePolicy.ASK,
        "stop_loss_percent": Decimal("2"),
        "profit_exit_percent": Decimal("4"),
        "maximum_leverage": Decimal("1"),
        "short_selling_permitted": False,
        "overnight_positions_permitted": False,
        "account_mode": AccountMode.PREPARATION,
        "kill_switch": KillSwitchState.DISENGAGED,
    }
    defaults.update(overrides)
    return OperatorTradingConfiguration(**defaults)  # type: ignore[arg-type]


def a_context(
    runtime: PostgresRepositoryRuntime,
    configuration: OperatorTradingConfiguration,
    *,
    context_id: str = "ECX-085-0001",
    watermark_id: str = "WM-085-0001",
) -> EvaluationContext:
    watermark = runtime.evaluation_evidence_watermarks.capture(watermark_governance_id=watermark_id)
    return build_evaluation_context(
        evaluation_context_id=context_id,
        configuration=configuration,
        watermark=watermark,
        quote_id="QTE-085-0001",
        account_snapshot_id="ACC-085-0001",
        session_id="SES-085-0001",
        cost_estimate_id="CST-085-0001",
        instrument_universe_version="UNIVERSE-2026-06",
        strategy_version="STRATEGY-0001",
        created_at=EVALUATED_AT,
    )


def a_proposal(
    configuration: OperatorTradingConfiguration,
    context: EvaluationContext,
    *,
    proposal_id: str = "PRP-085-0001",
    symbol: str = "AAPL",
) -> TradeProposal:
    outcome = evaluate_trade_proposal(
        configuration=configuration,
        evaluation_context_id=context.evaluation_context_id,
        proposal_governance_id=proposal_id,
        evaluated_at=EVALUATED_AT,
        symbol=symbol,
        quote=QuoteSnapshot(
            quote_id="QTE-085-0001",
            provider_id="PROVIDER-A",
            symbol=symbol,
            bid=Decimal("199.95"),
            ask=Decimal("200.10"),
            last_trade=Decimal("200.00"),
            observed_at=EVALUATED_AT - timedelta(seconds=5),
            feed_kind=DataFeedKind.REAL_TIME,
        ),
        account=AccountSnapshot(
            account_snapshot_id="ACC-085-0001",
            provider_id="PROVIDER-A",
            account_reference="PREP-ACCOUNT-1",
            base_currency="USD",
            cash_available=Decimal("5000"),
            equity_total=Decimal("10000"),
            realized_pnl_today=Decimal("0"),
            orders_submitted_today=0,
            observed_at=EVALUATED_AT - timedelta(seconds=5),
        ),
        session=SessionSnapshot(
            session_id="SES-085-0001",
            provider_id="PROVIDER-A",
            market="XNAS",
            status=MarketStatus.OPEN,
            observed_at=EVALUATED_AT - timedelta(seconds=5),
        ),
        instrument=InstrumentMetadata(
            symbol=symbol, market="XNAS", currency="USD", is_fractionable=False, lot_size=1
        ),
        liquidity=LiquiditySnapshot(
            symbol=symbol,
            average_daily_volume_shares=50_000_000,
            observed_at=EVALUATED_AT - timedelta(seconds=5),
        ),
        cost_estimate=TradingCostEstimate(
            estimate_id="CST-085-0001",
            provider_id="PROVIDER-A",
            symbol=symbol,
            commission=Decimal("1.00"),
            estimated_slippage_percent=Decimal("0.1"),
            observed_at=EVALUATED_AT - timedelta(seconds=5),
        ),
        positions=(),
        open_orders=(),
        evidence_age_seconds=Decimal("60"),
    )
    assert outcome.proposal is not None, outcome.no_trade_reason
    return outcome.proposal


def an_approved_intent(
    runtime: PostgresRepositoryRuntime,
    *,
    intent_id: str = "INT-085-0001",
    proposal_id: str = "PRP-085-0001",
    context_id: str = "ECX-085-0001",
    watermark_id: str = "WM-085-0001",
    configuration_id: str = "CFG-085-0001",
) -> ApprovedOrderIntent:
    """The whole real M084 chain, ending in one persisted approved intent.

    This is MILESTONE-085's entire input. Every M085 suite starts from a row
    produced exactly this way.
    """
    configuration = a_configuration(configuration_governance_id=configuration_id)
    runtime.operator_trading_configurations.save(configuration)
    context = a_context(runtime, configuration, context_id=context_id, watermark_id=watermark_id)
    runtime.evaluation_contexts.save(context)
    proposal = a_proposal(configuration, context, proposal_id=proposal_id)
    runtime.trade_proposals.save(proposal)

    decision = record_operator_decision(
        proposal=proposal,
        decision_governance_id=f"DEC-{proposal_id}",
        action=OperatorAction.APPROVE,
        operator_identity="owner",
        decided_at=EVALUATED_AT + timedelta(seconds=10),
        approval_expiry_seconds=configuration.approval_expiry_seconds,
    )
    runtime.approval_decisions.record(decision)
    approved = runtime.trade_proposals.set_status(
        proposal.proposal_governance_id, ProposalStatus.APPROVED
    )
    intent = build_approved_order_intent(
        intent_governance_id=intent_id,
        proposal=approved,
        decision=decision,
        created_at=EVALUATED_AT + timedelta(seconds=20),
        idempotency_key=f"IDEM-{intent_id}",
    )
    return runtime.approved_order_intents.issue(intent)


def paper_runtime(service: PostgresPersistenceService) -> PostgresPaperExecutionRuntime:
    return PostgresPaperExecutionRuntime(service)
