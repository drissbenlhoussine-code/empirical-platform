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
  - NETWORK ISOLATION'S REAL BOUNDARY. `operator_console._install_shutdown_control` refuses a
    request whose `REMOTE_ADDR` is not loopback, or that carries a header a naive reverse
    proxy or tunnel (Tailscale `serve`/`funnel`, nginx, etc.) typically adds
    (`X-Forwarded-For` and siblings). Those checks are a fast, defense-in-depth tripwire --
    NOT the actual isolation guarantee. A header-stripping, byte-for-byte TCP relay in front
    of this loopback port is indistinguishable, at the WSGI layer, from a genuine local
    caller: it connects to the console over loopback too, so `REMOTE_ADDR` is `127.0.0.1`
    either way, and it adds no header to catch. The guarantee that actually holds in that
    worst case is the per-instance secret token itself: it is generated fresh per process,
    kept only in memory and in a permission-narrowed file, and never sent over any network by
    anything that would legitimately know it. `tests/integration/test_m098_windows_console_
    shutdown.py::test_step5_shutdown_route_still_refuses_through_a_header_stripping_tcp_relay`
    proves this against a real, dumb TCP relay that adds no header at all.

SECURITY HARDENING (MILESTONE-098 follow-up, two rounds). Closed deliberately, without
changing the shape of the design above:
  1. FAIL CLOSED ON PERMISSIONS, VERIFIED BY SID. Narrowing a file or directory's permissions
     to the current OS user is not best-effort: a failure to apply it, or to verify afterward
     that it actually took effect, raises `ControlTokenPermissionError` instead of only
     logging. The caller (`operator_console._install_shutdown_control`) catches exactly this
     and does NOT register the `/control/shutdown` route -- the console keeps running its
     normal read-only/recovery functions, but the shutdown interface itself never activates.
     This also applies to the `console-control` DIRECTORY, not only the token file inside it.
     Verification is by SID (`WindowsIdentity.GetCurrent().User.Value`, and every ACE's
     `IdentityReference` resolved to its SID via `Get-Acl`), never by account display NAME:
     a name such as "Everyone" is itself localized on a non-English Windows installation (and
     is in principle renameable), while its well-known SID (`S-1-1-0`) never changes. The
     current user's own identity is likewise taken from the OS token directly, never from the
     `USERNAME`/`USERDOMAIN` environment variables.
  2. SYMLINKS AND JUNCTIONS ARE REFUSED, NEVER FOLLOWED -- AND NEVER RACED. The safety
     directory, the `console-control` directory, and the token file itself (and its write-time
     temporary file) are each checked before being trusted for a read or a write: first for a
     symlink (`Path.is_symlink()`), and -- because an NTFS junction uses a different reparse
     tag (`IO_REPARSE_TAG_MOUNT_POINT`) that `Path.is_symlink()` does not recognize, and
     requires no elevated privilege to create, unlike a symlink -- also for ANY reparse point
     via the file's attributes. Beyond that early check, the token file's actual read and its
     temp file's actual write each happen through a SINGLE open, closing the remaining TOCTOU
     window a separate "check, then open" pattern would leave for a swap in between: the read
     opens a raw handle reparse-point-aware (`FILE_FLAG_OPEN_REPARSE_POINT`) and reads through
     that SAME handle; the write uses the OS's own exclusive-create guarantee (`O_EXCL` on
     POSIX, `CREATE_NEW` on Windows), so anything already at that exact name -- planted in the
     race window -- makes the create itself fail closed instead of writing through it.
  3. PID REUSE WITHIN THE SAME SHORT WINDOW. Matching PID alone cannot distinguish the real
     console from an unrelated process that the OS reuses the same PID for moments later.
     `write_control_token` additionally records `process_start_fingerprint(os.getpid())` --
     an OS-queried (not self-reported) process start time -- and `read_control_token` now
     requires the caller's OWN freshly-queried fingerprint for `expected_pid` to match
     exactly. `tools/personal_paper_deploy.py` queries this immediately before the token
     read, closing the window between discovering the owning PID and actually stopping it.
