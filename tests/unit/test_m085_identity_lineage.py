"""Identity recovery: observing an order under our identity is not attributing it to us.

Three facts are kept apart and persisted separately (state, failure code, events):
  1. whether THIS attempt transmitted a request that could have created an order;
  2. whether an order exists at the broker under the derived `client_order_id`;
  3. whether that order is attributable to THIS human authorization.

Attribution requires lineage: a durable prior attempt that may have transmitted (an
ambiguous or unusable answer to OUR POST, or a dispatcher that died after claiming). A fresh
attempt whose pre-send lookup finds an order, a duplicate-identity answer to our POST (proof
the order predates it), or a reconstructed database without that lineage: the order is
observed and kept visible, but never adopted, never resent, never replaced.

Broker refusals are classified by documented Alpaca semantics (status + numeric code),
never by the shape of a JSON object. Fakes only.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import FakeView

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    RECOGNIZED_DEFINITIVE_REFUSAL_CODES,
    SEND_BOUNDARY_EVENT_TYPE,
    BrokerRefusalKind,
    PaperExecutionState,
    PaperOrderRequest,
    attempt_may_have_transmitted,
    classify_broker_refusal,
    order_terms_mismatches,
    send_boundary_binding,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerIdentityExistsError,
)

_DUPLICATE = '{"code": 40010001, "message": "client_order_id must be unique"}'
_NOT_FOUND = '{"code": 40410000, "message": "order not found"}'


@pytest.fixture(autouse=True)
def operation_clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(handlers._NOW) as clock:
        yield clock


def _identity(world: dict[str, Any]) -> str:
    authorization = world["authorizations"].latest_for_intent("INT-1")
    assert authorization is not None
    return str(authorization.client_order_id)


def _events(world: dict[str, Any]) -> list[str]:
    return [event.event_type for event in world["events"].rows]


def _attempt(world: dict[str, Any]):  # noqa: ANN202
    attempt = world["attempts"].for_intent("INT-1")
    assert attempt is not None
    return attempt


# ---------------------------------------------------------------------------
# Refusal semantics: documented (status, code) pairs, never shape
# ---------------------------------------------------------------------------


class TestRefusalsAreClassifiedByDocumentedSemantics:
    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (403, '{"code": 40310000, "message": "insufficient buying power"}'),
            (
                403,
                '{"code": 40310100, "message": "trade denied: pattern day trading protection"}',
            ),
            (422, '{"code": 40010001, "message": "invalid time_in_force"}'),
            (422, '{"code": 42210000, "message": "fractional orders must be DAY orders"}'),
            (400, '{"code": 40010001, "message": "qty or notional is required"}'),
            (401, '{"code": 40110000, "message": "unauthorized"}'),
        ],
    )
    def test_a_recognized_ordinary_refusal_is_definitive(self, status: int, body: str) -> None:
        assert classify_broker_refusal(status, body) is BrokerRefusalKind.DEFINITIVE_REFUSAL

    def test_the_documented_duplicate_identity_answer_is_its_own_kind(self) -> None:
        assert classify_broker_refusal(422, _DUPLICATE) is BrokerRefusalKind.CLIENT_ORDER_ID_EXISTS

    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (422, '{"code": 49999999, "message": "invalid time_in_force"}'),  # unknown code
            (403, '{"code": 40399999, "message": "insufficient buying power"}'),  # unknown code
            (
                400,
                '{"code": 40310000, "message": "insufficient buying power"}',
            ),  # 403 code on a 400
            (
                403,
                '{"code": 42210000, "message": "fractional orders must be DAY orders"}',
            ),  # 422 code on a 403
            (401, '{"code": 40010001, "message": "unauthorized"}'),  # 400-family code on a 401
            (
                422,
                '{"code": 42210000, "message": "client_order_id must be unique"}',
            ),  # identity words, wrong code
            (
                400,
                '{"code": 40010001, "message": "client_order_id must be unique"}',
            ),  # identity words, wrong status
            (422, '{"code": 40010001, "message": ""}'),
            (422, '{"code": "40010001", "message": "invalid time_in_force"}'),
            (422, "<html>unprocessable</html>"),
            (422, '{"error": "unprocessable"}'),
        ],
    )
    def test_unknown_or_inconsistent_semantics_are_uncertain(self, status: int, body: str) -> None:
        assert classify_broker_refusal(status, body) is BrokerRefusalKind.UNCERTAIN

    def test_the_recognized_table_is_narrow_and_documented(self) -> None:
        assert set(RECOGNIZED_DEFINITIVE_REFUSAL_CODES) == {400, 401, 403, 422}
        for status, codes in RECOGNIZED_DEFINITIVE_REFUSAL_CODES.items():
            assert codes, status
            # Alpaca codes embed the HTTP status as their leading digits, except that 422
            # validation refusals carry the 400-family code 40010001 (documented).
            assert all(
                code // 100000 == status or (status == 422 and code == 40010001) for code in codes
            ), (
                status,
                codes,
            )


# ---------------------------------------------------------------------------
# One canonical comparison of terms
# ---------------------------------------------------------------------------


def _authorized_order(**overrides: object) -> PaperOrderRequest:
    arguments: dict[str, object] = {
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "order_type": OrderType.LIMIT,
        "limit_price": Decimal("4.00"),
        "time_in_force": "DAY",
        "extended_hours": False,
        "client_order_id": "m085-abcdef0123456789",
    }
    arguments.update(overrides)
    return PaperOrderRequest(**arguments)  # type: ignore[arg-type]


class TestTheCanonicalTermsComparison:
    def test_an_exact_match_has_no_mismatches(self) -> None:
        view = FakeView(client_order_id="m085-abcdef0123456789")
        assert order_terms_mismatches(expected=_authorized_order(), actual=view) == ()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("client_order_id", "m085-someoneelse0000000"),
            ("symbol", "TSLA"),
            ("side", "sell"),
            ("quantity", "2"),
            ("order_type", "market"),
            ("limit_price", "5.00"),
            ("time_in_force", "gtc"),
            ("extended_hours", True),
        ],
    )
    def test_every_authorized_term_is_compared(self, field: str, value: object) -> None:
        fields: dict[str, object] = {"client_order_id": "m085-abcdef0123456789", field: value}
        assert field in order_terms_mismatches(
            expected=_authorized_order(), actual=FakeView(**fields)
        )

    @pytest.mark.parametrize(
        "field",
        [
            "symbol",
            "side",
            "quantity",
            "order_type",
            "limit_price",
            "time_in_force",
            "extended_hours",
        ],
    )
    def test_a_missing_or_malformed_field_is_a_mismatch_never_substituted(self, field: str) -> None:
        fields: dict[str, object] = {"client_order_id": "m085-abcdef0123456789", field: None}
        assert field in order_terms_mismatches(
            expected=_authorized_order(), actual=FakeView(**fields)
        )
        fields[field] = object()
        assert field in order_terms_mismatches(
            expected=_authorized_order(), actual=FakeView(**fields)
        )

    def test_a_bound_broker_order_id_must_stay_consistent(self) -> None:
        view = FakeView(client_order_id="m085-abcdef0123456789", broker_order_id="broker-2")
        assert order_terms_mismatches(
            expected=_authorized_order(), actual=view, bound_broker_order_id="broker-1"
        ) == ("broker_order_id",)
        assert (
            order_terms_mismatches(
                expected=_authorized_order(), actual=view, bound_broker_order_id="broker-2"
            )
            == ()
        )

    def test_a_market_order_must_not_come_back_with_a_limit_price(self) -> None:
        expected = _authorized_order(order_type=OrderType.MARKET, limit_price=None)
        view = FakeView(
            client_order_id="m085-abcdef0123456789", order_type="market", limit_price="4.00"
        )
        assert "limit_price" in order_terms_mismatches(expected=expected, actual=view)


# ---------------------------------------------------------------------------
# Lineage: who may be attributed an order found under our identity
# ---------------------------------------------------------------------------


class TestLineage:
    def test_an_ambiguous_post_may_have_transmitted(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_status = 503
        world["broker"].submit_body = '{"code": 50310000, "message": "unavailable"}'
        handlers._submit(world)
        assert attempt_may_have_transmitted(_attempt(world), world["events"].rows) is True

    def test_a_pre_send_observation_did_not_transmit(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].lookup_view = FakeView(client_order_id=_identity(world))
        handlers._submit(world)
        assert attempt_may_have_transmitted(_attempt(world), world["events"].rows) is False

    @pytest.mark.parametrize(
        ("state", "code", "event_type"),
        [
            # A dispatcher that recorded the observation but died before the transition.
            (PaperExecutionState.SUBMISSION_IN_PROGRESS, None, "IDENTITY_OBSERVED_BEFORE_SEND"),
            (PaperExecutionState.SUBMISSION_IN_PROGRESS, None, "IDENTITY_LOOKUP_INCONCLUSIVE"),
            (PaperExecutionState.SUBMISSION_IN_PROGRESS, None, "DISPATCH_NOT_SENT"),
            # A failure code rewritten to look transmitted cannot erase what the event says.
            (PaperExecutionState.SUBMISSION_UNKNOWN, "AMBIGUOUS", "CLIENT_ORDER_ID_COLLISION"),
            (PaperExecutionState.SUBMISSION_UNKNOWN, "UNCERTAIN_HTTP_503", "DISPATCH_NOT_SENT"),
        ],
    )
    def test_an_event_recording_no_send_outranks_a_state_that_would_otherwise_qualify(
        self, state: PaperExecutionState, code: str | None, event_type: str
    ) -> None:
        attempt = SimpleNamespace(
            attempt_id="ATT-1",
            authorization_id="AUT-1",
            request_fingerprint="a" * 64,
            client_order_id="m085-0123456789abcdef",
            state=state,
            failure_code=code,
        )
        boundary = SimpleNamespace(
            event_type=SEND_BOUNDARY_EVENT_TYPE,
            attempt_id="ATT-1",
            detail=send_boundary_binding(
                attempt_id="ATT-1",
                authorization_id="AUT-1",
                request_fingerprint="a" * 64,
                account_reference="ref:account",
                client_order_id="m085-0123456789abcdef",
                identity_lookup_status=404,
            ),
        )
        # With its send-boundary record this attempt WOULD qualify as possibly transmitted ...
        assert attempt_may_have_transmitted(attempt, [boundary]) is True
        # ... and the append-only record that nothing was sent is what denies it.
        events = [boundary, SimpleNamespace(event_type=event_type)]
        assert attempt_may_have_transmitted(attempt, events) is False

    def test_a_duplicate_answer_to_our_post_means_the_order_predates_it(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        broker.lookup_sequence = [(404, None, _NOT_FOUND)]
        broker.submit_status = 422
        broker.submit_body = _DUPLICATE
        handlers._submit(world)
        assert attempt_may_have_transmitted(_attempt(world), world["events"].rows) is False


# ---------------------------------------------------------------------------
# Dispatch: an identity observed before the send is not ours; it stays visible
# ---------------------------------------------------------------------------


class TestAnIdentityObservedBeforeTheSendIsNotAttributed:
    def test_an_exact_match_found_before_sending_is_observed_not_adopted(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        identity = _identity(world)
        world["broker"].lookup_view = FakeView(
            client_order_id=identity, broker_order_id="broker-old", status="filled"
        )
        result = handlers._submit(world)
        assert world["broker"].submitted == []
        # The broker was asked about the DERIVED identity, before the send and again when the
        # observation was recorded -- never about a replacement or a variant of it.
        assert world["broker"].lookups and set(world["broker"].lookups) == {identity}
        assert result.dispatched is False
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.failure_code == "IDENTITY_EXISTS_UNSENT"
        assert result.attempt.broker_order_id is None, "a historical order was adopted"
        assert "IDENTITY_OBSERVED_BEFORE_SEND" in _events(world)
        assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world)
        assert "IDENTITY_RECONCILED_EXACT_MATCH" not in _events(world)
        observed = next(
            e for e in world["events"].rows if e.event_type == "IDENTITY_OBSERVED_NOT_ATTRIBUTED"
        )
        assert "broker-old" in observed.detail and "filled" in observed.detail
        assert "not attributed" in result.note.lower() or "operator" in result.note.lower()

    def test_a_duplicate_answer_after_the_send_is_observed_not_adopted(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        identity = _identity(world)
        broker.lookup_sequence = [(404, None, _NOT_FOUND)]
        broker.submit_status = 422
        broker.submit_body = _DUPLICATE
        broker.lookup_view = FakeView(client_order_id=identity, broker_order_id="broker-old")
        result = handlers._submit(world)
        assert len(broker.submitted) == 1
        assert result.dispatched is True
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.failure_code == "IDENTITY_EXISTS_SENT"
        assert result.attempt.broker_order_id is None
        assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world)

    def test_a_duplicate_raised_by_the_adapter_takes_the_same_path(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        broker.lookup_sequence = [(404, None, _NOT_FOUND)]
        broker.submit_raises = BrokerIdentityExistsError(
            "duplicate", http_status=422, sanitized_body=_DUPLICATE, request_sent=True
        )
        broker.lookup_view = FakeView(client_order_id=_identity(world))
        result = handlers._submit(world)
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.failure_code == "IDENTITY_EXISTS_SENT"
        assert result.attempt.broker_order_id is None

    def test_nothing_is_ever_resent_and_no_later_authorization_reopens_it(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].lookup_view = FakeView(client_order_id=_identity(world))
        handlers._submit(world)
        assert handlers._submit(world).dispatched is False
        handlers._HELPER._authorize(world)
        assert handlers._submit(world).dispatched is False
        assert world["broker"].submitted == []
        # Reconciliation keeps observing; it still does not attribute.
        reconciled = handlers._reconcile(world, at_seconds=120)
        assert reconciled.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert reconciled.broker_order_id is None
        assert _events(world).count("IDENTITY_OBSERVED_NOT_ATTRIBUTED") >= 2

    def test_a_rebuilt_database_does_not_inherit_the_earlier_process_order(self) -> None:
        world_a = handlers._world()
        handlers._authorize(world_a)
        first = handlers._submit(world_a)
        assert first.dispatched is True
        broker = world_a["broker"]  # outlives the database
        world_b = handlers._world(broker=broker)
        handlers._authorize(world_b)
        second = handlers._submit(world_b)
        assert len(broker.submitted) == 1
        assert second.dispatched is False
        assert second.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert second.attempt.broker_order_id is None
        assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world_b)


# ---------------------------------------------------------------------------
# Dispatch: an inconclusive pre-send lookup is uncertainty, not a rejection
# ---------------------------------------------------------------------------


class TestAnInconclusiveLookupBeforeTheSendStaysRecoverable:
    @pytest.mark.parametrize("kind", ["http-500", "exception", "unusable-200"])
    def test_it_becomes_unknown_with_nothing_sent(self, kind: str) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        if kind == "http-500":
            broker.lookup_status = 500
            broker.lookup_view = None
            broker.lookup_body = '{"code": 50010000, "message": "internal"}'
        elif kind == "exception":
            broker.lookup_raises = TimeoutError("lookup timed out")
        else:
            broker.lookup_status = 200
            broker.lookup_view = None
            broker.lookup_body = "<html>not an order</html>"
        result = handlers._submit(world)
        assert broker.submitted == [], "a POST left after an inconclusive identity lookup"
        assert result.dispatched is False
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.is_terminal is False
        assert result.attempt.failure_code == "IDENTITY_UNRESOLVED_UNSENT"
        assert "IDENTITY_LOOKUP_INCONCLUSIVE" in _events(world)
        assert "DISPATCH_NOT_SENT" not in _events(world)

    def test_a_repeat_dispatch_cannot_discard_the_recorded_uncertainty(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].lookup_status = 500
        world["broker"].lookup_view = None
        handlers._submit(world)
        # A later refusal of any kind (here: the kill switch) does not turn the recorded
        # uncertainty into a terminal rejection; the attempt is simply not re-dispatched.
        world["kill_switch"].engaged = True
        again = handlers._submit(world)
        assert again.dispatched is False
        assert again.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert again.attempt.failure_code == "IDENTITY_UNRESOLVED_UNSENT"
        assert world["broker"].submitted == []

    def test_after_a_restart_a_successful_lookup_surfaces_the_order_without_attributing_it(
        self,
    ) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        broker.lookup_status = 500
        broker.lookup_view = None
        handlers._submit(world)
        # New process: the broker now answers, and it holds an order under the identity.
        broker.lookup_status = 200
        broker.lookup_view = FakeView(
            client_order_id=_identity(world), broker_order_id="broker-old", status="accepted"
        )
        assert handlers._handler(world).handle(handlers._HELPER._command()).dispatched is False
        surfaced = handlers._reconcile(world, at_seconds=5)
        assert surfaced.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert surfaced.broker_order_id is None
        assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world)
        observed = next(
            e for e in world["events"].rows if e.event_type == "IDENTITY_OBSERVED_NOT_ATTRIBUTED"
        )
        assert "broker-old" in observed.detail
        assert broker.submitted == []

    def test_after_a_restart_an_absent_order_resolves_under_the_bounded_policy(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        broker.lookup_status = 500
        broker.lookup_view = None
        handlers._submit(world)
        broker.lookup_status = 404
        broker.lookup_view = None
        assert (
            handlers._reconcile(world, at_seconds=120).state
            is PaperExecutionState.SUBMISSION_UNKNOWN
        )
        resolved = handlers._reconcile(world, at_seconds=121)
        assert resolved.state is PaperExecutionState.REJECTED
        assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
        assert broker.submitted == []


# ---------------------------------------------------------------------------
# Recovery with lineage still works, and is validated on every term and the account
# ---------------------------------------------------------------------------


class TestLegitimateRecoveryAfterALostAcknowledgement:
    def _unknown_after_our_post(self) -> dict[str, Any]:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_status = 503
        world["broker"].submit_body = '{"code": 50310000, "message": "unavailable"}'
        handlers._submit(world)
        assert _attempt(world).state is PaperExecutionState.SUBMISSION_UNKNOWN
        return world

    def test_our_own_order_is_adopted_after_the_answer_was_lost(self) -> None:
        world = self._unknown_after_our_post()
        recovered = handlers._reconcile(world, at_seconds=5)
        assert recovered.state is PaperExecutionState.PAPER_ACCEPTED
        assert recovered.broker_order_id == "broker-1"
        assert "RECONCILED" in _events(world)
        assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" not in _events(world)
        assert len(world["broker"].submitted) == 1

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("symbol", "TSLA"),
            ("quantity", "9"),
            ("side", "sell"),
            ("order_type", "market"),
            ("limit_price", "9.99"),
            ("time_in_force", "gtc"),
            ("extended_hours", True),
        ],
    )
    def test_a_differing_term_is_never_adopted_even_with_lineage(
        self, field: str, value: object
    ) -> None:
        world = self._unknown_after_our_post()
        world["broker"].lookup_fields = {field: value}
        result = handlers._reconcile(world, at_seconds=5)
        assert result.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.broker_order_id is None
        mismatch = next(
            e for e in world["events"].rows if e.event_type == "IDENTITY_COLLISION_MISMATCH"
        )
        assert field in mismatch.detail

    def test_an_account_that_is_not_the_authorized_one_is_never_adopted(self) -> None:
        world = self._unknown_after_our_post()
        world["broker"].account_overrides = {"id": "another-account"}
        result = handlers._reconcile(world, at_seconds=5)
        assert result.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.broker_order_id is None
        assert any(
            e.event_type == "IDENTITY_COLLISION_MISMATCH" and "account" in e.detail
            for e in world["events"].rows
        )

    def test_a_bound_broker_order_id_that_changes_is_a_collision_not_an_update(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        first = handlers._submit(world)
        assert first.attempt.broker_order_id == "broker-1"
        world["broker"].lookup_fields = {"broker_order_id": "broker-2", "status": "filled"}
        result = handlers._reconcile(world, at_seconds=5)
        assert result.state is PaperExecutionState.PAPER_ACCEPTED
        assert result.broker_order_id == "broker-1"
        assert any(
            e.event_type == "IDENTITY_COLLISION_MISMATCH" and "broker_order_id" in e.detail
            for e in world["events"].rows
        )

    def test_an_acknowledgement_that_differs_from_the_order_is_uncertain_not_accepted(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_raises = BrokerAmbiguousDispatchError(
            "acknowledged a different order",
            http_status=200,
            sanitized_body='{"time_in_force": "gtc"}',
        )
        result = handlers._submit(world)
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.broker_order_id is None
