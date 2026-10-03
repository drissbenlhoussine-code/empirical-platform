"""Broker-aware governance and execution; shared v1 risk/trigger semantics, no broker SDK."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.approved_plan import evaluate_exit_trigger
from empirical_platform.decision_candidate.helsinki_calendar import require_helsinki_open
from empirical_platform.decision_candidate.market_access_ports import (
    DispatchRecord,
    MarketExecutionPort,
    MarketJournal,
    ResolvedContract,
)
from empirical_platform.decision_candidate.market_identity import MarketQuote, PaperAccountIdentity
from empirical_platform.decision_candidate.market_plan import MarketPlan, OrderPurpose, OrderTruth
from empirical_platform.decision_candidate.operator_trading_configuration import (
    KillSwitchState,
    OperatorTradingConfiguration,
    configuration_fingerprint,
)
from empirical_platform.decision_candidate.trade_proposal import TradeProposal, compute_fingerprint

__all__ = [
    "MarketAccessService",
    "OperatorTradingConfiguration",
    "bind_market_proposal",
    "require_acceptance_policy",
]


def require_acceptance_policy(policy: OperatorTradingConfiguration) -> None:
    if (
        policy.risk_contract_version != 2
        or policy.base_currency != "EUR"
        or policy.permitted_markets != ("XHEL",)
        or policy.maximum_position_quantity_shares != 1
        or policy.maximum_planned_loss_per_trade is None
        or policy.maximum_planned_loss_per_trade > Decimal("5")
        or policy.maximum_capital_per_trade > Decimal("500")
        or policy.maximum_simultaneous_positions != 1
    ):
        raise ValueError(
            "explicit EUR Helsinki acceptance policy (1 share / 500 EUR / 5 EUR) required"
        )


def bind_market_proposal(
    proposal: TradeProposal,
    *,
    policy: OperatorTradingConfiguration,
    account: PaperAccountIdentity,
    contract: ResolvedContract,
    quote: MarketQuote,
    now: datetime,
) -> MarketPlan:
    """The existing canonical evaluator supplies prices, sizing and all independent gates."""
    require_acceptance_policy(policy)
    proposal.__post_init__()
    if proposal.content_fingerprint != compute_fingerprint(proposal) or proposal.entry_risk is None:
        raise ValueError("canonical risk-v2 proposal required")
    if (
        proposal.configuration_governance_id != policy.configuration_governance_id
        or proposal.configuration_version != policy.configuration_version
        or proposal.currency != policy.base_currency
        or proposal.symbol != contract.instrument.symbol
        or proposal.entry_risk.maximum_position_quantity_shares
        != policy.maximum_position_quantity_shares
        or proposal.entry_risk.maximum_planned_loss_per_trade
        != policy.maximum_planned_loss_per_trade
    ):
        raise ValueError("proposal, configuration or route mismatch")
    quote.validate(contract.instrument, now, policy.maximum_market_data_age_seconds)
    session = require_helsinki_open(
        now, broker_liquid_open=contract.liquid_open, broker_liquid_close=contract.liquid_close
    )
    assert contract.liquid_close is not None
    if proposal.limit_price is None or proposal.limit_price < quote.ask:
        raise ValueError("acceptance requires a marketable approved LIMIT")
    if proposal.limit_price % contract.minimum_tick:
        raise ValueError("entry violates exchange tick; regenerate terms, never silently reprice")
    if proposal.mandatory_liquidation_at > min(
        session.continuous_close, contract.liquid_close
    ) - timedelta(minutes=2):
        raise ValueError("mandatory exit must leave a buffer before continuous close")
    return MarketPlan(
        plan_id=proposal.proposal_governance_id,
        instrument=contract.instrument,
        account=account,
        configuration_id=policy.configuration_governance_id,
        configuration_version=policy.configuration_version,
        configuration_fingerprint=configuration_fingerprint(policy),
        proposal_fingerprint=proposal.content_fingerprint,
        risk=proposal.entry_risk,
        target=proposal.profit_exit_price,
        maximum_notional=policy.maximum_capital_per_trade,
        estimated_total_cash_required=proposal.estimated_total_cash_required,
        mandatory_exit=proposal.mandatory_liquidation_at,
        approval_expires=min(
            proposal.expires_at,
            now + timedelta(seconds=policy.approval_expiry_seconds),
            quote.source_at + timedelta(seconds=policy.maximum_market_data_age_seconds),
            quote.received_at + timedelta(seconds=policy.maximum_market_data_age_seconds),
        ),
        created_at=now,
        entry_quote=quote,
    )


class MarketAccessService:
    def __init__(
        self,
        *,
        journal: MarketJournal,
        broker: MarketExecutionPort,
        policy: Callable[[], OperatorTradingConfiguration],
        now: Callable[[], datetime],
    ) -> None:
        self.journal = journal
        self.broker = broker
        self.policy = policy
        self.now = now

    def _route(self, plan: MarketPlan) -> None:
        if plan.account != self.broker.identity:
            raise ValueError("broker/account/client identity mismatch")
        plan.__post_init__()
        if self.journal.get_plan(plan.plan_id) != plan:
            raise ValueError("durable plan terms changed")
        if self.journal.approval(plan.plan_id) is None:
            raise ValueError("Owner full-plan approval required")

    def _entry_gate(self, plan: MarketPlan, *, already_reserved: bool = False) -> None:
        self._route(plan)
        policy = self.policy()
        require_acceptance_policy(policy)
        if configuration_fingerprint(policy) != plan.configuration_fingerprint:
            raise ValueError("changed configuration invalidates old approval")
        if (
            plan.risk.maximum_position_quantity_shares != policy.maximum_position_quantity_shares
            or plan.risk.maximum_planned_loss_per_trade != policy.maximum_planned_loss_per_trade
            or plan.maximum_notional != policy.maximum_capital_per_trade
            or plan.instrument.symbol not in policy.watchlist
            or plan.instrument.symbol in policy.prohibited_instruments
        ):
            raise ValueError("plan risk/quantity/instrument differs from canonical configuration")
        if self.journal.kill_switch() or policy.kill_switch is KillSwitchState.ENGAGED:
            raise ValueError("kill switch blocks entry")
        account = self.broker.account()
        contract = self.broker.resolve(plan.instrument.symbol)
        quote = self.broker.quote(plan.instrument)
        positions = self.broker.positions()
        orders = self.broker.open_orders()
        now = self.now()
        if not plan.created_at <= now < plan.approval_expires:
            raise ValueError("expired plan requires new Owner approval")
        plan.entry_quote.validate(plan.instrument, now, policy.maximum_market_data_age_seconds)
        if account.identity != plan.account or not account.ready or positions or orders:
            raise ValueError("account, position or conflicting order gate refused")
        if contract.instrument != plan.instrument:
            raise ValueError("contract changed since approval")
        require_helsinki_open(
            now, broker_liquid_open=contract.liquid_open, broker_liquid_close=contract.liquid_close
        )
        quote.validate(plan.instrument, now, policy.maximum_market_data_age_seconds)
        if quote.ask > plan.risk.entry_ceiling:
            raise ValueError("market moved above approved ceiling; no automatic repricing")
        if (
            plan.risk.entry_ceiling < policy.minimum_price
            or policy.maximum_price is not None
            and plan.risk.entry_ceiling > policy.maximum_price
        ):
            raise ValueError("configured price gate")
        if (quote.ask - quote.bid) / (
            (quote.ask + quote.bid) / 2
        ) * 100 > policy.maximum_spread_percent:
            raise ValueError("configured spread gate")
        if plan.risk.entry_ceiling % contract.minimum_tick:
            raise ValueError("approved limit no longer valid for exchange tick")
        if (
            not 0
            <= (now - account.observed_at).total_seconds()
            <= policy.maximum_market_data_age_seconds
        ):
            raise ValueError("stale account evidence")
        if account.cash - policy.minimum_cash_reserve < plan.estimated_total_cash_required:
            raise ValueError("cash-only funding insufficient")
        if account.realized_pnl <= -policy.maximum_daily_loss:
            raise ValueError("independent daily-loss gate")
        local = now.astimezone(ZoneInfo(policy.operator_timezone))
        if (
            not policy.earliest_entry_time
            <= local.time().replace(tzinfo=None)
            <= policy.latest_entry_time
        ):
            raise ValueError("configured entry window closed")
        since = local.replace(hour=0, minute=0, second=0, microsecond=0)
        used = self.journal.entry_count(since) - int(already_reserved)
        if used >= policy.maximum_daily_order_count:
            raise ValueError("independent daily order-count gate")
        plan.risk.__post_init__()  # exact shared loss/quantity revalidation at final boundary

    def submit_entry(self, plan_id: str) -> DispatchRecord:
        plan = self.journal.get_plan(plan_id)
        existing = self.journal.dispatch(plan_id, OrderPurpose.ENTRY)
        if existing is not None:
            self.reconcile(plan, existing)
            return existing  # never repeat placeOrder, even after a missing broker response
        self._entry_gate(plan)
        record = self.journal.reserve(
            plan,
            OrderPurpose.ENTRY,
            self.broker.next_order_id(),
            Decimal(plan.risk.quantity),
            plan.risk.entry_ceiling,
            self.now(),
        )
        if record is None:
            raise ValueError("another dispatcher claimed this exact entry")
        try:
            self.broker.send_bound(
                plan, record, before_send=lambda: self._entry_gate(plan, already_reserved=True)
            )
        except Exception:
            self.journal.observe(plan, record, None)
            raise
        self.reconcile(plan, record)
        return record

    def reconcile(self, plan: MarketPlan, record: DispatchRecord) -> OrderTruth | None:
        self._route(plan)
        truth = self.broker.reconcile(plan, record)
        if truth is not None:
            truth.require_matches(plan, record.purpose, record.order_id)
            if truth.quantity != record.quantity:
                raise ValueError("broker quantity differs from claimed request")
        self.journal.observe(plan, record, truth)
        return truth

    def manage_exits_once(self, *, now: datetime) -> tuple[str, ...]:
        """Called by the one v1 Plan Manager thread; no second polling process."""
        outcomes = []
        for plan in self.journal.active_plans():
            try:
                outcomes.append(self._manage_plan(plan, now))
            except (ValueError, RuntimeError):
                outcomes.append(f"{plan.plan_id}:NEEDS_ATTENTION")
        return tuple(outcomes)

    def _manage_plan(self, plan: MarketPlan, now: datetime) -> str:
        self._route(plan)
        entry_record = self.journal.dispatch(plan.plan_id, OrderPurpose.ENTRY)
        if entry_record is None:
            return f"{plan.plan_id}:WAITING_FOR_ENTRY"
        entry = self.reconcile(plan, entry_record)
        if entry is not None and entry.status in ("WORKING", "PARTIAL"):
            approved = self.journal.approval(plan.plan_id)
            assert approved is not None
            quote = self.broker.quote(plan.instrument)
            at = self.now()
            quote.validate(plan.instrument, at, self.policy().maximum_market_data_age_seconds)
            trigger = approved.triggered_exit_kind or evaluate_exit_trigger(
                approved, last_price=quote.bid, now=at
            )
            if trigger is not None:
                self.journal.claim_trigger(plan.plan_id, trigger, at)
                if self.journal.claim_cancel(entry_record, at):
                    self.broker.cancel_bound(plan, entry_record)
                return f"{plan.plan_id}:CANCEL_RECONCILING"
        if entry is None or entry.status not in ("FILLED", "CANCELED") or entry.filled <= 0:
            return f"{plan.plan_id}:ENTRY_NOT_TERMINAL_OR_UNRESOLVED"
        exit_record = self.journal.dispatch(plan.plan_id, OrderPurpose.CLOSE)
        if exit_record:
            exit_truth = self.reconcile(plan, exit_record)
            if exit_truth and exit_truth.status == "FILLED" and exit_truth.filled == entry.filled:
                verification = self.broker.positions_snapshot()
                if verification.account != plan.account or verification.positions:
                    return f"{plan.plan_id}:FILLED_AWAITING_ZERO"
                assert exit_truth.average_price is not None and entry.average_price is not None
                self.journal.close_verified(
                    plan,
                    (exit_truth.average_price - entry.average_price) * entry.filled,
                    self.now(),
                    verification,
                )
                return f"{plan.plan_id}:CLOSED"
            return f"{plan.plan_id}:EXIT_RECONCILING"
        approved = self.journal.approval(plan.plan_id)
        assert approved is not None
        quote = self.broker.quote(plan.instrument)
        now = self.now()
        quote.validate(plan.instrument, now, self.policy().maximum_market_data_age_seconds)
        trigger = approved.triggered_exit_kind or evaluate_exit_trigger(
            approved, last_price=quote.bid, now=now
        )
        if trigger is None:
            return f"{plan.plan_id}:MONITORING"
        if approved.triggered_exit_kind is None and not self.journal.claim_trigger(
            plan.plan_id, trigger, now
        ):
            return f"{plan.plan_id}:TRIGGER_ALREADY_CLAIMED"
        self._close_gate(plan, entry.filled)
        record = self.journal.reserve(
            plan,
            OrderPurpose.CLOSE,
            self.broker.next_order_id(),
            entry.filled,
            quote.bid,
            self.now(),
        )
        if record is None:
            return f"{plan.plan_id}:EXIT_ALREADY_CLAIMED"
        try:
            self.broker.send_bound(
                plan, record, before_send=lambda: self._close_gate(plan, entry.filled)
            )
        except Exception:
            self.journal.observe(plan, record, None)
            raise
        self.reconcile(plan, record)
        return f"{plan.plan_id}:{trigger.value}"

    def _close_gate(self, plan: MarketPlan, quantity: Decimal) -> None:
        self._route(plan)
        positions = self.broker.positions()
        if (
            len(positions) != 1
            or positions[0].instrument != plan.instrument
            or positions[0].account != plan.account
            or positions[0].quantity != quantity
        ):
            raise ValueError("close must equal the exact attributable long position")
        contract = self.broker.resolve(plan.instrument.symbol)
        if contract.instrument != plan.instrument or self.broker.open_orders():
            raise ValueError("close route changed or conflicting orders exist")
        at = self.now()
        if (
            not 0
            <= (at - positions[0].observed_at).total_seconds()
            <= self.policy().maximum_market_data_age_seconds
        ):
            raise ValueError("stale position evidence")
        require_helsinki_open(
            at, broker_liquid_open=contract.liquid_open, broker_liquid_close=contract.liquid_close
        )
        # Kill switch deliberately does not block approved position reduction.
