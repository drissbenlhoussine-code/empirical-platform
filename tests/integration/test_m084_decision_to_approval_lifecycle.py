"""MILESTONE-084 -- the whole flow, end to end, against real PostgreSQL.

Where the attack suite proves what the database refuses, this proves what it
accepts: one configuration, one evaluation context bound to a real M083
watermark, one derived proposal, one human decision, one order intent -- each
step persisted, read back, and compared to what went in.

Round-tripping matters more here than it looks. Every value crosses a type
boundary twice (Decimal, timezone-aware datetime, naive time, StrEnum, text
array), and the repositories refuse rather than coerce on the way back, so a
round trip that returns an equal object is evidence that no conversion is
quietly reshaping the terms a human approved.
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
    recompute_consumed_receipt_digest,
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
    OperatorAction,
    SubmissionState,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import (
    ProposalStatus,
    TradeProposal,
    compute_fingerprint,
    evaluate_trade_proposal,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors.foundation import FoundationError
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVALUATED_AT = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=6,
        max_overflow=6,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m084-lifecycle",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url())
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(_alembic_config(), "head")
    try:
        yield eng
    finally:
        with eng.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        eng.dispose()


@pytest.fixture
def clean(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE approved_order_intent, trade_approval_decision, "
                "trade_proposal_risk_check, trade_proposal, evaluation_context, "
                "operator_trading_configuration, evaluation_evidence_watermark"
            )
        )
    return engine


@pytest.fixture
def runtime(clean: Engine) -> Iterator[PostgresRepositoryRuntime]:
    with postgres_repository_runtime(_config()) as composed:
        yield composed


def a_configuration(**overrides: object) -> OperatorTradingConfiguration:
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-084-0001",
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
    context_id: str = "ECX-0001",
    watermark_id: str = "WM-0001",
) -> EvaluationContext:
    """Capture a real M083 watermark and bind a context to it.

    The watermark is captured through the M083 repository, not fabricated, so
    the receipt count and digest below describe evidence that genuinely exists
    in this database.
    """
    watermark = runtime.evaluation_evidence_watermarks.capture(watermark_governance_id=watermark_id)
    return build_evaluation_context(
        evaluation_context_id=context_id,
        configuration=configuration,
        watermark=watermark,
        quote_id="QTE-0001",
        account_snapshot_id="ACC-0001",
        session_id="SES-0001",
        cost_estimate_id="CST-0001",
        instrument_universe_version="UNIVERSE-2026-06",
        strategy_version="STRATEGY-0001",
        created_at=_EVALUATED_AT,
    )


def a_proposal(
    configuration: OperatorTradingConfiguration,
    context: EvaluationContext,
    *,
    proposal_id: str = "PRP-0001",
) -> TradeProposal:
    outcome = evaluate_trade_proposal(
        configuration=configuration,
        evaluation_context_id=context.evaluation_context_id,
        proposal_governance_id=proposal_id,
        evaluated_at=_EVALUATED_AT,
        symbol="AAPL",
        quote=QuoteSnapshot(
            quote_id="QTE-0001",
            provider_id="PROVIDER-A",
            symbol="AAPL",
            bid=Decimal("199.95"),
            ask=Decimal("200.10"),
            last_trade=Decimal("200.00"),
            observed_at=_EVALUATED_AT - timedelta(seconds=5),
            feed_kind=DataFeedKind.REAL_TIME,
        ),
        account=AccountSnapshot(
            account_snapshot_id="ACC-0001",
            provider_id="PROVIDER-A",
            account_reference="PREP-ACCOUNT-1",
            base_currency="USD",
            cash_available=Decimal("5000"),
            equity_total=Decimal("10000"),
            realized_pnl_today=Decimal("0"),
            orders_submitted_today=0,
            observed_at=_EVALUATED_AT - timedelta(seconds=5),
        ),
        session=SessionSnapshot(
            session_id="SES-0001",
            provider_id="PROVIDER-A",
            market="XNAS",
            status=MarketStatus.OPEN,
            observed_at=_EVALUATED_AT - timedelta(seconds=5),
        ),
        instrument=InstrumentMetadata(
            symbol="AAPL", market="XNAS", currency="USD", is_fractionable=False, lot_size=1
        ),
        liquidity=LiquiditySnapshot(
            symbol="AAPL",
            average_daily_volume_shares=50_000_000,
            observed_at=_EVALUATED_AT - timedelta(seconds=5),
        ),
        cost_estimate=TradingCostEstimate(
            estimate_id="CST-0001",
            provider_id="PROVIDER-A",
            symbol="AAPL",
            commission=Decimal("1.00"),
            estimated_slippage_percent=Decimal("0.1"),
            observed_at=_EVALUATED_AT - timedelta(seconds=5),
        ),
        positions=(),
        open_orders=(),
        evidence_age_seconds=Decimal("60"),
    )
    assert outcome.proposal is not None, outcome.no_trade_reason
    return outcome.proposal


class TestConfigurationPersistence:
    def test_a_configuration_round_trips_unchanged(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        saved = runtime.operator_trading_configurations.save(a_configuration())
        loaded = runtime.operator_trading_configurations.get("CFG-084-0001", 1)
        assert loaded == saved == a_configuration()

    def test_every_decimal_survives_the_round_trip_exactly(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        # Money read back as a float would silently change what a limit means.
        runtime.operator_trading_configurations.save(a_configuration())
        loaded = runtime.operator_trading_configurations.get("CFG-084-0001", 1)
        assert loaded is not None
        assert isinstance(loaded.maximum_capital_per_trade, Decimal)
        assert loaded.maximum_capital_per_trade == Decimal("2000")

    def test_latest_returns_the_highest_version(self, runtime: PostgresRepositoryRuntime) -> None:
        runtime.operator_trading_configurations.save(a_configuration())
        runtime.operator_trading_configurations.save(a_configuration(configuration_version=3))
        runtime.operator_trading_configurations.save(a_configuration(configuration_version=2))
        latest = runtime.operator_trading_configurations.latest("CFG-084-0001")
        assert latest is not None
        assert latest.configuration_version == 3

    def test_an_unknown_configuration_reads_as_none(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        assert runtime.operator_trading_configurations.get("CFG-NOPE", 1) is None
        assert runtime.operator_trading_configurations.latest("CFG-NOPE") is None

    def test_a_forbidden_configuration_is_refused_by_the_database_as_well(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        # The domain type refuses this at construction, so the only way to
        # reach the database with it is to go around the constructor -- which
        # is exactly what a future careless caller would do.
        configuration = a_configuration()
        object.__setattr__(configuration, "account_mode", AccountMode.LIVE)
        with pytest.raises(FoundationError):
            runtime.operator_trading_configurations.save(configuration)


class TestEvaluationContextPersistence:
    def test_a_context_binds_a_real_watermark_and_round_trips(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = a_context(runtime, configuration)
        saved = runtime.evaluation_contexts.save(context)
        loaded = runtime.evaluation_contexts.get("ECX-0001")
        assert loaded == saved == context

    def test_the_stored_digest_still_matches_the_stored_watermark(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        # The point of the digest: a reader can check, later and independently,
        # that the context names the evidence set it claims.
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        runtime.evaluation_contexts.save(a_context(runtime, configuration))

        loaded = runtime.evaluation_contexts.get("ECX-0001")
        assert loaded is not None
        watermark = runtime.evaluation_evidence_watermarks.get(loaded.watermark_governance_id)
        assert watermark is not None
        assert loaded.consumed_receipt_digest == recompute_consumed_receipt_digest(watermark)
        assert loaded.consumed_receipt_count == watermark.captured_receipt_count

    def test_a_context_for_an_uncaptured_watermark_cannot_be_stored(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = a_context(runtime, configuration)
        object.__setattr__(context, "watermark_governance_id", "WM-NEVER-CAPTURED")
        with pytest.raises(FoundationError):
            runtime.evaluation_contexts.save(context)


class TestTheWholeFlow:
    def test_configuration_to_intent_end_to_end(self, runtime: PostgresRepositoryRuntime) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))

        prepared = runtime.trade_proposals.save(a_proposal(configuration, context))
        assert prepared.status is ProposalStatus.PREPARED
        assert prepared.quantity == 9

        decision = runtime.approval_decisions.record(
            record_operator_decision(
                proposal=prepared,
                decision_governance_id="DEC-0001",
                action=OperatorAction.APPROVE,
                operator_identity="operator-1",
                decided_at=_EVALUATED_AT + timedelta(seconds=10),
                approval_expiry_seconds=120,
            )
        )
        approved = runtime.trade_proposals.set_status("PRP-0001", ProposalStatus.APPROVED)
        assert approved.status is ProposalStatus.APPROVED

        intent = runtime.approved_order_intents.issue(
            build_approved_order_intent(
                intent_governance_id="INT-0001",
                proposal=approved,
                decision=decision,
                created_at=_EVALUATED_AT + timedelta(seconds=20),
                idempotency_key="IDEM-0001",
            )
        )
        assert intent.submission_state is SubmissionState.NOT_SUBMITTED
        assert intent.quantity == prepared.quantity
        assert intent.approved_fingerprint == prepared.content_fingerprint

    def test_the_persisted_proposal_still_carries_the_digest_of_its_own_terms(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        # The strongest single check in this file: after a full round trip
        # through PostgreSQL, the fingerprint recomputed from the READ-BACK
        # terms still equals the one stored with them. If any conversion had
        # reshaped a price or a timestamp, this would not hold.
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))
        runtime.trade_proposals.save(a_proposal(configuration, context))

        loaded = runtime.trade_proposals.get("PRP-0001")
        assert loaded is not None
        assert compute_fingerprint(loaded) == loaded.content_fingerprint

    def test_a_rejected_proposal_cannot_produce_an_intent(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))
        prepared = runtime.trade_proposals.save(a_proposal(configuration, context))

        runtime.approval_decisions.record(
            record_operator_decision(
                proposal=prepared,
                decision_governance_id="DEC-0001",
                action=OperatorAction.REJECT,
                operator_identity="operator-1",
                decided_at=_EVALUATED_AT + timedelta(seconds=10),
                approval_expiry_seconds=120,
            )
        )
        rejected = runtime.trade_proposals.set_status("PRP-0001", ProposalStatus.REJECTED)
        assert rejected.status is ProposalStatus.REJECTED
        assert runtime.approved_order_intents.for_proposal("PRP-0001") is None

    def test_a_terminal_proposal_cannot_be_moved_again_through_the_repository(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))
        runtime.trade_proposals.save(a_proposal(configuration, context))
        runtime.trade_proposals.set_status("PRP-0001", ProposalStatus.CANCELLED)
        with pytest.raises(FoundationError):
            runtime.trade_proposals.set_status("PRP-0001", ProposalStatus.APPROVED)

    def test_setting_the_status_of_a_proposal_that_does_not_exist_is_an_error(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        with pytest.raises(FoundationError, match="no trade proposal"):
            runtime.trade_proposals.set_status("PRP-NOPE", ProposalStatus.APPROVED)

    def test_prepared_proposals_are_listed_in_a_deterministic_order(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))
        for proposal_id in ("PRP-0003", "PRP-0001", "PRP-0002"):
            runtime.trade_proposals.save(
                a_proposal(configuration, context, proposal_id=proposal_id)
            )
        runtime.trade_proposals.set_status("PRP-0002", ProposalStatus.CANCELLED)

        listed = runtime.trade_proposals.list_by_status(ProposalStatus.PREPARED)
        assert [p.proposal_governance_id for p in listed] == ["PRP-0001", "PRP-0003"]

    def test_the_risk_checks_are_stored_and_read_back_in_evaluation_order(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        # "Which gates did this pass, and what did each one see" is the question
        # an operator asks months later. An answer that has to be re-derived
        # from code that has since changed is not an answer, so the checks are
        # persisted alongside the proposal and read back in the order they ran.
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))
        saved = runtime.trade_proposals.save(a_proposal(configuration, context))
        assert saved.risk_checks

        loaded = runtime.trade_proposals.get("PRP-0001")
        assert loaded is not None
        assert loaded.risk_checks == saved.risk_checks


class TestDecisionAndIntentQueries:
    def test_a_decision_is_found_by_identity_and_by_proposal(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        configuration = runtime.operator_trading_configurations.save(a_configuration())
        context = runtime.evaluation_contexts.save(a_context(runtime, configuration))
        prepared = runtime.trade_proposals.save(a_proposal(configuration, context))
        recorded = runtime.approval_decisions.record(
            record_operator_decision(
                proposal=prepared,
                decision_governance_id="DEC-0001",
                action=OperatorAction.APPROVE,
                operator_identity="operator-1",
                decided_at=_EVALUATED_AT + timedelta(seconds=10),
                approval_expiry_seconds=120,
            )
        )
        assert runtime.approval_decisions.get("DEC-0001") == recorded
        assert runtime.approval_decisions.for_proposal("PRP-0001") == recorded

    def test_an_unknown_decision_or_intent_reads_as_none(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        assert runtime.approval_decisions.get("DEC-NOPE") is None
        assert runtime.approval_decisions.for_proposal("PRP-NOPE") is None
        assert runtime.approved_order_intents.get("INT-NOPE") is None
        assert runtime.approved_order_intents.for_proposal("PRP-NOPE") is None

    def test_the_intent_repository_exposes_only_issue_and_reads(
        self, runtime: PostgresRepositoryRuntime
    ) -> None:
        # A capability that does not exist is proven by its absence from the
        # interface, so the interface is asserted rather than assumed. Nothing
        # named submit, send, or mark_submitted may appear here.
        public = {name for name in dir(runtime.approved_order_intents) if not name.startswith("_")}
        assert public == {"issue", "get", "for_proposal"}
