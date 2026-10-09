"""RELEASE v1 -- the automatic position-plan manager can never BUY, short, widen a stop/
target, increase quantity, or reach a Live client. Static/import-based checks, mirroring
`test_m089_paper_exit_boundaries.py`'s own style: these are claims about the SOURCE, not
just about what today's tests happen to exercise.
"""

from __future__ import annotations

import ast
from pathlib import Path

MANAGER = Path("src/empirical_platform/usecases/position_plan_manager.py")
PLAN_DOMAIN = Path("src/empirical_platform/decision_candidate/approved_plan.py")
PLAN_REPOS = Path("src/empirical_platform/decision_candidate/approved_plan_repositories.py")
V1_MODULES = (MANAGER, PLAN_DOMAIN, PLAN_REPOS)

#: Anything capable of expressing a BUY, a short, or a raw broker submission. The manager
#: must reach the broker ONLY through the existing exit handlers
#: (`AuthorizePositionExitHandler`/`SubmitAuthorizedPositionExitHandler`), never directly.
FORBIDDEN_SURFACE: tuple[str, ...] = (
    "empirical_platform.decision_candidate.paper_execution.PaperOrderRequest",
    "empirical_platform.decision_candidate.paper_execution_repositories.PaperBrokerPort",
    "empirical_platform.usecases.paper_execution",
    "submit_order",
    "PreparePaperBoundTradeProposalHandler",
    "IssuePaperBoundOrderIntentHandler",
    "SubmitAuthorizedPaperOrderHandler",
    # No Live surface exists anywhere in this codebase yet; this name is reserved and
    # forbidden here so that the day one IS added, this test fails loudly rather than
    # silently passing on a module that has quietly started importing it.
    "AlpacaLiveClient",
    "LiveBrokerPort",
    "LiveClient",
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


def _code_only(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        lines = text.splitlines(keepends=True)
        return "".join(lines[tree.body[0].end_lineno :])
    return text


def test_no_v1_plan_module_imports_or_names_a_buy_short_or_live_surface() -> None:
    for path in V1_MODULES:
        names = _imports(path)
        code = _code_only(path)
        for forbidden in FORBIDDEN_SURFACE:
            assert not any(forbidden in name for name in names), (path.name, forbidden)
            assert forbidden not in code, (path.name, forbidden)


def test_the_manager_never_constructs_an_order_or_exit_request_directly() -> None:
    """Quantity, price and side must come from the EXISTING exit pipeline's own verified
    construction (`PreviewPositionExitHandler`, which derives quantity from the broker-
    verified attributable position) -- never from a literal the manager assembles itself."""
    code = _code_only(MANAGER)
    for forbidden in ("PositionExitRequest(", "PaperOrderRequest(", "OrderType.MARKET"):
        assert forbidden not in code, forbidden


def test_the_manager_only_reaches_the_broker_through_the_existing_exit_handlers() -> None:
    names = _imports(MANAGER)
    required = {
        "empirical_platform.usecases.position_exit.AuthorizePositionExitHandler",
        "empirical_platform.usecases.position_exit.SubmitAuthorizedPositionExitHandler",
        "empirical_platform.usecases.position_exit.ReconcilePositionExitHandler",
    }
    assert required <= names


def test_approved_plan_domain_is_pure_no_io_no_broker_no_clock_reads() -> None:
    """Mirrors `operator_trading_configuration.py`'s own discipline: this module computes,
    it never fetches. No `datetime.now()`/`utcnow()`, no broker/network import."""
    code = _code_only(PLAN_DOMAIN)
    for forbidden in ("datetime.now(", "utcnow(", "requests.", "socket.", "psycopg"):
        assert forbidden not in code, forbidden
    names = _imports(PLAN_DOMAIN)
    assert not any(n.startswith("empirical_platform.shared.brokerage") for n in names)
