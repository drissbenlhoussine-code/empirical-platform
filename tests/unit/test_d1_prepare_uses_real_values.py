"""FIX D1 -- the Prepare path judges the daily limits on REAL numbers, not hardcoded zeros.

`prepare_v1_paper_candidate` used to hand `evaluate_trade_proposal` an account snapshot with
`realized_pnl_today=0`, `orders_submitted_today=0` and a position list that only saw the
target symbol, so the daily-loss, daily-order-count and position-count checks always passed.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from tests.unit._m085_fakes import (
    FakeAttempts,
    FakeBroker,
    FakeMarketData,
    FakeTimeBases,
    FakeView,
)
from tests.unit._m086_fakes import MemoryWatermarks
from tests.unit.test_v1_paper_candidate_preparation import (
    _LiveQuote,
    _now,
    _open_broker,
    _repositories,
    _v1_configuration,
)

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource
from empirical_platform.usecases.paper_operator_console import (
    V1PaperCandidateRefusedError,
    V1PreparedCandidate,
    prepare_v1_paper_candidate,
)


def _prepare(
    *, broker: FakeBroker | None = None, attempts: FakeAttempts | None = None, **cfg: object
) -> V1PreparedCandidate:
    configurations, contexts, proposals = _repositories(_v1_configuration(**cfg))
    market_data = FakeMarketData(quote=_LiveQuote())
    return prepare_v1_paper_candidate(
        configurations=configurations,
        contexts=contexts,
        proposals=proposals,
        watermarks=MemoryWatermarks(),
        time_bases=FakeTimeBases(),
        broker=broker or _open_broker(),  # type: ignore[arg-type]
        market_data=market_data,
        bars=market_data,
        attempts=attempts or FakeAttempts(),
        time_source=SystemPaperTimeSource(),
        now=_now(),
    )


def _counted_attempt_today(attempts: FakeAttempts, number: int) -> None:
    attempt_id = f"ATT-TODAY-{number}"
    attempts.rows[attempt_id] = ExecutionAttempt(
        attempt_id=attempt_id,
        intent_governance_id=f"INT-TODAY-{number}",
        authorization_id=f"AUT-TODAY-{number}",
        client_order_id=f"coid-today-{number}",
        request_fingerprint="f" * 64,
        state=PaperExecutionState.PAPER_ACCEPTED,
        claimed_at=_now() - timedelta(seconds=30),
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


def test_a_flat_break_even_account_with_no_orders_today_still_prepares() -> None:
    assert _prepare().proposal.symbol == "AAPL"


def test_the_real_daily_loss_refuses_the_candidate() -> None:
    broker = _open_broker()
    broker.account_overrides = {"equity": "99000", "last_equity": "100000"}
    with pytest.raises(V1PaperCandidateRefusedError, match="DAILY_LOSS_LIMIT_REACHED"):
        _prepare(broker=broker, maximum_daily_loss=Decimal("500"))


def test_a_gain_does_not_refuse() -> None:
    broker = _open_broker()
    broker.account_overrides = {"equity": "101000", "last_equity": "100000"}
    assert _prepare(broker=broker, maximum_daily_loss=Decimal("500")).proposal is not None


def test_the_durable_order_count_for_today_refuses_the_candidate() -> None:
    attempts = FakeAttempts()
    _counted_attempt_today(attempts, 1)
    with pytest.raises(V1PaperCandidateRefusedError, match="DAILY_ORDER_LIMIT_REACHED"):
        _prepare(attempts=attempts)  # the fixture configuration allows 1 order a day


def test_positions_in_other_symbols_count_toward_the_position_limit() -> None:
    broker = _open_broker()
    broker.portfolio_positions = (FakeView(symbol="MSFT", quantity="2", market_value="800"),)
    with pytest.raises(V1PaperCandidateRefusedError, match="POSITION_LIMIT_REACHED"):
        _prepare(broker=broker)  # the fixture configuration allows 1 position


@pytest.mark.parametrize("last_equity", [None, "garbage"])
def test_garbled_account_evidence_refuses_instead_of_defaulting_to_zero(
    last_equity: str | None,
) -> None:
    broker = _open_broker()
    broker.account_overrides = {"last_equity": last_equity}
    with pytest.raises(V1PaperCandidateRefusedError, match="could not be established"):
        _prepare(broker=broker)


def test_an_unreadable_position_listing_refuses() -> None:
    broker = _open_broker()
    broker.portfolio_read_raises = RuntimeError("positions endpoint down")
    with pytest.raises(RuntimeError, match="positions endpoint down"):
        _prepare(broker=broker)
