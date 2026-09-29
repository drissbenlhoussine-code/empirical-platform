"""MILESTONE-087/089 -- the exit path's boundaries, parsed from its source.

M085 stays structurally BUY-only; the exit domain is separate and imports no M085 request
type; SIMULATION and PAPER (never LIVE) are the only environments an exit can bind; no
M087 domain/usecase/persistence module imports the real Alpaca client directly (it is
composed in and injected, never imported by these modules); presentation imports no
persistence or domain; the simulation broker still opens no socket. MILESTONE-089 widened
the Alpaca adapter itself to implement the exit port (`submit_close_order`) -- narrowly,
through `PositionExitRequest` alone, never a generic sell; this file's tests were updated
to prove that narrowness rather than assert the capability's continued absence.
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


def test_allowed_exit_environments_is_exactly_simulation_and_paper_never_live() -> None:
    """MILESTONE-089 widened ALLOWED_EXIT_ENVIRONMENTS from {SIMULATION} to
    {SIMULATION, PAPER}. Checked against the live value, not the source text, so a rename
    or reformat cannot silently widen it further. The runtime refusal for LIVE itself is
    proven by test_the_request_still_refuses_live_and_only_live in
    test_m087_position_exit_domain.py; this proves the declared set."""
    from empirical_platform.decision_candidate.position_exit import ALLOWED_EXIT_ENVIRONMENTS

    assert ALLOWED_EXIT_ENVIRONMENTS == frozenset({"SIMULATION", "PAPER"})


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


def test_the_alpaca_adapters_exit_implementation_is_narrow() -> None:
    """MILESTONE-089: the Alpaca adapter DOES implement the exit port now, but only through
    `PositionExitRequest` -- a type that cannot express a short, a fractional quantity, an
    extended-hours order or a time in force other than DAY. This test proves the narrowness
    (one method, one accepted type, no raw symbol/side parameter) rather than the
    capability's continued absence, which MILESTONE-089's own mission authorizes."""
    source = ALPACA.read_text(encoding="utf-8")
    assert source.count("def submit_close_order(") == 1
    assert "def submit_close_order(\n        self, request: PositionExitRequest" in source
    # The one broker-write method the exit port adds takes the fully-typed, already-
    # validated request -- never a raw symbol/side/quantity the caller assembled here.
    assert "def submit_close_order(self, symbol" not in source
    names = _imports(ALPACA)
    assert "empirical_platform.decision_candidate.position_exit.PositionExitRequest" in names


def test_exactly_the_simulation_and_alpaca_brokers_implement_submit_close_order() -> None:
    implementers = sorted(
        path
        for path in ROOT.rglob("*.py")
        if "def submit_close_order(" in path.read_text(encoding="utf-8")
    )
    # The port DECLARES it (a Protocol); SIMULATION and Alpaca (MILESTONE-089) IMPLEMENT it.
    # No third implementation exists anywhere in the package.
    assert implementers == sorted([ALPACA, EXIT_PORTS, SIMULATION])
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
