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
    user only (created owner-only on Windows, `chmod` on POSIX) and the narrowing is read back
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

SECURITY HARDENING (MILESTONE-098 follow-up, two rounds, then M098-R). Closed deliberately, without
changing the shape of the design above:
  1. FAIL CLOSED ON PERMISSIONS, VERIFIED BY SID. Narrowing a file or directory's permissions
     to the current OS user is not best-effort: a failure to apply it, or to verify afterward
     that it actually took effect, raises `ControlTokenPermissionError` instead of only
     logging. The caller (`operator_console._install_shutdown_control`) catches exactly this
     and does NOT register the `/control/shutdown` route -- the console keeps running its
     normal read-only/recovery functions, but the shutdown interface itself never activates.
     This also applies to the `console-control` DIRECTORY, not only the token file inside it.
     Verification is by SID, read natively (the process token's user SID; every ACE of the
     DACL read with `GetSecurityInfo`), never by account display NAME: a name such as
     "Everyone" is itself localized on a non-English Windows installation (and is in
     principle renameable), while its well-known SID (`S-1-1-0`) never changes. The current
     user's own identity is likewise taken from the OS token directly, never from the
     `USERNAME`/`USERDOMAIN` environment variables.
  4. M098-R (root-cause resolution). The checks above were first implemented by running
     `powershell` (`WindowsIdentity`, `Get-Acl`, `Get-Process`) and `icacls` as subprocesses,
     found through PATH. On the windows-latest runner Windows PowerShell 5.1 could not load its
     own security module when started from a PowerShell 7 host, so every token write failed
     closed and 24 tests failed; a console or deployment started from a PowerShell 7 terminal
     would equally never have activated the route. Every Windows query is now a direct Win32
     call. With that, the rules were also tightened:
       - the token file and directory are CREATED with an owner-only, protected security
         descriptor (owner = current user; full control for the user, SYSTEM and
         Administrators only), so they never exist with inherited permissions;
       - verification is an ALLOWLIST (the user, SYSTEM, Administrators) and also refuses a
         NULL or unprotected DACL, inherited or unsupported ACE types, and a foreign owner --
         the previous check was a denylist of four broad SIDs, so a grant to any other
         specific account passed;
       - the deployment tool re-verifies the file's permissions when it READS the token;
       - every open checks that the object actually opened lives at exactly the requested
         path (`GetFinalPathNameByHandleW`), which reveals a junction or symlink on ANY
         ancestor directory, not only on the final component;
       - process identity and exit are observed on a process HANDLE, which keeps referring to
         the original process even if its PID is reused.
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
    "close_process_handle",
    "control_token_path",
    "open_process_for_shutdown",
    "process_handle_fingerprint",
    "process_start_fingerprint",
    "read_control_token",
    "remove_control_token",
    "wait_for_process_exit",
    "windows_process_is_running",
    "windows_tcp_listeners",
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
    # M098-R: every Windows identity, ACL and process query below is a direct Win32 call.
    # The earlier `powershell`/`icacls` subprocesses resolved their executables through PATH
    # and failed whenever Windows PowerShell 5.1 could not load its own security module (it
    # cannot when launched from a PowerShell 7 host: 24 tests failed that way on the
    # windows-latest runner), so the security checks depended on how the caller was started.
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.OpenProcess.restype = ctypes.c_void_p
    _kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    _kernel32.GetProcessTimes.restype = ctypes.c_int
    _kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_uint64)] * 4
    _kernel32.GetExitCodeProcess.restype = ctypes.c_int
    _kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    _kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.CreateDirectoryW.restype = ctypes.c_int
    _kernel32.CreateDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    _kernel32.GetFinalPathNameByHandleW.restype = ctypes.c_uint32
    _kernel32.GetFinalPathNameByHandleW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    _kernel32.GetLongPathNameW.restype = ctypes.c_uint32
    _kernel32.GetLongPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    _advapi32.OpenProcessToken.restype = ctypes.c_int
    _advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.GetTokenInformation.restype = ctypes.c_int
    _advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _advapi32.ConvertSidToStringSidW.restype = ctypes.c_int
    _advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = ctypes.c_int
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _advapi32.GetSecurityDescriptorDacl.restype = ctypes.c_int
    _advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int),
    ]
    _advapi32.GetSecurityDescriptorControl.restype = ctypes.c_int
    _advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _advapi32.GetSecurityInfo.restype = ctypes.c_uint32
    _advapi32.GetSecurityInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.SetSecurityInfo.restype = ctypes.c_uint32
    _advapi32.SetSecurityInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _advapi32.GetAce.restype = ctypes.c_int
    _advapi32.GetAce.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]


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
        handle = open_process_for_shutdown(pid)
        try:
            # An exited process stays openable while anyone still holds a handle to it; its
            # start time must never stand in for a live process's identity.
            if wait_for_process_exit(handle, timeout_seconds=0):
                raise RuntimeError(f"PID {pid} has already exited")
            return process_handle_fingerprint(handle)
        finally:
            _kernel32.CloseHandle(handle)
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


_PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_SYNCHRONIZE: Final = 0x00100000
_STILL_ACTIVE: Final = 259
_WAIT_OBJECT_0: Final = 0x0
_WAIT_TIMEOUT: Final = 0x102
_ERROR_INVALID_PARAMETER: Final = 87


def open_process_for_shutdown(pid: int) -> int:
    """Windows only. A handle to the process object itself (query + wait rights), so that its
    start time and, later, its exit are observed on THAT process object: a handle keeps
    referring to the original process even if its PID is released and reused, which a
    PID-based poll can never guarantee. Raises `RuntimeError` if `pid` does not exist or
    cannot be opened. The caller owns the handle and must `close_process_handle` it."""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, 0, int(pid))
    if not handle:
        raise RuntimeError(
            f"could not open PID {pid} to confirm its identity: "
            f"Win32 error {ctypes.get_last_error()}"
        )
    return int(handle)


def close_process_handle(handle: int) -> None:
    _kernel32.CloseHandle(handle)


def process_handle_fingerprint(handle: int) -> str:
    """The OS creation time (100 ns FILETIME ticks) of the process behind `handle`. Two
    processes can share a PID one after the other; they cannot share a creation time."""
    created, exited, kernel, user = (ctypes.c_uint64() for _ in range(4))
    if not _kernel32.GetProcessTimes(
        handle,
        ctypes.byref(created),
        ctypes.byref(exited),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise RuntimeError(f"GetProcessTimes failed: Win32 error {ctypes.get_last_error()}")
    return f"win-filetime:{created.value}"


def wait_for_process_exit(handle: int, *, timeout_seconds: float) -> bool:
    """True only once the process object behind `handle` has actually terminated."""
    milliseconds = max(0, int(timeout_seconds * 1000))
    result = _kernel32.WaitForSingleObject(handle, milliseconds)
    if result == _WAIT_OBJECT_0:
        return True
    if result == _WAIT_TIMEOUT:
        return False
    raise RuntimeError(f"WaitForSingleObject failed: Win32 error {ctypes.get_last_error()}")


def windows_process_is_running(pid: int) -> bool:
    """Windows only. False only when the OS confirms there is no such process (or it has
    exited). An error that leaves the answer unknown (for example access denied) is reported
    as running: a caller waiting for an exit must never mistake "could not tell" for
    "stopped"."""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, int(pid))
    if not handle:
        return ctypes.get_last_error() != _ERROR_INVALID_PARAMETER
    try:
        code = ctypes.c_uint32()
        if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        _kernel32.CloseHandle(handle)


_AF_INET: Final = 2
_AF_INET6: Final = 23
_TCP_TABLE_OWNER_PID_LISTENER: Final = 3
_ERROR_INSUFFICIENT_BUFFER: Final = 122


