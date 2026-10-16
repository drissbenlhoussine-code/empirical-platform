"""RELEASE v1 -- recording an external position closure can never BUY, SELL, short, cancel
an order, or reach a Live client. Static/import-based checks, mirroring
`test_v1_position_plan_manager_boundaries.py`'s own style: these are claims about the
SOURCE, not just about what today's tests happen to exercise.
"""

from __future__ import annotations

import ast
from pathlib import Path

HANDLER = Path("src/empirical_platform/usecases/record_external_position_closure.py")
DOMAIN = Path("src/empirical_platform/decision_candidate/external_position_closure.py")
REPOS = Path("src/empirical_platform/decision_candidate/external_position_closure_repositories.py")
V1_MODULES = (HANDLER, DOMAIN, REPOS)

#: Anything capable of expressing a BUY, a SELL dispatch, a cancel, or a raw broker write.
#: This handler may only READ the broker (`fetch_order_by_client_order_id`,
#: `fetch_position`) -- never submit or cancel anything, and never through a second,
#: parallel path to the one the manual/automatic exit pipeline already uses.
FORBIDDEN_SURFACE: tuple[str, ...] = (
    "submit_close_order",
    "submit_order",
    "cancel_order",
    "PositionExitRequest(",
    "PaperOrderRequest(",
    "SubmitAuthorizedPositionExitHandler",
    "SubmitAuthorizedPositionExitCommand",
    "AuthorizePositionExitHandler",
    "AuthorizePositionExitCommand",
    "PreviewPositionExitHandler",
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


def test_no_v1_external_closure_module_names_a_submit_cancel_or_live_surface() -> None:
    for path in V1_MODULES:
        names = _imports(path)
        code = _code_only(path)
        for forbidden in FORBIDDEN_SURFACE:
            assert not any(forbidden in name for name in names), (path.name, forbidden)
            assert forbidden not in code, (path.name, forbidden)


def test_the_handler_only_calls_read_only_broker_methods() -> None:
    """The ONLY two `self._broker.*` calls this module may ever make."""
    code = _code_only(HANDLER)
    calls = {
        match
        for match in ast.walk(ast.parse(code))
        if isinstance(match, ast.Attribute)
        and isinstance(match.value, ast.Attribute)
        and match.value.attr == "_broker"
    }
    called_names = {node.attr for node in calls}
    assert called_names <= {"fetch_order_by_client_order_id", "fetch_position"}
    assert called_names  # the test itself must exercise at least one real broker call


def test_the_handler_never_mutates_approved_plan() -> None:
    """The pre-existing `ApprovedPlan` row and its trigger history are preserved exactly --
    this module must never import `ApprovedPlanRepository` or call `claim_exit_trigger`."""
    code = _code_only(HANDLER)
    names = _imports(HANDLER)
    assert "claim_exit_trigger" not in code
    assert not any("approved_plan" in name for name in names)


def test_external_position_closure_domain_is_pure_no_io_no_broker_no_clock_reads() -> None:
    code = _code_only(DOMAIN)
    for forbidden in ("datetime.now(", "utcnow(", "requests.", "socket.", "psycopg"):
        assert forbidden not in code, forbidden
    names = _imports(DOMAIN)
    assert not any(n.startswith("empirical_platform.shared.brokerage") for n in names)
