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
  - On write, the file's (and its directory's) permissions are narrowed to the current OS
    user only (`icacls` grant on Windows, `chmod` on POSIX) and the narrowing is read back
    and verified -- see SECURITY HARDENING below for why this is fail-closed, not best-effort.
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

SECURITY HARDENING (MILESTONE-098 follow-up). Three gaps closed, deliberately, without
changing the shape of the design above:
  1. FAIL CLOSED ON PERMISSIONS. Narrowing a file or directory's permissions to the current
     OS user is no longer best-effort: a failure to apply it, or to verify afterward (by
     reading the permissions back) that it actually took effect, now raises
     `ControlTokenPermissionError` instead of only logging. The caller
     (`operator_console._install_shutdown_control`) catches exactly this and does NOT
     register the `/control/shutdown` route -- the console keeps running its normal
     read-only/recovery functions, but the shutdown interface itself never activates. This
     also applies to the `console-control` DIRECTORY, not only the token file inside it: a
     world- or group-writable directory would let an unprivileged local user delete and
     replace the file even if the file's own ACL were perfect.
  2. SYMLINKS ARE REFUSED, NEVER FOLLOWED. The safety directory, the `console-control`
     directory, and the token file itself (and its write-time temporary file) are each
     checked with `Path.is_symlink()` before being trusted for a read or a write. A symlink
     planted ahead of time at any of those locations is refused outright rather than
     transparently followed, which would otherwise let a co-resident, lower-privileged
     process redirect a security-critical read or write to a location it controls.
  3. PID REUSE WITHIN THE SAME SHORT WINDOW. Matching PID alone cannot distinguish the real
     console from an unrelated process that the OS reuses the same PID for moments later.
     `write_control_token` additionally records `process_start_fingerprint(os.getpid())` --
     an OS-queried (not self-reported) process start time -- and `read_control_token` now
     requires the caller's OWN freshly-queried fingerprint for `expected_pid` to match
     exactly. `tools/personal_paper_deploy.py` queries this immediately before the token
     read, closing the window between discovering the owning PID and actually stopping it.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

__all__ = [
    "CONTROL_TOKEN_HEADER",
    "ConsoleControlToken",
    "ControlTokenError",
    "ControlTokenPermissionError",
    "control_token_path",
    "process_start_fingerprint",
    "read_control_token",
    "remove_control_token",
    "write_control_token",
]

#: Never logged, never echoed. Carried as a plain header because the caller is a local tool
#: process, not a browser -- there is no cookie/session/CSRF concept for it to participate in.
CONTROL_TOKEN_HEADER: Final = "X-Empirical-Shutdown-Token"  # noqa: S105 - a header NAME, not a secret

#: Principals that must never appear in a narrowed Windows ACL readback. Their presence means
#: the grant/inheritance removal above did not actually take effect as intended.
_BROAD_WINDOWS_PRINCIPALS: Final = (
    "Everyone",
    "BUILTIN\\Users",
    "Authenticated Users",
    "ANONYMOUS LOGON",
)


class ControlTokenError(ValueError):
    """The control file is missing, unreadable, malformed, or names a different process."""


class ControlTokenPermissionError(ControlTokenError):
    """A control file or directory's permissions could not be narrowed to the current OS
    user, or could not be verified afterward, or a symlink was found where a plain file or
    directory was expected. FAIL CLOSED: the caller must treat this as a reason the
    shutdown route cannot safely activate, never as a logged-and-ignored warning."""


@dataclass(frozen=True, slots=True)
class ConsoleControlToken:
    pid: int
    port: int
    capability: str
    started_utc: str
    start_fingerprint: str
    token: str


def control_token_path(safety_directory: Path, *, port: int) -> Path:
    return safety_directory / "console-control" / f"paper-exit-{port}.json"


