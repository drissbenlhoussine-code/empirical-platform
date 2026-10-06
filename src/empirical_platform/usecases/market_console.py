"""Read models for routed evidence in the existing mobile console."""

from datetime import datetime

from empirical_platform.decision_candidate.entry_risk_contract import money, planned_loss
from empirical_platform.decision_candidate.helsinki_calendar import helsinki_session
from empirical_platform.decision_candidate.market_access_ports import MarketJournal
from empirical_platform.decision_candidate.market_plan import MarketPlan


class MarketReviewService:
    def __init__(self, journal: MarketJournal) -> None:
        self.journal = journal

    def plan(self, plan_id: str) -> tuple[tuple[str, str], ...]:
        return full_plan_fields(self.journal.get_plan(plan_id))

    def history(self) -> tuple[tuple[str, str, str, str, str, str], ...]:
        return tuple(
            (
                row.plan.plan_id,
                row.plan.instrument.broker.value,
                row.plan.instrument.venue,
                row.plan.instrument.currency.value,
                row.status,
                money(row.realized_price_pnl)
                if row.realized_price_pnl is not None
                else "Unverified",
            )
            for row in self.journal.history()
        )


def market_status(now: datetime) -> tuple[tuple[str, str], ...]:
    return (
        ("Broker", "IBKR PAPER"),
        ("Market", "NASDAQ HELSINKI / XHEL"),
        ("Currency", "EUR"),
        ("Exchange calendar", helsinki_session(now).status),
        ("Connection", "OWNER SETUP REQUIRED — connection and permissions unverified"),
        ("Execution", "Disabled — no real acceptance has been performed"),
    )


def full_plan_fields(plan: MarketPlan) -> tuple[tuple[str, str], ...]:
    gain = planned_loss(plan.target, plan.risk.entry_ceiling, plan.risk.quantity)
    return (
        ("Broker", plan.instrument.broker.value),
        ("Market", plan.instrument.venue),
        ("Currency", plan.instrument.currency.value),
        ("Instrument", f"{plan.instrument.symbol} / conid {plan.instrument.contract_id}"),
        (
            "Exchange / primary exchange",
            f"{plan.instrument.exchange} / {plan.instrument.primary_exchange}",
        ),
        ("Account identity fingerprint", plan.account.reference),
        ("Quantity", str(plan.risk.quantity)),
        ("Bid (EUR)", money(plan.entry_quote.bid)),
        ("Ask (EUR)", money(plan.entry_quote.ask)),
        ("Quote time", plan.entry_quote.source_at.isoformat()),
        ("Notional (EUR)", money(plan.risk.entry_ceiling * plan.risk.quantity)),
        ("Entry ceiling (EUR)", money(plan.risk.entry_ceiling)),
        ("Stop (EUR)", money(plan.risk.stop_price)),
        ("Target (EUR)", money(plan.target)),
        ("Planned price loss (EUR)", money(plan.risk.planned_loss)),
        ("Configured maximum planned loss (EUR)", money(plan.risk.maximum_planned_loss_per_trade)),
        ("Target price gain (EUR)", money(gain)),
        ("Reward / risk", str(gain / plan.risk.planned_loss)),
        ("Mandatory exit", plan.mandatory_exit.isoformat()),
        ("Approval expires", plan.approval_expires.isoformat()),
        ("Order terms", "BUY LIMIT / DAY / extended hours OFF / long only"),
        ("Configuration", f"{plan.configuration_id} / version {plan.configuration_version}"),
        ("Configuration fingerprint", plan.configuration_fingerprint),
        ("Full-plan fingerprint", plan.fingerprint),
    )