def windows_tcp_listeners(port: int) -> list[tuple[str, int]]:
    """Windows only. Every (local address, owning PID) LISTENING on TCP `port`, IPv4 and IPv6,
    read from the OS connection table (`GetExtendedTcpTable`) -- not by parsing `netstat`
    output, whose state column is localized (it does not say "LISTENING" on a German or
    French Windows) and whose executable is found through PATH. Raises `RuntimeError` if the
    table cannot be read: "could not determine" must never look like "nobody is listening"."""
    import ipaddress
    import struct

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = iphlpapi.GetExtendedTcpTable
    get_table.restype = ctypes.c_uint32
    get_table.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint32,
    ]
    found: list[tuple[str, int]] = []
    for family, row_size in ((_AF_INET, 24), (_AF_INET6, 56)):
        size = ctypes.c_uint32(0)
        buffer = ctypes.create_string_buffer(0)
        for _attempt in range(5):
            status = get_table(
                buffer, ctypes.byref(size), 0, family, _TCP_TABLE_OWNER_PID_LISTENER, 0
            )
            if status == 0:
                break
            if status != _ERROR_INSUFFICIENT_BUFFER:
                raise RuntimeError(f"GetExtendedTcpTable failed (family {family}): error {status}")
            buffer = ctypes.create_string_buffer(size.value)
        else:
            raise RuntimeError(
                "GetExtendedTcpTable kept growing; could not read the listener table"
            )
        raw = buffer.raw
        count = struct.unpack_from("<I", raw, 0)[0]
        for index in range(count):
            offset = 4 + index * row_size
            if family == _AF_INET:
                _state, addr, local_port, _ra, _rp, pid = struct.unpack_from("<6I", raw, offset)
                address = str(ipaddress.IPv4Address(struct.pack("<I", addr)))
            else:
                # MIB_TCP6ROW_OWNER_PID: local address [0:16], scope id, local port at 20,
                # remote address, scope id, port, state, owning PID at 52.
                address = str(ipaddress.IPv6Address(raw[offset : offset + 16]))
                local_port = struct.unpack_from("<I", raw, offset + 20)[0]
                pid = struct.unpack_from("<I", raw, offset + 52)[0]
            if socket_port_from_network_order(local_port) == port:
                found.append((address, pid))
    return found


def socket_port_from_network_order(value: int) -> int:
    """The TCP tables store ports as a network-byte-order 16-bit value in a DWORD."""
    low = value & 0xFFFF
    return ((low & 0xFF) << 8) | (low >> 8)


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


_TOKEN_QUERY: Final = 0x0008
_TOKEN_USER_CLASS: Final = 1
_SE_FILE_OBJECT: Final = 1
_OWNER_SECURITY_INFORMATION: Final = 0x00000001
_DACL_SECURITY_INFORMATION: Final = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION: Final = 0x80000000
_SDDL_REVISION_1: Final = 1
_SE_DACL_PROTECTED: Final = 0x1000
_ACCESS_ALLOWED_ACE_TYPE: Final = 0
_ACCESS_DENIED_ACE_TYPE: Final = 1
_INHERITED_ACE: Final = 0x10
_READ_CONTROL: Final = 0x00020000
_WRITE_DAC: Final = 0x00040000
_FILE_SHARE_DELETE: Final = 0x00000004
_ERROR_ALREADY_EXISTS: Final = 183

#: The only principals a narrowed control file or directory may grant anything to, besides the
#: current user: the machine's own OS and administrators, who can read any file on this disk by
#: other means anyway. An ALLOWLIST: any other principal at all -- a broad group, another local
#: account, a service account -- fails verification. (The previous check was a denylist of four
#: well-known broad SIDs, so a grant to any other specific account passed unnoticed.)
_MACHINE_PRINCIPAL_SIDS: Final = (
    "S-1-5-18",  # LocalSystem
    "S-1-5-32-544",  # BUILTIN\Administrators
)


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("sid", ctypes.c_void_p), ("attributes", ctypes.c_uint32)]


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("nLength", ctypes.c_uint32),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", ctypes.c_int),
    ]


@dataclass(frozen=True, slots=True)
class _WindowsAce:
    ace_type: int
    flags: int
    sid: str | None


