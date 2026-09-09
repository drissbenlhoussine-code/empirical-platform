"""MILESTONE-084 -- reading operator-asserted input and rendering results.

PARSING IS REFUSAL, NOT REPAIR. Every reader below raises on a missing key, an
unexpected type, or a value outside a closed enumeration. Nothing is defaulted,
coerced or filled in. A configuration file with a typo in `account_mode` is a
file whose author does not yet know what they configured, and quietly reading
it as PREPARATION would hide exactly that.

MONEY IS READ FROM STRINGS. `Decimal(str)` and never `Decimal(float)`: JSON has
no decimal type, so a price written as `200.10` in a file arrives in Python as
the float 200.10000000000000142..., and building a limit price from that would
mean the order terms a human approved were never quite the ones they typed. The
readers therefore require a JSON string for every amount and refuse a JSON
number, rather than accepting one and rounding it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
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
from empirical_platform.decision_candidate.product_market_inputs import (
    AccountSnapshot,
    DataFeedKind,
    InstrumentMetadata,
    LiquiditySnapshot,
    MarketStatus,
    OpenOrderSnapshot,
    PositionSnapshot,
    QuoteSnapshot,
    SessionSnapshot,
    TradingCostEstimate,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
)
from empirical_platform.decision_candidate.trade_proposal import (
    TradeProposal,
    TradeProposalOutcome,
)
from empirical_platform.usecases.decision_to_approval import (
    AuditHistory,
    InvalidationOutcome,
    OpenEvaluationContextCommand,
    SystemStatus,
)

__all__ = [
    "InputError",
    "MarketInputs",
    "load_json_file",
    "read_configuration",
    "read_context_request",
    "read_market_inputs",
    "render_audit_history_json",
    "render_audit_history_text",
    "render_configuration_json",
    "render_configuration_text",
    "render_context_json",
    "render_context_text",
    "render_decision_json",
    "render_decision_text",
    "render_intent_json",
    "render_intent_text",
    "render_invalidation_json",
    "render_invalidation_text",
    "render_money",
    "render_no_trade_explanation_json",
    "render_no_trade_explanation_text",
    "render_outcome_json",
    "render_outcome_text",
    "render_proposal_json",
    "render_proposal_text",
    "render_system_status_json",
    "render_system_status_text",
]


class InputError(ValueError):
    """Raised when operator-supplied input cannot be read as written."""


def _object(document: object, *, where: str) -> Mapping[str, Any]:
    if not isinstance(document, dict):
        raise InputError(f"{where} must be a JSON object")
    return document


def _text(document: Mapping[str, Any], key: str, *, where: str) -> str:
    if key not in document:
        raise InputError(f"{where} is missing {key!r}")
    value = document[key]
    if not isinstance(value, str):
        raise InputError(f"{where}.{key} must be a string, not {type(value).__name__}")
    return value


def _optional_text(document: Mapping[str, Any], key: str, *, where: str) -> str | None:
    if document.get(key) is None:
        return None
    return _text(document, key, where=where)


def _whole(document: Mapping[str, Any], key: str, *, where: str) -> int:
    if key not in document:
        raise InputError(f"{where} is missing {key!r}")
    value = document[key]
    # JSON has one number type, so `true` would otherwise read as 1 here.
    if isinstance(value, bool):
        raise InputError(f"{where}.{key} must be a whole number, not a boolean")
    if not isinstance(value, int):
        raise InputError(f"{where}.{key} must be a whole number, not {type(value).__name__}")
    return value


def _flag(document: Mapping[str, Any], key: str, *, where: str) -> bool:
    if key not in document:
        raise InputError(f"{where} is missing {key!r}")
    value = document[key]
    if not isinstance(value, bool):
        raise InputError(f"{where}.{key} must be true or false")
    return value


def _amount(document: Mapping[str, Any], key: str, *, where: str) -> Decimal:
    """Read one amount, from a string only. See the module docstring."""
    if key not in document:
        raise InputError(f"{where} is missing {key!r}")
    value = document[key]
    if isinstance(value, float | int) and not isinstance(value, bool):
        raise InputError(
            f'{where}.{key} must be a quoted string such as "200.10", not a JSON number: '
            "a JSON number is a float, and money read through a float is no longer the "
            "amount that was written"
        )
    if not isinstance(value, str):
        raise InputError(f"{where}.{key} must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise InputError(f"{where}.{key} is not a decimal number: {value!r}") from error
    if not amount.is_finite():
        raise InputError(f"{where}.{key} must be finite")
    return amount


def _optional_amount(document: Mapping[str, Any], key: str, *, where: str) -> Decimal | None:
    if document.get(key) is None:
        return None
    return _amount(document, key, where=where)


def _instant(document: Mapping[str, Any], key: str, *, where: str) -> datetime:
    raw = _text(document, key, where=where)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"{where}.{key} is not an ISO-8601 instant: {raw!r}") from error
    if parsed.tzinfo is None:
        raise InputError(
            f"{where}.{key} must carry a UTC offset: an instant without one is ambiguous, "
            "and this product refuses to guess which clock it came from"
        )
    return parsed


def _clock(document: Mapping[str, Any], key: str, *, where: str) -> time:
    raw = _text(document, key, where=where)
    try:
        parsed = time.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"{where}.{key} is not an ISO-8601 time: {raw!r}") from error
    if parsed.tzinfo is not None:
        raise InputError(
            f"{where}.{key} must be a local time with no offset; it is interpreted in "
            "operator_timezone"
        )
    return parsed


def _choice[EnumT: StrEnum](
    document: Mapping[str, Any], key: str, enum: type[EnumT], *, where: str
) -> EnumT:
    raw = _text(document, key, where=where)
    try:
        return enum(raw)
    except ValueError as error:
        permitted = ", ".join(sorted(member.value for member in enum))
        raise InputError(f"{where}.{key} must be one of {permitted}; got {raw!r}") from error


def _words(document: Mapping[str, Any], key: str, *, where: str) -> tuple[str, ...]:
    if key not in document:
        raise InputError(f"{where} is missing {key!r}")
    value = document[key]
    if not isinstance(value, list):
        raise InputError(f"{where}.{key} must be a JSON array of strings")
    for element in value:
        if not isinstance(element, str):
            raise InputError(f"{where}.{key} must contain only strings")
    return tuple(value)


def read_configuration(document: object) -> OperatorTradingConfiguration:
    """Read one operator configuration from a parsed JSON document.

    Every rule the configuration type enforces still applies: this function
    reads the file, and the type refuses a policy this product will not hold.
    """
    where = "configuration"
    body = _object(document, where=where)
    return OperatorTradingConfiguration(
        configuration_governance_id=_text(body, "configuration_governance_id", where=where),
        configuration_version=_whole(body, "configuration_version", where=where),
        base_currency=_text(body, "base_currency", where=where),
        permitted_markets=_words(body, "permitted_markets", where=where),
        watchlist=_words(body, "watchlist", where=where),
        prohibited_instruments=_words(body, "prohibited_instruments", where=where),
        maximum_deployable_capital=_amount(body, "maximum_deployable_capital", where=where),
        maximum_capital_per_trade=_amount(body, "maximum_capital_per_trade", where=where),
        maximum_percent_per_trade=_amount(body, "maximum_percent_per_trade", where=where),
        minimum_cash_reserve=_amount(body, "minimum_cash_reserve", where=where),
        maximum_simultaneous_positions=_whole(body, "maximum_simultaneous_positions", where=where),
        maximum_daily_loss=_amount(body, "maximum_daily_loss", where=where),
        maximum_daily_order_count=_whole(body, "maximum_daily_order_count", where=where),
        minimum_price=_amount(body, "minimum_price", where=where),
        maximum_price=_optional_amount(body, "maximum_price", where=where),
        minimum_liquidity_shares=_whole(body, "minimum_liquidity_shares", where=where),
        maximum_spread_percent=_amount(body, "maximum_spread_percent", where=where),
        maximum_estimated_slippage_percent=_amount(
            body, "maximum_estimated_slippage_percent", where=where
        ),
        maximum_evidence_age_seconds=_whole(body, "maximum_evidence_age_seconds", where=where),
        maximum_market_data_age_seconds=_whole(
            body, "maximum_market_data_age_seconds", where=where
        ),
        permitted_session=_choice(body, "permitted_session", TradingSession, where=where),
        earliest_entry_time=_clock(body, "earliest_entry_time", where=where),
        latest_entry_time=_clock(body, "latest_entry_time", where=where),
        mandatory_liquidation_time=_clock(body, "mandatory_liquidation_time", where=where),
        operator_timezone=_text(body, "operator_timezone", where=where),
        exchange_calendar_policy=_text(body, "exchange_calendar_policy", where=where),
        proposal_expiry_seconds=_whole(body, "proposal_expiry_seconds", where=where),
        approval_expiry_seconds=_whole(body, "approval_expiry_seconds", where=where),
        default_order_type=_choice(body, "default_order_type", OrderType, where=where),
        permitted_order_types=tuple(
            OrderType(value) for value in _words(body, "permitted_order_types", where=where)
        ),
        limit_price_policy=_choice(body, "limit_price_policy", LimitPricePolicy, where=where),
        stop_loss_percent=_amount(body, "stop_loss_percent", where=where),
        profit_exit_percent=_amount(body, "profit_exit_percent", where=where),
        maximum_leverage=_amount(body, "maximum_leverage", where=where),
        short_selling_permitted=_flag(body, "short_selling_permitted", where=where),
        overnight_positions_permitted=_flag(body, "overnight_positions_permitted", where=where),
        account_mode=_choice(body, "account_mode", AccountMode, where=where),
        kill_switch=_choice(body, "kill_switch", KillSwitchState, where=where),
    )


def read_context_request(document: object) -> OpenEvaluationContextCommand:
    """Read one evaluation-context request from a parsed JSON document.

    A file rather than a dozen command-line arguments: the identities being
    bound here are the whole point of the record, and a reviewer reading the
    file afterwards can see exactly what was bound to what.
    """
    where = "context"
    body = _object(document, where=where)
    return OpenEvaluationContextCommand(
        evaluation_context_id=_text(body, "evaluation_context_id", where=where),
        configuration_governance_id=_text(body, "configuration_governance_id", where=where),
        configuration_version=_whole(body, "configuration_version", where=where),
        watermark_governance_id=_text(body, "watermark_governance_id", where=where),
        quote_id=_text(body, "quote_id", where=where),
        account_snapshot_id=_text(body, "account_snapshot_id", where=where),
        session_id=_text(body, "session_id", where=where),
        cost_estimate_id=_optional_text(body, "cost_estimate_id", where=where),
        instrument_universe_version=_text(body, "instrument_universe_version", where=where),
        strategy_version=_text(body, "strategy_version", where=where),
        created_at=_instant(body, "created_at", where=where),
        research_session_id=_optional_text(body, "research_session_id", where=where),
        decision_candidate_id=_optional_text(body, "decision_candidate_id", where=where),
    )


class MarketInputs:
    """One set of operator-asserted observations for one evaluation.

    A plain container, not a domain type: each field below is already a
    validated domain snapshot, and this only holds them together so one CLI
    argument can carry the whole set.
    """

    __slots__ = (
        "account",
        "cost_estimate",
        "evidence_age_seconds",
        "instrument",
        "liquidity",
        "open_orders",
        "positions",
        "quote",
        "session",
    )

    def __init__(
        self,
        *,
        quote: QuoteSnapshot,
        account: AccountSnapshot,
        session: SessionSnapshot,
        instrument: InstrumentMetadata,
        liquidity: LiquiditySnapshot,
        cost_estimate: TradingCostEstimate | None,
        positions: tuple[PositionSnapshot, ...],
        open_orders: tuple[OpenOrderSnapshot, ...],
        evidence_age_seconds: Decimal,
    ) -> None:
        self.quote = quote
        self.account = account
        self.session = session
        self.instrument = instrument
        self.liquidity = liquidity
        self.cost_estimate = cost_estimate
        self.positions = positions
        self.open_orders = open_orders
        self.evidence_age_seconds = evidence_age_seconds


def _child(body: Mapping[str, Any], key: str, *, where: str) -> Mapping[str, Any]:
    if key not in body:
        raise InputError(f"{where} is missing {key!r}")
    return _object(body[key], where=f"{where}.{key}")


def read_market_inputs(document: object) -> MarketInputs:
    """Read one operator-asserted observation set from a parsed JSON document."""
    where = "inputs"
    body = _object(document, where=where)

    quote_body = _child(body, "quote", where=where)
    account_body = _child(body, "account", where=where)
    session_body = _child(body, "session", where=where)
    instrument_body = _child(body, "instrument", where=where)
    liquidity_body = _child(body, "liquidity", where=where)

    cost_estimate: TradingCostEstimate | None = None
    if body.get("cost_estimate") is not None:
        cost_body = _child(body, "cost_estimate", where=where)
        cost_estimate = TradingCostEstimate(
            estimate_id=_text(cost_body, "estimate_id", where="inputs.cost_estimate"),
            provider_id=_text(cost_body, "provider_id", where="inputs.cost_estimate"),
            symbol=_text(cost_body, "symbol", where="inputs.cost_estimate"),
            commission=_amount(cost_body, "commission", where="inputs.cost_estimate"),
            estimated_slippage_percent=_amount(
                cost_body, "estimated_slippage_percent", where="inputs.cost_estimate"
            ),
            observed_at=_instant(cost_body, "observed_at", where="inputs.cost_estimate"),
        )

    positions = tuple(
        PositionSnapshot(
            symbol=_text(_object(entry, where="inputs.positions[]"), "symbol", where="position"),
            quantity=_whole(
                _object(entry, where="inputs.positions[]"), "quantity", where="position"
            ),
            average_price=_amount(
                _object(entry, where="inputs.positions[]"), "average_price", where="position"
            ),
        )
        for entry in _sequence(body, "positions", where=where)
    )
    open_orders = tuple(
        OpenOrderSnapshot(
            order_reference=_text(
                _object(entry, where="inputs.open_orders[]"), "order_reference", where="order"
            ),
            symbol=_text(_object(entry, where="inputs.open_orders[]"), "symbol", where="order"),
            side=_text(_object(entry, where="inputs.open_orders[]"), "side", where="order"),
            quantity=_whole(
                _object(entry, where="inputs.open_orders[]"), "quantity", where="order"
            ),
        )
        for entry in _sequence(body, "open_orders", where=where)
    )

    return MarketInputs(
        quote=QuoteSnapshot(
            quote_id=_text(quote_body, "quote_id", where="inputs.quote"),
            provider_id=_text(quote_body, "provider_id", where="inputs.quote"),
            symbol=_text(quote_body, "symbol", where="inputs.quote"),
            bid=_amount(quote_body, "bid", where="inputs.quote"),
            ask=_amount(quote_body, "ask", where="inputs.quote"),
            last_trade=_amount(quote_body, "last_trade", where="inputs.quote"),
            observed_at=_instant(quote_body, "observed_at", where="inputs.quote"),
            feed_kind=_choice(quote_body, "feed_kind", DataFeedKind, where="inputs.quote"),
        ),
        account=AccountSnapshot(
            account_snapshot_id=_text(account_body, "account_snapshot_id", where="inputs.account"),
            provider_id=_text(account_body, "provider_id", where="inputs.account"),
            account_reference=_text(account_body, "account_reference", where="inputs.account"),
            base_currency=_text(account_body, "base_currency", where="inputs.account"),
            cash_available=_amount(account_body, "cash_available", where="inputs.account"),
            equity_total=_amount(account_body, "equity_total", where="inputs.account"),
            realized_pnl_today=_amount(account_body, "realized_pnl_today", where="inputs.account"),
            orders_submitted_today=_whole(
                account_body, "orders_submitted_today", where="inputs.account"
            ),
            observed_at=_instant(account_body, "observed_at", where="inputs.account"),
        ),
        session=SessionSnapshot(
            session_id=_text(session_body, "session_id", where="inputs.session"),
            provider_id=_text(session_body, "provider_id", where="inputs.session"),
            market=_text(session_body, "market", where="inputs.session"),
            status=_choice(session_body, "status", MarketStatus, where="inputs.session"),
            observed_at=_instant(session_body, "observed_at", where="inputs.session"),
        ),
        instrument=InstrumentMetadata(
            symbol=_text(instrument_body, "symbol", where="inputs.instrument"),
            market=_text(instrument_body, "market", where="inputs.instrument"),
            currency=_text(instrument_body, "currency", where="inputs.instrument"),
            is_fractionable=_flag(instrument_body, "is_fractionable", where="inputs.instrument"),
            lot_size=_whole(instrument_body, "lot_size", where="inputs.instrument"),
        ),
        liquidity=LiquiditySnapshot(
            symbol=_text(liquidity_body, "symbol", where="inputs.liquidity"),
            average_daily_volume_shares=_whole(
                liquidity_body, "average_daily_volume_shares", where="inputs.liquidity"
            ),
            observed_at=_instant(liquidity_body, "observed_at", where="inputs.liquidity"),
        ),
        cost_estimate=cost_estimate,
        positions=positions,
        open_orders=open_orders,
        evidence_age_seconds=_amount(body, "evidence_age_seconds", where=where),
    )


def _sequence(body: Mapping[str, Any], key: str, *, where: str) -> list[Any]:
    value = body.get(key, [])
    if not isinstance(value, list):
        raise InputError(f"{where}.{key} must be a JSON array")
    return value


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_money(value: Decimal) -> str:
    """Render one amount for a human, in whole cents where it fits.

    Deliberately NOT the same rule as the fingerprint's. The digest normalizes
    so that `200.10` and the `200.10000000` a NUMERIC(20,8) column returns hash
    identically; a person reading a price wants `200.10`, not `200.1`. Sub-cent
    precision is preserved rather than rounded away -- an amount that does not
    fit in cents is shown in full instead of being quietly made to look like it
    does.
    """
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    if isinstance(exponent, int) and exponent > -2:
        normalized = normalized.quantize(Decimal("0.01"))
    return format(normalized, "f")


def _money(value: Decimal | None) -> str | None:
    return None if value is None else render_money(value)


def render_proposal_json(proposal: TradeProposal) -> dict[str, Any]:
    return {
        "proposal_governance_id": proposal.proposal_governance_id,
        "proposal_version": proposal.proposal_version,
        "evaluation_context_id": proposal.evaluation_context_id,
        "configuration_governance_id": proposal.configuration_governance_id,
        "configuration_version": proposal.configuration_version,
        "symbol": proposal.symbol,
        "side": proposal.side,
        "quantity": proposal.quantity,
        "order_type": proposal.order_type.value,
        "limit_price": _money(proposal.limit_price),
        "currency": proposal.currency,
        "estimated_notional": _money(proposal.estimated_notional),
        "estimated_fees": _money(proposal.estimated_fees),
        "estimated_slippage_amount": _money(proposal.estimated_slippage_amount),
        "estimated_total_cash_required": _money(proposal.estimated_total_cash_required),
        "stop_loss_price": _money(proposal.stop_loss_price),
        "profit_exit_price": _money(proposal.profit_exit_price),
        "mandatory_liquidation_at": proposal.mandatory_liquidation_at.isoformat(),
        "created_at": proposal.created_at.isoformat(),
        "expires_at": proposal.expires_at.isoformat(),
        "status": proposal.status.value,
        "content_fingerprint": proposal.content_fingerprint,
        "risk_checks": [
            {"check_id": check.check_id, "outcome": check.outcome.value, "detail": check.detail}
            for check in proposal.risk_checks
        ],
    }


def render_proposal_text(proposal: TradeProposal) -> str:
    price = "market" if proposal.limit_price is None else f"limit {_money(proposal.limit_price)}"
    lines = [
        f"proposal {proposal.proposal_governance_id} v{proposal.proposal_version} "
        f"[{proposal.status.value}]",
        f"  {proposal.side} {proposal.quantity} {proposal.symbol} @ {price} "
        f"({proposal.order_type.value})",
        f"  notional {_money(proposal.estimated_notional)} {proposal.currency}"
        f"  fees {_money(proposal.estimated_fees)}"
        f"  slippage {_money(proposal.estimated_slippage_amount)}",
        f"  total cash required {_money(proposal.estimated_total_cash_required)} "
        f"{proposal.currency}",
        f"  stop {_money(proposal.stop_loss_price)}  target {_money(proposal.profit_exit_price)}",
        f"  liquidate by {proposal.mandatory_liquidation_at.isoformat()}",
        f"  expires {proposal.expires_at.isoformat()}",
        f"  fingerprint {proposal.content_fingerprint}",
        f"  context {proposal.evaluation_context_id}",
        f"  configuration {proposal.configuration_governance_id} v{proposal.configuration_version}",
        f"  risk checks passed: {len(proposal.risk_checks)}",
    ]
    return "\n".join(lines) + "\n"


def render_outcome_json(outcome: TradeProposalOutcome) -> dict[str, Any]:
    return {
        "decision": "PROPOSAL" if outcome.proposal is not None else "NO_TRADE",
        "no_trade_reason": (
            None if outcome.no_trade_reason is None else outcome.no_trade_reason.value
        ),
        "proposal": (None if outcome.proposal is None else render_proposal_json(outcome.proposal)),
        "risk_checks": [
            {"check_id": check.check_id, "outcome": check.outcome.value, "detail": check.detail}
            for check in outcome.risk_checks
        ],
    }


def render_outcome_text(outcome: TradeProposalOutcome) -> str:
    if outcome.proposal is not None:
        return render_proposal_text(outcome.proposal)
    assert outcome.no_trade_reason is not None
    lines = [f"NO_TRADE: {outcome.no_trade_reason.value}", "  checks:"]
    lines.extend(
        f"    {check.outcome.value:<8} {check.check_id}: {check.detail}"
        for check in outcome.risk_checks
        if check.outcome.value != "PASSED"
    )
    return "\n".join(lines) + "\n"


def render_context_json(context: EvaluationContext) -> dict[str, Any]:
    return {
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
        "created_at": context.created_at.isoformat(),
    }


def render_context_text(context: EvaluationContext) -> str:
    return (
        f"evaluation context {context.evaluation_context_id}\n"
        f"  configuration {context.configuration_governance_id} "
        f"v{context.configuration_version}\n"
        f"  watermark {context.watermark_governance_id} "
        f"({context.consumed_receipt_count} receipts)\n"
        f"  receipt set digest {context.consumed_receipt_digest}\n"
        f"  quote {context.quote_id}  account {context.account_snapshot_id}  "
        f"session {context.session_id}\n"
        f"  created {context.created_at.isoformat()}\n"
    )


def render_decision_json(decision: ApprovalDecision) -> dict[str, Any]:
    return {
        "decision_governance_id": decision.decision_governance_id,
        "proposal_governance_id": decision.proposal_governance_id,
        "proposal_version": decision.proposal_version,
        "approved_fingerprint": decision.approved_fingerprint,
        "action": decision.action.value,
        "operator_identity": decision.operator_identity,
        "decided_at": decision.decided_at.isoformat(),
        "expires_at": None if decision.expires_at is None else decision.expires_at.isoformat(),
        "resulting_status": decision.resulting_status.value,
    }


def render_decision_text(decision: ApprovalDecision) -> str:
    expiry = (
        "does not lapse"
        if decision.expires_at is None
        else f"lapses {decision.expires_at.isoformat()}"
    )
    return (
        f"decision {decision.decision_governance_id}: {decision.action.value} "
        f"-> {decision.resulting_status.value}\n"
        f"  proposal {decision.proposal_governance_id} v{decision.proposal_version}\n"
        f"  by {decision.operator_identity} at {decision.decided_at.isoformat()}\n"
        f"  approved fingerprint {decision.approved_fingerprint}\n"
        f"  {expiry}\n"
    )


def render_intent_json(intent: ApprovedOrderIntent) -> dict[str, Any]:
    return {
        "intent_governance_id": intent.intent_governance_id,
        "proposal_governance_id": intent.proposal_governance_id,
        "proposal_version": intent.proposal_version,
        "approved_fingerprint": intent.approved_fingerprint,
        "decision_governance_id": intent.decision_governance_id,
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": intent.quantity,
        "order_type": intent.order_type.value,
        "limit_price": _money(intent.limit_price),
        "currency": intent.currency,
        "time_in_force": intent.time_in_force,
        "mandatory_liquidation_at": intent.mandatory_liquidation_at.isoformat(),
        "account_mode_required": intent.account_mode_required,
        "idempotency_key": intent.idempotency_key,
        "configuration_governance_id": intent.configuration_governance_id,
        "configuration_version": intent.configuration_version,
        "evaluation_context_id": intent.evaluation_context_id,
        "created_at": intent.created_at.isoformat(),
        "expires_at": intent.expires_at.isoformat(),
        "submission_state": intent.submission_state.value,
    }


def render_intent_text(intent: ApprovedOrderIntent) -> str:
    price = "market" if intent.limit_price is None else f"limit {_money(intent.limit_price)}"
    return (
        f"order intent {intent.intent_governance_id} [{intent.submission_state.value}]\n"
        f"  {intent.side} {intent.quantity} {intent.symbol} @ {price} "
        f"({intent.order_type.value}, {intent.time_in_force})\n"
        f"  requires account mode {intent.account_mode_required}\n"
        f"  from proposal {intent.proposal_governance_id} v{intent.proposal_version} "
        f"approved by decision {intent.decision_governance_id}\n"
        f"  liquidate by {intent.mandatory_liquidation_at.isoformat()}\n"
        f"  expires {intent.expires_at.isoformat()}\n"
        f"  idempotency key {intent.idempotency_key}\n"
        "  NOT SUBMITTED. MILESTONE-084 provides no way to send this to a broker.\n"
    )


def load_json_file(path: str) -> object:
    """Read one JSON document from a file, refusing anything unparseable."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise InputError(f"{path} is not valid JSON: {error}") from error


