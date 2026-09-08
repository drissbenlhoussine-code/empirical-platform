"""MILESTONE-084 -- persistent, versioned operator trading configuration.

WHAT THIS IS. The single governing policy record for the decision-to-approval
product core: what the operator permits, how much capital may be deployed, what
risk and freshness limits apply, and which trading window is allowed. Every M084
proposal names the exact configuration version that governed it, so a proposal
can never be re-interpreted later under different limits.

PURE AND I/O-FREE. No clock read, no database, no provider. `evaluated_at`
style instants are always supplied by the caller from an authorized source --
this module never invents one, and never treats an operator-supplied timestamp
as proof of market chronology.

WHY SO MANY REJECTIONS. A configuration that is merely *storable* is not
enough: an internally inconsistent policy silently produces proposals nobody
intended. Every combination below that cannot produce a safe long-only intraday
proposal is refused at construction, so an impossible policy cannot reach the
proposal engine at all.

THE M084 MODE BOUNDARY. `AccountMode` names PAPER and LIVE so the enum is
honest about what will exist later, but this milestone accepts ONLY
`PREPARATION`. M084 is technically incapable of submitting an order; a
configuration that requests PAPER or LIVE is refused here, structurally, rather
than being accepted and then policed somewhere downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "AccountMode",
    "KillSwitchState",
    "LimitPricePolicy",
    "OperatorTradingConfiguration",
    "OrderType",
    "TradingSession",
]

# The longest identifier any M084 column accepts. Mirrors the 64-character
# governance-identity width M082/M083 already froze, so an identity that is
# storable there is storable here.
_MAXIMUM_IDENTIFIER_LENGTH = 64
_MAXIMUM_SYMBOL_LENGTH = 32
_MAXIMUM_LIST_LENGTH = 256

_ONE_HUNDRED = Decimal("100")


class AccountMode(StrEnum):
    """Which execution surface a configuration is declared for.

    Only `PREPARATION` is accepted in M084. PAPER belongs to M085 and LIVE to
    M086; both are named here so that a configuration requesting them is
    rejected with a precise reason rather than an obscure enum failure.
    """

    PREPARATION = "PREPARATION"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderType(StrEnum):
    """Order types the product core can express. Broker-neutral."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class LimitPricePolicy(StrEnum):
    """How a LIMIT price is derived from an observed quote."""

    LAST_TRADE = "LAST_TRADE"
    MID_QUOTE = "MID_QUOTE"
    ASK = "ASK"


class TradingSession(StrEnum):
    """Which exchange session an entry may occur in.

    Only `REGULAR` is permitted: pre- and post-market liquidity cannot satisfy
    this milestone's spread and liquidity gates honestly, and an intraday-only
    product has no reason to enter outside regular hours.
    """

    REGULAR = "REGULAR"
    PRE_MARKET = "PRE_MARKET"
    POST_MARKET = "POST_MARKET"


class KillSwitchState(StrEnum):
    """Operator-controlled global stop.

    ENGAGED means "produce no proposal and approve nothing". It is deliberately
    a stored configuration field rather than a runtime flag, so that engaging it
    is an auditable, versioned act.
    """

    DISENGAGED = "DISENGAGED"
    ENGAGED = "ENGAGED"


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def _require_symbols(values: tuple[str, ...], *, field: str) -> None:
    if len(values) > _MAXIMUM_LIST_LENGTH:
        raise ValueError(f"{field} must contain at most {_MAXIMUM_LIST_LENGTH} entries")
    for symbol in values:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(f"{field} must not contain a blank symbol")
        if len(symbol) > _MAXIMUM_SYMBOL_LENGTH:
            raise ValueError(f"{field} symbols must be at most {_MAXIMUM_SYMBOL_LENGTH} characters")
        if symbol != symbol.strip().upper():
            raise ValueError(f"{field} symbols must be upper-case and unpadded: {symbol!r}")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    if list(values) != sorted(values):
        raise ValueError(f"{field} must be in canonical ascending order")


