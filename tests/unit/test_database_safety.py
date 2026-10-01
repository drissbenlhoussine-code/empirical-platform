"""Database loss and hostile target selection fail before runtime or DDL."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from tools import personal_paper_backup as backups

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence import database_safety as safety


@pytest.fixture
def identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    path = tmp_path / "identity.json"
    monkeypatch.setattr(safety, "manifest_path", lambda: path)
    data = {
        "kind": "PERSONAL_PAPER",
        "version": 1,
        "host": "localhost",
        "port": 55433,
        "state": "INITIALIZED",
        "stores": {
            store: {
                "database": name,
                "identity": f"PERSONAL_PAPER:{store}:test-identity",
                "head": "reviewed-head",
                "minimum_attempts": 2,
            }
            for store, name in zip(("B", "C"), sorted(safety.PERSONAL_DATABASES), strict=True)
        },
    }
    path.write_text(json.dumps(data))
    return path, data


@pytest.mark.parametrize(
    "database,port,mode",
    [
        ("empirical_platform_paper", 5432, "TEST"),
        ("empirical_platform_paper_exit", 5432, "TEST"),
        ("disposable_test", 55433, "TEST"),
        ("disposable_test", 5432, "PERSONAL_PAPER"),
        ("looks_disposable", 5432, "TEST"),
    ],
)
def test_unsafe_test_target_refused_before_connect(
    monkeypatch: pytest.MonkeyPatch, database: str, port: int, mode: str
) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_DATABASE_MODE", mode)
    with pytest.raises(safety.DatabaseSafetyError):
        safety._before_test_connect(
            SimpleNamespace(name="postgresql"), None, [], {"dbname": database, "port": port}
        )


def test_explicit_isolated_target_and_non_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_DATABASE_MODE", "TEST")
    safety.require_test_target("disposable_test", 55436)
    safety._before_test_connect(SimpleNamespace(name="sqlite"), None, [], {})
    with create_engine("sqlite://").connect() as connection:
        safety._test_connection(connection)


def test_external_registry_protects_renamed_personal_store(
    identity: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    path, data = identity
    data["stores"]["B"]["database"] = "renamed_test"
    path.write_text(json.dumps(data))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_DATABASE_MODE", "TEST")
    with pytest.raises(safety.DatabaseSafetyError, match="PERSONAL_PAPER"):
        safety.require_test_target("renamed_test", 55436)


@pytest.mark.parametrize("mutation", ["missing", "broken", "wrong_kind", "wrong_store", "negative"])
def test_invalid_registry_fails_closed(
    identity: tuple[Path, dict[str, Any]], mutation: str
) -> None:
    path, data = identity
    if mutation == "missing":
        path.unlink()
    elif mutation == "broken":
        path.write_text("{")
    else:
        if mutation == "wrong_kind":
            data["kind"] = "TEST"
        elif mutation == "wrong_store":
            data["stores"].pop("C")
        else:
            data["stores"]["B"]["minimum_attempts"] = -1
        path.write_text(json.dumps(data))
    with pytest.raises(safety.DatabaseSafetyError):
        safety.read_manifest(path)


class Service:
    def __init__(
        self, identity: str | None, head: str | None = "reviewed-head", count: int = 2
    ) -> None:
        self.identity, self.head, self.count = identity, head, count
        self.queries = []

    @contextmanager
    def unit_of_work(self) -> Iterator[Service]:
        yield self

    def execute(self, query: str) -> list[dict[str, object]]:
        self.queries.append(query)
        if query == safety.IDENTITY_QUERY:
            return [{"identity": self.identity}]
        if "alembic_version" in query:
            if self.head is None:
                raise RuntimeError("missing table")
            return [{"version_num": self.head}]
        return [{"count": self.count}]


@pytest.mark.parametrize("store", ["B", "C"])
@pytest.mark.parametrize("failure", [None, "identity", "head", "history", "missing", "loss"])
def test_startup_loss_detection(
    identity: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    store: str,
    failure: str | None,
) -> None:
    path, data = identity
    monkeypatch.delenv("EMPIRICAL_PLATFORM_DATABASE_MODE", raising=False)
    expected = data["stores"][store]
    config = PostgreSQLConfigSnapshot(database=expected["database"], port=55433)
    service = Service(expected["identity"])
    if failure == "identity":
        service.identity = None
    if failure == "head":
        service.head = "unreviewed"
    if failure == "missing":
        service.head = None
    if failure == "history":
        service.count = 1
    if failure == "loss":
        data["state"] = "LOSS_DETECTED"
        path.write_text(json.dumps(data))
    if failure:
        with pytest.raises(safety.DatabaseSafetyError, match="LOSS_DETECTED"):
            safety.require_personal_identity(service, config, store=store)
    else:
        safety.require_personal_identity(service, config, store=store)
        assert len(service.queries) == 3


def test_test_runtime_requires_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_DATABASE_MODE", "TEST")
    config = PostgreSQLConfigSnapshot(database="isolated_test", port=55436)
    with pytest.raises(safety.DatabaseSafetyError, match="identity"):
        safety.require_personal_identity(Service(None), config, store="B")
    safety.require_personal_identity(Service(safety.TEST_IDENTITY), config, store="B")


def test_online_personal_migration_refused() -> None:
    with pytest.raises(safety.DatabaseSafetyError, match="migration refused"):
        safety.refuse_unplanned_personal_migration(
            PostgreSQLConfigSnapshot(database="empirical_platform_paper")
        )


def test_loss_blocks_backup_and_retention(
    identity: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    path, data = identity
    data["state"] = "LOSS_DETECTED"
    path.write_text(json.dumps(data))
    with pytest.raises(safety.DatabaseSafetyError, match="LOSS_DETECTED"):
        backups.backup(path, tmp_path / "backups", tmp_path)
    assert not (tmp_path / "backups").exists()


def test_retention_preserves_unknown_incomplete_and_corrupt_sets(tmp_path: Path) -> None:
    for name in ("001", "002", "003", "004"):
        directory = tmp_path / name
        directory.mkdir()
        files = {}
        for store in ("B", "C"):
            archive = directory / f"{store}.dump"
            archive.write_bytes(b"archive-test")
            files[store] = {"sha256": backups.digest(archive)}
        backups.atomic_json(
            directory / "complete.json",
            {
                "kind": "PERSONAL_PAPER_BACKUP",
                "files": files,
            },
        )
    (tmp_path / "004" / "B.dump").write_bytes(b"corrupted")
    (tmp_path / "005.partial").mkdir()
    (tmp_path / "unknown").mkdir()
    backups.rotate(tmp_path, 2)
    assert not (tmp_path / "001").exists()
    assert all(
        (tmp_path / name).exists() for name in ("002", "003", "004", "005.partial", "unknown")
    )


def test_pg_failure_does_not_expose_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backups.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="sensitive-diagnostic", stdout=""),
    )
    with pytest.raises(safety.DatabaseSafetyError) as error:
        backups.run_pg(["pg_dump"], {})
    assert "sensitive-diagnostic" not in str(error.value)


@pytest.mark.parametrize("marker", [None, "PERSONAL_PAPER:B:renamed", safety.TEST_IDENTITY])
def test_database_identity_independent_of_test_name(
    marker: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_DATABASE_MODE", "TEST")
    connection = MagicMock()
    connection.engine.url.database = "disposable_test"
    connection.engine.url.port = 55436
    connection.dialect.name = "postgresql"
    connection.exec_driver_sql.return_value.mappings.return_value.one.return_value = {
        "identity": marker
    }
    if marker == safety.TEST_IDENTITY:
        safety._test_connection(connection)
        connection.rollback.assert_called_once()
        safety.require_migration_connection(connection)
    else:
        with pytest.raises(safety.DatabaseSafetyError):
            safety._test_connection(connection)
        with pytest.raises(safety.DatabaseSafetyError):
            safety.require_migration_connection(connection)


def test_no_implicit_port_or_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMPIRICAL_PLATFORM_DATABASE_MODE", raising=False)
    with pytest.raises(safety.DatabaseSafetyError, match="explicit PostgreSQL test port"):
        safety.require_test_target("valid_test", None)
    with pytest.raises(safety.DatabaseSafetyError, match="DATABASE_MODE"):
        safety.require_test_target("valid_test", 55436)


def test_postgres_wrapper_keeps_dispatch_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "is_file", lambda path: path.name in {"pg_dump", "pg_dump.exe"})
    executable = backups.pg_executable(tmp_path, "pg_dump")
    assert executable.stem == "pg_dump"
    with pytest.raises(safety.DatabaseSafetyError, match="missing"):
        backups.pg_executable(tmp_path, "pg_restore")
