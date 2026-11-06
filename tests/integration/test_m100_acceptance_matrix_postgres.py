"""M100 -- the 24-step end-to-end acceptance matrix, on PostgreSQL, with a simulated broker.

WHAT IS REAL: PostgreSQL Store B at the current head (v2 entry-risk triggers), Store C at its own
head, the approved-plan table, every M084/M085/M087/M089 handler, the D1 trading-limit gate and the
D3 exit state machine. WHAT IS SIMULATED: only the broker and the clock. No network, no real order.

The matrix was defined in this milestone (no 24-step list existed in the repository); each step is
one test whose docstring states what it proves, and each records machine-readable evidence. Set
``M100_EVIDENCE_PATH`` to write that evidence to a JSON file.

Steps 1-11 entry execution and uncertainty, 12-17 trading limits, 18-24 exits and recovery.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from tests.integration._m085_support import build_engine
from tests.integration._m089_support import build_engine_c
from tests.integration._m100_matrix_support import Matrix

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedOrder,
    SimulationExitScenario,
    SimulationScenario,
)
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError
from empirical_platform.usecases.position_plan_manager import (
    EXIT_MAXIMUM_ATTEMPTS,
    EXIT_UNPROTECTED_ESCALATION_SECONDS,
    EXIT_WORKING_REST_SECONDS,
    PlanEvaluationOutcome,
    PlanOutcomeKind,
)

pytestmark = pytest.mark.integration

_EVIDENCE: dict[str, dict[str, object]] = {}


def evidence(step: int, title: str, **facts: object) -> None:
    _EVIDENCE[f"STEP-{step:02d}"] = {"title": title, **facts}


@pytest.fixture(scope="module", autouse=True)
def _write_evidence() -> Iterator[None]:
    yield
    target = os.environ.get("M100_EVIDENCE_PATH")
    if target:
        ordered = dict(sorted(_EVIDENCE.items()))
        Path(target).write_text(json.dumps(ordered, indent=2, sort_keys=True), encoding="utf-8")


@pytest.fixture(scope="module")
def engine_b() -> Iterator[Engine]:
    yield from build_engine("head")


@pytest.fixture(scope="module")
def engine_c() -> Iterator[Engine]:
    yield from build_engine_c("head")


@pytest.fixture
def m(engine_b: Engine, engine_c: Engine, tmp_path: Path) -> Iterator[Matrix]:
    matrix = Matrix(engine_b, engine_c, tmp_path)
    try:
        yield matrix
    finally:
        matrix.close()


def _filler(index: int, *, status: str, symbol: str) -> SimulatedOrder:
    return SimulatedOrder(
        broker_order_id=f"sim-x-{index:04d}",
        client_order_id=f"filler-{index:04d}",
        symbol=symbol,
        side="buy",
        quantity="1",
        order_type="limit",
        limit_price="1.00",
        time_in_force="day",
        extended_hours=False,
        status=status,
        filled_quantity="0",
        filled_avg_price=None,
        scenario="FILLER",
        lookups=0,
        cancel_requested=False,
        received_at="2026-06-10T11:00:00+00:00",
    )


def _attempt(m: Matrix, entry: object) -> ExecutionAttempt:
    attempt = m.paper.execution_attempts.for_intent(entry.intent_id)  # type: ignore[attr-defined]
    assert attempt is not None
    return attempt


def _tick(m: Matrix, seconds: float = 0) -> tuple[PlanEvaluationOutcome, ...]:
    if seconds:
        m.clock.advance(seconds)
    return m.manager().evaluate_once(now=m.clock.utc)


def _live_sells(m: Matrix) -> list[object]:
    live = {"new", "accepted", "partially_filled", "pending_cancel", "pending_new"}
    return [o for o in m.sells() if o.status in live]  # type: ignore[attr-defined]


# =============================================================================================
# 1-11  Entry execution, rejection, partial fills, duplicates, outages, restarts
# =============================================================================================


def test_step_01_the_entry_chain_is_persisted_at_the_current_head_with_governed_risk(
    m: Matrix,
) -> None:
    """prepare -> approve -> issue -> preview -> authorize persist on PostgreSQL; no order yet."""
    m.stage()
    entry = m.entry()
    intent = m.m084.approved_order_intents.get(entry.intent_id)
    assert intent is not None and intent.entry_risk is not None  # v2 evidence, trigger-enforced
    assert m.count("trade_proposal") == 1 and m.count("approved_order_intent") == 1
    assert m.count("paper_submission_preview") == 1
    assert m.count("paper_execution_authorization") == 1
    assert m.store.orders() == ()  # nothing has reached the broker
    evidence(1, "entry chain persisted", intent=entry.intent_id, quantity=intent.quantity)


def test_step_02_normal_execution_sends_exactly_one_order_and_records_the_attempt(
    m: Matrix,
) -> None:
    """Submit passes the D1 gate twice (pre-claim, send boundary) and dispatches once."""
    m.stage()
    entry = m.entry()
    result = m.submit(entry)
    assert result.dispatched is True  # type: ignore[attr-defined]
    assert len(m.buys()) == 1
    attempt = _attempt(m, entry)
    assert attempt.state in {
        PaperExecutionState.PAPER_SUBMITTED,
        PaperExecutionState.PAPER_ACCEPTED,
    }
    assert m.count("paper_execution_attempt") == 1
    evidence(2, "one order dispatched", state=attempt.state.value, orders=len(m.buys()))


def test_step_03_reconciliation_fills_the_entry_and_the_broker_holds_the_position(
    m: Matrix,
) -> None:
    """Broker truth, not the local record, closes the loop: FILLED + a real position."""
    entry = m.open_position()
    attempt = _attempt(m, entry)
    assert attempt.state is PaperExecutionState.FILLED
    assert m.store.position("AAPL") == int(attempt.filled_quantity)
    evidence(
        3, "entry filled", filled=str(attempt.filled_quantity), position=m.store.position("AAPL")
    )


def test_step_04_a_duplicate_submit_never_sends_a_second_order(m: Matrix) -> None:
    """A retry of the same intent returns the existing attempt; the broker sees one order."""
    m.stage()
    entry = m.entry()
    first = m.submit(entry)
    again = m.submit(entry)
    assert first.dispatched is True and again.dispatched is False  # type: ignore[attr-defined]
    assert len(m.buys()) == 1 and m.count("paper_execution_attempt") == 1
    evidence(4, "duplicate submit refused", orders=len(m.buys()))


def test_step_05_two_concurrent_submitters_produce_exactly_one_order(m: Matrix) -> None:
    """The PostgreSQL claim is the arbiter: of two simultaneous submits only one dispatches."""
    m.stage()
    entry = m.entry()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(m.submit, entry, snapshot_id=f"SNP-RACE-{i}") for i in range(2)]
        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=30))
            except PaperExecutionRefusedError as error:
                results.append(error)
    assert len(m.buys()) == 1
    assert m.count("paper_execution_attempt") == 1
    dispatched = [r for r in results if getattr(r, "dispatched", False)]
    assert len(dispatched) == 1
    evidence(5, "concurrent submitters", orders=len(m.buys()), attempts=1)


def test_step_06_a_broker_rejection_is_recorded_and_no_position_exists(m: Matrix) -> None:
    """A definitive rejection ends REJECTED; the account stays flat."""
    m.stage(entry=SimulationScenario.BROKER_REJECTION)
    entry = m.entry()
    m.submit(entry)
    attempt = _attempt(m, entry)
    assert attempt.state is PaperExecutionState.REJECTED
    assert m.store.position("AAPL") == 0
    evidence(6, "broker rejection", state=attempt.state.value, position=0)


def test_step_07_a_partial_entry_fill_blocks_the_exit_until_the_entry_is_final(m: Matrix) -> None:
    """A part-filled entry can still fill: the exit pipeline refuses to attribute the position."""
    m.stage(entry=SimulationScenario.PARTIAL_FILL)
    entry = m.entry()
    m.submit(entry)
    for _ in range(3):
        m.clock.advance(5)
        m.reconcile(entry)
    attempt = _attempt(m, entry)
    assert attempt.state is PaperExecutionState.PARTIALLY_FILLED
    held = m.store.position("AAPL")
    assert 0 < held < 5
    m.plan(entry)
    m.breach_stop()
    outcomes = _tick(m)
    assert outcomes[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
    assert "partially filled" in outcomes[0].detail
    assert m.sells() == []
    evidence(7, "partial entry", filled=held, exit_sent=False)


def test_step_08_a_failure_before_any_byte_is_sent_leaves_nothing_at_the_broker(
    m: Matrix,
) -> None:
    """NOT_SENT is terminal and provably created nothing; it does not poison later entries."""
    m.stage(entry=SimulationScenario.NETWORK_FAILURE_BEFORE_SEND)
    entry = m.entry()
    m.submit(entry)
    attempt = _attempt(m, entry)
    assert attempt.state is PaperExecutionState.REJECTED and attempt.failure_code == "NOT_SENT"
    assert m.buys() == []
    # The NOT_SENT attempt is not counted as an order or as exposure by the limit gate.
    m.stage("MSFT", entry=SimulationScenario.ACCEPTED_THEN_FILLED)
    second = m.entry("MSFT")
    assert m.submit(second).dispatched is True  # type: ignore[attr-defined]
    evidence(8, "failure before send", orders_before_retry=0, later_entry_allowed=True)


def test_step_09_an_ambiguous_submission_is_unknown_never_resent_and_reconciles(
    m: Matrix,
) -> None:
    """The request may have arrived: SUBMISSION_UNKNOWN, no second send, reconcile resolves it."""
    m.stage(entry=SimulationScenario.AMBIGUOUS_SUBMISSION)
    entry = m.entry()
    m.submit(entry)
    assert _attempt(m, entry).state is PaperExecutionState.SUBMISSION_UNKNOWN
    m.submit(entry)
    assert len(m.buys()) == 1
    m.clock.advance(65)  # past the absence-window so a "not found" could count; it IS found
    for _ in range(3):
        m.reconcile(entry)
        m.clock.advance(5)
    assert _attempt(m, entry).state in {
        PaperExecutionState.FILLED,
        PaperExecutionState.PAPER_ACCEPTED,
        PaperExecutionState.PAPER_SUBMITTED,
    }
    assert len(m.buys()) == 1
    evidence(9, "ambiguous submission", final=_attempt(m, entry).state.value, orders=1)


def test_step_10_a_broker_outage_during_limit_verification_blocks_without_spending_anything(
    m: Matrix, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unverifiable limits are a refusal: no attempt row, no order, authorization unconsumed."""
    m.stage()
    entry = m.entry()

    def _down(*, day_start: object) -> object:
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(m.broker, "fetch_portfolio_risk_evidence", _down)
    with pytest.raises(PaperExecutionRefusedError, match="could not be verified"):
        m.submit(entry)
    assert m.count("paper_execution_attempt") == 0 and m.buys() == []
    monkeypatch.undo()
    retry = m.submit(entry, snapshot_id="SNP-RETRY-0001")  # a retry carries a fresh snapshot id
    assert retry.dispatched is True  # type: ignore[attr-defined]  # outage over: retry works
    evidence(10, "outage blocks entry", attempts_during_outage=0, retry_dispatched=True)


