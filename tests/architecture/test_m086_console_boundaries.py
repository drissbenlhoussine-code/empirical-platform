"""MILESTONE-086 -- the Operator Console's own boundaries, parsed from its source.

The presentation layer (routes, pages, web plumbing) may not import PostgreSQL, SQLAlchemy,
psycopg, a broker adapter or a domain module; the composition root is the only console
module that may construct the simulation broker, and no console module may import the
real Alpaca client. There is no LIVE execution anywhere in the console.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
PRESENTATION = (
    ROOT / "entrypoints" / "operator_console_app.py",
    ROOT / "entrypoints" / "_operator_console_html.py",
    ROOT / "entrypoints" / "_operator_console_web.py",
)
COMPOSITION = ROOT / "entrypoints" / "_operator_console_composition.py"
LAUNCHER = ROOT / "entrypoints" / "operator_console.py"
SERVICES = (
    ROOT / "usecases" / "operator_console.py",
    ROOT / "usecases" / "operator_console_fixtures.py",
)
SIMULATION = ROOT / "shared" / "brokerage" / "simulation_paper.py"
CONSOLE_MODULES = (*PRESENTATION, COMPOSITION, LAUNCHER, *SERVICES, SIMULATION)


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


@pytest.mark.parametrize("path", PRESENTATION, ids=[p.name for p in PRESENTATION])
def test_presentation_imports_no_persistence_broker_or_domain(path: Path) -> None:
    names = _imports(path)
    for forbidden in (
        "empirical_platform.shared.persistence",
        "sqlalchemy",
        "psycopg",
        "empirical_platform.shared.brokerage",
        "empirical_platform.decision_candidate",
        "alembic",
    ):
        assert not any(n.startswith(forbidden) for n in names), (path.name, forbidden)


def test_only_the_composition_root_constructs_the_simulation_broker() -> None:
    for path in (*PRESENTATION, LAUNCHER, *SERVICES):
        assert "SimulatedPaperBroker" not in path.read_text(encoding="utf-8"), path.name
    assert "SimulatedPaperBroker(" in COMPOSITION.read_text(encoding="utf-8")


def test_no_console_module_imports_the_real_alpaca_client() -> None:
    for path in CONSOLE_MODULES:
        names = _imports(path)
        # Parsed imports, not prose: a docstring may NAME the client to say it is absent.
        for forbidden in (
            "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperClient",
            "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperMarketDataClient",
            "empirical_platform.shared.brokerage.alpaca_paper.credentials_from_environment",
            "empirical_platform.entrypoints._paper_composition",
        ):
            assert forbidden not in names, (path.name, forbidden)


def test_the_composition_root_refuses_every_capability_but_simulation() -> None:
    from empirical_platform.usecases.operator_console import ExecutionCapability

    source = COMPOSITION.read_text(encoding="utf-8")
    assert "if capability is not ExecutionCapability.SIMULATION:" in source
    assert "raise CapabilityRefusedError" in source
    # No branch names PAPER or LIVE as something to build.
    for member in (ExecutionCapability.PAPER, ExecutionCapability.LIVE):
        assert f"ExecutionCapability.{member.name}" not in source


def test_the_simulation_broker_opens_no_socket_and_reads_no_credential() -> None:
    names = _imports(SIMULATION)
    for forbidden in ("http", "socket", "ssl", "urllib", "requests", "os.environ"):
        assert not any(n == forbidden or n.startswith(forbidden + ".") for n in names), forbidden
    text = SIMULATION.read_text(encoding="utf-8")
    assert "os.environ" not in text and "getenv" not in text


def test_the_launcher_binds_loopback_only() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert 'DEFAULT_HOST = "127.0.0.1"' in text
    assert "0.0.0.0" not in text  # noqa: S104 - asserting its absence
    assert "is_loopback" in text


def test_the_pages_carry_no_script_and_no_external_asset() -> None:
    text = (ROOT / "entrypoints" / "_operator_console_html.py").read_text(encoding="utf-8")
    assert "<script" not in text
    assert "https://" not in text and "http://" not in text
    assert 'href="/static/console.css"' in text