@dataclass(frozen=True, slots=True)
class _WindowsSecurity:
    """What a file or directory's security descriptor actually says, read from an open handle."""

    owner_sid: str
    dacl_null: bool
    protected: bool
    aces: tuple[_WindowsAce, ...]


def _sid_to_string(sid_pointer: int) -> str:
    text = ctypes.c_void_p()
    if not _advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(text)):
        raise ControlTokenPermissionError(
            f"could not convert a SID to text: Win32 error {ctypes.get_last_error()}"
        )
    try:
        if text.value is None:
            raise ControlTokenPermissionError("ConvertSidToStringSidW returned no text")
        return ctypes.wstring_at(text.value)
    finally:
        _kernel32.LocalFree(text)


def _current_windows_user_sid() -> str:
    """The current process's own user SID, read from its access token -- never from the
    `USERNAME`/`USERDOMAIN` environment variables, which name a principal but do not identify
    one, and never through a PowerShell subprocess whose environment can break it."""
    token = ctypes.c_void_p()
    if not _advapi32.OpenProcessToken(
        _kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise ControlTokenPermissionError(
            "could not open this process's token to determine the current Windows user's SID: "
            f"Win32 error {ctypes.get_last_error()}"
        )
    try:
        needed = ctypes.c_uint32()
        _advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(max(needed.value, ctypes.sizeof(_SidAndAttributes)))
        if not _advapi32.GetTokenInformation(
            token, _TOKEN_USER_CLASS, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)
        ):
            raise ControlTokenPermissionError(
                "could not determine the current Windows user's SID: "
                f"Win32 error {ctypes.get_last_error()}"
            )
        user = _SidAndAttributes.from_buffer(buffer)
        return _sid_to_string(user.sid)
    finally:
        _kernel32.CloseHandle(token)


