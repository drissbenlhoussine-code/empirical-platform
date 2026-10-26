"""MILESTONE-098: unit coverage for `shared.console_control` (the token file read/write/
remove contract) and `_operator_console_web.Router.service_post` (the dispatch rule that
lets exactly one route skip CSRF/session cookie handling for a machine-to-machine caller).

Real OS process/port mechanics and the real console's `/control/shutdown` route wiring are
covered by `tests/integration/test_m098_windows_console_shutdown.py` (Windows-only, real
subprocesses) and by the updated dummy console in
`tests/integration/test_v1_personal_paper_deploy_postgres.py`. This file is fakes/tmp_path
only -- no real socket, no real subprocess.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from empirical_platform.entrypoints import operator_console
from empirical_platform.entrypoints._operator_console_web import (
    Request,
    Response,
    Router,
    SecuritySession,
    html_response,
)
from empirical_platform.shared import console_control

_SELF_PID = os.getpid()
_SELF_FINGERPRINT = console_control.process_start_fingerprint(_SELF_PID)

# ---------------------------------------------------------------------------------------
# write_control_token / read_control_token / remove_control_token
#
# `write_control_token` establishes ITS OWN identity via `os.getpid()` (never the `pid`
# kwarg, which only ends up in the payload for the caller's own bookkeeping) -- so every
# token written by this test process carries `_SELF_FINGERPRINT`, real and independently
# re-derivable, regardless of what fake `pid` value a test passes.
# ---------------------------------------------------------------------------------------


def test_write_then_read_round_trips_with_matching_identity(tmp_path: Path) -> None:
    token = console_control.write_control_token(
        tmp_path, pid=4242, port=8189, capability="paper-exit"
    )
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability="paper-exit",
        expected_pid=4242,
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )
    assert record.token == token
    assert record.pid == 4242
    assert record.port == 8189
    assert record.capability == "paper-exit"
    assert record.start_fingerprint == _SELF_FINGERPRINT


def test_read_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(console_control.ControlTokenError, match="no readable control token"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_read_refuses_malformed_json(tmp_path: Path) -> None:
    path = console_control.control_token_path(tmp_path, port=8189)
    _plant(path, "{not json")
    with pytest.raises(console_control.ControlTokenError, match="no readable control token"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_read_refuses_a_missing_field(tmp_path: Path) -> None:
    path = console_control.control_token_path(tmp_path, port=8189)
    _plant(path, json.dumps({"pid": 4242, "port": 8189}))
    with pytest.raises(console_control.ControlTokenError, match="malformed"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_read_refuses_a_capability_mismatch(tmp_path: Path) -> None:
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="simulation")
    with pytest.raises(console_control.ControlTokenError, match="capability"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_read_refuses_a_port_field_mismatch(tmp_path: Path) -> None:
    """Simulates manual tampering: the file lives at the path for port 8189 (so it IS the
    file this port's caller would read) but its own recorded `port` field disagrees."""
    path = console_control.control_token_path(tmp_path, port=8189)
    payload = {
        "pid": 4242,
        "port": 9999,
        "capability": "paper-exit",
        "started_utc": "2026-01-01T00:00:00+00:00",
        "start_fingerprint": _SELF_FINGERPRINT,
        "token": "deadbeef",
    }
    _plant(path, json.dumps(payload))
    with pytest.raises(console_control.ControlTokenError, match="different port"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_read_refuses_a_pid_mismatch_defeating_pid_reuse(tmp_path: Path) -> None:
    """The caller must independently confirm, at the OS level, which PID really owns the
    port right now, and pass THAT as `expected_pid` -- a stale file naming an old PID that
    has since been reused by an unrelated process must never be trusted."""
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    with pytest.raises(console_control.ControlTokenError, match="PID reuse"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=9999,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_read_refuses_a_stale_token_whose_start_fingerprint_no_longer_matches(
    tmp_path: Path,
) -> None:
    """MILESTONE-098 SECURITY HARDENING: a bare PID match is not enough. A token file left
    over from a process that has since exited, whose PID the OS has already reused for a
    DIFFERENT process the caller is now (correctly) asking about, must still be refused --
    even though `expected_pid` now matches the file's recorded `pid` -- because the two
    processes started at different times."""
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    with pytest.raises(console_control.ControlTokenError, match="start-time fingerprint"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint="a completely different, unrelated fingerprint",
        )


def test_the_raw_token_never_appears_in_any_mismatch_error_message(tmp_path: Path) -> None:
    token = console_control.write_control_token(
        tmp_path, pid=4242, port=8189, capability="paper-exit"
    )
    for expected_capability, expected_pid in (("simulation", 4242), ("paper-exit", 1)):
        with pytest.raises(console_control.ControlTokenError) as excinfo:
            console_control.read_control_token(
                tmp_path,
                port=8189,
                expected_capability=expected_capability,
                expected_pid=expected_pid,
                expected_start_fingerprint=_SELF_FINGERPRINT,
            )
        assert token not in str(excinfo.value)


def test_remove_control_token_deletes_the_file(tmp_path: Path) -> None:
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    path = console_control.control_token_path(tmp_path, port=8189)
    assert path.exists()
    console_control.remove_control_token(tmp_path, port=8189)
    assert not path.exists()


def test_remove_control_token_is_a_no_op_when_nothing_exists(tmp_path: Path) -> None:
    console_control.remove_control_token(tmp_path, port=8189)  # must not raise


def test_different_ports_use_different_files_and_do_not_collide(tmp_path: Path) -> None:
    console_control.write_control_token(tmp_path, pid=1, port=8189, capability="paper-exit")
    console_control.write_control_token(tmp_path, pid=2, port=9000, capability="paper-exit")
    first = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability="paper-exit",
        expected_pid=1,
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )
    second = console_control.read_control_token(
        tmp_path,
        port=9000,
        expected_capability="paper-exit",
        expected_pid=2,
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )
    assert first.pid == 1
    assert second.pid == 2


# ---------------------------------------------------------------------------------------
# MILESTONE-098 SECURITY HARDENING: permission narrowing is FAIL CLOSED -- a failure to
# apply or verify it raises `ControlTokenPermissionError`, and `write_control_token` cleans
# up any partial file before the error propagates.
#
# M098-R: on Windows the identity, ACL and process checks are native Win32 calls. The
# previous `powershell`/`icacls` subprocesses failed on the windows-latest runner (Windows
# PowerShell 5.1 cannot load its own security module when launched from a PowerShell 7
# host), which made 24 tests fail and would equally disable the shutdown route on any host
# started that way.
# ---------------------------------------------------------------------------------------

_WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows security descriptors")
_FAKE_USER = "S-1-5-21-1111111111-2222222222-3333333333-1001"


def _plant(path: Path, text: str) -> None:
    """Writes a hand-made token file the way the console would: on Windows with the owner-only
    descriptor (a plain `write_text` file inherits its directory's ACL and is, correctly,
    refused at read time now), elsewhere as a plain file."""
    if os.name == "nt":
        user_sid = console_control._current_windows_user_sid()  # noqa: SLF001
        path.parent.parent.mkdir(parents=True, exist_ok=True)
        console_control._create_owner_only_directory(path.parent, user_sid)  # noqa: SLF001
        console_control._create_token_text_exclusively(path, text, label="test", user_sid=user_sid)  # noqa: SLF001
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _security(
    *aces: tuple[int, int, str | None],
    owner: str = _FAKE_USER,
    null: bool = False,
    protected: bool = True,
) -> object:
    return console_control._WindowsSecurity(  # noqa: SLF001
        owner_sid=owner,
        dacl_null=null,
        protected=protected,
        aces=tuple(console_control._WindowsAce(t, f, s) for t, f, s in aces),  # noqa: SLF001
    )


_ALLOW = 0
_DENY = 1


def test_acl_rules_accept_only_the_user_system_and_administrators() -> None:
    """Pure logic, every platform: the allowlist. SYSTEM and Administrators may hold explicit
    grants (they can read any file on this disk anyway); deny ACEs are harmless."""
    console_control._check_windows_security(  # noqa: SLF001
        _security(
            (_ALLOW, 0, _FAKE_USER),
            (_ALLOW, 0, "S-1-5-18"),
            (_ALLOW, 0, "S-1-5-32-544"),
            (_DENY, 0, "S-1-1-0"),
        ),
        _FAKE_USER,
        path=Path("token.json"),
    )


@pytest.mark.parametrize(
    ("security", "reason"),
    [
        (
            _security((_ALLOW, 0, _FAKE_USER), (_ALLOW, 0, "S-1-1-0")),
            "unexpected principal (S-1-1-0)",
        ),
        # The previous check was a denylist of four broad SIDs: a grant to any OTHER account
        # (another local user, a service, INTERACTIVE) passed unnoticed.
        (
            _security(
                (_ALLOW, 0, _FAKE_USER),
                (_ALLOW, 0, "S-1-5-21-1111111111-2222222222-3333333333-1002"),
            ),
            "unexpected principal",
        ),
        (
            _security((_ALLOW, 0, _FAKE_USER), (_ALLOW, 0, "S-1-5-4")),
            "unexpected principal (S-1-5-4)",
        ),
        (_security(null=True), "NULL DACL"),
        (_security((_ALLOW, 0, _FAKE_USER), protected=False), "not protected"),
        (_security((_ALLOW, 0x10, _FAKE_USER)), "inherited ACE"),
        (_security((_ALLOW, 0, _FAKE_USER), (5, 0, None)), "unsupported type 5"),
        (
            _security(
                (_ALLOW, 0, _FAKE_USER), owner="S-1-5-21-1111111111-2222222222-3333333333-1002"
            ),
            "owner",
        ),
        (_security((_ALLOW, 0, "S-1-5-18")), "does not grant the current user"),
    ],
)
def test_acl_rules_refuse_every_unsafe_or_ambiguous_descriptor(
    security: object, reason: str
) -> None:
    with pytest.raises(console_control.ControlTokenPermissionError, match=re.escape(reason)):
        console_control._check_windows_security(security, _FAKE_USER, path=Path("token.json"))  # type: ignore[arg-type]  # noqa: SLF001


def test_write_raises_and_cleans_up_when_permission_narrowing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise console_control.ControlTokenPermissionError("narrowing refused in this test")

    monkeypatch.setattr(console_control, "_create_owner_only_directory", _refuse)
    monkeypatch.setattr(
        console_control.Path,
        "chmod",
        lambda self, mode: (_ for _ in ()).throw(OSError("chmod refused")),
    )
    with pytest.raises(console_control.ControlTokenPermissionError):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    assert not console_control.control_token_path(tmp_path, port=8189).exists()
    assert list(tmp_path.rglob("*.tmp")) == []


@_WINDOWS_ONLY
def test_write_raises_and_cleans_up_when_the_written_file_fails_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Creating the file may appear to succeed; what is verified on the handle is what
    counts. An unexpected principal in the readback fails the write and leaves nothing."""
    real = console_control._read_windows_security  # noqa: SLF001

    def _with_an_extra_principal(handle: int) -> object:
        security = real(handle)
        return console_control._WindowsSecurity(  # noqa: SLF001
            owner_sid=security.owner_sid,
            dacl_null=False,
            protected=True,
            aces=(*security.aces, console_control._WindowsAce(0, 0, "S-1-5-11")),  # noqa: SLF001
        )

    monkeypatch.setattr(console_control, "_read_windows_security", _with_an_extra_principal)
    with pytest.raises(console_control.ControlTokenPermissionError, match="S-1-5-11"):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    assert not console_control.control_token_path(tmp_path, port=8189).exists()
    assert list(tmp_path.rglob("*.tmp")) == []


@_WINDOWS_ONLY
def test_write_raises_when_the_current_users_sid_cannot_be_determined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_sid() -> str:
        raise console_control.ControlTokenPermissionError(
            "could not determine the current Windows user's SID"
        )

    monkeypatch.setattr(console_control, "_current_windows_user_sid", _no_sid)
    with pytest.raises(console_control.ControlTokenPermissionError, match="SID"):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    assert not console_control.control_token_path(tmp_path, port=8189).exists()


@_WINDOWS_ONLY
def test_root_cause_writing_and_reading_needs_no_subprocess_and_no_working_powershell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M098-R ROOT CAUSE REGRESSION. The previous implementation shelled out to `powershell`
    and `icacls` (PATH-resolved) for the user SID, the ACL readback and the process start
    time; on the windows-latest runner Windows PowerShell 5.1 could not load its own
    security module, and every token write failed. Here every subprocess is forbidden and
    PowerShell's module path is deliberately broken: the write, the verification and the
    read must all still succeed."""

    def _forbidden(*args: object, **_kwargs: object) -> None:
        raise AssertionError(f"no subprocess may be used on Windows here: {args!r}")

    monkeypatch.setattr(console_control.subprocess, "run", _forbidden)
    monkeypatch.setattr(console_control.subprocess, "Popen", _forbidden)
    monkeypatch.setenv("PSModulePath", str(tmp_path / "no-such-modules"))
    token = console_control.write_control_token(
        tmp_path, pid=4242, port=8189, capability="paper-exit"
    )
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability="paper-exit",
        expected_pid=4242,
        expected_start_fingerprint=console_control.process_start_fingerprint(_SELF_PID),
    )
    assert record.token == token


@_WINDOWS_ONLY
def test_the_real_token_file_and_directory_are_owner_only_and_protected(tmp_path: Path) -> None:
    """Read back from the real files on this real Windows machine, by SID."""
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    user = console_control._current_windows_user_sid()  # noqa: SLF001
    for path in (
        tmp_path / "console-control",
        console_control.control_token_path(tmp_path, port=8189),
    ):
        handle = console_control._open_windows_object(
            path, access=console_control._READ_CONTROL, label="t"
        )  # noqa: SLF001
        try:
            security = console_control._read_windows_security(handle)  # noqa: SLF001
        finally:
            console_control._kernel32.CloseHandle(handle)  # noqa: SLF001
        assert security.protected, path
        assert not security.dacl_null, path
        assert security.owner_sid == user, path
        assert {ace.sid for ace in security.aces} <= {user, "S-1-5-18", "S-1-5-32-544"}, path
        assert not any(ace.flags & 0x10 for ace in security.aces), path


@_WINDOWS_ONLY
@pytest.mark.parametrize("principal", ["S-1-1-0", "S-1-5-4", "S-1-5-32-545"])
def test_read_refuses_a_token_file_whose_real_acl_was_widened_after_writing(
    tmp_path: Path, principal: str
) -> None:
    """The ACL is verified again when the deployment tool READS the token, not only when the
    console wrote it. Everyone, INTERACTIVE (which the old four-SID denylist allowed) and
    BUILTIN\\Users each get a real grant here via icacls -- a test-side tool, never used by
    the code under test."""
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    path = console_control.control_token_path(tmp_path, port=8189)
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
        ["icacls", str(path), "/grant", f"*{principal}:R"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"could not add a test grant: {result.stdout} {result.stderr}")
    with pytest.raises(console_control.ControlTokenPermissionError, match=re.escape(principal)):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


@_WINDOWS_ONLY
def test_read_refuses_a_token_file_with_inherited_permissions(tmp_path: Path) -> None:
    path = console_control.control_token_path(tmp_path, port=8189)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    with pytest.raises(
        console_control.ControlTokenPermissionError, match="refusing to trust the permissions"
    ):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def _junction(link: Path, target: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"this environment could not create an NTFS junction: {result.stderr}")


@_WINDOWS_ONLY
def test_a_junction_on_an_ancestor_directory_is_refused_for_write_and_read(tmp_path: Path) -> None:
    """Checking each final path component (`Path.is_symlink()`, reparse attributes) misses a
    junction HIGHER UP the path, which redirects everything below it. The path the OS reports
    for the opened handle reveals it."""
    real_parent = tmp_path / "real-parent"
    (real_parent / "safety").mkdir(parents=True)
    linked_parent = tmp_path / "linked-parent"
    _junction(linked_parent, real_parent)
    with pytest.raises(console_control.ControlTokenPermissionError, match="redirects"):
        console_control.write_control_token(
            linked_parent / "safety", pid=4242, port=8189, capability="paper-exit"
        )
    console_control.write_control_token(
        real_parent / "safety", pid=4242, port=8190, capability="paper-exit"
    )
    with pytest.raises(console_control.ControlTokenPermissionError, match="redirects"):
        console_control.read_control_token(
            linked_parent / "safety",
            port=8190,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


@_WINDOWS_ONLY
def test_process_identity_and_exit_are_observed_on_the_process_handle() -> None:
    """A handle keeps referring to the original process object, so its start time and its
    exit cannot be confused with a later process that reuses the PID; an exited process's
    start time is never reported as a live identity."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])  # noqa: S603
    handle = console_control.open_process_for_shutdown(child.pid)
    try:
        assert console_control.process_handle_fingerprint(
            handle
        ) == console_control.process_start_fingerprint(child.pid)
        assert console_control.process_handle_fingerprint(handle) != _SELF_FINGERPRINT
        assert console_control.windows_process_is_running(child.pid)
        assert console_control.wait_for_process_exit(handle, timeout_seconds=0.05) is False
        assert console_control.wait_for_process_exit(handle, timeout_seconds=20) is True
    finally:
        console_control.close_process_handle(handle)
    child.wait()
    assert not console_control.windows_process_is_running(child.pid)
    with pytest.raises(RuntimeError):
        console_control.process_start_fingerprint(child.pid)


@_WINDOWS_ONLY
def test_the_native_listener_table_finds_this_process_on_ipv4_and_ipv6_loopback() -> None:
    import socket

    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as v4,
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as v6,
    ):
        v4.bind(("127.0.0.1", 0))
        v4.listen(1)
        v6.bind(("::1", 0))
        v6.listen(1)
        assert ("127.0.0.1", _SELF_PID) in console_control.windows_tcp_listeners(
            v4.getsockname()[1]
        )
        assert ("::1", _SELF_PID) in console_control.windows_tcp_listeners(v6.getsockname()[1])
        free = v4.getsockname()[1]
    assert console_control.windows_tcp_listeners(free) == []


def test_network_order_port_conversion() -> None:
    assert console_control.socket_port_from_network_order(0x0000_901F) == 8080
    assert console_control.socket_port_from_network_order(0xABCD_1F90) == 0x901F


def test_write_rejects_a_symlinked_console_control_directory(tmp_path: Path) -> None:
    real_target = tmp_path / "elsewhere"
    real_target.mkdir()
    linked = tmp_path / "console-control"
    try:
        linked.symlink_to(real_target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not permit creating symlinks")
    with pytest.raises(console_control.ControlTokenPermissionError, match="symlink"):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")


def test_write_rejects_a_windows_junction_planted_at_the_console_control_directory(
    tmp_path: Path,
) -> None:
    """MILESTONE-098 FINAL HARDENING: `Path.is_symlink()` does NOT detect an NTFS junction
    (`IO_REPARSE_TAG_MOUNT_POINT` -- a different reparse tag than a symlink's
    `IO_REPARSE_TAG_SYMLINK`); the assertion on `is_symlink()` below is this test's own
    proof of the gap this closes. A junction requires no elevated privilege to create,
    unlike a symlink, making it the MORE practical attack a lower-privileged co-resident
    process could mount."""
    if os.name != "nt":
        pytest.skip("NTFS junctions are a Windows-only concept")
    real_target = tmp_path / "elsewhere"
    real_target.mkdir()
    linked = tmp_path / "console-control"
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
        ["cmd", "/c", "mklink", "/J", str(linked), str(real_target)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"this environment could not create an NTFS junction: {result.stderr}")
    assert not linked.is_symlink(), (
        "this test's premise requires a junction that Path.is_symlink() misses entirely"
    )
    with pytest.raises(console_control.ControlTokenPermissionError, match="reparse point"):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")


def test_write_rejects_a_windows_junction_planted_at_the_safety_directory(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("NTFS junctions are a Windows-only concept")
    real_target = tmp_path / "real-safety"
    real_target.mkdir()
    linked_safety = tmp_path / "linked-safety"
    result = subprocess.run(  # noqa: S603 - fixed executable, explicit argument vector
        ["cmd", "/c", "mklink", "/J", str(linked_safety), str(real_target)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"this environment could not create an NTFS junction: {result.stderr}")
    with pytest.raises(console_control.ControlTokenPermissionError, match="reparse point"):
        console_control.write_control_token(
            linked_safety, pid=4242, port=8189, capability="paper-exit"
        )


def test_create_token_text_exclusively_fails_closed_if_something_already_exists(
    tmp_path: Path,
) -> None:
    """MILESTONE-098 FINAL HARDENING: the token temp file is now created with the OS's own
    exclusive-create guarantee (`O_EXCL` on POSIX, `CREATE_NEW` on Windows) specifically so
    a file planted at that exact name in the TOCTOU window between an earlier symlink check
    and the write cannot be silently written through or over. Exercises the low-level
    helper directly, independent of any ACL side effect `write_control_token`'s own
    directory-narrowing step could otherwise have on a pre-existing file's permissions."""
    path = tmp_path / "token.json"
    path.write_text("pre-existing-content", encoding="utf-8")
    with pytest.raises(console_control.ControlTokenPermissionError):
        console_control._create_token_text_exclusively(
            path,
            "attacker-controlled-overwrite",
            label="test file",
            user_sid=console_control._current_windows_user_sid() if os.name == "nt" else "",
        )
    assert path.read_text(encoding="utf-8") == "pre-existing-content"


def test_write_fails_closed_without_deleting_a_file_it_never_created(tmp_path: Path) -> None:
    """The end-to-end version of the test above: `write_control_token` itself must not
    unlink a pre-existing file at the temp-file path that its OWN exclusive-create step
    refused to touch -- only a temp file THIS call actually created is ever cleaned up."""
    directory = tmp_path / "console-control"
    directory.mkdir(parents=True)
    temp_path = directory / f"paper-exit-8189.json.{os.getpid()}.tmp"
    temp_path.write_text("attacker-planted-content", encoding="utf-8")
    with pytest.raises(console_control.ControlTokenPermissionError):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    assert temp_path.exists(), "a file this call never created must survive untouched"


def test_read_without_toctou_rejects_a_symlink_via_a_single_open(tmp_path: Path) -> None:
    """MILESTONE-098 FINAL HARDENING: proves the LOW-LEVEL read helper alone -- without
    relying on any earlier, separate `_reject_if_symlink` call -- refuses a symlink. This is
    what actually closes the TOCTOU window: the check and the read happen on the exact same
    open, so there is no separate second lookup for a swap to race against."""
    decoy = tmp_path / "decoy.json"
    decoy.write_text("{}", encoding="utf-8")
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(decoy)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not permit creating symlinks")
    with pytest.raises(console_control.ControlTokenPermissionError, match="reparse point"):
        console_control._read_token_text_without_toctou(linked, label="test file")


def test_write_rejects_a_symlinked_token_file_planted_in_advance(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy.json"
    decoy.write_text("{}", encoding="utf-8")
    path = console_control.control_token_path(tmp_path, port=8189)
    path.parent.mkdir(parents=True)
    try:
        path.symlink_to(decoy)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not permit creating symlinks")
    with pytest.raises(console_control.ControlTokenPermissionError, match="symlink"):
        console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")


def test_read_rejects_a_symlinked_token_file(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy.json"
    decoy.write_text(
        json.dumps(
            {
                "pid": 4242,
                "port": 8189,
                "capability": "paper-exit",
                "started_utc": "2026-01-01T00:00:00+00:00",
                "start_fingerprint": _SELF_FINGERPRINT,
                "token": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    path = console_control.control_token_path(tmp_path, port=8189)
    path.parent.mkdir(parents=True)
    try:
        path.symlink_to(decoy)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not permit creating symlinks")
    with pytest.raises(console_control.ControlTokenPermissionError, match="symlink"):
        console_control.read_control_token(
            tmp_path,
            port=8189,
            expected_capability="paper-exit",
            expected_pid=4242,
            expected_start_fingerprint=_SELF_FINGERPRINT,
        )


def test_process_start_fingerprint_is_stable_for_the_same_process(tmp_path: Path) -> None:
    del tmp_path
    first = console_control.process_start_fingerprint(_SELF_PID)
    second = console_control.process_start_fingerprint(_SELF_PID)
    assert first == second


def test_process_start_fingerprint_raises_for_a_pid_that_does_not_exist() -> None:
    # A PID vanishingly unlikely to be in use on any machine running this test.
    with pytest.raises(RuntimeError):
        console_control.process_start_fingerprint(2**30 - 1)


# ---------------------------------------------------------------------------------------
# Router.service_post: the dispatch rule the console's `/control/shutdown` route relies on.
# ---------------------------------------------------------------------------------------


def _wsgi_call(
    router: Router,
    *,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    remote_addr: str = "127.0.0.1",
) -> tuple[str, list[tuple[str, str]], bytes]:
    """`remote_addr` defaults to loopback: a real `wsgiref` server always populates
    `REMOTE_ADDR` for an actually-accepted connection, and defaulting it here to what a
    genuine local caller would present keeps every pre-existing test realistic. Tests of the
    MILESTONE-098 isolation hardening override it explicitly."""
    environ: dict[str, object] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "REMOTE_ADDR": remote_addr,
    }
    for key, value in (headers or {}).items():
        environ[f"HTTP_{key.upper().replace('-', '_')}"] = value
    captured: dict[str, object] = {}

    def start_response(status: str, response_headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = response_headers

    body = b"".join(router(environ, start_response))
    return captured["status"], captured["headers"], body  # type: ignore[return-value]


def test_service_post_calls_the_handler_when_authorized() -> None:
    router = Router(SecuritySession())
    calls: list[str] = []

    def handler(request: Request, csrf: str) -> Response:
        del request, csrf
        calls.append("called")
        return html_response("<p>ok</p>")

    router.service_post("/control/shutdown", handler, authorize=lambda request: True)
    status, headers, body = _wsgi_call(router, method="POST", path="/control/shutdown")
    assert status == "200 OK"
    assert calls == ["called"]
    assert b"ok" in body
    assert not any(name == "Set-Cookie" for name, _ in headers)


def test_service_post_refuses_without_calling_the_handler_when_unauthorized() -> None:
    router = Router(SecuritySession())
    calls: list[str] = []

    def handler(request: Request, csrf: str) -> Response:
        del request, csrf
        calls.append("called")
        return html_response("<p>ok</p>")

    router.service_post("/control/shutdown", handler, authorize=lambda request: False)
    status, _headers, _body = _wsgi_call(router, method="POST", path="/control/shutdown")
    assert status == "401 Unauthorized"
    assert calls == []


def test_service_post_never_requires_a_csrf_token_or_session_cookie() -> None:
    """The caller is a local tool process, not a browser -- there is no session for it to
    carry a CSRF token in, unlike every other POST route this console serves."""
    router = Router(SecuritySession())

    def handler(request: Request, csrf: str) -> Response:
        del request, csrf
        return html_response("<p>ok</p>")

    seen_headers: list[dict[str, str]] = []

    def authorize(request: Request) -> bool:
        seen_headers.append(dict(request.headers))
        return request.headers.get("x-empirical-shutdown-token") == "right-token"

    router.service_post("/control/shutdown", handler, authorize=authorize)
    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "right-token"},
    )
    assert status == "200 OK"
    assert "csrf_token" not in seen_headers[0]


# ---------------------------------------------------------------------------------------
# operator_console._install_shutdown_control: the real wiring, against a fake server
# object (no real socket -- real OS process/port mechanics are covered by the Windows-only
# integration file).
# ---------------------------------------------------------------------------------------


class _FakeServer:
    def __init__(self, port: int) -> None:
        self.server_port = port
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_install_shutdown_control_writes_a_token_naming_this_process(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )
    assert record.port == 8189


def test_install_shutdown_control_route_requires_the_exact_token(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]

    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "definitely-wrong"},
    )
    assert status == "401 Unauthorized"
    assert server.shutdown_calls == 0


def test_install_shutdown_control_accepts_the_real_token_and_shuts_down_async(
    tmp_path: Path,
) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )

    status, _headers, body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": record.token},
    )
    assert status == "202 Accepted"
    payload = json.loads(body)
    assert payload == {"accepted": True, "pid": operator_console.os.getpid()}

    # `server.shutdown()` is started on a background thread so the HTTP response can be
    # sent first (see the function's own docstring for why calling it synchronously, on
    # the same thread handling this request, would be the correct-but-irrelevant-here
    # deadlock case `BaseServer.shutdown()`'s own docs warn about).
    deadline = time.monotonic() + 2.0
    while server.shutdown_calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.shutdown_calls == 1


def test_install_shutdown_control_does_not_activate_when_permission_narrowing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MILESTONE-098 SECURITY HARDENING: an ACL/permission failure must prevent the
    shutdown route from EVER being reachable -- not merely from succeeding once reached. A
    request to `/control/shutdown` must now fall through to the ordinary "not found" / CSRF
    handling, with the route entirely absent from the Router's dispatch table."""

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise console_control.ControlTokenPermissionError("permission narrowing unavailable here")

    monkeypatch.setattr(console_control, "_create_owner_only_directory", _boom)
    monkeypatch.setattr(
        console_control.Path,
        "chmod",
        lambda self, mode: (_ for _ in ()).throw(OSError("chmod refused")),
    )
    router = Router(SecuritySession())
    server = _FakeServer(8189)

    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]

    assert ("POST", "/control/shutdown") not in router._service_routes  # noqa: SLF001
    assert not console_control.control_token_path(tmp_path, port=8189).exists()
    status, _headers, _body = _wsgi_call(router, method="POST", path="/control/shutdown")
    assert status != "202 Accepted"
    assert server.shutdown_calls == 0