def render_configuration_json(configuration: OperatorTradingConfiguration) -> dict[str, Any]:
    """The stored policy, in the same shape `read_configuration` accepts.

    Round-trippable on purpose: an operator who wants to change one limit
    should be able to write this out, edit it, bump the version and store it
    back, rather than reconstruct the file from documentation.
    """
    return {
        "configuration_governance_id": configuration.configuration_governance_id,
        "configuration_version": configuration.configuration_version,
        "base_currency": configuration.base_currency,
        "permitted_markets": list(configuration.permitted_markets),
        "watchlist": list(configuration.watchlist),
        "prohibited_instruments": list(configuration.prohibited_instruments),
        "maximum_deployable_capital": render_money(configuration.maximum_deployable_capital),
        "maximum_capital_per_trade": render_money(configuration.maximum_capital_per_trade),
        "maximum_percent_per_trade": render_money(configuration.maximum_percent_per_trade),
        "minimum_cash_reserve": render_money(configuration.minimum_cash_reserve),
        "maximum_simultaneous_positions": configuration.maximum_simultaneous_positions,
        "maximum_daily_loss": render_money(configuration.maximum_daily_loss),
        "maximum_daily_order_count": configuration.maximum_daily_order_count,
        "minimum_price": render_money(configuration.minimum_price),
        "maximum_price": _money(configuration.maximum_price),
        "minimum_liquidity_shares": configuration.minimum_liquidity_shares,
        "maximum_spread_percent": render_money(configuration.maximum_spread_percent),
        "maximum_estimated_slippage_percent": render_money(
            configuration.maximum_estimated_slippage_percent
        ),
        "maximum_evidence_age_seconds": configuration.maximum_evidence_age_seconds,
        "maximum_market_data_age_seconds": configuration.maximum_market_data_age_seconds,
        "permitted_session": configuration.permitted_session.value,
        "earliest_entry_time": configuration.earliest_entry_time.isoformat(),
        "latest_entry_time": configuration.latest_entry_time.isoformat(),
        "mandatory_liquidation_time": configuration.mandatory_liquidation_time.isoformat(),
        "operator_timezone": configuration.operator_timezone,
        "exchange_calendar_policy": configuration.exchange_calendar_policy,
        "proposal_expiry_seconds": configuration.proposal_expiry_seconds,
        "approval_expiry_seconds": configuration.approval_expiry_seconds,
        "default_order_type": configuration.default_order_type.value,
        "permitted_order_types": [t.value for t in configuration.permitted_order_types],
        "limit_price_policy": configuration.limit_price_policy.value,
        "stop_loss_percent": render_money(configuration.stop_loss_percent),
        "profit_exit_percent": render_money(configuration.profit_exit_percent),
        "maximum_leverage": render_money(configuration.maximum_leverage),
        "short_selling_permitted": configuration.short_selling_permitted,
        "overnight_positions_permitted": configuration.overnight_positions_permitted,
        "account_mode": configuration.account_mode.value,
        "kill_switch": configuration.kill_switch.value,
    }


