"""Static module-boundary checker for empirical_platform."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

PACKAGE = "empirical_platform"

ALLOWED: dict[str, set[str]] = {
    "shared": set(),
    "identifiers": {"shared"},
    "registry": {"shared", "identifiers"},
    "governance": {"shared", "identifiers", "registry"},
    "campaign": {"shared", "identifiers", "governance", "registry"},
    "datasets": {"shared", "identifiers", "campaign"},
    "run": {"shared", "identifiers", "datasets"},
    "evidence": {"shared", "identifiers", "datasets", "validation"},
    "acquisition": {"shared", "identifiers", "campaign", "datasets", "evidence"},
    "normalization": {"shared", "identifiers", "datasets", "evidence"},
    "validation": {"shared", "identifiers", "datasets", "normalization", "evidence"},
    "review": {"shared", "identifiers", "evidence"},
    "audit": {"shared", "identifiers", "evidence", "review", "registry"},
    "decision_candidate": {"shared", "identifiers", "audit", "evidence"},
    "archive": {"shared", "identifiers", "evidence", "audit", "decision_candidate"},
    "entrypoints": {"shared"},
}

ALLOWED_EXACT_IMPORTS: dict[str, set[str]] = {
    "run": {"empirical_platform.campaign.lifecycle"},
}

FORBIDDEN_IMPORT_PREFIXES: dict[str, tuple[str, ...]] = {
    "campaign": (
        "empirical_platform.shared.persistence",
        "sqlalchemy",
        "psycopg",
        "boto3",
    ),
    "run": (
        "empirical_platform.shared.persistence",
        "sqlalchemy",
        "psycopg",
        "boto3",
    ),
    "evidence": (
        "empirical_platform.shared.persistence",
        "sqlalchemy",
        "psycopg",
        "boto3",
    ),
    "review": (
        "empirical_platform.shared.persistence",
        "sqlalchemy",
        "psycopg",
        "boto3",
    ),
    "shared": (
        "empirical_platform.shared.persistence",
        "sqlalchemy",
        "psycopg",
        "boto3",
    ),
}


def module_for_path(path: Path, root: Path) -> str | None:
    """Return the top-level empirical_platform module for a file."""
    relative = path.relative_to(root)
    parts = relative.parts
    if len(parts) < 3 or parts[0] != "src" or parts[1] != PACKAGE:
        return None
    if parts[2] == "__init__.py" or parts[2].startswith("_"):
        return None
    return parts[2]


def imported_module(node: ast.AST) -> str | None:
    """Return imported empirical_platform module if present."""
    name: str | None = None
    if isinstance(node, ast.ImportFrom):
        name = node.module
    elif isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
        name = next((candidate for candidate in names if candidate.startswith(PACKAGE)), None)
    if not name or not name.startswith(f"{PACKAGE}."):
        return None
    return name


def imported_top_level(node: ast.AST) -> str | None:
    """Return imported empirical_platform top-level module if present."""
    name = imported_module(node)
    if name is None:
        return None
    parts = name.split(".")
    if len(parts) > 1 and parts[1].startswith("_"):
        return None
    return parts[1] if len(parts) > 1 else None


def check_path(root: Path) -> list[str]:
    """Return architecture violations for Python files below root."""
    violations: list[str] = []
    for path in root.rglob("*.py"):
        source_module = module_for_path(path, root)
        if source_module is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        allowed = ALLOWED.get(source_module, set())
        allowed_exact = ALLOWED_EXACT_IMPORTS.get(source_module, set())
        for node in ast.walk(tree):
            imported_name = imported_module(node)
            raw_imported_name = imported_name
            if raw_imported_name is None and isinstance(node, ast.Import):
                raw_imported_name = next((alias.name for alias in node.names), None)
            elif raw_imported_name is None and isinstance(node, ast.ImportFrom):
                raw_imported_name = node.module
            forbidden_prefixes = FORBIDDEN_IMPORT_PREFIXES.get(source_module, ())
            if source_module == "shared" and "domain" not in path.parts:
                forbidden_prefixes = ()
            if raw_imported_name is not None and any(
                raw_imported_name == forbidden or raw_imported_name.startswith(f"{forbidden}.")
                for forbidden in forbidden_prefixes
            ):
                violations.append(f"{path}: {source_module} may not import {raw_imported_name}")
                continue
            imported = imported_top_level(node)
            if imported is None or imported == source_module:
                continue
            if imported_name in allowed_exact:
                continue
            if imported not in allowed:
                violations.append(f"{path}: {source_module} may not import {imported}")
    return violations


def main() -> int:
    """Run architecture validation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    violations = check_path(Path(args.root).resolve())
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