def test_shutdown_route_rejects_a_request_with_no_token_header_at_all(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]

    status, _headers, _body = _wsgi_call(router, method="POST", path="/control/shutdown")
    assert status == "401 Unauthorized"
    assert server.shutdown_calls == 0


def test_shutdown_route_rejects_a_wrong_token_and_console_keeps_running(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]

    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "wrong-token-entirely"},
    )
    assert status == "401 Unauthorized"
    assert server.shutdown_calls == 0
    # The console is still answering: a second, correctly-authorized request still succeeds.
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )
    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": record.token},
    )
    assert status == "202 Accepted"


def test_shutdown_route_rejects_a_stale_token_file_left_by_an_earlier_instance(
    tmp_path: Path,
) -> None:
    """A control-token file from a PREVIOUS instance that bound the same port (e.g. an
    unclean exit) must never authorize a request against the NEW instance -- the new
    instance's own in-memory token is unrelated to whatever token the stale file names."""
    stale_path = console_control.control_token_path(tmp_path, port=8189)
    stale_path.parent.mkdir(parents=True)
    stale_payload = {
        "pid": 999999,
        "port": 8189,
        "capability": operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        "started_utc": "2020-01-01T00:00:00+00:00",
        "start_fingerprint": "stale-fingerprint-from-a-process-long-gone",
        "token": "stale-token-value",
    }
    stale_path.write_text(json.dumps(stale_payload), encoding="utf-8")

    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]

    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "stale-token-value"},
    )
    assert status == "401 Unauthorized"
    assert server.shutdown_calls == 0


