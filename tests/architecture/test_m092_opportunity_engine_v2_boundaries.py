"""MILESTONE-092 -- the V2 research modules' boundaries. Mirrors
`test_m090_opportunity_engine_boundaries.py`'s own discipline exactly: the approval/dispatch
boundary is structural, never just documented, and V2 never touches V1's own frozen files.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
V2_DOMAIN = ROOT / "decision_candidate" / "opportunity_engine_v2.py"
V2_REPLAY = ROOT / "usecases" / "opportunity_engine_v2_replay.py"
V2_MODULES = (V2_DOMAIN, V2_REPLAY)

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


@pytest.mark.parametrize("path", V2_MODULES, ids=[p.name for p in V2_MODULES])
def test_no_v2_module_imports_the_dispatch_surface(path: Path) -> None:
    names = _imports(path)
    source = path.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
        assert forbidden not in source, (path.name, forbidden)


@pytest.mark.parametrize("path", V2_MODULES, ids=[p.name for p in V2_MODULES])
def test_no_v2_module_calls_a_forbidden_dispatch_name_in_code(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for forbidden in ("submit_order(", "submit_close_order(", "cancel_order(", ".submit_order"):
        assert forbidden not in source, (path.name, forbidden)


def test_v2_domain_never_imports_v1s_frozen_opportunity_engine_module() -> None:
    """V1 is immutable historical evidence (Phase 2): V2's OWN domain module must never
    import `decision_candidate.opportunity_engine` (V1's module) -- not even to reuse a
    constant, since that would create a coupling that could let a future V1 change silently
    ripple into V2. Every V2 building block V2 needs is defined fresh in
    `opportunity_engine_v2.py` itself."""
    names = _imports(V2_DOMAIN)
    assert not any(
        name == "empirical_platform.decision_candidate.opportunity_engine"
        or name.startswith("empirical_platform.decision_candidate.opportunity_engine.")
        for name in names
    )


def test_v2_replay_never_imports_v1s_frozen_replay_module() -> None:
    """Same independence requirement for the usecases layer: V2's replay harness never
    imports `usecases.opportunity_engine_replay` (V1's replay module)."""
    names = _imports(V2_REPLAY)
    assert not any(
        name == "empirical_platform.usecases.opportunity_engine_replay"
        or name.startswith("empirical_platform.usecases.opportunity_engine_replay.")
        for name in names
    )


def test_v2_model_ids_are_distinct_from_v1s() -> None:
    """Every V2 model identity must be textually distinct from V1's own frozen constants --
    proves V2 never silently reuses a V1 identity string."""
    source = V2_DOMAIN.read_text(encoding="utf-8")
    v1_ids = (
        "BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME",
        "SPREAD_LIQUIDITY_TREND_REWARD_RISK_FRESHNESS_WEIGHTED_SUM",
    )
    for v1_id in v1_ids:
        # The V1 id may appear only as a substring of a distinct V2 id (e.g. with a _V2
        # suffix), never as an exact standalone string literal.
        assert f'"{v1_id}"' not in source, (v1_id, "V2 must never reuse a V1 model id exactly")