def test_step_11_a_restart_mid_uncertainty_resumes_from_the_database_without_a_resend(
    m: Matrix,
) -> None:
    """Every connection and handler is rebuilt; durable state alone resolves the unknown."""
    m.stage(entry=SimulationScenario.AMBIGUOUS_SUBMISSION)
    entry = m.entry()
    m.submit(entry)
    assert _attempt(m, entry).state is PaperExecutionState.SUBMISSION_UNKNOWN
    m.restart()
    assert _attempt(m, entry).state is PaperExecutionState.SUBMISSION_UNKNOWN
    m.submit(entry)  # a new process retrying must not resend
    assert len(m.buys()) == 1
    for _ in range(3):
        m.clock.advance(5)
        m.reconcile(entry)
    assert len(m.buys()) == 1
    evidence(11, "restart mid-uncertainty", orders=1, final=_attempt(m, entry).state.value)


# =============================================================================================
# 12-17  Trading limits at the broker submission boundary (D1)
# =============================================================================================


def _refused(m: Matrix, entry: object, fragment: str) -> None:
    # each attempt carries a fresh snapshot id, as every real submit does
    _refused.calls += 1
    with pytest.raises(PaperExecutionRefusedError, match=fragment):
        m.submit(entry, snapshot_id=f"SNP-REF-{_refused.calls:04d}")
    assert m.count("paper_execution_attempt") == 0  # refused before the claim: nothing spent


