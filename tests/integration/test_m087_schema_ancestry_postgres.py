"""MILESTONE-087 -- machine-checkable proof that the M087 migration is an additive descendant.

Before/after catalogs of every M085-owned object (tables, columns, constraints, indexes,
triggers, trigger function definitions and the transition enforcement inside them) at the M085
head, after upgrading to the M087 head, and after downgrading back: byte-identical. And the M085
migration FILES are byte-identical to the published M085 head (sha256 manifest recorded from
commit 54ae23c), so nothing was inserted into or replaced inside M085's history.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import alembic_config, build_engine

from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    M085_SCHEMA_HEAD,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    M087_SCHEMA_HEAD,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "external-review" / "MILESTONE-087" / "m085-migration-manifest.sha256"

#: M085-owned (and earlier) object name prefixes. Everything the M087 migration may not touch.
_M085_TABLE_PREFIXES = ("paper_",)
_M085_FUNCTION_PREFIXES = ("paper_", "m085_")


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    # Built at the M085 head on purpose: the catalog is captured BEFORE M087 exists.
    yield from build_engine(M085_SCHEMA_HEAD)


def _catalog(engine: Engine) -> dict[str, Any]:
    """Every M085-owned object, in a deterministic, comparable shape."""
    with engine.begin() as connection:
        tables = sorted(
            r[0]
            for r in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
            if r[0].startswith(_M085_TABLE_PREFIXES)
        )
        columns = connection.execute(
            text(
                "SELECT table_name, column_name, data_type, is_nullable, column_default, "
                "numeric_precision, numeric_scale, character_maximum_length "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position"
            )
        ).all()
        constraints = connection.execute(
            text(
                "SELECT c.conrelid::regclass::text AS table_name, c.conname, "
                "pg_get_constraintdef(c.oid) AS definition "
                "FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = 'public' ORDER BY 1, 2"
            )
        ).all()
        indexes = connection.execute(
            text(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' ORDER BY tablename, indexname"
            )
        ).all()
        triggers = connection.execute(
            text(
                "SELECT c.relname AS table_name, t.tgname, pg_get_triggerdef(t.oid) AS definition "
                "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND NOT t.tgisinternal ORDER BY 1, 2"
            )
        ).all()
        functions = connection.execute(
            text(
                "SELECT p.proname, pg_get_functiondef(p.oid) AS definition "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' ORDER BY p.proname"
            )
        ).all()
    m085_tables = set(tables)
    return {
        "tables": tables,
        "columns": [tuple(map(str, r)) for r in columns if r[0] in m085_tables],
        "constraints": [tuple(map(str, r)) for r in constraints if r[0] in m085_tables],
        "indexes": [tuple(map(str, r)) for r in indexes if r[0] in m085_tables],
        "triggers": [tuple(map(str, r)) for r in triggers if r[0] in m085_tables],
        "functions": [
            tuple(map(str, r)) for r in functions if r[0].startswith(_M085_FUNCTION_PREFIXES)
        ],
    }


def _head(engine: Engine) -> str:
    with engine.begin() as connection:
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def test_m087_adds_objects_and_leaves_every_m085_object_byte_identical(engine: Engine) -> None:
    assert _head(engine) == M085_SCHEMA_HEAD
    before = _catalog(engine)
    assert before["tables"] and before["functions"]  # the M085 schema is really there
    assert "paper_execution_attempt" in before["tables"]
    attempt_guard = next(
        d for name, d in before["functions"] if name == "paper_execution_attempt_guard_update"
    )
    assert "is not an allowed paper execution transition" in attempt_guard

    alembic_command.upgrade(alembic_config(), M087_SCHEMA_HEAD)
    try:
        assert _head(engine) == M087_SCHEMA_HEAD
        after = _catalog(engine)
        assert after == before, "an M085-owned object changed under the M087 migration"
        with engine.begin() as connection:
            all_tables = {
                r[0]
                for r in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).all()
            }
            all_functions = {
                r[0]
                for r in connection.execute(
                    text(
                        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n "
                        "ON n.oid = p.pronamespace WHERE n.nspname = 'public'"
                    )
                ).all()
            }
        added_tables = sorted(all_tables - set(before["tables"]) - _non_m085_tables(engine))
        assert added_tables == [
            "position_exit_acknowledgement",
            "position_exit_attempt",
            "position_exit_authorization",
            "position_exit_event",
            "position_exit_preview",
            "position_exit_reconciliation_round",
        ]
        m087_functions = sorted(
            f for f in all_functions if f.startswith(("position_exit_", "m087_"))
        )
        assert m087_functions == [
            "m087_append_only",
            "position_exit_attempt_guard_insert",
            "position_exit_attempt_guard_update",
            "position_exit_authorization_guard_insert",
            "position_exit_authorization_guard_update",
            "position_exit_preview_guard_insert",
            "position_exit_round_guard_insert",
            "position_exit_round_guard_update",
        ]
        # No M087 object is a foreign key INTO an M085 table: the link to the entry is a
        # BEFORE INSERT guard that reads `paper_execution_attempt`, never a constraint on it.
        with engine.begin() as connection:
            foreign_keys_into_m085 = connection.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class r ON r.oid = c.conrelid JOIN pg_class f ON f.oid = c.confrelid "
                    "WHERE c.contype = 'f' AND r.relname LIKE 'position_exit_%' "
                    "AND f.relname LIKE 'paper_%'"
                )
            ).all()
        assert foreign_keys_into_m085 == []
    finally:
        alembic_command.downgrade(alembic_config(), M085_SCHEMA_HEAD)
    assert _head(engine) == M085_SCHEMA_HEAD
    assert _catalog(engine) == before, "an M085-owned object changed under the M087 downgrade"


def _non_m085_tables(engine: Engine) -> set[str]:
    """Tables of milestones before M085 (and alembic's own), so the added set is exactly M087's."""
    with engine.begin() as connection:
        return {
            r[0]
            for r in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
            if not r[0].startswith(("paper_", "position_exit_"))
        }


def _read_manifest(path: Path) -> dict[str, str]:
    """sha256sum format (`<digest> *<path>`) after comment lines, as the repository's manifests."""
    recorded: dict[str, str] = {}
    header: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            header.append(line)
            continue
        digest, _, name = line.partition(" *")
        recorded[name] = digest
    assert any("54ae23c" in h for h in header), "the manifest must name the M085 head commit"
    return recorded


def test_the_m085_migration_files_are_byte_identical_to_the_published_m085_head() -> None:
    recorded = _read_manifest(MANIFEST)
    assert len(recorded) == 26
    for path, digest in recorded.items():
        current = (REPO_ROOT / path).read_bytes()
        assert hashlib.sha256(current).hexdigest() == digest, f"{path} differs from the M085 head"
    present = sorted(
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "migrations" / "versions").glob("*.py")
    )
    added = sorted(set(present) - set(recorded))
    # MILESTONE-090 and RELEASE v1 pinned: their own additive migrations are now also
    # present beyond the M085 manifest, alongside M087's. All three are KNOWN,
    # accounted-for additions; nothing else is.
    assert added == [
        "migrations/versions/a2b4c6d8e0f2_create_m090_opportunity_engine_schema.py",
        "migrations/versions/b9f2c4d6a8e1_create_v1_approved_plan_schema.py",
        "migrations/versions/e7c1a9d3b5f2_create_m087_position_exit_schema.py",
    ]
    assert not (set(recorded) - set(present))  # nothing removed