def render_configuration_text(configuration: OperatorTradingConfiguration) -> str:
    trading = "PERMITTED" if configuration.is_trading_permitted else "STOPPED (kill switch)"
    return (
        f"configuration {configuration.configuration_governance_id} "
        f"v{configuration.configuration_version}\n"
        f"  account mode {configuration.account_mode.value}   kill switch "
        f"{configuration.kill_switch.value}   -> {trading}\n"
        f"  long-only, unleveraged, intraday: short_selling="
        f"{configuration.short_selling_permitted} overnight="
        f"{configuration.overnight_positions_permitted} "
        f"leverage={render_money(configuration.maximum_leverage)}\n"
        f"  currency {configuration.base_currency}   markets "
        f"{', '.join(configuration.permitted_markets)}\n"
        f"  watchlist {', '.join(configuration.watchlist)}\n"
        f"  prohibited {', '.join(configuration.prohibited_instruments) or '(none)'}\n"
        f"  capital {render_money(configuration.maximum_deployable_capital)} "
        f"per-trade {render_money(configuration.maximum_capital_per_trade)} "
        f"({render_money(configuration.maximum_percent_per_trade)}%) "
        f"reserve {render_money(configuration.minimum_cash_reserve)}\n"
        f"  daily loss limit {render_money(configuration.maximum_daily_loss)}   "
        f"daily order limit {configuration.maximum_daily_order_count}   "
        f"max positions {configuration.maximum_simultaneous_positions}\n"
        f"  session {configuration.permitted_session.value} "
        f"{configuration.earliest_entry_time.isoformat()}-"
        f"{configuration.latest_entry_time.isoformat()} "
        f"liquidate {configuration.mandatory_liquidation_time.isoformat()} "
        f"({configuration.operator_timezone})\n"
        f"  proposal expiry {configuration.proposal_expiry_seconds}s   "
        f"approval expiry {configuration.approval_expiry_seconds}s\n"
        f"  order {configuration.default_order_type.value} "
        f"({configuration.limit_price_policy.value})   "
        f"stop {render_money(configuration.stop_loss_percent)}%   "
        f"target {render_money(configuration.profit_exit_percent)}%\n"
    )


