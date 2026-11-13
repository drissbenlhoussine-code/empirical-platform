"""Authenticated graceful stop of the PERSONAL PAPER console (M101 closure).

The same call path deploy step 5 uses (`RealProcessPort.graceful_stop`, M098): confirm which
process owns the console port, verify that process's identity, read the per-instance control token
from the safety directory, `POST /control/shutdown` to loopback only, then wait for that exact
process to exit. The console runs its normal shutdown (reconciler joined, Plan Manager stopped,
token removed, database closed) and exits 64 ("deliberate shutdown, do not restart").

It starts nothing, creates no maintenance hold, migrates nothing and never signals any process
other than the verified owner of the port. It works for the normal and the recovery-mode console.

    python tools\\stop_paper_console.py --check      # who owns 8189? changes nothing
    python tools\\stop_paper_console.py              # stop it

Exit codes: 0 stopped (or --check succeeded); 2 refused or failed (nothing was stopped); 3 nothing
is listening; 4 the request was accepted but the process did not exit in time.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

from tools.personal_paper_deploy import (
    ConsoleShutdownError,
    NetworkPort,
    ProcessPort,
    RealNetworkPort,
    RealProcessPort,
)

from empirical_platform.shared.persistence.database_safety import manifest_path

EXIT_STOPPED: Final = 0
EXIT_REFUSED: Final = 2
EXIT_NOT_RUNNING: Final = 3
EXIT_TIMEOUT: Final = 4


def stop_console(
    *,
    host: str,
    port: int,
    safety_directory: Path,
    network: NetworkPort,
    process: ProcessPort,
    timeout_seconds: float = 90.0,
    check_only: bool = False,
    out: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    try:
        owner = network.owning_pid(host, port)
    except RuntimeError as error:
        out(f"REFUSED: could not determine what is listening on {host}:{port}: {error}")
        return EXIT_REFUSED
    if owner is None:
        out(f"No console is listening on {host}:{port}. Nothing to stop.")
        return EXIT_NOT_RUNNING
    out(f"Console listener on {host}:{port}: PID {owner}")
    if check_only:
        return EXIT_STOPPED
    # Re-confirm immediately before acting (closes the discovery-to-signal window, as step 5 does).
    try:
        reconfirmed = network.owning_pid(host, port)
    except RuntimeError as error:
        out(f"REFUSED: could not re-confirm the listener on {host}:{port}: {error}")
        return EXIT_REFUSED
    if reconfirmed != owner:
        out(
            f"REFUSED: the listener on {host}:{port} changed from PID {owner} to "
            f"{reconfirmed!r} while checking; nothing was signalled."
        )
        return EXIT_REFUSED
    try:
        process.graceful_stop(owner, host=host, port=port, safety_directory=safety_directory)
    except ConsoleShutdownError as error:
        out(f"REFUSED: {error}. Nothing was stopped.")
        return EXIT_REFUSED
    out(f"Authenticated shutdown request accepted by PID {owner}; waiting for it to exit.")
    deadline = monotonic() + timeout_seconds
    while process.is_running(owner):
        if monotonic() >= deadline:
            out(
                f"PID {owner} accepted the request but is still running after {timeout_seconds:g}s."
            )
            return EXIT_TIMEOUT
        sleep(0.5)
    out(f"PID {owner} has exited. The console is stopped.")
    return EXIT_STOPPED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8189)
    parser.add_argument(
        "--safety-directory",
        type=Path,
        default=None,
        help="where the console wrote its control token (default: the Safety Manifest's directory)",
    )
    parser.add_argument("--timeout", type=float, default=90.0, help="seconds to wait for the exit")
    parser.add_argument("--check", action="store_true", help="only report the port owner")
    arguments = parser.parse_args(argv)
    return stop_console(
        host=arguments.host,
        port=arguments.port,
        safety_directory=arguments.safety_directory or manifest_path().parent,
        network=RealNetworkPort(),
        process=RealProcessPort(),
        timeout_seconds=arguments.timeout,
        check_only=arguments.check,
    )


if __name__ == "__main__":
    sys.exit(main())