_refused.calls = 0  # type: ignore[attr-defined]


def test_step_12_the_daily_realized_loss_limit_blocks_the_entry(m: Matrix) -> None:
    m.stage()
    entry = m.entry()
    m.store.stage_day_pnl(realized="-500", whole_day="-500")  # the configured limit is 500
    _refused(m, entry, "daily loss limit")
    assert m.buys() == []
    evidence(12, "daily loss limit", limit="500", observed="-500", orders=0)


def test_step_13_the_daily_order_count_limit_blocks_the_entry(m: Matrix) -> None:
    m.stage()
    entry = m.entry()
    for index in range(10):  # the configured limit is 10, rejected orders count
        m.store.put(_filler(index, status="rejected", symbol="MSFT"))
    _refused(m, entry, "daily limit is 10")
    assert not [o for o in m.buys() if not o.client_order_id.startswith("filler")]  # type: ignore[attr-defined]
    assert len(m.store.orders()) == 10
    evidence(13, "daily order count", limit=10, observed=10)


def test_step_14_the_simultaneous_position_limit_blocks_the_entry(m: Matrix) -> None:
    m.stage()
    entry = m.entry()
    held = {f"HLD{i:02d}": ("10.00", "10.10") for i in range(3)}  # the configured limit is 3
    m.stage(extra_quotes=held)
    for symbol in held:
        m.store.add_position(symbol, 1)
    _refused(m, entry, "simultaneous positions")
    evidence(14, "simultaneous positions", limit=3, held=3)


