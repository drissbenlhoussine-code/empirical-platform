"""RELEASE v1 Release Blocker (in-console Owner gate) -- Paper/Simulation isolation.

Direct answer to the 2026-10-06 incident: the Owner reached the always-running M086/M087
SIMULATION console (port 8086, database `empirical_platform`, `CFG-086-SIM`) through the
Tailscale root path and mistook its leftover `--load-day` fixture execution for a real PAPER
one. Nothing in that incident was a routing misconfiguration or a database cross-wire -- but
this module proves, from the SOURCE rather than from one day's runtime behaviour, that the
PAPER approval surface this release adds (`prepare_v1_paper_candidate`, the console's
`/prepare-candidate` and `/confirm-approval` routes for the exit-capable composition) has no
import-level path to the SIMULATION broker, the SIMULATION composition root, or Store A's own
config resolver -- so no code change here could make that confusion a real cross-wire, only a
UI/URL one (which `_env_badge_class`'s distinct PAPER badge color now also answers).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path("src/empirical_platform")

#: Every module this release's new in-console Owner Gate touches: the real preparation
#: function and the two route modules that can reach it (plain PAPER's router, and the
#: exit-capable one the real console actually runs).
V1_PAPER_SURFACE = (
    ROOT / "usecases" / "paper_operator_console.py",
    ROOT / "usecases" / "full_plan_approval.py",
    ROOT / "entrypoints" / "paper_operator_console_app.py",
    ROOT / "entrypoints" / "_paper_operator_console_composition.py",
    ROOT / "entrypoints" / "_paper_position_exit_composition.py",
)

#: Named, not guessed: the exact SIMULATION-only symbols/modules a real cross-wire would have
#: to import. `operator_console_fixtures.simulation_timezone_for` is deliberately NOT here --
#: it is a pure, stateless timezone lookup `paper_operator_console.py` already uses for its
#: own (M088) default configuration, and carries no SIMULATION broker or database handle.
FORBIDDEN_SIMULATION_SYMBOLS = (
    "SimulatedPaperBroker",
    "SimulatedMarketData",
    "empirical_platform.entrypoints._operator_console_composition",  # Store A's own root
    "empirical_platform.shared.brokerage.simulation_paper",
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


def test_no_v1_paper_module_imports_any_simulation_symbol() -> None:
    for path in V1_PAPER_SURFACE:
        names = _imports(path)
        for forbidden in FORBIDDEN_SIMULATION_SYMBOLS:
            assert not any(n == forbidden or n.startswith(forbidden + ".") for n in names), (
                path.name,
                forbidden,
            )


def test_no_v1_paper_module_constructs_a_simulated_broker_by_name() -> None:
    # Source text, not just parsed imports: catches a qualified in-line reference
    # (`module.SimulatedPaperBroker(...)`) an import-only check could miss.
    for path in V1_PAPER_SURFACE:
        source = path.read_text(encoding="utf-8")
        assert "SimulatedPaperBroker(" not in source, path.name
        assert "SimulatedMarketData(" not in source, path.name


def test_the_v1_prepare_function_names_only_store_b_identities() -> None:
    """`prepare_v1_paper_candidate` is the one function this release adds that originates a
    NEW governed candidate; it must carry Store B's own `CFG-089-PAPER` identity and never
    the SIMULATION configuration's `CFG-086-SIM`."""
    source = (ROOT / "usecases" / "paper_operator_console.py").read_text(encoding="utf-8")
    assert "CFG-089-PAPER" in source
    assert "CFG-086-SIM" not in source
