"""RELEASE v1 hardening -- single-instance lock, maintenance hold and exit-code contract for the
PAPER (`--capability paper-exit`) Operator Console.

Everything lives in the console's control directory (`<safety dir>/console-control`, the same
owner-only directory the M098 shutdown token uses; created and verified by
`console_control.ensure_control_directory`).

SINGLE-INSTANCE LOCK (`paper-exit-console.lock`). An OS-level exclusive, non-blocking file lock
(`msvcrt.locking` on Windows, `fcntl.flock` on POSIX) on byte 0, taken BEFORE any database,
broker or listener is opened and held for the process's life. The OS drops it when the process
dies, so a crash leaves no stale lock (a leftover file from a dead process is simply
re-acquirable). The holder's PID and start time are written after byte 0 for diagnostics only;
the lock itself is the lock, never the file contents.

MAINTENANCE HOLD (`maintenance-hold.json`). A durable marker created atomically (exclusive
create, owner-only) by `tools/personal_paper_deploy.py` before it stops the console. While it
exists: the autostart wrapper refuses to launch, and the console refuses to start in FULL
(non-recovery) mode. `--recovery-mode` is still allowed. Nothing in the deploy tool removes it;
the Owner removes it with `python -m empirical_platform.entrypoints.release_maintenance_hold`
when authorizing normal PAPER start.

EXIT CODES (documented contract with `deploy/windows/run-v1-console.ps1`):
  0   clean stop (Ctrl+C)                          -> wrapper does NOT restart
  64  deliberate authenticated shutdown (M098)     -> wrapper does NOT restart
  2   refused at startup (bad flags etc.)          -> wrapper does NOT restart
  73  another console already holds the lock       -> wrapper does NOT restart
  74  refused: maintenance hold present (full mode)-> wrapper does NOT restart
  anything else (crash)                            -> wrapper restarts, bounded
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from empirical_platform.shared import console_control

__all__ = [
    "EXIT_ALREADY_RUNNING",
    "EXIT_DELIBERATE_SHUTDOWN",
    "EXIT_MAINTENANCE_HOLD",
    "EXIT_NO_RESTART_CODES",
    "HOLD_FILE_NAME",
    "LOCK_FILE_NAME",
    "ConsoleAlreadyRunningError",
    "ConsoleInstanceLock",
    "MaintenanceHoldError",
    "create_maintenance_hold",
    "hold_path",
    "maintenance_hold_active",
    "release_maintenance_hold",
]

EXIT_DELIBERATE_SHUTDOWN: Final = 64
EXIT_ALREADY_RUNNING: Final = 73
EXIT_MAINTENANCE_HOLD: Final = 74
EXIT_NO_RESTART_CODES: Final = frozenset({0, 2, 64, 73, 74})

LOCK_FILE_NAME: Final = "paper-exit-console.lock"
HOLD_FILE_NAME: Final = "maintenance-hold.json"


class ConsoleAlreadyRunningError(RuntimeError):
    """Another PAPER console already holds the single-instance lock."""


class MaintenanceHoldError(RuntimeError):
    """The maintenance hold or lock directory could not be prepared or changed safely."""


def _control_dir(safety_directory: Path) -> Path:
    return Path(safety_directory) / "console-control"


def hold_path(safety_directory: Path) -> Path:
    return _control_dir(safety_directory) / HOLD_FILE_NAME


def maintenance_hold_active(safety_directory: Path) -> bool:
    """True when anything exists at the hold path (a dangling symlink counts: fail closed)."""
    path = hold_path(safety_directory)
    return path.exists() or path.is_symlink()


def _prepare_directory(safety_directory: Path) -> Path:
    try:
        return console_control.ensure_control_directory(Path(safety_directory))
    except (console_control.ControlTokenError, OSError) as error:
        raise MaintenanceHoldError(
            f"cannot prepare the console-control directory: {error}"
        ) from error


def create_maintenance_hold(
    safety_directory: Path, *, reason: str, now: datetime | None = None
) -> bool:
    """Atomically creates the hold. Returns True if created now, False if one already existed
    (idempotent: a resumed deployment leaves the existing hold untouched). Raises
    `MaintenanceHoldError` if it cannot be created safely."""
    path = _prepare_directory(safety_directory) / HOLD_FILE_NAME
    if path.exists() or path.is_symlink():
        return False
    payload = {
        "reason": reason,
        "created_utc": (now or datetime.now(UTC)).isoformat(),
        "created_by_pid": os.getpid(),
    }
    try:
        console_control.create_owner_only_file_exclusively(
            path, json.dumps(payload, sort_keys=True), label="the maintenance hold"
        )
    except console_control.ControlTokenError as error:
        if path.exists():  # lost a creation race: a hold exists, which is the goal
            return False
        raise MaintenanceHoldError(f"cannot create the maintenance hold: {error}") from error
    return True


def release_maintenance_hold(safety_directory: Path) -> bool:
    """Removes the hold; True if one was removed. Owner-authorized actions only."""
    path = hold_path(safety_directory)
    if not (path.exists() or path.is_symlink()):
        return False
    try:
        path.unlink()
    except OSError as error:
        raise MaintenanceHoldError(f"cannot remove the maintenance hold {path}: {error}") from error
    return True


class ConsoleInstanceLock:
    """Exclusive, non-blocking, OS-released lock; see the module docstring."""

    def __init__(self, safety_directory: Path) -> None:
        self._safety_directory = Path(safety_directory)
        self._path = _control_dir(self._safety_directory) / LOCK_FILE_NAME
        self._handle: Any = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        _prepare_directory(self._safety_directory)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(fd, "r+b", buffering=0)
        try:
            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"\0")
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            holder = self._describe_holder()
            handle.close()
            raise ConsoleAlreadyRunningError(
                f"another PAPER Operator Console already holds {self._path}{holder}; refusing to "
                "start a second one. Nothing was opened or changed."
            ) from error
        self._handle = handle
        self._record_holder()

    def _record_holder(self) -> None:
        info = json.dumps({"pid": os.getpid(), "started_utc": datetime.now(UTC).isoformat()})
        try:
            self._handle.seek(1)
            self._handle.truncate(1)
            self._handle.write(info.encode("utf-8"))
        except OSError:
            pass  # diagnostics only; the lock itself is already held

    def _describe_holder(self) -> str:
        try:
            with open(self._path, "rb") as stream:
                stream.seek(1)
                info = json.loads(stream.read().decode("utf-8"))
            return f" (held by PID {info['pid']}, started {info['started_utc']})"
        except (OSError, ValueError, KeyError, TypeError):
            return ""

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> ConsoleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
