"""V1 MICRO PAPER TRADING (10-20 EUR equivalent) -- DESIGN PHASE, PARTIAL IMPLEMENTATION.

See `docs/v1-micro-paper-eur/design.md` for the full design, what is and is not built here,
and the explicit, honest list of deferred work (no FX provider is selected or integrated;
no broker-submission wiring exists; no new Postgres migration or configuration row exists).

WHY THIS IS A NEW, FULLY ISOLATED MODULE. The existing M084-M089 entry/approval/exit
pipeline types `quantity` as `int` throughout (`TradeProposal.quantity`,
`ApprovedPlan.approved_quantity`, `PositionExitRequest.quantity` -- whose own docstring
says "quantity is whole and positive") -- the pipeline this platform already relies on for
every whole-share PAPER trade. Widening those types to `Decimal` would touch the frozen
M084 decision core and every handler built on it, which the mission's "keep existing
whole-share PAPER v1 behavior backward compatible" instruction rules out. This module
touches NONE of that: it is pure, read-only, `Decimal`-typed sizing/verification math with
no broker call, no persistence, and no side effect, callable from a future isolated
composition root the same way `decision_candidate/external_position_closure.py` or PR
#27's own `market_access.py` are isolated from the core they sit beside.

NOTHING HERE CAN SUBMIT AN ORDER. There is no broker adapter, no composition root, and no
console capability flag anywhere in this module or its callers (there are none yet). Every
function below is a pure refusal-or-value computation over values the (not-yet-built)
caller must supply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

__all__ = [
    "EurUsdFxQuote",
    "fractional_notional_for_eur_target",
    "fx_quote_refusal",
    "portfolio_exposure_refusal",
    "portfolio_loss_limit_refusal",
]

#: Alpaca's own documented minimum: "a minimum 1 USD notional amount for Buy entry
#: orders." Not configurable -- it is the broker's own floor, independent of any
#: Owner-chosen per-trade cap.
ALPACA_MINIMUM_USD_NOTIONAL = Decimal("1.00")

#: Alpaca accepts up to 9 decimal places on `notional`; this module always rounds to cents
#: (2 decimal places) instead -- a real USD order amount has never needed sub-cent
#: precision, and rounding DOWN (never up) means the submitted notional can never exceed
#: what the Owner's EUR amount, converted, actually authorized.
_NOTIONAL_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class EurUsdFxQuote:
    """One EUR->USD rate reading, with enough evidence to judge its own freshness.

    `rate` is USD per 1 EUR (so `eur_amount * rate` is the equivalent USD amount).
    `source` names WHICH provider this came from -- never blank, so a refusal or an audit
    trail can always say which rate was used, not just that "a" rate was used. `as_of` is
    when the PROVIDER says this rate was valid; `fetched_at` is when this process retrieved
    it -- the two differ whenever a provider serves a cached or delayed quote, and both are
    kept because staleness must be judged against `as_of` (the rate's own age), not merely
    against when this process happened to ask for it.
    """

    rate: Decimal
    source: str
    as_of: datetime
    fetched_at: datetime


def _require_aware(value: object, *, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")


def fx_quote_refusal(
    quote: EurUsdFxQuote, *, now: datetime, max_staleness_seconds: float
) -> str | None:
    """Refuse (never guess) an unusable or stale FX quote. Returns `None` only when the
    quote is internally consistent, strictly positive, and fresh enough right now --
    literal enforcement of "refusal on stale FX (never assume 10 EUR = 10 USD)."

    Deliberately conservative: a quote whose `as_of` is in the future (evidence of a clock
    problem on one side or the other, not a usable rate) is refused exactly like a stale
    one, never treated as "extra fresh."
    """
    _require_aware(now, field="now")
    if not isinstance(quote.source, str) or not quote.source.strip():
        return "the FX quote names no source; it cannot be trusted or audited"
    if not isinstance(quote.as_of, datetime) or quote.as_of.tzinfo is None:
        return "the FX quote's as_of timestamp is not timezone-aware"
    if not isinstance(quote.fetched_at, datetime) or quote.fetched_at.tzinfo is None:
        return "the FX quote's fetched_at timestamp is not timezone-aware"
    if not isinstance(quote.rate, Decimal) or quote.rate <= 0:
        return "the FX quote's rate must be a positive Decimal"
    if quote.as_of > now:
        return "the FX quote's as_of timestamp is in the future; the rate cannot be trusted"
    age_seconds = (now - quote.as_of).total_seconds()
    if age_seconds > max_staleness_seconds:
        return (
            f"the FX quote from {quote.source!r} is {age_seconds:.0f}s old, exceeding the "
            f"{max_staleness_seconds:.0f}s staleness limit; refusing rather than assuming "
            "it still holds"
        )
    return None


def fractional_notional_for_eur_target(
    eur_amount: Decimal,
    fx: EurUsdFxQuote,
    *,
    minimum_usd_notional: Decimal = ALPACA_MINIMUM_USD_NOTIONAL,
    maximum_usd_notional_per_trade: Decimal,
    asset_fractionable: bool,
) -> Decimal | str:
    """The USD `notional` to submit for an Owner-approved EUR target, or a refusal string.

    Returns the rounded `Decimal` notional on success, a human-readable refusal `str`
    otherwise -- callers must check `isinstance(result, Decimal)` before using it as an
    order amount (mirrors this codebase's existing `exit_eligibility`-style "tuple of
    refusals, empty means eligible" convention, adapted to a single value-or-refusal
    return because there is exactly one thing to compute here, not a list of independent
    checks to accumulate).

    NEVER returns a share-count (`qty`): this platform only ever sizes a fractional PAPER
    trade as a dollar `notional`, so "accidental whole-share rounding" cannot happen by
    construction -- there is no share-count rounding step anywhere in this function.
    """
    if not asset_fractionable:
        return "this symbol is not fractionable at the broker; a notional order would be rejected"
    if not isinstance(eur_amount, Decimal) or eur_amount <= 0:
        return "the EUR target amount must be a positive Decimal"
    if (
        not isinstance(maximum_usd_notional_per_trade, Decimal)
        or maximum_usd_notional_per_trade <= 0
    ):
        return "the per-trade maximum USD notional must be a positive Decimal"
    notional = (eur_amount * fx.rate).quantize(_NOTIONAL_QUANTUM, rounding=ROUND_DOWN)
    if notional < minimum_usd_notional:
        return (
            f"the converted notional ({notional} USD) is below the broker's own minimum "
            f"order size ({minimum_usd_notional} USD); nothing would be accepted"
        )
    if notional > maximum_usd_notional_per_trade:
        return (
            f"the converted notional ({notional} USD) exceeds this trade's own maximum "
            f"({maximum_usd_notional_per_trade} USD); refusing rather than silently capping it"
        )
    return notional


def portfolio_exposure_refusal(
    existing_open_notional: Decimal,
    new_trade_notional: Decimal,
    *,
    maximum_portfolio_notional: Decimal,
) -> str | None:
    """Refuse a new fractional trade that would push this path's own total open notional
    (across every still-open micro position, never just this one trade) past the
    portfolio-level exposure cap. `None` means the cap is respected.

    Pure: the caller is responsible for computing `existing_open_notional` from its own
    live positions (no such read exists yet -- see the module docstring and the design
    doc's deferred-work list)."""
    if existing_open_notional < 0 or new_trade_notional < 0:
        return "notional amounts must never be negative"
    total = existing_open_notional + new_trade_notional
    if total > maximum_portfolio_notional:
        return (
            f"this trade would bring total open micro-trade notional to {total} USD, "
            f"exceeding the portfolio exposure cap of {maximum_portfolio_notional} USD"
        )
    return None


def portfolio_loss_limit_refusal(
    realized_and_unrealized_loss: Decimal, *, maximum_portfolio_loss: Decimal
) -> str | None:
    """Refuse further trading once this path's own running loss (realized plus unrealized,
    expressed as a non-negative `Decimal` -- the caller passes the MAGNITUDE of the loss,
    never a signed P&L) has reached or passed the Owner's own portfolio-level loss limit.
    `None` means the limit has not yet been reached.

    This is a portfolio-level backstop distinct from, and in addition to, the existing
    per-trade `maximum_planned_loss_per_trade` risk-contract check the M084 core already
    enforces for every entry -- it answers "has this WHOLE path lost too much, cumulatively,
    regardless of any single trade's own approved risk", which no existing check answers.
    """
    if realized_and_unrealized_loss < 0:
        return "a loss magnitude must never be negative; pass the absolute value of the loss"
    if realized_and_unrealized_loss >= maximum_portfolio_loss:
        return (
            f"cumulative loss ({realized_and_unrealized_loss} USD) has reached the "
            f"portfolio loss limit ({maximum_portfolio_loss} USD); no further micro trades "
            "may be opened until the Owner reviews and resets this path"
        )
    return None
