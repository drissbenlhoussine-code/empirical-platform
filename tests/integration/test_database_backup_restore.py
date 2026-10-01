"""Real dump/restore and retention rehearsal on explicit disposable PostgreSQL only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.shared.persistence.database_safety import (
    IDENTITY_QUERY,
    TEST_IDENTITY,
    require_test_target,
)


@pytest.mark.integration
def test_real_dump_restore_retention_and_loss_refusal(tmp_path: Path) -> None:
    if os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("explicit isolated PostgreSQL opt-in required")
    config = resolve_foundation_config().postgresql
    require_test_target(config.database, config.port)
    executable = shutil.which("pg_dump")
    if not executable:
        pytest.fail("pg_dump must be installed for the backup rehearsal")
    pg_bin = Path(executable).parent
    password = config.password.get_secret_value() if config.password else ""
    parameters = {
        "host": config.host,
        "port": config.port,
        "user": config.user,
        "password": password,
        "autocommit": True,
    }
    token = uuid4().hex[:10]
    sources = {store: f"safety_{token}_{store.lower()}_test" for store in ("B", "C")}
    targets = {store: f"restore_{token}_{store.lower()}_test" for store in ("B", "C")}
    manifest = {
        "kind": "PERSONAL_PAPER",
        "version": 1,
        "state": "INITIALIZED",
        "host": config.host,
        "port": config.port,
        "stores": {
            store: {
                "database": sources[store],
                "identity": f"PERSONAL_PAPER:{store}:{token}",
                "head": "backup-fixture",
                "minimum_attempts": 3,
            }
            for store in ("B", "C")
        },
    }
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(manifest))
    root = tmp_path / "backups"
    created = []
    with psycopg.connect(dbname=config.database, **parameters) as admin:
        assert admin.execute(IDENTITY_QUERY).fetchone()[1] == TEST_IDENTITY
        try:
            for name in (*sources.values(), *targets.values()):
                require_test_target(name, config.port)
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            for store, name in sources.items():
                with psycopg.connect(dbname=name, **parameters) as conn:
                    conn.execute(
                        sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                            sql.Identifier(name), sql.Literal(manifest["stores"][store]["identity"])
                        )
                    )
                    conn.execute("CREATE TABLE alembic_version(version_num text)")
                    conn.execute("INSERT INTO alembic_version VALUES ('backup-fixture')")
                    table = "paper_execution_attempt" if store == "B" else "position_exit_attempt"
                    conn.execute(
                        sql.SQL("CREATE TABLE {} (id integer PRIMARY KEY)").format(
                            sql.Identifier(table)
                        )
                    )
                    conn.execute(
                        sql.SQL("INSERT INTO {} VALUES (1),(2),(3)").format(sql.Identifier(table))
                    )
            command = [
                sys.executable,
                "tools/personal_paper_backup.py",
                "--manifest",
                str(identity_path),
                "--root",
                str(root),
                "--pg-bin",
                str(pg_bin),
                "--keep",
                "2",
            ]
            for _ in range(3):
                result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
                assert result.returncode == 0, result.stdout
            sets = sorted(p for p in root.iterdir() if (p / "complete.json").exists())
            assert len(sets) == 2
            environment = dict(
                os.environ,
                PGHOST=config.host,
                PGPORT=str(config.port),
                PGUSER=config.user,
                PGPASSWORD=password,
            )
            for store, name in targets.items():
                result = subprocess.run(  # noqa: S603 - fixed vector, isolated database
                    [
                        str(pg_bin / ("pg_restore.exe" if os.name == "nt" else "pg_restore")),
                        "--no-password",
                        "--exit-on-error",
                        "--dbname=" + name,
                        str(sets[-1] / f"{store}.dump"),
                    ],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert result.returncode == 0, "restore rehearsal failed"
                with psycopg.connect(dbname=name, **parameters) as conn:
                    table = "paper_execution_attempt" if store == "B" else "position_exit_attempt"
                    assert (
                        conn.execute(
                            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                        ).fetchone()[0]
                        == 3
                    )
            with psycopg.connect(dbname=sources["C"], **parameters) as conn:
                conn.execute("DELETE FROM position_exit_attempt WHERE id = 3")
            result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
            assert result.returncode == 2
            assert all(p.exists() for p in sets), "failed backup must never rotate good sets"
        finally:
            for name in reversed(created):
                require_test_target(name, config.port)
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
