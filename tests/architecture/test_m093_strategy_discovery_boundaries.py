"""MILESTONE-093 -- the strategy-discovery modules' boundaries. Mirrors
`test_m092_opportunity_engine_v2_boundaries.py`'s own discipline: the broker-write surface is
structurally unreachable, M093 never imports V1/V2's frozen modules, and (specific to this
milestone) the FINAL HOLDOUT range cannot be fetched by any M093 code without the guard
refusing -- proven here both structurally (the one fetch entry point's source calls the guard)
and functionally (calling it for a holdout date raises before any port method runs)."""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.m093_holdout_guard import HoldoutLockedError
from empirical_platform.usecases.m093_research_framework import fetch_session_bars_guarded

ROOT = Path("src/empirical_platform")
HOLDOUT_GUARD = ROOT / "decision_candidate" / "m093_holdout_guard.py"
RESEARCH_FRAMEWORK = ROOT / "usecases" / "m093_research_framework.py"
FAMILY_A = ROOT / "decision_candidate" / "opportunity_family_trend_continuation.py"
FAMILY_B = ROOT / "decision_candidate" / "opportunity_family_vwap_pullback.py"
FAMILY_C = ROOT / "decision_candidate" / "opportunity_family_opening_range.py"
FAMILY_D = ROOT / "decision_candidate" / "opportunity_family_mean_reversion.py"
FAMILY_E = ROOT / "decision_candidate" / "opportunity_family_relative_strength.py"
M093_MODULES = (
    HOLDOUT_GUARD,
    RESEARCH_FRAMEWORK,
    FAMILY_A,
    FAMILY_B,
    FAMILY_C,
    FAMILY_D,
    FAMILY_E,
)

#: Same forbidden dispatch surface every other milestone's boundary test checks.
FORBIDDEN_DISPATCH_SURFACE: tuple[str, ...] = (
    "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperClient",
    "AlpacaPaperClient",
    "submit_order",
    "submit_close_order",
    "cancel_order",
    "empirical_platform.usecases.paper_execution.SubmitAuthorizedPaperOrderHandler",
    "SubmitAuthorizedPaperOrderHandler",
    "IssuePaperBoundOrderIntentHandler",
    "IssueOrderIntentHandler",
    "empirical_platform.usecases.position_exit.SubmitAuthorizedPositionExitHandler",
    "SubmitAuthorizedPositionExitHandler",
)

#: V1/V2's own frozen modules -- M093 must be architecturally independent of both, exactly as
#: V2 was independent of V1.
FROZEN_PREDECESSOR_MODULES: tuple[str, ...] = (
    "empirical_platform.decision_candidate.opportunity_engine",
    "empirical_platform.decision_candidate.opportunity_engine_v2",
    "empirical_platform.usecases.opportunity_engine_replay",
    "empirical_platform.usecases.opportunity_engine_v2_replay",
    "empirical_platform.usecases.opportunity_engine_validation",
    "empirical_platform.usecases.opportunity_engine_v2_validation",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("path", M093_MODULES, ids=[p.name for p in M093_MODULES])
def test_no_m093_module_imports_the_dispatch_surface(path: Path) -> None:
    names = _imports(path)
    source = path.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
        assert forbidden not in source, (path.name, forbidden)


@pytest.mark.parametrize("path", M093_MODULES, ids=[p.name for p in M093_MODULES])
def test_no_m093_module_calls_a_forbidden_dispatch_name_in_code(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for forbidden in ("submit_order(", "submit_close_order(", "cancel_order(", ".submit_order"):
        assert forbidden not in source, (path.name, forbidden)


@pytest.mark.parametrize("path", M093_MODULES, ids=[p.name for p in M093_MODULES])
def test_no_m093_module_imports_v1_or_v2s_frozen_modules(path: Path) -> None:
    names = _imports(path)
    for frozen in FROZEN_PREDECESSOR_MODULES:
        assert not any(name == frozen or name.startswith(f"{frozen}.") for name in names), (
            path.name,
            frozen,
        )


def test_the_one_bar_fetch_entry_point_calls_the_holdout_guard_in_source() -> None:
    """Structural proof: the single M093 data-fetching entry point's source text calls
    `assert_not_holdout` -- not just documents that it does."""
    source = RESEARCH_FRAMEWORK.read_text(encoding="utf-8")
    assert "assert_not_holdout(session_date)" in source
    # And the guard is imported from the dedicated module, not redefined locally.
    names = _imports(RESEARCH_FRAMEWORK)
    assert "empirical_platform.decision_candidate.m093_holdout_guard.assert_not_holdout" in names


def test_the_bar_fetch_entry_point_refuses_a_holdout_date_before_touching_the_port() -> None:
    """Functional proof, not just structural: calling the real fetch entry point for a date
    inside the locked FINAL HOLDOUT range raises `HoldoutLockedError` -- and a stub port whose
    `fetch_minute_bars` would fail the test if ever called proves the guard runs FIRST, before
    any network-shaped call."""

    class _PortThatMustNeverBeCalled:
        @property
        def endpoint_host(self) -> str:
            return "unused.invalid"

        def fetch_minute_bars(
            self, symbol: str, *, start: datetime, end: datetime, limit: int
        ) -> tuple[object, ...]:
            raise AssertionError(
                "fetch_minute_bars was called -- the holdout guard failed to refuse first"
            )

    with pytest.raises(HoldoutLockedError):
        fetch_session_bars_guarded(
            _PortThatMustNeverBeCalled(),  # type: ignore[arg-type]
            "AAPL",
            date(2026, 4, 1),  # inside 2026-03-18 .. 2026-05-12
            session_start=time(13, 30, tzinfo=UTC),
            session_end=time(20, 0, tzinfo=UTC),
            operator_timezone="UTC",
        )


def test_m093_model_ids_are_distinct_from_v1_and_v2s() -> None:
    """Every M093 family's model identity must be textually distinct from V1's/V2's own
    frozen constants -- proves no family silently reuses a predecessor's identity string."""
    predecessor_ids = (
        "BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME",
        "SPREAD_LIQUIDITY_TREND_REWARD_RISK_FRESHNESS_WEIGHTED_SUM",
    )
    for path in (FAMILY_A, FAMILY_B, FAMILY_C, FAMILY_D, FAMILY_E):
        source = path.read_text(encoding="utf-8")
        for predecessor_id in predecessor_ids:
            assert f'"{predecessor_id}"' not in source, (path.name, predecessor_id)
