"""IDENTITY-SAFETY CORRECTION (F1): an order that already exists under our identity.

SUPERSEDED IN PART by the send-boundary correction: adoption of an order observed before the
send, after a duplicate answer, or after a database reconstruction is no longer performed
(observing is not attributing); those cases are specified in
`tests/unit/test_m085_identity_lineage.py`. The tests kept here still hold.

The unsafe sequence this closes: a deterministic `client_order_id` is derived; the
broker already holds an order under it (a rebuilt database, a lost attempt row, an
earlier process); a new submission is answered with Alpaca's duplicate-identity 422;
the old code recorded a terminal REJECTED and lost track of a live order.

Now: the identity is looked up BEFORE anything is sent; a duplicate answer AFTER a send
is not a refusal; both enter one reconciliation path that adopts the broker's order only
when it equals the authorized one on every field, records a collision otherwise, and
never sends again. Fakes only; no broker, no network, no database here.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import FakeView

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    DEFINITIVE_BROKER_REFUSAL_STATUSES,
    BrokerRefusalKind,
    PaperExecutionState,
    PaperOrderRequest,
    classify_broker_refusal,
    is_client_order_id_collision,
    is_definitive_broker_refusal,
    order_terms_mismatches,
)
from empirical_platform.shared.brokerage.alpaca_paper import BrokerIdentityExistsError

_DUPLICATE = '{"code": 40010001, "message": "client_order_id must be unique"}'
_ORDINARY_422 = '{"code": 40010001, "message": "qty must be integer"}'
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


# ---------------------------------------------------------------------------
# 422 is classified semantically, never by status and JSON-ness alone
# ---------------------------------------------------------------------------


class TestA422IsClassifiedSemantically:
    def test_the_documented_duplicate_answer_is_an_existing_identity(self) -> None:
        assert classify_broker_refusal(422, _DUPLICATE) is BrokerRefusalKind.CLIENT_ORDER_ID_EXISTS
        assert is_client_order_id_collision(422, _DUPLICATE) is True
        assert is_definitive_broker_refusal(422, _DUPLICATE) is False

    @pytest.mark.parametrize(
        "body",
        [
            _ORDINARY_422,
            '{"code": 40010001, "message": "insufficient qty available for order"}',
            '{"code": 42210000, "message": "limit_price must be positive"}',
        ],
    )
    def test_an_ordinary_invalid_order_422_is_a_definitive_refusal(self, body: str) -> None:
        assert classify_broker_refusal(422, body) is BrokerRefusalKind.DEFINITIVE_REFUSAL
        assert is_definitive_broker_refusal(422, body) is True
        assert is_client_order_id_collision(422, body) is False

    @pytest.mark.parametrize(
        "body",
        [
            "<html>422</html>",
            "",
            '{"message": "trunc',
            '["client_order_id must be unique"]',
            '{"message": "client_order_id must be unique"}',
            '{"code": "40010001", "message": "client_order_id must be unique"}',
            '{"code": true, "message": "qty must be integer"}',
            '{"code": 40010001}',
            '{"code": 40010001, "message": ""}',
            '{"code": 40010001, "message": 12}',
        ],
    )
    def test_an_unknown_shape_is_uncertain(self, body: str) -> None:
        # Malformed bodies, arrays, missing or non-integer codes, missing or empty
        # messages: none is the broker's documented error object, so none proves anything.
        assert classify_broker_refusal(422, body) is BrokerRefusalKind.UNCERTAIN
        assert is_definitive_broker_refusal(422, body) is False
        assert is_client_order_id_collision(422, body) is False

    @pytest.mark.parametrize(
        "body",
        [
            '{"code": 40010001, "message": "client_order_id is too long"}',
            '{"code": 40010001, "message": "invalid client order id"}',
            '{"code": 40010001, "message": "client_order_id must not be empty"}',
        ],
    )
    def test_an_identity_error_that_is_not_the_duplicate_answer_is_uncertain(
        self, body: str
    ) -> None:
        assert classify_broker_refusal(422, body) is BrokerRefusalKind.UNCERTAIN

    @pytest.mark.parametrize("status", [400, 401, 403])
    def test_the_duplicate_message_on_another_status_is_uncertain_not_a_collision(
        self, status: int
    ) -> None:
        # Alpaca documents the duplicate answer as a 422. The same words on another
        # status are not that answer, and they are still about the identity.
        assert classify_broker_refusal(status, _DUPLICATE) is BrokerRefusalKind.UNCERTAIN

    @pytest.mark.parametrize("status", [404, 408, 409, 429, 500, 502, 503, 504])
    def test_a_non_definitive_status_is_uncertain_whatever_the_body_says(self, status: int) -> None:
        assert classify_broker_refusal(status, _DUPLICATE) is BrokerRefusalKind.UNCERTAIN
        assert classify_broker_refusal(status, _ORDINARY_422) is BrokerRefusalKind.UNCERTAIN

    def test_the_definitive_statuses_are_unchanged(self) -> None:
        assert DEFINITIVE_BROKER_REFUSAL_STATUSES == frozenset({400, 401, 403, 422})


# ---------------------------------------------------------------------------
# Only the exact authorized order is ever adopted
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


class TestOnlyTheExactAuthorizedOrderIsAdopted:
    def test_an_exact_match_has_no_mismatches(self) -> None:
        view = FakeView(client_order_id="m085-abcdef0123456789")
        assert order_terms_mismatches(expected=_authorized_order(), actual=view) == ()

    def test_case_of_side_and_type_does_not_matter_but_the_value_does(self) -> None:
        view = FakeView(client_order_id="m085-abcdef0123456789", side="BUY", order_type="LIMIT")
        assert order_terms_mismatches(expected=_authorized_order(), actual=view) == ()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("symbol", "TSLA"),
            ("quantity", "2"),
            ("side", "sell"),
            ("order_type", "market"),
            ("limit_price", "5.00"),
            ("client_order_id", "m085-someoneelse0000000"),
        ],
    )
    def test_a_mismatched_field_is_a_collision(self, field: str, value: str) -> None:
        fields: dict[str, object] = {"client_order_id": "m085-abcdef0123456789", field: value}
        view = FakeView(**fields)
        assert field in order_terms_mismatches(expected=_authorized_order(), actual=view)

    @pytest.mark.parametrize("field", ["symbol", "quantity", "side", "order_type", "limit_price"])
    def test_a_field_the_broker_did_not_report_is_a_mismatch_not_a_match(self, field: str) -> None:
        view = FakeView(client_order_id="m085-abcdef0123456789", **{field: None})
        assert field in order_terms_mismatches(expected=_authorized_order(), actual=view)

    def test_a_non_decimal_quantity_or_price_is_a_mismatch(self) -> None:
        view = FakeView(client_order_id="m085-abcdef0123456789", quantity="one", limit_price="4,00")
        assert {"quantity", "limit_price"} <= set(
            order_terms_mismatches(expected=_authorized_order(), actual=view)
        )


# ---------------------------------------------------------------------------
# The dispatch handler: identity first, then send; collision -> reconcile, never resend
# ---------------------------------------------------------------------------


class TestAnExistingIdentityIsReconciledNotRejected:
    def test_a_fresh_identity_is_looked_up_and_then_the_order_is_sent_once(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        result = handlers._submit(world)
        assert result.dispatched is True
        assert world["broker"].lookups == [_identity(world)]
        assert len(world["broker"].submitted) == 1
        assert result.attempt.state is PaperExecutionState.PAPER_ACCEPTED

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("symbol", "TSLA"),
            ("quantity", "2"),
            ("side", "sell"),
            ("limit_price", "5.00"),
            ("order_type", "market"),
        ],
    )
    def test_a_mismatching_order_under_our_identity_is_a_collision_and_never_adopted(
        self, field: str, value: str
    ) -> None:
        world = handlers._world()
        handlers._authorize(world)
        identity = _identity(world)
        world["broker"].lookup_view = FakeView(client_order_id=identity, **{field: value})
        result = handlers._submit(world)
        assert world["broker"].submitted == []
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.is_terminal is False
        assert result.attempt.failure_code == "IDENTITY_EXISTS_UNSENT"
        assert result.attempt.broker_order_id is None
        assert "IDENTITY_COLLISION_MISMATCH" in _events(world)
        mismatch = next(
            e for e in world["events"].rows if e.event_type == "IDENTITY_COLLISION_MISMATCH"
        )
        assert field in mismatch.detail
        assert "NOT adopted" in result.note and "operator" in result.note

    def test_a_collision_is_never_followed_by_a_second_dispatch(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        identity = _identity(world)
        world["broker"].lookup_view = FakeView(client_order_id=identity, symbol="TSLA")
        handlers._submit(world)
        # The same process, a new process, and a fresh human authorization.
        assert handlers._submit(world).dispatched is False
        assert handlers._handler(world).handle(handlers._HELPER._command()).dispatched is False
        handlers._HELPER._authorize(world)
        assert handlers._submit(world).dispatched is False
        assert world["broker"].submitted == []
        assert [s for _, s in world["attempts"].transitions].count(
            PaperExecutionState.SUBMISSION_IN_PROGRESS
        ) == 1

    def test_a_duplicate_answer_raised_by_the_adapter_takes_the_same_path(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        identity = _identity(world)
        broker = world["broker"]
        broker.lookup_sequence = [(404, None, _NOT_FOUND)]
        broker.submit_raises = BrokerIdentityExistsError(
            "duplicate", http_status=422, sanitized_body=_DUPLICATE, request_sent=True
        )
        broker.lookup_view = FakeView(client_order_id=identity, symbol="MSFT")
        result = handlers._submit(world)
        assert len(broker.submitted) == 1
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert "IDENTITY_COLLISION_MISMATCH" in _events(world)
        assert handlers._submit(world).dispatched is False
        assert len(broker.submitted) == 1

    def test_a_duplicate_answer_whose_lookup_finds_nothing_stays_unknown(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        broker = world["broker"]
        broker.lookup_sequence = [(404, None, _NOT_FOUND), (404, None, _NOT_FOUND)]
        broker.submit_status = 422
        broker.submit_body = _DUPLICATE
        result = handlers._submit(world)
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert "IDENTITY_LOOKUP_UNRESOLVED" in _events(world)
        assert handlers._submit(world).dispatched is False
        assert len(broker.submitted) == 1


# ---------------------------------------------------------------------------
# Recovery after a process restart, through production handlers over the same repositories
# ---------------------------------------------------------------------------


class _Crash(BaseException):
    """The process dies after the request left and before anything was recorded."""


class TestRecoveryAfterRestart:
    def test_an_unknown_attempt_is_recovered_by_a_new_process_through_the_same_identity(
        self,
    ) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_raises = (
            BrokerIdentityExistsError("x", request_sent=True) if False else None
        )
        world["broker"].submit_status = 503
        world["broker"].submit_body = '{"code": 50310000, "message": "unavailable"}'
        first = handlers._submit(world)
        assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        # "New process": fresh handler instances over the same persisted fakes. The fake
        # broker received the order, so its lookup echoes exactly what was sent.
        world["broker"].submit_status = 200
        assert handlers._handler(world).handle(handlers._HELPER._command()).dispatched is False
        recovered = handlers._reconcile(world, at_seconds=5)
        assert recovered.state is PaperExecutionState.PAPER_ACCEPTED
        assert world["broker"].lookups[-1] == _identity(world)
        assert len(world["broker"].submitted) == 1

    def test_a_crash_after_the_send_leaves_in_progress_and_a_new_process_recovers_it(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_raises = _Crash()
        with pytest.raises(_Crash):
            handlers._submit(world)
        stranded = world["attempts"].for_intent("INT-1")
        assert stranded.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
        assert len(world["broker"].submitted) == 1
        world["broker"].submit_raises = None
        # New process: nothing is resent; reconciliation after the not-found window
        # finds the order under the same identity and adopts it.
        assert handlers._handler(world).handle(handlers._HELPER._command()).dispatched is False
        assert (
            handlers._reconcile(world, at_seconds=30).state
            is PaperExecutionState.SUBMISSION_IN_PROGRESS
        )
        assert handlers._reconcile(world, at_seconds=61).state is PaperExecutionState.PAPER_ACCEPTED
        assert len(world["broker"].submitted) == 1

    def test_reconciliation_after_restart_refuses_a_mismatching_order_under_our_identity(
        self,
    ) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_raises = _Crash()
        with pytest.raises(_Crash):
            handlers._submit(world)
        world["broker"].submit_raises = None
        world["broker"].lookup_view = FakeView(client_order_id=_identity(world), quantity="9")
        before = len(world["events"].rows)
        result = handlers._reconcile(world, at_seconds=61)
        assert result.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
        assert result.broker_order_id is None
        assert [e.event_type for e in world["events"].rows[before:]] == [
            "IDENTITY_COLLISION_MISMATCH"
        ]
        # Still refused on the next look, and nothing is ever resent.
        assert (
            handlers._reconcile(world, at_seconds=120).state
            is PaperExecutionState.SUBMISSION_IN_PROGRESS
        )
        assert handlers._handler(world).handle(handlers._HELPER._command()).dispatched is False
        assert len(world["broker"].submitted) == 1

    def test_reconciliation_of_an_unknown_attempt_refuses_a_mismatching_order(self) -> None:
        world = handlers._world()
        handlers._authorize(world)
        world["broker"].submit_status = 502
        world["broker"].submit_body = "<html>bad gateway</html>"
        handlers._submit(world)
        world["broker"].lookup_view = FakeView(client_order_id=_identity(world), symbol="TSLA")
        result = handlers._reconcile(world, at_seconds=5)
        assert result.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert "IDENTITY_COLLISION_MISMATCH" in _events(world)
        world["broker"].lookup_view = FakeView(client_order_id=_identity(world), status="accepted")
        assert handlers._reconcile(world, at_seconds=6).state is PaperExecutionState.PAPER_ACCEPTED

    def test_a_rebuilt_database_meets_a_different_order_under_its_identity(self) -> None:
        world_a = handlers._world()
        handlers._authorize(world_a)
        handlers._submit(world_a)
        broker = world_a["broker"]
        broker.lookup_fields = {"quantity": "3"}  # the broker's order is not this one
        world_b = handlers._world(broker=broker)
        handlers._authorize(world_b)
        second = handlers._submit(world_b)
        assert len(broker.submitted) == 1
        assert second.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert "IDENTITY_COLLISION_MISMATCH" in _events(world_b)
        assert handlers._submit(world_b).dispatched is False
        assert len(broker.submitted) == 1
