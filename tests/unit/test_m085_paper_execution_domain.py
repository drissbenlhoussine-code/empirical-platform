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

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    ALLOWED_PAPER_TRANSITIONS,
    CLIENT_ORDER_ID_PREFIX,
    MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH,
    MAXIMUM_QUOTE_LEAD_SECONDS,
    MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS,
    MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS,
    NOT_FOUND_ALONE_RESOLVES_UNKNOWN,
    PAPER_ENDPOINT_HOST,
    RECONCILIATION_UNKNOWN_POLICY,
    TERMINAL_PAPER_STATES,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    PaperOrderRequest,
    authorize_submission,
    build_submission_preview,
    derive_client_order_id,
    is_paper_transition_allowed,
    request_fingerprint,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovedOrderIntent,
    SubmissionState,
)

_NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
_DIGEST = "a" * 64
_WATCHLIST = frozenset({"AAPL"})


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
        "approved_watchlist": _WATCHLIST,
        "maximum_notional": Decimal("5"),
        "quote_maximum_age_seconds": 60,
        "existing_position_quantity": 0,
        "execution_kill_switch_engaged": False,
        "created_at": _NOW,
    }
    arguments.update(overrides)
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
            ({"approved_watchlist": frozenset({"MSFT"})}, "not on the approved watchlist"),
            ({"asset_tradable": False}, "not tradable"),
            ({"asset_status": "inactive"}, "not an active asset"),
            ({"asset_class": "crypto"}, "not a US equity"),
            ({"existing_position_quantity": 5}, "position of 5 already exists"),
            ({"maximum_notional": Decimal("1")}, "exceeds the limit"),
            ({"account": an_account(buying_power=Decimal("1"))}, "exceeds paper buying power"),
            ({"quote_captured_at": None}, "no quote was captured"),
            ({"quote_maximum_age_seconds": 1}, "older than the"),
            ({"quote_captured_at": _NOW + timedelta(seconds=11)}, "dated after this preview"),
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
            approved_watchlist=frozenset({"MSFT"}),
        )
        assert len(preview.refusals) >= 3

    def test_a_quote_further_ahead_than_the_lead_bound_is_refused(self) -> None:
        # Beyond MAXIMUM_QUOTE_LEAD_SECONDS the two clocks genuinely disagree, and
        # that is still refused rather than treated as maximally fresh.
        preview = a_preview(
            quote_captured_at=_NOW + timedelta(seconds=MAXIMUM_QUOTE_LEAD_SECONDS + 1)
        )
        assert any("dated after this preview" in reason for reason in preview.refusals)
        assert preview.is_authorizable is False

    def test_a_quote_fetched_after_the_preview_instant_is_fresh_not_from_the_future(self) -> None:
        """FIND-P7-01 -- the market-open regression.

        `created_at` is stamped before the handler fetches the evidence, and in an
        open market a new quote arrives during the round-trips almost every time. The
        first version of the rule refused that as "from the future", so the product
        could not authorize or dispatch while the market was open. The measured lead on
        the day it was found was 3.15 s.
        """
        preview = a_preview(quote_captured_at=_NOW + timedelta(seconds=3, milliseconds=150))
        assert not preview.refusals
        assert preview.is_authorizable is True

    def test_the_lead_bound_is_inclusive_and_typed(self) -> None:
        assert isinstance(MAXIMUM_QUOTE_LEAD_SECONDS, int)
        assert 0 < MAXIMUM_QUOTE_LEAD_SECONDS < 60, "a lead bound is not a staleness tolerance"
        at_bound = a_preview(quote_captured_at=_NOW + timedelta(seconds=MAXIMUM_QUOTE_LEAD_SECONDS))
        assert at_bound.is_authorizable is True
        past_bound = a_preview(
            quote_captured_at=_NOW + timedelta(seconds=MAXIMUM_QUOTE_LEAD_SECONDS, milliseconds=1)
        )
        assert past_bound.is_authorizable is False

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
        )
        assert (
            authorization.refusal_against(
                request_fingerprint_now=preview.request_fingerprint,
                account_reference_now=preview.account_reference,
                instant=_NOW,
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
        )
        arguments: dict[str, object] = {
            "request_fingerprint_now": preview.request_fingerprint,
            "account_reference_now": preview.account_reference,
            "instant": _NOW,
        }
        arguments.update(mutation)
        refusal = authorization.refusal_against(**arguments)  # type: ignore[arg-type]
        assert refusal is not None
        assert fragment in refusal

    def test_a_consumed_authorization_permits_nothing_further(self) -> None:
        preview = a_preview()
        base = authorize_submission(
            authorization_id="AUT-1",
            preview=preview,
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=60,
        )
        consumed = ExecutionAuthorization(
            authorization_id=base.authorization_id,
            intent_governance_id=base.intent_governance_id,
            preview_id=base.preview_id,
            preview_version=base.preview_version,
            request_fingerprint=base.request_fingerprint,
            account_reference=base.account_reference,
            client_order_id=base.client_order_id,
            authorized_by=base.authorized_by,
            authorized_at=base.authorized_at,
            expires_at=base.expires_at,
            consumed_at=_NOW + timedelta(seconds=1),
            consumed_by_attempt_id="ATT-1",
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