def _require_positive(value: Decimal, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise ValueError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_non_negative(value: Decimal, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise ValueError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if value < 0:
        raise ValueError(f"{field} must not be negative")


def _require_percent(value: Decimal, *, field: str, allow_zero: bool = False) -> None:
    _require_non_negative(value, field=field)
    if not allow_zero and value == 0:
        raise ValueError(f"{field} must be positive")
    if value > _ONE_HUNDRED:
        raise ValueError(f"{field} must not exceed 100")


def _require_positive_int(value: int, *, field: str) -> None:
    # bool is an int subclass; a boolean here is a caller mistake, not a count.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


@dataclass(frozen=True, slots=True)
class OperatorTradingConfiguration:
    """One immutable, versioned operator policy.

    Long-only, intraday-only, unleveraged, preparation-mode. Those four are not
    configurable switches that happen to default safely -- they are invariants
    this type refuses to be constructed without.
    """

    configuration_governance_id: str
    configuration_version: int

    # --- currency and universe -------------------------------------------
    base_currency: str
    permitted_markets: tuple[str, ...]
    watchlist: tuple[str, ...]
    prohibited_instruments: tuple[str, ...]

    # --- capital ----------------------------------------------------------
    maximum_deployable_capital: Decimal
    maximum_capital_per_trade: Decimal
    maximum_percent_per_trade: Decimal
    minimum_cash_reserve: Decimal
    maximum_simultaneous_positions: int

    # --- loss and activity limits ----------------------------------------
    maximum_daily_loss: Decimal
    maximum_daily_order_count: int

    # --- instrument quality ----------------------------------------------
    minimum_price: Decimal
    maximum_price: Decimal | None
    minimum_liquidity_shares: int
    maximum_spread_percent: Decimal
    maximum_estimated_slippage_percent: Decimal

    # --- freshness --------------------------------------------------------
    maximum_evidence_age_seconds: int
    maximum_market_data_age_seconds: int

    # --- session ----------------------------------------------------------
    permitted_session: TradingSession
    earliest_entry_time: time
    latest_entry_time: time
    mandatory_liquidation_time: time
    operator_timezone: str
    exchange_calendar_policy: str

    # --- expiry -----------------------------------------------------------
    proposal_expiry_seconds: int
    approval_expiry_seconds: int

    # --- order policy -----------------------------------------------------
    default_order_type: OrderType
    permitted_order_types: tuple[OrderType, ...]
    limit_price_policy: LimitPricePolicy
    stop_loss_percent: Decimal
    profit_exit_percent: Decimal

    # --- hard product invariants -----------------------------------------
    maximum_leverage: Decimal
    short_selling_permitted: bool
    overnight_positions_permitted: bool
    account_mode: AccountMode
    kill_switch: KillSwitchState

    def __post_init__(self) -> None:
        _require_identifier(self.configuration_governance_id, field="configuration_governance_id")
        if isinstance(self.configuration_version, bool) or not isinstance(
            self.configuration_version, int
        ):
            raise ValueError("configuration_version must be an int")
        if self.configuration_version < 1:
            raise ValueError("configuration_version must start at 1")

        # --- currency and universe ---------------------------------------
        if not isinstance(self.base_currency, str) or len(self.base_currency) != 3:
            raise ValueError("base_currency must be a 3-letter ISO code")
        if self.base_currency != self.base_currency.upper():
            raise ValueError("base_currency must be upper-case")
        _require_symbols(self.permitted_markets, field="permitted_markets")
        if not self.permitted_markets:
            raise ValueError("permitted_markets must not be empty")
        _require_symbols(self.watchlist, field="watchlist")
        if not self.watchlist:
            raise ValueError("watchlist must not be empty")
        _require_symbols(self.prohibited_instruments, field="prohibited_instruments")
        overlap = set(self.watchlist) & set(self.prohibited_instruments)
        if overlap:
            raise ValueError(
                f"an instrument may not be both watchlisted and prohibited: {sorted(overlap)}"
            )

        # --- capital ------------------------------------------------------
        _require_positive(self.maximum_deployable_capital, field="maximum_deployable_capital")
        _require_positive(self.maximum_capital_per_trade, field="maximum_capital_per_trade")
        _require_percent(self.maximum_percent_per_trade, field="maximum_percent_per_trade")
        _require_non_negative(self.minimum_cash_reserve, field="minimum_cash_reserve")
        _require_positive_int(
            self.maximum_simultaneous_positions, field="maximum_simultaneous_positions"
        )
        if self.maximum_capital_per_trade > self.maximum_deployable_capital:
            raise ValueError("maximum_capital_per_trade must not exceed maximum_deployable_capital")
        if self.minimum_cash_reserve >= self.maximum_deployable_capital:
            raise ValueError("minimum_cash_reserve must leave deployable capital available")

        # --- loss and activity limits -------------------------------------
        _require_positive(self.maximum_daily_loss, field="maximum_daily_loss")
        _require_positive_int(self.maximum_daily_order_count, field="maximum_daily_order_count")

        # --- instrument quality -------------------------------------------
        _require_positive(self.minimum_price, field="minimum_price")
        if self.maximum_price is not None:
            _require_positive(self.maximum_price, field="maximum_price")
            if self.maximum_price <= self.minimum_price:
                raise ValueError("maximum_price must exceed minimum_price")
        _require_positive_int(self.minimum_liquidity_shares, field="minimum_liquidity_shares")
        _require_percent(self.maximum_spread_percent, field="maximum_spread_percent")
        _require_percent(
            self.maximum_estimated_slippage_percent,
            field="maximum_estimated_slippage_percent",
        )

        # --- freshness ------------------------------------------------------
        _require_positive_int(
            self.maximum_evidence_age_seconds, field="maximum_evidence_age_seconds"
        )
        _require_positive_int(
            self.maximum_market_data_age_seconds, field="maximum_market_data_age_seconds"
        )

        # --- session --------------------------------------------------------
        if self.permitted_session is not TradingSession.REGULAR:
            raise ValueError(
                "only the REGULAR session is permitted: pre- and post-market "
                "liquidity cannot satisfy this milestone's spread and liquidity gates"
            )
        for field_name in (
            "earliest_entry_time",
            "latest_entry_time",
            "mandatory_liquidation_time",
        ):
            if not isinstance(getattr(self, field_name), time):
                raise ValueError(f"{field_name} must be a datetime.time")
            if getattr(self, field_name).tzinfo is not None:
                raise ValueError(
                    f"{field_name} must be a naive local time interpreted in operator_timezone"
                )
        if self.earliest_entry_time >= self.latest_entry_time:
            raise ValueError("earliest_entry_time must precede latest_entry_time")
        if self.mandatory_liquidation_time <= self.latest_entry_time:
            raise ValueError(
                "mandatory_liquidation_time must follow latest_entry_time: an intraday "
                "position that cannot be closed after the last permitted entry is an "
                "overnight position"
            )
        if not isinstance(self.operator_timezone, str) or not self.operator_timezone.strip():
            raise ValueError("operator_timezone must be a non-empty IANA zone name")
        try:
            ZoneInfo(self.operator_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(
                f"operator_timezone must be a known IANA zone: {self.operator_timezone!r}"
            ) from error
        _require_identifier(self.exchange_calendar_policy, field="exchange_calendar_policy")

        # --- expiry ----------------------------------------------------------
        _require_positive_int(self.proposal_expiry_seconds, field="proposal_expiry_seconds")
        _require_positive_int(self.approval_expiry_seconds, field="approval_expiry_seconds")
        if self.approval_expiry_seconds > self.proposal_expiry_seconds:
            raise ValueError(
                "approval_expiry_seconds must not exceed proposal_expiry_seconds: an "
                "approval cannot outlive the proposal version it authorizes"
            )

        # --- order policy ------------------------------------------------------
        if not self.permitted_order_types:
            raise ValueError("permitted_order_types must not be empty")
        if len(set(self.permitted_order_types)) != len(self.permitted_order_types):
            raise ValueError("permitted_order_types must not contain duplicates")
        for order_type in self.permitted_order_types:
            if not isinstance(order_type, OrderType):
                raise ValueError("permitted_order_types must contain OrderType members")
        if not isinstance(self.default_order_type, OrderType):
            raise ValueError("default_order_type must be an OrderType")
        if self.default_order_type not in self.permitted_order_types:
            raise ValueError("default_order_type must be one of permitted_order_types")
        if not isinstance(self.limit_price_policy, LimitPricePolicy):
            raise ValueError("limit_price_policy must be a LimitPricePolicy")
        _require_percent(self.stop_loss_percent, field="stop_loss_percent")
        _require_percent(self.profit_exit_percent, field="profit_exit_percent")

        # --- hard product invariants ---------------------------------------------
        if not isinstance(self.maximum_leverage, Decimal):
            raise ValueError("maximum_leverage must be a Decimal")
        if self.maximum_leverage != Decimal("1"):
            raise ValueError(
                "maximum_leverage must be exactly 1: this product is unleveraged, and "
                "leverage is not a configurable dial"
            )
        if not isinstance(self.short_selling_permitted, bool):
            raise ValueError("short_selling_permitted must be a bool")
        if self.short_selling_permitted:
            raise ValueError("short_selling_permitted must be False: this product is long-only")
        if not isinstance(self.overnight_positions_permitted, bool):
            raise ValueError("overnight_positions_permitted must be a bool")
        if self.overnight_positions_permitted:
            raise ValueError(
                "overnight_positions_permitted must be False: this product is intraday-only"
            )
        if not isinstance(self.account_mode, AccountMode):
            raise ValueError("account_mode must be an AccountMode")
        if self.account_mode is not AccountMode.PREPARATION:
            raise ValueError(
                "account_mode must be PREPARATION in MILESTONE-084: this milestone is "
                "technically incapable of submitting an order, so declaring PAPER or "
                "LIVE would describe a capability that does not exist"
            )
        if not isinstance(self.kill_switch, KillSwitchState):
            raise ValueError("kill_switch must be a KillSwitchState")

    @property
    def is_trading_permitted(self) -> bool:
        """False whenever the operator has engaged the global stop."""
        return self.kill_switch is KillSwitchState.DISENGAGED