def render_no_trade_explanation_json(outcome: TradeProposalOutcome) -> dict[str, Any]:
    """Every check, not only the reason precedence selected.

    `render_outcome_json` answers "what happened"; this answers "why, and what
    else was true at the same time". An operator debugging a refusal needs the
    second, because the reported reason is one of possibly several.
    """
    return {
        "decision": "PROPOSAL" if outcome.proposal is not None else "NO_TRADE",
        "reported_reason": (
            None if outcome.no_trade_reason is None else outcome.no_trade_reason.value
        ),
        "checks_evaluated": len(outcome.risk_checks),
        "checks_not_passed": [
            {"check_id": c.check_id, "outcome": c.outcome.value, "detail": c.detail}
            for c in outcome.risk_checks
            if c.outcome.value != "PASSED"
        ],
        "checks": [
            {"check_id": c.check_id, "outcome": c.outcome.value, "detail": c.detail}
            for c in outcome.risk_checks
        ],
    }


def render_no_trade_explanation_text(outcome: TradeProposalOutcome) -> str:
    lines: list[str] = []
    if outcome.proposal is not None:
        lines.append("PROPOSAL: every applicable check passed. Nothing to explain.")
    else:
        assert outcome.no_trade_reason is not None
        lines.append(f"NO_TRADE reported reason: {outcome.no_trade_reason.value}")
        lines.append(
            "  One reason is reported, chosen by explicit precedence. Every check "
            "that did not pass is listed below."
        )
    lines.append(f"  {len(outcome.risk_checks)} checks evaluated:")
    lines.extend(f"    {c.outcome.value:<8} {c.check_id}: {c.detail}" for c in outcome.risk_checks)
    return "\n".join(lines) + "\n"