"""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import stat
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

#: Well-known, locale- and rename-INDEPENDENT SIDs that must never appear in a narrowed
#: Windows ACL readback. Checking by SID (rather than a display name like "Everyone", which
#: is itself localized on a non-English Windows installation) is what MILESTONE-098's final
#: hardening round closed -- see the module docstring's hardening item 1.
_BROAD_WINDOWS_SIDS: Final = (
    "S-1-1-0",  # Everyone
    "S-1-5-7",  # ANONYMOUS LOGON
    "S-1-5-11",  # Authenticated Users
    "S-1-5-32-545",  # BUILTIN\Users
)


class _ByHandleFileInformation(ctypes.Structure):
    """Mirrors Win32's `BY_HANDLE_FILE_INFORMATION`; only `dwFileAttributes` is actually used
    here (to detect a reparse point on an already-open handle), but every field must be
    present and correctly sized for `GetFileInformationByHandle` to write into this struct
    safely. Built from plain `ctypes` primitives (no `ctypes.wintypes`, which is importable
    only on Windows) so this class definition itself never fails to import on POSIX."""

    _fields_ = [
        ("dwFileAttributes", ctypes.c_uint32),
        ("ftCreationTime_low", ctypes.c_uint32),
        ("ftCreationTime_high", ctypes.c_uint32),
        ("ftLastAccessTime_low", ctypes.c_uint32),
        ("ftLastAccessTime_high", ctypes.c_uint32),
        ("ftLastWriteTime_low", ctypes.c_uint32),
        ("ftLastWriteTime_high", ctypes.c_uint32),
        ("dwVolumeSerialNumber", ctypes.c_uint32),
        ("nFileSizeHigh", ctypes.c_uint32),
        ("nFileSizeLow", ctypes.c_uint32),
        ("nNumberOfLinks", ctypes.c_uint32),
        ("nFileIndexHigh", ctypes.c_uint32),
        ("nFileIndexLow", ctypes.c_uint32),
    ]


_GENERIC_READ: Final = 0x80000000
_GENERIC_WRITE: Final = 0x40000000
_FILE_SHARE_READ: Final = 0x00000001
_FILE_SHARE_WRITE: Final = 0x00000002
_OPEN_EXISTING: Final = 3
_CREATE_NEW: Final = 1
_FILE_FLAG_BACKUP_SEMANTICS: Final = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT: Final = 0x00200000
_INVALID_HANDLE_VALUE: Final = ctypes.c_void_p(-1).value
_ERROR_FILE_NOT_FOUND: Final = 2
_ERROR_PATH_NOT_FOUND: Final = 3
#: `os.O_NOFOLLOW` does not exist in the Windows `os` module (not even as a no-op) -- the
#: POSIX-only branches that use it never execute on Windows at runtime (`os.name != "nt"`
#: guards them), but `getattr` avoids a static attribute-lookup error when this module (and
#: its type stubs) are evaluated on a platform where the real flag is absent.
_O_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)

if os.name == "nt":
    #: `use_last_error=True` is required for `ctypes.get_last_error()` to reflect the real
    #: Win32 `GetLastError()` value immediately after a call below -- without it, ctypes'
    #: own bookkeeping can clobber it first. `restype`/`argtypes` are set explicitly because
    #: ctypes otherwise assumes a 32-bit `c_int` return, which TRUNCATES a 64-bit handle
    #: pointer on 64-bit Windows.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.restype = ctypes.c_void_p
    _kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    _kernel32.GetFileInformationByHandle.restype = ctypes.c_int
    _kernel32.GetFileInformationByHandle.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ByHandleFileInformation),
    ]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


class ControlTokenError(ValueError):
    """The control file is missing, unreadable, malformed, or names a different process."""


class ControlTokenPermissionError(ControlTokenError):
    """A control file or directory's permissions could not be narrowed to the current OS
    user, or could not be verified afterward, or a symlink/junction/reparse point was found
    where a plain file or directory was expected. FAIL CLOSED: the caller must treat this as
    a reason the shutdown route cannot safely activate, never as a logged-and-ignored
    warning."""


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
    expected case for a fresh write.

    This alone is not enough on Windows: an NTFS junction is a DIFFERENT reparse tag
    (`IO_REPARSE_TAG_MOUNT_POINT`, not `IO_REPARSE_TAG_SYMLINK`) that `Path.is_symlink()`
    does not recognize at all, and -- unlike a symlink -- a junction requires no elevated
    privilege to create, making it the more practical attack a lower-privileged co-resident
    process could mount. `os.lstat`'s `st_file_attributes` is checked for ANY reparse point,
    closing that gap."""
    if path.is_symlink():
        raise ControlTokenPermissionError(
            f"refusing to use {label} at {path}: it is a symlink, which could silently "
            "redirect this security-critical read or write to an unexpected location"
        )
    if os.name != "nt":
        return
    try:
        attributes = os.lstat(path).st_file_attributes
    except FileNotFoundError:
        return
    except OSError as error:
        raise ControlTokenPermissionError(
            f"could not inspect {label} at {path} to rule out a reparse point: {error}"
        ) from error
    if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ControlTokenPermissionError(
            f"refusing to use {label} at {path}: it is a reparse point (for example an "
            "NTFS junction or mount point), which Path.is_symlink() does not detect on "
            "Windows, and which could just as easily redirect this security-critical read "
            "or write to a location outside this process's control"
        )


