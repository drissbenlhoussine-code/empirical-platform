"""FIX D1 -- daily loss, daily order count, simultaneous positions and total exposure are
enforced at the PAPER submission boundary, fail closed, for ENTRY orders only.

Three layers, all in memory (the Postgres twin of the atomic admission is in
`tests/integration/test_d1_entry_admission_postgres.py`):

1. the pure decision and the strict evidence parser (`paper_portfolio_limits`);
2. the real `SubmitAuthorizedPaperOrderHandler` driven through its dispatch path, including a
   re-check that happens INSIDE `before_send` after the pre-claim check passed;
3. concurrency: real threads, a barrier that proves they overlap, and exactly K of N sent.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as h
from tests.unit import test_m085_paper_execution_handlers as base
from tests.unit._m085_fakes import (
    _NOW,
    FakeAttempts,
    FakeBroker,
    FakeConfigurations,
    FakeIntents,
    FakeKillSwitch,
    FakeMarketData,
    FakeView,
    a_configuration,
    a_portfolio,
    a_portfolio_limits,
    a_provenance,
    an_intent,
    time_bases_for,
)
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.decision_candidate.paper_execution import (
    TERMINAL_PAPER_STATES,
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.paper_portfolio_limits import (
    EntryLedgerRow,
    PortfolioEvidence,
    PortfolioEvidenceError,
    PortfolioPosition,
    PortfolioWorkingBuy,
    decode_admission_detail,
    encode_admission_detail,
    ledger_counts_order,
    ledger_order_in_flight,
    portfolio_limit_refusal,
    read_portfolio_evidence,
    trading_day_bounds,
)
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    PaperExecutionRefusedError,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)


@pytest.fixture(autouse=True)
def operation_clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(_NOW) as clock:
        yield clock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    attempt_id: str = "ATT-X",
    *,
    state: str = "FILLED",
    admitted: bool = True,
    failure_code: str | None = None,
    symbol: str | None = "MSFT",
    notional: Decimal | None = Decimal("100"),
    client_order_id: str | None = None,
) -> EntryLedgerRow:
    return EntryLedgerRow(
        attempt_id=attempt_id,
        client_order_id=client_order_id or f"coid-{attempt_id}",
        state=state,
        failure_code=failure_code,
        admitted=admitted,
        symbol=symbol if admitted else None,
        notional=notional if admitted else None,
    )


def _refusal(**overrides: object) -> str | None:
    arguments: dict[str, Any] = {
        "limits": a_portfolio_limits(),
        "portfolio": a_portfolio(),
        "ledger": (),
        "attempt_id": "ATT-NEW",
        "client_order_id": "coid-new",
        "symbol": "AAPL",
        "order_notional": Decimal("4"),
    }
    arguments.update(overrides)
    return portfolio_limit_refusal(**arguments)


def _world_with(**configuration_overrides: object) -> dict[str, Any]:
    return h._world(configurations=FakeConfigurations(a_configuration(**configuration_overrides)))


def _held(symbol: str, quantity: str = "10", market_value: str = "100") -> FakeView:
    return FakeView(symbol=symbol, quantity=quantity, market_value=market_value)


def _prior_attempt(
    world: dict[str, Any],
    number: int,
    *,
    state: PaperExecutionState = PaperExecutionState.FILLED,
    admitted: bool = True,
    failure_code: str | None = None,
    symbol: str = "MSFT",
    notional: Decimal = Decimal("100"),
) -> None:
    attempts: FakeAttempts = world["attempts"]
    attempt_id = f"ATT-PRIOR-{number}"
    attempts.rows[attempt_id] = ExecutionAttempt(
        attempt_id=attempt_id,
        intent_governance_id=f"INT-PRIOR-{number}",
        authorization_id=f"AUT-PRIOR-{number}",
        client_order_id=f"coid-prior-{number}",
        request_fingerprint="f" * 64,
        state=state,
        claimed_at=_NOW - timedelta(minutes=5),
        submitted_at=None,
        acknowledged_at=None,
        terminal_at=_NOW if state in TERMINAL_PAPER_STATES else None,
        broker_order_id=None,
        broker_status=None,
        filled_quantity=None,
        filled_avg_price=None,
        failure_code=failure_code,
        failure_detail=None,
    )
    if admitted:
        attempts.admissions[attempt_id] = (symbol, notional, f"coid-prior-{number}")


# ---------------------------------------------------------------------------
# 1. The pure decision
# ---------------------------------------------------------------------------


class TestThePureDecision:
    def test_a_flat_account_inside_every_limit_passes(self) -> None:
        assert _refusal() is None

    def test_daily_loss_at_the_limit_refuses_and_just_inside_passes(self) -> None:
        limits = a_portfolio_limits(maximum_daily_loss=Decimal("500"))
        at_limit = a_portfolio(equity=Decimal("99500"))
        inside = a_portfolio(equity=Decimal("99500.01"))
        message = _refusal(limits=limits, portfolio=at_limit)
        assert message is not None and "daily loss limit reached" in message
        assert "500" in message
        assert _refusal(limits=limits, portfolio=inside) is None

    def test_a_gain_is_never_a_loss(self) -> None:
        assert _refusal(portfolio=a_portfolio(equity=Decimal("150000"))) is None

    def test_order_count_includes_the_order_being_sent(self) -> None:
        limits = a_portfolio_limits(maximum_daily_order_count=2)
        one_before = (_row("A"),)
        two_before = (_row("A"), _row("B"))
        assert _refusal(limits=limits, ledger=one_before) is None  # this is the 2nd of 2
        message = _refusal(limits=limits, ledger=two_before)  # this would be the 3rd
        assert message is not None and "daily order count limit reached" in message
        assert "3 orders" in message and "maximum_daily_order_count 2" in message

    def test_the_attempts_own_ledger_row_is_not_double_counted(self) -> None:
        limits = a_portfolio_limits(maximum_daily_order_count=1)
        assert _refusal(limits=limits, ledger=(_row("ATT-NEW"),)) is None

    def test_an_attempt_closed_not_sent_does_not_count(self) -> None:
        limits = a_portfolio_limits(maximum_daily_order_count=1)
        closed = _row("A", state="REJECTED", failure_code="NOT_SENT")
        assert not ledger_counts_order(closed)
        assert _refusal(limits=limits, ledger=(closed,)) is None

    def test_a_broker_rejected_attempt_still_counts_and_so_does_an_unknown_one(self) -> None:
        limits = a_portfolio_limits(maximum_daily_order_count=1)
        for state, code in (("REJECTED", "HTTP_422"), ("SUBMISSION_UNKNOWN", None)):
            row = _row("A", state=state, failure_code=code)
            assert ledger_counts_order(row)
            assert _refusal(limits=limits, ledger=(row,)) is not None

    def test_a_claimed_but_unadmitted_concurrent_attempt_does_not_count(self) -> None:
        # Otherwise N simultaneous submissions would each count the other N-1 and ALL refuse.
        limits = a_portfolio_limits(maximum_daily_order_count=1)
        racing = _row("A", state="SUBMISSION_IN_PROGRESS", admitted=False)
        assert not ledger_counts_order(racing)
        assert _refusal(limits=limits, ledger=(racing,)) is None

    def test_a_legacy_unmarked_attempt_that_reached_the_broker_counts(self) -> None:
        limits = a_portfolio_limits(maximum_daily_order_count=1)
        legacy = _row("A", state="FILLED", admitted=False)
        assert ledger_counts_order(legacy)
        assert _refusal(limits=limits, ledger=(legacy,)) is not None

    def test_position_count_is_held_plus_working_buy_symbols_plus_this_one(self) -> None:
        limits = a_portfolio_limits(maximum_simultaneous_positions=3)
        two_held = a_portfolio(
            positions=(
                PortfolioPosition("MSFT", Decimal("1"), Decimal("10")),
                PortfolioPosition("NVDA", Decimal("1"), Decimal("10")),
            )
        )
        assert _refusal(limits=limits, portfolio=two_held) is None  # 2 + AAPL == 3
        working = a_portfolio(
            positions=two_held.positions,
            working_buys=(PortfolioWorkingBuy("w1", "TSLA", Decimal("10")),),
        )
        message = _refusal(limits=limits, portfolio=working)  # 2 + 1 working + AAPL == 4
        assert message is not None and "simultaneous position limit reached" in message
        assert "maximum_simultaneous_positions 3" in message

    def test_the_symbol_being_entered_is_not_counted_twice(self) -> None:
        limits = a_portfolio_limits(maximum_simultaneous_positions=1)
        already = a_portfolio(working_buys=(PortfolioWorkingBuy("w1", "AAPL", Decimal("4")),))
        assert _refusal(limits=limits, portfolio=already) is None

    def test_a_zero_quantity_position_is_not_a_position(self) -> None:
        limits = a_portfolio_limits(maximum_simultaneous_positions=1)
        flat = a_portfolio(positions=(PortfolioPosition("MSFT", Decimal("0"), Decimal("0")),))
        assert _refusal(limits=limits, portfolio=flat) is None

    def test_an_admitted_in_flight_order_counts_until_the_broker_shows_it(self) -> None:
        limits = a_portfolio_limits(maximum_simultaneous_positions=1)
        in_flight = _row("A", state="SUBMISSION_IN_PROGRESS", symbol="MSFT")
        assert ledger_order_in_flight(in_flight)
        message = _refusal(limits=limits, ledger=(in_flight,))
        assert message is not None and "simultaneous position limit reached" in message
        # Once the broker lists that very order it is counted from the broker, once.
        visible = a_portfolio(working_buys=(PortfolioWorkingBuy("coid-A", "MSFT", Decimal("100")),))
        refused = _refusal(limits=limits, ledger=(in_flight,), portfolio=visible)
        assert refused is not None  # still one position (MSFT) plus AAPL > 1

    def test_exposure_sums_positions_working_buys_in_flight_and_this_order(self) -> None:
        limits = a_portfolio_limits(maximum_deployable_capital=Decimal("100"))
        held = a_portfolio(positions=(PortfolioPosition("MSFT", Decimal("1"), Decimal("-60")),))
        # |-60| (a short counts by magnitude) + 4 == 64 <= 100
        assert _refusal(limits=limits, portfolio=held) is None
        busy = a_portfolio(
            positions=held.positions,
            working_buys=(PortfolioWorkingBuy("w", "NVDA", Decimal("30")),),
        )
        in_flight = _row("A", state="SUBMISSION_IN_PROGRESS", symbol="TSLA", notional=Decimal("5"))
        assert _refusal(limits=limits, portfolio=busy, ledger=(in_flight,)) is None  # 99 <= 100
        in_flight_more = _row(
            "A", state="SUBMISSION_IN_PROGRESS", symbol="TSLA", notional=Decimal("6.01")
        )
        message = _refusal(limits=limits, portfolio=busy, ledger=(in_flight_more,))
        assert message is not None and "total exposure limit reached" in message
        assert "maximum_deployable_capital 100" in message

    def test_missing_evidence_refuses_rather_than_passing(self) -> None:
        for field in ("limits", "portfolio", "ledger"):
            message = _refusal(**{field: None})
            assert message is not None and "missing" in message

    def test_the_admission_detail_round_trips_and_garbage_is_refused(self) -> None:
        detail = encode_admission_detail(
            symbol="AAPL", notional=Decimal("4.00"), client_order_id="coid-1"
        )
        assert decode_admission_detail(detail) == ("AAPL", Decimal("4.00"), "coid-1")
        for garbage in (
            "",
            "symbol=AAPL",
            "symbol=;notional=1;client_order_id=x",
            "symbol=A;notional=abc;client_order_id=x",
            "symbol=A;notional=1;client_order_id=x;extra=1",
        ):
            with pytest.raises(PortfolioEvidenceError):
                decode_admission_detail(garbage)

    def test_the_trading_day_is_the_new_york_calendar_day(self) -> None:
        # 03:30 UTC on 2026-07-02 is still 23:30 on 2026-07-01 in New York (EDT, UTC-4).
        start, end = trading_day_bounds(datetime(2026, 7, 2, 3, 30, tzinfo=UTC))
        assert start == datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
        assert end == datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
        with pytest.raises(ValueError):
            trading_day_bounds(datetime(2026, 7, 2, 3, 30))


class TestTheStrictEvidenceParser:
    ACCOUNT = {"equity": "100000", "last_equity": "100000"}

    def _read(
        self, account: object = None, positions: tuple = (), orders: tuple = ()
    ) -> PortfolioEvidence:
        return read_portfolio_evidence(
            account_payload=self.ACCOUNT if account is None else account,
            positions=positions,
            open_orders=orders,
        )

    def test_a_well_formed_account_parses(self) -> None:
        evidence = self._read(
            {"equity": "99000.50", "last_equity": "100000"},
            positions=(_held("MSFT", "2", "-250.5"),),
            orders=(
                FakeView(
                    symbol="NVDA",
                    side="buy",
                    quantity="10",
                    filled_quantity="4",
                    limit_price="5.00",
                    client_order_id="w1",
                ),
                FakeView(symbol="NVDA", side="sell", client_order_id="w2"),
            ),
        )
        assert evidence.daily_pnl == Decimal("-999.50")
        assert evidence.positions[0].market_value == Decimal("-250.5")
        (working,) = evidence.working_buys  # the SELL is risk-reducing and ignored
        assert working.notional == Decimal("30.00")  # (10 - 4 filled) * 5.00

    @pytest.mark.parametrize(
        "account",
        [
            None,
            "not a dict",
            {"equity": "100000"},  # last_equity absent
            {"equity": "100000", "last_equity": None},
            {"equity": "100000", "last_equity": "garbage"},
            {"equity": "100000", "last_equity": "NaN"},
            {"equity": "100000", "last_equity": "-1"},
            {"equity": "100000", "last_equity": True},
            {"equity": None, "last_equity": "100000"},
            {"equity": "Infinity", "last_equity": "100000"},
        ],
    )
    def test_a_missing_or_garbled_account_refuses(self, account: object) -> None:
        with pytest.raises(PortfolioEvidenceError):
            read_portfolio_evidence(
                account_payload=account if account is not None else None,
                positions=(),
                open_orders=(),
            )

    @pytest.mark.parametrize(
        "view",
        [
            FakeView(symbol="", quantity="1", market_value="1"),
            FakeView(symbol="X", quantity=None, market_value="1"),
            FakeView(symbol="X", quantity="1", market_value=None),
            FakeView(symbol="X", quantity="1", market_value="oops"),
            FakeView(symbol="X", quantity="1", market_value="NaN"),
        ],
    )
    def test_a_garbled_position_refuses(self, view: FakeView) -> None:
        with pytest.raises(PortfolioEvidenceError):
            self._read(positions=(view,))

    def test_a_duplicate_position_refuses(self) -> None:
        with pytest.raises(PortfolioEvidenceError, match="twice"):
            self._read(positions=(_held("X"), _held("X")))

    @pytest.mark.parametrize(
        "fields",
        [
            {"limit_price": None},  # exposure cannot be bounded
            {"quantity": None},
            {"quantity": "0"},
            {"filled_quantity": "99"},  # filled more than ordered
            {"side": "sideways"},
            {"side": None},
            {"client_order_id": ""},
            {"symbol": None},
        ],
    )
    def test_a_garbled_working_buy_refuses(self, fields: dict[str, object]) -> None:
        defaults: dict[str, object] = {
            "symbol": "X",
            "side": "buy",
            "quantity": "1",
            "limit_price": "4.00",
            "client_order_id": "w",
        }
        order = FakeView(**{**defaults, **fields})
        with pytest.raises(PortfolioEvidenceError):
            self._read(orders=(order,))


# ---------------------------------------------------------------------------
# 2. The real handler: each limit refuses at the boundary
# ---------------------------------------------------------------------------


class TestEachLimitRefusesAtTheSubmissionBoundary:
    def _refused(self, world: dict[str, Any], match: str) -> None:
        with pytest.raises(PaperExecutionRefusedError, match=match):
            h._submit(world)
        assert world["broker"].submitted == []

    def test_a_clean_account_still_dispatches(self) -> None:
        world = h._world()
        h._authorize(world)
        result = h._submit(world)
        assert result.dispatched is True
        assert len(world["broker"].submitted) == 1
        # The admission marker was written for the attempt that actually left.
        assert set(world["attempts"].admissions) == {"ATT-1"}

    def test_daily_loss_refuses(self) -> None:
        world = _world_with(maximum_daily_loss=Decimal("500"))
        h._authorize(world)
        world["broker"].account_overrides = {"equity": "99500", "last_equity": "100000"}
        self._refused(world, "daily loss limit reached")
        assert world["attempts"].rows == {}  # refused before the claim: no authorization spent

    def test_daily_loss_just_inside_the_limit_dispatches(self) -> None:
        world = _world_with(maximum_daily_loss=Decimal("500"))
        h._authorize(world)
        world["broker"].account_overrides = {"equity": "99500.01", "last_equity": "100000"}
        assert h._submit(world).dispatched is True

    def test_daily_order_count_refuses_the_order_that_would_exceed_it(self) -> None:
        world = _world_with(maximum_daily_order_count=2)
        h._authorize(world)
        _prior_attempt(world, 1)
        _prior_attempt(world, 2)
        self._refused(world, "daily order count limit reached: 3 orders today")

    def test_daily_order_count_allows_the_last_permitted_order(self) -> None:
        world = _world_with(maximum_daily_order_count=2)
        h._authorize(world)
        _prior_attempt(world, 1)
        assert h._submit(world).dispatched is True

    def test_orders_from_an_earlier_trading_day_do_not_count(self) -> None:
        world = _world_with(maximum_daily_order_count=1)
        h._authorize(world)
        _prior_attempt(world, 1)
        old = world["attempts"].rows["ATT-PRIOR-1"]
        world["attempts"].rows["ATT-PRIOR-1"] = replace(old, claimed_at=_NOW - timedelta(days=1))
        assert h._submit(world).dispatched is True

    def test_not_sent_and_unadmitted_attempts_do_not_count(self) -> None:
        world = _world_with(maximum_daily_order_count=1)
        h._authorize(world)
        _prior_attempt(
            world, 1, state=PaperExecutionState.REJECTED, failure_code="NOT_SENT", admitted=True
        )
        _prior_attempt(world, 2, state=PaperExecutionState.SUBMISSION_IN_PROGRESS, admitted=False)
        assert h._submit(world).dispatched is True

    def test_simultaneous_positions_refuses_across_symbols_not_just_the_target(self) -> None:
        world = _world_with(maximum_simultaneous_positions=2)
        h._authorize(world)
        world["broker"].portfolio_positions = (_held("MSFT"), _held("NVDA"))
        self._refused(world, "simultaneous position limit reached: 3 symbols")

    def test_a_working_buy_in_another_symbol_counts_as_a_position(self) -> None:
        world = _world_with(maximum_simultaneous_positions=2)
        h._authorize(world)
        world["broker"].portfolio_positions = (_held("MSFT"),)
        world["broker"].all_open_orders = (
            FakeView(
                symbol="NVDA", side="buy", quantity="1", limit_price="9.00", client_order_id="w1"
            ),
        )
        self._refused(world, "simultaneous position limit reached")

    def test_a_portfolio_that_changes_after_the_pre_claim_read_is_still_caught(self) -> None:
        """M100 final review (P1): the read that matters is the one taken INSIDE the day lock.
        The pre-claim read sees an empty account (as if a concurrent entry had not been sent
        yet); by the time the lock is held that other entry is visible, so this one is refused."""
        world = _world_with(maximum_simultaneous_positions=1)
        h._authorize(world)
        broker = world["broker"]
        reads = {"count": 0}

        def positions() -> tuple[object, ...]:
            reads["count"] += 1
            return () if reads["count"] == 1 else (_held("MSFT"),)

        broker.fetch_all_positions = positions
        result = h._submit(world)
        assert result.dispatched is False
        assert result.attempt.failure_code == "NOT_SENT"
        assert "simultaneous position limit reached" in (result.attempt.failure_detail or "")
        assert broker.submitted == []
        assert reads["count"] == 2  # pre-claim read, then the read taken inside the day lock

    def test_one_slot_left_dispatches(self) -> None:
        world = _world_with(maximum_simultaneous_positions=2)
        h._authorize(world)
        world["broker"].portfolio_positions = (_held("MSFT"),)
        assert h._submit(world).dispatched is True

    def test_total_exposure_refuses(self) -> None:
        world = _world_with(
            maximum_deployable_capital=Decimal("100"), minimum_cash_reserve=Decimal("1")
        )
        h._authorize(world)
        # 97 held + the order's USD 4.00 cost ceiling == 101 > 100.
        world["broker"].portfolio_positions = (_held("MSFT", market_value="97"),)
        self._refused(world, "total exposure limit reached: 101")

    def test_total_exposure_counts_working_buy_notional(self) -> None:
        world = _world_with(
            maximum_deployable_capital=Decimal("100"), minimum_cash_reserve=Decimal("1")
        )
        h._authorize(world)
        world["broker"].all_open_orders = (
            FakeView(
                symbol="NVDA",
                side="buy",
                quantity="10",
                limit_price="9.70",
                filled_quantity="0",
                client_order_id="w1",
            ),
        )
        self._refused(world, "total exposure limit reached")

    def test_exposure_exactly_at_the_ceiling_dispatches(self) -> None:
        world = _world_with(
            maximum_deployable_capital=Decimal("100"), minimum_cash_reserve=Decimal("1")
        )
        h._authorize(world)
        world["broker"].portfolio_positions = (_held("MSFT", market_value="96"),)
        assert h._submit(world).dispatched is True


class TestMissingOrGarbledEvidenceRefuses:
    @pytest.mark.parametrize(
        "mutate",
        [
            lambda b: b.account_overrides.update({"last_equity": None}),
            lambda b: b.account_overrides.update({"last_equity": "not-a-number"}),
            lambda b: b.account_overrides.update({"last_equity": 100000}),
            lambda b: setattr(
                b, "portfolio_positions", (FakeView(symbol="X", quantity="1", market_value=None),)
            ),
            lambda b: setattr(
                b, "portfolio_positions", (FakeView(symbol="X", quantity="1", market_value="?"),)
            ),
            lambda b: setattr(
                b,
                "all_open_orders",
                (
                    FakeView(
                        symbol="X", side="buy", quantity="1", limit_price=None, client_order_id="w"
                    ),
                ),
            ),
            lambda b: setattr(b, "portfolio_read_raises", RuntimeError("broker down")),
        ],
        ids=[
            "last_equity-missing",
            "last_equity-garbled",
            "last_equity-not-a-string",
            "position-without-market-value",
            "position-garbled-market-value",
            "working-buy-without-limit",
            "portfolio-read-fails",
        ],
    )
    def test_it_is_a_refusal_never_a_zero(self, mutate: Callable[[FakeBroker], object]) -> None:
        world = h._world()
        h._authorize(world)
        mutate(world["broker"])
        with pytest.raises(PaperExecutionRefusedError, match="portfolio risk evidence"):
            h._submit(world)
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_an_unreadable_admission_record_refuses(self) -> None:
        world = h._world()
        h._authorize(world)
        attempts: FakeAttempts = world["attempts"]

        def broken(**_: object) -> tuple[EntryLedgerRow, ...]:
            raise PortfolioEvidenceError("an entry-admission record is unreadable")

        attempts.entry_ledger = broken  # type: ignore[method-assign]
        with pytest.raises(PortfolioEvidenceError):
            h._submit(world)
        assert world["broker"].submitted == []


class TestTheCheckHappensInsideBeforeSend:
    def test_a_breach_that_appears_after_the_pre_claim_check_is_still_refused(self) -> None:
        world = _world_with(
            maximum_deployable_capital=Decimal("100"), minimum_cash_reserve=Decimal("1")
        )
        h._authorize(world)
        broker: FakeBroker = world["broker"]
        calls = {"n": 0}

        def positions() -> tuple[object, ...]:
            calls["n"] += 1
            # Clean for the pre-claim read, heavily invested by the read inside `before_send`.
            return () if calls["n"] == 1 else (_held("MSFT", market_value="99"),)

        broker.fetch_all_positions = positions  # type: ignore[method-assign]
        result = h._submit(world)
        assert calls["n"] == 2
        assert result.dispatched is False
        assert broker.submitted == []
        attempt = world["attempts"].rows["ATT-1"]  # claimed, then refused at the boundary
        assert attempt.state is PaperExecutionState.REJECTED
        assert attempt.failure_code == "NOT_SENT"
        assert "total exposure limit reached" in (attempt.failure_detail or "")
        assert "ATT-1" not in world["attempts"].admissions

    def test_an_attempt_refused_after_admission_frees_its_slot(self) -> None:
        world = _world_with(maximum_daily_order_count=1)
        h._authorize(world)
        broker: FakeBroker = world["broker"]
        original_clock = broker.fetch_clock
        calls = {"n": 0}

        def clock() -> object:
            calls["n"] += 1
            if calls["n"] == 2:  # inside `before_send`, after the admission step
                world["kill_switch"].engaged = True
            return original_clock()

        broker.fetch_clock = clock  # type: ignore[method-assign]
        # The switch is engaged at the clock read, i.e. BEFORE the admission step: the
        # attempt is refused and must not hold a slot either way.
        result = h._submit(world)
        assert result.dispatched is False and broker.submitted == []
        ledger = world["attempts"].entry_ledger(
            day_start=_NOW - timedelta(days=1), day_end=_NOW + timedelta(days=1)
        )
        assert [ledger_counts_order(row) for row in ledger] == [False]

    def test_the_kill_switch_still_wins_and_is_still_read_first(self) -> None:
        world = _world_with(maximum_daily_loss=Decimal("500"))
        h._authorize(world)
        world["kill_switch"].engaged = True
        world["broker"].account_overrides = {"equity": "1", "last_equity": "100000"}
        with pytest.raises(PaperExecutionRefusedError, match="kill switch"):
            h._submit(world)
        assert world["broker"].submitted == []


# ---------------------------------------------------------------------------
# 3. Concurrency
# ---------------------------------------------------------------------------


class _Race:
    """N independent intents that share ONE account, ONE attempt store and ONE broker."""

    def __init__(self, count: int, *, order_cap: int, **configuration: object) -> None:
        self.count = count
        shared: dict[str, Any] = {
            "configurations": FakeConfigurations(
                a_configuration(maximum_daily_order_count=order_cap, **configuration)
            ),
            "attempts": FakeAttempts(),
            "broker": FakeBroker(),
            "market_data": FakeMarketData(),
            "kill_switch": FakeKillSwitch(),
        }
        self.shared = shared
        self.worlds: list[dict[str, Any]] = []
        for number in range(count):
            intent = an_intent(
                intent_governance_id=f"INT-R{number}",
                idempotency_key=f"IDEM-R{number}",
                proposal_governance_id=f"PRP-R{number}",
                decision_governance_id=f"DEC-R{number}",
            )
            world = h._world(
                intents=FakeIntents(intent),
                time_bases=time_bases_for(a_provenance(intent)),
                **shared,
            )
            self._authorize(world, number)
            self.worlds.append(world)

    @staticmethod
    def _authorize(world: dict[str, Any], number: int) -> None:
        preview = PreviewPaperSubmissionHandler(
            intents=world["intents"],
            configurations=world["configurations"],
            time_bases=world["time_bases"],
            snapshots=world["snapshots"],
            previews=world["previews"],
            events=world["events"],
            broker=world["broker"],
            market_data=world["market_data"],
            kill_switch=world["kill_switch"],
        ).handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id=f"INT-R{number}",
                preview_id=f"PVW-R{number}",
                account_snapshot_id=f"SNP-RP{number}",
                created_at=_NOW,
            )
        )
        assert preview.is_authorizable, preview.refusals
        AuthorizePaperSubmissionHandler(
            previews=world["previews"],
            authorizations=world["authorizations"],
            events=world["events"],
            broker=world["broker"],
        ).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id=f"AUT-R{number}",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
            )
        )

    def overlap_the_threads(self) -> None:
        """Every thread does its pre-claim portfolio read at the SAME time, so all of them
        have passed every read-only check before any admission. (The read inside the day lock
        is serialized by design -- M100 final review -- and is deliberately not synchronized.)"""
        broker: FakeBroker = self.shared["broker"]
        original = broker.fetch_all_positions
        barriers = [threading.Barrier(self.count, timeout=20)]
        local = threading.local()

        def positions() -> tuple[object, ...]:
            index = getattr(local, "reads", 0)
            local.reads = index + 1
            if index < 1:
                barriers[index].wait()
            return original()

        broker.fetch_all_positions = positions  # type: ignore[method-assign]

    def submit(self, number: int) -> Any:  # noqa: ANN401 - PaperSubmissionResult
        world = self.worlds[number]
        return h._handler(world).handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=f"INT-R{number}",
                attempt_id=f"ATT-R{number}",
                account_snapshot_id=f"SNP-RS{number}",
                at=_NOW,
            )
        )


class TestSimultaneousSubmissionsCannotBothPassALimitThatAllowsOne:
    @pytest.mark.parametrize("repetition", range(5))
    def test_n_parallel_submits_against_a_cap_of_k_send_exactly_k(self, repetition: int) -> None:
        del repetition
        count, cap = 8, 3
        race = _Race(count, order_cap=cap)
        race.overlap_the_threads()
        outcomes: list[Any] = [None] * count
        errors: list[BaseException] = []

        def run(number: int) -> None:
            try:
                outcomes[number] = race.submit(number)
            except BaseException as error:  # noqa: BLE001 - asserted on below
                errors.append(error)

        threads = [threading.Thread(target=run, args=(n,)) for n in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert not any(thread.is_alive() for thread in threads)
        # A thread that reaches the PRE-claim check after others were admitted is refused
        # there (an exception, nothing claimed); the rest are refused at the boundary
        # (a NOT_SENT outcome). Either way the limit holds and the reason is the right one.
        for error in errors:
            assert isinstance(error, PaperExecutionRefusedError), error
            assert "daily order count limit reached" in str(error)

        done = [outcome for outcome in outcomes if outcome is not None]
        sent = [outcome for outcome in done if outcome.dispatched]
        refused = [outcome for outcome in done if not outcome.dispatched]
        assert len(sent) == cap
        assert len(race.shared["broker"].submitted) == cap
        assert len(refused) + len(errors) == count - cap
        for outcome in refused:
            assert outcome.attempt.failure_code == "NOT_SENT"
            assert "daily order count limit reached" in (outcome.attempt.failure_detail or "")
        assert len(race.shared["attempts"].admissions) == cap

    def test_an_exposure_ceiling_that_allows_two_admits_exactly_two(self) -> None:
        # All eight orders are for AAPL, so the position limit is not what binds; the
        # exposure ceiling is: each order's USD 4.00 ceiling against a 9.00 deployable cap
        # admits exactly two (8.00), never three. The broker lists an order the moment it is
        # POSTed, as the real one does; the in-flight ledger covers the gap before that.
        count = 8
        race = _Race(
            count,
            order_cap=20,
            maximum_deployable_capital=Decimal("9"),
            maximum_capital_per_trade=Decimal("5"),
            minimum_cash_reserve=Decimal("1"),
        )
        race.overlap_the_threads()
        broker: FakeBroker = race.shared["broker"]

        def working() -> tuple[object, ...]:
            return tuple(
                FakeView(
                    symbol=order.symbol,
                    side="buy",
                    quantity=str(order.quantity),
                    filled_quantity="0",
                    limit_price=str(order.limit_price),
                    client_order_id=order.client_order_id,
                )
                for order in list(broker.submitted)
            )

        broker.fetch_all_open_orders = working  # type: ignore[method-assign]
        outcomes: list[Any] = [None] * count

        def run(number: int) -> None:
            try:
                outcomes[number] = race.submit(number)
            except PaperExecutionRefusedError:
                pass  # refused at the pre-claim check after others were admitted

        threads = [threading.Thread(target=run, args=(n,)) for n in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert sum(1 for outcome in outcomes if outcome is not None and outcome.dispatched) == 2
        assert len(race.shared["broker"].submitted) == 2

    def test_the_in_memory_ledger_serializes_count_and_admit(self) -> None:
        attempts = FakeAttempts()
        limits = a_portfolio_limits(maximum_daily_order_count=4)
        count = 24
        day_start, day_end = trading_day_bounds(_NOW)
        barrier = threading.Barrier(count, timeout=20)
        results: list[str | None] = [None] * count

        for number in range(count):
            _prior_attempt(
                {"attempts": attempts},
                number,
                admitted=False,
                state=PaperExecutionState.SUBMISSION_IN_PROGRESS,
            )

        def run(number: int) -> None:
            attempt_id = f"ATT-PRIOR-{number}"

            def decide(ledger: tuple[EntryLedgerRow, ...]) -> str | None:
                return portfolio_limit_refusal(
                    limits=limits,
                    portfolio=a_portfolio(),
                    ledger=ledger,
                    attempt_id=attempt_id,
                    client_order_id=f"coid-prior-{number}",
                    symbol="AAPL",
                    order_notional=Decimal("4"),
                )

            barrier.wait()
            results[number] = attempts.admit_entry(
                attempt_id=attempt_id,
                day_start=day_start,
                day_end=day_end,
                at=_NOW,
                symbol="AAPL",
                notional=Decimal("4"),
                client_order_id=f"coid-prior-{number}",
                decide=decide,
            )

        threads = [threading.Thread(target=run, args=(n,)) for n in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert results.count(None) == 4  # admitted
        assert len(attempts.admissions) == 4


# ---------------------------------------------------------------------------
# 4. Exits are risk-reducing and are never blocked by entry limits
# ---------------------------------------------------------------------------


def test_an_exit_still_goes_when_every_entry_limit_is_breached(tmp_path: Path) -> None:
    world: World = simulation_world(tmp_path, exits=True)
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal)
    assert world.service.confirm_approval(proposal, view.ticket).sent == "sent"
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    intent = f"INT-{proposal}"
    exits = world.service.exits
    assert exits is not None
    review = exits.review(intent)

    # Breach every entry limit the broker can state, and make any portfolio READ fail loudly:
    # the exit path must neither consult nor be stopped by them.
    real_account = world.broker.fetch_account

    def breached_account() -> tuple[int, dict[str, object]]:
        status, payload = real_account()
        return status, {**payload, "equity": "1", "last_equity": "1000000"}

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("an exit must never read the entry-limit portfolio evidence")

    world.broker.fetch_account = breached_account  # type: ignore[method-assign]
    world.broker.fetch_all_positions = forbidden  # type: ignore[method-assign]
    world.broker.fetch_all_open_orders = forbidden  # type: ignore[method-assign]
    outcome = exits.confirm(intent, review.ticket)
    assert outcome.ok and outcome.sent == "sent"
    assert [o for o in world.store.orders() if o.side == "sell"] != []


def test_the_exit_modules_do_not_import_the_entry_limit_module() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "empirical_platform"
    for relative in ("usecases/position_exit.py", "usecases/position_plan_manager.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "paper_portfolio_limits" not in source, relative


# keep the unused-import linter honest about helpers used only in some parametrizations
_ = (base, PortfolioWorkingBuy, SubmitAuthorizedPaperOrderHandler)
