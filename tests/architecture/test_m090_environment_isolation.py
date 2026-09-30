"""MILESTONE-090 Category I (environment) -- M090's own console cannot reach a write path, a
Live endpoint, or a second, unreviewed credential convention.

Static/import-based checks, mirroring `test_m090_opportunity_engine_boundaries.py`'s own style
-- no console is started here; SIMULATION (8086) and the M088/M089 PAPER console (8189) are
left completely untouched by this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
COMPOSITION = ROOT / "entrypoints" / "_opportunity_engine_composition.py"
ENTRYPOINT_SCRIPT = ROOT / "entrypoints" / "opportunity_engine.py"
APP = ROOT / "entrypoints" / "opportunity_engine_app.py"
HTML = ROOT / "entrypoints" / "_opportunity_engine_html.py"
M090_ENTRYPOINT_MODULES = (COMPOSITION, ENTRYPOINT_SCRIPT, APP, HTML)

#: Every write-capable object M088/M089's OWN composition roots construct or export. None of
#: M090's entrypoint modules may import or reference any of these by name -- M090 reads real
#: Alpaca Paper market data, but never through a console that could also dispatch an order.
M088_M089_WRITE_CAPABLE_SURFACE: tuple[str, ...] = (
    "_paper_operator_console_composition",
    "paper_operator_console_runtime",
    "PaperConsoleBackend",
    "_paper_position_exit_composition",
    "paper_operator_console_with_exit_runtime",
    "OperatorConsoleService",
    "PositionExitConsole",
    "ConsoleRepositories",
    "HmacSigner",
    "SubmitAuthorizedPaperOrderHandler",
    "SubmitAuthorizedPositionExitHandler",
    "IssuePaperBoundOrderIntentHandler",
    "IssueOrderIntentHandler",
)

#: The only Alpaca hosts this repository's own adapter recognizes as legitimate (see
#: `shared.brokerage.alpaca_paper`'s `PAPER_ENDPOINT_HOST`/`DATA_ENDPOINT_HOST`). Any OTHER
#: `alpaca.markets` (or similar) host literal appearing in an M090 entrypoint module would be
#: evidence of a second, unreviewed endpoint -- this repository has no LIVE host anywhere, and
#: this test proves M090 does not introduce the first one.
_ALLOWED_ALPACA_HOST_FRAGMENTS = ("paper-api.alpaca.markets", "data.alpaca.markets")


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


@pytest.mark.parametrize(
    "path", M090_ENTRYPOINT_MODULES, ids=[p.name for p in M090_ENTRYPOINT_MODULES]
)
def test_no_m090_entrypoint_imports_the_m088_or_m089_write_capable_surface(path: Path) -> None:
    names = _imports(path)
    source = path.read_text(encoding="utf-8")
    for forbidden in M088_M089_WRITE_CAPABLE_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
        # Also check plain source text, not just import statements: a reference could arrive
        # as a type annotation string or a dynamically-looked-up attribute.
        assert forbidden not in source, (path.name, forbidden)


@pytest.mark.parametrize(
    "path", M090_ENTRYPOINT_MODULES, ids=[p.name for p in M090_ENTRYPOINT_MODULES]
)
def test_no_m090_entrypoint_calls_submit_or_cancel(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for forbidden in ("submit_order(", "cancel_order(", ".submit_order", ".cancel_order"):
        assert forbidden not in source, (path.name, forbidden)


def test_the_composition_module_pins_only_the_known_paper_and_data_hosts() -> None:
    """No LIVE or otherwise unrecognized Alpaca host literal appears anywhere in the module
    that constructs this milestone's broker clients."""
    source = COMPOSITION.read_text(encoding="utf-8")
    for fragment in ("alpaca.markets", "api.alpaca"):
        for occurrence_start in _find_all(source, fragment):
            window = source[max(0, occurrence_start - 40) : occurrence_start + 40]
            assert any(allowed in window for allowed in _ALLOWED_ALPACA_HOST_FRAGMENTS), (
                "unrecognized Alpaca host literal near",
                window,
            )


def _find_all(haystack: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index == -1:
            return positions
        positions.append(index)
        start = index + 1


def test_the_composition_module_reuses_the_single_established_credential_convention() -> None:
    """`resolve_paper_endpoint`/`credentials_from_environment` -- the SAME pair
    `entrypoints._paper_composition.paper_execution_runtime` already uses -- are both present,
    and no second credential-reading function is defined in this module. A composition root
    that read `os.environ["..."]` for an API key ITSELF, rather than delegating to the one
    reviewed function, would be a second, unreviewed credential path."""
    source = COMPOSITION.read_text(encoding="utf-8")
    assert "resolve_paper_endpoint" in source
    assert "credentials_from_environment" in source
    assert "from empirical_platform.entrypoints._paper_composition import" in source
    # The only os.environ access in this module is the ONE bulk copy handed to
    # `credentials_from_environment` -- never a direct index/get for a credential-shaped key.
    tree = ast.parse(source)
    environ_subscripts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
    ]
    assert environ_subscripts == []


def test_no_m090_entrypoint_module_names_a_second_configuration_source() -> None:
    """M090 reads configuration through `usecases.opportunity_engine`'s own re-exported
    `OperatorTradingConfigurationRepository`/`OperatorTradingConfiguration` -- proving no M090
    entrypoint module imports `decision_candidate` directly (the boundary
    `tools/check_architecture.py` already enforces globally; this restates it narrowly for
    M090's own files so a regression here fails fast, close to the change that would cause it)."""
    for path in M090_ENTRYPOINT_MODULES:
        names = _imports(path)
        assert not any(name == "empirical_platform.decision_candidate" for name in names)
        assert not any(
            name.startswith("empirical_platform.decision_candidate.") for name in names
        ), path.name


def test_m090_persistence_module_also_avoids_the_write_capable_surface() -> None:
    path = (
        ROOT
        / "shared"
        / "persistence"
        / "postgres_repositories"
        / "opportunity_engine_repositories.py"
    )
    names = _imports(path)
    source = path.read_text(encoding="utf-8")
    for forbidden in M088_M089_WRITE_CAPABLE_SURFACE:
        assert not any(forbidden in name for name in names), (path.name, forbidden)
        assert forbidden not in source, (path.name, forbidden)
