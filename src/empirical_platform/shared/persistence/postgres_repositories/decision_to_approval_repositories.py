"""MILESTONE-084 persistence for the decision-to-approval product core.

FIVE REPOSITORIES, ONE MODULE. They share one row-reading discipline and one
set of fail-closed converters, and every one of them exists to serve a single
five-step flow. Splitting them across five files would duplicate the
converters or force a sixth shared module, which is how the discipline drifts.

FAIL CLOSED ON READ, THE MILESTONE-083 AUD-001 LESSON. Nothing here coerces a
persisted value into the type it should have been. A stored value of the wrong
type is a signal that something outside this milestone's enforcement boundary
wrote the row -- `ALTER TABLE ... DISABLE TRIGGER`, DDL authority, a superuser
-- and reading it back is exactly where that should be noticed, not papered
over with `str(value)` or `int(value)`.

THE DATABASE IS THE SECOND OPINION, NOT THE ONLY ONE. Every rule these classes
rely on is also a constraint or trigger in migration a3f7c21d9b04. Neither
layer is decoration: the domain refusal is the legible one a developer meets
first, and the database refusal is the one that still applies to a psql
session that never imported this file.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from empirical_platform.decision_candidate.evaluation_context import EvaluationContext
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
    OperatorAction,
    SubmissionState,
)
from empirical_platform.decision_candidate.trade_proposal import (
    ProposalStatus,
    RiskCheck,
    RiskCheckOutcome,
    TradeProposal,
)
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = [
    "PostgresApprovalDecisionRepository",
    "PostgresApprovedOrderIntentRepository",
    "PostgresEvaluationContextRepository",
    "PostgresOperatorTradingConfigurationRepository",
    "PostgresTradeProposalRepository",
]

_OPERATION = "m084.row_mapping"


def _fail(field: str, value: object, expected: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted MILESTONE-084 value {field} is {type(value).__name__}, not {expected}; "
            "refusing to coerce a malformed stored value"
        ),
        layer="persistence",
        operation=_OPERATION,
        context={"field": field, "actual_type": type(value).__name__},
    )


def _str(row: Mapping[str, Any], field: str) -> str:
    value = row[field]
    if not isinstance(value, str):
        raise _fail(field, value, "str")
    return value


def _optional_str(row: Mapping[str, Any], field: str) -> str | None:
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise _fail(field, value, "str or NULL")
    return value


def _int(row: Mapping[str, Any], field: str) -> int:
    value = row[field]
    # bool is an int subclass; a boolean in a count column is a malformed row,
    # so it is refused before the int check rather than passing through it.
    if isinstance(value, bool):
        raise _fail(field, value, "int")
    if not isinstance(value, int):
        raise _fail(field, value, "int")
    return value


def _bool(row: Mapping[str, Any], field: str) -> bool:
    value = row[field]
    if not isinstance(value, bool):
        raise _fail(field, value, "bool")
    return value


def _decimal(row: Mapping[str, Any], field: str) -> Decimal:
    value = row[field]
    if not isinstance(value, Decimal):
        raise _fail(field, value, "Decimal")
    return value


def _optional_decimal(row: Mapping[str, Any], field: str) -> Decimal | None:
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise _fail(field, value, "Decimal or NULL")
    return value


def _instant(row: Mapping[str, Any], field: str) -> datetime:
    value = row[field]
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _fail(field, value, "timezone-aware datetime")
    return value


def _optional_instant(row: Mapping[str, Any], field: str) -> datetime | None:
    if row[field] is None:
        return None
    return _instant(row, field)


def _time(row: Mapping[str, Any], field: str) -> time:
    value = row[field]
    if not isinstance(value, time) or value.tzinfo is not None:
        raise _fail(field, value, "naive datetime.time")
    return value


def _strings(row: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = row[field]
    if not isinstance(value, list | tuple):
        raise _fail(field, value, "array")
    for position, element in enumerate(value):
        if not isinstance(element, str):
            raise _fail(f"{field}[{position}]", element, "str")
    return tuple(value)


def _member[EnumT: StrEnum](row: Mapping[str, Any], field: str, enum: type[EnumT]) -> EnumT:
    """Read a closed enumeration, refusing any value outside it.

    A stored value the enum does not name is not mapped to a default or to
    None: an unknown status is not a known one, and guessing which known one it
    meant is how a REJECTED proposal becomes something else on read.
    """
    raw = _str(row, field)
    try:
        return enum(raw)
    except ValueError as error:
        raise FoundationError(
            category=FoundationErrorCategory.PERSISTENCE,
            message=(
                f"persisted MILESTONE-084 value {field} is {raw!r}, which is not a "
                f"member of {enum.__name__}; refusing to map it onto a known member"
            ),
            layer="persistence",
            operation=_OPERATION,
            context={"field": field, "stored_value": raw, "enum": enum.__name__},
        ) from error


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _configuration_parameters(configuration: OperatorTradingConfiguration) -> dict[str, Any]:
    return {
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
        "permitted_order_types": [order.value for order in configuration.permitted_order_types],
        "limit_price_policy": configuration.limit_price_policy.value,
        "stop_loss_percent": configuration.stop_loss_percent,
        "profit_exit_percent": configuration.profit_exit_percent,
        "maximum_leverage": configuration.maximum_leverage,
        "short_selling_permitted": configuration.short_selling_permitted,
        "overnight_positions_permitted": configuration.overnight_positions_permitted,
        "account_mode": configuration.account_mode.value,
        "kill_switch": configuration.kill_switch.value,
    }


def _row_to_configuration(row: Mapping[str, Any]) -> OperatorTradingConfiguration:
    return OperatorTradingConfiguration(
        configuration_governance_id=_str(row, "configuration_governance_id"),
        configuration_version=_int(row, "configuration_version"),
        base_currency=_str(row, "base_currency"),
        permitted_markets=_strings(row, "permitted_markets"),
        watchlist=_strings(row, "watchlist"),
        prohibited_instruments=_strings(row, "prohibited_instruments"),
        maximum_deployable_capital=_decimal(row, "maximum_deployable_capital"),
        maximum_capital_per_trade=_decimal(row, "maximum_capital_per_trade"),
        maximum_percent_per_trade=_decimal(row, "maximum_percent_per_trade"),
        minimum_cash_reserve=_decimal(row, "minimum_cash_reserve"),
        maximum_simultaneous_positions=_int(row, "maximum_simultaneous_positions"),
        maximum_daily_loss=_decimal(row, "maximum_daily_loss"),
        maximum_daily_order_count=_int(row, "maximum_daily_order_count"),
        minimum_price=_decimal(row, "minimum_price"),
        maximum_price=_optional_decimal(row, "maximum_price"),
        minimum_liquidity_shares=_int(row, "minimum_liquidity_shares"),
        maximum_spread_percent=_decimal(row, "maximum_spread_percent"),
        maximum_estimated_slippage_percent=_decimal(row, "maximum_estimated_slippage_percent"),
        maximum_evidence_age_seconds=_int(row, "maximum_evidence_age_seconds"),
        maximum_market_data_age_seconds=_int(row, "maximum_market_data_age_seconds"),
        permitted_session=_member(row, "permitted_session", TradingSession),
        earliest_entry_time=_time(row, "earliest_entry_time"),
        latest_entry_time=_time(row, "latest_entry_time"),
        mandatory_liquidation_time=_time(row, "mandatory_liquidation_time"),
        operator_timezone=_str(row, "operator_timezone"),
        exchange_calendar_policy=_str(row, "exchange_calendar_policy"),
        proposal_expiry_seconds=_int(row, "proposal_expiry_seconds"),
        approval_expiry_seconds=_int(row, "approval_expiry_seconds"),
        default_order_type=_member(row, "default_order_type", OrderType),
        permitted_order_types=tuple(
            OrderType(value) for value in _strings(row, "permitted_order_types")
        ),
        limit_price_policy=_member(row, "limit_price_policy", LimitPricePolicy),
        stop_loss_percent=_decimal(row, "stop_loss_percent"),
        profit_exit_percent=_decimal(row, "profit_exit_percent"),
        maximum_leverage=_decimal(row, "maximum_leverage"),
        short_selling_permitted=_bool(row, "short_selling_permitted"),
        overnight_positions_permitted=_bool(row, "overnight_positions_permitted"),
        account_mode=_member(row, "account_mode", AccountMode),
        kill_switch=_member(row, "kill_switch", KillSwitchState),
    )


class PostgresOperatorTradingConfigurationRepository:
    """Append-only store of versioned operator policy."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, configuration: OperatorTradingConfiguration) -> OperatorTradingConfiguration:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "INSERT INTO public.operator_trading_configuration (configuration_governance_id, "
                "configuration_version, base_currency, permitted_markets, watchlist, "
                "prohibited_instruments, maximum_deployable_capital, maximum_capital_per_trade, "
                "maximum_percent_per_trade, minimum_cash_reserve, maximum_simultaneous_positions, "
                "maximum_daily_loss, maximum_daily_order_count, minimum_price, maximum_price, "
                "minimum_liquidity_shares, maximum_spread_percent, "
                "maximum_estimated_slippage_percent, maximum_evidence_age_seconds, "
                "maximum_market_data_age_seconds, permitted_session, earliest_entry_time, "
                "latest_entry_time, mandatory_liquidation_time, operator_timezone, "
                "exchange_calendar_policy, proposal_expiry_seconds, approval_expiry_seconds, "
                "default_order_type, permitted_order_types, limit_price_policy, stop_loss_percent, "
                "profit_exit_percent, maximum_leverage, short_selling_permitted, "
                "overnight_positions_permitted, account_mode, kill_switch) VALUES "
                "(:configuration_governance_id, :configuration_version, :base_currency, "
                ":permitted_markets, :watchlist, :prohibited_instruments, "
                ":maximum_deployable_capital, :maximum_capital_per_trade, "
                ":maximum_percent_per_trade, :minimum_cash_reserve, "
                ":maximum_simultaneous_positions, :maximum_daily_loss, :maximum_daily_order_count, "
                ":minimum_price, :maximum_price, :minimum_liquidity_shares, "
                ":maximum_spread_percent, :maximum_estimated_slippage_percent, "
                ":maximum_evidence_age_seconds, :maximum_market_data_age_seconds, "
                ":permitted_session, :earliest_entry_time, :latest_entry_time, "
                ":mandatory_liquidation_time, :operator_timezone, :exchange_calendar_policy, "
                ":proposal_expiry_seconds, :approval_expiry_seconds, :default_order_type, "
                ":permitted_order_types, :limit_price_policy, :stop_loss_percent, "
                ":profit_exit_percent, :maximum_leverage, :short_selling_permitted, "
                ":overnight_positions_permitted, :account_mode, :kill_switch) RETURNING "
                "configuration_governance_id, configuration_version, base_currency, "
                "permitted_markets, watchlist, prohibited_instruments, maximum_deployable_capital, "
                "maximum_capital_per_trade, maximum_percent_per_trade, minimum_cash_reserve, "
                "maximum_simultaneous_positions, maximum_daily_loss, maximum_daily_order_count, "
                "minimum_price, maximum_price, minimum_liquidity_shares, maximum_spread_percent, "
                "maximum_estimated_slippage_percent, maximum_evidence_age_seconds, "
                "maximum_market_data_age_seconds, permitted_session, earliest_entry_time, "
                "latest_entry_time, mandatory_liquidation_time, operator_timezone, "
                "exchange_calendar_policy, proposal_expiry_seconds, approval_expiry_seconds, "
                "default_order_type, permitted_order_types, limit_price_policy, stop_loss_percent, "
                "profit_exit_percent, maximum_leverage, short_selling_permitted, "
                "overnight_positions_permitted, account_mode, kill_switch",
                _configuration_parameters(configuration),
            )
        return _row_to_configuration(rows[0])

    def get(
        self, configuration_governance_id: str, configuration_version: int
    ) -> OperatorTradingConfiguration | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT configuration_governance_id, configuration_version, base_currency, "
                    "permitted_markets, watchlist, prohibited_instruments, "
                    "maximum_deployable_capital, maximum_capital_per_trade, "
                    "maximum_percent_per_trade, minimum_cash_reserve, "
                    "maximum_simultaneous_positions, maximum_daily_loss, maximum_daily_order_count,"
                    " minimum_price, maximum_price, minimum_liquidity_shares, "
                    "maximum_spread_percent, maximum_estimated_slippage_percent, "
                    "maximum_evidence_age_seconds, maximum_market_data_age_seconds, "
                    "permitted_session, earliest_entry_time, latest_entry_time, "
                    "mandatory_liquidation_time, operator_timezone, exchange_calendar_policy, "
                    "proposal_expiry_seconds, approval_expiry_seconds, default_order_type, "
                    "permitted_order_types, limit_price_policy, stop_loss_percent, "
                    "profit_exit_percent, maximum_leverage, short_selling_permitted, "
                    "overnight_positions_permitted, account_mode, kill_switch FROM "
                    "public.operator_trading_configuration "
                    "WHERE configuration_governance_id = :gid AND configuration_version = :ver",
                    {"gid": configuration_governance_id, "ver": configuration_version},
                )
            )
        return _row_to_configuration(rows[0]) if rows else None

    def latest(self, configuration_governance_id: str) -> OperatorTradingConfiguration | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT configuration_governance_id, configuration_version, base_currency, "
                    "permitted_markets, watchlist, prohibited_instruments, "
                    "maximum_deployable_capital, maximum_capital_per_trade, "
                    "maximum_percent_per_trade, minimum_cash_reserve, "
                    "maximum_simultaneous_positions, maximum_daily_loss, maximum_daily_order_count,"
                    " minimum_price, maximum_price, minimum_liquidity_shares, "
                    "maximum_spread_percent, maximum_estimated_slippage_percent, "
                    "maximum_evidence_age_seconds, maximum_market_data_age_seconds, "
                    "permitted_session, earliest_entry_time, latest_entry_time, "
                    "mandatory_liquidation_time, operator_timezone, exchange_calendar_policy, "
                    "proposal_expiry_seconds, approval_expiry_seconds, default_order_type, "
                    "permitted_order_types, limit_price_policy, stop_loss_percent, "
                    "profit_exit_percent, maximum_leverage, short_selling_permitted, "
                    "overnight_positions_permitted, account_mode, kill_switch FROM "
                    "public.operator_trading_configuration "
                    "WHERE configuration_governance_id = :gid "
                    "ORDER BY configuration_version DESC LIMIT 1",
                    {"gid": configuration_governance_id},
                )
            )
        return _row_to_configuration(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------


def _row_to_context(row: Mapping[str, Any]) -> EvaluationContext:
    return EvaluationContext(
        evaluation_context_id=_str(row, "evaluation_context_id"),
        configuration_governance_id=_str(row, "configuration_governance_id"),
        configuration_version=_int(row, "configuration_version"),
        watermark_governance_id=_str(row, "watermark_governance_id"),
        consumed_receipt_count=_int(row, "consumed_receipt_count"),
        consumed_receipt_digest=_str(row, "consumed_receipt_digest"),
        quote_id=_str(row, "quote_id"),
        account_snapshot_id=_str(row, "account_snapshot_id"),
        session_id=_str(row, "session_id"),
        cost_estimate_id=_optional_str(row, "cost_estimate_id"),
        research_session_id=_optional_str(row, "research_session_id"),
        decision_candidate_id=_optional_str(row, "decision_candidate_id"),
        instrument_universe_version=_str(row, "instrument_universe_version"),
        strategy_version=_str(row, "strategy_version"),
        created_at=_instant(row, "created_at"),
    )


class PostgresEvaluationContextRepository:
    """Append-only store of what one evaluation consumed."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, context: EvaluationContext) -> EvaluationContext:
        parameters = {
            "evaluation_context_id": context.evaluation_context_id,
            "configuration_governance_id": context.configuration_governance_id,
            "configuration_version": context.configuration_version,
            "watermark_governance_id": context.watermark_governance_id,
            "consumed_receipt_count": context.consumed_receipt_count,
            "consumed_receipt_digest": context.consumed_receipt_digest,
            "quote_id": context.quote_id,
            "account_snapshot_id": context.account_snapshot_id,
            "session_id": context.session_id,
            "cost_estimate_id": context.cost_estimate_id,
            "research_session_id": context.research_session_id,
            "decision_candidate_id": context.decision_candidate_id,
            "instrument_universe_version": context.instrument_universe_version,
            "strategy_version": context.strategy_version,
            "created_at": context.created_at,
        }
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "INSERT INTO public.evaluation_context (evaluation_context_id, "
                "configuration_governance_id, configuration_version, watermark_governance_id, "
                "consumed_receipt_count, consumed_receipt_digest, quote_id, account_snapshot_id, "
                "session_id, cost_estimate_id, research_session_id, decision_candidate_id, "
                "instrument_universe_version, strategy_version, created_at) VALUES "
                "(:evaluation_context_id, :configuration_governance_id, :configuration_version, "
                ":watermark_governance_id, :consumed_receipt_count, :consumed_receipt_digest, "
                ":quote_id, :account_snapshot_id, :session_id, :cost_estimate_id, "
                ":research_session_id, :decision_candidate_id, :instrument_universe_version, "
                ":strategy_version, :created_at) RETURNING evaluation_context_id, "
                "configuration_governance_id, configuration_version, watermark_governance_id, "
                "consumed_receipt_count, consumed_receipt_digest, quote_id, account_snapshot_id, "
                "session_id, cost_estimate_id, research_session_id, decision_candidate_id, "
                "instrument_universe_version, strategy_version, created_at",
                parameters,
            )
        return _row_to_context(rows[0])

    def get(self, evaluation_context_id: str) -> EvaluationContext | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT evaluation_context_id, configuration_governance_id, "
                    "configuration_version, watermark_governance_id, consumed_receipt_count, "
                    "consumed_receipt_digest, quote_id, account_snapshot_id, session_id, "
                    "cost_estimate_id, research_session_id, decision_candidate_id, "
                    "instrument_universe_version, strategy_version, created_at FROM "
                    "public.evaluation_context "
                    "WHERE evaluation_context_id = :cid",
                    {"cid": evaluation_context_id},
                )
            )
        return _row_to_context(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------


def _row_to_proposal(row: Mapping[str, Any], risk_checks: tuple[RiskCheck, ...]) -> TradeProposal:
    """Rebuild one proposal.

    `risk_checks` is supplied by the caller rather than read from a column:
    the checks are diagnostic output of the evaluation, deliberately excluded
    from the fingerprint and from the schema, so a re-read proposal carries the
    checks its reader has or none at all -- never invented ones.
    """
    return TradeProposal(
        proposal_governance_id=_str(row, "proposal_governance_id"),
        proposal_version=_int(row, "proposal_version"),
        evaluation_context_id=_str(row, "evaluation_context_id"),
        configuration_governance_id=_str(row, "configuration_governance_id"),
        configuration_version=_int(row, "configuration_version"),
        symbol=_str(row, "symbol"),
        side=_str(row, "side"),
        quantity=_int(row, "quantity"),
        order_type=_member(row, "order_type", OrderType),
        limit_price=_optional_decimal(row, "limit_price"),
        currency=_str(row, "currency"),
        estimated_notional=_decimal(row, "estimated_notional"),
        estimated_fees=_decimal(row, "estimated_fees"),
        estimated_slippage_amount=_decimal(row, "estimated_slippage_amount"),
        estimated_total_cash_required=_decimal(row, "estimated_total_cash_required"),
        stop_loss_price=_decimal(row, "stop_loss_price"),
        profit_exit_price=_decimal(row, "profit_exit_price"),
        mandatory_liquidation_at=_instant(row, "mandatory_liquidation_at"),
        created_at=_instant(row, "created_at"),
        expires_at=_instant(row, "expires_at"),
        status=_member(row, "status", ProposalStatus),
        content_fingerprint=_str(row, "content_fingerprint"),
        risk_checks=risk_checks,
    )


class PostgresTradeProposalRepository:
    """Append-only store of proposals whose only mutable field is `status`."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, proposal: TradeProposal) -> TradeProposal:
        parameters = {
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
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "INSERT INTO public.trade_proposal (proposal_governance_id, proposal_version, "
                "evaluation_context_id, configuration_governance_id, configuration_version, symbol,"
                " side, quantity, order_type, limit_price, currency, estimated_notional, "
                "estimated_fees, estimated_slippage_amount, estimated_total_cash_required, "
                "stop_loss_price, profit_exit_price, mandatory_liquidation_at, created_at, "
                "expires_at, status, content_fingerprint) VALUES (:proposal_governance_id, "
                ":proposal_version, :evaluation_context_id, :configuration_governance_id, "
                ":configuration_version, :symbol, :side, :quantity, :order_type, :limit_price, "
                ":currency, :estimated_notional, :estimated_fees, :estimated_slippage_amount, "
                ":estimated_total_cash_required, :stop_loss_price, :profit_exit_price, "
                ":mandatory_liquidation_at, :created_at, :expires_at, :status, "
                ":content_fingerprint) RETURNING proposal_governance_id, proposal_version, "
                "evaluation_context_id, configuration_governance_id, configuration_version, symbol,"
                " side, quantity, order_type, limit_price, currency, estimated_notional, "
                "estimated_fees, estimated_slippage_amount, estimated_total_cash_required, "
                "stop_loss_price, profit_exit_price, mandatory_liquidation_at, created_at, "
                "expires_at, status, content_fingerprint",
                parameters,
            )
            # Same unit of work as the proposal row: a proposal whose checks
            # failed to store would read back as one that passed no gates.
            for ordinal, check in enumerate(proposal.risk_checks):
                work.execute(
                    "INSERT INTO public.trade_proposal_risk_check "
                    "(proposal_governance_id, check_id, ordinal, outcome, detail) "
                    "VALUES (:pid, :check_id, :ordinal, :outcome, :detail)",
                    {
                        "pid": proposal.proposal_governance_id,
                        "check_id": check.check_id,
                        "ordinal": ordinal,
                        "outcome": check.outcome.value,
                        "detail": check.detail,
                    },
                )
        return _row_to_proposal(rows[0], proposal.risk_checks)

    def _risk_checks(self, proposal_governance_id: str) -> tuple[RiskCheck, ...]:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT check_id, outcome, detail FROM public.trade_proposal_risk_check "
                    "WHERE proposal_governance_id = :pid ORDER BY ordinal",
                    {"pid": proposal_governance_id},
                )
            )
        return tuple(
            RiskCheck(
                check_id=_str(row, "check_id"),
                outcome=_member(row, "outcome", RiskCheckOutcome),
                detail=_str(row, "detail"),
            )
            for row in rows
        )

    def get(self, proposal_governance_id: str) -> TradeProposal | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT proposal_governance_id, proposal_version, evaluation_context_id, "
                    "configuration_governance_id, configuration_version, symbol, side, quantity, "
                    "order_type, limit_price, currency, estimated_notional, estimated_fees, "
                    "estimated_slippage_amount, estimated_total_cash_required, stop_loss_price, "
                    "profit_exit_price, mandatory_liquidation_at, created_at, expires_at, status, "
                    "content_fingerprint FROM public.trade_proposal "
                    "WHERE proposal_governance_id = :pid",
                    {"pid": proposal_governance_id},
                )
            )
        if not rows:
            return None
        return _row_to_proposal(rows[0], self._risk_checks(proposal_governance_id))

    def list_by_status(self, status: ProposalStatus) -> tuple[TradeProposal, ...]:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT proposal_governance_id, proposal_version, evaluation_context_id, "
                    "configuration_governance_id, configuration_version, symbol, side, quantity, "
                    "order_type, limit_price, currency, estimated_notional, estimated_fees, "
                    "estimated_slippage_amount, estimated_total_cash_required, stop_loss_price, "
                    "profit_exit_price, mandatory_liquidation_at, created_at, expires_at, status, "
                    "content_fingerprint FROM public.trade_proposal "
                    "WHERE status = :status "
                    'ORDER BY created_at, proposal_governance_id COLLATE "C"',
                    {"status": status.value},
                )
            )
        return tuple(
            _row_to_proposal(row, self._risk_checks(_str(row, "proposal_governance_id")))
            for row in rows
        )

    def counts_by_status(self) -> Mapping[ProposalStatus, int]:
        """How many proposals sit in each status.

        Every member of the enumeration appears in the result, including the
        ones with no rows: a status summary that silently omitted the empty
        statuses would read as though those states did not exist.
        """
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT status, count(*) AS row_count FROM public.trade_proposal "
                    "GROUP BY status",
                    {},
                )
            )
        counts = dict.fromkeys(ProposalStatus, 0)
        for row in rows:
            counts[_member(row, "status", ProposalStatus)] = _int(row, "row_count")
        return counts

    def set_status(self, proposal_governance_id: str, status: ProposalStatus) -> TradeProposal:
        """Move one proposal along the transition table.

        The UPDATE names only `status`. The database's own guard would refuse a
        statement that touched anything else; naming one column here means no
        such statement is ever generated in the first place.
        """
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "UPDATE public.trade_proposal SET status = :status "
                "WHERE proposal_governance_id = :pid RETURNING proposal_governance_id, "
                "proposal_version, evaluation_context_id, configuration_governance_id, "
                "configuration_version, symbol, side, quantity, order_type, limit_price, currency, "
                "estimated_notional, estimated_fees, estimated_slippage_amount, "
                "estimated_total_cash_required, stop_loss_price, profit_exit_price, "
                "mandatory_liquidation_at, created_at, expires_at, status, content_fingerprint",
                {"status": status.value, "pid": proposal_governance_id},
            )
        if not rows:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message=f"no trade proposal with governance id {proposal_governance_id!r}",
                layer="persistence",
                operation="m084.trade_proposal.set_status",
                context={"proposal_governance_id": proposal_governance_id},
            )
        return _row_to_proposal(rows[0], self._risk_checks(proposal_governance_id))


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


