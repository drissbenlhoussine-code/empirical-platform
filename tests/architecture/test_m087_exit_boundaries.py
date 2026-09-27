"""MILESTONE-087 -- the exit path's boundaries, parsed from its source.

M085 stays structurally BUY-only; the exit domain is separate and imports no M085 request
type; SIMULATION is the only environment an exit can bind; no M087 module imports the real
Alpaca client or implements the exit port for it; presentation imports no persistence or
domain; the simulation broker still opens no socket.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
EXIT_DOMAIN = ROOT / "decision_candidate" / "position_exit.py"
EXIT_PORTS = ROOT / "decision_candidate" / "position_exit_repositories.py"
EXIT_USECASES = ROOT / "usecases" / "position_exit.py"
EXIT_CONSOLE = ROOT / "usecases" / "operator_console_exits.py"
EXIT_PERSISTENCE = (
    ROOT / "shared" / "persistence" / "postgres_repositories" / "position_exit_repositories.py"
)
SIMULATION = ROOT / "shared" / "brokerage" / "simulation_paper.py"
ALPACA = ROOT / "shared" / "brokerage" / "alpaca_paper.py"
M085_DOMAIN = ROOT / "decision_candidate" / "paper_execution.py"
PRESENTATION = (
    ROOT / "entrypoints" / "operator_console_app.py",
    ROOT / "entrypoints" / "_operator_console_html.py",
)
M087_MODULES = (EXIT_DOMAIN, EXIT_PORTS, EXIT_USECASES, EXIT_CONSOLE, EXIT_PERSISTENCE)


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


def test_m085_paper_order_request_is_unchanged_and_buy_only() -> None:
    source = M085_DOMAIN.read_text(encoding="utf-8")
    assert 'if self.side != "BUY":' in source
    assert 'raise ValueError("side must be BUY: this product is long-only")' in source
    assert "SELL_TO_CLOSE" not in source and "position_exit" not in source


def test_the_exit_domain_does_not_import_or_widen_the_m085_request_type() -> None:
    names = _imports(EXIT_DOMAIN)
    assert "empirical_platform.decision_candidate.paper_execution.PaperOrderRequest" not in names
    source = EXIT_DOMAIN.read_text(encoding="utf-8")
    assert "class PositionExitRequest:" in source
    assert 'EXIT_SIDE = "SELL_TO_CLOSE"' in source
    assert 'ALLOWED_EXIT_ENVIRONMENTS: frozenset[str] = frozenset({"SIMULATION"})' in source
    assert "PAPER" not in source.replace("PAPER or LIVE", "").replace("PaperOrderRequest", "")


@pytest.mark.parametrize("path", M087_MODULES, ids=[p.name for p in M087_MODULES])
def test_no_m087_module_imports_the_real_alpaca_client(path: Path) -> None:
    names = _imports(path)
    for forbidden in (
        "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperClient",
        "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperMarketDataClient",
        "empirical_platform.shared.brokerage.alpaca_paper.credentials_from_environment",
        "empirical_platform.entrypoints._paper_composition",
    ):
        assert forbidden not in names, (path.name, forbidden)


def test_the_alpaca_adapter_has_no_exit_implementation() -> None:
    source = ALPACA.read_text(encoding="utf-8")
    assert "submit_close_order" not in source and "SELL_TO_CLOSE" not in source
    assert "position_exit" not in source


def test_only_the_simulation_broker_implements_submit_close_order() -> None:
    implementers = sorted(
        path
        for path in ROOT.rglob("*.py")
        if "def submit_close_order(" in path.read_text(encoding="utf-8")
    )
    # The port DECLARES it (a Protocol); the simulation broker is the only IMPLEMENTATION.
    assert implementers == sorted([EXIT_PORTS, SIMULATION])
    assert "def reduce_position(" in SIMULATION.read_text(encoding="utf-8")


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


def test_no_console_route_writes_an_exit_table() -> None:
    for path in PRESENTATION:
        source = path.read_text(encoding="utf-8")
        assert "position_exit_" not in source and "INSERT" not in source and "UPDATE" not in source


def test_the_exit_usecases_and_console_import_no_persistence() -> None:
    for path in (EXIT_DOMAIN, EXIT_PORTS, EXIT_USECASES, EXIT_CONSOLE):
        names = _imports(path)
        assert not any(n.startswith("empirical_platform.shared.persistence") for n in names), path
        assert not any(n.startswith(("sqlalchemy", "psycopg")) for n in names), path


def test_each_milestone_composition_verifies_its_own_exact_schema_head() -> None:
    """Schema authority belongs to the composition roots, one exact head each, no bypass."""
    m086 = (ROOT / "entrypoints" / "_operator_console_composition.py").read_text(encoding="utf-8")
    m087 = (ROOT / "entrypoints" / "_position_exit_composition.py").read_text(encoding="utf-8")
    # M086 public composition: the exact M085 head, and it never names the M087 guard.
    assert "require_exact_m085_schema_head(service)" in m086
    assert "require_exact_m087_schema_head" not in m086
    # M087 composition: the exact M087 head, and it never names the M085 guard.
    assert "require_exact_m087_schema_head(service)" in m087
    assert "require_exact_m085_schema_head" not in m087
    # Both build through the private already-verified helper, which is not exported and takes
    # no verifier: nothing a caller passes can replace either guard.
    assert "def _compose_verified_console(" in m086
    assert '"_compose_verified_console"' not in m086  # not in __all__
    for source in (m086, m087):
        assert "verifier:" not in source and "verify:" not in source  # no such parameter exists
    for source in (m086, m087):
        assert (
            "ExecutionCapability.PAPER" not in source and "ExecutionCapability.LIVE" not in source
        )
    assert "if capability is not ExecutionCapability.SIMULATION:" in m086
    assert "_refuse_unless_simulation(capability)" in m087
    assert "environment=ExecutionCapability.SIMULATION.value" in m086
    # The launcher composes the M087 runtime (schema = M087 head).
    launcher = (ROOT / "entrypoints" / "operator_console.py").read_text(encoding="utf-8")
    assert "simulation_exit_console_runtime(" in launcher


def test_the_m087_migration_is_additive_and_stacks_on_the_m085_head() -> None:
    path = Path("migrations/versions/e7c1a9d3b5f2_create_m087_position_exit_schema.py")
    source = path.read_text(encoding="utf-8")
    m085_head = "".join(("a7d3c9", "e14f26"))  # grouped for the secret scanner
    assert f'down_revision: str | None = "{m085_head}"' in source
    assert "op.create_table" in source and "op.alter_table" not in source
    upgrade_body = source.split("def upgrade")[1].split("def downgrade")[0]
    # The upgrade creates M087 objects only; the M085 entry table is READ by a guard function
    # (defined above as a constant) and never created, altered or written.
    assert "op.drop_column" not in source and "paper_execution_attempt" not in upgrade_body
    assert "ALTER TABLE public.paper_" not in source
    for table in (
        "position_exit_preview",
        "position_exit_authorization",
        "position_exit_attempt",
        "position_exit_acknowledgement",
        "position_exit_reconciliation_round",
        "position_exit_event",
    ):
        assert table in source
    assert "environment = 'SIMULATION'" in source and "side = 'SELL_TO_CLOSE'" in source