def test_shutdown_route_rejects_a_request_whose_remote_addr_is_not_loopback(
    tmp_path: Path,
) -> None:
    """MILESTONE-098 SECURITY HARDENING: isolation from Tailscale/a reverse proxy. Even a
    CORRECT token is refused if the WSGI server itself did not observe this connection as
    coming from loopback -- a defense-in-depth layer independent of (and in addition to) the
    launcher's own `--host` loopback-only refusal."""
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )

    for remote_addr in ("10.0.0.7", "100.64.12.3", "203.0.113.5"):
        status, _headers, _body = _wsgi_call(
            router,
            method="POST",
            path="/control/shutdown",
            headers={"X-Empirical-Shutdown-Token": record.token},
            remote_addr=remote_addr,
        )
        assert status == "401 Unauthorized", remote_addr
    assert server.shutdown_calls == 0


def test_shutdown_route_rejects_a_request_carrying_a_forwarding_header(tmp_path: Path) -> None:
    """MILESTONE-098 SECURITY HARDENING: a request that LOOKS like it arrived on loopback
    (e.g. a local reverse proxy or a Tailscale `serve`/`funnel` listener that itself connects
    via 127.0.0.1) but carries a forwarding header is refused -- a direct local caller (the
    deployment tool) never sends any of these."""
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )

    for forwarding_header in (
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Real-Ip",
        "Forwarded",
        "Via",
    ):
        status, _headers, _body = _wsgi_call(
            router,
            method="POST",
            path="/control/shutdown",
            headers={
                "X-Empirical-Shutdown-Token": record.token,
                forwarding_header: "203.0.113.5",
            },
        )
        assert status == "401 Unauthorized", forwarding_header
    assert server.shutdown_calls == 0

    # The same token, with no forwarding header and a genuine loopback REMOTE_ADDR, still
    # works -- the hardening above adds a check, it does not break the legitimate caller.
    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": record.token},
    )
    assert status == "202 Accepted"


def test_shutdown_route_answers_401_not_500_for_a_non_ascii_token(tmp_path: Path) -> None:
    """M098-R: `hmac.compare_digest` raises TypeError on a str holding non-ASCII characters,
    which turned a malformed header into an unhandled server error. Compared as bytes, it is
    simply a wrong token."""
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "tökén-☃"},
    )
    assert status == "401 Unauthorized"
    assert server.shutdown_calls == 0


def test_a_repeated_authenticated_shutdown_request_starts_only_one_shutdown(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
        expected_start_fingerprint=_SELF_FINGERPRINT,
    )
    for _attempt in range(3):
        status, _headers, _body = _wsgi_call(
            router,
            method="POST",
            path="/control/shutdown",
            headers={"X-Empirical-Shutdown-Token": record.token},
        )
        assert status == "202 Accepted"
    time.sleep(0.3)
    assert server.shutdown_calls == 1