def _row_to_decision(row: Mapping[str, Any]) -> ApprovalDecision:
    return ApprovalDecision(
        decision_governance_id=_str(row, "decision_governance_id"),
        proposal_governance_id=_str(row, "proposal_governance_id"),
        proposal_version=_int(row, "proposal_version"),
        approved_fingerprint=_str(row, "approved_fingerprint"),
        action=_member(row, "action", OperatorAction),
        operator_identity=_str(row, "operator_identity"),
        decided_at=_instant(row, "decided_at"),
        expires_at=_optional_instant(row, "expires_at"),
        resulting_status=_member(row, "resulting_status", ProposalStatus),
    )


class PostgresApprovalDecisionRepository:
    """Append-only store of explicit human decisions."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def record(self, decision: ApprovalDecision) -> ApprovalDecision:
        parameters = {
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
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "INSERT INTO public.trade_approval_decision (decision_governance_id, "
                "proposal_governance_id, proposal_version, approved_fingerprint, action, "
                "operator_identity, decided_at, expires_at, resulting_status) VALUES "
                "(:decision_governance_id, :proposal_governance_id, :proposal_version, "
                ":approved_fingerprint, :action, :operator_identity, :decided_at, :expires_at, "
                ":resulting_status) RETURNING decision_governance_id, proposal_governance_id, "
                "proposal_version, approved_fingerprint, action, operator_identity, decided_at, "
                "expires_at, resulting_status",
                parameters,
            )
        return _row_to_decision(rows[0])

    def get(self, decision_governance_id: str) -> ApprovalDecision | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT decision_governance_id, proposal_governance_id, proposal_version, "
                    "approved_fingerprint, action, operator_identity, decided_at, expires_at, "
                    "resulting_status FROM public.trade_approval_decision "
                    "WHERE decision_governance_id = :did",
                    {"did": decision_governance_id},
                )
            )
        return _row_to_decision(rows[0]) if rows else None

    def for_proposal(self, proposal_governance_id: str) -> ApprovalDecision | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT decision_governance_id, proposal_governance_id, proposal_version, "
                    "approved_fingerprint, action, operator_identity, decided_at, expires_at, "
                    "resulting_status FROM public.trade_approval_decision "
                    "WHERE proposal_governance_id = :pid",
                    {"pid": proposal_governance_id},
                )
            )
        return _row_to_decision(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


def _row_to_intent(row: Mapping[str, Any]) -> ApprovedOrderIntent:
    return ApprovedOrderIntent(
        intent_governance_id=_str(row, "intent_governance_id"),
        proposal_governance_id=_str(row, "proposal_governance_id"),
        proposal_version=_int(row, "proposal_version"),
        approved_fingerprint=_str(row, "approved_fingerprint"),
        decision_governance_id=_str(row, "decision_governance_id"),
        symbol=_str(row, "symbol"),
        side=_str(row, "side"),
        quantity=_int(row, "quantity"),
        order_type=_member(row, "order_type", OrderType),
        limit_price=_optional_decimal(row, "limit_price"),
        currency=_str(row, "currency"),
        time_in_force=_str(row, "time_in_force"),
        mandatory_liquidation_at=_instant(row, "mandatory_liquidation_at"),
        account_mode_required=_str(row, "account_mode_required"),
        idempotency_key=_str(row, "idempotency_key"),
        configuration_governance_id=_str(row, "configuration_governance_id"),
        configuration_version=_int(row, "configuration_version"),
        evaluation_context_id=_str(row, "evaluation_context_id"),
        created_at=_instant(row, "created_at"),
        expires_at=_instant(row, "expires_at"),
        submission_state=_member(row, "submission_state", SubmissionState),
    )


class PostgresApprovedOrderIntentRepository:
    """Append-only store of broker-neutral, never-submitted order intents.

    There is no `submit`, `send`, `mark_submitted` or `set_submission_state`
    method, and no SQL here writes `submission_state` to anything but the
    NOT_SUBMITTED the intent already carries.
    """

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def issue(self, intent: ApprovedOrderIntent) -> ApprovedOrderIntent:
        parameters = {
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
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "INSERT INTO public.approved_order_intent (intent_governance_id, "
                "proposal_governance_id, proposal_version, approved_fingerprint, "
                "decision_governance_id, symbol, side, quantity, order_type, limit_price, currency,"
                " time_in_force, mandatory_liquidation_at, account_mode_required, idempotency_key, "
                "configuration_governance_id, configuration_version, evaluation_context_id, "
                "created_at, expires_at, submission_state) VALUES (:intent_governance_id, "
                ":proposal_governance_id, :proposal_version, :approved_fingerprint, "
                ":decision_governance_id, :symbol, :side, :quantity, :order_type, :limit_price, "
                ":currency, :time_in_force, :mandatory_liquidation_at, :account_mode_required, "
                ":idempotency_key, :configuration_governance_id, :configuration_version, "
                ":evaluation_context_id, :created_at, :expires_at, :submission_state) RETURNING "
                "intent_governance_id, proposal_governance_id, proposal_version, "
                "approved_fingerprint, decision_governance_id, symbol, side, quantity, order_type, "
                "limit_price, currency, time_in_force, mandatory_liquidation_at, "
                "account_mode_required, idempotency_key, configuration_governance_id, "
                "configuration_version, evaluation_context_id, "
                "created_at, expires_at, submission_state",
                parameters,
            )
        return _row_to_intent(rows[0])

    def get(self, intent_governance_id: str) -> ApprovedOrderIntent | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT intent_governance_id, proposal_governance_id, proposal_version, "
                    "approved_fingerprint, decision_governance_id, symbol, side, quantity, "
                    "order_type, limit_price, currency, time_in_force, mandatory_liquidation_at, "
                    "account_mode_required, idempotency_key, configuration_governance_id, "
                    "configuration_version, evaluation_context_id, created_at, expires_at, "
                    "submission_state FROM public.approved_order_intent "
                    "WHERE intent_governance_id = :iid",
                    {"iid": intent_governance_id},
                )
            )
        return _row_to_intent(rows[0]) if rows else None

    def for_proposal(self, proposal_governance_id: str) -> ApprovedOrderIntent | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT intent_governance_id, proposal_governance_id, proposal_version, "
                    "approved_fingerprint, decision_governance_id, symbol, side, quantity, "
                    "order_type, limit_price, currency, time_in_force, mandatory_liquidation_at, "
                    "account_mode_required, idempotency_key, configuration_governance_id, "
                    "configuration_version, evaluation_context_id, created_at, expires_at, "
                    "submission_state FROM public.approved_order_intent "
                    "WHERE proposal_governance_id = :pid",
                    {"pid": proposal_governance_id},
                )
            )
        return _row_to_intent(rows[0]) if rows else None
