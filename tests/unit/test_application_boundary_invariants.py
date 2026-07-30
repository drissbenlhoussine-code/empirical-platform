"""MILESTONE-029 structural invariant tests for the application package.

Verifies, by inspecting source rather than runtime behavior, the frozen
design constraints that a purely behavioral test cannot prove: no
transaction/persistence coupling, no custom exception hierarchy, no
runtime Protocol introspection, and synchronous-only execution.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import empirical_platform.application as application
from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.application.query import QueryEntryPoint

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "src" / "empirical_platform" / "application"
_MODULE_FILES = (_PACKAGE_DIR / "command.py", _PACKAGE_DIR / "query.py")


def _imported_top_level_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    return names


def test_only_entry_points_are_exported() -> None:
    assert set(application.__all__) == {"CommandEntryPoint", "QueryEntryPoint"}


def test_modules_import_only_frozen_contracts_and_future_annotations() -> None:
    for path in _MODULE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = _imported_top_level_names(tree)
        assert imported == {"__future__", "empirical_platform"}, (
            f"{path} imports beyond the frozen contract boundary: {imported}"
        )


def test_modules_do_not_import_persistence_or_transaction_machinery() -> None:
    forbidden_substrings = (
        "persistence",
        "run_composed",
        "sqlalchemy",
        "psycopg",
        "PostgresRepositoryRuntime",
        "PostgresPersistenceService",
    )
    for path in _MODULE_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} references forbidden '{forbidden}'"


def test_no_custom_exception_hierarchy_is_defined() -> None:
    for path in _MODULE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = base.id if isinstance(base, ast.Name) else ast.dump(base)
                    assert "Error" not in base_name and "Exception" not in base_name, (
                        f"{path} defines an exception subclass {node.name} deriving "
                        f"from {base_name}; M029 propagates errors unchanged and "
                        "defines no exception hierarchy"
                    )


def test_no_runtime_protocol_introspection_is_used() -> None:
    forbidden_substrings = ("isinstance(", "runtime_checkable", "getattr(")
    for path in _MODULE_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, (
                f"{path} performs runtime Protocol introspection via '{forbidden}'"
            )


def test_no_handler_registry_or_discovery_is_implemented() -> None:
    """No class, function, or variable in the module implements a
    registry, discovery, or service-locator mechanism. Substring matching
    against raw source would false-positive on the docstrings that
    correctly document these mechanisms' absence, so this inspects only
    the identifiers the module actually defines or references."""
    forbidden_fragments = ("registry", "discover", "locator")
    for path in _MODULE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        identifiers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                identifiers.add(node.name)
            elif isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
        lowered = {identifier.lower() for identifier in identifiers}
        for forbidden in forbidden_fragments:
            assert not any(forbidden in identifier for identifier in lowered), (
                f"{path} defines or references an identifier containing '{forbidden}'"
            )


def test_invocation_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(CommandEntryPoint.__call__)
    assert not inspect.iscoroutinefunction(QueryEntryPoint.__call__)
    for path in _MODULE_FILES:
        source = path.read_text(encoding="utf-8")
        assert "async def" not in source
        assert "await " not in source


def test_command_and_query_entry_points_are_distinct_types() -> None:
    assert CommandEntryPoint is not QueryEntryPoint
    assert not issubclass(CommandEntryPoint, QueryEntryPoint)
    assert not issubclass(QueryEntryPoint, CommandEntryPoint)
