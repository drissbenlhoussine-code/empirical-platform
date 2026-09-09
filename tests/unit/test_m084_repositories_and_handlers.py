"""MILESTONE-084 -- repository row mapping and handler control flow, offline.

Two things are exercised here, both without a database:

  - the repositories' own row mapping and Python branching, through a
    hand-written fake that duck-types the narrow `unit_of_work()`/`execute()`
    surface `PostgresPersistenceService` exposes. The fake is NOT a database
    and NOT a simulation of any constraint or trigger: it returns pre-scripted
    rows so that the REPOSITORY CLASS's own behaviour can be checked. Real
    constraint, trigger and concurrency semantics stay covered exclusively by
    the PostgreSQL integration tests, because faking those would make the test
    glue the thing under test instead of PostgreSQL.

  - the usecase handlers' branching, through in-memory repositories. Same
    reasoning: what is under test is the handler's decision to refuse, to load
    before writing, and to record a decision before moving a status -- not the
    database's enforcement of the same rules.

This file follows MILESTONE-083 REV-004's precedent, which established that a
repository whose Python control flow is only reachable through a live database
is a repository whose control flow is untested wherever that database is
absent -- as it is in CI.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from tests.unit.test_m084_domain_core import (
    EVALUATED_AT,
    a_configuration,
    a_cost_estimate,
    a_liquidity,
    a_proposal,
    a_quote,
    a_session,
    an_account,
    an_instrument,
)

from empirical_platform.decision_candidate.evaluation_context import EvaluationContext
from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
    OperatorAction,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus, TradeProposal
from empirical_platform.shared.errors.foundation import FoundationError
from empirical_platform.shared.persistence.postgres_repositories.decision_to_approval_repositories import (  # noqa: E501
    PostgresApprovalDecisionRepository,
    PostgresApprovedOrderIntentRepository,
    PostgresEvaluationContextRepository,
    PostgresOperatorTradingConfigurationRepository,
    PostgresTradeProposalRepository,
    _row_to_configuration,
    _row_to_context,
    _row_to_decision,
    _row_to_intent,
    _row_to_proposal,
)
from empirical_platform.usecases.decision_to_approval import (
    DecideTradeProposalCommand,
    DecideTradeProposalHandler,
    GetApprovedOrderIntentHandler,
    GetApprovedOrderIntentQuery,
    GetTradeProposalHandler,
    GetTradeProposalQuery,
    IssueApprovedOrderIntentCommand,
    IssueApprovedOrderIntentHandler,
    ListTradeProposalsHandler,
    ListTradeProposalsQuery,
    NotFoundError,
    OpenEvaluationContextCommand,
    OpenEvaluationContextHandler,
    PrepareTradeProposalCommand,
    PrepareTradeProposalHandler,
    SaveOperatorTradingConfigurationCommand,
    SaveOperatorTradingConfigurationHandler,
)

# ---------------------------------------------------------------------------
# The fake persistence surface
# ---------------------------------------------------------------------------

Script = Callable[[str, Mapping[str, object]], Sequence[Mapping[str, Any]]]


class _FakeUnitOfWork:
    def __init__(self, script: Script, statements: list[str]) -> None:
        self._script = script
        self._statements = statements

    def __enter__(self) -> _FakeUnitOfWork:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def execute(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, Any]]:
        self._statements.append(statement)
        return self._script(statement, parameters or {})


class _FakeService:
    def __init__(self, script: Script) -> None:
        self._script = script
        self.statements: list[str] = []

    def unit_of_work(self) -> _FakeUnitOfWork:
        return _FakeUnitOfWork(self._script, self.statements)


def _rows(*rows: Mapping[str, Any]) -> Script:
    return lambda _statement, _parameters: list(rows)


def _empty() -> Script:
    return lambda _statement, _parameters: []


def configuration_row(**overrides: object) -> dict[str, Any]:
    configuration = a_configuration()
    row: dict[str, Any] = {
        "configuration_governance_id": configuration.configuration_governance_id,
        "configuration_version": configuration.configuration_version,
        "base_currency": configuration.base_currency,
        "permitted_markets": list(configuration.permitted_markets),
        "watchlist": list(configuration.watchlist),
        "prohibited_instruments": list(configuration.prohibited_instruments),
        "maximum_deployable_capital": configuration.maximum_deployable_capital,
        "maximum_capital_per_trade": configuration.maximum_capital_per_trade,
        "maximum_percent_per_trade": configuration.maximum_percent_per_trade,
        "minimum_cash_reserve": configuration.minimum_cash_reserve,
        "maximum_simultaneous_positions": configuration.maximum_simultaneous_positions,
        "maximum_daily_loss": configuration.maximum_daily_loss,
        "maximum_daily_order_count": configuration.maximum_daily_order_count,
        "minimum_price": configuration.minimum_price,
        "maximum_price": configuration.maximum_price,
        "minimum_liquidity_shares": configuration.minimum_liquidity_shares,
        "maximum_spread_percent": configuration.maximum_spread_percent,
        "maximum_estimated_slippage_percent": configuration.maximum_estimated_slippage_percent,
        "maximum_evidence_age_seconds": configuration.maximum_evidence_age_seconds,
        "maximum_market_data_age_seconds": configuration.maximum_market_data_age_seconds,
        "permitted_session": configuration.permitted_session.value,
        "earliest_entry_time": configuration.earliest_entry_time,
        "latest_entry_time": configuration.latest_entry_time,
        "mandatory_liquidation_time": configuration.mandatory_liquidation_time,
        "operator_timezone": configuration.operator_timezone,
        "exchange_calendar_policy": configuration.exchange_calendar_policy,
        "proposal_expiry_seconds": configuration.proposal_expiry_seconds,
        "approval_expiry_seconds": configuration.approval_expiry_seconds,
        "default_order_type": configuration.default_order_type.value,
        "permitted_order_types": [t.value for t in configuration.permitted_order_types],
        "limit_price_policy": configuration.limit_price_policy.value,
        "stop_loss_percent": configuration.stop_loss_percent,
        "profit_exit_percent": configuration.profit_exit_percent,
        "maximum_leverage": configuration.maximum_leverage,
        "short_selling_permitted": configuration.short_selling_permitted,
        "overnight_positions_permitted": configuration.overnight_positions_permitted,
        "account_mode": configuration.account_mode.value,
        "kill_switch": configuration.kill_switch.value,
    }
    row.update(overrides)
    return row


def proposal_row(**overrides: object) -> dict[str, Any]:
    proposal = a_proposal()
    row: dict[str, Any] = {
        "proposal_governance_id": proposal.proposal_governance_id,
        "proposal_version": proposal.proposal_version,
        "evaluation_context_id": proposal.evaluation_context_id,
        "configuration_governance_id": proposal.configuration_governance_id,
        "configuration_version": proposal.configuration_version,
        "symbol": proposal.symbol,
        "side": proposal.side,
        "quantity": proposal.quantity,
        "order_type": proposal.order_type.value,
        "limit_price": proposal.limit_price,
        "currency": proposal.currency,
        "estimated_notional": proposal.estimated_notional,
        "estimated_fees": proposal.estimated_fees,
        "estimated_slippage_amount": proposal.estimated_slippage_amount,
        "estimated_total_cash_required": proposal.estimated_total_cash_required,
        "stop_loss_price": proposal.stop_loss_price,
        "profit_exit_price": proposal.profit_exit_price,
        "mandatory_liquidation_at": proposal.mandatory_liquidation_at,
        "created_at": proposal.created_at,
        "expires_at": proposal.expires_at,
        "status": proposal.status.value,
        "content_fingerprint": proposal.content_fingerprint,
    }
    row.update(overrides)
    return row


def context_row(**overrides: object) -> dict[str, Any]:
    row: dict[str, Any] = {
        "evaluation_context_id": "ECX-0001",
        "configuration_governance_id": "CFG-084-0001",
        "configuration_version": 1,
        "watermark_governance_id": "WM-0001",
        "consumed_receipt_count": 3,
        "consumed_receipt_digest": "a" * 64,
        "quote_id": "QTE-0001",
        "account_snapshot_id": "ACC-0001",
        "session_id": "SES-0001",
        "cost_estimate_id": "CST-0001",
        "research_session_id": None,
        "decision_candidate_id": None,
        "instrument_universe_version": "UNIVERSE-2026-06",
        "strategy_version": "STRATEGY-0001",
        "created_at": EVALUATED_AT,
    }
    row.update(overrides)
    return row


def a_decision(proposal: TradeProposal | None = None, **overrides: object) -> ApprovalDecision:
    decision = record_operator_decision(
        proposal=proposal if proposal is not None else a_proposal(),
        decision_governance_id="DEC-0001",
        action=OperatorAction.APPROVE,
        operator_identity="alice",
        decided_at=EVALUATED_AT + timedelta(seconds=10),
        approval_expiry_seconds=120,
    )
    return replace(decision, **overrides) if overrides else decision


def decision_row(**overrides: object) -> dict[str, Any]:
    decision = a_decision()
    row: dict[str, Any] = {
        "decision_governance_id": decision.decision_governance_id,
        "proposal_governance_id": decision.proposal_governance_id,
        "proposal_version": decision.proposal_version,
        "approved_fingerprint": decision.approved_fingerprint,
        "action": decision.action.value,
        "operator_identity": decision.operator_identity,
        "decided_at": decision.decided_at,
        "expires_at": decision.expires_at,
        "resulting_status": decision.resulting_status.value,
    }
    row.update(overrides)
    return row


def an_intent() -> ApprovedOrderIntent:
    prepared = a_proposal()
    return build_approved_order_intent(
        intent_governance_id="INT-0001",
        proposal=replace(prepared, status=ProposalStatus.APPROVED),
        decision=a_decision(prepared),
        created_at=EVALUATED_AT + timedelta(seconds=20),
        idempotency_key="IDEM-0001",
    )


def intent_row(**overrides: object) -> dict[str, Any]:
    intent = an_intent()
    row: dict[str, Any] = {
        "intent_governance_id": intent.intent_governance_id,
        "proposal_governance_id": intent.proposal_governance_id,
        "proposal_version": intent.proposal_version,
        "approved_fingerprint": intent.approved_fingerprint,
        "decision_governance_id": intent.decision_governance_id,
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": intent.quantity,
        "order_type": intent.order_type.value,
        "limit_price": intent.limit_price,
        "currency": intent.currency,
        "time_in_force": intent.time_in_force,
        "mandatory_liquidation_at": intent.mandatory_liquidation_at,
        "account_mode_required": intent.account_mode_required,
        "idempotency_key": intent.idempotency_key,
        "configuration_governance_id": intent.configuration_governance_id,
        "configuration_version": intent.configuration_version,
        "evaluation_context_id": intent.evaluation_context_id,
        "created_at": intent.created_at,
        "expires_at": intent.expires_at,
        "submission_state": intent.submission_state.value,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Row mapping: nothing is coerced, ever
# ---------------------------------------------------------------------------


class TestRowMappingRefusesRatherThanCoerces:
    def test_a_well_formed_configuration_row_maps_back_to_the_configuration(self) -> None:
        assert _row_to_configuration(configuration_row()) == a_configuration()

    def test_a_well_formed_proposal_row_maps_back_to_the_proposal(self) -> None:
        proposal = a_proposal()
        assert _row_to_proposal(proposal_row(), proposal.risk_checks) == proposal

    def test_a_well_formed_context_row_maps(self) -> None:
        assert _row_to_context(context_row()).consumed_receipt_count == 3

    def test_a_well_formed_decision_row_maps_back_to_the_decision(self) -> None:
        assert _row_to_decision(decision_row()) == a_decision()

    def test_a_well_formed_intent_row_maps_back_to_the_intent(self) -> None:
        assert _row_to_intent(intent_row()) == an_intent()

    @pytest.mark.parametrize(
        ("column", "stored"),
        [
            ("configuration_governance_id", 42),
            ("base_currency", None),
            ("operator_timezone", b"Europe/Helsinki"),
        ],
    )
    def test_a_string_column_holding_something_else_is_refused(
        self, column: str, stored: object
    ) -> None:
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_configuration(configuration_row(**{column: stored}))

    @pytest.mark.parametrize("stored", ["3", 3.0, None, True])
    def test_a_count_column_holding_something_else_is_refused(self, stored: object) -> None:
        # `True` matters: bool is an int subclass, so a boolean would otherwise
        # read as the count 1.
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_context(context_row(consumed_receipt_count=stored))

    @pytest.mark.parametrize("stored", ["2000", 2000.0, None])
    def test_a_money_column_holding_something_else_is_refused(self, stored: object) -> None:
        # A float here would mean a limit the operator never set.
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_configuration(configuration_row(maximum_capital_per_trade=stored))

    def test_an_optional_money_column_may_be_null_but_not_a_string(self) -> None:
        assert _row_to_configuration(configuration_row(maximum_price=None)).maximum_price is None
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_configuration(configuration_row(maximum_price="1000"))

    def test_an_optional_string_column_may_be_null_but_not_a_number(self) -> None:
        assert _row_to_context(context_row(cost_estimate_id=None)).cost_estimate_id is None
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_context(context_row(cost_estimate_id=7))

    @pytest.mark.parametrize("stored", ["2026-06-10T12:00:00+00:00", None, 0])
    def test_an_instant_column_holding_something_else_is_refused(self, stored: object) -> None:
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_context(context_row(created_at=stored))

    def test_a_naive_instant_is_refused(self) -> None:
        # An instant with no zone is an instant this product cannot place.
        with pytest.raises(FoundationError, match="timezone-aware"):
            _row_to_context(context_row(created_at=datetime(2026, 6, 10, 12, 0)))  # noqa: DTZ001

    def test_a_time_column_carrying_a_zone_is_refused(self) -> None:
        with pytest.raises(FoundationError, match="naive datetime.time"):
            _row_to_configuration(configuration_row(earliest_entry_time=time(10, 0, tzinfo=UTC)))

    def test_a_boolean_column_holding_something_else_is_refused(self) -> None:
        with pytest.raises(FoundationError, match="refusing to coerce"):
            _row_to_configuration(configuration_row(short_selling_permitted="false"))

    def test_an_array_column_holding_something_else_is_refused(self) -> None:
        with pytest.raises(FoundationError, match="not array"):
            _row_to_configuration(configuration_row(watchlist="AAPL"))

    def test_an_array_element_of_the_wrong_type_names_its_position(self) -> None:
        with pytest.raises(FoundationError, match=r"watchlist\[1\]"):
            _row_to_configuration(configuration_row(watchlist=["AAPL", 7]))

    @pytest.mark.parametrize(
        ("row_builder", "column", "stored"),
        [
            (proposal_row, "status", "SUBMITTED"),
            (proposal_row, "order_type", "STOP"),
            (decision_row, "action", "AUTO_APPROVE"),
            (intent_row, "submission_state", "SUBMITTED"),
            (configuration_row, "account_mode", "LIVE_TRADING"),
        ],
    )
    def test_a_stored_value_outside_a_closed_enumeration_is_refused(
        self, row_builder: Callable[..., dict[str, Any]], column: str, stored: str
    ) -> None:
        # Not mapped onto a plausible member and not defaulted: an unknown
        # status is not a known one, and guessing is how a REJECTED proposal
        # becomes something else on read.
        mapper = {
            "proposal_row": lambda row: _row_to_proposal(row, a_proposal().risk_checks),
            "decision_row": _row_to_decision,
            "intent_row": _row_to_intent,
            "configuration_row": _row_to_configuration,
        }[row_builder.__name__]
        with pytest.raises(FoundationError, match="not a member of"):
            mapper(row_builder(**{column: stored}))


# ---------------------------------------------------------------------------
# Repository control flow
# ---------------------------------------------------------------------------


class TestConfigurationRepository:
    def test_save_returns_the_row_the_database_returned(self) -> None:
        service = _FakeService(_rows(configuration_row()))
        repository = PostgresOperatorTradingConfigurationRepository(service)  # type: ignore[arg-type]
        assert repository.save(a_configuration()) == a_configuration()
        assert service.statements[0].startswith("INSERT INTO public.operator_trading_configuration")

    def test_get_returns_none_when_no_row_matches(self) -> None:
        repository = PostgresOperatorTradingConfigurationRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        assert repository.get("CFG-NOPE", 1) is None

    def test_get_reads_one_row(self) -> None:
        repository = PostgresOperatorTradingConfigurationRepository(  # type: ignore[arg-type]
            _FakeService(_rows(configuration_row()))
        )
        assert repository.get("CFG-084-0001", 1) == a_configuration()

    def test_latest_orders_by_version_descending(self) -> None:
        service = _FakeService(_rows(configuration_row(configuration_version=3)))
        repository = PostgresOperatorTradingConfigurationRepository(service)  # type: ignore[arg-type]
        latest = repository.latest("CFG-084-0001")
        assert latest is not None
        assert latest.configuration_version == 3
        assert "ORDER BY configuration_version DESC" in service.statements[0]

    def test_latest_returns_none_when_nothing_was_ever_stored(self) -> None:
        repository = PostgresOperatorTradingConfigurationRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        assert repository.latest("CFG-NOPE") is None


class TestEvaluationContextRepository:
    def test_save_returns_the_stored_context(self) -> None:
        service = _FakeService(_rows(context_row()))
        repository = PostgresEvaluationContextRepository(service)  # type: ignore[arg-type]
        stored = repository.save(_row_to_context(context_row()))
        assert stored.watermark_governance_id == "WM-0001"
        assert service.statements[0].startswith("INSERT INTO public.evaluation_context")

    def test_get_returns_none_when_no_row_matches(self) -> None:
        repository = PostgresEvaluationContextRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        assert repository.get("ECX-NOPE") is None

    def test_get_reads_one_row(self) -> None:
        repository = PostgresEvaluationContextRepository(_FakeService(_rows(context_row())))  # type: ignore[arg-type]
        context = repository.get("ECX-0001")
        assert context is not None
        assert context.consumed_receipt_digest == "a" * 64


class TestTradeProposalRepository:
    def test_save_writes_the_proposal_and_then_each_risk_check(self) -> None:
        service = _FakeService(_rows(proposal_row()))
        repository = PostgresTradeProposalRepository(service)  # type: ignore[arg-type]
        proposal = a_proposal()
        stored = repository.save(proposal)

        assert stored == proposal
        assert service.statements[0].startswith("INSERT INTO public.trade_proposal ")
        check_statements = [s for s in service.statements if "trade_proposal_risk_check" in s]
        # One statement per gate, in the same unit of work as the proposal row:
        # a proposal whose checks failed to store would read back as one that
        # passed no gates.
        assert len(check_statements) == len(proposal.risk_checks)

    def test_get_returns_none_when_no_row_matches(self) -> None:
        repository = PostgresTradeProposalRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        assert repository.get("PRP-NOPE") is None

    def test_get_reads_the_proposal_and_its_stored_checks(self) -> None:
        def script(statement: str, _parameters: Mapping[str, object]) -> list[dict[str, Any]]:
            if "trade_proposal_risk_check" in statement:
                return [{"check_id": "kill_switch", "outcome": "PASSED", "detail": "DISENGAGED"}]
            return [proposal_row()]

        repository = PostgresTradeProposalRepository(_FakeService(script))  # type: ignore[arg-type]
        proposal = repository.get("PRP-0001")
        assert proposal is not None
        assert [check.check_id for check in proposal.risk_checks] == ["kill_switch"]

    def test_list_by_status_orders_deterministically(self) -> None:
        def script(statement: str, _parameters: Mapping[str, object]) -> list[dict[str, Any]]:
            if "trade_proposal_risk_check" in statement:
                return [{"check_id": "kill_switch", "outcome": "PASSED", "detail": "DISENGAGED"}]
            return [proposal_row()]

        service = _FakeService(script)
        repository = PostgresTradeProposalRepository(service)  # type: ignore[arg-type]
        listed = repository.list_by_status(ProposalStatus.PREPARED)
        assert len(listed) == 1
        assert 'ORDER BY created_at, proposal_governance_id COLLATE "C"' in service.statements[0]

    def test_set_status_names_only_the_status_column(self) -> None:
        def script(statement: str, _parameters: Mapping[str, object]) -> list[dict[str, Any]]:
            if "trade_proposal_risk_check" in statement:
                return [{"check_id": "kill_switch", "outcome": "PASSED", "detail": "DISENGAGED"}]
            return [proposal_row(status="APPROVED")]

        service = _FakeService(script)
        repository = PostgresTradeProposalRepository(service)  # type: ignore[arg-type]
        moved = repository.set_status("PRP-0001", ProposalStatus.APPROVED)
        assert moved.status is ProposalStatus.APPROVED
        update = service.statements[0]
        assert update.startswith("UPDATE public.trade_proposal SET status = :status ")
        assert " SET " in update and update.count("=") >= 1
        assert "quantity =" not in update

    def test_set_status_on_a_proposal_that_does_not_exist_is_an_error(self) -> None:
        repository = PostgresTradeProposalRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        with pytest.raises(FoundationError, match="no trade proposal"):
            repository.set_status("PRP-NOPE", ProposalStatus.APPROVED)

    def test_a_proposal_whose_stored_checks_vanished_is_refused_rather_than_read(self) -> None:
        # Fail closed. The checks cannot go missing through any path this
        # milestone offers -- they are written in the same unit of work and the
        # table is append-only -- so a proposal that reads back without them
        # means something outside the enforcement boundary touched the row, and
        # reading it as a proposal that passed no gates would be worse than
        # refusing it.
        def script(statement: str, _parameters: Mapping[str, object]) -> list[dict[str, Any]]:
            if "trade_proposal_risk_check" in statement:
                return []
            return [proposal_row()]

        repository = PostgresTradeProposalRepository(_FakeService(script))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="risk_checks must be a non-empty tuple"):
            repository.get("PRP-0001")


class TestDecisionRepository:
    def test_record_returns_the_stored_decision(self) -> None:
        service = _FakeService(_rows(decision_row()))
        repository = PostgresApprovalDecisionRepository(service)  # type: ignore[arg-type]
        assert repository.record(a_decision()) == a_decision()
        assert service.statements[0].startswith("INSERT INTO public.trade_approval_decision")

    def test_get_and_for_proposal_return_none_when_nothing_matches(self) -> None:
        repository = PostgresApprovalDecisionRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        assert repository.get("DEC-NOPE") is None
        assert repository.for_proposal("PRP-NOPE") is None

    def test_get_and_for_proposal_read_one_row(self) -> None:
        repository = PostgresApprovalDecisionRepository(_FakeService(_rows(decision_row())))  # type: ignore[arg-type]
        assert repository.get("DEC-0001") == a_decision()
        assert repository.for_proposal("PRP-0001") == a_decision()


class TestIntentRepository:
    def test_issue_returns_the_stored_intent(self) -> None:
        service = _FakeService(_rows(intent_row()))
        repository = PostgresApprovedOrderIntentRepository(service)  # type: ignore[arg-type]
        assert repository.issue(an_intent()) == an_intent()
        assert service.statements[0].startswith("INSERT INTO public.approved_order_intent")

    def test_no_statement_it_issues_writes_any_other_submission_state(self) -> None:
        # The absent capability, checked rather than assumed: nothing this
        # class emits can put an intent into a submitted state.
        service = _FakeService(_rows(intent_row()))
        repository = PostgresApprovedOrderIntentRepository(service)  # type: ignore[arg-type]
        repository.issue(an_intent())
        repository.get("INT-0001")
        repository.for_proposal("PRP-0001")
        for statement in service.statements:
            assert "UPDATE" not in statement
            assert "DELETE" not in statement
            assert "SUBMITTED'" not in statement.replace("NOT_SUBMITTED'", "")

    def test_get_and_for_proposal_return_none_when_nothing_matches(self) -> None:
        repository = PostgresApprovedOrderIntentRepository(_FakeService(_empty()))  # type: ignore[arg-type]
        assert repository.get("INT-NOPE") is None
        assert repository.for_proposal("PRP-NOPE") is None


# ---------------------------------------------------------------------------
# Handler control flow, over in-memory repositories
# ---------------------------------------------------------------------------


class _MemoryConfigurations:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, int], OperatorTradingConfiguration] = {}

    def save(self, configuration: OperatorTradingConfiguration) -> OperatorTradingConfiguration:
        key = (configuration.configuration_governance_id, configuration.configuration_version)
        self.rows[key] = configuration
        return configuration

    def get(self, gid: str, version: int) -> OperatorTradingConfiguration | None:
        return self.rows.get((gid, version))

    def latest(self, gid: str) -> OperatorTradingConfiguration | None:
        matches = [c for (g, _), c in self.rows.items() if g == gid]
        return max(matches, key=lambda c: c.configuration_version) if matches else None


class _MemoryContexts:
    def __init__(self) -> None:
        self.rows: dict[str, EvaluationContext] = {}

    def save(self, context: EvaluationContext) -> EvaluationContext:
        self.rows[context.evaluation_context_id] = context
        return context

    def get(self, context_id: str) -> EvaluationContext | None:
        return self.rows.get(context_id)


class _MemoryWatermarks:
    def __init__(self, *watermarks: EvaluationEvidenceWatermark) -> None:
        self.rows = {w.watermark_governance_id: w for w in watermarks}

    def capture(self, *, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        return self.rows[watermark_governance_id]

    def get(self, watermark_governance_id: str) -> EvaluationEvidenceWatermark | None:
        return self.rows.get(watermark_governance_id)


class _MemoryProposals:
    def __init__(self) -> None:
        self.rows: dict[str, TradeProposal] = {}

    def save(self, proposal: TradeProposal) -> TradeProposal:
        self.rows[proposal.proposal_governance_id] = proposal
        return proposal

    def get(self, proposal_id: str) -> TradeProposal | None:
        return self.rows.get(proposal_id)

    def list_by_status(self, status: ProposalStatus) -> tuple[TradeProposal, ...]:
        return tuple(p for p in self.rows.values() if p.status is status)

    def counts_by_status(self) -> dict[ProposalStatus, int]:
        counts = dict.fromkeys(ProposalStatus, 0)
        for proposal in self.rows.values():
            counts[proposal.status] += 1
        return counts

    def set_status(self, proposal_id: str, status: ProposalStatus) -> TradeProposal:
        moved = replace(self.rows[proposal_id], status=status)
        self.rows[proposal_id] = moved
        return moved


class _MemoryDecisions:
    def __init__(self) -> None:
        self.rows: dict[str, ApprovalDecision] = {}

    def record(self, decision: ApprovalDecision) -> ApprovalDecision:
        self.rows[decision.decision_governance_id] = decision
        return decision

    def get(self, decision_id: str) -> ApprovalDecision | None:
        return self.rows.get(decision_id)

    def for_proposal(self, proposal_id: str) -> ApprovalDecision | None:
        return next(
            (d for d in self.rows.values() if d.proposal_governance_id == proposal_id), None
        )


class _MemoryIntents:
    def __init__(self) -> None:
        self.rows: dict[str, ApprovedOrderIntent] = {}

    def issue(self, intent: ApprovedOrderIntent) -> ApprovedOrderIntent:
        self.rows[intent.intent_governance_id] = intent
        return intent

    def get(self, intent_id: str) -> ApprovedOrderIntent | None:
        return self.rows.get(intent_id)

    def for_proposal(self, proposal_id: str) -> ApprovedOrderIntent | None:
        return next(
            (i for i in self.rows.values() if i.proposal_governance_id == proposal_id), None
        )


class TestConfigurationHandler:
    def test_the_configuration_is_stored_as_given(self) -> None:
        configurations = _MemoryConfigurations()
        handler = SaveOperatorTradingConfigurationHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        stored = handler.handle(
            SaveOperatorTradingConfigurationCommand(configuration=a_configuration())
        )
        assert stored == a_configuration()
        assert configurations.rows[("CFG-084-0001", 1)] == a_configuration()


class TestOpenEvaluationContextHandler:
    def _handler(
        self, *, watermarks: _MemoryWatermarks, configurations: _MemoryConfigurations
    ) -> tuple[OpenEvaluationContextHandler, _MemoryContexts]:
        contexts = _MemoryContexts()
        return (
            OpenEvaluationContextHandler(
                configuration_repository=configurations,  # type: ignore[arg-type]
                evaluation_context_repository=contexts,  # type: ignore[arg-type]
                evaluation_evidence_watermark_repository=watermarks,  # type: ignore[arg-type]
            ),
            contexts,
        )

    def _command(self, **overrides: object) -> OpenEvaluationContextCommand:
        defaults: dict[str, object] = {
            "evaluation_context_id": "ECX-0001",
            "configuration_governance_id": "CFG-084-0001",
            "configuration_version": 1,
            "watermark_governance_id": "WM-0001",
            "quote_id": "QTE-0001",
            "account_snapshot_id": "ACC-0001",
            "session_id": "SES-0001",
            "cost_estimate_id": "CST-0001",
            "instrument_universe_version": "UNIVERSE-2026-06",
            "strategy_version": "STRATEGY-0001",
            "created_at": EVALUATED_AT,
        }
        defaults.update(overrides)
        return OpenEvaluationContextCommand(**defaults)  # type: ignore[arg-type]

    def test_the_receipt_count_comes_from_the_loaded_watermark(self) -> None:
        watermark = EvaluationEvidenceWatermark(
            watermark_governance_id="WM-0001",
            receipt_governance_ids=("RCPT-0001", "RCPT-0002"),
        )
        configurations = _MemoryConfigurations()
        configurations.save(a_configuration())
        handler, contexts = self._handler(
            watermarks=_MemoryWatermarks(watermark), configurations=configurations
        )
        context = handler.handle(self._command())
        assert context.consumed_receipt_count == 2
        assert contexts.rows["ECX-0001"] is context

    def test_a_watermark_that_was_never_captured_is_refused(self) -> None:
        configurations = _MemoryConfigurations()
        configurations.save(a_configuration())
        handler, _ = self._handler(watermarks=_MemoryWatermarks(), configurations=configurations)
        with pytest.raises(NotFoundError, match="cannot be bound to evidence that does not exist"):
            handler.handle(self._command())

    def test_a_configuration_version_that_does_not_exist_is_refused(self) -> None:
        watermark = EvaluationEvidenceWatermark(
            watermark_governance_id="WM-0001", receipt_governance_ids=()
        )
        handler, _ = self._handler(
            watermarks=_MemoryWatermarks(watermark), configurations=_MemoryConfigurations()
        )
        with pytest.raises(NotFoundError, match="no configuration"):
            handler.handle(self._command())


class TestPrepareTradeProposalHandler:
    def _handler(
        self,
        *,
        contexts: _MemoryContexts,
        proposals: _MemoryProposals,
        configurations: _MemoryConfigurations | None = None,
    ) -> PrepareTradeProposalHandler:
        if configurations is None:
            configurations = _MemoryConfigurations()
            configurations.save(a_configuration())
        return PrepareTradeProposalHandler(
            configuration_repository=configurations,  # type: ignore[arg-type]
            evaluation_context_repository=contexts,  # type: ignore[arg-type]
            trade_proposal_repository=proposals,  # type: ignore[arg-type]
        )

    def _command(self, **overrides: object) -> PrepareTradeProposalCommand:
        defaults: dict[str, object] = {
            "proposal_governance_id": "PRP-0001",
            "evaluation_context_id": "ECX-0001",
            "symbol": "AAPL",
            "evaluated_at": EVALUATED_AT,
            "quote": a_quote(),
            "account": an_account(),
            "session": a_session(),
            "instrument": an_instrument(),
            "liquidity": a_liquidity(),
            "cost_estimate": a_cost_estimate(),
            "positions": (),
            "open_orders": (),
            "evidence_age_seconds": Decimal("60"),
        }
        defaults.update(overrides)
        return PrepareTradeProposalCommand(**defaults)  # type: ignore[arg-type]

    def _contexts(self) -> _MemoryContexts:
        contexts = _MemoryContexts()
        contexts.save(_row_to_context(context_row()))
        return contexts

    def test_a_clean_evaluation_stores_one_proposal(self) -> None:
        proposals = _MemoryProposals()
        handler = self._handler(contexts=self._contexts(), proposals=proposals)
        outcome = handler.handle(self._command())
        assert outcome.proposal is not None
        assert proposals.rows["PRP-0001"] is outcome.proposal

    def test_a_no_trade_stores_nothing(self) -> None:
        # A refusal is a legitimate answer, and a table full of refusals would
        # obscure the few proposals that exist.
        proposals = _MemoryProposals()
        handler = self._handler(contexts=self._contexts(), proposals=proposals)
        outcome = handler.handle(self._command(cost_estimate=None))
        assert outcome.proposal is None
        assert outcome.no_trade_reason is not None
        assert proposals.rows == {}

    def test_an_evaluation_context_that_does_not_exist_is_refused(self) -> None:
        handler = self._handler(contexts=_MemoryContexts(), proposals=_MemoryProposals())
        with pytest.raises(NotFoundError, match="no evaluation context"):
            handler.handle(self._command())

    def test_a_context_citing_a_missing_configuration_version_is_refused(self) -> None:
        """FIND-H5-01. This branch carried `# pragma: no cover`.

        The pragma's reasoning was that a stored context always cites a stored
        configuration version, which the foreign key does guarantee in the
        database. But the handler takes its repositories as parameters, so the
        branch is reachable from here with a repository that returns None --
        which is exactly what a caller composing this handler differently would
        produce. A coverage pragma on a branch a unit test can reach is a
        suppression that was never needed, and it hid a `raise` nobody had run.
        """
        handler = self._handler(
            contexts=self._contexts(),
            proposals=_MemoryProposals(),
            configurations=_MemoryConfigurations(),
        )
        with pytest.raises(NotFoundError, match="which does not exist"):
            handler.handle(self._command())


class TestDecideTradeProposalHandler:
    def _setup(
        self, proposal: TradeProposal | None = None, *, store_configuration: bool = True
    ) -> tuple[DecideTradeProposalHandler, _MemoryProposals, _MemoryDecisions]:
        configurations = _MemoryConfigurations()
        if store_configuration:
            configurations.save(a_configuration())
        proposals = _MemoryProposals()
        proposals.save(proposal if proposal is not None else a_proposal())
        decisions = _MemoryDecisions()
        return (
            DecideTradeProposalHandler(
                configuration_repository=configurations,  # type: ignore[arg-type]
                approval_decision_repository=decisions,  # type: ignore[arg-type]
                trade_proposal_repository=proposals,  # type: ignore[arg-type]
            ),
            proposals,
            decisions,
        )

    def _command(self, **overrides: object) -> DecideTradeProposalCommand:
        defaults: dict[str, object] = {
            "proposal_governance_id": "PRP-0001",
            "decision_governance_id": "DEC-0001",
            "action": OperatorAction.APPROVE,
            "operator_identity": "alice",
            "decided_at": EVALUATED_AT + timedelta(seconds=10),
        }
        defaults.update(overrides)
        return DecideTradeProposalCommand(**defaults)  # type: ignore[arg-type]

    def test_a_proposal_citing_a_missing_configuration_version_is_refused(self) -> None:
        # FIND-H5-01, the second of the two branches that carried a coverage
        # pragma. Reachable here for the same reason as the first: the handler
        # takes its repositories as parameters.
        handler, _, _ = self._setup(store_configuration=False)
        with pytest.raises(NotFoundError, match="cites a configuration version"):
            handler.handle(self._command())

    def test_an_approval_records_the_decision_and_then_moves_the_proposal(self) -> None:
        handler, proposals, decisions = self._setup()
        outcome = handler.handle(self._command())
        assert outcome.decision.operator_identity == "alice"
        assert outcome.proposal.status is ProposalStatus.APPROVED
        assert proposals.rows["PRP-0001"].status is ProposalStatus.APPROVED
        assert decisions.rows["DEC-0001"].approved_fingerprint == a_proposal().content_fingerprint

    @pytest.mark.parametrize(
        ("action", "status"),
        [
            (OperatorAction.REJECT, ProposalStatus.REJECTED),
            (OperatorAction.CANCEL, ProposalStatus.CANCELLED),
        ],
    )
    def test_a_refusal_moves_the_proposal_to_its_own_terminal_state(
        self, action: OperatorAction, status: ProposalStatus
    ) -> None:
        handler, proposals, _ = self._setup()
        handler.handle(self._command(action=action))
        assert proposals.rows["PRP-0001"].status is status

    def test_an_unnamed_operator_is_refused_before_anything_is_written(self) -> None:
        with pytest.raises(ValueError, match="must name the person who decided"):
            self._command(operator_identity="   ")

    def test_a_proposal_that_does_not_exist_is_refused(self) -> None:
        handler, _, _ = self._setup()
        with pytest.raises(NotFoundError, match="no trade proposal"):
            handler.handle(self._command(proposal_governance_id="PRP-NOPE"))


class TestIssueApprovedOrderIntentHandler:
    def _setup(self) -> tuple[IssueApprovedOrderIntentHandler, _MemoryIntents, _MemoryDecisions]:
        prepared = a_proposal()
        proposals = _MemoryProposals()
        proposals.save(replace(prepared, status=ProposalStatus.APPROVED))
        decisions = _MemoryDecisions()
        decisions.record(a_decision(prepared))
        intents = _MemoryIntents()
        return (
            IssueApprovedOrderIntentHandler(
                approval_decision_repository=decisions,  # type: ignore[arg-type]
                approved_order_intent_repository=intents,  # type: ignore[arg-type]
                trade_proposal_repository=proposals,  # type: ignore[arg-type]
            ),
            intents,
            decisions,
        )

    def _command(self, **overrides: object) -> IssueApprovedOrderIntentCommand:
        defaults: dict[str, object] = {
            "intent_governance_id": "INT-0001",
            "proposal_governance_id": "PRP-0001",
            "idempotency_key": "IDEM-0001",
            "created_at": EVALUATED_AT + timedelta(seconds=20),
        }
        defaults.update(overrides)
        return IssueApprovedOrderIntentCommand(**defaults)  # type: ignore[arg-type]

    def test_an_approved_proposal_yields_one_never_submitted_intent(self) -> None:
        handler, intents, _ = self._setup()
        intent = handler.handle(self._command())
        assert intent.submission_state.value == "NOT_SUBMITTED"
        assert intents.rows["INT-0001"] is intent

    def test_a_proposal_with_no_recorded_decision_is_refused(self) -> None:
        prepared = a_proposal()
        proposals = _MemoryProposals()
        proposals.save(replace(prepared, status=ProposalStatus.APPROVED))
        handler = IssueApprovedOrderIntentHandler(
            approval_decision_repository=_MemoryDecisions(),  # type: ignore[arg-type]
            approved_order_intent_repository=_MemoryIntents(),  # type: ignore[arg-type]
            trade_proposal_repository=proposals,  # type: ignore[arg-type]
        )
        with pytest.raises(NotFoundError, match="never the absence of a rejection"):
            handler.handle(self._command())

    def test_a_proposal_that_does_not_exist_is_refused(self) -> None:
        handler, _, _ = self._setup()
        with pytest.raises(NotFoundError, match="no trade proposal"):
            handler.handle(self._command(proposal_governance_id="PRP-NOPE"))


class TestQueryHandlers:
    def test_getting_a_proposal_that_exists(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        handler = GetTradeProposalHandler(trade_proposal_repository=proposals)  # type: ignore[arg-type]
        assert handler.handle(GetTradeProposalQuery("PRP-0001")) == a_proposal()

    def test_getting_a_proposal_that_does_not_exist_is_an_explicit_refusal(self) -> None:
        handler = GetTradeProposalHandler(trade_proposal_repository=_MemoryProposals())  # type: ignore[arg-type]
        with pytest.raises(NotFoundError, match="no trade proposal"):
            handler.handle(GetTradeProposalQuery("PRP-NOPE"))

    def test_listing_filters_by_status(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        handler = ListTradeProposalsHandler(trade_proposal_repository=proposals)  # type: ignore[arg-type]
        assert len(handler.handle(ListTradeProposalsQuery(ProposalStatus.PREPARED))) == 1
        assert handler.handle(ListTradeProposalsQuery(ProposalStatus.APPROVED)) == ()

    def test_getting_an_intent_that_exists(self) -> None:
        intents = _MemoryIntents()
        intents.issue(an_intent())
        handler = GetApprovedOrderIntentHandler(approved_order_intent_repository=intents)  # type: ignore[arg-type]
        assert handler.handle(GetApprovedOrderIntentQuery("INT-0001")) == an_intent()

    def test_getting_an_intent_that_does_not_exist_is_an_explicit_refusal(self) -> None:
        handler = GetApprovedOrderIntentHandler(approved_order_intent_repository=_MemoryIntents())  # type: ignore[arg-type]
        with pytest.raises(NotFoundError, match="no approved order intent"):
            handler.handle(GetApprovedOrderIntentQuery("INT-NOPE"))
