"""MILESTONE-027 unit tests for the CommandHandler contract module.

Covers what `test_command_handler_typing.py` does not: the module's
import-graph (zero dependency beyond `typing`), its export surface
(`CommandHandler` only, not the private `TypeVar`s), and variance proofs
demonstrating the contravariant-input/covariant-output generics accept
wider-command and narrower-result handlers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import empirical_platform.shared.contracts as contracts
from empirical_platform.shared.contracts.command import CommandHandler

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "empirical_platform"
    / "shared"
    / "contracts"
    / "command.py"
)


def test_module_imports_cleanly() -> None:
    assert CommandHandler is not None


def test_module_has_zero_dependency_beyond_typing() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
    assert imported_modules == {"typing", "__future__"}


def test_only_command_handler_is_exported() -> None:
    assert "CommandHandler" in contracts.__all__
    assert "_CommandT_contra" not in contracts.__all__
    assert "_ResultT_co" not in contracts.__all__
    assert not hasattr(contracts, "_CommandT_contra")
    assert not hasattr(contracts, "_ResultT_co")


def test_variance_proofs_are_present_in_the_type_checked_module() -> None:
    """The actual contravariant/covariant proof is type-checked by mypy
    against `command.py` itself (verified manually and covered by the
    canonical `mypy` gate in `verify.ps1`), not by this pytest test --
    Python does not enforce type annotations at runtime, so an `isinstance`
    assertion here would prove nothing about variance correctness. This
    test only confirms the proof code has not been silently deleted from
    the module mypy actually checks."""
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "_contravariant_input_check" in source
    assert "_covariant_output_check" in source
    assert "_WiderInputExampleHandler" in source
    assert "_NarrowerOutputExampleHandler" in source
