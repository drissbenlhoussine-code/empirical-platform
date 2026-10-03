from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans
from tests.unit.test_ibkr_market_access import NOW, Broker, Journal, plan, service
from tests.unit.test_v1_position_plan_manager import _manager

from empirical_platform.decision_candidate.market_access_ports import MarketHistoryEntry
from empirical_platform.decision_candidate.market_plan import read_market_plan
from empirical_platform.entrypoints._market_console_routes import register_market_routes
from empirical_platform.entrypoints._operator_console_web import Request, Router, SecuritySession
from empirical_platform.usecases.market_console import MarketReviewService


class ReviewJournal(Journal):
    def history(self) -> tuple[MarketHistoryEntry, ...]:
        return (MarketHistoryEntry(self.plan, "CLOSED", Decimal("4"), NOW),)


def test_one_console_renders_exact_review_and_currency_labeled_history() -> None:
    router = Router(SecuritySession())
    register_market_routes(router, MarketReviewService(ReviewJournal()))  # type: ignore[arg-type]
    request = Request("GET", "/markets/review", {"plan": [plan().plan_id]}, {}, {}, {})
    body = router._routes[("GET", "/markets/review")](request, "").body.decode()
    assert plan().fingerprint in body and "SELL_TO_CLOSE" in body
    assert "new explicit approval" in body and "<form" not in body
    body = router._routes[("GET", "/markets/history")](request, "").body.decode()
    assert "IBKR_PAPER" in body and "XHEL" in body and "EUR" in body
    assert "CLOSED" in body and "before fees" in body
    request = replace(request, query={"plan": ["not-a-plan"]})
    assert router._routes[("GET", "/markets/review")](request, "").status == "409 Conflict"


def test_same_plan_manager_tick_delegates_only_approved_exit_cycle(tmp_path: Path) -> None:
    world = simulation_world(tmp_path, exits=True)
    manager = _manager(world, FakeApprovedPlans())
    calls = []

    class Cycle:
        def manage_exits_once(self, *, now: datetime) -> tuple[str, ...]:
            calls.append(now)
            return ("MARKET-PLAN:MONITORING", "UNKNOWN-PLAN:NEEDS_ATTENTION")

    manager._market_exit_cycles = (Cycle(),)
    result = manager.evaluate_once(now=NOW)
    assert calls == [NOW] and len(result) == 2
    assert result[-1].kind.value == "NEEDS_ATTENTION"


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("time_in_force", "GTC"),
        ("extended_hours", True),
        ("risk", None),
        ("configuration_fingerprint", "bad"),
        ("configuration_version", 0),
        ("target", "NaN"),
        ("maximum_notional", 500),
        ("estimated_total_cash_required", "0"),
        ("created_at", "2026-10-02T10:00:00"),
    ],
)
def test_persisted_plan_mutations_cannot_be_coerced(field: str, value: object) -> None:
    document = plan().document()
    document[field] = value
    with pytest.raises((ValueError, TypeError)):
        read_market_plan(document)


def test_original_market_evidence_expiry_is_not_replaced_with_a_new_quote() -> None:
    journal, broker = Journal(), Broker()
    broker.before = lambda: setattr(broker, "at", NOW + timedelta(seconds=61))
    with pytest.raises(ValueError, match="stale"):
        service(journal, broker).submit_entry(journal.plan.plan_id)
    assert not broker.sent
