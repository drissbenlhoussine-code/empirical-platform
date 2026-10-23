"""MILESTONE-098 -- a cooperative, authenticated local shutdown control for the PERSONAL_PAPER
operator console.

WHY THIS EXISTS. MILESTONE-097's deployment attempt stopped at its graceful-shutdown step:
`os.kill(pid, signal.CTRL_BREAK_EVENT)` returned `WinError 87` against the real, already-
running console, because Windows can only deliver a console-control event to a process GROUP
the SENDING process itself created with `CREATE_NEW_PROCESS_GROUP` -- an independently-launched
console (started before the deployment tool ever ran, by a different parent/console session)
is simply not addressable that way, on any Windows machine, by design of the OS primitive
itself. Separately -- and this would have mattered even if delivery had succeeded -- the real
console entrypoint (`entrypoints.operator_console`) never installs a `SIGBREAK` handler; its
`serve_forever()` loop only catches `KeyboardInterrupt` (Ctrl+C). An unhandled console-control
event hits Windows' own default action, not the documented "SHUTDOWN ORDER" (reconciler
stopped and joined, then the plan manager, then the server/database/lock release).

THE FIX. Replace process signalling with a loopback HTTP request the console answers itself,
authenticated by a per-instance secret only the same OS user who started the console can
read. This works identically regardless of how the console was launched (independently, or by
`tools/personal_paper_deploy.py::start_recovery_console`) because it never touches process
groups or signals at all -- it is a plain function call (`BaseServer.shutdown()`) triggered by
an authenticated request, which flows through the EXACT SAME `try/finally` teardown already
proven correct for `KeyboardInterrupt` (see `operator_console._serve_with_reconciler`).

SECURITY MODEL.
  - The control file lives under the Safety Manifest's own directory
    (`database_safety.manifest_path().parent`), never inside the git worktree (which a
    deployment fast-forwards/replaces) and never inside a world- or group-readable location.
  - On write, the file's permissions are narrowed to the current OS user only (`icacls` grant
    on Windows, `chmod 0600` on POSIX) -- best-effort: the token itself, not the file mode, is
    the primary authentication factor, so a narrowing failure is logged, never fatal.
  - The console only ever serves this route on loopback (the launcher's own `--host`
    validation already refuses any other bind address; this module adds no new bind surface).
  - The token is `secrets.token_hex(32)` (256 bits) and is compared with `hmac.compare_digest`
    (constant-time) -- never logged, never echoed back in any response or error message.
  - The file also records the capability, PID, port and start time. A caller MUST
    independently confirm -- at the OS level, freshly, right before reading this file -- that
    the PID it is about to stop currently OWNS the given port (see
    `tools/personal_paper_deploy.py::RealNetworkPort.owning_pid`); `read_control_token` then
    refuses unless that confirmed PID matches the file's own recorded PID. A stale file
    surviving an unclean exit can therefore never be replayed against an unrelated process
    that later happens to reuse the same PID or the same port.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

__all__ = [
    "CONTROL_TOKEN_HEADER",
    "ConsoleControlToken",
    "ControlTokenError",
    "control_token_path",
    "read_control_token",
    "remove_control_token",
    "write_control_token",
]

#: Never logged, never echoed. Carried as a plain header because the caller is a local tool
#: process, not a browser -- there is no cookie/session/CSRF concept for it to participate in.
CONTROL_TOKEN_HEADER: Final = "X-Empirical-Shutdown-Token"  # noqa: S105 - a header NAME, not a secret


class ControlTokenError(ValueError):
    """The control file is missing, unreadable, malformed, or names a different process."""


@dataclass(frozen=True, slots=True)
class ConsoleControlToken:
    pid: int
    port: int
    capability: str
    started_utc: str
    token: str


def control_token_path(safety_directory: Path, *, port: int) -> Path:
    return safety_directory / "console-control" / f"paper-exit-{port}.json"


def _restrict_to_current_user(path: Path) -> None:
    """Best-effort ACL narrowing. Never raises: the secret token itself, not the file mode,
    is what actually authenticates a request -- a narrowing failure only weakens a defense-in-
    depth layer, and must never block the console from starting or stopping."""
    try:
        if os.name == "nt":
            domain = os.environ.get("USERDOMAIN", "")
            user = os.environ.get("USERNAME", "")
            if not user:
                return
            account = f"{domain}\\{user}" if domain else user
            subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:F"],  # noqa: S607
                capture_output=True,
                check=False,
                timeout=15,
            )
        else:
            path.chmod(0o600)
    except OSError as error:
        print(f"console-control: could not narrow permissions on {path}: {error}", file=sys.stderr)


def write_control_token(safety_directory: Path, *, pid: int, port: int, capability: str) -> str:
    """Called once, by the console itself, right after it binds its port. Returns the raw
    token; the caller keeps it only in memory (never logs it) to authenticate the one route
    that accepts it."""
    path = control_token_path(safety_directory, port=port)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    payload = {
        "pid": pid,
        "port": port,
        "capability": capability,
        "started_utc": datetime.now(UTC).isoformat(),
        "token": token,
    }
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    _restrict_to_current_user(temporary)
    temporary.replace(path)
    _restrict_to_current_user(path)
    return token


def read_control_token(
    safety_directory: Path, *, port: int, expected_capability: str, expected_pid: int
) -> ConsoleControlToken:
    """Fail closed: every field must match exactly, or `ControlTokenError` is raised with no
    secret in its message. `expected_pid` must already be independently confirmed by the
    caller (a fresh OS-level query) to be the process that currently owns `port` -- this
    function trusts the file's own claims no further than matching them against that."""
    path = control_token_path(safety_directory, port=port)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ControlTokenError(f"no readable control token at {path}") from error
    try:
        record = ConsoleControlToken(
            pid=int(raw["pid"]),
            port=int(raw["port"]),
            capability=str(raw["capability"]),
            started_utc=str(raw["started_utc"]),
            token=str(raw["token"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ControlTokenError(f"control token at {path} is malformed") from error
    if record.capability != expected_capability:
        raise ControlTokenError(
            f"control token capability {record.capability!r} != expected "
            f"{expected_capability!r}; refusing to stop a different capability's console"
        )
    if record.port != port:
        raise ControlTokenError("control token names a different port than expected")
    if record.pid != expected_pid:
        raise ControlTokenError(
            f"control token PID {record.pid} != the process ({expected_pid}) independently "
            "confirmed to own the port -- refusing (stale token or PID reuse)"
        )
    return record


def remove_control_token(safety_directory: Path, *, port: int) -> None:
    """Best-effort cleanup; a missing file is not an error."""
    control_token_path(safety_directory, port=port).unlink(missing_ok=True)
