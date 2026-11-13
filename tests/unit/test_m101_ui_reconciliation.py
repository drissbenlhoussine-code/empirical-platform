"""M101 -- Today / Active / execution-page reconciliation (display semantics only).

INCIDENT (2026-11-13, read-only reconciliation): Today showed `Positions 2`, `Active executions 3`
and `Open opportunities 2` while the broker held nothing. Every number was explained by the durable
records: two October entries closed by Owner-recorded external sales, one approved intent that was
never authorized or sent, and one approval that never issued an intent. The counters only knew
about closures made through a platform exit attempt, and the cards said "Approved; awaiting
execution" for an intent that had expired a month earlier.

These tests pin every corrected classification over the in-memory world (REAL service, REAL exit
console, REAL simulation broker, virtual clock). They never touch a broker or a database, and they
assert that no historical record is removed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.unit._m085_fakes import _NOW as _POLICY_NOW
from tests.unit._m085_fakes import a_policy
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
    external_position_closure_id,
)
from empirical_platform.decision_candidate.paper_execution import (
    PaperExecutionState,
    quote_refusal,
)
from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.shared.brokerage.paper_time import BoundedInstant
from empirical_platform.usecases.operator_console import (
    HistoryEntry,
    HumanState,
    intent_expired_unsubmitted,
)
from empirical_platform.usecases.operator_console_exits import (
    CATEGORY_EXPIRED_UNSUBMITTED,
    CATEGORY_EXTERNALLY_CLOSED,
    CATEGORY_POSITION_CLOSED,
    CATEGORY_WORKING_ENTRY,
)
from empirical_platform.usecases.paper_operator_console import paper_health


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _intent(world: World) -> str:
    return f"INT-{world.proposal_id('AAPL')}"


def _approve_and_fill(world: World) -> str:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal)
    assert world.service.confirm_approval(proposal, view.ticket).sent == "sent"
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    entry = world.repositories.attempts.for_intent(_intent(world))
    assert entry is not None and entry.state is PaperExecutionState.FILLED
    return _intent(world)


def _go_to(world: World, moment: datetime) -> None:
    world.clock.advance((moment - world.clock.utc).total_seconds())


def _counters(world: World) -> tuple[int, int, int]:
    today = world.service.today()
    return (
        today.active_positions_count,
        today.active_executions_count,
        today.open_opportunities_count,
    )


def _record_external_closure(world: World, intent: str) -> None:
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.filled_quantity is not None
    world.external_closures.save(
        ExternalPositionClosure(
            closure_id=external_position_closure_id(intent),
            entry_intent_governance_id=intent,
            symbol="AAPL",
            quantity=int(entry.filled_quantity),
            broker_order_id="BRK-EXTERNAL-SELL-1",
            client_order_id="EXTERNAL-SELL-1",
            filled_avg_price=Decimal("227.40"),
            recorded_by="owner",
            recorded_at=world.clock.utc,
        )
    )


def _approved_never_sent(world: World) -> str:
    """The durable shape of the 2026-10-15 intent: approved, intent issued, NO attempt row."""
    intent = _approve_and_fill(world)
    world.repositories.attempts.rows.clear()  # type: ignore[attr-defined]
    assert world.repositories.attempts.for_intent(intent) is None
    return intent


# -- (1) Positions: a position that is no longer held is not counted ----------------------


def test_a_held_position_is_counted_by_positions_and_active_executions(world: World) -> None:
    _approve_and_fill(world)
    assert _counters(world) == (1, 1, 0)


def test_an_externally_closed_position_is_not_counted_as_held_or_active(world: World) -> None:
    intent = _approve_and_fill(world)
    _record_external_closure(world, intent)
    assert _counters(world) == (0, 0, 0)
    assert world.service.active_trades() == ()
    summary = world.service.execution(intent)
    assert summary.category == CATEGORY_EXTERNALLY_CLOSED and not summary.position_open


def test_an_externally_closed_entry_stays_in_history_and_keeps_its_records(world: World) -> None:
    intent = _approve_and_fill(world)
    _record_external_closure(world, intent)
    (row,) = world.service.history(symbol="AAPL")
    assert row.intent_id == intent and row.final_state is HumanState.FILLED
    assert world.repositories.attempts.for_intent(intent) is not None  # nothing deleted
    assert world.external_closures.for_entry(intent) is not None


def test_a_platform_verified_exit_closure_is_also_not_counted(world: World) -> None:
    intent = _approve_and_fill(world)
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    assert world.service.exits.confirm(intent, review.ticket).ok  # type: ignore[union-attr]
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    assert world.service.execution(intent).category == CATEGORY_POSITION_CLOSED
    assert _counters(world) == (0, 0, 0)


# -- (5) No contradictory "Open position" wording next to a closure -----------------------


def test_a_closed_externally_execution_never_says_open_position(world: World) -> None:
    intent = _approve_and_fill(world)
    assert "Open position" in (world.service.execution(intent).pending_reason or "")  # before
    _record_external_closure(world, intent)
    summary = world.service.execution(intent)
    assert summary.pending_reason is None
    assert summary.exit_status.startswith("Position closed externally")
    for text in (summary.pending_reason or "", summary.exit_status, *summary.warnings):
        assert "Open position" not in text and "exit locked" not in text


def test_a_platform_closed_execution_never_says_open_position(world: World) -> None:
    intent = _approve_and_fill(world)
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    summary = world.service.execution(intent)
    assert summary.position_closed and summary.pending_reason is None
    assert "Open position" not in summary.exit_status


# -- (2)(3)(4) An intent that expired unsent -----------------------------------------------


def test_a_live_unsent_intent_is_still_approved_and_awaiting_execution(world: World) -> None:
    intent = _approved_never_sent(world)
    record = world.repositories.intents.get(intent)
    assert record is not None
    _go_to(world, record.expires_at - timedelta(seconds=1))
    (card,) = world.service.today().opportunities
    assert card.attention_note is not None and "awaiting execution" in card.attention_note
    assert world.service.execution(intent).category == CATEGORY_WORKING_ENTRY
    assert _counters(world)[1:] == (1, 1)  # still active and still an open opportunity


def test_an_unsent_intent_that_expired_is_not_active_open_or_awaiting(world: World) -> None:
    intent = _approved_never_sent(world)
    record = world.repositories.intents.get(intent)
    assert record is not None
    _go_to(world, record.expires_at)
    summary = world.service.execution(intent)
    assert summary.category == CATEGORY_EXPIRED_UNSUBMITTED
    assert summary.pending_reason == "Expired — never submitted. Nothing was sent."
    assert world.service.active_trades() == ()
    assert _counters(world) == (0, 0, 0)
    cards = world.service.today().opportunities
    for card in cards:  # the stale card, if shown at all, never claims it awaits execution
        assert "awaiting execution" not in (card.attention_note or "")
        assert card.state is HumanState.EXPIRED


def test_the_proposal_state_and_the_exit_console_agree_on_the_expiry_boundary(
    world: World,
) -> None:
    intent = _approved_never_sent(world)
    record = world.repositories.intents.get(intent)
    assert record is not None
    for offset, expected in ((-1, False), (0, True), (1, True)):
        moment = record.expires_at + timedelta(seconds=offset)
        _go_to(world, moment)
        by_helper = intent_expired_unsubmitted(record, None, moment)
        by_console = world.service.execution(intent).category == CATEGORY_EXPIRED_UNSUBMITTED
        assert by_helper is by_console is expected


def test_an_approval_that_never_issued_an_intent_stops_being_open_once_it_expires(
    world: World,
) -> None:
    intent = _approve_and_fill(world)
    proposal_id = world.proposal_id("AAPL")
    world.repositories.attempts.rows.clear()  # type: ignore[attr-defined]
    world.repositories.intents.rows.pop(intent)  # type: ignore[attr-defined]
    proposal = world.repositories.proposals.get(proposal_id)
    assert proposal is not None
    _go_to(world, proposal.expires_at - timedelta(seconds=1))
    (card,) = world.service.today().opportunities
    assert card.state is HumanState.APPROVED and "no order intent was issued" in (
        card.attention_note or ""
    )
    assert _counters(world)[2] == 1
    _go_to(world, proposal.expires_at + timedelta(seconds=1))
    (card,) = world.service.today().opportunities
    assert card.state is HumanState.EXPIRED
    assert "before it expired" in (card.attention_note or "")
    assert _counters(world) == (0, 0, 0)
    assert world.repositories.proposals.get(proposal_id) is not None  # the record is preserved


def _drop_attempts_for(world: World, intent: str) -> None:
    rows = world.repositories.attempts.rows  # type: ignore[attr-defined]
    for key in [k for k, a in rows.items() if a.intent_governance_id == intent]:
        rows.pop(key)


def test_the_2026_11_13_live_shape_reconciles_to_zero_counters(world: World) -> None:
    """The exact shape the read-only reconciliation found on the live host: an approval that never
    issued an intent (10-06), an entry closed by an Owner-recorded sale (10-09), an approved
    intent that was never authorized or sent (10-15) and a second externally closed entry
    (10-16). The broker is flat. Before M101 this read Positions 2 / Active executions 3 / Open
    opportunities 2; after it, nothing is counted because nothing is held, working or awaiting."""
    day = timedelta(days=1)

    first = _approve_and_fill(world)  # 10-06: approved, but no intent was ever issued
    _drop_attempts_for(world, first)
    world.repositories.intents.rows.pop(first)  # type: ignore[attr-defined]

    world.store.reset()  # the broker is flat again between the real entries
    world.clock.advance(day.total_seconds())
    closed_a = _approve_and_fill(world)  # 10-09: filled, then sold outside the platform
    _record_external_closure(world, closed_a)

    world.store.reset()
    world.clock.advance(day.total_seconds())
    unsent = _approve_and_fill(world)  # 10-15: approved, intent issued, never sent
    _drop_attempts_for(world, unsent)

    world.store.reset()
    world.clock.advance(day.total_seconds())
    closed_b = _approve_and_fill(world)  # 10-16: filled, then sold outside the platform
    _record_external_closure(world, closed_b)

    world.clock.advance(30 * day.total_seconds())  # a month later, as on the live host
    assert _counters(world) == (0, 0, 0)
    assert world.service.today().opportunities == ()  # nothing stale is offered on Today
    assert world.service.active_trades() == ()
    # every historical record is still there
    assert len(world.service.history(symbol="AAPL")) == 4
    for intent in (closed_a, closed_b):
        assert world.external_closures.for_entry(intent) is not None
    assert world.service.execution(unsent).category == CATEGORY_EXPIRED_UNSUBMITTED


# -- (6) Quote age: display only, freshness validation untouched --------------------------


class _Broker:
    endpoint_host = "paper-api.alpaca.markets"

    def fetch_account(self) -> tuple[int, dict[str, object]]:
        return 200, {"id": "acct", "status": "ACTIVE"}

    def fetch_clock(self) -> SimpleNamespace:
        return SimpleNamespace(is_open=True, next_open=None, next_close=None)

    def fetch_asset(self, symbol: str) -> SimpleNamespace:
        del symbol
        return SimpleNamespace(tradable=True, status="active")

    def fetch_position(self, symbol: str) -> None:
        del symbol


class _Market:
    endpoint_host = "data.alpaca.markets"

    def __init__(self, captured_at: datetime | None) -> None:
        self._captured_at = captured_at

    def fetch_quote(self, symbol: str) -> SimpleNamespace | None:
        del symbol
        if self._captured_at is None:
            return None
        return SimpleNamespace(
            bid=Decimal("100.00"),
            ask=Decimal("100.05"),
            captured_at=self._captured_at,
            source="alpaca-iex",
        )


_HEALTH_NOW = datetime(2026, 11, 13, 20, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("captured_offset_seconds", "expected"),
    [(2.2, "0.0"), (0.04, "0.0"), (0.0, "0.0"), (-0.2, "0.2"), (-5.4, "5.4"), (-61.0, "61.0")],
)
def test_the_health_quote_age_is_never_negative(
    captured_offset_seconds: float, expected: str
) -> None:
    captured = _HEALTH_NOW + timedelta(seconds=captured_offset_seconds)
    view = paper_health(
        broker=_Broker(),  # type: ignore[arg-type]
        market_data=_Market(captured),  # type: ignore[arg-type]
        now=_HEALTH_NOW,
    )
    assert view.quote_age_seconds == expected
    assert not view.quote_age_seconds.startswith("-")


def test_a_missing_quote_still_shows_no_age() -> None:
    view = paper_health(
        broker=_Broker(),  # type: ignore[arg-type]
        market_data=_Market(None),  # type: ignore[arg-type]
        now=_HEALTH_NOW,
    )
    assert view.quote_age_seconds == ""


def test_quote_freshness_validation_is_not_weakened() -> None:
    """The display clamp lives in `paper_health` only: the send-time gate still refuses a quote
    older than the limit and one dated after the latest possible broker time."""
    policy = a_policy()
    common = {"bid": Decimal("4.00"), "ask": Decimal("4.01"), "policy": policy}
    at = BoundedInstant(earliest=_POLICY_NOW, latest=_POLICY_NOW)
    stale = quote_refusal(captured_at=_POLICY_NOW - timedelta(seconds=300), broker_now=at, **common)  # type: ignore[arg-type]
    future = quote_refusal(captured_at=_POLICY_NOW + timedelta(seconds=5), broker_now=at, **common)  # type: ignore[arg-type]
    fresh = quote_refusal(captured_at=_POLICY_NOW - timedelta(seconds=1), broker_now=at, **common)  # type: ignore[arg-type]
    assert stale is not None and "old" in stale
    assert future is not None and "after the latest possible" in future
    assert fresh is None


# -- (7) History on a phone: minimal CSS, every evidence column and the scroll kept -------


def _mobile_block() -> str:
    css = html.STYLESHEET
    start = css.index("@media (max-width:600px)")
    return css[start:]


def test_the_history_table_keeps_its_horizontal_scroll_and_gains_phone_rules() -> None:
    css = html.STYLESHEET
    assert ".table-wrap{overflow-x:auto;" in css  # the scroll container is unchanged
    block = _mobile_block()
    assert (
        "table.history th:first-child,table.history td:first-child{position:sticky;left:0" in block
    )
    assert "-webkit-overflow-scrolling:touch" in block
    assert "table.history{font-size:13px}" in block
    # still one balanced media block (a stray brace would swallow the rules after it)
    assert block.count("{") == block.count("}")
    # nothing hides a column or turns the table into cards
    assert "display:none" not in block and "display:block" not in block.split("table.history")[1]


def test_the_history_page_still_renders_every_evidence_column() -> None:
    entry = HistoryEntry(
        proposal_id="PRP-1",
        symbol="AAPL",
        created_at=_HEALTH_NOW,
        proposal_state="Filled",
        decision="Approved",
        decided_at=_HEALTH_NOW,
        decided_by="owner",
        execution_kind="entry",
        execution_outcome="Filled",
        final_state=HumanState.FILLED,
        quantity="1",
        price="341.67",
        result="Closed round trip",
        intent_id="INT-1",
        timestamp=_HEALTH_NOW,
    )
    page = html.history_page(
        (entry,),
        filters={},
        capability_label="Paper",
        kill_switch_engaged=False,
        plan_cells={"INT-1": "Trigger STOP<br>Zero-verified Yes"},
    )
    for column in (
        "When",
        "Symbol",
        "Model proposal",
        "Owner decision",
        "Execution",
        "Final state",
        "Qty @ price",
        "Result",
        "Plan",
    ):
        assert f"<th>{column}</th>" in page, column
    assert '<div class="table-wrap"><table class="history">' in page
    assert "Zero-verified Yes" in page
