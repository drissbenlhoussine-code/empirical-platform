import ast
from pathlib import Path

import pytest
from tools.check_architecture import ORDER_SUBMISSION_PREFIXES, check_path


def test_current_source_tree_respects_boundaries() -> None:
    assert check_path(Path.cwd()) == []


def test_negative_fixture_detects_illegal_import() -> None:
    fixture_root = Path("tests/fixtures/illegal_imports")
    violations = check_path(fixture_root)
    assert any("review may not import acquisition" in violation for violation in violations)
    assert any("datasets may not import run" in violation for violation in violations)
    assert any("campaign may not import datasets" in violation for violation in violations)
    assert any("campaign may not import run" in violation for violation in violations)
    assert any("run may not import campaign" in violation for violation in violations)
    assert any("evidence may not import run" in violation for violation in violations)
    assert any("review may not import run" in violation for violation in violations)
    assert any(
        "campaign may not import empirical_platform.shared.persistence" in violation
        for violation in violations
    )
    assert any("review may not import sqlalchemy" in violation for violation in violations)
    assert any("campaign may not import boto3" in violation for violation in violations)
    assert any("evidence may not import psycopg" in violation for violation in violations)
    assert any("campaign may not import sqlalchemy" in violation for violation in violations)
    assert any("evidence may not import boto3" in violation for violation in violations)
    assert any("review may not import psycopg" in violation for violation in violations)
    assert any(
        "run may not import empirical_platform.shared.persistence" in violation
        for violation in violations
    )
    assert any("shared may not import audit" in violation for violation in violations)
    assert any(
        "application may not import empirical_platform.shared.persistence" in violation
        for violation in violations
    )
    assert any("application may not import entrypoints" in violation for violation in violations)
    assert any("campaign may not import application" in violation for violation in violations)
    assert any(
        "usecases may not import empirical_platform.shared.persistence" in violation
        for violation in violations
    )
    assert any(
        "usecases may not import "
        "empirical_platform.shared.persistence.postgres_repositories.runtime" in violation
        for violation in violations
    )
    assert any("usecases may not import sqlalchemy" in violation for violation in violations)
    assert any("usecases may not import psycopg" in violation for violation in violations)
    assert any("usecases may not import boto3" in violation for violation in violations)
    assert any("campaign may not import usecases" in violation for violation in violations)
    assert any("run may not import usecases" in violation for violation in violations)
    assert any("evidence may not import usecases" in violation for violation in violations)
    assert any("review may not import usecases" in violation for violation in violations)
    assert any("entrypoints may not import sqlalchemy" in violation for violation in violations)
    assert any("entrypoints may not import psycopg" in violation for violation in violations)
    assert any("entrypoints may not import boto3" in violation for violation in violations)


@pytest.mark.parametrize(
    ("module", "dependency"),
    [
        ("decision_candidate", "alpaca"),
        ("usecases", "ib_insync"),
        ("entrypoints", "alpaca.trading.client"),
        ("application", "quickfix"),
    ],
)
def test_negative_fixture_detects_an_order_submission_dependency(
    module: str, dependency: str
) -> None:
    """MILESTONE-084: order submission must be refused, not merely absent."""
    violations = check_path(Path("tests/fixtures/illegal_imports"))
    expected = f"{module} may not import order-submission dependency {dependency}"
    assert any(expected in violation for violation in violations), expected


def test_no_source_file_imports_an_order_submission_dependency() -> None:
    """Every source file, including the ones `check_path` deliberately skips.

    `module_for_path` ignores `__init__.py` and underscore-prefixed modules, so
    the boundary check alone would leave those as a route by which an order
    client could enter the package. This walks the whole tree.
    """
    source_files = list(Path("src").rglob("*.py"))
    assert source_files, "the source tree must not be empty"

    offenders: list[str] = []
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            offenders.extend(
                f"{path}: {name}"
                for name in names
                for prefix in ORDER_SUBMISSION_PREFIXES
                if name == prefix or name.startswith(f"{prefix}.")
            )
    assert offenders == []
