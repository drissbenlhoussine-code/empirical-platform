"""MILESTONE-090 -- the Opportunity Engine's boundaries, parsed from its source.

THE APPROVAL BOUNDARY IS STRUCTURAL (Phase 17-18). No module of this milestone imports a
broker order-submission method or an M085 dispatch handler: `ApproveOpportunityHandler`
durably records OWNER_APPROVED and returns the approved plan, and that is where this
milestone's capability ends. `IntradayBarsPort` is read-only by construction (one method,
no order-shaped argument); `tools/check_architecture.py`'s own `ORDER_SUBMISSION_PREFIXES`
already forbids every module of this package from importing a real broker SDK, but this file
additionally proves the M090 modules specifically never reach for the IN-REPOSITORY dispatch
surface either (`submit_order`, `submit_close_order`, the M085 issue/dispatch handlers).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
DOMAIN = ROOT / "decision_candidate" / "opportunity_engine.py"
PORTS = ROOT / "decision_candidate" / "opportunity_engine_repositories.py"
USECASES = ROOT / "usecases" / "opportunity_engine.py"
M090_MODULES = (DOMAIN, PORTS, USECASES)

#: Everything that could submit, modify or cancel a real or simulated order, or bind an
#: approved plan into the M085/M087/M089 dispatch pipeline. Grepped for as plain substrings
#: of the fully-qualified import path, not just the top-level module, so a `from x import
#: submit_order` is caught exactly the same as `import x.submit_order`.
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


@pytest.mark.parametrize("path", M090_MODULES, ids=[p.name for p in M090_MODULES])
def test_no_m090_module_imports_the_dispatch_surface(path: Path) -> None:
    names = _imports(path)
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)


@pytest.mark.parametrize("path", M090_MODULES, ids=[p.name for p in M090_MODULES])
def test_no_m090_module_calls_a_forbidden_dispatch_name_in_code(path: Path) -> None:
    """A stricter, source-text check: even a dynamically-imported or locally-defined call to
    one of these exact names cannot appear in the executable body of any M090 module."""
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


def test_intraday_bars_port_is_read_only() -> None:
    """One method, no order-shaped argument or return value exists to accept or express one."""
    source = PORTS.read_text(encoding="utf-8")
    port_source = source.split("class IntradayBarsPort")[1].split("class OpportunityRepository")[0]
    # Exactly one property (`endpoint_host`) and exactly one real method (`fetch_minute_bars`)
    # -- nothing else is declared on this port.
    assert port_source.count("def ") == 2
    assert port_source.count("@property") == 1
    assert "def fetch_minute_bars(" in port_source
    # Check each DEFINITION LINE itself (the actual capability surface), never the
    # class/method docstring prose explaining what is deliberately absent -- that prose
    # legitimately names the very words being checked for here.
    definition_lines = [
        line
        for line in port_source.splitlines()
        if line.strip().startswith(("def ", "@property", "@"))
    ]
    for forbidden in ("submit", "cancel", "place_order", "modify"):
        assert not any(forbidden in line.lower() for line in definition_lines)


def test_the_alpaca_bars_capability_added_this_milestone_is_narrow() -> None:
    """`fetch_minute_bars` is the ONE new method AlpacaPaperMarketDataClient gained; it takes
    no order-shaped argument."""
    path = ROOT / "shared" / "brokerage" / "alpaca_paper.py"
    source = path.read_text(encoding="utf-8")
    assert source.count("def fetch_minute_bars(") == 1
    signature = (
        "def fetch_minute_bars(\n        self, symbol: str, *, start: datetime, end: datetime"
    )
    assert signature in source


def test_approve_handler_is_the_terminal_capability_and_it_only_records_a_decision() -> None:
    """`ApproveOpportunityHandler.handle` calls exactly the two durable-write repository
    methods it needs (`transition`, `save` on the decision repository) and nothing broker-
    shaped -- the boundary the module docstring claims, checked in code, not just prose."""
    source = USECASES.read_text(encoding="utf-8")
    handler_source = source.split("class ApproveOpportunityHandler")[1]
    assert "self._opportunities.transition(" in handler_source
    assert "self._decisions.save(" in handler_source
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert forbidden not in handler_source


def test_m090_persistence_repositories_module_also_avoids_the_dispatch_surface() -> None:
    """Once the Postgres implementation exists, it must be equally clean -- checked here so a
    later addition to that file is covered by the same guard without a separate test file."""
    path = (
        ROOT
        / "shared"
        / "persistence"
        / "postgres_repositories"
        / "opportunity_engine_repositories.py"
    )
    if not path.exists():
        pytest.skip("Postgres persistence for M090 has not been added yet")
    names = _imports(path)
    for forbidden in FORBIDDEN_DISPATCH_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
