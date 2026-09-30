"""MILESTONE-091 -- the validation layer's boundaries, parsed from its source.

Mirrors `test_m090_opportunity_engine_boundaries.py`'s own discipline: the validation
module consumes already-computed `ReplayDecision`/`ReplaySessionResult` objects and never
imports a broker client, an order type, or a dispatch handler. It performs no I/O of its
own -- `tools/m091_validation.py` is the ONLY place real network calls happen, and it too
must never import the write-capable surface.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
VALIDATION = ROOT / "usecases" / "opportunity_engine_validation.py"
CLI = Path("tools") / "m091_validation.py"
M091_MODULES = (VALIDATION, CLI)

#: Same forbidden surface `test_m090_opportunity_engine_boundaries.py` checks -- reused
#: verbatim so a change to the real dispatch surface only needs updating in one place's
#: spirit, even though this is a separate list (architecture tests intentionally do not
#: import from each other, so each stays independently readable and independently correct).
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


@pytest.mark.parametrize("path", M091_MODULES, ids=[p.name for p in M091_MODULES])
def test_no_m091_module_imports_the_dispatch_surface(path: Path) -> None:
    names = _imports(path)
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)


@pytest.mark.parametrize("path", M091_MODULES, ids=[p.name for p in M091_MODULES])
def test_no_m091_module_calls_a_forbidden_dispatch_name_in_code(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    forbidden_calls = (
        "submit_order(",
        "submit_close_order(",
        "cancel_order(",
        ".submit_order",
        ".cancel_order",
    )
    for forbidden in forbidden_calls:
        assert forbidden not in source, (path.name, forbidden)


def test_the_validation_module_never_imports_the_frozen_domain_gates_directly() -> None:
    """`opportunity_engine_validation.py` consumes `ReplayDecision`/`ReplaySessionResult`
    ONLY -- it never reaches into `decision_candidate.opportunity_engine`'s own gate
    functions, proving it cannot silently re-implement or loosen a gate the frozen replay
    already applied."""
    names = _imports(VALIDATION)
    assert not any(
        name.startswith("empirical_platform.decision_candidate.opportunity_engine")
        for name in names
    )


def test_the_validation_module_only_reads_replay_output_types() -> None:
    source = VALIDATION.read_text(encoding="utf-8")
    assert "from empirical_platform.usecases.opportunity_engine_replay import" in source
    assert "ReplayDecision" in source
    assert "ReplaySessionResult" in source