def process_start_fingerprint(pid: int) -> str:
    """An OS-queried (never self-reported) fingerprint of when `pid` started, used as a
    second identity factor alongside the PID itself: two processes can share a PID (one
    after the other, via OS reuse) but cannot share a start time. Raises `RuntimeError` --
    never returns a placeholder -- if the OS query itself could not be completed, so a
    caller never mistakes "could not determine" for a value that would simply fail to
    match."""
    pid = int(pid)
    if os.name == "nt":
        result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
            [  # noqa: S607 - fixed executable name, no PATH-relative ambiguity intended
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-Process -Id {pid} -ErrorAction Stop).StartTime.ToUniversalTime()"
                ".ToString('o')",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        fingerprint = result.stdout.strip()
        if result.returncode != 0 or not fingerprint:
            raise RuntimeError(
                f"could not determine the start time of PID {pid}: "
                f"{result.stderr.strip() or 'no output from Get-Process'}"
            )
        return fingerprint
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
        ["ps", "-o", "lstart=", "-p", str(pid)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    fingerprint = result.stdout.strip()
    if result.returncode != 0 or not fingerprint:
        raise RuntimeError(f"could not determine the start time of PID {pid} via 'ps'")
    return fingerprint


def _reject_if_symlink(path: Path, *, label: str) -> None:
    """`Path.is_symlink()` is lstat-based (never follows the link itself), which is exactly
    what is needed here: detect a planted symlink without ever opening whatever it points
    at. A path that does not exist at all is not a symlink and passes -- that is the normal,
    expected case for a fresh write."""
    if path.is_symlink():
        raise ControlTokenPermissionError(
            f"refusing to use {label} at {path}: it is a symlink, which could silently "
            "redirect this security-critical read or write to an unexpected location"
        )


def _verify_windows_acl(path: Path, account: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
        ["icacls", str(path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise ControlTokenPermissionError(
            f"could not read back icacls permissions on {path} to verify them"
        )
    output = result.stdout
    if account.lower() not in output.lower():
        raise ControlTokenPermissionError(
            f"icacls on {path} does not show the expected owner {account!r} after "
            "narrowing; refusing to trust this file's permissions"
        )
    for principal in _BROAD_WINDOWS_PRINCIPALS:
        if principal.lower() in output.lower():
            raise ControlTokenPermissionError(
                f"icacls on {path} still grants {principal!r} after narrowing; refusing to "
                "trust a control file or directory readable beyond the current user"
            )


def _restrict_to_current_user(path: Path, *, posix_mode: int = 0o600) -> None:
    """FAIL CLOSED (MILESTONE-098 hardening): raises `ControlTokenPermissionError` if
    narrowing cannot be applied, or if applying it cannot be independently verified
    afterward by reading the permissions back -- never only logs and continues. The caller
    (`write_control_token`, and through it `operator_console._install_shutdown_control`) is
    responsible for treating this as "the shutdown route must not activate", not as "the
    console must crash"."""
    if os.name == "nt":
        domain = os.environ.get("USERDOMAIN", "")
        user = os.environ.get("USERNAME", "")
        if not user:
            raise ControlTokenPermissionError(
                "cannot determine the current Windows user (USERNAME is unset); refusing "
                f"to narrow or trust permissions on {path}"
            )
        account = f"{domain}\\{user}" if domain else user
        try:
            result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:F"],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except OSError as error:
            raise ControlTokenPermissionError(
                f"icacls could not run for {path}: {error}"
            ) from error
        if result.returncode != 0:
            raise ControlTokenPermissionError(
                f"icacls failed to narrow permissions on {path} (exit {result.returncode}): "
                f"{(result.stderr or result.stdout).strip()}"
            )
        _verify_windows_acl(path, account)
        return
    try:
        path.chmod(posix_mode)
    except OSError as error:
        raise ControlTokenPermissionError(
            f"chmod({oct(posix_mode)}) failed for {path}: {error}"
        ) from error
    actual_mode = path.stat().st_mode & 0o777
    if actual_mode != posix_mode:
        raise ControlTokenPermissionError(
            f"permissions on {path} are {oct(actual_mode)} after chmod, not "
            f"{oct(posix_mode)}; refusing to trust it"
        )


def write_control_token(safety_directory: Path, *, pid: int, port: int, capability: str) -> str:
    """Called once, by the console itself, right after it binds its port. Returns the raw
    token; the caller keeps it only in memory (never logs it) to authenticate the one route
    that accepts it.

    Raises `ControlTokenPermissionError` -- never silently degrades -- if a symlink is found
    anywhere along the path, if this process's own start-time identity cannot be
    established, or if permissions cannot be narrowed and verified on either the
    `console-control` directory or the token file itself. On any such failure, any partial
    file this call created is removed before the error propagates."""
    _reject_if_symlink(safety_directory, label="the safety directory")
    directory = control_token_path(safety_directory, port=port).parent
    path = control_token_path(safety_directory, port=port)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _reject_if_symlink(directory, label="the console-control directory")
        _restrict_to_current_user(directory, posix_mode=0o700)
        _reject_if_symlink(path, label="the control token file")
        _reject_if_symlink(temporary, label="the control token temp file")
        try:
            fingerprint = process_start_fingerprint(os.getpid())
        except RuntimeError as error:
            raise ControlTokenPermissionError(
                f"could not establish this process's own start-time identity: {error}"
            ) from error
        token = secrets.token_hex(32)
        payload = {
            "pid": pid,
            "port": port,
            "capability": capability,
            "started_utc": datetime.now(UTC).isoformat(),
            "start_fingerprint": fingerprint,
            "token": token,
        }
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        _restrict_to_current_user(temporary)
        temporary.replace(path)
        _restrict_to_current_user(path)
    except ControlTokenPermissionError:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return token


def read_control_token(
    safety_directory: Path,
    *,
    port: int,
    expected_capability: str,
    expected_pid: int,
    expected_start_fingerprint: str,
) -> ConsoleControlToken:
    """Fail closed: every field must match exactly, or `ControlTokenError` is raised with no
    secret in its message. `expected_pid` must already be independently confirmed by the
    caller (a fresh OS-level query) to be the process that currently owns `port`, and
    `expected_start_fingerprint` must be that SAME caller's own fresh
    `process_start_fingerprint(expected_pid)` -- queried as close as possible to this call --
    so a PID reused within the same short window by an unrelated process is rejected even
    though the bare PID number would otherwise match."""
    path = control_token_path(safety_directory, port=port)
    _reject_if_symlink(path, label="the control token file")
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
            start_fingerprint=str(raw["start_fingerprint"]),
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
    if record.start_fingerprint != expected_start_fingerprint:
        raise ControlTokenError(
            f"control token start-time fingerprint for PID {expected_pid} does not match "
            "the process currently owning the port -- refusing (stale token or a fast PID "
            "reuse within the same window)"
        )
    return record


def remove_control_token(safety_directory: Path, *, port: int) -> None:
    """Best-effort cleanup; a missing file is not an error."""
    control_token_path(safety_directory, port=port).unlink(missing_ok=True)