def render_audit_history_json(history: AuditHistory) -> dict[str, Any]:
    return {
        "proposal": render_proposal_json(history.proposal),
        "evaluation_context": (
            None if history.context is None else render_context_json(history.context)
        ),
        "configuration": (
            None
            if history.configuration is None
            else render_configuration_json(history.configuration)
        ),
        "decision": None if history.decision is None else render_decision_json(history.decision),
        "approved_order_intent": (
            None if history.intent is None else render_intent_json(history.intent)
        ),
    }


def render_audit_history_text(history: AuditHistory) -> str:
    parts = [f"AUDIT HISTORY for proposal {history.proposal.proposal_governance_id}", ""]
    parts.append("1. CONFIGURATION")
    parts.append(
        "   (missing)\n"
        if history.configuration is None
        else "".join(
            f"   {line}\n" for line in render_configuration_text(history.configuration).splitlines()
        )
    )
    parts.append("2. EVALUATION CONTEXT")
    parts.append(
        "   (missing)\n"
        if history.context is None
        else "".join(f"   {line}\n" for line in render_context_text(history.context).splitlines())
    )
    parts.append("3. PROPOSAL")
    parts.append(
        "".join(f"   {line}\n" for line in render_proposal_text(history.proposal).splitlines())
    )
    parts.append("4. HUMAN DECISION")
    parts.append(
        "   (no decision recorded)\n"
        if history.decision is None
        else "".join(f"   {line}\n" for line in render_decision_text(history.decision).splitlines())
    )
    parts.append("5. APPROVED ORDER INTENT")
    parts.append(
        "   (no intent issued)\n"
        if history.intent is None
        else "".join(f"   {line}\n" for line in render_intent_text(history.intent).splitlines())
    )
    return "\n".join(parts)