def _ps_single_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _current_windows_user_sid() -> str:
    """The current process's own OS-reported identity SID -- queried directly from its
    Windows token (`WindowsIdentity.GetCurrent()`), never derived from environment
    variables like `USERNAME`/`USERDOMAIN`. Those name a principal but are not themselves
    an authoritative identity, and could in principle be absent, stale, or (for a child
    process) influenced by whatever set up its environment."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
            [  # noqa: S607 - fixed executable name, no PATH-relative ambiguity intended
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except OSError as error:
        raise ControlTokenPermissionError(
            f"could not run powershell to determine the current Windows user's SID: {error}"
        ) from error
    sid = result.stdout.strip()
    if result.returncode != 0 or not sid:
        raise ControlTokenPermissionError(
            "could not determine the current Windows user's SID: "
            f"{result.stderr.strip() or 'no output from WindowsIdentity.GetCurrent()'}"
        )
    return sid


def _windows_acl_sids(path: Path) -> list[str]:
    """Every ACE on `path` resolved to its SID -- the authoritative, locale- and
    rename-independent identifier for the principal it grants to. A display name such as
    "Everyone" is itself localized on a non-English Windows installation (e.g. "Jeder",
    "Todos") and would silently defeat a broad-principal check based on string names alone;
    its well-known SID (`S-1-1-0`) never changes regardless of locale or any rename."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
            [  # noqa: S607 - fixed executable name, no PATH-relative ambiguity intended
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-Acl -LiteralPath {_ps_single_quote(str(path))}).Access | "
                "ForEach-Object { $_.IdentityReference.Translate("
                "[System.Security.Principal.SecurityIdentifier]).Value }",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except OSError as error:
        raise ControlTokenPermissionError(
            f"could not run powershell to read back the ACL on {path} via Get-Acl: {error}"
        ) from error
    if result.returncode != 0:
        raise ControlTokenPermissionError(
            f"could not read back the ACL on {path} via Get-Acl to verify it by SID: "
            f"{result.stderr.strip()}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _verify_windows_acl(path: Path, expected_sid: str) -> None:
    """Fails closed if the current user's own SID is missing, or if any UNPRIVILEGED,
    broad-audience SID (`_BROAD_WINDOWS_SIDS` -- Everyone, Authenticated Users, etc.) is
    present. Deliberately does NOT object to SYSTEM (`S-1-5-18`) or local Administrators
    (`S-1-5-32-544`) explicit ACEs that `/grant:r` on a single principal does not remove and
    that Windows commonly attaches to a newly-created file regardless: the threat this
    module defends against is an unprivileged, co-resident local user reading the token,
    not the machine's own OS/admin principals, which could already read anything on this
    machine's disk by other means."""
    sids = _windows_acl_sids(path)
    if expected_sid not in sids:
        raise ControlTokenPermissionError(
            f"the ACL on {path} does not grant the current user's SID ({expected_sid}) "
            "after narrowing; refusing to trust this file's permissions"
        )
    broad = [sid for sid in sids if sid in _BROAD_WINDOWS_SIDS]
    if broad:
        raise ControlTokenPermissionError(
            f"the ACL on {path} still grants a well-known broad SID {broad!r} after "
            "narrowing; refusing to trust a control file or directory readable beyond the "
            "current user"
        )


def _restrict_to_current_user(path: Path, *, posix_mode: int = 0o600) -> None:
    """FAIL CLOSED (MILESTONE-098 hardening): raises `ControlTokenPermissionError` if
    narrowing cannot be applied, or if applying it cannot be independently verified
    afterward by reading the permissions back -- never only logs and continues. The caller
    (`write_control_token`, and through it `operator_console._install_shutdown_control`) is
    responsible for treating this as "the shutdown route must not activate", not as "the
    console must crash".

    On Windows, both the grant and its verification are keyed by SID
    (`_current_windows_user_sid`/`_verify_windows_acl`), not by an account display name."""
    if os.name == "nt":
        sid = _current_windows_user_sid()
        try:
            result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"],  # noqa: S607
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
        _verify_windows_acl(path, sid)
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


def _create_token_text_exclusively(path: Path, text: str, *, label: str) -> None:
    """Creates `path` using the OS's own exclusive-create guarantee -- `O_EXCL` (POSIX) or
    `CREATE_NEW` (Windows) -- so anything already at this exact name (planted by an attacker
    in the TOCTOU window between an earlier symlink/reparse-point check and this write)
    makes the create itself fail closed, rather than silently writing through or over
    whatever was already there."""
    data = text.encode("utf-8")
    if os.name != "nt":
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o600)
        except OSError as error:
            # Nothing was created -- O_EXCL guarantees the create and the failure are
            # atomic -- so there is nothing of ours to clean up here.
            raise ControlTokenPermissionError(
                f"could not exclusively create {label} at {path}: {error}"
            ) from error
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
        except OSError as error:
            # The create succeeded (this call -- and only this call -- owns the file
            # now) but writing to it failed; clean up the partial file we made.
            path.unlink(missing_ok=True)
            raise ControlTokenPermissionError(
                f"could not write {label} at {path}: {error}"
            ) from error
        return
    handle = _kernel32.CreateFileW(
        str(path),
        _GENERIC_WRITE,
        _FILE_SHARE_READ,
        None,
        _CREATE_NEW,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        # CREATE_NEW guarantees the create and the failure are atomic: nothing was
        # created, so there is nothing of ours to clean up here.
        raise ControlTokenPermissionError(
            f"could not exclusively create {label} at {path}: Win32 error {ctypes.get_last_error()}"
        )
    import msvcrt  # Windows-only stdlib module; a top-level import would break POSIX

    try:
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except OSError as error:
        _kernel32.CloseHandle(handle)
        path.unlink(missing_ok=True)
        raise ControlTokenPermissionError(f"could not write {label} at {path}: {error}") from error
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    except OSError as error:
        # `os.fdopen`'s context manager has already closed the handle on the way out,
        # whether or not the write itself succeeded -- safe to unlink now.
        path.unlink(missing_ok=True)
        raise ControlTokenPermissionError(f"could not write {label} at {path}: {error}") from error


def _read_token_text_without_toctou(path: Path, *, label: str) -> str:
    """Reads `path` through a SINGLE open, never a path-based check followed by a second,
    independently-resolved open that an attacker could have swapped the target of in
    between (a classic file-swap TOCTOU race).

    POSIX: `os.O_NOFOLLOW` makes the kernel refuse, atomically at open time, if the final
    path component is a symlink -- there is no window to race.
    Windows: a raw `CreateFileW` handle opened with `FILE_FLAG_OPEN_REPARSE_POINT` reveals
    (rather than transparently follows) a reparse point -- a symlink or an NTFS junction --
    via `GetFileInformationByHandle` on that handle; the content is then read through that
    SAME handle, never a second, freshly-resolved path."""
    if os.name != "nt":
        try:
            posix_fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        except OSError as error:
            raise ControlTokenPermissionError(
                f"could not open {label} at {path} without following a symlink: {error}"
            ) from error
        with os.fdopen(posix_fd, "r", encoding="utf-8") as stream:
            return stream.read()
    handle = _kernel32.CreateFileW(
        str(path),
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        error_code = ctypes.get_last_error()
        if error_code in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
            raise FileNotFoundError(f"{label} at {path} does not exist")
        raise ControlTokenPermissionError(
            f"could not open {label} at {path}: Win32 error {error_code}"
        )
    fd: int | None = None
    try:
        info = _ByHandleFileInformation()
        if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ControlTokenPermissionError(
                f"could not inspect {label} at {path}: Win32 error {ctypes.get_last_error()}"
            )
        if info.dwFileAttributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ControlTokenPermissionError(
                f"refusing to use {label} at {path}: it is a reparse point (for example an "
                "NTFS junction or a symlink) discovered on the handle actually opened for "
                "reading -- there is no separate, later open for a swap to race against"
            )
        import msvcrt  # Windows-only stdlib module; a top-level import would break POSIX

        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    finally:
        if fd is None:
            _kernel32.CloseHandle(handle)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        return stream.read()


def write_control_token(safety_directory: Path, *, pid: int, port: int, capability: str) -> str:
    """Called once, by the console itself, right after it binds its port. Returns the raw
    token; the caller keeps it only in memory (never logs it) to authenticate the one route
    that accepts it.

    Raises `ControlTokenPermissionError` -- never silently degrades -- if a symlink or
    reparse point is found anywhere along the path, if this process's own start-time
    identity cannot be established, or if permissions cannot be narrowed and verified on
    either the `console-control` directory or the token file itself. On any such failure,
    any partial file this call created is removed before the error propagates."""
    _reject_if_symlink(safety_directory, label="the safety directory")
    directory = control_token_path(safety_directory, port=port).parent
    path = control_token_path(safety_directory, port=port)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    created_temp = False
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
        # `created_temp` tracks whether THIS call is the one that brought `temporary`
        # into existence -- the exclusive create below either creates it atomically or
        # raises without creating anything (see `_create_token_text_exclusively`), so the
        # flag below is only ever set once we KNOW we own it. The `except` block uses it
        # to decide whether to unlink: if `_create_token_text_exclusively` itself failed
        # (e.g. something was already there, planted in the TOCTOU window the exclusive
        # create exists to close), that something is NOT ours to delete.
        _create_token_text_exclusively(
            temporary, json.dumps(payload), label="the control token temp file"
        )
        created_temp = True
        _restrict_to_current_user(temporary)
        temporary.replace(path)
        created_temp = False  # ownership moved to `path` via the rename
        _restrict_to_current_user(path)
    except ControlTokenPermissionError:
        if created_temp:
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
        raw = json.loads(_read_token_text_without_toctou(path, label="the control token file"))
    except ControlTokenPermissionError:
        raise
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
