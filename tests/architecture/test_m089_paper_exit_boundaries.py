"""MILESTONE-089 -- Store C's boundaries, parsed from its source.

Store C (the PAPER exit-lifecycle database) runs its own self-contained Alembic chain that
can never apply the M082-M087 migrations or be applied by `migrations/`'s own chain; its
schema-head guard checks ONLY Store C's revision, never Store A's or Store B's; its migration
creates no cross-database trigger and never names `paper_execution_attempt`; its composition
module reuses M087's Postgres repository classes UNCHANGED rather than duplicating them, and
never modifies or is imported by MILESTONE-088's own `_paper_operator_console_composition.py`
(`paper_operator_console_runtime`, the function serving the stable, already-deployed M088
console, must have zero source-level dependency on this milestone's additions beyond the two
names it deliberately exports and this milestone imports: `PAPER_CAPABILITY`,
`PaperConsoleBackend`).

Checks that must not trip on this milestone's OWN prose (a docstring explaining what a file
deliberately does NOT do necessarily names the thing it does not do) run against the source
with its module docstring stripped, never the raw file text.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path("src/empirical_platform")
STORE_C_SCHEMA = (
    ROOT / "shared" / "persistence" / "postgres_repositories" / "paper_position_exit_schema.py"
)
STORE_C_COMPOSITION = ROOT / "entrypoints" / "_paper_position_exit_composition.py"
M088_COMPOSITION = ROOT / "entrypoints" / "_paper_operator_console_composition.py"
M087_POSTGRES_REPOS = (
    ROOT / "shared" / "persistence" / "postgres_repositories" / "position_exit_repositories.py"
)
STORE_C_MIGRATION = Path(
    "migrations_paper_exit/versions/f083b6c29d17_create_m089_paper_exit_schema.py"
)
STORE_C_ALEMBIC_ENV = Path("migrations_paper_exit/env.py")
STORE_C_INI = Path("alembic_paper_exit.ini")
MASTER_INI = Path("alembic.ini")


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


def _imported_names_from(path: Path, module_suffix: str) -> set[str]:
    """The exact names bound by `from ...module_suffix import a, b` in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(module_suffix):
            bound.update(alias.asname or alias.name for alias in node.names)
    return bound


def _code_only(path: Path) -> str:
    """The source with its module docstring removed, so prose cannot trip a code-only check."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        lines = text.splitlines(keepends=True)
        return "".join(lines[tree.body[0].end_lineno :])
    return text


def test_store_c_migration_chain_is_self_contained() -> None:
    """`down_revision = None`: this chain can never apply, or be applied after, M082-M087."""
    source = STORE_C_MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "f083b6c2" + "9d17"' in source
    assert "down_revision: str | None = None" in source


def test_store_c_migration_never_names_the_m085_entry_table_in_code() -> None:
    """The one property this whole design exists to prove: no local FK/trigger dependency.

    A comment MAY explain the table's absence by naming it (and does); no SQL fragment this
    file executes may reference it as a real object -- no `FROM public.paper_execution_attempt`
    and no `REFERENCES ... paper_execution_attempt`.
    """
    code = _code_only(STORE_C_MIGRATION)
    assert "FROM public.paper_execution_attempt" not in code
    assert not any(
        "REFERENCES" in line and "paper_execution_attempt" in line for line in code.splitlines()
    )
    assert "position_exit_preview_guard_insert" not in code
    assert "environment = 'PAPER'" in code
    assert "environment = 'SIMULATION'" not in code


def test_store_c_ini_points_at_its_own_script_location_never_the_master_chain() -> None:
    ini_text = STORE_C_INI.read_text(encoding="utf-8")
    assert "script_location = migrations_paper_exit" in ini_text
    master_text = MASTER_INI.read_text(encoding="utf-8")
    assert "script_location = migrations" in master_text
    assert "migrations_paper_exit" not in master_text


def test_store_c_alembic_env_resolves_a_distinct_database_variable() -> None:
    source = STORE_C_ALEMBIC_ENV.read_text(encoding="utf-8")
    assert '_DATABASE_VARIABLE = "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE"' in source
    names = _imports(STORE_C_ALEMBIC_ENV)
    assert "empirical_platform.shared.config.settings.resolve_foundation_config" in names
    # This environment does not import the OTHER one: two independent scripts, never one
    # importing the other's `run_migrations_online`/`run_migrations_offline`.
    assert "migrations.env" not in names


def test_store_c_schema_head_guard_checks_only_store_c() -> None:
    from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
        M085_SCHEMA_HEAD,
    )
    from empirical_platform.shared.persistence.postgres_repositories.paper_position_exit_schema import (  # noqa: E501
        M089_SCHEMA_HEAD,
    )
    from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
        M087_SCHEMA_HEAD,
    )

    assert M089_SCHEMA_HEAD not in (M085_SCHEMA_HEAD, M087_SCHEMA_HEAD)
    code = _code_only(STORE_C_SCHEMA)
    assert "require_exact_m085_schema_head" not in code
    assert "require_exact_m087_schema_head" not in code
    names = _imports(STORE_C_SCHEMA)
    assert not any(n.startswith("empirical_platform.decision_candidate") for n in names)


def test_store_c_composition_reuses_the_m087_postgres_repositories_unmodified() -> None:
    """No second `PostgresPositionExit*Repository` class family exists for Store C."""
    names = _imports(STORE_C_COMPOSITION)
    assert (
        "empirical_platform.shared.persistence.postgres_repositories."
        "position_exit_repositories.PostgresPositionExitRuntime" in names
    )
    repo_source = M087_POSTGRES_REPOS.read_text(encoding="utf-8")
    assert repo_source.count("class PostgresPositionExit") == 7  # 6 repositories + the runtime
    composition_source = STORE_C_COMPOSITION.read_text(encoding="utf-8")
    assert "class Postgres" not in composition_source


def test_store_c_composition_does_not_modify_or_widen_the_m088_console_runtime() -> None:
    """`paper_operator_console_runtime` (M088's own function) is imported, never redefined."""
    composition_source = STORE_C_COMPOSITION.read_text(encoding="utf-8")
    assert "def paper_operator_console_runtime(" not in composition_source
    imported = _imported_names_from(STORE_C_COMPOSITION, "_paper_operator_console_composition")
    assert imported == {"PAPER_CAPABILITY", "PaperConsoleBackend"}


def test_m088_composition_has_no_source_dependency_on_m089() -> None:
    """The file serving the stable, already-deployed M088 console is untouched by this work."""
    source = M088_COMPOSITION.read_text(encoding="utf-8")
    assert "paper_position_exit" not in source
    assert "Store C" not in source
    assert "MILESTONE-089" not in source


def test_store_c_composition_names_a_distinct_database_environment_variable() -> None:
    code = _code_only(STORE_C_COMPOSITION)
    assert 'PAPER_EXIT_DATABASE_VARIABLE = "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE"' in (
        code
    )
    # Store B's own database-name variable is read only indirectly, through
    # `resolve_foundation_config()`; it is never spelled out as a literal here.
    assert '"EMPIRICAL_PLATFORM_POSTGRES_DATABASE"' not in code


@pytest.mark.parametrize("path", (STORE_C_COMPOSITION, STORE_C_SCHEMA), ids=lambda p: p.name)
def test_store_c_modules_never_import_the_alpaca_client_directly(path: Path) -> None:
    names = _imports(path)
    for forbidden in (
        "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperClient",
        "empirical_platform.shared.brokerage.alpaca_paper.AlpacaPaperMarketDataClient",
    ):
        assert forbidden not in names, (path.name, forbidden)
