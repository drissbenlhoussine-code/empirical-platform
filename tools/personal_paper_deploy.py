"""Fail-closed, checkpointed deployment procedure for PR #40 + PR #41 into PERSONAL_PAPER.

WHAT THIS IS. A reviewed, auditable, 14-step deployment procedure (`STEP_ORDER` below) that:
  1-2. confirms the real broker is flat and nothing is in flight,
  3.   confirms the release worktree is exactly the approved, clean commit,
  4.   takes a fresh, hash-verified, structurally-verified Store B/C backup,
  5-6. gracefully stops the running console and confirms it actually stopped,
  7-9. applies the ONE pending Store B migration (f3a7c9e2b164) via the reviewed offline SQL
       in `personal_paper_deploy_migration_f3a7c9e2b164.sql`, then verifies the new schema and
       that no historical row (Store B or Store C) changed,
  10.  atomically updates the safety manifest with an auditable migration record, preserving a
       verbatim copy of the pre-change manifest,
  11.  fast-forwards the release worktree and verifies its migration chain's head matches the
       schema that is now actually live (never the other way around),
  12-13. starts the console in `--recovery-mode` (read-only; the automatic Plan Manager is not
       built) and verifies it came up correctly, and
  14.  STOPS. There is no step that transitions to Active Mode -- that is always a separate,
       later, explicitly Owner-authorized action outside this script.

WHY A SCRIPT AND NOT A RUNBOOK. `alembic upgrade` in online mode is unconditionally refused
for Store B/C (`refuse_unplanned_personal_migration`, database_safety.py) before it ever
connects -- by design, there is no "just run alembic" path for this database. The sanctioned
path is: generate the SQL offline (already done, reviewed, and hash-pinned here), apply it
with an explicit, narrow tool that re-verifies identity and the expected pre-image before
touching anything, and keep an auditable trail of exactly what ran and when. This script is
that tool, factored so every step is independently unit-testable against fakes and the
Postgres-touching steps are independently integration-tested against disposable databases
(see tests/unit/test_v1_personal_paper_deploy.py and
tests/integration/test_v1_personal_paper_deploy_postgres.py).

SAFETY BY CONSTRUCTION, NOT BY CONVENTION.
  - `BrokerPort` exposes only read (GET) operations -- there is no method on it, anywhere in
    this module, capable of submitting, closing or canceling an order. A caller cannot submit
    a broker order through this script even by mistake.
  - Every DB write in this module names its target database/host/port explicitly, verifies
    the PERSONAL_PAPER identity comment and the exact expected pre-image head before writing,
    and refuses (fails closed) on any mismatch. See `_identity_and_head` and `_manifest_identity`.
  - The migration step never runs `alembic upgrade` online (see WHY above); it runs exactly
    the hash-pinned SQL file via `psql -f`, inside one transaction the file itself opens and
    closes.
  - Every step is idempotent to re-invocation: a step that finds its own postcondition already
    satisfied (e.g. manifest head already bumped) returns cleanly rather than re-acting. This
    is what makes Phase 3's "kill it here and resume" scenarios safe to test at all.
  - Rollback of an applied migration is explicitly NOT attempted by this script, anywhere, for
    any step. On a failure after step 7 begins, `recovery_instructions_for` says so explicitly
    and points at the pre-migration backup; any restore is a SEPARATE, Owner-authorized,
    out-of-band action.
  - `run_deployment` never proceeds past `STEP_14_STOP_BEFORE_ACTIVE`. There is no code path in
    this module that can transition a console into Active Mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.database_safety import (
    IDENTITY_QUERY,
    PERSONAL_DATABASES,
    DatabaseSafetyError,
    read_manifest,
)

# ---------------------------------------------------------------------------------------
# Pinned, reviewed migration. Regenerate with:
#   alembic -c alembic.ini upgrade 83e15e6bfae4:f3a7c9e2b164 --sql
# and re-pin deliberately (never silently) if the migration itself ever changes.
# ---------------------------------------------------------------------------------------
MIGRATION_SQL_FILENAME: Final = "personal_paper_deploy_migration_f3a7c9e2b164.sql"
MIGRATION_PRE_HEAD: Final = "83e15e6bfae4"
MIGRATION_POST_HEAD: Final = "f3a7c9e2b164"
MIGRATION_SQL_SHA256: Final = "3eb561af82efe61373ca12501b2fdc40edd2ab0210333159557af3af60e4e5c1"

STORE_C_HEAD: Final = "d4e9c2a7f183"  # unchanged by this deployment; verified, never migrated.

#: Alpaca order states that are unambiguously "resting, working as expected" for an account
#: that should otherwise be flat. Anything else returned by `status=open` (e.g.
#: `pending_cancel`, `pending_replace`, `calculated`, `stopped`, `suspended`) is treated as
#: needing human investigation before any deployment proceeds.
_CLEAR_OPEN_ORDER_STATES: Final = frozenset({"new", "accepted", "pending_new", "partially_filled"})

STEP_1_BROKER_VERIFY: Final = "STEP_1_BROKER_VERIFY"
STEP_2_NO_INFLIGHT: Final = "STEP_2_NO_INFLIGHT"
STEP_3_RELEASE_HEAD: Final = "STEP_3_RELEASE_HEAD"
STEP_4_BACKUP: Final = "STEP_4_BACKUP"
STEP_5_SHUTDOWN: Final = "STEP_5_SHUTDOWN"
STEP_6_VERIFY_STOPPED: Final = "STEP_6_VERIFY_STOPPED"
STEP_7_MIGRATE: Final = "STEP_7_MIGRATE"
STEP_8_VERIFY_SCHEMA: Final = "STEP_8_VERIFY_SCHEMA"
STEP_9_VERIFY_UNCHANGED: Final = "STEP_9_VERIFY_UNCHANGED"
STEP_10_MANIFEST_UPDATE: Final = "STEP_10_MANIFEST_UPDATE"
STEP_11_FAST_FORWARD: Final = "STEP_11_FAST_FORWARD"
STEP_12_RECOVERY_START: Final = "STEP_12_RECOVERY_START"
STEP_13_VERIFY_STARTUP: Final = "STEP_13_VERIFY_STARTUP"
STEP_14_STOP_BEFORE_ACTIVE: Final = "STEP_14_STOP_BEFORE_ACTIVE"

STEP_ORDER: Final[tuple[str, ...]] = (
    STEP_1_BROKER_VERIFY,
    STEP_2_NO_INFLIGHT,
    STEP_3_RELEASE_HEAD,
    STEP_4_BACKUP,
    STEP_5_SHUTDOWN,
    STEP_6_VERIFY_STOPPED,
    STEP_7_MIGRATE,
    STEP_8_VERIFY_SCHEMA,
    STEP_9_VERIFY_UNCHANGED,
    STEP_10_MANIFEST_UPDATE,
    STEP_11_FAST_FORWARD,
    STEP_12_RECOVERY_START,
    STEP_13_VERIFY_STARTUP,
    STEP_14_STOP_BEFORE_ACTIVE,
)

#: One entry per step: the generic, accurate, step-specific recovery guidance. A
#: `DeploymentBlockedError` combines this with the concrete `reason` it was raised with.
_RECOVERY_TEXT: Final[Mapping[str, str]] = {
    STEP_1_BROKER_VERIFY: (
        "Nothing was changed. Re-run once the broker account is flat (zero positions, zero "
        "open orders, zero UNKNOWN-state orders) and not trading-blocked."
    ),
    STEP_2_NO_INFLIGHT: (
        "Nothing was changed. An exit dispatch, authorization or non-terminal attempt is still "
        "in flight in Store B or Store C. Wait for it to resolve (or for the Owner to resolve "
        "it) and re-run; do not force it closed from this script."
    ),
    STEP_3_RELEASE_HEAD: (
        "Nothing was changed. The worktree is not exactly the approved, clean commit. Fetch, "
        "inspect `git status`/`git log`, and resolve by hand -- this script never commits, "
        "resets or force-checks-out on your behalf."
    ),
    STEP_4_BACKUP: (
        "Nothing in Store B/C was touched. No deployment may proceed without a fresh, verified "
        "backup. Investigate the backup failure (see personal_paper_backup.py's own "
        "BACKUP_BLOCKED diagnostics) and re-run from the top."
    ),
    STEP_5_SHUTDOWN: (
        "The console may still be running or may be mid-shutdown. Do NOT start a second "
        "console on the same port. Check process state by hand before re-running; a hung "
        "shutdown needs investigation (in-flight reconciliation?), not a force-kill from here."
    ),
    STEP_6_VERIFY_STOPPED: (
        "The prior console process or port 8189 did not clear in time. The migration has NOT "
        "started. Confirm no process is listening and no stale lock remains before re-running; "
        "do not proceed to migration while this is ambiguous."
    ),
    STEP_7_MIGRATE: (
        "The migration transaction did not commit cleanly (psql reported a non-zero exit, or "
        "the pre-flight identity/head check refused to start it). The migration SQL file is "
        "fully transactional (BEGIN/COMMIT); a failure before COMMIT leaves Store B at its "
        "PRE-migration head, unchanged -- verify this directly (`SELECT version_num FROM "
        "alembic_version`) before deciding anything. Do NOT attempt an alembic downgrade and "
        "do NOT restore from backup without separate, explicit Owner authorization; the "
        "pre-migration backup from step 4 is preserved untouched either way."
    ),
    STEP_8_VERIFY_SCHEMA: (
        "The migration SQL reported success but the post-migration schema check (head, "
        "columns, constraints, guard function) did not match what it should produce. Treat "
        "Store B as being in an UNKNOWN, possibly half-migrated state. Do NOT update the "
        "manifest (step 10 will refuse to run past this point anyway) and do NOT attempt a "
        "downgrade. This needs manual DBA inspection and separate Owner authorization before "
        "any further action, including restore."
    ),
    STEP_9_VERIFY_UNCHANGED: (
        "The new schema looks correct, but a historical row count changed where it must not "
        "have (Store B's approved_plan or Store C's position_exit_attempt). Do NOT update the "
        "manifest. This is treated as a possible concurrent write during the maintenance "
        "window (the console should have been stopped in step 5/6) and needs investigation "
        "before any further step; preserve the step-4 backup and do not restore without "
        "separate Owner authorization."
    ),
    STEP_10_MANIFEST_UPDATE: (
        "Store B's schema IS already migrated (steps 7-9 passed) but the manifest update did "
        "not complete or did not verify. A verbatim pre-change copy of the manifest was "
        "written before any edit (see the step's reported backup path) -- restore the manifest "
        "from that copy if the on-disk manifest looks corrupted, then re-run step 10 alone "
        "(it is idempotent: it will see the live head already matches the migrated schema and "
        "only needs to confirm, not re-migrate). The console must stay stopped until the "
        "manifest correctly reflects the new head -- starting against a stale manifest would "
        "fail closed (PERSONAL_PAPER_LOSS_DETECTED) by design, which is safe but confusing; "
        "fix the manifest first."
    ),
    STEP_11_FAST_FORWARD: (
        "The worktree could not be fast-forwarded to the approved HEAD, or (critically) its "
        "own migrations/ chain head does not match the schema that is now actually live. DO "
        "NOT start the console from this worktree while this mismatch exists -- that is "
        "exactly the old-code-against-new-schema / new-code-against-old-schema hazard this "
        "procedure exists to prevent. Resolve the worktree state by hand; the migration and "
        "manifest are already correct and do not need to be touched again."
    ),
    STEP_12_RECOVERY_START: (
        "The console process did not start or did not begin listening on the expected port in "
        "time. Check for a stale process already holding the port, check captured "
        "stdout/stderr for a startup exception (most likely `require_personal_identity` "
        "refusing a mismatch -- re-verify the manifest head against the live schema head by "
        "hand), and re-run step 12 alone once the port is confirmed free."
    ),
    STEP_13_VERIFY_STARTUP: (
        "The console is running but did not verify cleanly (an HTTP check failed, broker was "
        "not flat, schema identity mismatched, or it did not report recovery-mode read-only "
        "status). Do NOT hand this console to the Owner for Active Mode authorization in this "
        "state. Stop it, re-diagnose from captured output, and re-run from step 12 once "
        "resolved."
    ),
    STEP_14_STOP_BEFORE_ACTIVE: (
        "Deployment completed through recovery-mode startup and verification. This script "
        "stops here by construction -- transitioning to Active Mode is always a separate, "
        "explicit, Owner-authorized action taken outside this script."
    ),
}


def recovery_instructions_for(step: str, reason: str) -> str:
    """Accurate, step-specific state report + recovery guidance for any failure."""
    generic = _RECOVERY_TEXT.get(step, "Stop and investigate by hand before re-running.")
    return f"BLOCKED at {step}: {reason}\n{generic}"


class DeploymentBlockedError(RuntimeError):
    """Raised by any step that cannot proceed. Carries an accurate state report."""

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(recovery_instructions_for(step, reason))


# ---------------------------------------------------------------------------------------
# Journal: an ordered, append-only, atomically-written record of what this run did. The
# last record always tells you exactly where a crashed run stopped.
# ---------------------------------------------------------------------------------------

StepStatus = Literal["started", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class StepRecord:
    step: str
    status: StepStatus
    at: str
    detail: str


@dataclass(slots=True)
class DeploymentJournal:
    records: list[StepRecord] = field(default_factory=list)

    def append(self, step: str, status: StepStatus, detail: str, *, now: datetime) -> None:
        self.records.append(StepRecord(step, status, now.isoformat(), detail))

    def completed_steps(self) -> set[str]:
        return {r.step for r in self.records if r.status == "completed"}

    def last(self) -> StepRecord | None:
        return self.records[-1] if self.records else None

    def to_json(self) -> dict[str, object]:
        return {
            "records": [
                {"step": r.step, "status": r.status, "at": r.at, "detail": r.detail}
                for r in self.records
            ]
        }

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> DeploymentJournal:
        raw = value.get("records", [])
        if not isinstance(raw, list):
            raise ValueError("journal 'records' must be a list")
        records: list[StepRecord] = [StepRecord(**item) for item in raw]
        return cls(records)

    def save(self, path: Path) -> None:
        _atomic_write_json(path, self.to_json())

    @classmethod
    def load_or_new(cls, path: Path) -> DeploymentJournal:
        if not path.exists():
            return cls()
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


def _atomic_write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


# ---------------------------------------------------------------------------------------
# Ports: everything this module touches outside its own process is behind a narrow,
# structurally-typed interface, so every step is testable against a fake without touching
# a real broker, a real console process, or real Postgres.
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    account_status: str
    trading_blocked: bool
    position_count: int
    open_order_count: int
    unknown_order_count: int


class BrokerPort(Protocol):
    """Read-only, by construction: no method here can submit, close or cancel an order."""

    def account_snapshot(self) -> BrokerSnapshot: ...


class ProcessPort(Protocol):
    def is_running(self, pid: int) -> bool: ...
    def graceful_stop(self, pid: int) -> None: ...
    def start_recovery_console(
        self, *, executable: Sequence[str], env: Mapping[str, str], log_path: Path
    ) -> int: ...


class NetworkPort(Protocol):
    def port_is_free(self, host: str, port: int) -> bool: ...
    def http_get(self, url: str, *, timeout: float) -> tuple[int, str]: ...


@dataclass(frozen=True, slots=True)
class Ports:
    broker: BrokerPort
    process: ProcessPort
    network: NetworkPort


def wait_until(
    predicate: Callable[[], bool], *, timeout_seconds: float, interval_seconds: float = 0.25
) -> bool:
    """Poll a predicate until true or the timeout elapses. Pure, no OS access of its own."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_seconds)


