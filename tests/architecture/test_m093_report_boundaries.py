"""MILESTONE-093 -- the read-only Owner strategy-discovery report console has no trading
controls.

Static/import-based checks, mirroring `test_m092_report_boundaries.py`'s own style. This
console renders one already-computed JSON file; it must never import a broker client, a
usecase handler, or persistence, and it must never define a POST route.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
HTML = ROOT / "entrypoints" / "_strategy_discovery_report_html.py"
CONSOLE = ROOT / "entrypoints" / "strategy_discovery_report.py"
M093_REPORT_MODULES = (HTML, CONSOLE)

FORBIDDEN_SURFACE: tuple[str, ...] = (
    "empirical_platform.shared.brokerage.alpaca_paper",
    "AlpacaPaperClient",
    "AlpacaPaperMarketDataClient",
    "submit_order",
    "submit_close_order",
    "cancel_order",
    "empirical_platform.usecases.opportunity_engine",
    "empirical_platform.usecases.opportunity_engine_v2_validation",
    "empirical_platform.usecases.m093_research_framework",
    "empirical_platform.usecases.paper_execution",
    "empirical_platform.usecases.position_exit",
    "empirical_platform.shared.persistence",
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


@pytest.mark.parametrize("path", M093_REPORT_MODULES, ids=[p.name for p in M093_REPORT_MODULES])
def test_no_report_module_imports_a_broker_or_usecase_surface(path: Path) -> None:
    names = _imports(path)
    source = path.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
        assert forbidden not in source, (path.name, forbidden)


def test_the_console_defines_no_post_route() -> None:
    source = CONSOLE.read_text(encoding="utf-8")
    assert "router.post(" not in source
    assert ".post(" not in source


def test_the_html_module_emits_no_form_or_button() -> None:
    """Checks the module's executable body, excluding its own module docstring: the
    docstring legitimately says "no CSRF token" to explain what is deliberately absent."""
    source = HTML.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    docstring_end = 0
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        docstring_end = tree.body[0].end_lineno or 0
    body = "".join(lines[docstring_end:])
    for forbidden in ("<form", "<button", 'method="post"', "csrf"):
        assert forbidden not in body.lower(), forbidden
