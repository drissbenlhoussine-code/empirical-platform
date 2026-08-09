"""No-future-data structural audit for MILESTONE-060."""

from __future__ import annotations

import inspect

from empirical_platform.decision_candidate.position_plan import build_position_plan
from empirical_platform.usecases.build_position_plan import BuildPositionPlanHandler


def test_build_position_plan_accepts_no_market_bars_or_wall_clock() -> None:
    signature = inspect.signature(build_position_plan)
    assert tuple(signature.parameters) == ("identity", "trade_plan", "sizing_context", "policy")
    forbidden = {"bar", "bars", "window", "observation", "market", "price_refresh", "now"}
    assert not forbidden.intersection({name.lower() for name in signature.parameters})


def test_build_position_plan_handler_imports_no_market_data_or_live_quote_dependency() -> None:
    source = inspect.getsource(BuildPositionPlanHandler)
    forbidden = (
        "Bar",
        "ObservationWindow",
        "current_quote",
        "quote_lookup",
        "refresh_price",
        "trading_opportunity_scan_repository",
        "decision_candidate_repository",
    )
    for token in forbidden:
        assert token not in source
