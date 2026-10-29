"""Read-only paired pg_dump backups. Never restores or initializes a database.

An INITIALIZED identity manifest is mandatory. LOSS_DETECTED stops rotation so
an empty replacement cannot evict recoverable history. Restore rehearsal is a
separate, explicitly operated procedure on disposable databases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine

from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.shared.persistence.database_safety import (
    IDENTITY_QUERY,
    DatabaseSafetyError,
    manifest_path,
    read_manifest,
)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run_pg(arguments: list[str], environment: dict[str, str]) -> str:
    result = subprocess.run(  # noqa: S603 - explicit executable and argument vector, no shell
        arguments, env=environment, capture_output=True, text=True, timeout=600, check=False
    )
    if result.returncode:
        # Do not echo libpq diagnostics: an invalid environment can contain credentials.
        raise DatabaseSafetyError(f"{Path(arguments[0]).stem} failed; backup not committed")
    return result.stdout


def pg_executable(pg_bin: Path, name: str) -> Path:
    # Debian's pg_dump/pg_restore symlinks share pg_wrapper, which dispatches by
    # argv[0]. Resolving the final symlink destroys that dispatch information.
    suffix = ".exe" if os.name == "nt" else ""
    executable = pg_bin.absolute() / (name + suffix)
    if not executable.is_file():
        raise DatabaseSafetyError("required PostgreSQL executable is missing")
    return executable


def rotate(root: Path, keep: int) -> None:
    """Only this tool's complete, hash-verified sets can be removed; unknown files stay."""
    complete = []
    for candidate in root.iterdir():
        if not candidate.is_dir() or candidate.is_symlink() or candidate.is_junction():
            continue
        try:
            data = json.loads((candidate / "complete.json").read_text(encoding="utf-8"))
            if data["kind"] != "PERSONAL_PAPER_BACKUP" or set(data["files"]) != {"B", "C"}:
                continue
            if set(p.name for p in candidate.iterdir()) != {"B.dump", "C.dump", "complete.json"}:
                continue
            if not all(
                not (candidate / f"{store}.dump").is_symlink()
                and digest(candidate / f"{store}.dump") == data["files"][store]["sha256"]
                for store in ("B", "C")
            ):
                continue
            complete.append(candidate)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for candidate in sorted(complete, reverse=True)[keep:]:
        # Resolve every deletion target and ensure it is immediately under the chosen root.
        if candidate.resolve().parent != root.resolve():
            raise DatabaseSafetyError("backup retention target escaped backup root")
        shutil.rmtree(candidate)


def backup(identity_path: Path, root: Path, pg_bin: Path, keep: int = 168) -> Path:
    if keep < 2:
        raise DatabaseSafetyError("retention must keep at least two complete backup sets")
    manifest = read_manifest(identity_path)
    if manifest["state"] != "INITIALIZED":
        raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: backup and retention blocked")
    config = resolve_foundation_config().postgresql
    if (config.host, config.port) != (manifest["host"], manifest["port"]):
        raise DatabaseSafetyError("backup endpoint differs from PERSONAL_PAPER identity")
    dump = pg_executable(pg_bin, "pg_dump")
    restore = pg_executable(pg_bin, "pg_restore")
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".backup.lock"
    try:
        lock_descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise DatabaseSafetyError(
            "backup already active or stale lock requires investigation"
        ) from error
    os.close(lock_descriptor)
    try:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
        staging = root / (stamp + ".partial")
        staging.mkdir()
        files = {}
        # No credentials in command lines, reports or manifests; child environment only.
        environment = dict(os.environ)
        environment.update(
            PGHOST=config.host,
            PGPORT=str(config.port),
            PGUSER=config.user,
            PGPASSWORD=config.password.get_secret_value() if config.password else "",
            PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=300000",
            PGCONNECT_TIMEOUT="10",
        )
        for store in ("B", "C"):
            expected = manifest["stores"][store]
            engine = create_engine(
                config.model_copy(update={"database": expected["database"]}).sqlalchemy_url(),
                connect_args={"options": environment["PGOPTIONS"]},
            )
            try:
                # Snapshot validation and pg_dump must see the SAME state, even under writes.
                with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
                    row = conn.exec_driver_sql(IDENTITY_QUERY).mappings().one()
                    if row["identity"] != expected["identity"]:
                        raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: identity mismatch")
                    heads = (
                        conn.exec_driver_sql("SELECT version_num FROM public.alembic_version")
                        .scalars()
                        .all()
                    )
                    if heads != [expected["head"]]:
                        raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: revision mismatch")
                    query = (
                        "SELECT count(*) FROM public.paper_execution_attempt"
                        if store == "B"
                        else "SELECT count(*) FROM public.position_exit_attempt"
                    )
                    attempts = conn.exec_driver_sql(query).scalar_one()
                    if attempts < expected["minimum_attempts"]:
                        raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: history shrank")
                    snapshot = conn.exec_driver_sql("SELECT pg_export_snapshot()").scalar_one()
                    archive = staging / f"{store}.dump"
                    run_pg(
                        [
                            str(dump),
                            "--format=custom",
                            "--no-password",
                            "--lock-wait-timeout=30s",
                            "--snapshot=" + snapshot,
                            "--file=" + str(archive),
                            expected["database"],
                        ],
                        environment,
                    )
                    listing = run_pg([str(restore), "--list", str(archive)], environment)
                    if "alembic_version" not in listing:
                        raise DatabaseSafetyError(
                            "archive validation failed: migration table absent"
                        )
                    files[store] = {
                        "database": expected["database"],
                        "identity": expected["identity"],
                        "head": expected["head"],
                        "attempts": attempts,
                        "sha256": digest(archive),
                    }
            finally:
                engine.dispose()
        atomic_json(
            staging / "complete.json",
            {
                "kind": "PERSONAL_PAPER_BACKUP",
                "created_utc": stamp,
                "files": files,
                "consistency": "per-store snapshot; restore requires cross-store reconciliation",
            },
        )
        completed = root / stamp
        staging.rename(completed)
        for store in ("B", "C"):
            manifest["stores"][store]["minimum_attempts"] = files[store]["attempts"]
        atomic_json(identity_path, manifest)
        rotate(root, keep)
        return completed
    finally:
        lock.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=manifest_path())
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--pg-bin", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=168)
    args = parser.parse_args()
    try:
        result = backup(args.manifest, args.root, args.pg_bin, args.keep)
        print(f"BACKUP_COMPLETE {result}")
        return 0
    except Exception:
        # Explicit loss detection remains visible; no raw database/credential exceptions.
        print("BACKUP_BLOCKED: verify identity, loss state, credentials, binaries and free space")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
