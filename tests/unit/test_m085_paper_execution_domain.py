"""MILESTONE-085 domain: what cannot be expressed, and what cannot be inferred.

These tests are about ABSENCE as much as behaviour. A product whose job is to
refuse is only as good as the things it makes unrepresentable, so most of what
follows constructs something forbidden and requires a refusal -- a sell, a
fractional quantity, an extended-hours order, an authorization that outlives its
expiry, a permission that covers two orders, a state machine edge that would turn
an ambiguous dispatch into a second one.

NO NETWORK AND NO DATABASE. Everything here is pure domain, so a failure names a
rule rather than an environment.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from tests.unit._m085_fakes import a_policy, a_provenance

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    ALLOWED_PAPER_TRANSITIONS,
    CLIENT_ORDER_ID_PREFIX,
    MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH,
    MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS,
    MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS,
    NO_AUTHORIZATION_TIME_BASIS,
    NO_DECISION_TIME_BASIS,
    NO_INTENT_TIME_BASIS,
    NO_PROPOSAL_TIME_BASIS,
    NOT_FOUND_ALONE_RESOLVES_UNKNOWN,
    PAPER_ENDPOINT_HOST,
    RECONCILIATION_UNKNOWN_POLICY,
    TERMINAL_PAPER_STATES,
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionPolicy,
    M084TimeProvenance,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    PaperOrderRequest,
    authorize_submission,
    bind_intent_time_basis,
    build_submission_preview,
    derive_client_order_id,
    is_paper_transition_allowed,
    m084_deadline_refusal_on_broker_time,
    m084_provenance_refusal,
    request_fingerprint,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovedOrderIntent,
    SubmissionState,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, BrokerTimeBasis

_NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
_DIGEST = "a" * 64


def _policy(**overrides: object) -> ExecutionPolicy:
    """The intent's configuration policy, with a UTC entry window that contains `_NOW`.

    `_NOW` is 08:00 in New York, before the acceptance window, so these pure-domain
    tests state a window around their own clock rather than moving the clock.
    """
    arguments: dict[str, object] = {
        "operator_timezone": "UTC",
        "earliest_entry_time": time(9, 0),
        "latest_entry_time": time(20, 0),
        "mandatory_liquidation_time": time(20, 30),
    }
    arguments.update(overrides)
    return a_policy(**arguments)


def _binding() -> dict[str, object]:
    """The preview-binding copies a hand-built authorization must carry."""
    policy = _policy()
    return {
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "order_type": OrderType.LIMIT,
        "limit_price": Decimal("4.00"),
        "maximum_notional": policy.maximum_notional,
        "quote_bid": Decimal("199.95"),
        "quote_ask": Decimal("200.10"),
        "quote_captured_at": _NOW - timedelta(seconds=5),
        "configuration_governance_id": policy.configuration_governance_id,
        "configuration_version": policy.configuration_version,
        "policy_fingerprint": policy.fingerprint,
        "preview_binding_fingerprint": _DIGEST,
    }


def _basis(
    at: datetime = _NOW,
    *,
    broker_offset: timedelta = timedelta(0),
    round_trip: timedelta = timedelta(0),
) -> BrokerTimeBasis:
    """A measured basis: host readings bracketing `at`, the broker `broker_offset` ahead."""
    return BrokerTimeBasis(
        host_requested_at=at - round_trip,
        host_at=at,
        broker_earliest_at=at + broker_offset - round_trip,
        broker_latest_at=at + broker_offset,
    )


def an_intent(**overrides: object) -> ApprovedOrderIntent:
    defaults: dict[str, object] = {
        "intent_governance_id": "INT-1",
        "proposal_governance_id": "PRP-1",
        "proposal_version": 1,
        "approved_fingerprint": _DIGEST,
        "decision_governance_id": "DEC-1",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "order_type": OrderType.LIMIT,
        "limit_price": Decimal("4.00"),
        "currency": "USD",
        "time_in_force": "DAY",
        "mandatory_liquidation_at": _NOW + timedelta(hours=3),
        "account_mode_required": "PREPARATION",
        "idempotency_key": "IDEM-1",
        "configuration_governance_id": "CFG-1",
        "configuration_version": 1,
        "evaluation_context_id": "ECX-1",
        "created_at": _NOW - timedelta(minutes=1),
        "expires_at": _NOW + timedelta(hours=1),
        "submission_state": SubmissionState.NOT_SUBMITTED,
    }
    defaults.update(overrides)
    return ApprovedOrderIntent(**defaults)  # type: ignore[arg-type]


def an_account(**overrides: object) -> PaperAccountSnapshot:
    defaults: dict[str, object] = {
        "snapshot_id": "SNP-1",
        "environment": PaperEnvironment.PAPER,
        "endpoint_host": PAPER_ENDPOINT_HOST,
        "account_reference": "ref:abc123",
        "account_status": "ACTIVE",
        "currency": "USD",
        "buying_power": Decimal("100000"),
        "cash": Decimal("100000"),
        "equity": Decimal("100000"),
        "multiplier": "4",
        "shorting_enabled": True,
        "trading_blocked": False,
        "transfers_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "captured_at": _NOW,
    }
    defaults.update(overrides)
    return PaperAccountSnapshot(**defaults)  # type: ignore[arg-type]


def a_preview(**overrides: object):  # noqa: ANN201 - returns SubmissionPreview
    arguments: dict[str, object] = {
        "preview_id": "PVW-1",
        "intent": an_intent(),
        "account": an_account(),
        "preview_version": 1,
        "market_is_open": True,
        "market_next_open": None,
        "market_next_close": _NOW + timedelta(hours=3),
        "quote_bid": Decimal("199.95"),
        "quote_ask": Decimal("200.10"),
        "quote_captured_at": _NOW - timedelta(seconds=5),
        "quote_source": "alpaca-iex",
        "asset_tradable": True,
        "asset_status": "active",
        "asset_class": "us_equity",
        "asset_exchange": "NASDAQ",
        "asset_fractionable": True,
        "policy": _policy(),
        "existing_position_quantity": 0,
        "execution_kill_switch_engaged": False,
        "created_at": _NOW,
        "broker_now": BoundedInstant(earliest=_NOW, latest=_NOW),
    }
    arguments.update(overrides)
    if "m084_provenance" not in overrides:
        arguments["m084_provenance"] = a_provenance(arguments["intent"])  # type: ignore[arg-type]
    return build_submission_preview(**arguments)  # type: ignore[arg-type]


class TestTheOrderRequestCannotExpressWhatIsForbidden:
    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"side": "SELL"}, "long-only"),
            ({"side": "buy"}, "long-only"),
            ({"quantity": 0}, "positive"),
            ({"quantity": -1}, "positive"),
            ({"quantity": True}, "must be an int"),
            ({"time_in_force": "GTC"}, "DAY"),
            ({"time_in_force": "day"}, "DAY"),
            ({"extended_hours": True}, "extended-hours"),
            ({"symbol": "aapl"}, "upper-case"),
            ({"symbol": " AAPL"}, "upper-case"),
            ({"client_order_id": ""}, "non-empty"),
        ],
    )
    def test_a_forbidden_request_is_refused(
        self, override: dict[str, object], fragment: str
    ) -> None:
        arguments: dict[str, object] = {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "order_type": OrderType.LIMIT,
            "limit_price": Decimal("4.00"),
            "time_in_force": "DAY",
            "extended_hours": False,
            "client_order_id": "m085-x",
        }
        arguments.update(override)
        with pytest.raises(ValueError, match=fragment):
            PaperOrderRequest(**arguments)  # type: ignore[arg-type]

    def test_a_fractional_quantity_is_not_even_representable(self) -> None:
        # Alpaca's fractional-order rules are removed from the reachable surface
        # rather than handled: the type takes an int.
        with pytest.raises(ValueError, match="must be an int"):
            PaperOrderRequest(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("0.5"),  # type: ignore[arg-type]
                order_type=OrderType.LIMIT,
                limit_price=Decimal("4.00"),
                time_in_force="DAY",
                extended_hours=False,
                client_order_id="m085-x",
            )

    def test_a_limit_order_without_a_price_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must carry a limit_price"):
            PaperOrderRequest(
                symbol="AAPL",
                side="BUY",
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=None,
                time_in_force="DAY",
                extended_hours=False,
                client_order_id="m085-x",
            )

    def test_a_market_order_has_no_knowable_cost_ceiling(self) -> None:
        # None rather than an estimate. A guessed ceiling that a caller then
        # enforces would be a limit in name only.
        request = PaperOrderRequest(
            symbol="AAPL",
            side="BUY",
            quantity=1,
            order_type=OrderType.MARKET,
            limit_price=None,
            time_in_force="DAY",
            extended_hours=False,
            client_order_id="m085-x",
        )
        assert request.notional_ceiling is None

    def test_a_limit_order_ceiling_is_exact_decimal_arithmetic(self) -> None:
        request = PaperOrderRequest(
            symbol="AAPL",
            side="BUY",
            quantity=3,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("1.10"),
            time_in_force="DAY",
            extended_hours=False,
            client_order_id="m085-x",
        )
        assert request.notional_ceiling == Decimal("3.30")


class TestTheClientOrderIdIsDerivedNotGenerated:
    def test_it_is_a_pure_function_of_persisted_identity(self) -> None:
        first = derive_client_order_id(
            intent_governance_id="INT-1", account_reference="ref:a", approved_fingerprint=_DIGEST
        )
        second = derive_client_order_id(
            intent_governance_id="INT-1", account_reference="ref:a", approved_fingerprint=_DIGEST
        )
        assert first == second

    def test_a_different_account_yields_a_different_order_identity(self) -> None:
        # The same intent sent to another paper account must not collide with the
        # first one at the broker.
        assert derive_client_order_id(
            intent_governance_id="INT-1", account_reference="ref:a", approved_fingerprint=_DIGEST
        ) != derive_client_order_id(
            intent_governance_id="INT-1", account_reference="ref:b", approved_fingerprint=_DIGEST
        )

    def test_different_order_terms_yield_a_different_order_identity(self) -> None:
        assert derive_client_order_id(
            intent_governance_id="INT-1", account_reference="ref:a", approved_fingerprint="a" * 64
        ) != derive_client_order_id(
            intent_governance_id="INT-1", account_reference="ref:a", approved_fingerprint="b" * 64
        )

    def test_it_fits_the_broker_limit_and_the_storage_column(self) -> None:
        value = derive_client_order_id(
            intent_governance_id="I" * 64, account_reference="r" * 64, approved_fingerprint=_DIGEST
        )
        assert value.startswith(CLIENT_ORDER_ID_PREFIX)
        assert len(value) <= MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH
        assert len(value) <= 64

    def test_a_malformed_fingerprint_is_refused(self) -> None:
        with pytest.raises(ValueError, match="hex digest"):
            derive_client_order_id(
                intent_governance_id="INT-1",
                account_reference="ref:a",
                approved_fingerprint="NOTHEX",
            )


class TestTheFingerprintBindsMoreThanTheOrder:
    def _order(self, **overrides: object) -> PaperOrderRequest:
        arguments: dict[str, object] = {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "order_type": OrderType.LIMIT,
            "limit_price": Decimal("4.00"),
            "time_in_force": "DAY",
            "extended_hours": False,
            "client_order_id": "m085-x",
        }
        arguments.update(overrides)
        return PaperOrderRequest(**arguments)  # type: ignore[arg-type]

    def _fingerprint(self, **overrides: object) -> str:
        arguments: dict[str, object] = {
            "order": self._order(),
            "account_reference": "ref:a",
            "endpoint_host": PAPER_ENDPOINT_HOST,
            "intent_governance_id": "INT-1",
            "approved_fingerprint": _DIGEST,
            "policy_fingerprint": _policy().fingerprint,
        }
        arguments.update(overrides)
        return request_fingerprint(**arguments)  # type: ignore[arg-type]

    def test_it_is_stable_for_identical_inputs(self) -> None:
        assert self._fingerprint() == self._fingerprint()

    @pytest.mark.parametrize(
        "override",
        [
            {"account_reference": "ref:somebody-else"},
            {"intent_governance_id": "INT-2"},
            {"approved_fingerprint": "b" * 64},
            # Corrective pass (D1): the send-time policy is part of what is authorized.
            {"policy_fingerprint": _policy(maximum_capital_per_trade=Decimal("6")).fingerprint},
            {"policy_fingerprint": _policy(maximum_market_data_age_seconds=61).fingerprint},
        ],
    )
    def test_changing_any_binding_changes_the_fingerprint(
        self, override: dict[str, object]
    ) -> None:
        assert self._fingerprint() != self._fingerprint(**override)

    @pytest.mark.parametrize(
        "order_override",
        [
            {"quantity": 2},
            {"limit_price": Decimal("4.01")},
            {"symbol": "MSFT"},
            {"order_type": OrderType.MARKET, "limit_price": None},
        ],
    )
    def test_changing_any_order_term_changes_the_fingerprint(
        self, order_override: dict[str, object]
    ) -> None:
        assert self._fingerprint() != self._fingerprint(order=self._order(**order_override))

    def test_a_trailing_zero_on_the_price_is_a_different_fingerprint(self) -> None:
        # Decimal("4.00") and Decimal("4.0") are numerically equal but are not the
        # same written price. The fingerprint follows the written form, so a
        # re-typed price cannot silently reuse an old authorization.
        assert self._fingerprint(
            order=self._order(limit_price=Decimal("4.00"))
        ) != self._fingerprint(order=self._order(limit_price=Decimal("4.0")))

    def test_a_live_endpoint_cannot_be_fingerprinted_at_all(self) -> None:
        with pytest.raises(ValueError, match=PAPER_ENDPOINT_HOST):
            self._fingerprint(endpoint_host="api.alpaca.markets")


class TestThePreviewCollectsEveryRefusal:
    def test_a_clean_preview_is_authorizable(self) -> None:
        preview = a_preview()
        assert preview.refusals == ()
        assert preview.is_authorizable is True

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"execution_kill_switch_engaged": True}, "kill switch"),
            ({"account": an_account(trading_blocked=True)}, "does not permit orders"),
            ({"account": an_account(account_blocked=True)}, "does not permit orders"),
            ({"account": an_account(account_status="INACTIVE")}, "does not permit orders"),
            ({"account": an_account(trade_suspended_by_user=True)}, "does not permit orders"),
            ({"policy": _policy(watchlist=("MSFT",))}, "not on the approved watchlist"),
            ({"asset_tradable": False}, "not tradable"),
            ({"asset_status": "inactive"}, "not an active asset"),
            ({"asset_class": "crypto"}, "not a US equity"),
            ({"existing_position_quantity": 5}, "position of 5 already exists"),
            ({"policy": _policy(maximum_capital_per_trade=Decimal("1"))}, "exceeds the limit"),
            ({"account": an_account(buying_power=Decimal("1"))}, "exceeds paper buying power"),
            ({"quote_captured_at": None}, "no quote was captured"),
            ({"policy": _policy(maximum_market_data_age_seconds=1)}, "older than the"),
            (
                {"quote_captured_at": _NOW + timedelta(seconds=11)},
                "dated after the latest possible",
            ),
        ],
    )
    def test_each_condition_produces_its_own_refusal(
        self, override: dict[str, object], fragment: str
    ) -> None:
        preview = a_preview(**override)
        assert preview.is_authorizable is False
        assert any(fragment in reason for reason in preview.refusals), preview.refusals

    def test_all_refusals_are_reported_at_once(self) -> None:
        # An operator should not have to fix these one round trip at a time.
        preview = a_preview(
            execution_kill_switch_engaged=True,
            asset_tradable=False,
            policy=_policy(watchlist=("MSFT",)),
        )
        assert len(preview.refusals) >= 3

    def test_a_quote_after_the_latest_possible_broker_instant_is_refused(self) -> None:
        # A quote dated after every instant the broker's clock could now be
        # showing is inconsistent evidence, not a maximally fresh quote.
        preview = a_preview(quote_captured_at=_NOW + timedelta(seconds=1))
        assert any("dated after the latest possible" in reason for reason in preview.refusals)
        assert preview.is_authorizable is False

    def test_an_age_interval_straddling_the_limit_is_refused(self) -> None:
        # Age bounded by [59s, 61s] against a 60s ceiling. The limit holds at one
        # end and not the other, so it does not hold THROUGHOUT the justified
        # interval and the preview must refuse. Testing the midpoint, or the
        # youngest end, would permit an order whose quote may already be stale.
        quote_at = _NOW - timedelta(seconds=61)
        preview = a_preview(
            quote_captured_at=quote_at,
            broker_now=BoundedInstant(earliest=_NOW - timedelta(seconds=2), latest=_NOW),
        )
        assert any("older than the 60s limit" in reason for reason in preview.refusals)
        assert preview.is_authorizable is False

    def test_an_age_interval_wholly_inside_the_limit_is_accepted(self) -> None:
        # The same width, moved so that BOTH ends satisfy the ceiling.
        quote_at = _NOW - timedelta(seconds=59)
        assert a_preview(
            quote_captured_at=quote_at,
            broker_now=BoundedInstant(earliest=_NOW - timedelta(seconds=2), latest=_NOW),
        ).is_authorizable

    def test_a_session_close_inside_the_interval_is_treated_as_passed(self) -> None:
        # The close falls between the earliest and latest instants the broker's
        # clock could now be showing: it MIGHT already have passed, so it counts
        # as passed.
        close = _NOW + timedelta(seconds=1)
        preview = a_preview(
            market_next_close=close,
            broker_now=BoundedInstant(earliest=_NOW, latest=_NOW + timedelta(seconds=2)),
        )
        assert any("market session is closed" in reason for reason in preview.refusals)
        assert preview.is_authorizable is False

    def test_a_quote_inside_the_measured_uncertainty_is_not_refused(self) -> None:
        # The replaced model refused this: it compared the quote against a single
        # instant, so any quote arriving during the fetch round trips looked
        # future-dated. The allowance here is the MEASURED round trip, not a
        # constant -- widen the bound and the same quote becomes usable.
        quote_at = _NOW + timedelta(milliseconds=400)
        assert not a_preview(quote_captured_at=quote_at).is_authorizable
        assert a_preview(
            quote_captured_at=quote_at,
            broker_now=BoundedInstant(earliest=_NOW, latest=_NOW + timedelta(milliseconds=500)),
        ).is_authorizable

    def test_quote_at_evaluation_is_fresh_but_future_quote_is_not(self) -> None:
        assert a_preview(quote_captured_at=_NOW).is_authorizable
        assert not a_preview(quote_captured_at=_NOW + timedelta(microseconds=1)).is_authorizable

    def test_an_expired_intent_is_refused(self) -> None:
        preview = a_preview(intent=an_intent(expires_at=_NOW - timedelta(seconds=1)))
        assert any("has expired" in reason for reason in preview.refusals)

    def test_a_passed_liquidation_deadline_is_refused(self) -> None:
        preview = a_preview(intent=an_intent(mandatory_liquidation_at=_NOW - timedelta(seconds=1)))
        assert any("liquidation deadline" in reason for reason in preview.refusals)

    def test_a_market_order_cannot_be_authorized_under_a_notional_limit(self) -> None:
        preview = a_preview(
            intent=an_intent(order_type=OrderType.MARKET, limit_price=None),
        )
        assert any("no knowable cost ceiling" in reason for reason in preview.refusals)

    def test_the_preview_carries_the_derived_order_identity(self) -> None:
        preview = a_preview()
        assert preview.order.client_order_id == derive_client_order_id(
            intent_governance_id="INT-1",
            account_reference="ref:abc123",
            approved_fingerprint=_DIGEST,
        )


class TestAuthorizationIsNarrowAndExpiring:
    def test_a_refused_preview_cannot_be_authorized(self) -> None:
        with pytest.raises(ValueError, match="cannot be authorized"):
            authorize_submission(
                authorization_id="AUT-1",
                preview=a_preview(execution_kill_switch_engaged=True),
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=60,
                time_basis=_basis(_NOW),
            )

    @pytest.mark.parametrize("validity", [0, -1])
    def test_a_non_positive_validity_is_refused(self, validity: int) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            authorize_submission(
                authorization_id="AUT-1",
                preview=a_preview(),
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=validity,
                time_basis=_basis(_NOW),
            )

    def test_there_is_no_way_to_express_an_unexpiring_authorization(self) -> None:
        # `validity_seconds` has no sentinel meaning "forever": every value
        # produces an expiry strictly after the authorization instant.
        authorization = authorize_submission(
            authorization_id="AUT-1",
            preview=a_preview(),
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=1,
            time_basis=_basis(_NOW),
        )
        assert authorization.expires_at > authorization.authorized_at
        assert authorization.is_expired_at(authorization.expires_at) is True

    def test_a_fresh_authorization_permits_its_own_exact_dispatch(self) -> None:
        preview = a_preview()
        authorization = authorize_submission(
            authorization_id="AUT-1",
            preview=preview,
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=60,
            time_basis=_basis(_NOW),
        )
        assert (
            authorization.refusal_against(
                request_fingerprint_now=preview.request_fingerprint,
                account_reference_now=preview.account_reference,
                instant=_NOW,
                broker_now=BoundedInstant(earliest=_NOW, latest=_NOW),
            )
            is None
        )

    @pytest.mark.parametrize(
        ("mutation", "fragment"),
        [
            ({"request_fingerprint_now": "b" * 64}, "order changed after it was authorized"),
            ({"account_reference_now": "ref:other"}, "different paper account"),
            ({"instant": _NOW + timedelta(seconds=61)}, "has expired"),
        ],
    )
    def test_every_material_change_removes_the_permission(
        self, mutation: dict[str, object], fragment: str
    ) -> None:
        preview = a_preview()
        authorization = authorize_submission(
            authorization_id="AUT-1",
            preview=preview,
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=60,
            time_basis=_basis(_NOW),
        )
        arguments: dict[str, object] = {
            "request_fingerprint_now": preview.request_fingerprint,
            "account_reference_now": preview.account_reference,
            "instant": _NOW,
            "broker_now": BoundedInstant(earliest=_NOW, latest=_NOW),
        }
        arguments.update(mutation)
        refusal = authorization.refusal_against(**arguments)  # type: ignore[arg-type]
        assert refusal is not None
        assert fragment in refusal

    def test_a_basis_cannot_be_checked_without_broker_time(self) -> None:
        # The broker check must not be skippable. A caller that omits the broker's
        # instant does not fall back to the weaker host-only answer; it is refused,
        # so there is no call shape that quietly drops the stronger guarantee.
        authorization = authorize_submission(
            authorization_id="AUT-1",
            preview=a_preview(),
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=60,
            time_basis=_basis(_NOW),
        )
        refusal = authorization.refusal_against(
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            instant=_NOW,
        )
        assert refusal is not None
        assert "without the broker's current instant" in refusal

    def test_an_authorization_without_a_basis_cannot_be_mapped(self) -> None:
        # A row written before the basis existed is neither trusted nor guessed at.
        legacy = ExecutionAuthorization(
            authorization_id="AUT-OLD",
            intent_governance_id="INT-1",
            preview_id="PVW-1",
            preview_version=1,
            request_fingerprint=_DIGEST,
            account_reference="ref:abc123",
            client_order_id="m085-x",
            authorized_by="owner",
            authorized_at=_NOW,
            expires_at=_NOW + timedelta(seconds=60),
            consumed_at=None,
            consumed_by_attempt_id=None,
            **_binding(),  # type: ignore[arg-type]
        )
        assert legacy.has_broker_time_basis is False
        with pytest.raises(ValueError, match="no broker time basis"):
            legacy.on_broker_timeline(_NOW)

    def test_the_basis_maps_a_host_instant_by_the_measured_difference(self) -> None:
        # The mapping is the broker's reported timestamp minus this host's reading
        # AFTER the response -- the smallest offset the measured round trip allows.
        # SUPERSEDED: this comment used to say "two readings taken together".
        authorization = authorize_submission(
            authorization_id="AUT-1",
            preview=a_preview(),
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=60,
            # Host reads _NOW before and _NOW+1s after; broker stamped _NOW+8s at
            # the latest, so its earliest is _NOW+7s and the offset is exactly +6s.
            time_basis=_basis(
                _NOW + timedelta(seconds=1),
                broker_offset=timedelta(seconds=7),
                round_trip=timedelta(seconds=1),
            ),
        )
        assert authorization.on_broker_timeline(_NOW) == _NOW + timedelta(seconds=6)
        assert authorization.on_broker_timeline(authorization.expires_at) == _NOW + timedelta(
            seconds=66
        )

    def test_a_consumed_authorization_permits_nothing_further(self) -> None:
        preview = a_preview()
        base = authorize_submission(
            authorization_id="AUT-1",
            preview=preview,
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=60,
            time_basis=_basis(_NOW),
        )
        consumed = replace(
            base, consumed_at=_NOW + timedelta(seconds=1), consumed_by_attempt_id="ATT-1"
        )
        assert consumed.is_consumed is True
        refusal = consumed.refusal_against(
            request_fingerprint_now=preview.request_fingerprint,
            account_reference_now=preview.account_reference,
            instant=_NOW + timedelta(seconds=2),
        )
        assert refusal is not None
        assert "already been used" in refusal

    def test_consumption_must_record_what_consumed_it(self) -> None:
        with pytest.raises(ValueError, match="set together"):
            ExecutionAuthorization(
                authorization_id="AUT-1",
                intent_governance_id="INT-1",
                preview_id="PVW-1",
                preview_version=1,
                request_fingerprint=_DIGEST,
                account_reference="ref:a",
                client_order_id="m085-x",
                authorized_by="owner",
                authorized_at=_NOW,
                expires_at=_NOW + timedelta(seconds=60),
                consumed_at=_NOW,
                consumed_by_attempt_id=None,
                **_binding(),  # type: ignore[arg-type]
            )

    def test_an_expiry_before_the_authorization_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must follow"):
            ExecutionAuthorization(
                authorization_id="AUT-1",
                intent_governance_id="INT-1",
                preview_id="PVW-1",
                preview_version=1,
                request_fingerprint=_DIGEST,
                account_reference="ref:a",
                client_order_id="m085-x",
                authorized_by="owner",
                authorized_at=_NOW,
                expires_at=_NOW,
                consumed_at=None,
                consumed_by_attempt_id=None,
                **_binding(),  # type: ignore[arg-type]
            )


def _legacy_authorization(**basis: datetime | None) -> ExecutionAuthorization:
    return ExecutionAuthorization(
        authorization_id="AUT-OLD",
        intent_governance_id="INT-1",
        preview_id="PVW-1",
        preview_version=1,
        request_fingerprint=_DIGEST,
        account_reference="ref:abc123",
        client_order_id="m085-x",
        authorized_by="owner",
        authorized_at=_NOW,
        expires_at=_NOW + timedelta(seconds=60),
        consumed_at=None,
        consumed_by_attempt_id=None,
        **_binding(),  # type: ignore[arg-type]
        **basis,  # type: ignore[arg-type]
    )


class TestTheTwoTimeBasesHaveDistinctProvenance:
    """An authorization's basis and an intent's basis are measured in different acts."""

    def test_fetch_latency_does_not_move_the_mapped_authorization_expiry(self) -> None:
        # The command instant precedes a 120 s clock fetch; the broker's truthful
        # reply arrives as this host reads 120 s later. Paired with that later host
        # reading, the permission ends at the command instant plus its validity.
        authorization = authorize_submission(
            authorization_id="AUT-1",
            # A 300 s freshness limit, so the 120 s fetch does not already make the
            # preview too old to authorize (that refusal is tested on its own).
            preview=a_preview(policy=_policy(maximum_market_data_age_seconds=300)),
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=300,
            time_basis=BrokerTimeBasis(
                host_requested_at=_NOW,
                host_at=_NOW + timedelta(seconds=120),
                broker_earliest_at=_NOW + timedelta(seconds=120),
                broker_latest_at=_NOW + timedelta(seconds=240),
            ),
        )
        assert authorization.on_broker_timeline(authorization.expires_at) == _NOW + timedelta(
            seconds=300
        )

    def test_the_replaced_pre_fetch_pairing_is_no_longer_trusted(self) -> None:
        # The shape the defect wrote -- host reading equal to the pre-fetch command
        # instant, no interval -- would have mapped the same expiry 120 s later.
        legacy = _legacy_authorization(
            basis_host_at=_NOW, basis_broker_earliest_at=_NOW + timedelta(seconds=120)
        )
        assert legacy.time_basis is None
        assert legacy.has_broker_time_basis is False
        refusal = legacy.refusal_against(
            request_fingerprint_now=_DIGEST,
            account_reference_now="ref:abc123",
            instant=_NOW,
            broker_now=BoundedInstant(earliest=_NOW, latest=_NOW),
        )
        assert refusal == NO_AUTHORIZATION_TIME_BASIS

    def test_an_authorization_with_no_basis_at_all_is_not_dispatchable(self) -> None:
        refusal = _legacy_authorization().refusal_against(
            request_fingerprint_now=_DIGEST,
            account_reference_now="ref:abc123",
            instant=_NOW,
            broker_now=BoundedInstant(earliest=_NOW, latest=_NOW),
        )
        assert refusal == NO_AUTHORIZATION_TIME_BASIS

    def test_a_future_dated_authorization_cannot_be_mapped(self) -> None:
        with pytest.raises(ValueError, match="future-dated"):
            authorize_submission(
                authorization_id="AUT-1",
                preview=a_preview(),
                authorized_by="owner",
                authorized_at=_NOW + timedelta(seconds=1),
                validity_seconds=60,
                time_basis=_basis(_NOW),
            )

    @pytest.mark.parametrize("missing", ["basis_host_requested_at", "basis_broker_latest_at"])
    def test_half_an_interval_is_refused(self, missing: str) -> None:
        readings: dict[str, datetime | None] = {
            "basis_host_at": _NOW,
            "basis_broker_earliest_at": _NOW,
            "basis_host_requested_at": _NOW,
            "basis_broker_latest_at": _NOW,
        }
        readings[missing] = None
        with pytest.raises(ValueError, match="set together"):
            _legacy_authorization(**readings)

    def test_an_interval_without_the_readings_it_bounds_is_refused(self) -> None:
        with pytest.raises(ValueError, match="requires the basis readings"):
            _legacy_authorization(basis_host_requested_at=_NOW, basis_broker_latest_at=_NOW)

    def test_intent_evidence_cannot_be_attached_after_issuance(self) -> None:
        intent = an_intent()
        with pytest.raises(ValueError, match="after the fact"):
            bind_intent_time_basis(
                intent=intent,
                time_basis=_basis(intent.created_at + timedelta(minutes=5)),
                broker_endpoint_host=PAPER_ENDPOINT_HOST,
            )

    def test_intent_evidence_must_come_from_the_paper_host(self) -> None:
        intent = an_intent()
        with pytest.raises(ValueError, match="broker_endpoint_host"):
            bind_intent_time_basis(
                intent=intent,
                time_basis=_basis(intent.created_at),
                broker_endpoint_host="api.alpaca.markets",
            )

    @pytest.mark.parametrize(
        ("missing", "refusal"),
        [
            ("proposal", NO_PROPOSAL_TIME_BASIS),
            ("decision", NO_DECISION_TIME_BASIS),
            ("intent", NO_INTENT_TIME_BASIS),
        ],
    )
    def test_missing_evidence_for_any_act_refuses_the_preview(
        self, missing: str, refusal: str
    ) -> None:
        # Each deadline needs the basis of the act that wrote it; none is borrowed.
        provenance = replace(a_provenance(an_intent()), **{missing: None})
        preview = a_preview(m084_provenance=provenance)
        assert refusal in preview.refusals
        assert preview.is_authorizable is False

    def test_proposal_evidence_describing_another_proposal_refuses_the_preview(self) -> None:
        base = a_provenance(an_intent())
        other = a_provenance(an_intent(expires_at=_NOW + timedelta(hours=2)))
        preview = a_preview(m084_provenance=replace(base, proposal=other.proposal))
        assert any(
            "proposal-time broker basis does not describe this exact record (expires_at)" in r
            for r in preview.refusals
        ), preview.refusals

    def test_decision_evidence_describing_another_approval_refuses_the_preview(self) -> None:
        base = a_provenance(an_intent())
        other = a_provenance(an_intent(decision_governance_id="DEC-2"))
        preview = a_preview(m084_provenance=replace(base, decision=other.decision))
        assert any(
            "decision-time broker basis does not describe this exact record "
            "(decision_governance_id)" in r
            for r in preview.refusals
        ), preview.refusals

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"intent_governance_id": "INT-2"}, "intent_governance_id"),
            ({"approved_fingerprint": "b" * 64}, "approved_fingerprint"),
            ({"created_at": _NOW - timedelta(minutes=2)}, "created_at"),
            ({"expires_at": _NOW + timedelta(hours=2)}, "expires_at"),
            ({"mandatory_liquidation_at": _NOW + timedelta(hours=4)}, "mandatory_liquidation_at"),
        ],
    )
    def test_evidence_for_a_different_intent_refuses_the_preview(
        self, change: dict[str, object], field: str
    ) -> None:
        base = a_provenance(an_intent())
        other = a_provenance(an_intent(**change))
        preview = a_preview(m084_provenance=replace(base, intent=other.intent))
        assert preview.is_authorizable is False
        assert any(
            "does not describe this exact intent" in reason and f"({field})" in reason
            for reason in preview.refusals
        ), preview.refusals

    def test_the_intent_deadline_is_mapped_through_the_proposal_basis(self) -> None:
        # The proposal that wrote the deadline was evaluated while the host clock ran
        # an hour BEHIND the broker, so the stored host expiry (_NOW+1h) is _NOW+2h on
        # the broker's clock -- whatever the issuance basis says.
        intent = an_intent()
        provenance = a_provenance(intent, proposal_offset=timedelta(hours=1))
        just_before = _NOW + timedelta(hours=2) - timedelta(seconds=1)
        assert (
            m084_deadline_refusal_on_broker_time(
                intent=intent,
                provenance=provenance,
                broker_now=BoundedInstant(earliest=just_before, latest=just_before),
            )
            is None
        )
        at_it = _NOW + timedelta(hours=2)
        refusal = m084_deadline_refusal_on_broker_time(
            intent=intent,
            provenance=provenance,
            broker_now=BoundedInstant(earliest=at_it, latest=at_it),
        )
        assert refusal == "the approved intent has expired on the broker's clock"

    def test_the_mandatory_liquidation_deadline_is_mapped_too(self) -> None:
        intent = an_intent(expires_at=_NOW + timedelta(hours=5))
        at_liquidation = intent.mandatory_liquidation_at
        refusal = m084_deadline_refusal_on_broker_time(
            intent=intent,
            provenance=a_provenance(intent),
            broker_now=BoundedInstant(earliest=at_liquidation, latest=at_liquidation),
        )
        assert refusal == "the mandatory liquidation deadline has passed on the broker's clock"

    def test_missing_evidence_is_a_refusal_not_a_skipped_check(self) -> None:
        refusal = m084_deadline_refusal_on_broker_time(
            intent=an_intent(),
            provenance=M084TimeProvenance(proposal=None, decision=None, intent=None),
            broker_now=BoundedInstant(earliest=_NOW, latest=_NOW),
        )
        assert refusal == NO_PROPOSAL_TIME_BASIS

    def test_an_issuance_basis_cannot_rescue_deadlines_written_at_evaluation(self) -> None:
        # THE INDEPENDENT REVIEW'S CASE, IN MINIATURE. The proposal and approval were
        # recorded with host and broker agreeing; the proposal expires 5 minutes later.
        # The intent was issued an hour of REAL time later while the host clock read
        # barely a minute on -- the issuance basis measured a 59-minute offset.
        intent = an_intent(
            created_at=_NOW + timedelta(minutes=1),
            expires_at=_NOW + timedelta(minutes=5),
            mandatory_liquidation_at=_NOW + timedelta(minutes=10),
        )
        provenance = a_provenance(intent, intent_offset=timedelta(minutes=59))
        at_the_broker = _NOW + timedelta(hours=1)
        assert provenance.intent is not None
        # The replaced design mapped the deadline through the issuance basis and got
        # _NOW+64m -- still in the future at _NOW+60m. That is the defect.
        assert provenance.intent.time_basis.on_broker_timeline(intent.expires_at) > at_the_broker
        refusal = m084_deadline_refusal_on_broker_time(
            intent=intent,
            provenance=provenance,
            broker_now=BoundedInstant(earliest=at_the_broker, latest=at_the_broker),
        )
        assert (
            refusal == "the proposal had expired on the broker's clock when the intent was issued"
        )

    def test_an_approval_that_expired_before_issuance_is_refused(self) -> None:
        # The approval lasts an hour from its decision; the issuance happened two hours
        # of broker time after it, while the proposal itself was still current.
        intent = an_intent(
            expires_at=_NOW + timedelta(hours=5),
            mandatory_liquidation_at=_NOW + timedelta(hours=6),
        )
        refusal = m084_provenance_refusal(
            intent=intent, provenance=a_provenance(intent, intent_offset=timedelta(hours=2))
        )
        assert (
            refusal == "the approval had expired on the broker's clock when the intent was issued"
        )

    def test_an_approval_recorded_after_the_proposal_expired_is_refused(self) -> None:
        intent = an_intent(expires_at=_NOW + timedelta(seconds=30))
        refusal = m084_provenance_refusal(
            intent=intent, provenance=a_provenance(intent, decision_offset=timedelta(minutes=2))
        )
        assert refusal == (
            "the approval was recorded after the proposal had expired on the broker's clock"
        )

    def test_authorization_expiry_and_intent_deadlines_do_not_borrow_each_others_basis(
        self,
    ) -> None:
        # The proposal was evaluated with this host an hour behind the broker; the human
        # authorized with this host correct. Each basis decides only its own question.
        intent = an_intent()
        provenance = a_provenance(intent, proposal_offset=timedelta(hours=1))
        preview = a_preview(intent=intent, m084_provenance=provenance)
        # 3600 s: exactly as long as the intent lives on the host clock. Corrective pass:
        # an authorization may not outlive the intent, so 7200 s is now refused.
        authorization = authorize_submission(
            authorization_id="AUT-1",
            preview=preview,
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=3600,
            time_basis=_basis(_NOW),
        )
        thirty_minutes = BoundedInstant(
            earliest=_NOW + timedelta(minutes=30), latest=_NOW + timedelta(minutes=30)
        )
        ninety_minutes = BoundedInstant(
            earliest=_NOW + timedelta(minutes=90), latest=_NOW + timedelta(minutes=90)
        )
        # Through its own basis the intent expires at _NOW+2h, so at 90 minutes it has
        # not. Through the authorization's it would be _NOW+1h -- already passed -- which
        # is the borrowed answer this design refuses to use.
        assert (
            m084_deadline_refusal_on_broker_time(
                intent=intent, provenance=provenance, broker_now=ninety_minutes
            )
            is None
        )
        assert authorization.on_broker_timeline(intent.expires_at) == _NOW + timedelta(hours=1)
        # And the authorization's own expiry is not shifted by the intent's offset: it
        # ends at _NOW+1h on the broker's clock, although the intent lives to _NOW+2h.
        arguments: dict[str, object] = {
            "request_fingerprint_now": preview.request_fingerprint,
            "account_reference_now": preview.account_reference,
            "instant": _NOW,
        }
        assert authorization.refusal_against(**arguments, broker_now=thirty_minutes) is None  # type: ignore[arg-type]
        assert (
            authorization.refusal_against(**arguments, broker_now=ninety_minutes)  # type: ignore[arg-type]
            == "the authorization has expired on the broker's clock"
        )


class TestTheStateMachineIsClosed:
    def test_every_state_has_an_entry(self) -> None:
        assert set(ALLOWED_PAPER_TRANSITIONS) == set(PaperExecutionState)

    def test_every_terminal_state_has_no_outgoing_edge(self) -> None:
        for state in TERMINAL_PAPER_STATES:
            assert ALLOWED_PAPER_TRANSITIONS[state] == frozenset(), state

    def test_an_unknown_outcome_can_be_resolved_but_never_retried(self) -> None:
        # The edge that must NOT exist: going back to SUBMISSION_IN_PROGRESS would
        # be how an ambiguous dispatch became a second order.
        outgoing = ALLOWED_PAPER_TRANSITIONS[PaperExecutionState.SUBMISSION_UNKNOWN]
        assert PaperExecutionState.SUBMISSION_IN_PROGRESS not in outgoing
        assert PaperExecutionState.DISPATCH_CLAIMED not in outgoing
        assert PaperExecutionState.FILLED in outgoing
        assert PaperExecutionState.CANCELED in outgoing

    def test_a_cancel_request_can_still_lose_to_a_fill(self) -> None:
        outgoing = ALLOWED_PAPER_TRANSITIONS[PaperExecutionState.CANCEL_REQUESTED]
        assert PaperExecutionState.FILLED in outgoing
        assert PaperExecutionState.PARTIALLY_FILLED in outgoing

    def test_only_authorized_can_reach_dispatch_claimed(self) -> None:
        """A dispatch is claimed once, and only out of AUTHORIZED.

        AUTHORIZED -> DISPATCH_CLAIMED is the single entry into the attempt
        lifecycle. What must not exist is a SECOND way in: any other edge to
        DISPATCH_CLAIMED would be a claim made without a human authorization
        immediately behind it, or a re-claim of an attempt already in flight.
        """
        sources = [
            state
            for state, outgoing in ALLOWED_PAPER_TRANSITIONS.items()
            if PaperExecutionState.DISPATCH_CLAIMED in outgoing
        ]
        assert sources == [PaperExecutionState.AUTHORIZED]

    def test_the_transition_check_refuses_a_non_member(self) -> None:
        with pytest.raises(ValueError, match="PaperExecutionState"):
            is_paper_transition_allowed("DISPATCH_CLAIMED", PaperExecutionState.FILLED)  # type: ignore[arg-type]

    def test_a_terminal_attempt_requires_a_terminal_instant(self) -> None:
        with pytest.raises(ValueError, match="requires terminal_at"):
            ExecutionAttempt(
                attempt_id="ATT-1",
                intent_governance_id="INT-1",
                authorization_id="AUT-1",
                client_order_id="m085-x",
                request_fingerprint=_DIGEST,
                state=PaperExecutionState.FILLED,
                claimed_at=_NOW,
                submitted_at=None,
                acknowledged_at=None,
                terminal_at=None,
                broker_order_id=None,
                broker_status=None,
                filled_quantity=None,
                filled_avg_price=None,
                failure_code=None,
                failure_detail=None,
            )

    def test_a_non_terminal_attempt_may_not_carry_one(self) -> None:
        with pytest.raises(ValueError, match="only set for a terminal state"):
            ExecutionAttempt(
                attempt_id="ATT-1",
                intent_governance_id="INT-1",
                authorization_id="AUT-1",
                client_order_id="m085-x",
                request_fingerprint=_DIGEST,
                state=PaperExecutionState.PAPER_SUBMITTED,
                claimed_at=_NOW,
                submitted_at=None,
                acknowledged_at=None,
                terminal_at=_NOW,
                broker_order_id=None,
                broker_status=None,
                filled_quantity=None,
                filled_avg_price=None,
                failure_code=None,
                failure_detail=None,
            )

    def test_only_submission_unknown_reports_an_unknown_outcome(self) -> None:
        def attempt(state: PaperExecutionState) -> ExecutionAttempt:
            return ExecutionAttempt(
                attempt_id="ATT-1",
                intent_governance_id="INT-1",
                authorization_id="AUT-1",
                client_order_id="m085-x",
                request_fingerprint=_DIGEST,
                state=state,
                claimed_at=_NOW,
                submitted_at=None,
                acknowledged_at=None,
                terminal_at=_NOW if state in TERMINAL_PAPER_STATES else None,
                broker_order_id=None,
                broker_status=None,
                filled_quantity=None,
                filled_avg_price=None,
                failure_code=None,
                failure_detail=None,
            )

        assert attempt(PaperExecutionState.SUBMISSION_UNKNOWN).outcome_is_known is False
        assert attempt(PaperExecutionState.PAPER_ACCEPTED).outcome_is_known is True


class TestTheEnvironmentHasNoLiveMember:
    def test_paper_is_the_only_environment(self) -> None:
        # A milestone that cannot reach a live venue must not own a symbol for
        # one: a declared LIVE would be a value code could branch on.
        assert [member.value for member in PaperEnvironment] == ["PAPER"]

    def test_an_account_snapshot_cannot_name_another_host(self) -> None:
        with pytest.raises(ValueError, match=PAPER_ENDPOINT_HOST):
            an_account(endpoint_host="api.alpaca.markets")

    def test_an_account_snapshot_must_be_usd(self) -> None:
        with pytest.raises(ValueError, match="USD"):
            an_account(currency="EUR")

    def test_dispatchability_asks_only_about_the_account(self) -> None:
        # Narrow on purpose: combining the market, asset and policy checks in here
        # would let one of them pass by being forgotten.
        assert an_account().is_dispatchable is True
        assert an_account(shorting_enabled=True).is_dispatchable is True
        assert an_account(trading_blocked=True).is_dispatchable is False


class TestTheReconciliationPolicyIsBoundedAndPublished:
    def test_a_single_not_found_never_resolves_an_unknown(self) -> None:
        assert NOT_FOUND_ALONE_RESOLVES_UNKNOWN is False
        assert MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS >= 2

    def test_the_policy_requires_elapsed_time_as_well_as_observations(self) -> None:
        assert MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS >= 60

    def test_the_published_document_is_derived_from_the_enforced_constants(self) -> None:
        # Anti-vacuity: the authority package renders the mapping, the handler uses
        # the constants, and this is what keeps them from disagreeing.
        assert (
            RECONCILIATION_UNKNOWN_POLICY["minimum_consecutive_not_found_observations"]
            == MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS
        )
        assert (
            RECONCILIATION_UNKNOWN_POLICY["minimum_seconds_since_dispatch_before_not_found_counts"]
            == MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS
        )
        assert (
            RECONCILIATION_UNKNOWN_POLICY["not_found_alone_resolves_unknown"]
            is NOT_FOUND_ALONE_RESOLVES_UNKNOWN
        )