def _read_windows_security(handle: int) -> _WindowsSecurity:
    """The owner and every ACE of the DACL of the object behind `handle`, each principal by
    SID (locale- and rename-independent), including each ACE's type and inheritance flags."""
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = _advapi32.GetSecurityInfo(
        handle,
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if status != 0:
        raise ControlTokenPermissionError(
            f"could not read the security descriptor: Win32 error {status}"
        )
    try:
        control = ctypes.c_uint16()
        revision = ctypes.c_uint32()
        if not _advapi32.GetSecurityDescriptorControl(
            descriptor, ctypes.byref(control), ctypes.byref(revision)
        ):
            raise ControlTokenPermissionError(
                "could not read the security descriptor's control flags: "
                f"Win32 error {ctypes.get_last_error()}"
            )
        aces: list[_WindowsAce] = []
        if dacl.value:
            ace_count = ctypes.c_uint16.from_address(dacl.value + 4).value
            for index in range(ace_count):
                ace = ctypes.c_void_p()
                if not _advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                    raise ControlTokenPermissionError(
                        f"could not read ACE {index}: Win32 error {ctypes.get_last_error()}"
                    )
                address = ace.value
                if address is None:
                    raise ControlTokenPermissionError(f"ACE {index} has no address")
                ace_type = ctypes.c_uint8.from_address(address).value
                flags = ctypes.c_uint8.from_address(address + 1).value
                sid = (
                    _sid_to_string(address + 8)
                    if ace_type in (_ACCESS_ALLOWED_ACE_TYPE, _ACCESS_DENIED_ACE_TYPE)
                    else None
                )
                aces.append(_WindowsAce(ace_type=ace_type, flags=flags, sid=sid))
        if owner.value is None:
            raise ControlTokenPermissionError("the security descriptor names no owner")
        return _WindowsSecurity(
            owner_sid=_sid_to_string(owner.value),
            dacl_null=not dacl.value,
            protected=bool(control.value & _SE_DACL_PROTECTED),
            aces=tuple(aces),
        )
    finally:
        _kernel32.LocalFree(descriptor)


def _check_windows_security(security: _WindowsSecurity, user_sid: str, *, path: Path) -> None:
    """FAIL CLOSED unless the descriptor grants access only to the current user and the
    machine's own principals. Pure logic (no OS access), so every rule is unit-testable on
    any platform:
      * a NULL DACL grants everyone everything;
      * an unprotected DACL keeps inheriting whatever its parent grants later;
      * an inherited ACE is a grant this code did not write;
      * an ACE type other than plain allow/deny (object, callback, conditional ACEs) cannot be
        judged here and is refused rather than guessed about;
      * an allow ACE for any principal outside the allowlist exposes the token;
      * an owner outside the allowlist can rewrite the DACL at any time;
      * the current user must actually hold an allow ACE, or the file is not "ours"."""
    allowed = {user_sid, *_MACHINE_PRINCIPAL_SIDS}
    problems: list[str] = []
    if security.dacl_null:
        problems.append("it has a NULL DACL (full access for everyone)")
    if not security.protected:
        problems.append("its DACL is not protected from inheritance")
    if security.owner_sid not in allowed:
        problems.append(f"its owner is an unexpected principal ({security.owner_sid})")
    for ace in security.aces:
        if ace.flags & _INHERITED_ACE:
            problems.append(f"it carries an inherited ACE ({ace.sid or f'type {ace.ace_type}'})")
        if ace.ace_type not in (_ACCESS_ALLOWED_ACE_TYPE, _ACCESS_DENIED_ACE_TYPE):
            problems.append(f"it carries an ACE of unsupported type {ace.ace_type}")
        elif ace.ace_type == _ACCESS_ALLOWED_ACE_TYPE and ace.sid not in allowed:
            problems.append(f"it grants access to an unexpected principal ({ace.sid})")
    if not any(
        ace.ace_type == _ACCESS_ALLOWED_ACE_TYPE and ace.sid == user_sid for ace in security.aces
    ):
        problems.append(f"it does not grant the current user's SID ({user_sid})")
    if problems:
        raise ControlTokenPermissionError(
            f"refusing to trust the permissions on {path}: " + "; ".join(problems)
        )


def _normalized_windows_path(text: str) -> str:
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[len("\\\\?\\UNC\\") :]
    elif text.startswith("\\\\?\\"):
        text = text[len("\\\\?\\") :]
    return os.path.normcase(os.path.normpath(text))


def _long_path(path: Path) -> str:
    absolute = os.path.abspath(str(path))
    buffer = ctypes.create_unicode_buffer(32768)
    length = _kernel32.GetLongPathNameW(absolute, buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) else absolute


def _verify_handle_is_the_expected_object(handle: int, path: Path, *, label: str) -> None:
    """The object actually opened must be a plain file or directory, at exactly the path
    that was asked for. Checking only the final component (as `_reject_if_symlink` does) misses
    a junction or symlink on ANY ancestor, which silently redirects every component below it;
    the path the OS reports for the opened handle reveals any such redirection, and it is the
    handle -- not the name -- that every later read or write goes through."""
    info = _ByHandleFileInformation()
    if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ControlTokenPermissionError(
            f"could not inspect {label} at {path}: Win32 error {ctypes.get_last_error()}"
        )
    if info.dwFileAttributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ControlTokenPermissionError(
            f"refusing to use {label} at {path}: it is a reparse point (for example an NTFS "
            "junction or a symlink) discovered on the handle actually opened"
        )
    buffer = ctypes.create_unicode_buffer(32768)
    length = _kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if not 0 < length < len(buffer):
        raise ControlTokenPermissionError(
            f"could not resolve the real location of {label} at {path}: "
            f"Win32 error {ctypes.get_last_error()}"
        )
    actual = _normalized_windows_path(buffer.value)
    expected = _normalized_windows_path(_long_path(path))
    if actual != expected:
        raise ControlTokenPermissionError(
            f"refusing to use {label} at {path}: the opened object really lives at {buffer.value} "
            "(a junction, symlink or mount point somewhere on the path redirects it)"
        )


def _open_windows_object(path: Path, *, access: int, label: str) -> int:
    handle = _kernel32.CreateFileW(
        str(path),
        access,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
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
    return int(handle)


def _owner_only_descriptor(user_sid: str, *, directory: bool) -> ctypes.c_void_p:
    """A self-relative security descriptor: owner = the current user; a PROTECTED DACL granting
    full control only to the current user, SYSTEM and Administrators. Applied at creation, so
    the object never exists for a moment with inherited (possibly broader) permissions."""
    inherit = "OICI" if directory else ""
    sddl = f"O:{user_sid}D:P(A;{inherit};FA;;;{user_sid})(A;{inherit};FA;;;SY)(A;{inherit};FA;;;BA)"
    descriptor = ctypes.c_void_p()
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, _SDDL_REVISION_1, ctypes.byref(descriptor), None
    ):
        raise ControlTokenPermissionError(
            "could not build an owner-only security descriptor: "
            f"Win32 error {ctypes.get_last_error()}"
        )
    return descriptor


def _verify_windows_path(path: Path, user_sid: str, *, label: str) -> None:
    handle = _open_windows_object(path, access=_READ_CONTROL, label=label)
    try:
        _verify_handle_is_the_expected_object(handle, path, label=label)
        _check_windows_security(_read_windows_security(handle), user_sid, path=path)
    finally:
        _kernel32.CloseHandle(handle)


def _create_owner_only_directory(path: Path, user_sid: str) -> None:
    """Creates `path` with the owner-only descriptor, or -- if it already exists -- replaces its
    DACL through a handle opened without following a reparse point, then verifies it."""
    descriptor = _owner_only_descriptor(user_sid, directory=True)
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, 0)
        if not _kernel32.CreateDirectoryW(str(path), ctypes.byref(attributes)):
            error_code = ctypes.get_last_error()
            if error_code != _ERROR_ALREADY_EXISTS:
                raise ControlTokenPermissionError(
                    f"could not create the console-control directory at {path}: "
                    f"Win32 error {error_code}"
                )
            handle = _open_windows_object(
                path, access=_READ_CONTROL | _WRITE_DAC, label="the console-control directory"
            )
            try:
                _verify_handle_is_the_expected_object(
                    handle, path, label="the console-control directory"
                )
                present = ctypes.c_int()
                dacl = ctypes.c_void_p()
                defaulted = ctypes.c_int()
                if not _advapi32.GetSecurityDescriptorDacl(
                    descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
                ):
                    raise ControlTokenPermissionError(
                        f"could not read the owner-only DACL: Win32 error {ctypes.get_last_error()}"
                    )
                status = _advapi32.SetSecurityInfo(
                    handle,
                    _SE_FILE_OBJECT,
                    _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
                    None,
                    None,
                    dacl,
                    None,
                )
                if status != 0:
                    raise ControlTokenPermissionError(
                        f"could not narrow the permissions on {path}: Win32 error {status}"
                    )
            finally:
                _kernel32.CloseHandle(handle)
    finally:
        _kernel32.LocalFree(descriptor)
    _verify_windows_path(path, user_sid, label="the console-control directory")


