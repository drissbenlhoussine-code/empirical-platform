"""MILESTONE-086 -- `empirical-platform-operator-console`: start the Operator Console.

    empirical-platform-operator-console                 # serve on http://127.0.0.1:8086 and open it
    empirical-platform-operator-console --load-day      # also stage the simulation day at start
    empirical-platform-operator-console --no-browser --port 8090

SIMULATION ONLY. The console composes the deterministic simulated broker and nothing else;
no Alpaca credential is read and no order can reach any venue. It binds to the loopback
address and refuses any other host. One process serves the pages and, in the background,
asks the simulated broker about every open execution through the MILESTONE-085 reconciler,
so Active trades moves from Submitted to Accepted to Filled without shell interaction.

ONE CONSOLE PER STATE DIRECTORY. The simulation state directory is locked with an
operating-system file lock before anything else is opened; a second console started on the
same directory is refused with exit code 2 before it can read or mutate simulation state.

SHUTDOWN ORDER. On Ctrl+C the server stops accepting requests, the background reconciler is
signalled AND joined -- for as long as its pass in flight takes; there is no "close anyway" --
and only then are the server, the PostgreSQL service and the state lock released. No
repository or service is closed while the reconciler thread is alive.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

from empirical_platform.entrypoints._operator_console_web import SecuritySession, serve
from empirical_platform.entrypoints._position_exit_composition import (
    simulation_exit_console_runtime,
)
from empirical_platform.entrypoints.operator_console_app import build_application
from empirical_platform.shared.brokerage.simulation_paper import SimulationStateLockedError

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8086
DEFAULT_STATE_DIR = Path.home() / ".empirical-platform" / "operator-console"
RECONCILER_JOIN_REPORT_INTERVAL_SECONDS = 30.0  # diagnostics only; never permits teardown


def _loopback(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise SystemExit(
            f"REFUSED: --host must be a loopback IP address such as {DEFAULT_HOST}; got {host!r}"
        ) from error
    if not address.is_loopback:
        raise SystemExit(
            f"REFUSED: the Operator Console binds to the loopback address only; {host!r} is not "
            "loopback. It must not be exposed beyond this machine."
        )
    return host


class _Reconciler(threading.Thread):
    """Ask the broker about open executions every few seconds, until stopped and joined."""

    def __init__(self, refresh: Callable[[], object], interval: float) -> None:
        super().__init__(name="operator-console-reconciler", daemon=True)
        self._refresh = refresh
        self._interval = interval
        self._stop = threading.Event()
        self.passes = 0

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._refresh()
            except Exception as error:  # noqa: BLE001 - keep reconciling; the handler recorded it
                print(
                    f"operator-console: reconciliation pass failed: {type(error).__name__}",
                    file=sys.stderr,
                )
            finally:
                self.passes += 1

    def stop(self, *, report_every: float = RECONCILER_JOIN_REPORT_INTERVAL_SECONDS) -> None:
        """Signal the loop and JOIN it until the thread has actually terminated.

        Called before the server, the runtime and its PostgreSQL service are closed, so a pass
        in flight completes its M085 handler call against an open service and no pass can start
        against a closed one. There is no timeout that permits teardown: `report_every` only
        governs how often a still-running pass is reported on stderr while we keep waiting. A
        KeyboardInterrupt during the wait is reported and the wait continues -- the database must
        not be closed under a running reconciliation.
        """
        self._stop.set()
        while self.is_alive():
            try:
                self.join(timeout=report_every)
            except KeyboardInterrupt:
                print(
                    "operator-console: still waiting for the reconciliation pass in flight; "
                    "the database is not closed while it runs",
                    file=sys.stderr,
                )
                continue
            if self.is_alive():
                print(
                    "operator-console: waiting for the reconciliation pass in flight "
                    f"({report_every:.0f}s and counting); nothing is closed until it finishes",
                    file=sys.stderr,
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="loopback address to bind (default 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default 8086)")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="where the simulated broker keeps its durable state "
        "(default ~/.empirical-platform/operator-console)",
    )
    parser.add_argument(
        "--load-day", action="store_true", help="stage the deterministic simulation day at start"
    )
    parser.add_argument(
        "--reset-simulation",
        action="store_true",
        help="forget the simulated broker's orders first",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument(
        "--reconcile-every",
        type=float,
        default=5.0,
        help="seconds between background reconciliation passes (0 disables)",
    )
    arguments = parser.parse_args(argv)
    host = _loopback(arguments.host)

    try:
        # MILESTONE-087: this launcher composes the console WITH the exit path, so it requires
        # the exact M087 schema head (the M086 runtime would require the M085 head).
        with simulation_exit_console_runtime(state_dir=arguments.state_dir) as runtime:
            if arguments.reset_simulation:
                runtime.store.reset()
            if arguments.load_day:
                report = runtime.load_day()
                print(
                    f"simulation day {report.day}: proposed "
                    f"{', '.join(report.proposed) or 'nothing'}; already present "
                    f"{', '.join(report.already_present) or 'nothing'}"
                )
            application = build_application(runtime, security=SecuritySession())
            reconciler: _Reconciler | None = None
            try:
                if arguments.reconcile_every > 0:
                    reconciler = _Reconciler(
                        runtime.service.refresh_executions, arguments.reconcile_every
                    )
                    reconciler.start()
                with serve(application, host=host, port=arguments.port) as server:
                    url = f"http://{host}:{server.server_port}/today"
                    print("=" * 72)
                    print("  OPERATOR CONSOLE -- SIMULATION ONLY. No order can reach any venue.")
                    print(f"  Open {url}")
                    print("  Paper execution locked -- acceptance pending. Live -- not authorized.")
                    print("  Press Ctrl+C to stop.")
                    print("=" * 72, flush=True)
                    if not arguments.no_browser:
                        webbrowser.open(url)
                    try:
                        server.serve_forever(poll_interval=0.5)
                    except KeyboardInterrupt:
                        print("\noperator-console: stopping")
                    finally:
                        # Order matters: no new requests, then the reconciler is stopped AND
                        # joined until it has terminated, and only after that does the server
                        # close and the runtime's service and lock release.
                        if reconciler is not None:
                            reconciler.stop()
            finally:
                # Also holds if the server never started (port in use, Ctrl+C during startup):
                # the runtime context below cannot exit while the reconciler is alive.
                if reconciler is not None:
                    reconciler.stop()
    except SimulationStateLockedError as refused:
        print(f"REFUSED: {refused}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
