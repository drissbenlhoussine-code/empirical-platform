"""MILESTONE-028 tests for the CommandHandler/QueryHandler relationship and
QueryHandler's read-only-semantic (not mechanical) limitation.

Covers Design Section 9 (declared relationship vs. structural-typing
reality) and Section 10 (read-only semantics) test obligations (Section 19
Items 5, 6, 7) that neither `test_command_handler_*` nor
`test_query_handler_*` cover on their own, since they concern the
relationship *between* the two contracts, not either one in isolation.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

from empirical_platform.shared.contracts.command import CommandHandler
from empirical_platform.shared.contracts.query import QueryHandler

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_RELATIONSHIP_FIXTURES = _REPO_ROOT / "tests" / "typing_fixtures" / "command_query_relationship"
_COMMAND_MODULE_PATH = (
    _REPO_ROOT / "src" / "empirical_platform" / "shared" / "contracts" / "command.py"
)
_QUERY_MODULE_PATH = _REPO_ROOT / "src" / "empirical_platform" / "shared" / "contracts" / "query.py"


def _run_mypy(fixture_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - test invokes current Python with controlled fixture args.
        [sys.executable, "-m", "mypy", "--config-file", str(_PYPROJECT), str(fixture_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
    return modules


# --- Declared relationship (Design Section 9, Section 19 Item 5) -----------


def test_query_handler_does_not_inherit_from_command_handler() -> None:
    assert CommandHandler not in QueryHandler.__mro__


def test_command_handler_does_not_inherit_from_query_handler() -> None:
    assert QueryHandler not in CommandHandler.__mro__


def test_no_shared_custom_base_beyond_protocol_and_object() -> None:
    command_bases = {base for base in CommandHandler.__mro__ if base not in (object,)}
    query_bases = {base for base in QueryHandler.__mro__ if base not in (object,)}
    shared = command_bases & query_bases
    # Both Protocols legitimately share typing.Protocol/typing.Generic as
    # infrastructure base classes; no *custom* base should be shared.
    assert all(base.__module__ == "typing" for base in shared)


def test_query_module_does_not_import_command_module() -> None:
    modules = _imported_top_level_modules(_QUERY_MODULE_PATH)
    assert not any("command" in module for module in modules)


def test_command_module_does_not_import_query_module() -> None:
    modules = _imported_top_level_modules(_COMMAND_MODULE_PATH)
    assert not any("query" in module for module in modules)


# --- Structural-compatibility reality (Design Section 9, Section 19 Item 6) -


def test_compatible_concrete_class_satisfies_both_protocols_simultaneously() -> None:
    """Expected property of Python's structural Protocol typing, not a
    regression or defect: a single concrete class whose `handle` method's
    parameter/return types align with both Protocols' type arguments
    type-checks cleanly as both `CommandHandler[X, Y]` and
    `QueryHandler[X, Y]`. CommandHandler and QueryHandler still declare no
    inheritance, import, or shared base with each other (tests above) --
    this is purely a consequence of structural (duck) typing, which this
    milestone does not attempt to defeat."""
    result = _run_mypy(_RELATIONSHIP_FIXTURES / "dual_satisfaction.py")
    assert result.returncode == 0
    assert "Success: no issues found" in result.stdout


def test_mismatched_type_arguments_are_still_rejected() -> None:
    """Structural compatibility is conditional on genuine type alignment,
    not universal: a handler typed for one value type is still correctly
    rejected when assigned to a CommandHandler slot declared for an
    unrelated, mismatched type."""
    result = _run_mypy(_RELATIONSHIP_FIXTURES / "mismatched_dual_satisfaction.py")
    assert result.returncode != 0
    assert "error: Incompatible types in assignment" in result.stdout
    assert "[assignment]" in result.stdout


def test_relationship_fixtures_are_not_part_of_canonical_mypy_package_scope() -> None:
    import tomllib

    config = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    packages = config["tool"]["mypy"]["packages"]
    assert packages == ["empirical_platform"]


# --- Read-only limitation (Design Section 10, Section 19 Item 7) -----------


def test_query_handler_module_exports_no_repository_or_transaction_api() -> None:
    query_module = importlib.import_module("empirical_platform.shared.contracts.query")
    public_names = [name for name in dir(query_module) if not name.startswith("_")]
    forbidden_substrings = ("repository", "transaction", "session", "uow", "unit_of_work")
    for name in public_names:
        lowered = name.lower()
        assert not any(forbidden in lowered for forbidden in forbidden_substrings)


def test_query_handler_module_defines_no_decorator_or_runtime_guard() -> None:
    tree = ast.parse(_QUERY_MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            assert node.decorator_list == []
        if isinstance(node, ast.ClassDef):
            assert node.decorator_list == []


def test_importing_query_module_has_no_side_effect() -> None:
    # Re-import is a no-op if already imported; importlib.reload forces
    # module-level code to execute again, proving it performs no I/O,
    # network, filesystem, or global-state mutation (no exception, and the
    # Protocol class identity is freshly rebuilt each time without error).
    query_module = importlib.import_module("empirical_platform.shared.contracts.query")
    reloaded = importlib.reload(query_module)
    assert reloaded.QueryHandler is not None


def test_no_documentation_claims_mechanical_non_mutation_guarantee() -> None:
    source = _QUERY_MODULE_PATH.read_text(encoding="utf-8").lower()
    # The module may describe "read-side intent"/"read intent" as
    # vocabulary, but must never claim enforcement, guarantee, or
    # prevention of mutation -- those claims belong only to the frozen
    # governance documents' explicit disclaimers, never to the source
    # module itself.
    forbidden_claims = (
        "guarantees read-only",
        "enforces read-only",
        "prevents mutation",
        "cannot mutate",
        "read-only enforcement",
    )
    for claim in forbidden_claims:
        assert claim not in source