def render_system_status_json(status: SystemStatus) -> dict[str, Any]:
    return {
        "proposal_counts": {s.value: n for s, n in status.proposal_counts.items()},
        "configuration_governance_id": status.configuration_governance_id,
        "configuration_version": status.configuration_version,
        "account_mode": status.account_mode,
        "kill_switch": status.kill_switch,
        "submission_capability": status.submission_capability,
    }


def render_system_status_text(status: SystemStatus) -> str:
    lines = ["system status", ""]
    if status.configuration_governance_id is None:
        lines.append("  configuration: (none named)")
    else:
        trading = (
            "STOPPED (kill switch ENGAGED)" if status.kill_switch == "ENGAGED" else "permitted"
        )
        lines.append(
            f"  configuration: {status.configuration_governance_id} "
            f"v{status.configuration_version}  mode={status.account_mode}  "
            f"kill switch={status.kill_switch} -> {trading}"
        )
    lines.append("  proposals:")
    lines.extend(f"    {name.value:<12} {count}" for name, count in status.proposal_counts.items())
    lines.append(f"  submission capability: {status.submission_capability}")
    lines.append(
        "    MILESTONE-084 cannot send an order. No broker client may be imported "
        "anywhere in this package, and no intent can leave NOT_SUBMITTED."
    )
    return "\n".join(lines) + "\n"


def render_invalidation_json(outcome: InvalidationOutcome) -> dict[str, Any]:
    return {
        "expired": list(outcome.expired),
        "invalidated": list(outcome.invalidated),
        "total": outcome.total,
    }


def render_invalidation_text(outcome: InvalidationOutcome) -> str:
    if outcome.total == 0:
        return "no PREPARED proposal needed invalidating\n"
    lines = [f"invalidated {outcome.total} proposal(s)"]
    lines.extend(f"  EXPIRED      {pid}" for pid in outcome.expired)
    lines.extend(
        f"  INVALIDATED  {pid}  (a newer configuration version exists)"
        for pid in outcome.invalidated
    )
    return "\n".join(lines) + "\n"