def _restrict_to_current_user(path: Path, *, posix_mode: int = 0o600) -> None:
    """POSIX only (Windows objects are created owner-only and verified instead). FAIL CLOSED:
    raises `ControlTokenPermissionError` if narrowing cannot be applied or verified."""
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


def _create_token_text_exclusively(
    path: Path, text: str, *, label: str, user_sid: str = ""
) -> None:
    """Creates `path` using the OS's own exclusive-create guarantee -- `O_EXCL` (POSIX) or
    `CREATE_NEW` (Windows) -- so anything already at this exact name makes the create itself
    fail closed. On Windows the file is created with the owner-only security descriptor in the
    same call, so it never exists with inherited permissions, and the handle is checked to be
    exactly the expected file before anything is written through it."""
    data = text.encode("utf-8")
    if os.name != "nt":
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o600)
        except OSError as error:
            raise ControlTokenPermissionError(
                f"could not exclusively create {label} at {path}: {error}"
            ) from error
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
        except OSError as error:
            path.unlink(missing_ok=True)
            raise ControlTokenPermissionError(
                f"could not write {label} at {path}: {error}"
            ) from error
        return
    descriptor = _owner_only_descriptor(user_sid, directory=False)
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, 0)
        handle = _kernel32.CreateFileW(
            str(path),
            _GENERIC_WRITE | _READ_CONTROL,
            _FILE_SHARE_READ,
            ctypes.byref(attributes),
            _CREATE_NEW,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
    finally:
        _kernel32.LocalFree(descriptor)
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        # CREATE_NEW guarantees the create and the failure are atomic: nothing was created.
        raise ControlTokenPermissionError(
            f"could not exclusively create {label} at {path}: Win32 error {ctypes.get_last_error()}"
        )
    import msvcrt  # Windows-only stdlib module; a top-level import would break POSIX

    win_fd: int | None = None
    try:
        _verify_handle_is_the_expected_object(handle, path, label=label)
        _check_windows_security(_read_windows_security(handle), user_sid, path=path)
        win_fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except (ControlTokenPermissionError, OSError) as error:
        if win_fd is None:
            _kernel32.CloseHandle(handle)
        path.unlink(missing_ok=True)
        if isinstance(error, ControlTokenPermissionError):
            raise
        raise ControlTokenPermissionError(f"could not write {label} at {path}: {error}") from error
    try:
        with os.fdopen(win_fd, "wb") as stream:
            stream.write(data)
    except OSError as error:
        path.unlink(missing_ok=True)
        raise ControlTokenPermissionError(f"could not write {label} at {path}: {error}") from error


def _read_token_text_without_toctou(path: Path, *, label: str) -> str:
    """Reads `path` through a SINGLE open, never a path-based check followed by a second,
    independently-resolved open that an attacker could have swapped in between.

    POSIX: `os.O_NOFOLLOW` makes the kernel refuse, atomically at open time, if the final
    path component is a symlink.
    Windows: one handle, opened without following a reparse point, is checked to be a plain
    file at exactly the requested path (no junction or symlink on any ancestor either), and
    its permissions are verified by SID against the allowlist -- AT READ TIME, not only when
    the console wrote it -- before the content is read through that same handle."""
    if os.name != "nt":
        try:
            posix_fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        except OSError as error:
            raise ControlTokenPermissionError(
                f"could not open {label} at {path} without following a symlink: {error}"
            ) from error
        with os.fdopen(posix_fd, "r", encoding="utf-8") as stream:
            return stream.read()
    handle = _open_windows_object(path, access=_GENERIC_READ | _READ_CONTROL, label=label)
    fd: int | None = None
    try:
        _verify_handle_is_the_expected_object(handle, path, label=label)
        _check_windows_security(
            _read_windows_security(handle), _current_windows_user_sid(), path=path
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
    identity cannot be established, or if owner-only permissions cannot be established and
    verified on either the `console-control` directory or the token file itself. On any such
    failure, any partial file this call created is removed before the error propagates."""
    _reject_if_symlink(safety_directory, label="the safety directory")
    directory = control_token_path(safety_directory, port=port).parent
    path = control_token_path(safety_directory, port=port)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    created_temp = False
    user_sid = ""
    try:
        if os.name == "nt":
            user_sid = _current_windows_user_sid()
            safety_directory.mkdir(parents=True, exist_ok=True)
            _reject_if_symlink(directory, label="the console-control directory")
            _create_owner_only_directory(directory, user_sid)
        else:
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
        # `created_temp` is set only once the exclusive create has succeeded: a file that was
        # already at that name (planted in a race) is NOT ours, and is never deleted by us.
        _create_token_text_exclusively(
            temporary, json.dumps(payload), label="the control token temp file", user_sid=user_sid
        )
        created_temp = True
        if os.name != "nt":
            _restrict_to_current_user(temporary)
        temporary.replace(path)
        created_temp = False  # ownership moved to `path` via the rename
        if os.name == "nt":
            _verify_windows_path(path, user_sid, label="the control token file")
        else:
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
