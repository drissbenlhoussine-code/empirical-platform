"""Route-bound envelope around the existing v1 risk and full-plan contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, derive_system_identity
from empirical_platform.decision_candidate.entry_risk_contract import (
    EntryRiskContract,
    money,
    read_risk,
)
from empirical_platform.decision_candidate.market_identity import (
    BrokerIdentity,
    Currency,
    InstrumentIdentity,
    MarketQuote,
    PaperAccountIdentity,
    aware,
    fingerprint,
)


class OrderPurpose(StrEnum):
    ENTRY = "BUY"
    CLOSE = "SELL_TO_CLOSE"


@dataclass(frozen=True, slots=True)
class MarketPlan:
    plan_id: str
    instrument: InstrumentIdentity
    account: PaperAccountIdentity
    configuration_id: str
    configuration_version: int
    configuration_fingerprint: str
    proposal_fingerprint: str
    risk: EntryRiskContract
    target: Decimal
    maximum_notional: Decimal
    estimated_total_cash_required: Decimal
    mandatory_exit: datetime
    approval_expires: datetime
    created_at: datetime
    entry_quote: MarketQuote

    def __post_init__(self) -> None:
        if (
            self.instrument.broker != self.account.broker
            or self.instrument.currency != self.account.currency
        ):
            raise ValueError("broker/account/currency mismatch")
        self.risk.__post_init__()
        if self.entry_quote.instrument != self.instrument:
            raise ValueError("entry quote route mismatch")
        if not self.entry_quote.realtime or self.entry_quote.ask > self.risk.entry_ceiling:
            raise ValueError("approved entry requires a live marketable quote")
        for value in (self.target, self.maximum_notional, self.estimated_total_cash_required):
            money(value)
        if self.estimated_total_cash_required < self.risk.entry_ceiling * self.risk.quantity:
            raise ValueError("cash requirement cannot omit entry notional")
        if self.target <= self.risk.entry_ceiling:
            raise ValueError("long target must exceed entry")
        if self.risk.entry_ceiling * self.risk.quantity > self.maximum_notional:
            raise ValueError("notional cap exceeded")
        for instant in (self.created_at, self.approval_expires, self.mandatory_exit):
            aware(instant)
        if not self.created_at < self.approval_expires < self.mandatory_exit:
            raise ValueError("invalid plan deadlines")
        if not self.plan_id or len(self.plan_id) > 48 or not self.configuration_id:
            raise ValueError("invalid governance identity")
        if type(self.configuration_version) is not int or self.configuration_version <= 0:
            raise ValueError("invalid configuration version")
        for digest in (self.configuration_fingerprint, self.proposal_fingerprint):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid immutable fingerprint")

    def document(self) -> dict[str, Any]:
        return {
            "version": 1,
            "plan_id": self.plan_id,
            "instrument": asdict(self.instrument),
            "account": asdict(self.account),
            "configuration_id": self.configuration_id,
            "configuration_version": self.configuration_version,
            "configuration_fingerprint": self.configuration_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "risk": self.risk.document(),
            "target": money(self.target),
            "maximum_notional": money(self.maximum_notional),
            "estimated_total_cash_required": money(self.estimated_total_cash_required),
            "mandatory_exit": self.mandatory_exit.isoformat(),
            "approval_expires": self.approval_expires.isoformat(),
            "created_at": self.created_at.isoformat(),
            "time_in_force": "DAY",
            "extended_hours": False,
            "entry_quote": {
                "bid": money(self.entry_quote.bid),
                "ask": money(self.entry_quote.ask),
                "source_at": self.entry_quote.source_at.isoformat(),
                "received_at": self.entry_quote.received_at.isoformat(),
                "realtime": self.entry_quote.realtime,
            },
        }

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.document())

    def order_reference(self, purpose: OrderPurpose) -> str:
        # Stable and short enough for orderRef. Never a ticker-only identity.
        return "ep-" + fingerprint({"plan": self.fingerprint, "purpose": purpose.value})[:28]

    def approve(self, owner: str, expected: str, now: datetime) -> ApprovedPlan:
        aware(now)
        if not owner.strip() or owner.startswith("system:") or expected != self.fingerprint:
            raise ValueError("explicit Owner identity and exact full-plan approval required")
        if not self.created_at <= now < self.approval_expires:
            raise ValueError("expired plan requires new terms and new Owner approval")
        return ApprovedPlan(
            plan_id=self.plan_id,
            candidate_id=self.plan_id,
            entry_intent_governance_id=self.order_reference(OrderPurpose.ENTRY),
            symbol=self.instrument.symbol,
            approved_quantity=Decimal(self.risk.quantity),
            stop_price=self.risk.stop_price,
            target_price=self.target,
            mandatory_liquidation_at=self.mandatory_exit,
            owner_approval_id=owner,
            system_identity=derive_system_identity(plan_id=self.plan_id, owner_approval_id=owner),
            created_at=now,
        )


def read_market_plan(document: dict[str, Any]) -> MarketPlan:
    body = dict(document)
    version = body.pop("version")
    if (
        type(version) is not int
        or version != 1
        or body.pop("time_in_force") != "DAY"
        or body.pop("extended_hours") is not False
    ):
        raise ValueError("unsupported plan contract")
    instrument = dict(body.pop("instrument"))
    instrument["broker"] = BrokerIdentity(instrument["broker"])
    instrument["currency"] = Currency(instrument["currency"])
    account = dict(body.pop("account"))
    account["broker"] = BrokerIdentity(account["broker"])
    account["currency"] = Currency(account["currency"])
    body["instrument"] = InstrumentIdentity(**instrument)
    quote = body.pop("entry_quote")
    if not isinstance(quote["bid"], str) or not isinstance(quote["ask"], str):
        raise ValueError("exact quote decimals required")
    body["entry_quote"] = MarketQuote(
        body["instrument"],
        Decimal(quote["bid"]),
        Decimal(quote["ask"]),
        datetime.fromisoformat(quote["source_at"]),
        datetime.fromisoformat(quote["received_at"]),
        quote["realtime"],
    )
    body["account"] = PaperAccountIdentity(**account)
    body["risk"] = read_risk(body["risk"])
    if body["risk"] is None:
        raise ValueError("risk contract required")
    for name in ("target", "maximum_notional", "estimated_total_cash_required"):
        if not isinstance(body[name], str):
            raise ValueError("exact decimal strings required")
        body[name] = Decimal(body[name])
    for name in ("mandatory_exit", "approval_expires", "created_at"):
        body[name] = datetime.fromisoformat(body[name])
    return MarketPlan(**body)


@dataclass(frozen=True, slots=True)
class OrderTruth:
    instrument: InstrumentIdentity
    account: PaperAccountIdentity
    reference: str
    order_id: int
    permanent_id: int
    purpose: OrderPurpose
    quantity: Decimal
    filled: Decimal
    average_price: Decimal | None
    status: str
    observed_at: datetime

    def __post_init__(self) -> None:
        aware(self.observed_at)
        if not isinstance(self.purpose, OrderPurpose):
            raise ValueError("explicit order purpose required")
        if (
            type(self.order_id) is not int
            or self.order_id < 0
            or type(self.permanent_id) is not int
            or self.permanent_id <= 0
        ):
            raise ValueError("positive permanent broker identity required")
        for amount in (self.quantity, self.filled):
            money(amount)
        if not 0 <= self.filled <= self.quantity or self.quantity <= 0:
            raise ValueError("invalid fill quantities")
        if self.average_price is not None:
            money(self.average_price)
        if self.filled and (self.average_price is None or self.average_price <= 0):
            raise ValueError("filled order requires execution price")
        if self.status not in {"WORKING", "PARTIAL", "FILLED", "CANCELED", "REJECTED", "UNKNOWN"}:
            raise ValueError("unmapped order state")
        if self.status == "FILLED" and self.filled != self.quantity:
            raise ValueError("filled status disagrees with quantity")

    def require_matches(self, plan: MarketPlan, purpose: OrderPurpose, order_id: int) -> None:
        if (
            self.instrument != plan.instrument
            or self.account != plan.account
            or self.reference != plan.order_reference(purpose)
            or self.purpose != purpose
            or self.order_id != order_id
            or self.quantity > plan.risk.quantity
        ):
            raise ValueError("order identity does not match immutable approved route")
