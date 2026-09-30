"""MILESTONE-092 Phase 18-19 -- the V2 concentration/classification module and the
VALIDATION/FINAL HOLDOUT orchestration script never touch the broker-write surface.

Separate file from `test_m092_opportunity_engine_v2_boundaries.py` (which covers the V2
domain/replay modules the research stage built) -- this one covers the concentration/
classification module and orchestration script this stage added.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
V2_VALIDATION = ROOT / "usecases" / "opportunity_engine_v2_validation.py"
VALIDATE_HOLDOUT_CLI = Path("tools") / "m092_validate_holdout.py"
MODULES = (V2_VALIDATION, VALIDATE_HOLDOUT_CLI)

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


@pytest.mark.parametrize("path", MODULES, ids=[p.name for p in MODULES])
def test_no_module_imports_the_dispatch_surface(path: Path) -> None:
    names = _imports(path)
    source = path.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
        assert forbidden not in source, (path.name, forbidden)


def test_v2_validation_module_never_imports_a_broker_client_at_all() -> None:
    """`opportunity_engine_v2_validation.py` is pure post-hoc math over already-computed
    records -- it should never need to import the broker adapter module at all, not merely
    avoid the specific write methods."""
    names = _imports(V2_VALIDATION)
    assert not any("alpaca_paper" in name for name in names)


def test_the_orchestration_script_only_reads_market_data_never_writes_an_order() -> None:
    """The one module in this pair that DOES legitimately import the broker adapter (for
    read-only historical bars) -- proven here to use only the read-only market-data client,
    never the order-capable trading client's write methods."""
    source = VALIDATE_HOLDOUT_CLI.read_text(encoding="utf-8")
    assert "AlpacaPaperMarketDataClient" in source
    assert "AlpacaPaperClient(" not in source
    for forbidden in ("submit_order(", "cancel_order(", "submit_close_order("):
        assert forbidden not in source
