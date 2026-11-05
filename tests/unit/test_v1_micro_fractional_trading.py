"""V1 MICRO PAPER TRADING (10-20 EUR equivalent) -- pure domain tests for the isolated
sizing/FX-verification module. See `docs/v1-micro-paper-eur/design.md` for what this module
does and, explicitly, does not implement (no FX provider, no broker wiring).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.micro_fractional_trading import (
    ALPACA_MINIMUM_USD_NOTIONAL,
    EurUsdFxQuote,
    fractional_notional_for_eur_target,
    fx_quote_refusal,
    portfolio_exposure_refusal,
    portfolio_loss_limit_refusal,
)

_NOW = datetime(2026, 10, 20, 14, 30, tzinfo=UTC)


def _quote(
    *,
    rate: Decimal = Decimal("1.08"),
    source: str = "test-provider",
    as_of: datetime = _NOW,
    fetched_at: datetime = _NOW,
) -> EurUsdFxQuote:
    return EurUsdFxQuote(rate=rate, source=source, as_of=as_of, fetched_at=fetched_at)


# ---------------------------------------------------------------------------
# fx_quote_refusal
# ---------------------------------------------------------------------------


def test_a_fresh_valid_quote_is_not_refused() -> None:
    quote = _quote(as_of=_NOW - timedelta(seconds=5))
    assert fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60) is None


def test_a_stale_quote_is_refused() -> None:
    quote = _quote(as_of=_NOW - timedelta(seconds=120))
    refusal = fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60)
    assert refusal is not None
    assert "stale" in refusal or "exceeding" in refusal
    assert "test-provider" in refusal


def test_a_quote_exactly_at_the_staleness_boundary_is_not_refused() -> None:
    quote = _quote(as_of=_NOW - timedelta(seconds=60))
    assert fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60) is None


def test_a_quote_one_second_past_the_boundary_is_refused() -> None:
    quote = _quote(as_of=_NOW - timedelta(seconds=61))
    assert fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60) is not None


def test_a_quote_from_the_future_is_refused_never_treated_as_extra_fresh() -> None:
    quote = _quote(as_of=_NOW + timedelta(seconds=5))
    refusal = fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60)
    assert refusal is not None
    assert "future" in refusal


def test_a_blank_source_is_refused() -> None:
    quote = _quote(source="   ")
    assert fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60) is not None


def test_a_zero_or_negative_rate_is_refused() -> None:
    assert (
        fx_quote_refusal(_quote(rate=Decimal("0")), now=_NOW, max_staleness_seconds=60) is not None
    )
    assert (
        fx_quote_refusal(_quote(rate=Decimal("-1.08")), now=_NOW, max_staleness_seconds=60)
        is not None
    )


def test_a_naive_as_of_timestamp_is_refused() -> None:
    quote = _quote(as_of=datetime(2026, 10, 20, 14, 30))  # no tzinfo
    assert fx_quote_refusal(quote, now=_NOW, max_staleness_seconds=60) is not None


# ---------------------------------------------------------------------------
# fractional_notional_for_eur_target
# ---------------------------------------------------------------------------


def test_a_typical_15_eur_target_converts_and_rounds_down_to_cents() -> None:
    result = fractional_notional_for_eur_target(
        Decimal("15"),
        _quote(rate=Decimal("1.0847")),
        maximum_usd_notional_per_trade=Decimal("25.00"),
        asset_fractionable=True,
    )
    assert isinstance(result, Decimal)
    # 15 * 1.0847 = 16.2705 -> rounded DOWN to cents = 16.27
    assert result == Decimal("16.27")


def test_rounding_is_always_down_never_up_past_the_approved_eur_amount() -> None:
    result = fractional_notional_for_eur_target(
        Decimal("10"),
        _quote(rate=Decimal("1.0999")),
        maximum_usd_notional_per_trade=Decimal("50.00"),
        asset_fractionable=True,
    )
    assert isinstance(result, Decimal)
    # 10 * 1.0999 = 10.999 -> DOWN to 10.99, never 11.00
    assert result == Decimal("10.99")


def test_a_non_fractionable_asset_is_refused_before_any_math() -> None:
    result = fractional_notional_for_eur_target(
        Decimal("15"),
        _quote(),
        maximum_usd_notional_per_trade=Decimal("25.00"),
        asset_fractionable=False,
    )
    assert isinstance(result, str)
    assert "not fractionable" in result


def test_a_non_positive_eur_amount_is_refused() -> None:
    for bad in (Decimal("0"), Decimal("-5")):
        result = fractional_notional_for_eur_target(
            bad,
            _quote(),
            maximum_usd_notional_per_trade=Decimal("25.00"),
            asset_fractionable=True,
        )
        assert isinstance(result, str)


def test_below_the_alpaca_minimum_notional_is_refused() -> None:
    result = fractional_notional_for_eur_target(
        Decimal("0.50"),
        _quote(rate=Decimal("1.00")),
        maximum_usd_notional_per_trade=Decimal("25.00"),
        asset_fractionable=True,
    )
    assert isinstance(result, str)
    assert "minimum" in result
    assert str(ALPACA_MINIMUM_USD_NOTIONAL) in result


def test_above_the_per_trade_maximum_is_refused_never_silently_capped() -> None:
    result = fractional_notional_for_eur_target(
        Decimal("50"),
        _quote(rate=Decimal("1.08")),
        maximum_usd_notional_per_trade=Decimal("20.00"),
        asset_fractionable=True,
    )
    assert isinstance(result, str)
    assert "exceeds" in result


def test_a_non_positive_per_trade_maximum_is_refused() -> None:
    result = fractional_notional_for_eur_target(
        Decimal("15"),
        _quote(),
        maximum_usd_notional_per_trade=Decimal("0"),
        asset_fractionable=True,
    )
    assert isinstance(result, str)


def test_never_returns_a_whole_share_quantity_only_ever_a_notional_decimal() -> None:
    """There is no share-count rounding step anywhere in this function -- the result, when
    accepted, is always a dollar notional with at most 2 decimal places."""
    result = fractional_notional_for_eur_target(
        Decimal("20"),
        _quote(rate=Decimal("1.0847")),
        maximum_usd_notional_per_trade=Decimal("25.00"),
        asset_fractionable=True,
    )
    assert isinstance(result, Decimal)
    assert result.as_tuple().exponent >= -2, "never more than 2 decimal places"


# ---------------------------------------------------------------------------
# portfolio_exposure_refusal
# ---------------------------------------------------------------------------


def test_exposure_within_the_cap_is_not_refused() -> None:
    assert (
        portfolio_exposure_refusal(
            Decimal("30"), Decimal("15"), maximum_portfolio_notional=Decimal("100")
        )
        is None
    )


def test_exposure_exactly_at_the_cap_is_not_refused() -> None:
    assert (
        portfolio_exposure_refusal(
            Decimal("85"), Decimal("15"), maximum_portfolio_notional=Decimal("100")
        )
        is None
    )


def test_exposure_over_the_cap_is_refused() -> None:
    refusal = portfolio_exposure_refusal(
        Decimal("90"), Decimal("15"), maximum_portfolio_notional=Decimal("100")
    )
    assert refusal is not None
    assert "105" in refusal
    assert "100" in refusal


def test_negative_notional_inputs_are_refused() -> None:
    assert (
        portfolio_exposure_refusal(
            Decimal("-1"), Decimal("15"), maximum_portfolio_notional=Decimal("100")
        )
        is not None
    )


# ---------------------------------------------------------------------------
# portfolio_loss_limit_refusal
# ---------------------------------------------------------------------------


def test_loss_below_the_limit_is_not_refused() -> None:
    assert portfolio_loss_limit_refusal(Decimal("10"), maximum_portfolio_loss=Decimal("50")) is None


def test_loss_at_the_limit_is_refused_fail_closed_at_the_boundary() -> None:
    refusal = portfolio_loss_limit_refusal(Decimal("50"), maximum_portfolio_loss=Decimal("50"))
    assert refusal is not None


def test_loss_over_the_limit_is_refused() -> None:
    refusal = portfolio_loss_limit_refusal(Decimal("75"), maximum_portfolio_loss=Decimal("50"))
    assert refusal is not None
    assert "75" in refusal
    assert "50" in refusal


def test_a_negative_loss_magnitude_is_refused_caller_must_pass_absolute_value() -> None:
    assert (
        portfolio_loss_limit_refusal(Decimal("-10"), maximum_portfolio_loss=Decimal("50"))
        is not None
    )
