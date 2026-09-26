"""MILESTONE-085 corrective pass: the dispatch path, driven through the real handlers.

The world, preview and authorization are built exactly as in
`test_m085_paper_execution_handlers.TestSubmitAuthorizedPaperOrder` -- through the real
preview and authorize handlers -- by using that class's helpers through the MODULE, so
pytest does not collect its tests a second time here.

WHAT EVERY TEST HERE PROVES ABOUT THE BROKER. `FakeBroker.submitted` records every call
that reached the order endpoint. Each refusal path asserts it is EMPTY, and each
uncertain-outcome path asserts it holds EXACTLY ONE entry however many times the
dispatch, a second authorization or reconciliation is attempted afterwards.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_paper_execution_handlers as base
from tests.unit._m085_fakes import (
    _NOW,
    FakeAcknowledgements,
    FakeAttempts,
    FakeConfigurations,
    FakeEvents,
    FakeMarketData,
    FakeQuote,
    FakeView,
    a_configuration,
    a_provenance,
    an_intent,
    time_bases_for,
)

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
    is_paper_transition_allowed,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
)
from empirical_platform.usecases.paper_execution import (
    PaperExecutionRefusedError,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
    SubmitAuthorizedPaperOrderHandler,
)

_HELPER = base.TestSubmitAuthorizedPaperOrder()


@pytest.fixture(autouse=True)
def operation_clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(_NOW) as clock:
        yield clock


def _world(**overrides: object) -> dict[str, Any]:
    return _HELPER._world(**overrides)


def _authorize(world: dict[str, Any], *, validity_seconds: int = 300) -> object:
    return _HELPER._authorize(world, validity_seconds=validity_seconds)


def _handler(world: dict[str, Any]) -> SubmitAuthorizedPaperOrderHandler:
    return _HELPER._handler(world)


def _submit(world: dict[str, Any]) -> Any:  # noqa: ANN401 - PaperSubmissionResult
    return _handler(world).handle(_HELPER._command())


def _reconcile(world: dict[str, Any], *, at_seconds: int) -> ExecutionAttempt:
    # The reconciler's host clock and the fake broker's clock (`datetime.now`, frozen) both
    # read the command instant: the waiting interval is measured on the broker clock.
    with freeze_time(_NOW + timedelta(seconds=at_seconds)):
        return ReconcilePaperOrderHandler(
            attempts=world["attempts"],
            acknowledgements=world["acknowledgements"],
            events=world["events"],
            broker=world["broker"],
            authorizations=world["authorizations"],
            previews=world["previews"],
            rounds=world["rounds"],
        ).handle(
            ReconcilePaperOrderCommand(
                intent_governance_id="INT-1", at=_NOW + timedelta(seconds=at_seconds)
            )
        )


class _StaleQuote(FakeQuote):
    captured_at = _NOW - timedelta(hours=1)


class _WideQuote(FakeQuote):
    bid = "280.00"
    ask = "299.70"


# ---------------------------------------------------------------------------
# D1 -- command arguments cannot weaken an authorization
# ---------------------------------------------------------------------------


class TestNothingOutsideTheConfigurationCanLoosenAnAuthorization:
    def test_the_reproduced_hour_old_quote_is_refused_and_nothing_is_claimed(self) -> None:
        # THE REVIEW'S REPRODUCTION. Authorized under 5 USD / 60 s / AAPL; the quote at
        # dispatch is an hour old. The old submit command accepted `500 99999 AAPL,TSLA`
        # and dispatched. There is now no argument to pass, and the configuration's
        # 60 s refuses.
        world = _world()
        _authorize(world)
        world["market_data"] = FakeMarketData(quote=_StaleQuote())
        with pytest.raises(PaperExecutionRefusedError, match="older than the 60s limit"):
            _submit(world)
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_a_looser_stored_configuration_refuses_before_any_broker_call(self) -> None:
        # Even a store rewritten under the same id and version cannot loosen the limits:
        # the policy the human authorized is fingerprinted and compared.
        world = _world()
        _authorize(world)
        world["configurations"].rows[("CFG-1", 1)] = a_configuration(
            maximum_capital_per_trade=Decimal("500"),
            maximum_market_data_age_seconds=99999,
            watchlist=("AAPL", "TSLA"),
        )
        reads: list[str] = []
        original = world["broker"].fetch_account
        world["broker"].fetch_account = lambda: reads.append("account") or original()
        with pytest.raises(PaperExecutionRefusedError, match="not the policy the human authorized"):
            _submit(world)
        assert reads == [] and world["broker"].submitted == []

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("maximum_notional", Decimal("500")),
            ("quote_captured_at", _NOW - timedelta(hours=1)),
            ("policy_fingerprint", "b" * 64),
            ("symbol", "TSLA"),
        ],
    )
    def test_a_tampered_stored_authorization_refuses(self, field: str, value: object) -> None:
        from dataclasses import replace

        world = _world()
        _authorize(world)
        stored = world["authorizations"].rows["AUT-1"]
        world["authorizations"].rows["AUT-1"] = replace(stored, **{field: value})
        with pytest.raises(PaperExecutionRefusedError, match=field):
            _submit(world)
        assert world["broker"].submitted == []

    def test_a_missing_configuration_version_refuses(self) -> None:
        world = _world()
        _authorize(world)
        world["configurations"].rows.clear()
        with pytest.raises(PaperExecutionRefusedError, match="does not exist"):
            _submit(world)
        assert world["broker"].submitted == []


# ---------------------------------------------------------------------------
# Item 7 -- every input is read again at the final controllable boundary
# ---------------------------------------------------------------------------


def _after_the_claim(world: dict[str, Any], action: Callable[[], None]) -> None:
    """Run `action` once the attempt moves to SUBMISSION_IN_PROGRESS: after the claim."""
    original = world["attempts"].transition

    def transition(**kwargs: object) -> object:
        if kwargs.get("target") is PaperExecutionState.SUBMISSION_IN_PROGRESS:
            action()
        return original(**kwargs)

    world["attempts"].transition = transition


def _assert_not_sent(result: Any, fragment: str) -> None:  # noqa: ANN401
    assert result.dispatched is False
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert result.attempt.failure_code == "NOT_SENT"
    assert fragment in (result.attempt.failure_detail or ""), result.attempt.failure_detail


class TestTheFinalGuardReadsEverythingAgain:
    def test_a_quote_that_goes_stale_after_the_claim_is_refused(self) -> None:
        world = _world()
        _authorize(world)
        _after_the_claim(world, lambda: setattr(world["market_data"], "_quote", _StaleQuote()))
        _assert_not_sent(_submit(world), "older than the 60s limit")
        assert world["broker"].submitted == []

    def test_a_spread_that_widens_after_the_claim_is_refused(self) -> None:
        world = _world()
        _authorize(world)
        _after_the_claim(world, lambda: setattr(world["market_data"], "_quote", _WideQuote()))
        _assert_not_sent(_submit(world), "spread")
        assert world["broker"].submitted == []

    def test_a_market_that_closes_after_the_claim_is_refused(self) -> None:
        world = _world()
        _authorize(world)
        original = world["broker"].fetch_clock
        state = {"closed": False}

        def clock() -> object:
            value = original()
            if state["closed"]:
                value.is_open = False
            return value

        world["broker"].fetch_clock = clock
        _after_the_claim(world, lambda: state.update(closed=True))
        _assert_not_sent(_submit(world), "session is closed")
        assert world["broker"].submitted == []

    def test_a_kill_switch_engaged_after_the_claim_is_refused(self) -> None:
        # The review found this re-read untested (D6): engaging before the handler runs
        # is refused earlier, so only an engagement after the claim reaches it.
        world = _world()
        _authorize(world)
        _after_the_claim(world, lambda: setattr(world["kill_switch"], "engaged", True))
        _assert_not_sent(_submit(world), "kill switch")
        assert world["broker"].submitted == []

    def test_a_configuration_changed_after_the_claim_is_refused(self) -> None:
        world = _world()
        _authorize(world)
        looser = a_configuration(maximum_market_data_age_seconds=3600)
        _after_the_claim(
            world, lambda: world["configurations"].rows.__setitem__(("CFG-1", 1), looser)
        )
        _assert_not_sent(_submit(world), "not the policy the human authorized")
        assert world["broker"].submitted == []

    def test_an_entry_window_that_closes_during_connection_preparation_is_refused(
        self, operation_clock: FrozenDateTimeFactory
    ) -> None:
        # The window closes at _NOW (10:00 New York); connecting takes one second.
        world = _world(
            configurations=FakeConfigurations(a_configuration(latest_entry_time=time(10, 0)))
        )
        _authorize(world)
        original = world["broker"].submit_order

        def slow_connect(order: object, *, before_send: Callable[[], None] | None = None) -> object:
            def guard() -> None:
                operation_clock.tick(delta=timedelta(seconds=1))
                if before_send is not None:
                    before_send()

            return original(order, before_send=guard)

        world["broker"].submit_order = slow_connect
        _assert_not_sent(_submit(world), "entry window")
        assert world["broker"].submitted == []

    def test_the_final_guard_really_fetches_clock_quote_and_configuration_again(self) -> None:
        world = _world()
        _authorize(world)
        counts = {"clock": 0, "quote": 0}
        original_clock = world["broker"].fetch_clock
        original_quote = world["market_data"].fetch_quote

        def clock() -> object:
            counts["clock"] += 1
            return original_clock()

        def quote(symbol: str) -> object:
            counts["quote"] += 1
            return original_quote(symbol)

        world["broker"].fetch_clock = clock
        world["market_data"].fetch_quote = quote
        reads_before = world["configurations"].reads
        result = _submit(world)
        assert result.dispatched is True
        # Once in the pre-claim gather, once more inside the final guard.
        assert counts == {"clock": 2, "quote": 2}
        assert world["configurations"].reads - reads_before == 2


# ---------------------------------------------------------------------------
# D2 -- an uncertain outcome is never a refusal and never a second submission
# ---------------------------------------------------------------------------


def _uncertain_broker(kind: str, world: dict[str, Any]) -> None:
    broker = world["broker"]
    if kind == "timeout-after-send":
        broker.submit_raises = BrokerAmbiguousDispatchError("read timed out")
    elif kind == "server-error-503":
        broker.submit_raises = BrokerAmbiguousDispatchError(
            "HTTP 503", http_status=503, sanitized_body='{"message": "unavailable"}'
        )
    elif kind == "fake-500-without-view":
        broker.submit_status = 500
        broker.submit_body = '{"message": "internal"}'
    elif kind == "fake-429":
        broker.submit_status = 429
        broker.submit_body = '{"message": "too many requests"}'
    elif kind == "fake-422-from-a-proxy-page":
        broker.submit_status = 422
        broker.submit_body = "<html>blocked</html>"
    elif kind == "fake-200-without-an-order":
        broker.submit_status = 200
        broker.submit_view = None
    elif kind == "unexpected-fault-after-send":
        broker.submit_raises = RuntimeError("the process misbehaved after writing the request")
    else:  # pragma: no cover - the parametrization is closed
        raise AssertionError(kind)


_UNCERTAIN = (
    "timeout-after-send",
    "server-error-503",
    "fake-500-without-view",
    "fake-429",
    "fake-422-from-a-proxy-page",
    "fake-200-without-an-order",
    "unexpected-fault-after-send",
)


class TestAnUncertainOutcomeIsResolvedNotRetried:
    @pytest.mark.parametrize("kind", _UNCERTAIN)
    def test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission(
        self, kind: str
    ) -> None:
        world = _world()
        _authorize(world)
        _uncertain_broker(kind, world)
        first = _submit(world)
        assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert first.attempt.is_terminal is False
        assert "do not send again" in first.note
        assert len(world["broker"].submitted) == 1

        # A second submit, a fresh human authorization for the same intent, and a
        # third submit: none of them reaches the broker again.
        assert _submit(world).dispatched is False
        _HELPER._authorize(world)
        assert _submit(world).dispatched is False
        assert len(world["broker"].submitted) == 1
        assert [state for _, state in world["attempts"].transitions].count(
            PaperExecutionState.SUBMISSION_IN_PROGRESS
        ) == 1

    def test_an_uncertain_answer_with_a_body_is_recorded_as_said(self) -> None:
        world = _world()
        _authorize(world)
        _uncertain_broker("server-error-503", world)
        _submit(world)
        (acknowledgement,) = world["acknowledgements"].rows
        assert acknowledgement.http_status == 503
        assert "unavailable" in acknowledgement.sanitized_payload

    def test_a_definitive_refusal_is_rejected_and_still_sent_only_once(self) -> None:
        world = _world()
        _authorize(world)
        world["broker"].submit_status = 403
        world["broker"].submit_body = '{"code": 40310000, "message": "insufficient buying power"}'
        result = _submit(world)
        assert result.attempt.state is PaperExecutionState.REJECTED
        assert result.attempt.failure_code == "HTTP_403"
        assert _submit(world).dispatched is False
        assert len(world["broker"].submitted) == 1

    def test_a_definitely_unsent_request_is_rejected_and_never_resent(self) -> None:
        world = _world()
        _authorize(world)
        world["broker"].submit_raises = BrokerNotSentError("connection refused")
        assert _submit(world).attempt.state is PaperExecutionState.REJECTED
        assert _submit(world).dispatched is False
        assert len(world["broker"].submitted) <= 1

    def test_reconciliation_finds_the_order_the_uncertain_answer_hid(self) -> None:
        world = _world()
        _authorize(world)
        _uncertain_broker("fake-500-without-view", world)
        attempt = _submit(world).attempt
        world["broker"].lookup_view = FakeView(
            client_order_id=attempt.client_order_id, status="accepted"
        )
        reconciled = _reconcile(world, at_seconds=5)
        assert reconciled.state is PaperExecutionState.PAPER_ACCEPTED
        assert reconciled.broker_order_id == "broker-1"
        # Two lookups of the SAME identity: the pre-send identity check (F1) and the
        # reconciliation. Never a different id.
        assert world["broker"].lookups == [attempt.client_order_id] * 2
        assert [state for _, state in world["attempts"].transitions][-2:] == [
            PaperExecutionState.PAPER_SUBMITTED,
            PaperExecutionState.PAPER_ACCEPTED,
        ]
        assert len(world["broker"].submitted) == 1

    def test_reconciliation_resolves_an_absent_order_only_under_the_bounded_policy(self) -> None:
        world = _world()
        _authorize(world)
        _uncertain_broker("timeout-after-send", world)
        _submit(world)
        world["broker"].lookup_status = 404
        world["broker"].lookup_view = None
        assert _reconcile(world, at_seconds=120).state is PaperExecutionState.SUBMISSION_UNKNOWN
        # Q-4: the waiting interval runs on the broker clock from the FIRST round (the anchor);
        # one second after it is not 60 seconds after it.
        assert _reconcile(world, at_seconds=121).state is PaperExecutionState.SUBMISSION_UNKNOWN
        resolved = _reconcile(world, at_seconds=181)
        assert resolved.state is PaperExecutionState.REJECTED
        assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
        assert len(world["broker"].submitted) == 1


class TestAnInterruptedDispatchCanBeReconciled:
    def _stuck_in_progress(self) -> dict[str, Any]:
        """A dispatch that crashed after claiming and before recording any answer."""
        world = _world()
        _authorize(world)
        # CRASH-CONSISTENT LINEAGE (L1): the interruption comes AFTER the request left --
        # the fake broker receives the order, then raises -- so the attempt carries its
        # send-boundary record. An attempt that died before that boundary has no lineage and
        # is never attributed a found order (`test_m085_pre_send_crash.py`); this helper used
        # to replace `submit_order` wholesale, i.e. die before any send, which was the L1 gap.
        world["broker"].submit_raises = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            _submit(world)
        world["broker"].submit_raises = None
        assert len(world["broker"].submitted) == 1
        (attempt,) = world["attempts"].rows.values()
        assert attempt.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
        return world

    def test_absence_never_resolves_an_interrupted_dispatch(self) -> None:
        # Nothing proves an interrupted dispatch did not send, and nothing proves its
        # dispatcher has stopped: repeated not-found answers leave it for an operator.
        world = self._stuck_in_progress()
        world["broker"].lookup_status = 404
        world["broker"].lookup_view = None
        transitions = list(world["attempts"].transitions)
        for seconds in (120, 240, 900):
            state = _reconcile(world, at_seconds=seconds).state
            assert state is PaperExecutionState.SUBMISSION_IN_PROGRESS
        # One pre-send identity lookup by the dispatcher, then one per reconciliation.
        assert len(world["broker"].lookups) == 1 + 3
        assert world["attempts"].transitions == transitions
        assert len(world["broker"].submitted) == 1, "reconciliation never sends"

    def test_absence_while_the_dispatcher_is_still_sending_never_rejects(self) -> None:
        # THE REVIEW'S RACE. The dispatcher is past the claim but has not sent: two
        # reconciliations, minutes apart, get not-found. The order is then sent. The
        # replaced policy recorded REJECTED in between, leaving a live paper order.
        world = _world()
        _authorize(world)
        original = world["broker"].submit_order
        seen: list[PaperExecutionState] = []

        def still_sending(
            order: object, *, before_send: Callable[[], None] | None = None
        ) -> object:
            world["broker"].lookup_status = 404
            world["broker"].lookup_view = None
            for seconds in (120, 240):
                seen.append(_reconcile(world, at_seconds=seconds).state)
            return original(order, before_send=before_send)

        world["broker"].submit_order = still_sending
        result = _submit(world)
        assert seen == [PaperExecutionState.SUBMISSION_IN_PROGRESS] * 2
        assert result.dispatched is True
        assert result.attempt.state is not PaperExecutionState.REJECTED
        assert result.attempt.failure_code != "NOT_FOUND_AT_BROKER"
        assert len(world["broker"].submitted) == 1

    def test_a_live_dispatch_is_left_to_finish(self) -> None:
        world = self._stuck_in_progress()
        lookups_before = list(world["broker"].lookups)  # the dispatcher's own pre-send lookup
        assert _reconcile(world, at_seconds=10).state is PaperExecutionState.SUBMISSION_IN_PROGRESS
        assert world["broker"].lookups == lookups_before, "a live dispatch is not even looked up"

    def test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer(self) -> None:
        world = self._stuck_in_progress()
        (attempt,) = world["attempts"].rows.values()
        world["broker"].lookup_view = FakeView(
            client_order_id=attempt.client_order_id, status="filled", filled_quantity="1"
        )
        reconciled = _reconcile(world, at_seconds=120)
        assert reconciled.state is PaperExecutionState.FILLED
        assert world["broker"].lookups[-1] == attempt.client_order_id
        # And it is still one order: the reconciliation asked, it did not send.
        assert len(world["broker"].submitted) == 1
        # EVERY RECORDED EDGE IS ONE THE CLOSED TABLE ALLOWS. The fake store does not
        # enforce the table -- the database trigger does -- so without this the handler
        # could jump SUBMISSION_IN_PROGRESS -> FILLED here and be refused only in
        # production. Campaign run 1 found exactly that: the mutation survived.
        states = [PaperExecutionState.DISPATCH_CLAIMED] + [
            state
            for attempt_id, state in world["attempts"].transitions
            if attempt_id == attempt.attempt_id
        ]
        for current, target in zip(states, states[1:], strict=False):
            assert current is target or is_paper_transition_allowed(current, target), (
                current,
                target,
            )
        assert PaperExecutionState.PAPER_SUBMITTED in states


# ---------------------------------------------------------------------------
# P2 -- a terminal attempt is immutable
# ---------------------------------------------------------------------------


class TestATerminalAttemptIsImmutable:
    def _filled(self) -> dict[str, Any]:
        world = _world()
        _authorize(world)
        world["broker"].submit_fields = {"status": "filled", "filled_quantity": "1"}
        assert _submit(world).attempt.state is PaperExecutionState.FILLED
        return world

    @pytest.mark.parametrize(
        "target",
        [PaperExecutionState.FILLED, PaperExecutionState.CANCELED, PaperExecutionState.EXPIRED],
    )
    def test_no_update_reaches_a_terminal_attempt(self, target: PaperExecutionState) -> None:
        world = self._filled()
        before = dict(world["attempts"].rows)
        with pytest.raises(ValueError, match="terminal and is immutable"):
            world["attempts"].transition(
                attempt_id="ATT-1", target=target, at=_NOW, broker_order_id="rewritten"
            )
        assert world["attempts"].rows == before

    def test_reconciliation_neither_asks_nor_writes_after_a_terminal_state(self) -> None:
        world = self._filled()
        transitions = list(world["attempts"].transitions)
        lookups = list(world["broker"].lookups)  # the dispatch's own pre-send identity check
        assert _reconcile(world, at_seconds=600).state is PaperExecutionState.FILLED
        assert world["broker"].lookups == lookups
        assert world["attempts"].transitions == transitions


# ---------------------------------------------------------------------------
# T1 -- the liquidation deadline at dispatch
# ---------------------------------------------------------------------------


class TestTheLiquidationDeadlineAtDispatch:
    def test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline(self) -> None:
        # Liquidation at 15:45 New York, written while this host ran 30 minutes slow.
        # A new process dispatches at 15:50 on the broker's clock with the host still
        # 30 minutes behind: the replaced mapping said 16:15 and let it through.
        liquidation = _NOW.replace(hour=19, minute=45)
        intent = an_intent(
            mandatory_liquidation_at=liquidation, expires_at=_NOW + timedelta(hours=8)
        )
        # An entry window that still admits 15:50, so the liquidation deadline is the
        # only rule that can refuse. Under the 15:30 window the window refused first and
        # removing the liquidation rule was not observable (campaign run 1).
        world = _world(
            intents=base.FakeIntents(intent),
            time_bases=time_bases_for(a_provenance(intent, proposal_offset=timedelta(minutes=30))),
            configurations=FakeConfigurations(
                a_configuration(
                    latest_entry_time=time(15, 55), mandatory_liquidation_time=time(16, 0)
                )
            ),
        )
        # Still valid at 15:50 (and inside the intent's eight hours), for the same reason:
        # an expired authorization would otherwise refuse in the liquidation rule's place.
        _authorize(world, validity_seconds=6 * 3600)
        broker_time = liquidation + timedelta(minutes=5)
        with pytest.raises(
            PaperExecutionRefusedError,
            match="mandatory liquidation deadline has passed on the broker's clock",
        ):
            _HELPER._dispatch_in_a_new_process(
                world, host_now=broker_time - timedelta(minutes=30), broker_time=broker_time
            )
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    @pytest.mark.parametrize("phase", ["claim", "connect"])
    def test_a_liquidation_deadline_crossed_during_a_wait_never_submits(
        self, operation_clock: FrozenDateTimeFactory, phase: str
    ) -> None:
        intent = an_intent(mandatory_liquidation_at=_NOW + timedelta(seconds=1))
        world = _world(intents=base.FakeIntents(intent))
        _authorize(world)
        target, method = {
            "claim": (world["attempts"], "claim_dispatch"),
            "connect": (world["broker"], "submit_order"),
        }[phase]
        original = getattr(target, method)

        def delayed(*args: object, **kwargs: object) -> object:
            operation_clock.tick(delta=timedelta(seconds=2))
            return original(*args, **kwargs)

        setattr(target, method, delayed)
        result = _submit(world)
        _assert_not_sent(result, "liquidation deadline")
        assert world["broker"].submitted == []
        assert _submit(world).dispatched is False


def test_the_fakes_used_here_record_every_submission() -> None:
    # Anti-vacuity for every `submitted == []` above: the fake does record a send.
    world = _world()
    _authorize(world)
    assert _submit(world).dispatched is True
    assert len(world["broker"].submitted) == 1
    assert isinstance(world["acknowledgements"], FakeAcknowledgements)
    assert isinstance(world["events"], FakeEvents)
    assert isinstance(world["attempts"], FakeAttempts)