# ---------------------------------------------------------------------------------------
# Real port implementations. Not exercised against the real PERSONAL_PAPER console or the
# real broker in this repository's own test suite -- only read-only broker calls are ever
# made for real, and only against disposable fixtures in tests.
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlpacaReadOnlyBrokerPort:
    """Three GET calls. No submit/cancel/close method exists anywhere on this class."""

    api_key: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"

    def _get(self, path: str) -> Any:  # noqa: ANN401 - raw JSON payload, shape varies by endpoint
        request = urllib.request.Request(  # noqa: S310 - fixed https base_url, GET only
            self.base_url + path,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def account_snapshot(self) -> BrokerSnapshot:
        account = self._get("/v2/account")
        positions = self._get("/v2/positions")
        open_orders = self._get("/v2/orders?status=open&limit=500")
        unknown = [
            order for order in open_orders if order.get("status") not in _CLEAR_OPEN_ORDER_STATES
        ]
        return BrokerSnapshot(
            account_status=str(account.get("status", "")),
            trading_blocked=bool(account.get("trading_blocked", True)),
            position_count=len(positions),
            open_order_count=len(open_orders),
            unknown_order_count=len(unknown),
        )


class RealProcessPort:
    """Windows- and POSIX-aware; never used against a PID this repository's own tests did
    not spawn themselves."""

    def is_running(self, pid: int) -> bool:
        if os.name == "nt":
            result = subprocess.run(  # noqa: S603 - fixed executable, explicit vector
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False
        return True

    def graceful_stop(self, pid: int) -> None:
        import signal

        if os.name == "nt":
            # CTRL_BREAK_EVENT, not taskkill: a plain (non-GUI) console process started
            # with CREATE_NEW_PROCESS_GROUP (see `start_recovery_console`) receives no
            # window-close message at all, so `taskkill` without `/F` silently does
            # nothing to it. CTRL_BREAK_EVENT is what Windows actually delivers to such a
            # process as a graceful, catchable signal (Python maps it to `SIGBREAK`).
            os.kill(pid, signal.CTRL_BREAK_EVENT)
            return
        os.kill(pid, signal.SIGTERM)

    def start_recovery_console(
        self, *, executable: Sequence[str], env: Mapping[str, str], log_path: Path
    ) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log_file:
            creationflags: int = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(  # noqa: S603 - fixed, explicit argument vector
                list(executable),
                env=dict(env),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        return process.pid


class RealNetworkPort:
    def port_is_free(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            return probe.connect_ex((host, port)) != 0

    def http_get(self, url: str, *, timeout: float) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                return response.status, response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeployConfig:
    repo_path: Path
    expected_release_head: str
    manifest_path: Path
    backup_root: Path
    pg_bin: Path
    store_b_config: PostgreSQLConfigSnapshot
    store_c_config: PostgreSQLConfigSnapshot
    migration_sql_path: Path
    console_host: str
    console_port: int
    console_pid: int | None  # None until step 5 is reached for a fresh journal
    shutdown_timeout_seconds: float = 60.0
    startup_timeout_seconds: float = 30.0


def _psql_executable(pg_bin: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    executable = pg_bin.absolute() / ("psql" + suffix)
    if not executable.is_file():
        raise DeploymentBlockedError(STEP_7_MIGRATE, "required psql executable is missing")
    return executable


def _pg_environment(config: PostgreSQLConfigSnapshot) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        PGHOST=config.host,
        PGPORT=str(config.port),
        PGUSER=config.user,
        PGPASSWORD=config.password.get_secret_value() if config.password else "",
        PGCONNECT_TIMEOUT="10",
    )
    return environment


def _engine_for(config: PostgreSQLConfigSnapshot) -> Engine:
    return create_engine(config.sqlalchemy_url(), connect_args={"connect_timeout": 10})


def _identity_and_head(config: PostgreSQLConfigSnapshot) -> tuple[str | None, str | None]:
    engine = _engine_for(config)
    try:
        with engine.connect() as connection:
            row = connection.exec_driver_sql(IDENTITY_QUERY).mappings().one()
            identity = row["identity"]
            heads: Sequence[Any] = (
                connection.exec_driver_sql("SELECT version_num FROM public.alembic_version")
                .scalars()
                .all()
            )
            head = heads[0] if len(heads) == 1 else None
            return identity, head
    finally:
        engine.dispose()


def _row_count(config: PostgreSQLConfigSnapshot, table: str) -> int:
    """`table` is always one of this module's own hardcoded constants, never external input."""
    engine = _engine_for(config)
    try:
        with engine.connect() as connection:
            statement = f"SELECT count(*) FROM public.{table}"  # noqa: S608
            return int(connection.exec_driver_sql(statement).scalar_one())
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------------------
# Steps. Each is a plain function: (cfg, ports, journal, now) -> detail string on success,
# or it raises DeploymentBlockedError. `run_deployment` wraps each with journal bookkeeping.
# ---------------------------------------------------------------------------------------


def step1_broker_verify(cfg: DeployConfig, ports: Ports) -> str:
    snapshot = ports.broker.account_snapshot()
    if snapshot.account_status != "ACTIVE" or snapshot.trading_blocked:
        raise DeploymentBlockedError(
            STEP_1_BROKER_VERIFY,
            f"account not tradeable: status={snapshot.account_status} "
            f"trading_blocked={snapshot.trading_blocked}",
        )
    if snapshot.position_count or snapshot.open_order_count or snapshot.unknown_order_count:
        raise DeploymentBlockedError(
            STEP_1_BROKER_VERIFY,
            f"broker is not flat: positions={snapshot.position_count} "
            f"open_orders={snapshot.open_order_count} unknown={snapshot.unknown_order_count}",
        )
    return "broker ACTIVE, not blocked, positions=0 open_orders=0 unknown=0"


_NON_TERMINAL_EXECUTION_STATES: Final = (
    "NOT_SUBMITTED",
    "PAPER_SUBMITTED",
    "PARTIALLY_FILLED",
    "SUBMISSION_UNKNOWN",
)


def step2_no_inflight(cfg: DeployConfig) -> str:
    in_flight: list[str] = []
    for config, table, store in (
        (cfg.store_b_config, "paper_execution_attempt", "B"),
        (cfg.store_c_config, "position_exit_attempt", "C"),
    ):
        engine = _engine_for(config)
        try:
            with engine.connect() as connection:
                # `table` is always one of this function's own hardcoded tuple entries above,
                # never external input.
                placeholders = ", ".join(f"'{s}'" for s in _NON_TERMINAL_EXECUTION_STATES)
                statement = f"SELECT attempt_id FROM public.{table} WHERE state IN ({placeholders})"  # noqa: S608
                rows: Sequence[Any] = connection.exec_driver_sql(statement).scalars().all()
                in_flight.extend(f"Store {store} {table} {attempt_id}" for attempt_id in rows)
        finally:
            engine.dispose()
    if in_flight:
        raise DeploymentBlockedError(
            STEP_2_NO_INFLIGHT, f"non-terminal attempts in flight: {', '.join(in_flight)}"
        )
    return "no non-terminal paper_execution_attempt/position_exit_attempt rows"


def _git(cfg: DeployConfig, step: str, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit vector
        ["git", *args],  # noqa: S607
        cwd=cfg.repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeploymentBlockedError(step, f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def step3_release_head(cfg: DeployConfig) -> str:
    status = _git(cfg, STEP_3_RELEASE_HEAD, "status", "--porcelain")
    if status:
        raise DeploymentBlockedError(STEP_3_RELEASE_HEAD, f"worktree is not clean:\n{status}")
    head = _git(cfg, STEP_3_RELEASE_HEAD, "rev-parse", "HEAD")
    if head != cfg.expected_release_head:
        raise DeploymentBlockedError(
            STEP_3_RELEASE_HEAD, f"HEAD is {head}, expected {cfg.expected_release_head}"
        )
    return f"worktree clean at exact expected HEAD {head}"


def step4_backup(cfg: DeployConfig) -> tuple[str, Path]:
    from tools.personal_paper_backup import backup as run_backup  # local import: tools/ sibling

    try:
        completed = run_backup(cfg.manifest_path, cfg.backup_root, cfg.pg_bin, keep=168)
    except DatabaseSafetyError as error:
        raise DeploymentBlockedError(STEP_4_BACKUP, str(error)) from error
    complete_json = json.loads((completed / "complete.json").read_text(encoding="utf-8"))
    for store in ("B", "C"):
        dump = completed / f"{store}.dump"
        actual = hashlib.file_digest(dump.open("rb"), "sha256").hexdigest()
        expected = complete_json["files"][store]["sha256"]
        if actual != expected:
            raise DeploymentBlockedError(
                STEP_4_BACKUP, f"{store}.dump SHA-256 mismatch: {actual} != {expected}"
            )
        listing = subprocess.run(  # noqa: S603
            [str(_pg_restore_executable(cfg.pg_bin)), "--list", str(dump)],
            capture_output=True,
            text=True,
            check=False,
        )
        if listing.returncode != 0 or "alembic_version" not in listing.stdout:
            raise DeploymentBlockedError(
                STEP_4_BACKUP, f"{store}.dump failed independent structural verification"
            )
    return (
        f"backup {completed.name} complete, SHA-256 and structure independently verified",
        completed,
    )


def _latest_complete_backup(backup_root: Path) -> Path:
    """Re-derive the most recent complete backup directory from disk alone. Used by the
    orchestrator when resuming a run that crashed *after* step 4 actually completed (in an
    earlier process) -- the in-memory path from that step4 call no longer exists, but the
    directory it created still does, named so that sorting is chronological."""
    candidates = sorted(
        p for p in backup_root.iterdir() if p.is_dir() and (p / "complete.json").exists()
    )
    if not candidates:
        raise DeploymentBlockedError(
            STEP_10_MANIFEST_UPDATE, f"no complete backup found under {backup_root}"
        )
    return candidates[-1]


def _pg_restore_executable(pg_bin: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    executable = pg_bin.absolute() / ("pg_restore" + suffix)
    if not executable.is_file():
        raise DeploymentBlockedError(STEP_4_BACKUP, "required pg_restore executable is missing")
    return executable


def step5_shutdown(cfg: DeployConfig, ports: Ports) -> str:
    if cfg.console_pid is None:
        raise DeploymentBlockedError(STEP_5_SHUTDOWN, "no console PID was provided to stop")
    pid = cfg.console_pid
    if not ports.process.is_running(pid):
        return f"PID {pid} already not running"
    ports.process.graceful_stop(pid)
    stopped = wait_until(
        lambda: not ports.process.is_running(pid), timeout_seconds=cfg.shutdown_timeout_seconds
    )
    if not stopped:
        raise DeploymentBlockedError(
            STEP_5_SHUTDOWN, f"PID {pid} did not exit within {cfg.shutdown_timeout_seconds}s"
        )
    return f"PID {pid} exited gracefully"


def step6_verify_stopped(cfg: DeployConfig, ports: Ports) -> str:
    if cfg.console_pid is not None and ports.process.is_running(cfg.console_pid):
        raise DeploymentBlockedError(
            STEP_6_VERIFY_STOPPED, f"PID {cfg.console_pid} is still running"
        )
    lock = cfg.backup_root / ".backup.lock"
    if lock.exists():
        raise DeploymentBlockedError(STEP_6_VERIFY_STOPPED, f"backup lock still held: {lock}")
    port_free = wait_until(
        lambda: ports.network.port_is_free(cfg.console_host, cfg.console_port),
        timeout_seconds=10.0,
    )
    if not port_free:
        raise DeploymentBlockedError(
            STEP_6_VERIFY_STOPPED, f"port {cfg.console_port} is still occupied"
        )
    return f"process stopped, backup lock clear, port {cfg.console_port} free"


def step7_migrate(cfg: DeployConfig) -> str:
    sql_bytes = cfg.migration_sql_path.read_bytes()
    actual_hash = hashlib.sha256(sql_bytes).hexdigest()
    if actual_hash != MIGRATION_SQL_SHA256:
        raise DeploymentBlockedError(
            STEP_7_MIGRATE,
            f"migration SQL file hash mismatch: {actual_hash} != pinned {MIGRATION_SQL_SHA256}; "
            "refusing to run unreviewed SQL",
        )
    identity, head = _identity_and_head(cfg.store_b_config)
    if head == MIGRATION_POST_HEAD:
        return "Store B already at post-migration head; migration not re-applied (idempotent)"
    expected_identity = _manifest_identity(cfg.manifest_path, "B")
    if identity != expected_identity:
        raise DeploymentBlockedError(
            STEP_7_MIGRATE,
            f"Store B identity mismatch: expected {expected_identity!r}, found {identity!r}",
        )
    if head != MIGRATION_PRE_HEAD:
        raise DeploymentBlockedError(
            STEP_7_MIGRATE,
            f"Store B head is {head!r}, expected pre-migration head {MIGRATION_PRE_HEAD!r}",
        )
    result = subprocess.run(  # noqa: S603
        [
            str(_psql_executable(cfg.pg_bin)),
            "--no-password",
            "-v",
            "ON_ERROR_STOP=1",
            "-d",
            cfg.store_b_config.database,
            "-f",
            str(cfg.migration_sql_path),
        ],
        env=_pg_environment(cfg.store_b_config),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeploymentBlockedError(
            STEP_7_MIGRATE, f"psql exited {result.returncode}: {result.stderr.strip()}"
        )
    return f"migration SQL (sha256={actual_hash[:12]}...) applied via psql"


def _manifest_identity(manifest_path: Path, store: str) -> str:
    manifest = read_manifest(manifest_path)
    identity = manifest["stores"][store]["identity"]
    if not isinstance(identity, str):
        raise DeploymentBlockedError(STEP_7_MIGRATE, "manifest store identity is not a string")
    return identity


def step8_verify_schema(cfg: DeployConfig) -> str:
    identity, head = _identity_and_head(cfg.store_b_config)
    expected_identity = _manifest_identity(cfg.manifest_path, "B")
    if identity != expected_identity or head != MIGRATION_POST_HEAD:
        raise DeploymentBlockedError(
            STEP_8_VERIFY_SCHEMA,
            f"post-migration identity/head check failed: identity={identity!r} head={head!r}",
        )
    engine = _engine_for(cfg.store_b_config)
    try:
        with engine.connect() as connection:
            columns: set[str] = set(
                connection.exec_driver_sql(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='approved_plan'"
                )
                .scalars()
                .all()
            )
            expected_columns = {
                "triggered_exit_quote_bid",
                "triggered_exit_quote_ask",
                "triggered_exit_quote_captured_at",
                "triggered_exit_quote_source",
            }
            missing = expected_columns - columns
            if missing:
                raise DeploymentBlockedError(STEP_8_VERIFY_SCHEMA, f"missing columns: {missing}")
            constraints: set[str] = set(
                connection.exec_driver_sql(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'public.approved_plan'::regclass"
                )
                .scalars()
                .all()
            )
            expected_constraints = {
                "ck_approved_plan_trigger_quote_paired",
                "ck_approved_plan_trigger_quote_not_mandatory_exit",
            }
            missing_constraints = expected_constraints - constraints
            if missing_constraints:
                raise DeploymentBlockedError(
                    STEP_8_VERIFY_SCHEMA, f"missing constraints: {missing_constraints}"
                )
            definition: str = connection.exec_driver_sql(
                "SELECT pg_get_functiondef('public.approved_plan_guard_update()'::regprocedure)"
            ).scalar_one()
            if "quote evidence columns must be set" not in definition:
                raise DeploymentBlockedError(
                    STEP_8_VERIFY_SCHEMA, "guard function does not contain the new evidence check"
                )
    finally:
        engine.dispose()
    return f"Store B head={head}, 4 columns + 2 constraints + guard clause all present"


def step9_verify_unchanged(cfg: DeployConfig) -> str:
    """Compares against the manifest's own `minimum_attempts`, not an in-process value --
    that field is durably set by step 4's backup to the exact row count observed at backup
    time, under REPEATABLE READ, with the console already stopped (steps 5-6) before step 7
    ever runs. That makes it the correct, crash-resumable baseline: unlike a local Python
    variable, it survives this process dying between steps 7 and 9 and being re-run."""
    manifest = read_manifest(cfg.manifest_path)
    expected_b = manifest["stores"]["B"]["minimum_attempts"]
    expected_c = manifest["stores"]["C"]["minimum_attempts"]
    post_b = _row_count(cfg.store_b_config, "paper_execution_attempt")
    post_c = _row_count(cfg.store_c_config, "position_exit_attempt")
    _, head_c = _identity_and_head(cfg.store_c_config)
    if post_b != expected_b:
        raise DeploymentBlockedError(
            STEP_9_VERIFY_UNCHANGED,
            f"Store B paper_execution_attempt row count changed: {expected_b} -> {post_b}",
        )
    if post_c != expected_c:
        raise DeploymentBlockedError(
            STEP_9_VERIFY_UNCHANGED,
            f"Store C position_exit_attempt row count changed: {expected_c} -> {post_c}",
        )
    if head_c != STORE_C_HEAD:
        raise DeploymentBlockedError(
            STEP_9_VERIFY_UNCHANGED, f"Store C head changed: now {head_c!r}"
        )
    return (
        f"Store B paper_execution_attempt={post_b} rows, "
        f"Store C position_exit_attempt={post_c} rows, both unchanged vs. the backup baseline"
    )


def step10_manifest_update(
    cfg: DeployConfig,
    *,
    release_head: str,
    backup_location: Path,
    migration_sql_sha256: str,
    now: datetime,
) -> str:
    manifest = read_manifest(cfg.manifest_path)
    if manifest["stores"]["B"]["head"] == MIGRATION_POST_HEAD and "last_migration" in manifest:
        return "manifest already reflects the post-migration head (idempotent)"
    if manifest["stores"]["B"]["head"] != MIGRATION_PRE_HEAD:
        raise DeploymentBlockedError(
            STEP_10_MANIFEST_UPDATE,
            f"manifest Store B head is {manifest['stores']['B']['head']!r}, "
            f"expected pre-migration {MIGRATION_PRE_HEAD!r} -- refusing to overwrite an "
            "already-divergent manifest",
        )
    raw_backup_path = cfg.manifest_path.with_name(
        cfg.manifest_path.stem + f".pre-migration-{now.strftime('%Y%m%dT%H%M%S%fZ')}.bak.json"
    )
    raw_backup_path.write_bytes(cfg.manifest_path.read_bytes())
    manifest["stores"]["B"]["head"] = MIGRATION_POST_HEAD
    manifest["last_migration"] = {
        "revision": MIGRATION_POST_HEAD,
        "applied_at": now.isoformat(),
        "release_head": release_head,
        "migration_sql_sha256": migration_sql_sha256,
        "backup_location": str(backup_location),
        "pre_head": MIGRATION_PRE_HEAD,
        "post_head": MIGRATION_POST_HEAD,
    }
    _atomic_write_json(cfg.manifest_path, manifest)
    reread = read_manifest(cfg.manifest_path)  # re-validate through the strict reader
    if reread["stores"]["B"]["head"] != MIGRATION_POST_HEAD:
        raise DeploymentBlockedError(
            STEP_10_MANIFEST_UPDATE, "manifest did not re-read as expected after write"
        )
    return f"manifest updated (pre-change copy preserved at {raw_backup_path.name})"


def _find_chain_head(versions_dir: Path) -> str:
    revisions: dict[str, str | None] = {}
    for file in sorted(versions_dir.glob("*.py")):
        text = file.read_text(encoding="utf-8")
        revision = _extract_literal(text, "revision")
        down_revision = _extract_literal(text, "down_revision")
        if revision is not None:
            revisions[revision] = down_revision
    referenced = {down for down in revisions.values() if down is not None}
    heads = [rev for rev in revisions if rev not in referenced]
    if len(heads) != 1:
        raise DeploymentBlockedError(
            STEP_11_FAST_FORWARD,
            f"expected exactly one migration head in {versions_dir}, found {heads}",
        )
    return heads[0]


def _extract_literal(source: str, name: str) -> str | None:
    import re

    match = re.search(rf"^{name}\s*:\s*str\s*\|\s*None\s*=\s*(.+)$", source, re.MULTILINE)
    if match is None:
        match = re.search(rf"^{name}\s*:\s*str\s*=\s*(.+)$", source, re.MULTILINE)
    if match is None:
        return None
    expression = match.group(1).strip()
    if expression == "None":
        return None
    # Handles both a plain literal and this repo's split-hex-literal style ("ab" + "cd").
    pieces = re.findall(r'"([^"]*)"', expression)
    return "".join(pieces) if pieces else None


def step11_fast_forward(cfg: DeployConfig) -> str:
    branch = _git(cfg, STEP_11_FAST_FORWARD, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "release/v1-personal-paper":
        raise DeploymentBlockedError(
            STEP_11_FAST_FORWARD,
            f"worktree is on branch {branch!r}, expected release/v1-personal-paper",
        )
    _git(cfg, STEP_11_FAST_FORWARD, "fetch", "origin", "release/v1-personal-paper")
    _git(cfg, STEP_11_FAST_FORWARD, "merge", "--ff-only", "origin/release/v1-personal-paper")
    head = _git(cfg, STEP_11_FAST_FORWARD, "rev-parse", "HEAD")
    if head != cfg.expected_release_head:
        raise DeploymentBlockedError(
            STEP_11_FAST_FORWARD, f"fast-forwarded to {head}, expected {cfg.expected_release_head}"
        )
    store_b_head = _find_chain_head(cfg.repo_path / "migrations" / "versions")
    store_c_head = _find_chain_head(cfg.repo_path / "migrations_paper_exit" / "versions")
    _, live_b_head = _identity_and_head(cfg.store_b_config)
    _, live_c_head = _identity_and_head(cfg.store_c_config)
    if store_b_head != live_b_head:
        raise DeploymentBlockedError(
            STEP_11_FAST_FORWARD,
            f"worktree's Store B migration chain head {store_b_head!r} != live schema head "
            f"{live_b_head!r} -- refusing to start new code against mismatched schema",
        )
    if store_c_head != live_c_head:
        raise DeploymentBlockedError(
            STEP_11_FAST_FORWARD,
            f"worktree's Store C migration chain head {store_c_head!r} != live schema head "
            f"{live_c_head!r} -- refusing to start new code against mismatched schema",
        )
    return f"fast-forwarded to {head}; code's migration chains match the live schema exactly"


def step12_recovery_start(
    cfg: DeployConfig,
    ports: Ports,
    *,
    executable: Sequence[str],
    env: Mapping[str, str],
    log_path: Path,
) -> tuple[str, int]:
    if not ports.network.port_is_free(cfg.console_host, cfg.console_port):
        raise DeploymentBlockedError(
            STEP_12_RECOVERY_START, f"port {cfg.console_port} is already occupied before startup"
        )
    pid = ports.process.start_recovery_console(executable=executable, env=env, log_path=log_path)
    started = wait_until(
        lambda: not ports.network.port_is_free(cfg.console_host, cfg.console_port),
        timeout_seconds=cfg.startup_timeout_seconds,
    )
    if not started:
        raise DeploymentBlockedError(
            STEP_12_RECOVERY_START,
            f"PID {pid} did not begin listening on port {cfg.console_port} within "
            f"{cfg.startup_timeout_seconds}s; see {log_path}",
        )
    return (
        f"recovery-mode console PID {pid} listening on {cfg.console_host}:{cfg.console_port}",
        pid,
    )


def step13_verify_startup(cfg: DeployConfig, ports: Ports) -> str:
    base = f"http://{cfg.console_host}:{cfg.console_port}"
    status, body = ports.network.http_get(f"{base}/safety", timeout=10.0)
    if status != 200:
        raise DeploymentBlockedError(STEP_13_VERIFY_STARTUP, f"GET /safety returned {status}")
    if "HEALTHY" in body and "tick(s) completed" in body:
        raise DeploymentBlockedError(
            STEP_13_VERIFY_STARTUP,
            "/safety reports the automatic Plan Manager as running -- this is not recovery mode",
        )
    status, body = ports.network.http_get(f"{base}/health", timeout=10.0)
    if status != 200:
        raise DeploymentBlockedError(STEP_13_VERIFY_STARTUP, f"GET /health returned {status}")
    needle = "Current position (shares)</dt><dd>0</dd>".replace(" ", "")
    if needle not in body.replace(" ", ""):
        raise DeploymentBlockedError(
            STEP_13_VERIFY_STARTUP, "/health does not report a flat position"
        )
    identity, head = _identity_and_head(cfg.store_b_config)
    expected_identity = _manifest_identity(cfg.manifest_path, "B")
    if identity != expected_identity or head != MIGRATION_POST_HEAD:
        raise DeploymentBlockedError(
            STEP_13_VERIFY_STARTUP,
            f"schema identity check failed post-startup: {identity!r}/{head!r}",
        )
    read_manifest(cfg.manifest_path)  # must still validate
    return "recovery-mode console verified: read-only, broker flat, schema identity correct"


def step14_stop_before_active() -> str:
    return (
        "Deployment procedure complete through recovery-mode startup. STOPPING HERE by "
        "construction. Transitioning to Active Mode is a separate, explicit, Owner-authorized "
        "action outside this script."
    )


# ---------------------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecoveryConsoleLaunch:
    executable: Sequence[str]
    env: Mapping[str, str]
    log_path: Path


def run_deployment(
    cfg: DeployConfig,
    ports: Ports,
    journal: DeploymentJournal,
    journal_path: Path,
    *,
    launch: RecoveryConsoleLaunch,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    resume: bool = True,
) -> DeploymentJournal:
    """Run steps 1-14 in order, persisting the journal (to `journal_path`) after every step.
    Never proceeds past STEP_14. Steps already marked 'completed' in a resumed journal are
    skipped (each step function is itself idempotent too, so a step re-run after a crash
    mid-step is also safe)."""
    completed = journal.completed_steps() if resume else set()
    backup_location: Path | None = None

    def record(step: str, status: StepStatus, detail: str) -> None:
        journal.append(step, status, detail, now=now())
        journal.save(journal_path)

    for step in STEP_ORDER:
        if step in completed:
            continue
        record(step, "started", "")
        try:
            if step == STEP_1_BROKER_VERIFY:
                detail = step1_broker_verify(cfg, ports)
            elif step == STEP_2_NO_INFLIGHT:
                detail = step2_no_inflight(cfg)
            elif step == STEP_3_RELEASE_HEAD:
                detail = step3_release_head(cfg)
            elif step == STEP_4_BACKUP:
                detail, backup_location = step4_backup(cfg)
            elif step == STEP_5_SHUTDOWN:
                detail = step5_shutdown(cfg, ports)
            elif step == STEP_6_VERIFY_STOPPED:
                detail = step6_verify_stopped(cfg, ports)
            elif step == STEP_7_MIGRATE:
                detail = step7_migrate(cfg)
            elif step == STEP_8_VERIFY_SCHEMA:
                detail = step8_verify_schema(cfg)
            elif step == STEP_9_VERIFY_UNCHANGED:
                detail = step9_verify_unchanged(cfg)
            elif step == STEP_10_MANIFEST_UPDATE:
                if backup_location is None:
                    # Either step 4 ran earlier in THIS process, or (on resume, after a crash
                    # in a prior process) it ran and completed before this process started --
                    # either way, re-derive it from disk rather than require step 4 to re-run.
                    backup_location = _latest_complete_backup(cfg.backup_root)
                detail = step10_manifest_update(
                    cfg,
                    release_head=cfg.expected_release_head,
                    backup_location=backup_location,
                    migration_sql_sha256=MIGRATION_SQL_SHA256,
                    now=now(),
                )
            elif step == STEP_11_FAST_FORWARD:
                detail = step11_fast_forward(cfg)
            elif step == STEP_12_RECOVERY_START:
                detail, _recovery_pid = step12_recovery_start(
                    cfg,
                    ports,
                    executable=launch.executable,
                    env=launch.env,
                    log_path=launch.log_path,
                )
            elif step == STEP_13_VERIFY_STARTUP:
                detail = step13_verify_startup(cfg, ports)
            else:
                detail = step14_stop_before_active()
        except DeploymentBlockedError as blocked:
            record(step, "failed", blocked.reason)
            raise
        record(step, "completed", detail)

    return journal


# ---------------------------------------------------------------------------------------
# CLI. Safety by construction: running against the real PERSONAL_PAPER manifest/stores
# requires BOTH `--confirm-production` AND that the manifest path given is the real default
# production path -- there is no flag combination that silently targets production.
# ---------------------------------------------------------------------------------------

_REAL_MANIFEST_PATH: Final = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "EmpiricalPlatform"
    / "safety"
    / "personal-paper.json"
)


def _env_config(prefix: str, environ: Mapping[str, str]) -> PostgreSQLConfigSnapshot:
    from pydantic import SecretStr

    return PostgreSQLConfigSnapshot(
        host=environ.get(f"{prefix}_HOST", "localhost"),
        port=int(environ.get(f"{prefix}_PORT", "5432")),
        database=environ[f"{prefix}_DATABASE"],
        user=environ.get(f"{prefix}_USER", "empirical"),
        password=SecretStr(environ[f"{prefix}_PASSWORD"])
        if f"{prefix}_PASSWORD" in environ
        else None,
    )


#: M096 FIX (found during the 2026-10-22 read-only preflight): the real console entrypoint
#: (`_paper_position_exit_composition.resolve_paper_exit_postgres_config`) reuses Store B's
#: host/port/user/password verbatim for Store C and only swaps the database name -- there is
#: ONE real Postgres server, two databases. The real environment never sets
#: EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST/_PORT/_USER/_PASSWORD at all. This script's
#: Store C resolution used to call `_env_config("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES", ...)`
#: unconditionally, which hard-requires `_DATABASE` (`environ[...]`) and silently defaults
#: host/port to "localhost"/5432 (Store B's real port is 55433) -- so invoking this script
#: against the real environment crashed with an unhandled `KeyError` before touching
#: anything, a gap CI never caught because every test sets all five
#: EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_* variables itself.
#:
#: The constant and default below are duplicated from that module rather than imported --
#: the SAME discipline that module's own docstring already applies to Store B's wiring: a
#: tiny, stable value duplicated on purpose so a change to the console's composition root
#: can never silently change what this script assumes, and vice versa.
#: `test_store_c_fallback_constants_match_the_real_console_entrypoint` pins the two together.
_PAPER_EXIT_DATABASE_VARIABLE: Final = "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE"
_PAPER_EXIT_HOST_VARIABLE: Final = "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST"
_DEFAULT_STORE_C_DATABASE: Final = "empirical_platform_paper_exit"


def _store_c_config(
    store_b_config: PostgreSQLConfigSnapshot, environ: Mapping[str, str]
) -> PostgreSQLConfigSnapshot:
    """Store C's connectivity, resolved the SAME way the real console resolves it.

    Independent Store C configuration is opt-in and signaled by
    `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST` being set: when it is, every
    `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_*` field is resolved independently via
    `_env_config`, exactly as this script always has. When it is absent -- the real topology
    today, one Postgres server for both stores -- Store C reuses Store B's host/port/user/
    password verbatim, with only the database name taken from
    `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE` (or the same default the real console
    entrypoint uses). `_PORT`/`_USER`/`_PASSWORD` set WITHOUT `_HOST` is refused rather than
    silently mixed with Store B's values: that combination cannot mean anything safe.
    """
    independent = _PAPER_EXIT_HOST_VARIABLE in environ
    partially_configured = any(
        f"EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_{field}" in environ
        for field in ("PORT", "USER", "PASSWORD")
    )
    if not independent and partially_configured:
        raise DatabaseSafetyError(
            "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_{PORT,USER,PASSWORD} is set without "
            f"{_PAPER_EXIT_HOST_VARIABLE} -- ambiguous partial Store C override, refused."
        )
    if independent:
        return _env_config("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES", environ)
    database = environ.get(_PAPER_EXIT_DATABASE_VARIABLE, _DEFAULT_STORE_C_DATABASE)
    return store_b_config.model_copy(update={"database": database})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", required=True, type=Path)
    parser.add_argument("--expected-release-head", required=True)
    parser.add_argument("--manifest-path", required=True, type=Path)
    parser.add_argument("--backup-root", required=True, type=Path)
    parser.add_argument("--pg-bin", required=True, type=Path)
    parser.add_argument("--console-host", default="127.0.0.1")
    parser.add_argument("--console-port", type=int, default=8189)
    parser.add_argument("--console-pid", type=int, default=None)
    parser.add_argument("--journal-path", required=True, type=Path)
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required, in addition to --manifest-path matching the real production path "
        "exactly, before this script will touch Store B/C or the real manifest at all.",
    )
    arguments = parser.parse_args(argv)

    try:
        store_b_config = _env_config("EMPIRICAL_PLATFORM_POSTGRES", os.environ)
        store_c_config = _store_c_config(store_b_config, os.environ)
    except (KeyError, ValueError) as error:  # DatabaseSafetyError is a ValueError subclass.
        print(
            f"REFUSED: Store B/C configuration is incomplete or invalid ({error}). "
            "Nothing was touched.",
            file=sys.stderr,
        )
        return 2

    # ADVERSARIAL REVIEW FOLLOW-UP: the guard must key off every real-world thing that could
    # make this touch production, not just the manifest path. A decoy --manifest-path with
    # the ambient environment still pointed at the real Store B/C would otherwise sail through
    # the manifest-only check below. `PERSONAL_DATABASES` is the SAME frozenset
    # `database_safety.py` itself uses to decide what counts as a protected database.
    targets_production = (
        arguments.manifest_path.resolve() == _REAL_MANIFEST_PATH.resolve()
        or store_b_config.database in PERSONAL_DATABASES
        or store_c_config.database in PERSONAL_DATABASES
    )
    if targets_production and not arguments.confirm_production:
        print(
            "REFUSED: --manifest-path is the real PERSONAL_PAPER manifest path, or the "
            "configured Store B/C database is a real protected database, but "
            "--confirm-production was not given. Nothing was touched.",
            file=sys.stderr,
        )
        return 2
    if arguments.confirm_production and not targets_production:
        print(
            "REFUSED: --confirm-production was given but neither --manifest-path nor the "
            f"configured Store B/C database ({_REAL_MANIFEST_PATH}; {PERSONAL_DATABASES!r}) "
            "is actually a real production target. Nothing was touched.",
            file=sys.stderr,
        )
        return 2

    api_key = os.environ.get("EMPIRICAL_ALPACA_PAPER_API_KEY", "")
    secret_key = os.environ.get("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", "")
    if not api_key or not secret_key:
        print(
            "REFUSED: Alpaca PAPER credentials are not set. Nothing was touched.", file=sys.stderr
        )
        return 2

    cfg = DeployConfig(
        repo_path=arguments.repo_path,
        expected_release_head=arguments.expected_release_head,
        manifest_path=arguments.manifest_path,
        backup_root=arguments.backup_root,
        pg_bin=arguments.pg_bin,
        store_b_config=store_b_config,
        store_c_config=store_c_config,
        migration_sql_path=arguments.repo_path / "tools" / MIGRATION_SQL_FILENAME,
        console_host=arguments.console_host,
        console_port=arguments.console_port,
        console_pid=arguments.console_pid,
    )
    ports = Ports(
        broker=AlpacaReadOnlyBrokerPort(api_key=api_key, secret_key=secret_key),
        process=RealProcessPort(),
        network=RealNetworkPort(),
    )
    launch = RecoveryConsoleLaunch(
        executable=[
            str(
                arguments.repo_path
                / ".venv"
                / "Scripts"
                / "empirical-platform-operator-console.exe"
            ),
            "--capability",
            "paper-exit",
            "--recovery-mode",
            "--host",
            arguments.console_host,
            "--port",
            str(arguments.console_port),
            "--base-path",
            "/paper",
            "--no-browser",
        ],
        env=dict(os.environ),
        log_path=arguments.backup_root.parent / "recovery-console.log",
    )
    journal = DeploymentJournal.load_or_new(arguments.journal_path)
    try:
        run_deployment(cfg, ports, journal, arguments.journal_path, launch=launch)
    except DeploymentBlockedError as blocked:
        print(str(blocked), file=sys.stderr)
        return 1
    print(
        "Deployment procedure complete through STEP_14 (recovery mode). Awaiting separate "
        "Owner authorization for Active Mode."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