def test_step_15_existing_position_and_working_order_conflicts_block_the_entry(m: Matrix) -> None:
    m.stage()
    first = m.entry()
    m.store.add_position("AAPL", 1)
    _refused(m, first, "already exists in AAPL")
    m.store.reduce_position("AAPL", 1)
    m.store.put(_filler(1, status="accepted", symbol="AAPL"))
    _refused(m, first, "already exists in AAPL")
    evidence(15, "position and working-order conflicts", blocked=2)


def test_step_16_an_entry_claimed_elsewhere_counts_even_before_the_broker_lists_it(
    m: Matrix, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Broker lag + a concurrent claim: the durable attempt in PostgreSQL holds the slot."""
    held = {f"HLD{i:02d}": ("10.00", "10.10") for i in range(2)}  # 2 of 3 slots taken
    m.stage(extra_quotes=held)
    for symbol in held:
        m.store.add_position(symbol, 1)
    m.stage("MSFT")
    first, second = m.entry("AAPL"), m.entry("MSFT")
    frozen = m.broker.fetch_portfolio_risk_evidence(day_start=m.clock.utc)  # before the first send
    assert m.submit(first).dispatched is True  # type: ignore[attr-defined]
    monkeypatch.setattr(
        m.broker,
        "fetch_portfolio_risk_evidence",
        lambda *, day_start: replace(frozen, captured_at=m.clock.utc),
    )
    with pytest.raises(PaperExecutionRefusedError, match="simultaneous positions|in flight"):
        m.submit(second)
    assert not [o for o in m.buys() if o.symbol == "MSFT"]  # type: ignore[attr-defined]
    evidence(16, "in-flight claim under broker lag", second_order_sent=False)


def test_step_17_an_engaged_kill_switch_blocks_entries_but_never_exits(m: Matrix) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.stage("MSFT")
    pending = m.entry("MSFT")  # authorized while the switch was still released
    m.paper.execution_kill_switch.engage(changed_by="owner", changed_at=m.clock.utc, reason="drill")
    with pytest.raises(PaperExecutionRefusedError, match="kill switch"):
        m.submit(pending)
    assert [o for o in m.buys() if o.symbol == "MSFT"] == []  # type: ignore[attr-defined]
    m.breach_stop()
    outcomes = _tick(m)
    assert any(o.kind is PlanOutcomeKind.EXIT_CLAIMED for o in outcomes)
    _tick(m, 5)
    _tick(m, 5)
    assert m.store.position("AAPL") == 0
    evidence(17, "exit proceeds under kill switch", sells=len(m.sells()), entry_blocked=True)


# =============================================================================================
# 18-24  Exits (D3) and recovery
# =============================================================================================


def test_step_18_a_triggered_stop_sells_once_and_the_position_is_verified_closed(m: Matrix) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.breach_stop()
    for _ in range(4):
        _tick(m, 5)
    attempts = m.exit_rt.attempts.for_entry(entry.intent_id)
    assert len(attempts) == 1 and attempts[0].position_closed
    assert len(m.sells()) == 1 and m.store.position("AAPL") == 0
    evidence(18, "stop exit closes the position", sells=1, closed=True)


def test_step_19_repeated_ticks_and_manager_restarts_never_create_a_second_exit(m: Matrix) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.set_exit(SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    m.breach_stop()
    m.set_exit(SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    for index in range(20):
        _tick(m, 3)
        if index % 4 == 0:
            m.restart()  # a brand-new process every few ticks
        assert len(_live_sells(m)) <= 1
    assert len(m.sells()) == 1
    evidence(19, "no duplicate exit", ticks=20, restarts=5, sells=1)


def test_step_20_an_unfilled_exit_is_cancelled_confirmed_rearmed_and_fills(m: Matrix) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.breach_stop()
    m.set_exit(SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    _tick(m)
    _tick(m, EXIT_WORKING_REST_SECONDS + 1)  # rested: cancel REQUESTED
    assert (
        m.exit_rt.attempts.for_entry(entry.intent_id)[0].state is PositionExitState.CANCEL_REQUESTED
    )
    assert len(m.sells()) == 1  # a request is not a cancellation: no replacement yet
    _tick(m, 1)  # broker confirms
    assert m.exit_rt.attempts.for_entry(entry.intent_id)[0].state is PositionExitState.CANCELED
    m.set_exit(SimulationExitScenario.EXIT_FILLED)
    for _ in range(5):
        _tick(m, 2)
        assert len(_live_sells(m)) <= 1
    attempts = m.exit_rt.attempts.for_entry(entry.intent_id)
    assert len(attempts) == 2 and attempts[1].position_closed
    assert len({a.client_order_id for a in attempts}) == 2
    evidence(20, "cancel, confirm, re-arm", attempts=2, closed=True)


def test_step_21_a_partial_exit_fill_rearms_only_the_remainder_and_never_oversells(
    m: Matrix,
) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.breach_stop()
    m.set_exit(SimulationExitScenario.EXIT_PARTIAL_FILL)
    _tick(m)
    _tick(m, 2)
    first = m.exit_rt.attempts.for_entry(entry.intent_id)[0]
    sold = int(first.filled_quantity or 0)
    assert 0 < sold < 5
    _tick(m, EXIT_WORKING_REST_SECONDS + 1)
    _tick(m, 1)
    m.set_exit(SimulationExitScenario.EXIT_FILLED)
    for _ in range(6):
        _tick(m, 2)
        assert len(_live_sells(m)) <= 1
    attempts = m.exit_rt.attempts.for_entry(entry.intent_id)
    assert attempts[1].quantity == 5 - sold
    total = sum(int(float(o.filled_quantity)) for o in m.sells())  # type: ignore[attr-defined]
    assert total == 5 and m.store.position("AAPL") == 0
    evidence(21, "partial exit then remainder", first_fill=sold, second_qty=5 - sold, total=total)


def test_step_22_exhausted_exit_attempts_escalate_durably_and_block_new_entries(m: Matrix) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.breach_stop()
    m.set_exit(SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    _tick(m)
    for _ in range(300):
        _tick(m, 10)
        if m.paper.execution_kill_switch.is_engaged():
            break
    attempts = m.exit_rt.attempts.for_entry(entry.intent_id)
    assert len(attempts) == EXIT_MAXIMUM_ATTEMPTS
    risk = [
        e
        for e in m.exit_rt.events.for_entry(entry.intent_id)
        if e.event_type == "EXIT_UNRESOLVED_RISK"
    ]
    assert len(risk) == 1  # durable in Store C, written once
    assert m.paper.execution_kill_switch.is_engaged()  # durable in Store B
    m.stage("MSFT")
    with pytest.raises(Exception, match="kill switch"):
        m.entry("MSFT")  # preparing/previewing a new entry now refuses
    evidence(
        22, "unresolved exit risk", attempts=len(attempts), risk_events=1, entries_blocked=True
    )


def test_step_23_a_restart_in_the_middle_of_a_cancel_resumes_without_a_second_exit(
    m: Matrix,
) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.breach_stop()
    m.set_exit(SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    _tick(m)
    _tick(m, EXIT_WORKING_REST_SECONDS + 1)  # cancel requested
    m.restart()
    _tick(m, 1)
    assert m.exit_rt.attempts.for_entry(entry.intent_id)[0].state is PositionExitState.CANCELED
    m.restart()
    m.set_exit(SimulationExitScenario.EXIT_FILLED)
    for _ in range(5):
        _tick(m, 2)
        assert len(_live_sells(m)) <= 1
    assert m.exit_rt.attempts.for_entry(entry.intent_id)[-1].position_closed
    evidence(23, "restart mid-cancel", sells=len(m.sells()), closed=True)


def test_step_24_broker_outage_and_market_close_never_cause_a_blind_exit_action(
    m: Matrix, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = m.open_position()
    m.plan(entry)
    m.breach_stop()
    m.set_exit(SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    _tick(m)
    real = m.broker.fetch_order_by_client_order_id

    def _down(client_order_id: str) -> object:
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(m.broker, "fetch_order_by_client_order_id", _down)
    outcomes = _tick(m, EXIT_WORKING_REST_SECONDS + 30)
    assert outcomes[-1].kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert m.exit_rt.attempts.for_entry(entry.intent_id)[0].state is PositionExitState.ACCEPTED
    monkeypatch.setattr(m.broker, "fetch_order_by_client_order_id", real)
    # The DAY order lapses at the close; the market is closed; nothing is sent into it.
    (order,) = m.sells()
    m.store.put(replace(order, status="expired"))  # type: ignore[type-var]
    m.store.set_market_open(False)
    _tick(m, 1)
    waiting = _tick(m, 1)
    assert waiting[-1].kind is PlanOutcomeKind.EXIT_WAITING_FOR_MARKET
    escalated = _tick(m, EXIT_UNPROTECTED_ESCALATION_SECONDS + 1)
    assert escalated[-1].kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert len(m.sells()) == 1 and m.paper.execution_kill_switch.is_engaged()
    evidence(24, "outage then market close", sells=1, escalated=True, entries_blocked=True)
