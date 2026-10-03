"""Explicit routing identity. Absence in historical records never implies a new broker."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.entry_risk_contract import money


class BrokerIdentity(StrEnum):
    ALPACA_PAPER = "ALPACA_PAPER"
    IBKR_PAPER = "IBKR_PAPER"


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware timestamp required")


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    broker: BrokerIdentity
    contract_id: str
    symbol: str
    venue: str
    exchange: str
    primary_exchange: str
    currency: Currency
    security_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.broker, BrokerIdentity) or not isinstance(self.currency, Currency):
            raise ValueError("explicit supported Paper broker and currency required")
        for value in (
            self.contract_id,
            self.symbol,
            self.venue,
            self.exchange,
            self.primary_exchange,
            self.security_type,
        ):
            if not value or value != value.strip() or len(value) > 64:
                raise ValueError("invalid instrument identity")
        if self.broker is BrokerIdentity.IBKR_PAPER:
            if not self.contract_id.isascii() or not self.contract_id.isdecimal():
                raise ValueError("IBKR requires a numeric conid")
            if str(int(self.contract_id)) != self.contract_id or int(self.contract_id) <= 0:
                raise ValueError("IBKR conid must be canonical and positive")
            if (
                self.venue,
                self.exchange,
                self.primary_exchange,
                self.currency,
                self.security_type,
            ) != ("XHEL", "HEX", "HEX", Currency.EUR, "STK"):
                raise ValueError("only direct Nasdaq Helsinki EUR equities are permitted")
        elif self.currency is not Currency.USD:
            raise ValueError("historical Alpaca route is USD only")

    @property
    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class MarketQuote:
    instrument: InstrumentIdentity
    bid: Decimal
    ask: Decimal
    source_at: datetime
    received_at: datetime
    realtime: bool

    def __post_init__(self) -> None:
        aware(self.source_at)
        aware(self.received_at)
        if type(self.realtime) is not bool:
            raise ValueError("explicit realtime boolean required")
        for amount in (self.bid, self.ask):
            money(amount)
        if not 0 < self.bid <= self.ask:
            raise ValueError("missing, nonpositive or crossed quote")

    def validate(self, instrument: InstrumentIdentity, now: datetime, max_age: int) -> None:
        aware(now)
        if self.instrument != instrument or not self.realtime:
            raise ValueError("wrong instrument or non-realtime quote")
        if max_age <= 0:
            raise ValueError("positive freshness bound required")
        for instant in (self.source_at, self.received_at):
            if not 0 <= (now - instant).total_seconds() <= max_age:
                raise ValueError("stale or future quote")


@dataclass(frozen=True, slots=True)
class PaperAccountIdentity:
    broker: BrokerIdentity
    account: str
    currency: Currency
    client_id: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.broker, BrokerIdentity) or not isinstance(self.currency, Currency):
            raise ValueError("explicit Paper identity required")
        if self.broker is BrokerIdentity.IBKR_PAPER:
            if type(self.client_id) is not int or self.client_id <= 0:
                raise ValueError("dedicated persistent IBKR client ID required")
            if (
                not self.account.startswith("DU")
                or not self.account[2:].isascii()
                or not self.account[2:].isdigit()
                or self.currency is not Currency.EUR
            ):
                raise ValueError("explicit IBKR Paper DU account and EUR required")
        elif not self.account or self.currency is not Currency.USD:
            raise ValueError("explicit Alpaca USD account required")

    @property
    def reference(self) -> str:
        return fingerprint(asdict(self))
