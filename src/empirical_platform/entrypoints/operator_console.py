"""MILESTONE-086/088 -- `empirical-platform-operator-console`: start the Operator Console.

    empirical-platform-operator-console                 # SIMULATION: serve on http://127.0.0.1:8086
    empirical-platform-operator-console --load-day      # also stage the simulation day at start
    empirical-platform-operator-console --no-browser --port 8090
    empirical-platform-operator-console --capability paper   # PAPER: real Alpaca paper endpoint

SIMULATION IS THE DEFAULT (MILESTONE-088 Phase 6): `--capability` defaults to `simulation`
and every existing flag and behaviour below is unchanged for it. `--capability paper`
composes over Store B instead (`entrypoints._paper_operator_console_composition`) -- the
same real Alpaca-credentialed context `tools/m085_paper_acceptance.py` uses -- and refuses
`--load-day`/`--reset-simulation`, which have no PAPER meaning. No `--capability live`
exists: there is no composition path in this repository that can build one. It binds to
the loopback address only and refuses any
other host, in both capabilities. One process serves the pages and, in the background, asks
the broker (simulated, or the real Alpaca paper endpoint) about every open execution through
the MILESTONE-085 reconciler, so Active trades moves from Submitted to Accepted to Filled
without shell interaction.

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
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.entrypoints._operator_console_web import SecuritySession, serve
from empirical_platform.entrypoints._paper_operator_console_composition import (
    paper_operator_console_runtime,
)
from empirical_platform.entrypoints._paper_position_exit_composition import (
    paper_operator_console_with_exit_runtime,
)
from empirical_platform.entrypoints._position_exit_composition import (
    simulation_exit_console_runtime,
)
from empirical_platform.entrypoints.operator_console_app import build_application
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.shared.brokerage.simulation_paper import SimulationStateLockedError
from empirical_platform.usecases.position_plan_manager import PlanManagerThread, PositionPlanManager

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8086
DEFAULT_STATE_DIR = Path.home() / ".empirical-platform" / "operator-console"
RECONCILER_JOIN_REPORT_INTERVAL_SECONDS = 30.0  # diagnostics only; never permits teardown


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


def _serve_with_reconciler(
    application: Callable[..., Iterable[bytes]],
    *,
    refresh: Callable[[], object],
    host: str,
    port: int,
    no_browser: bool,
    reconcile_every: float,
    banner: tuple[str, ...],
    plan_manager: PositionPlanManager | None = None,
    base_path: str = "",
) -> None:
    """Shared by both capabilities: start the reconciler, serve, and shut down in order.

    Order matters, in both capabilities alike: no new requests, then the reconciler is
    stopped AND joined until it has actually terminated, and only THEN does the server close
    and the composition's own service, persistence and lock release -- no repository or
    broker client is closed while a reconciliation pass (which calls it) is still running.

    RELEASE v1: when `plan_manager` is given (only `--capability paper-exit`'s composition
    builds one), its `PlanManagerThread` starts and stops alongside the reconciler, inside
    THIS SAME process -- never a second process -- so any `ApprovedPlan` the Owner approves
    begins being monitored immediately, with no separate manual step.
    """
    reconciler: _Reconciler | None = None
    manager_thread: PlanManagerThread | None = None
    try:
        if reconcile_every > 0:
            reconciler = _Reconciler(refresh, reconcile_every)
            reconciler.start()
        if plan_manager is not None:
            manager_thread = PlanManagerThread(plan_manager, now=_utc_now)
            manager_thread.start()
        with serve(application, host=host, port=port) as server:
            # Direct/local URL is always unprefixed, same reasoning as the Opportunity
            # Engine's own launcher: this process only ever registers unprefixed routes (a
            # reverse proxy strips base_path before forwarding here, it never reaches this
            # process). base_path only shapes the URLs this process generates in its own pages.
            url = f"http://{host}:{server.server_port}/today"
            print("=" * 72)
            for line in banner:
                print(line)
            print(f"  Open {url}")
            if base_path:
                print(f"  Configured base path for a reverse proxy: {base_path}")
            print("  Press Ctrl+C to stop.")
            print("=" * 72, flush=True)
            if not no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever(poll_interval=0.5)
            except KeyboardInterrupt:
                print("\noperator-console: stopping")
            finally:
                if reconciler is not None:
                    reconciler.stop()
                if manager_thread is not None:
                    manager_thread.stop()
    finally:
        # Also holds if the server never started (port in use, Ctrl+C during startup): the
        # composition's own context manager cannot exit while the reconciler is alive.
        if reconciler is not None:
            reconciler.stop()
        if manager_thread is not None:
            manager_thread.stop()


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
        "(default ~/.empirical-platform/operator-console); SIMULATION only",
    )
    parser.add_argument(
        "--capability",
        choices=("simulation", "paper", "paper-exit"),
        default="simulation",
        help="SIMULATION (default), PAPER (MILESTONE-088, real Alpaca paper endpoint, no exit "
        "path) or paper-exit (MILESTONE-089, PAPER plus SELL_TO_CLOSE over Store B + Store "
        "C). There is no 'live' choice: no composition path in this repository can build one.",
    )
    parser.add_argument(
        "--load-day",
        action="store_true",
        help="stage the deterministic simulation day at start; SIMULATION only",
    )
    parser.add_argument(
        "--reset-simulation",
        action="store_true",
        help="forget the simulated broker's orders first; SIMULATION only",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument(
        "--reconcile-every",
        type=float,
        default=5.0,
        help="seconds between background reconciliation passes (0 disables)",
    )
    parser.add_argument(
        "--base-path",
        default="",
        help="path prefix this console is reverse-proxied under, e.g. /paper (default: none, "
        "i.e. root behaviour) -- mirrors the Opportunity Engine's own --base-path exactly. "
        "Only shapes the URLs this process generates in its own pages; routes always register "
        "unprefixed because a reverse proxy strips the prefix before forwarding here.",
    )
    arguments = parser.parse_args(argv)
    host = _loopback(arguments.host)
    try:
        base_path = html.validate_base_path(arguments.base_path)
    except ValueError as error:
        raise SystemExit(f"REFUSED: {error}") from error

    if arguments.capability in ("paper", "paper-exit"):
        if arguments.load_day or arguments.reset_simulation:
            print(
                f"REFUSED: --load-day and --reset-simulation have no meaning for "
                f"--capability {arguments.capability}. Nothing was started.",
                file=sys.stderr,
            )
            return 2
        if arguments.capability == "paper-exit":
            # MILESTONE-089: the ONLY difference from --capability paper is which composition
            # function opens Store C alongside Store B and wires the exit console; the routes,
            # the app and the banner's first two lines are otherwise identical.
            with paper_operator_console_with_exit_runtime() as backend:
                application = build_paper_application(
                    backend, security=SecuritySession(), base_path=base_path
                )
                _serve_with_reconciler(
                    application,
                    refresh=backend.service.refresh_executions,
                    host=host,
                    port=arguments.port,
                    no_browser=arguments.no_browser,
                    reconcile_every=arguments.reconcile_every,
                    banner=(
                        "  OPERATOR CONSOLE -- PAPER. Orders reach the real Alpaca PAPER "
                        "endpoint only.",
                        "  Not real money. Every submission requires explicit Owner approval.",
                        "  MILESTONE-089: SELL_TO_CLOSE is enabled for attributable PAPER "
                        "positions.",
                        "  RELEASE v1: an Owner-approved full plan is managed automatically "
                        "(stop/target/mandatory exit) -- see /safety.",
                        "  Live -- not authorized.",
                    ),
                    plan_manager=backend._plan_manager,
                    base_path=base_path,
                )
            return 0
        with paper_operator_console_runtime() as backend:
            application = build_paper_application(
                backend, security=SecuritySession(), base_path=base_path
            )
            _serve_with_reconciler(
                application,
                refresh=backend.service.refresh_executions,
                host=host,
                port=arguments.port,
                no_browser=arguments.no_browser,
                reconcile_every=arguments.reconcile_every,
                banner=(
                    "  OPERATOR CONSOLE -- PAPER. Orders reach the real Alpaca PAPER "
                    "endpoint only.",
                    "  Not real money. Every submission requires explicit Owner approval.",
                    "  Live -- not authorized.",
                ),
                base_path=base_path,
            )
        return 0

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
            application = build_application(
                runtime, security=SecuritySession(), base_path=base_path
            )
            _serve_with_reconciler(
                application,
                refresh=runtime.service.refresh_executions,
                host=host,
                port=arguments.port,
                no_browser=arguments.no_browser,
                reconcile_every=arguments.reconcile_every,
                banner=(
                    "  OPERATOR CONSOLE -- SIMULATION ONLY. No order can reach any venue.",
                    "  Paper execution locked -- acceptance pending. Live -- not authorized.",
                ),
                base_path=base_path,
            )
    except SimulationStateLockedError as refused:
        print(f"REFUSED: {refused}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
